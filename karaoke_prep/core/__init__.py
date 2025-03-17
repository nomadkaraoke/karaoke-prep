"""
Core module for the karaoke_prep package.

This module contains the core domain models and exceptions.
"""

from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import KaraokeGenError

__all__ = ["ProjectConfig", "Track", "KaraokeGenError"]
