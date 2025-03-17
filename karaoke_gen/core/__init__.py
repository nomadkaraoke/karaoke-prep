"""
Core module for the karaoke_gen package.

This module contains the core domain models and exceptions.
"""

from karaoke_gen.core.project import ProjectConfig
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import KaraokeGenError

__all__ = ["ProjectConfig", "Track", "KaraokeGenError"]
