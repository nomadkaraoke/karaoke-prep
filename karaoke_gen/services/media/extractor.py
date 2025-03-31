import os
import asyncio
import shutil
from PIL import Image
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import MediaError


class MediaExtractor:
    """
    Handles extracting content from media files.
    """
    
    def __init__(self, config):
        """
        Initialize the media extractor.
        
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
    
    async def extract_still_image(self, track):
        """
        Extract a still image from a video file.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Extracting still image for {track.base_name}")
        
        # Skip if input is not a video file
        if not self._is_video_file(track.input_media):
            self.logger.info(f"Input is not a video file, skipping still image extraction")
            return track
        
        # Define output path with (Original) label
        output_filename_no_extension = os.path.join(
            track.track_output_dir, 
            f"{track.base_name} (Original)"
        )
        output_image = f"{output_filename_no_extension}.jpg"
        
        # Skip if output already exists
        if os.path.isfile(output_image):
            self.logger.info(f"Still image already exists: {output_image}")
            track.input_still_image = output_image
            return track
        
        # Build ffmpeg command
        command = f'{self.ffmpeg_base_command} -i "{track.input_media}" -vf "select=eq(n\\,0)" -q:v 1 "{output_image}"'
        
        # Execute command
        if not self.config.dry_run:
            try:
                self.logger.debug(f"Executing command: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise MediaError(f"Failed to extract still image: {error_message}")
                
                self.logger.info(f"Successfully extracted still image: {output_image}")
                track.input_still_image = output_image
                
            except Exception as e:
                self.logger.error(f"Failed to extract still image: {str(e)}")
                # Continue without still image
        else:
            self.logger.info(f"[DRY RUN] Would extract still image: {output_image}")
            track.input_still_image = output_image
        
        return track
    
    async def extract_audio_from_video(self, track):
        """
        Extract audio from a video file.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Extracting audio from video for {track.base_name}")
        
        # Skip if input is not a video file
        if not self._is_video_file(track.input_media):
            self.logger.info(f"Input is not a video file, skipping audio extraction")
            return track
        
        # Define output path with (Original) label
        output_filename_no_extension = os.path.join(
            track.track_output_dir, 
            f"{track.base_name} (Original)"
        )
        output_wav = f"{output_filename_no_extension}.wav"
        
        # Skip if output already exists
        if os.path.isfile(output_wav):
            self.logger.info(f"Audio file already exists: {output_wav}")
            track.input_audio_wav = output_wav
            return track
        
        # Build ffmpeg command
        command = f'{self.ffmpeg_base_command} -i "{track.input_media}" -vn -acodec pcm_s16le -ar 44100 -ac 2 "{output_wav}"'
        
        # Execute command
        if not self.config.dry_run:
            try:
                self.logger.debug(f"Executing command: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise MediaError(f"Failed to extract audio: {error_message}")
                
                self.logger.info(f"Successfully extracted audio: {output_wav}")
                track.input_audio_wav = output_wav
                
            except Exception as e:
                raise MediaError(f"Failed to extract audio: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would extract audio: {output_wav}")
            track.input_audio_wav = output_wav
        
        return track
    
    async def copy_audio_file(self, track):
        """
        Copy an audio file to the output directory.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Copying audio file for {track.base_name}")
        
        # Define output path with (Original) label
        output_filename_no_extension = os.path.join(
            track.track_output_dir, 
            f"{track.base_name} (Original)"
        )
        
        # Determine output extension
        input_ext = os.path.splitext(track.input_media)[1].lower()
        output_file = f"{output_filename_no_extension}{input_ext}"
        
        # Skip if output already exists
        if os.path.isfile(output_file) and os.path.abspath(output_file) != os.path.abspath(track.input_media):
            self.logger.info(f"Audio file already exists: {output_file}")
        elif not self.config.dry_run:
            try:
                # Copy file
                shutil.copy2(track.input_media, output_file)
                self.logger.info(f"Successfully copied audio file: {output_file}")
            except Exception as e:
                raise MediaError(f"Failed to copy audio file: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would copy audio file: {output_file}")
        
        # Convert to WAV if needed
        output_wav = f"{output_filename_no_extension}.wav"
        
        # Skip if output already exists
        if os.path.isfile(output_wav):
            self.logger.info(f"WAV file already exists: {output_wav}")
            track.input_audio_wav = output_wav
            return track
        
        # Build ffmpeg command
        command = f'{self.ffmpeg_base_command} -i "{output_file}" -vn -acodec pcm_s16le -ar 44100 -ac 2 "{output_wav}"'
        
        # Execute command
        if not self.config.dry_run:
            try:
                self.logger.debug(f"Executing command: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise MediaError(f"Failed to convert audio to WAV: {error_message}")
                
                self.logger.info(f"Successfully converted audio to WAV: {output_wav}")
                track.input_audio_wav = output_wav
                
            except Exception as e:
                raise MediaError(f"Failed to convert audio to WAV: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would convert audio to WAV: {output_wav}")
            track.input_audio_wav = output_wav
        
        return track
    
    async def copy_image_file(self, track):
        """
        Copy an image file to the output directory.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Copying image file for {track.base_name}")
        
        # Define output path with (Original) label
        output_filename_no_extension = os.path.join(
            track.track_output_dir, 
            f"{track.base_name} (Original)"
        )
        
        # Determine output extension
        input_ext = os.path.splitext(track.input_media)[1].lower()
        output_file = f"{output_filename_no_extension}{input_ext}"
        
        # Skip if output already exists
        if os.path.isfile(output_file) and os.path.abspath(output_file) != os.path.abspath(track.input_media):
            self.logger.info(f"Image file already exists: {output_file}")
        elif not self.config.dry_run:
            try:
                # Copy file
                shutil.copy2(track.input_media, output_file)
                self.logger.info(f"Successfully copied image file: {output_file}")
            except Exception as e:
                raise MediaError(f"Failed to copy image file: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would copy image file: {output_file}")
        
        # Set still image
        track.input_still_image = output_file
        
        return track
    
    def _is_video_file(self, file_path):
        """
        Check if a file is a video file.
        
        Args:
            file_path: The path to the file
            
        Returns:
            True if the file is a video file, False otherwise
        """
        if not file_path or not os.path.isfile(file_path):
            return False
        
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']
        _, ext = os.path.splitext(file_path)
        return ext.lower() in video_extensions
        
    async def extract_media(self, track: Track) -> Track:
        """
        Extract media from the input file based on its type.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Extracting media for {track.base_name}")
        
        # Check if the input is a video file
        if self._is_video_file(track.input_media):
            # Extract still image and audio from video
            track = await self.extract_still_image(track)
            track = await self.extract_audio_from_video(track)
        elif self._is_image_file(track.input_media):
            # Copy image file
            track = await self.copy_image_file(track)
        else:
            # Assume it's an audio file
            track = await self.copy_audio_file(track)
        
        return track
    
    def _is_image_file(self, file_path):
        """
        Check if a file is an image file.
        
        Args:
            file_path: The path to the file
            
        Returns:
            True if the file is an image file, False otherwise
        """
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
        ext = os.path.splitext(file_path)[1].lower()
        return ext in image_extensions 