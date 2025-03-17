import os
import asyncio
import tempfile
import subprocess
import shutil
from karaoke_gen.core.exceptions import VideoError


class VideoRenderer:
    """
    Handles video rendering operations.
    """
    
    def __init__(self, config):
        """
        Initialize the video renderer.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
        
        # Path to ffmpeg
        self.ffmpeg_path = "ffmpeg"
        
        # Set up ffmpeg base command
        self.ffmpeg_base_command = f"{self.ffmpeg_path} -hide_banner -nostats"
        
        if self.config.log_level <= 10:  # DEBUG
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"
        
        # Initialize temporary files list
        self._temp_files = []
    
    async def render_video(self, track, output_file=None, resolution=None, fps=None, 
                          codec=None, bitrate=None, background_color=None):
        """
        Render a video for a track.
        
        Args:
            track: The track to process
            output_file: The output file path
            resolution: The resolution
            fps: The frames per second
            codec: The codec
            bitrate: The bitrate
            background_color: The background color
            
        Returns:
            The output file path
        """
        self.logger.info(f"Rendering video for {track.base_name}")
        
        # Set default output file
        if output_file is None:
            output_file = os.path.join(track.track_output_dir, f"{track.base_name} (Video).mov")
        
        # Skip if output already exists
        if os.path.isfile(output_file):
            self.logger.info(f"Video already exists: {output_file}")
            track.video = output_file
            return track
        
        # Set default values
        resolution = resolution or self.config.video_resolution or "1920x1080"
        fps = fps or self.config.video_fps or 30
        codec = codec or self.config.video_codec or "prores_ks"
        bitrate = bitrate or self.config.video_bitrate or "8000k"
        background_color = background_color or self.config.video_background_color or "black"
        
        # Check if audio file exists
        if not track.audio_file or not os.path.isfile(track.audio_file):
            self.logger.error(f"Audio file not found: {track.audio_file}")
            raise VideoError(f"Audio file not found: {track.audio_file}")
        
        # Create video
        if not self.config.dry_run:
            try:
                # Create a video from audio
                await self._create_video_from_audio(
                    track.audio_file,
                    output_file,
                    track.duration,
                    resolution,
                    fps,
                    codec,
                    bitrate,
                    background_color
                )
                
                track.video = output_file
                self.logger.info(f"Successfully rendered video: {output_file}")
                
            except Exception as e:
                raise VideoError(f"Failed to render video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would render video: {output_file}")
            track.video = output_file
        
        return track
    
    async def combine_videos(self, videos, output_file, transition_duration=None):
        """
        Combine multiple videos into one.
        
        Args:
            videos: The list of video files to combine
            output_file: The output file path
            transition_duration: The transition duration in seconds
            
        Returns:
            The output file path
        """
        self.logger.info(f"Combining {len(videos)} videos")
        
        # Skip if output already exists
        if os.path.isfile(output_file):
            self.logger.info(f"Combined video already exists: {output_file}")
            return output_file
        
        # Check if videos exist
        for video in videos:
            if not os.path.isfile(video):
                self.logger.error(f"Video file not found: {video}")
                raise VideoError(f"Video file not found: {video}")
        
        # Set default transition duration
        transition_duration = transition_duration or self.config.transition_duration or 0.5
        
        # Create video
        if not self.config.dry_run:
            try:
                # Create a temporary file for the concat list
                with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
                    concat_list = temp_file.name
                    self._temp_files.append(concat_list)  # Track temporary file
                
                # Write concat list
                with open(concat_list, "w") as f:
                    for video in videos:
                        f.write(f"file '{video}'\n")
                
                # Combine videos
                if transition_duration > 0:
                    await self._combine_videos_with_transitions(videos, output_file, transition_duration)
                else:
                    await self._combine_videos_simple(concat_list, output_file)
                
                self.logger.info(f"Successfully combined videos: {output_file}")
                
            except Exception as e:
                raise VideoError(f"Failed to combine videos: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would combine videos: {output_file}")
        
        return output_file
    
    async def add_audio_to_video(self, video_file, audio_file, output_file):
        """
        Add audio to a video.
        
        Args:
            video_file: The video file
            audio_file: The audio file
            output_file: The output file path
            
        Returns:
            The output file path
        """
        self.logger.info(f"Adding audio to video: {video_file}")
        
        # Skip if output already exists
        if os.path.isfile(output_file):
            self.logger.info(f"Video with audio already exists: {output_file}")
            return output_file
        
        # Check if files exist
        if not os.path.isfile(video_file):
            self.logger.error(f"Video file not found: {video_file}")
            raise VideoError(f"Video file not found: {video_file}")
        
        if not os.path.isfile(audio_file):
            self.logger.error(f"Audio file not found: {audio_file}")
            raise VideoError(f"Audio file not found: {audio_file}")
        
        # Add audio to video
        if not self.config.dry_run:
            try:
                command = (
                    f'{self.ffmpeg_base_command} -i "{video_file}" -i "{audio_file}" '
                    f'-c:v copy -c:a pcm_s24le -shortest "{output_file}"'
                )
                
                self.logger.debug(f"Adding audio to video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to add audio to video: {error_message}")
                
                self.logger.info(f"Successfully added audio to video: {output_file}")
                
            except Exception as e:
                raise VideoError(f"Failed to add audio to video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would add audio to video: {output_file}")
        
        return output_file
    
    async def _create_video_from_audio(self, audio_file, output_file, duration, resolution, 
                                      fps, codec, bitrate, background_color):
        """
        Create a video from an audio file.
        
        Args:
            audio_file: The audio file
            output_file: The output file path
            duration: The duration in seconds
            resolution: The resolution
            fps: The frames per second
            codec: The codec
            bitrate: The bitrate
            background_color: The background color
            
        Returns:
            The output file path
        """
        # Create a video from audio
        command = (
            f'{self.ffmpeg_base_command} -f lavfi -i color=c={background_color}:s={resolution}:r={fps} '
            f'-i "{audio_file}" -t {duration} -c:v {codec} -profile:v 3 -vendor ap10 '
            f'-b:v {bitrate} -pix_fmt yuv422p10le -c:a pcm_s24le "{output_file}"'
        )
        
        self.logger.debug(f"Creating video from audio: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to create video from audio: {error_message}")
        
        return output_file
    
    async def _combine_videos_simple(self, concat_list, output_file):
        """
        Combine videos using the concat demuxer.
        
        Args:
            concat_list: The concat list file
            output_file: The output file path
            
        Returns:
            The output file path
        """
        # Combine videos
        command = (
            f'{self.ffmpeg_base_command} -f concat -safe 0 -i "{concat_list}" '
            f'-c:v prores_ks -profile:v 3 -vendor ap10 -bits_per_mb 8000 '
            f'-pix_fmt yuv422p10le -c:a pcm_s24le "{output_file}"'
        )
        
        self.logger.debug(f"Combining videos: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to combine videos: {error_message}")
        
        return output_file
    
    async def _combine_videos_with_transitions(self, videos, output_file, transition_duration):
        """
        Combine videos with crossfade transitions.
        
        Args:
            videos: The list of video files
            output_file: The output file path
            transition_duration: The transition duration in seconds
            
        Returns:
            The output file path
        """
        # Create a complex filter for crossfade transitions
        filter_complex = ""
        inputs = ""
        
        # Add input files
        for i, video in enumerate(videos):
            inputs += f' -i "{video}"'
        
        # Create filter complex
        for i in range(len(videos)):
            filter_complex += f"[{i}:v]setpts=PTS-STARTPTS[v{i}];"
        
        # Add crossfade transitions
        for i in range(len(videos) - 1):
            filter_complex += (
                f"[v{i}][v{i+1}]xfade=transition=fade:duration={transition_duration}:offset="
                f"{self._get_video_duration(videos[i]) - transition_duration}[v{i}out];"
            )
        
        # Finalize filter complex
        if len(videos) > 2:
            for i in range(len(videos) - 2):
                filter_complex += f"[v{i}out][v{i+2}]concat=n=2:v=1:a=0[v{i+1}out];"
            filter_complex = filter_complex[:-1]  # Remove last semicolon
            output_label = f"[v{len(videos)-2}out]"
        else:
            output_label = "[v0out]"
        
        # Combine videos with transitions
        command = (
            f'{self.ffmpeg_base_command}{inputs} -filter_complex "{filter_complex}" '
            f'-map "{output_label}" -c:v prores_ks -profile:v 3 -vendor ap10 '
            f'-bits_per_mb 8000 -pix_fmt yuv422p10le "{output_file}"'
        )
        
        self.logger.debug(f"Combining videos with transitions: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to combine videos with transitions: {error_message}")
        
        return output_file
    
    async def _get_video_duration(self, video_file):
        """
        Get the duration of a video file.
        
        Args:
            video_file: The video file
            
        Returns:
            The duration in seconds
        """
        # Get video duration
        command = (
            f'{self.ffmpeg_path} -i "{video_file}" -hide_banner 2>&1 | '
            f'grep "Duration" | cut -d " " -f 4 | sed s/,//'
        )
        
        self.logger.debug(f"Getting video duration: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            shell=True
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to get video duration: {error_message}")
        
        # Parse duration
        duration_str = stdout.decode().strip()
        if not duration_str:
            raise VideoError(f"Failed to get video duration: {video_file}")
        
        # Convert HH:MM:SS.ms to seconds
        hours, minutes, seconds = duration_str.split(":")
        seconds, milliseconds = seconds.split(".")
        
        duration = (
            int(hours) * 3600 +
            int(minutes) * 60 +
            int(seconds) +
            int(milliseconds) / 100
        )
        
        return duration
    
    async def render_lyrics_video(self, track):
        """
        Render a video with lyrics.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Rendering lyrics video for {track.base_name}")
        
        # Define output path
        output_path = os.path.join(track.track_output_dir, f"{track.base_name} (With Lyrics).mp4")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"Lyrics video already exists: {output_path}")
            track.video_with_lyrics = output_path
            return track
        
        # Check for processed lyrics
        if not track.processed_lyrics or not os.path.isfile(track.processed_lyrics):
            self.logger.warning(f"No processed lyrics found for {track.base_name}")
            return track
        
        # Check for instrumental audio
        if not track.instrumental or not os.path.isfile(track.instrumental):
            self.logger.warning(f"No instrumental audio found for {track.base_name}")
            return track
        
        # Render video
        if not self.config.dry_run:
            try:
                # Create temporary subtitle file in ASS format if needed
                if track.processed_lyrics.endswith('.lrc'):
                    subtitle_file = await self._convert_lrc_to_ass(track.processed_lyrics, track.track_output_dir)
                else:
                    subtitle_file = track.processed_lyrics
                
                # Build ffmpeg command
                command = (
                    f'{self.ffmpeg_base_command} -i "{track.title_video}" -i "{track.instrumental}" '
                    f'-vf "ass={subtitle_file}" '
                    f'-c:v libx264 -preset medium -crf 22 -c:a aac -b:a 192k '
                    f'-pix_fmt yuv420p -shortest "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Rendering lyrics video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to render lyrics video: {error_message}")
                
                track.video_with_lyrics = output_path
                self.logger.info(f"Successfully rendered lyrics video: {output_path}")
                
                # Clean up temporary files
                if track.processed_lyrics.endswith('.lrc') and os.path.isfile(subtitle_file):
                    os.remove(subtitle_file)
                
            except Exception as e:
                self.logger.error(f"Failed to render lyrics video: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would render lyrics video: {output_path}")
            track.video_with_lyrics = output_path
        
        return track
    
    async def render_instrumental_video(self, track):
        """
        Render a video with instrumental audio.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Rendering instrumental video for {track.base_name}")
        
        # Define output path
        output_path = os.path.join(track.track_output_dir, f"{track.base_name} (Instrumental).mp4")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"Instrumental video already exists: {output_path}")
            track.video_with_instrumental = output_path
            return track
        
        # Check for title video
        if not track.title_video or not os.path.isfile(track.title_video):
            self.logger.warning(f"No title video found for {track.base_name}")
            return track
        
        # Check for instrumental audio
        if not track.instrumental or not os.path.isfile(track.instrumental):
            self.logger.warning(f"No instrumental audio found for {track.base_name}")
            return track
        
        # Render video
        if not self.config.dry_run:
            try:
                # Build ffmpeg command
                command = (
                    f'{self.ffmpeg_base_command} -i "{track.title_video}" -i "{track.instrumental}" '
                    f'-map 0:v -map 1:a -c:v libx264 -preset medium -crf 22 -c:a aac -b:a 192k '
                    f'-pix_fmt yuv420p -shortest "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Rendering instrumental video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to render instrumental video: {error_message}")
                
                track.video_with_instrumental = output_path
                self.logger.info(f"Successfully rendered instrumental video: {output_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to render instrumental video: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would render instrumental video: {output_path}")
            track.video_with_instrumental = output_path
        
        return track
    
    async def render_karaoke_video(self, track):
        """
        Render a karaoke video with lyrics and instrumental audio.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Rendering karaoke video for {track.base_name}")
        
        # Skip if no processed lyrics
        if not track.processed_lyrics or not track.processed_lyrics.get("lrc_filepath"):
            self.logger.info("No processed lyrics available, skipping karaoke video rendering")
            return track
        
        # Skip if no instrumental audio
        if not track.separated_audio["clean_instrumental"].get("instrumental"):
            self.logger.info("No instrumental audio available, skipping karaoke video rendering")
            return track
        
        # Define output path
        output_path = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).mp4")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"Karaoke video already exists: {output_path}")
            track.final_video = output_path
            return track
        
        # Get input paths
        title_video = track.title_video
        end_video = track.end_video
        instrumental_audio = track.separated_audio["clean_instrumental"]["instrumental"]
        lyrics_file = track.processed_lyrics.get("lrc_filepath")
        
        # Check if all required files exist
        if not all(os.path.isfile(f) for f in [title_video, instrumental_audio, lyrics_file]):
            self.logger.warning("Missing required files for karaoke video rendering")
            return track
        
        # Render video
        if not self.config.dry_run:
            try:
                # Create temporary subtitle file in ASS format
                ass_file = await self._convert_lrc_to_ass(lyrics_file, track.track_output_dir)
                
                # Build ffmpeg command
                command = (
                    f'{self.ffmpeg_base_command} -i "{title_video}" -i "{instrumental_audio}" '
                )
                
                # Add end video if available
                if end_video and os.path.isfile(end_video):
                    command += f'-i "{end_video}" '
                    filter_complex = (
                        f'-filter_complex "[0:v][1:a][2:v][1:a]concat=n=2:v=1:a=1[outv][outa]" '
                        f'-map "[outv]" -map "[outa]" '
                    )
                else:
                    filter_complex = ""
                    command += f'-map 0:v -map 1:a '
                
                # Add subtitle filter
                if filter_complex:
                    command = command.replace("-filter_complex", f'-filter_complex "ass={ass_file}:')
                else:
                    command += f'-vf "ass={ass_file}" '
                
                # Add output options
                command += (
                    f'-c:v libx264 -preset medium -crf 22 -c:a aac -b:a 192k '
                    f'-pix_fmt yuv420p -shortest "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Rendering karaoke video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to render karaoke video: {error_message}")
                
                track.final_video = output_path
                self.logger.info(f"Successfully rendered karaoke video: {output_path}")
                
                # Clean up temporary files
                if os.path.isfile(ass_file):
                    os.remove(ass_file)
                
            except Exception as e:
                self.logger.error(f"Failed to render karaoke video: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would render karaoke video: {output_path}")
            track.final_video = output_path
        
        return track
    
    async def _convert_lrc_to_ass(self, lrc_file, output_dir):
        """
        Convert LRC file to ASS subtitle format.
        
        Args:
            lrc_file: The LRC file path
            output_dir: The output directory
            
        Returns:
            The path to the ASS file
        """
        self.logger.info(f"Converting LRC file to ASS: {lrc_file}")
        
        # Define output path
        ass_file = os.path.join(output_dir, os.path.basename(lrc_file).replace(".lrc", ".ass"))
        
        # Skip if output already exists
        if os.path.isfile(ass_file):
            self.logger.info(f"ASS file already exists: {ass_file}")
            return ass_file
        
        # Create a temporary file for the ASS file
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as temp_file:
            temp_ass_file = temp_file.name
            self._temp_files.append(temp_ass_file)  # Track temporary file
        
        # Read LRC file
        with open(lrc_file, "r", encoding="utf-8") as f:
            lrc_content = f.readlines()
        
        # Parse LRC content
        lyrics = []
        for line in lrc_content:
            line = line.strip()
            if not line or line.startswith("[ti:") or line.startswith("[ar:") or line.startswith("[al:"):
                continue
            
            # Extract timestamp and text
            if line.startswith("[") and "]" in line:
                timestamp = line[1:line.find("]")]
                text = line[line.find("]") + 1:].strip()
                
                # Parse timestamp
                if ":" in timestamp and "." in timestamp:
                    minutes, seconds = timestamp.split(":")
                    seconds, milliseconds = seconds.split(".")
                    
                    start_time = int(minutes) * 60 + int(seconds) + int(milliseconds) / 100
                    lyrics.append((start_time, text))
        
        # Sort lyrics by timestamp
        lyrics.sort(key=lambda x: x[0])
        
        # Calculate end times
        for i in range(len(lyrics) - 1):
            lyrics[i] = (lyrics[i][0], lyrics[i + 1][0], lyrics[i][1])
        
        # Add end time for last lyric
        if lyrics:
            lyrics[-1] = (lyrics[-1][0], lyrics[-1][0] + 5, lyrics[-1][1])
        
        # Create ASS file
        with open(temp_ass_file, "w", encoding="utf-8") as f:
            # Write header
            f.write("[Script Info]\n")
            f.write("Title: Karaoke Lyrics\n")
            f.write("ScriptType: v4.00+\n")
            f.write("PlayResX: 3840\n")
            f.write("PlayResY: 2160\n")
            f.write("Collisions: Normal\n\n")
            
            # Write styles
            f.write("[V4+ Styles]\n")
            f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            f.write("Style: Default,Arial,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,0,2,20,20,20,1\n\n")
            
            # Write events
            f.write("[Events]\n")
            f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            
            # Write lyrics
            for start_time, end_time, text in lyrics:
                start_str = self._format_time(start_time)
                end_str = self._format_time(end_time)
                f.write(f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{text}\n")
        
        # Copy to output path
        shutil.copy2(temp_ass_file, ass_file)
        
        self.logger.info(f"Successfully converted LRC to ASS: {ass_file}")
        return ass_file
    
    def _format_time(self, seconds):
        """
        Format time in seconds to ASS format (h:mm:ss.cc).
        
        Args:
            seconds: The time in seconds
            
        Returns:
            The formatted time string
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        centiseconds = int((seconds - int(seconds)) * 100)
        seconds = int(seconds)
        
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
    
    async def cleanup(self):
        """
        Perform cleanup operations for the video renderer.
        """
        self.logger.info("Cleaning up video renderer resources")
        
        # Clean up any temporary files
        if hasattr(self, '_temp_files') and self._temp_files:
            for temp_file in self._temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        self.logger.debug(f"Removed temporary file: {temp_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove temporary file {temp_file}: {str(e)}")
        
        self.logger.info("Video renderer cleanup complete")