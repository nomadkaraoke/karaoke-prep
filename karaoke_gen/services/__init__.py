"""
Services module for the karaoke_gen package.

This module contains the various services used by the karaoke generator.
"""

# Import and re-export service modules
from karaoke_gen.services.audio import AudioService
from karaoke_gen.services.lyrics import LyricsService
from karaoke_gen.services.media import MediaService
from karaoke_gen.services.video import VideoService
from karaoke_gen.services.distribution import DistributionService

# Import main service
from karaoke_gen.services.main import MainService

__all__ = [
    "MainService",
    "AudioService",
    "LyricsService",
    "MediaService",
    "VideoService",
    "DistributionService",
]
