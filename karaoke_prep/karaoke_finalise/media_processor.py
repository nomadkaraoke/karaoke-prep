import os
import shlex
import logging
import sys
import subprocess
import shutil
import tempfile

from karaoke_prep.karaoke_finalise.mediainfo_parser import MediaInfoParser


class MediaProcessor:
    def __init__(self, logger=None, dry_run=False, log_level=logging.INFO, non_interactive=False):
        self.logger = logger or logging.getLogger(__name__)
        self.dry_run = dry_run
        self.log_level = log_level
        self.non_interactive = non_interactive
        
        # Path to the Windows PyInstaller frozen bundled ffmpeg.exe, or the system-installed FFmpeg binary on Mac/Linux
        ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg.exe") if getattr(sys, "frozen", False) else "ffmpeg"

        self.ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"

        if self.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"
            
        # MP4 output flags for better compatibility and streaming
        self.mp4_flags = "-pix_fmt yuv420p -movflags +faststart+frag_keyframe+empty_moov"
        
        # Update ffmpeg base command to include -y if non-interactive
        if self.non_interactive:
            self.ffmpeg_base_command += " -y"
            
        # Determine best available AAC codec
        self.aac_codec = self.detect_best_aac_codec()

        self.mediainfo_parser = MediaInfoParser(logger=logger)

    def execute_command(self, command, description):
        self.logger.info(description)
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would run command: {command}")
        else:
            self.logger.info(f"Running command: {command}")
            os.system(command)

    def detect_best_aac_codec(self):
        """Detect the best available AAC codec (aac_at > libfdk_aac > aac)"""
        self.logger.info("Detecting best available AAC codec...")

        codec_check_command = f"{self.ffmpeg_base_command} -codecs"
        result = os.popen(codec_check_command).read()

        if "aac_at" in result:
            self.logger.info("Using aac_at codec (best quality)")
            return "aac_at"
        elif "libfdk_aac" in result:
            self.logger.info("Using libfdk_aac codec (good quality)")
            return "libfdk_aac"
        else:
            self.logger.info("Using built-in aac codec (basic quality)")
            return "aac"

    def remux_with_instrumental(self, with_vocals_file, instrumental_audio, output_file):
        """Remux the video with instrumental audio to create karaoke version"""
        # fmt: off
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -an -i "{with_vocals_file}" '
            f'-vn -i "{instrumental_audio}" -c:v copy -c:a pcm_s16le "{output_file}"'
        )
        # fmt: on
        self.execute_command(ffmpeg_command, "Remuxing video with instrumental audio")

    def convert_mov_to_mp4(self, input_file, output_file):
        """Convert MOV file to MP4 format"""
        # fmt: off
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -i "{input_file}" '
            f'-c:v libx264 -c:a {self.aac_codec} {self.mp4_flags} "{output_file}"'
        )
        # fmt: on
        self.execute_command(ffmpeg_command, "Converting MOV video to MP4")

    def encode_lossless_mp4(self, title_mov_file, karaoke_mp4_file, env_mov_input, ffmpeg_filter, output_file):
        """Create the final MP4 with PCM audio (lossless)"""
        # fmt: off
        ffmpeg_command = (
            f"{self.ffmpeg_base_command} -i {title_mov_file} -i {karaoke_mp4_file} {env_mov_input} "
            f'{ffmpeg_filter} -map "[outv]" -map "[outa]" -c:v libx264 -c:a pcm_s16le '
            f'{self.mp4_flags} "{output_file}"'
        )
        # fmt: on
        self.execute_command(ffmpeg_command, "Creating MP4 version with PCM audio")

    def encode_lossy_mp4(self, input_file, output_file):
        """Create MP4 with AAC audio (lossy, for wider compatibility)"""
        # fmt: off
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -i "{input_file}" '
            f'-c:v copy -c:a {self.aac_codec} -b:a 320k {self.mp4_flags} "{output_file}"'
        )
        # fmt: on
        self.execute_command(ffmpeg_command, "Creating MP4 version with AAC audio")

    def encode_lossless_mkv(self, input_file, output_file):
        """Create MKV with FLAC audio (for YouTube)"""
        # fmt: off
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -i "{input_file}" '
            f'-c:v copy -c:a flac "{output_file}"'
        )
        # fmt: on
        self.execute_command(ffmpeg_command, "Creating MKV version with FLAC audio for YouTube")

    def encode_720p_version(self, input_file, output_file):
        """Create 720p MP4 with AAC audio (for smaller file size)"""
        # fmt: off
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -i "{input_file}" '
            f'-c:v libx264 -vf "scale=1280:720" -b:v 200k -preset medium -tune animation '
            f'-c:a {self.aac_codec} -b:a 128k {self.mp4_flags} "{output_file}"'
        )
        # fmt: on
        self.execute_command(ffmpeg_command, "Encoding 720p version of the final video")

    def prepare_concat_filter(self, input_files):
        """Prepare the concat filter and additional input for end credits if present"""
        env_mov_input = ""
        ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]"'

        if "end_mov" in input_files and os.path.isfile(input_files["end_mov"]):
            self.logger.info(f"Found end_mov file: {input_files['end_mov']}, including in final MP4")
            end_mov_file = shlex.quote(os.path.abspath(input_files["end_mov"]))
            env_mov_input = f"-i {end_mov_file}"
            ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0][2:v:0][2:a:0]concat=n=3:v=1:a=1[outv][outa]"'

        return env_mov_input, ffmpeg_filter

    def remux_and_encode_output_video_files(self, with_vocals_file, input_files, output_files, user_interface=None):
        self.logger.info(f"Remuxing and encoding output video files...")

        # Check if output files already exist
        if os.path.isfile(output_files["final_karaoke_lossless_mp4"]) and os.path.isfile(output_files["final_karaoke_lossless_mkv"]):
            if user_interface and not user_interface.prompt_user_bool(
                f"Found existing Final Karaoke output files. Overwrite (y) or skip (n)?",
            ):
                self.logger.info(f"Skipping Karaoke MP4 remux and Final video renders, existing files will be used.")
                return

        # Create karaoke version with instrumental audio
        self.remux_with_instrumental(with_vocals_file, input_files["instrumental_audio"], output_files["karaoke_mp4"])

        # Convert the with vocals video to MP4 if needed
        if not with_vocals_file.endswith(".mp4"):
            self.convert_mov_to_mp4(with_vocals_file, output_files["with_vocals_mp4"])

            # Delete the with vocals mov after successfully converting it to mp4
            if not self.dry_run and os.path.isfile(with_vocals_file):
                self.logger.info(f"Deleting with vocals MOV file: {with_vocals_file}")
                os.remove(with_vocals_file)

        # Quote file paths to handle special characters
        title_mov_file = shlex.quote(os.path.abspath(input_files["title_mov"]))
        karaoke_mp4_file = shlex.quote(os.path.abspath(output_files["karaoke_mp4"]))

        # Prepare concat filter for combining videos
        env_mov_input, ffmpeg_filter = self.prepare_concat_filter(input_files)

        # Create all output versions
        self.encode_lossless_mp4(title_mov_file, karaoke_mp4_file, env_mov_input, ffmpeg_filter, output_files["final_karaoke_lossless_mp4"])
        self.encode_lossy_mp4(output_files["final_karaoke_lossless_mp4"], output_files["final_karaoke_lossy_mp4"])
        self.encode_lossless_mkv(output_files["final_karaoke_lossless_mp4"], output_files["final_karaoke_lossless_mkv"])
        self.encode_720p_version(output_files["final_karaoke_lossless_mp4"], output_files["final_karaoke_lossy_720p_mp4"])

        # Prompt user to check final video files before proceeding
        if user_interface:
            user_interface.prompt_user_confirmation_or_raise_exception(
                f"Final video files created:\n"
                f"- Lossless 4K MP4: {output_files['final_karaoke_lossless_mp4']}\n"
                f"- Lossless 4K MKV: {output_files['final_karaoke_lossless_mkv']}\n"
                f"- Lossy 4K MP4: {output_files['final_karaoke_lossy_mp4']}\n"
                f"- Lossy 720p MP4: {output_files['final_karaoke_lossy_720p_mp4']}\n"
                f"Please check them! Proceed?",
                "Refusing to proceed without user confirmation they're happy with the Final videos.",
                allow_empty=True,
            )

    def crop_video(self, input_path, output_path, crop_params):
        """
        Crop a video using FFmpeg.
        
        Args:
            input_path: Path to the input video file
            output_path: Path to save the cropped video
            crop_params: Dictionary containing crop parameters (top, bottom, left, right)
        
        Raises:
            RuntimeError: If FFmpeg command fails
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video file not found: {input_path}")
            
        # Calculate crop filter parameters
        left = crop_params.get('left', 0)
        right = crop_params.get('right', 0)
        top = crop_params.get('top', 0)
        bottom = crop_params.get('bottom', 0)
        
        crop_filter = f"crop=in_w-{left}-{right}:in_h-{top}-{bottom}:{left}:{top}"
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", crop_filter,
            "-c:v", "libx264", "-preset", "medium",
            "-c:a", "copy",
            output_path
        ]
        
        if self.logger:
            self.logger.info(f"Cropping video: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg command failed with error: {result.stderr}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def overlay_image(self, input_path, overlay_path, output_path):
        """
        Overlay an image on top of a video using FFmpeg.
        
        Args:
            input_path: Path to the input video file
            overlay_path: Path to the overlay image
            output_path: Path to save the output video
        
        Raises:
            RuntimeError: If FFmpeg command fails
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video file not found: {input_path}")
        
        if not os.path.exists(overlay_path):
            raise FileNotFoundError(f"Overlay image not found: {overlay_path}")
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path, "-i", overlay_path,
            "-filter_complex", "overlay=0:0",
            "-c:v", "libx264", "-preset", "medium",
            "-c:a", "copy",
            output_path
        ]
        
        if self.logger:
            self.logger.info(f"Overlaying image: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg command failed with error: {result.stderr}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def create_video_thumbnail(self, input_path, output_path, time_offset=5):
        """
        Create a thumbnail from a video at a specific time offset.
        
        Args:
            input_path: Path to the input video file
            output_path: Path to save the thumbnail image
            time_offset: Time offset in seconds to capture the thumbnail (default: 5)
        
        Raises:
            RuntimeError: If FFmpeg command fails
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video file not found: {input_path}")
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-ss", str(time_offset),
            "-vframes", "1",
            output_path
        ]
        
        if self.logger:
            self.logger.info(f"Creating thumbnail: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg command failed with error: {result.stderr}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def extract_audio(self, input_path, output_path, audio_format="mp3"):
        """
        Extract audio from a video file.
        
        Args:
            input_path: Path to the input video file
            output_path: Path to save the extracted audio
            audio_format: Format of the output audio (default: mp3)
        
        Raises:
            RuntimeError: If FFmpeg command fails
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video file not found: {input_path}")
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn",  # No video
            "-acodec", "libmp3lame" if audio_format == "mp3" else "copy",
            output_path
        ]
        
        if self.logger:
            self.logger.info(f"Extracting audio: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg command failed with error: {result.stderr}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def scale_video(self, input_path, output_path, resolution):
        """
        Scale a video to a specific resolution.
        
        Args:
            input_path: Path to the input video file
            output_path: Path to save the scaled video
            resolution: Tuple containing (width, height)
        
        Raises:
            RuntimeError: If FFmpeg command fails
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video file not found: {input_path}")
        
        width, height = resolution
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", f"scale={width}:{height}",
            "-c:v", "libx264", "-preset", "medium",
            "-c:a", "copy",
            output_path
        ]
        
        if self.logger:
            self.logger.info(f"Scaling video: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg command failed with error: {result.stderr}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def overlay_text(self, input_path, output_path, text, position, font_size=24, font_color="white", font_file=None):
        """
        Overlay text on a video.
        
        Args:
            input_path: Path to the input video file
            output_path: Path to save the output video
            text: Text to overlay
            position: Tuple containing (x, y) coordinates
            font_size: Font size (default: 24)
            font_color: Font color (default: white)
            font_file: Path to font file (optional)
        
        Raises:
            RuntimeError: If FFmpeg command fails
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video file not found: {input_path}")
        
        x, y = position
        
        drawtext_params = f"text='{text}':x={x}:y={y}:fontsize={font_size}:fontcolor={font_color}"
        
        if font_file and os.path.exists(font_file):
            drawtext_params += f":fontfile='{font_file}'"
        
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vf", f"drawtext={drawtext_params}",
            "-c:v", "libx264", "-preset", "medium",
            "-c:a", "copy",
            output_path
        ]
        
        if self.logger:
            self.logger.info(f"Overlaying text: {' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"FFmpeg command failed with error: {result.stderr}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def get_video_dimensions(self, input_path):
        """
        Get the dimensions of a video file.
        
        Args:
            input_path: Path to the video file
        
        Returns:
            Tuple containing (width, height)
        """
        return self.mediainfo_parser.get_video_resolution(input_path)
    
    def get_video_duration(self, input_path):
        """
        Get the duration of a video file in seconds.
        
        Args:
            input_path: Path to the video file
        
        Returns:
            Duration in seconds (float)
        """
        return self.mediainfo_parser.get_video_duration(input_path)
    
    def process_video(self, input_path, output_path, crop_params=None, overlay_path=None):
        """
        Process a video file with multiple operations.
        
        Args:
            input_path: Path to the input video file
            output_path: Path to save the processed video
            crop_params: Dictionary containing crop parameters (optional)
            overlay_path: Path to overlay image (optional)
        
        Raises:
            RuntimeError: If any of the processing steps fail
        """
        if not os.path.exists(input_path):
            raise FileNotFoundError(f"Input video file not found: {input_path}")
        
        # If no operations are requested, just copy the file
        if not crop_params and not overlay_path:
            shutil.copy(input_path, output_path)
            if self.logger:
                self.logger.info(f"No processing required, copied {input_path} to {output_path}")
            return
        
        # If we need to do both crop and overlay, use a temporary file
        if crop_params and overlay_path:
            with tempfile.NamedTemporaryFile(suffix=".mp4") as temp_file:
                # First crop the video
                self.crop_video(input_path, temp_file.name, crop_params)
                
                # Then overlay the image
                self.overlay_image(temp_file.name, overlay_path, output_path)
        
        # If only cropping is needed
        elif crop_params:
            self.crop_video(input_path, output_path, crop_params)
        
        # If only overlay is needed
        elif overlay_path:
            self.overlay_image(input_path, overlay_path, output_path) 