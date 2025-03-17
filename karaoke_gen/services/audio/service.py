import logging
import os
import asyncio
from karaoke_gen.core.project import ProjectConfig
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import AudioError
from karaoke_gen.services.audio.converter import AudioConverter
from karaoke_gen.services.audio.separator import AudioSeparator
from karaoke_gen.services.audio.normalizer import AudioNormalizer
from karaoke_gen.services.audio.mixer import AudioMixer


class AudioService:
    """
    Service for orchestrating the audio processing workflow.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the audio service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        
        # Initialize components
        self.converter = AudioConverter(config)
        self.separator = AudioSeparator(config)
        self.normalizer = AudioNormalizer(config)
        self.mixer = AudioMixer(config)
    
    async def separate_audio(self, track: Track) -> Track:
        """
        Separate audio for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with separated audio
        """
        self.logger.info(f"Separating audio for {track.base_name}")
        return await self.separator.separate_audio(track)
    
    async def process_audio(self, track: Track) -> Track:
        """
        Process audio for a track, including separation, mixing, and normalization.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Processing audio for {track.base_name}")
        
        try:
            # Skip if instrumental already exists and we're not forcing regeneration
            if track.instrumental and os.path.isfile(track.instrumental) and not self.config.force_regenerate:
                self.logger.info(f"Instrumental already exists for {track.base_name}, skipping audio processing")
                return track
            
            # Separate audio
            track = await self.separator.separate_audio(track)
            
            # Mix audio
            track = await self.mixer.mix_audio(track)
            
            # Normalize audio
            track = await self.normalizer.normalize_audio(track)
            
            return track
            
        except Exception as e:
            self.logger.error(f"Failed to process audio for {track.base_name}: {str(e)}")
            # Continue with other processing
            return track
    
    async def cleanup(self):
        """
        Perform cleanup operations for audio processing.
        """
        self.logger.info("Cleaning up audio processing resources")
        
        # Close any open resources
        await self.separator.cleanup()
        
        self.logger.info("Audio processing cleanup complete") 