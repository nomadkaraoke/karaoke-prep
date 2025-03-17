"""
Karaoke Generator package.
"""

__version__ = "0.1.0"

# Import legacy classes for backward compatibility
from karaoke_prep.legacy import KaraokePrep, KaraokeFinalise

# Import new API
from karaoke_prep.controller import KaraokeController
from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import KaraokeGenError
