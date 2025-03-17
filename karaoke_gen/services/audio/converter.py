import os
import subprocess
import asyncio
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import AudioError


class AudioConverter:
    """
    Handles audio format conversion operations.
    """
    
    def __init__(self, config):
        """
        Initialize the audio converter.
        
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
    
    async def convert_to_wav(self, track):
        """
        Convert the input audio to WAV format.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Converting audio to WAV for {track.base_name}")
        
        # Determine input file
        input_file = track.input_media
        if not os.path.isfile(input_file):
            raise AudioError(f"Input file not found: {input_file}")
        
        # Determine output file
        output_filename_no_extension = os.path.join(
            track.track_output_dir, 
            f"{track.base_name}"
        )
        output_wav = f"{output_filename_no_extension}.wav"
        
        # Skip if output already exists
        if os.path.isfile(output_wav):
            self.logger.info(f"WAV file already exists: {output_wav}")
            track.input_audio_wav = output_wav
            return track
        
        # Build ffmpeg command
        command = f'{self.ffmpeg_base_command} -i "{input_file}" -vn -acodec pcm_s16le -ar 44100 -ac 2 "{output_wav}"'
        
        # Execute command
        if not self.config.dry_run:
            self.logger.debug(f"Executing command: {command}")
            try:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise AudioError(f"Failed to convert audio to WAV: {error_message}")
                
                self.logger.info(f"Successfully converted audio to WAV: {output_wav}")
                track.input_audio_wav = output_wav
                
            except Exception as e:
                raise AudioError(f"Failed to convert audio to WAV: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would convert audio to WAV: {output_wav}")
            track.input_audio_wav = output_wav
        
        return track 