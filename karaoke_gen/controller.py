import asyncio
import logging
import os
from typing import List, Optional

from karaoke_gen.core.project import ProjectConfig
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import KaraokeGenError


class KaraokeController:
    """
    Main controller for the karaoke generation process.
    This class orchestrates the entire workflow by delegating to specialized services.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the controller with the given configuration.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        
        # Services will be imported and initialized lazily to avoid circular imports
        self._audio_service = None
        self._lyrics_service = None
        self._media_service = None
        self._video_service = None
        self._distribution_service = None
    
    @property
    def audio_service(self):
        """Lazy-loaded audio service"""
        if self._audio_service is None:
            from karaoke_gen.services.audio import AudioService
            self._audio_service = AudioService(self.config)
        return self._audio_service
    
    @property
    def lyrics_service(self):
        """Lazy-loaded lyrics service"""
        if self._lyrics_service is None:
            from karaoke_gen.services.lyrics import LyricsService
            self._lyrics_service = LyricsService(self.config)
        return self._lyrics_service
    
    @property
    def media_service(self):
        """Lazy-loaded media service"""
        if self._media_service is None:
            from karaoke_gen.services.media import MediaService
            self._media_service = MediaService(self.config)
        return self._media_service
    
    @property
    def video_service(self):
        """Lazy-loaded video service"""
        if self._video_service is None:
            from karaoke_gen.services.video import VideoService
            self._video_service = VideoService(self.config)
        return self._video_service
    
    @property
    def distribution_service(self):
        """Lazy-loaded distribution service"""
        if self._distribution_service is None:
            from karaoke_gen.services.distribution.service import DistributionService
            self._distribution_service = DistributionService(self.config)
        return self._distribution_service
    
    async def process_track(self, track: Track) -> Track:
        """
        Process a single track through the entire workflow.
        
        Args:
            track: The track to process
            
        Returns:
            The processed track with updated information
        """
        self.logger.info(f"Processing track: {track.base_name}")
        
        try:
            # Setup output directory
            track = await self._setup_output_directory(track)
            
            # Media acquisition and preparation
            if track.is_url:
                track = await self.media_service.download_media(track)
            elif track.is_file:
                track = await self.media_service.prepare_media(track)
            
            # Skip further processing if we're only doing lyrics
            if self.config.lyrics_only:
                track = await self.lyrics_service.process_lyrics(track)
                return track
            
            # Audio processing (if not skipped)
            if not self.config.skip_separation:
                track = await self.audio_service.separate_audio(track)
            
            # Lyrics processing (if not skipped)
            if not self.config.skip_lyrics:
                track = await self.lyrics_service.process_lyrics(track)
            
            # Video generation
            track = await self.video_service.create_videos(track)
            
            # Distribution (if not prep_only)
            if not self.config.prep_only:
                track = await self.distribution_service.distribute(track)
            
            self.logger.info(f"Successfully processed track: {track.base_name}")
            return track
            
        except KaraokeGenError as e:
            self.logger.error(f"Error processing track {track.base_name}: {str(e)}")
            raise
    
    async def _setup_output_directory(self, track: Track) -> Track:
        """
        Set up the output directory for the track.
        
        Args:
            track: The track to set up the output directory for
            
        Returns:
            The track with updated output directory information
        """
        if self.config.create_track_subfolders and track.artist and track.title:
            # Create a subfolder for the track
            track_dir_name = f"{track.artist} - {track.title}"
            track_dir_name = self._sanitize_filename(track_dir_name)
            track_output_dir = os.path.join(self.config.output_dir, track_dir_name)
            
            # Create the directory if it doesn't exist
            if not os.path.exists(track_output_dir) and not self.config.dry_run:
                os.makedirs(track_output_dir, exist_ok=True)
                self.logger.info(f"Created output directory: {track_output_dir}")
        else:
            # Use the output directory directly
            track_output_dir = self.config.output_dir
        
        track.track_output_dir = track_output_dir
        return track
    
    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename by removing invalid characters.
        
        Args:
            filename: The filename to sanitize
            
        Returns:
            The sanitized filename
        """
        # Replace characters that are invalid in filenames
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename
    
    async def process_tracks(self, tracks: List[Track] = None) -> List[Track]:
        """
        Process multiple tracks.
        
        Args:
            tracks: List of tracks to process. If None, a track will be created from the config.
            
        Returns:
            List of processed tracks
        """
        if tracks is None:
            # Create a track from the configuration
            track = Track(
                artist=self.config.artist,
                title=self.config.title,
                input_media=self.config.input_media
            )
            tracks = [track]
        
        processed_tracks = []
        for track in tracks:
            processed_track = await self.process_track(track)
            processed_tracks.append(processed_track)
        
        return processed_tracks
    
    async def process(self) -> List[Track]:
        """
        Process tracks based on the configuration.
        This is the main entry point for the controller.
        
        Returns:
            List of processed tracks
        """
        # Handle edit lyrics mode
        if self.config.edit_lyrics:
            return await self._handle_edit_lyrics_mode()
        
        # Handle finalise only mode
        if self.config.finalise_only:
            return await self._handle_finalise_only_mode()
        
        # Normal processing
        return await self.process_tracks()
    
    async def _handle_edit_lyrics_mode(self) -> List[Track]:
        """
        Handle edit lyrics mode.
        
        Returns:
            List of processed tracks
        """
        self.logger.info("Running in edit-lyrics mode...")
        
        # Get the current directory name to extract artist and title
        current_dir = os.path.basename(os.getcwd())
        self.logger.info(f"Current directory: {current_dir}")
        
        # Extract artist and title from directory name
        if " - " not in current_dir:
            raise ValueError("Current directory name does not contain ' - ' separator. Cannot extract artist and title.")
            
        parts = current_dir.split(" - ")
        if len(parts) == 2:
            artist, title = parts
        elif len(parts) >= 3:
            # Handle brand code format: "BRAND-XXXX - Artist - Title"
            artist = parts[1]
            title = " - ".join(parts[2:])
        else:
            raise ValueError(f"Could not parse artist and title from directory name: {current_dir}")
            
        self.logger.info(f"Extracted artist: {artist}, title: {title}")
        
        # Create a track
        track = Track(
            artist=artist,
            title=title,
            track_output_dir=os.getcwd()
        )
        
        # Backup existing outputs and get the input audio file
        track = await self.lyrics_service.backup_and_prepare_for_edit(track)
        
        # Process lyrics
        track = await self.lyrics_service.process_lyrics(track)
        
        # Distribute
        track = await self.distribution_service.distribute(track, replace_existing=True)
        
        return [track]
    
    async def _handle_finalise_only_mode(self) -> List[Track]:
        """
        Handle finalise only mode.
        
        Returns:
            List of processed tracks
        """
        self.logger.info("Running in finalise-only mode...")
        
        # Create a track with the current directory
        track = Track(track_output_dir=os.getcwd())
        
        # Distribute
        track = await self.distribution_service.distribute(track)
        
        return [track] 