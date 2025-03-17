import logging
import os
import asyncio
import shutil
import glob
from typing import Dict, Any, Optional, Tuple
from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import MediaError, DownloadError, ConversionError
from karaoke_prep.services.media.downloader import MediaDownloader
from karaoke_prep.services.media.extractor import MediaExtractor
from karaoke_prep.services.media.detector import MediaDetector


class MediaService:
    """
    Service for media handling operations including downloading, extraction, and detection.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the media service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        
        # Initialize components
        self.downloader = MediaDownloader(config)
        self.extractor = MediaExtractor(config)
        self.detector = MediaDetector(config)
    
    async def download_media(self, track: Track) -> Track:
        """
        Download media for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        if self.config.skip_download:
            self.logger.info("Skipping media download")
            return track
        
        self.logger.info(f"Downloading media for {track.base_name}")
        
        # Download media
        track = await self.downloader.download_media(track)
        
        return track
    
    async def extract_media(self, track: Track) -> Track:
        """
        Extract audio and other components from media.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated extracted media information
        """
        if self.config.skip_extraction:
            self.logger.info("Skipping media extraction")
            return track
        
        self.logger.info(f"Extracting media for {track.base_name}")
        
        # Extract media
        track = await self.extractor.extract_media(track)
        
        return track
    
    async def detect_media_info(self, track: Track) -> Track:
        """
        Detect media information.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        if self.config.skip_detection:
            self.logger.info("Skipping media detection")
            return track
        
        self.logger.info(f"Detecting media info for {track.base_name}")
        
        # Detect media info
        track = await self.detector.detect_media_info(track)
        
        return track
    
    async def process_media(self, track: Track) -> Track:
        """
        Process media for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Processing media for {track.base_name}")
        
        # Download media
        track = await self.download_media(track)
        
        # Extract media
        track = await self.extract_media(track)
        
        # Detect media info
        track = await self.detect_media_info(track)
        
        return track 