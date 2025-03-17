import os
import asyncio
import tempfile
from karaoke_prep.core.exceptions import VideoError


class VideoCompositor:
    """
    Handles video composition operations.
    """
    
    def __init__(self, config):
        """
        Initialize the video compositor.
        
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
    
    async def compose_final_video(self, track):
        """
        Compose the final video by combining title, content, and end videos.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Composing final video for {track.base_name}")
        
        # Define output path
        output_path = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke).mp4")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"Final video already exists: {output_path}")
            track.final_video = output_path
            return track
        
        # Check for required videos
        title_video = track.title_video
        content_video = track.video_with_lyrics or track.video_with_instrumental
        end_video = track.end_video
        
        if not title_video or not os.path.isfile(title_video):
            self.logger.warning("Title video not found, skipping final video composition")
            return track
        
        if not content_video or not os.path.isfile(content_video):
            self.logger.warning("Content video not found, skipping final video composition")
            return track
        
        # Compose video
        if not self.config.dry_run:
            try:
                # Build ffmpeg command
                command = f'{self.ffmpeg_base_command} -i "{title_video}" -i "{content_video}" '
                
                # Add end video if available
                if end_video and os.path.isfile(end_video):
                    command += f'-i "{end_video}" '
                    filter_complex = '[0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[outv][outa]'
                else:
                    filter_complex = '[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[outv][outa]'
                
                # Add filter complex and output options
                command += (
                    f'-filter_complex "{filter_complex}" '
                    f'-map "[outv]" -map "[outa]" '
                    f'-c:v libx264 -preset medium -crf 22 -c:a aac -b:a 192k '
                    f'-pix_fmt yuv420p "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Composing final video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to compose final video: {error_message}")
                
                track.final_video = output_path
                self.logger.info(f"Successfully composed final video: {output_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to compose final video: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would compose final video: {output_path}")
            track.final_video = output_path
        
        return track
    
    async def create_lossless_version(self, track):
        """
        Create a lossless version of the final video.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Creating lossless version for {track.base_name}")
        
        # Skip if no final video
        if not track.final_video or not os.path.isfile(track.final_video):
            self.logger.info("No final video available, skipping lossless version creation")
            return track
        
        # Define output path
        output_path = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke).mkv")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"Lossless version already exists: {output_path}")
            track.final_video_mkv = output_path
            return track
        
        # Create lossless version
        if not self.config.dry_run:
            try:
                # Build ffmpeg command
                command = (
                    f'{self.ffmpeg_base_command} -i "{track.final_video}" '
                    f'-c:v copy -c:a flac "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Creating lossless version: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to create lossless version: {error_message}")
                
                track.final_video_mkv = output_path
                self.logger.info(f"Successfully created lossless version: {output_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to create lossless version: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would create lossless version: {output_path}")
            track.final_video_mkv = output_path
        
        return track
    
    async def create_720p_version(self, track):
        """
        Create a 720p version of the final video.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Creating 720p version for {track.base_name}")
        
        # Skip if no final video
        if not track.final_video or not os.path.isfile(track.final_video):
            self.logger.info("No final video available, skipping 720p version creation")
            return track
        
        # Define output path
        output_path = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke 720p).mp4")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"720p version already exists: {output_path}")
            track.final_video_720p = output_path
            return track
        
        # Create 720p version
        if not self.config.dry_run:
            try:
                # Build ffmpeg command
                command = (
                    f'{self.ffmpeg_base_command} -i "{track.final_video}" '
                    f'-c:v libx264 -vf "scale=1280:720" -b:v 2000k -preset medium -tune animation '
                    f'-c:a aac -b:a 128k -pix_fmt yuv420p "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Creating 720p version: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to create 720p version: {error_message}")
                
                track.final_video_720p = output_path
                self.logger.info(f"Successfully created 720p version: {output_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to create 720p version: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would create 720p version: {output_path}")
            track.final_video_720p = output_path
        
        return track
    
    async def create_lossy_version(self, track):
        """
        Create a lossy version of the final video.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Creating lossy version for {track.base_name}")
        
        # Skip if no final video
        if not track.final_video or not os.path.isfile(track.final_video):
            self.logger.warning(f"No final video found for {track.base_name}")
            return track
        
        # Define output path
        output_path = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke Lossy).mp4")
        
        # Skip if output already exists
        if os.path.isfile(output_path) and not self.config.force_regenerate:
            self.logger.info(f"Lossy version already exists: {output_path}")
            track.final_video_lossy = output_path
            return track
        
        # Create lossy version
        if not self.config.dry_run:
            try:
                # Build ffmpeg command
                command = (
                    f'{self.ffmpeg_base_command} -i "{track.final_video}" '
                    f'-c:v libx264 -preset slow -crf 23 -c:a aac -b:a 128k '
                    f'-pix_fmt yuv420p "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Creating lossy version: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to create lossy version: {error_message}")
                
                track.final_video_lossy = output_path
                self.logger.info(f"Successfully created lossy version: {output_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to create lossy version: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would create lossy version: {output_path}")
            track.final_video_lossy = output_path
        
        return track
    
    async def add_subtitles_to_video(self, track, subtitles_file, output_file=None):
        """
        Add subtitles to a video.
        
        Args:
            track: The track to process
            subtitles_file: The subtitles file
            output_file: The output file path
            
        Returns:
            The track with updated subtitled video information
        """
        self.logger.info(f"Adding subtitles to video for {track.base_name}")
        
        # Set default output file
        if output_file is None:
            output_file = os.path.join(track.track_output_dir, f"{track.base_name} (Subtitled).mov")
        
        # Skip if output already exists
        if os.path.isfile(output_file):
            self.logger.info(f"Subtitled video already exists: {output_file}")
            track.subtitled_video = output_file
            return track
        
        # Check if required files exist
        if not track.video or not os.path.isfile(track.video):
            self.logger.error(f"Video not found: {track.video}")
            raise VideoError(f"Video not found: {track.video}")
        
        if not os.path.isfile(subtitles_file):
            self.logger.error(f"Subtitles file not found: {subtitles_file}")
            raise VideoError(f"Subtitles file not found: {subtitles_file}")
        
        # Add subtitles to video
        if not self.config.dry_run:
            try:
                await self._add_subtitles_to_video(track.video, subtitles_file, output_file)
                
                track.subtitled_video = output_file
                self.logger.info(f"Successfully added subtitles to video: {output_file}")
                
            except Exception as e:
                raise VideoError(f"Failed to add subtitles to video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would add subtitles to video: {output_file}")
            track.subtitled_video = output_file
        
        return track
    
    async def overlay_videos(self, background_video, overlay_video, output_file, position=None, 
                            start_time=None, end_time=None, opacity=None):
        """
        Overlay one video on top of another.
        
        Args:
            background_video: The background video file
            overlay_video: The overlay video file
            output_file: The output file path
            position: The position (x:y)
            start_time: The start time in seconds
            end_time: The end time in seconds
            opacity: The opacity (0.0-1.0)
            
        Returns:
            The output file path
        """
        self.logger.info(f"Overlaying video on {background_video}")
        
        # Skip if output already exists
        if os.path.isfile(output_file):
            self.logger.info(f"Overlaid video already exists: {output_file}")
            return output_file
        
        # Check if required files exist
        if not os.path.isfile(background_video):
            self.logger.error(f"Background video not found: {background_video}")
            raise VideoError(f"Background video not found: {background_video}")
        
        if not os.path.isfile(overlay_video):
            self.logger.error(f"Overlay video not found: {overlay_video}")
            raise VideoError(f"Overlay video not found: {overlay_video}")
        
        # Set default values
        position = position or self.config.overlay_position or "10:10"
        opacity = opacity or self.config.overlay_opacity or 1.0
        
        # Overlay video
        if not self.config.dry_run:
            try:
                # Create filter complex
                filter_complex = (
                    f"[0:v][1:v]overlay={position}"
                )
                
                # Add start time if specified
                if start_time is not None:
                    filter_complex += f":enable='between(t,{start_time},{end_time or 999999})'"
                
                # Add opacity if less than 1.0
                if opacity < 1.0:
                    filter_complex += f":alpha={opacity}"
                
                # Overlay video
                command = (
                    f'{self.ffmpeg_base_command} -i "{background_video}" -i "{overlay_video}" '
                    f'-filter_complex "{filter_complex}" -c:v prores_ks -profile:v 3 '
                    f'-vendor ap10 -bits_per_mb 8000 -pix_fmt yuv422p10le -c:a copy "{output_file}"'
                )
                
                self.logger.debug(f"Overlaying video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to overlay video: {error_message}")
                
                self.logger.info(f"Successfully overlaid video: {output_file}")
                
            except Exception as e:
                raise VideoError(f"Failed to overlay video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would overlay video: {output_file}")
        
        return output_file
    
    async def create_picture_in_picture(self, main_video, pip_video, output_file, position=None, 
                                       size=None, start_time=None, end_time=None, border=None, 
                                       border_color=None):
        """
        Create a picture-in-picture video.
        
        Args:
            main_video: The main video file
            pip_video: The picture-in-picture video file
            output_file: The output file path
            position: The position (x:y)
            size: The size (width:height)
            start_time: The start time in seconds
            end_time: The end time in seconds
            border: The border width
            border_color: The border color
            
        Returns:
            The output file path
        """
        self.logger.info(f"Creating picture-in-picture video with {main_video} and {pip_video}")
        
        # Skip if output already exists
        if os.path.isfile(output_file):
            self.logger.info(f"Picture-in-picture video already exists: {output_file}")
            return output_file
        
        # Check if required files exist
        if not os.path.isfile(main_video):
            self.logger.error(f"Main video not found: {main_video}")
            raise VideoError(f"Main video not found: {main_video}")
        
        if not os.path.isfile(pip_video):
            self.logger.error(f"Picture-in-picture video not found: {pip_video}")
            raise VideoError(f"Picture-in-picture video not found: {pip_video}")
        
        # Set default values
        position = position or self.config.pip_position or "main_w-overlay_w-10:main_h-overlay_h-10"
        size = size or self.config.pip_size or "iw/4:ih/4"
        border = border or self.config.pip_border or 0
        border_color = border_color or self.config.pip_border_color or "black"
        
        # Create picture-in-picture video
        if not self.config.dry_run:
            try:
                # Create filter complex
                filter_complex = (
                    f"[1:v]scale={size}"
                )
                
                # Add border if specified
                if border > 0:
                    filter_complex += f",pad=iw+{border*2}:ih+{border*2}:{border}:{border}:{border_color}"
                
                filter_complex += f"[pip]; [0:v][pip]overlay={position}"
                
                # Add start time if specified
                if start_time is not None:
                    filter_complex += f":enable='between(t,{start_time},{end_time or 999999})'"
                
                # Create picture-in-picture video
                command = (
                    f'{self.ffmpeg_base_command} -i "{main_video}" -i "{pip_video}" '
                    f'-filter_complex "{filter_complex}" -c:v prores_ks -profile:v 3 '
                    f'-vendor ap10 -bits_per_mb 8000 -pix_fmt yuv422p10le -c:a copy "{output_file}"'
                )
                
                self.logger.debug(f"Creating picture-in-picture video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to create picture-in-picture video: {error_message}")
                
                self.logger.info(f"Successfully created picture-in-picture video: {output_file}")
                
            except Exception as e:
                raise VideoError(f"Failed to create picture-in-picture video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would create picture-in-picture video: {output_file}")
        
        return output_file
    
    async def _combine_videos(self, videos, output_file):
        """
        Combine multiple videos into one.
        
        Args:
            videos: The list of video files
            output_file: The output file path
            
        Returns:
            The output file path
        """
        # Create a temporary file for the concat list
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as temp_file:
            concat_list = temp_file.name
            self._temp_files.append(concat_list)  # Track temporary file
        
        # Write concat list
        with open(concat_list, "w") as f:
            for video in videos:
                f.write(f"file '{video}'\n")
        
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
    
    async def _add_subtitles_to_video(self, video_file, subtitles_file, output_file):
        """
        Add subtitles to a video.
        
        Args:
            video_file: The video file
            subtitles_file: The subtitles file
            output_file: The output file path
            
        Returns:
            The output file path
        """
        # Determine subtitles format
        subtitles_format = os.path.splitext(subtitles_file)[1].lower()
        
        # Add subtitles to video
        if subtitles_format == ".srt":
            # Use subtitles filter for SRT
            command = (
                f'{self.ffmpeg_base_command} -i "{video_file}" '
                f'-vf "subtitles={subtitles_file}" -c:v prores_ks -profile:v 3 '
                f'-vendor ap10 -bits_per_mb 8000 -pix_fmt yuv422p10le -c:a copy "{output_file}"'
            )
        elif subtitles_format == ".ass":
            # Use ASS filter for ASS/SSA
            command = (
                f'{self.ffmpeg_base_command} -i "{video_file}" '
                f'-vf "ass={subtitles_file}" -c:v prores_ks -profile:v 3 '
                f'-vendor ap10 -bits_per_mb 8000 -pix_fmt yuv422p10le -c:a copy "{output_file}"'
            )
        else:
            # Use subtitles filter for other formats
            command = (
                f'{self.ffmpeg_base_command} -i "{video_file}" -i "{subtitles_file}" '
                f'-c:v prores_ks -profile:v 3 -vendor ap10 -bits_per_mb 8000 '
                f'-pix_fmt yuv422p10le -c:a copy -c:s mov_text "{output_file}"'
            )
        
        self.logger.debug(f"Adding subtitles to video: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to add subtitles to video: {error_message}")
        
        return output_file
    
    async def cleanup(self):
        """
        Perform cleanup operations for the video compositor.
        """
        self.logger.info("Cleaning up video compositor resources")
        
        # Clean up any temporary files
        if hasattr(self, '_temp_files') and self._temp_files:
            for temp_file in self._temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        self.logger.debug(f"Removed temporary file: {temp_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove temporary file {temp_file}: {str(e)}")
        
        self.logger.info("Video compositor cleanup complete") 