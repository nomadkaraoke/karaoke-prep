import os
import asyncio
import mimetypes
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import MediaError


class MediaDetector:
    """
    Handles detecting media types.
    """
    
    def __init__(self, config):
        """
        Initialize the media detector.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
        
        # Initialize mimetypes
        mimetypes.init()
    
    async def detect_media_type(self, file_path):
        """
        Detect the type of a media file.
        
        Args:
            file_path: The path to the media file
            
        Returns:
            The media type (audio, video, image, or unknown)
        """
        self.logger.debug(f"Detecting media type for {file_path}")
        
        if not os.path.isfile(file_path):
            raise MediaError(f"File not found: {file_path}")
        
        # Get file extension
        _, ext = os.path.splitext(file_path)
        ext = ext.lower()
        
        # Check file extension
        if ext in ['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac']:
            self.logger.debug(f"Detected audio file by extension: {ext}")
            return "audio"
        elif ext in ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v']:
            self.logger.debug(f"Detected video file by extension: {ext}")
            return "video"
        elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']:
            self.logger.debug(f"Detected image file by extension: {ext}")
            return "image"
        
        # Check mimetype
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type:
            if mime_type.startswith('audio/'):
                self.logger.debug(f"Detected audio file by mimetype: {mime_type}")
                return "audio"
            elif mime_type.startswith('video/'):
                self.logger.debug(f"Detected video file by mimetype: {mime_type}")
                return "video"
            elif mime_type.startswith('image/'):
                self.logger.debug(f"Detected image file by mimetype: {mime_type}")
                return "image"
        
        # Use ffprobe as a fallback
        media_type = await self._detect_media_type_with_ffprobe(file_path)
        if media_type:
            self.logger.debug(f"Detected {media_type} file with ffprobe")
            return media_type
        
        self.logger.warning(f"Could not detect media type for {file_path}")
        return "unknown"
    
    async def _detect_media_type_with_ffprobe(self, file_path):
        """
        Detect the type of a media file using ffprobe.
        
        Args:
            file_path: The path to the media file
            
        Returns:
            The media type (audio, video, image, or None if detection failed)
        """
        # Build ffprobe command
        command = f'ffprobe -v error -show_entries stream=codec_type -of default=noprint_wrappers=1 "{file_path}"'
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                self.logger.debug(f"ffprobe failed: {stderr.decode()}")
                return None
            
            output = stdout.decode()
            
            if "codec_type=video" in output and "codec_type=audio" in output:
                return "video"
            elif "codec_type=audio" in output:
                return "audio"
            elif "codec_type=video" in output:
                # Check if it's a single frame (image) or a video
                duration_command = f'ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 "{file_path}"'
                process = await asyncio.create_subprocess_shell(
                    duration_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode == 0:
                    try:
                        duration = float(stdout.decode().strip())
                        if duration < 0.1:  # Very short duration, likely an image
                            return "image"
                        else:
                            return "video"
                    except (ValueError, TypeError):
                        pass
                
                return "video"  # Default to video if duration check fails
            
            return None
            
        except Exception as e:
            self.logger.debug(f"Error detecting media type with ffprobe: {str(e)}")
            return None 