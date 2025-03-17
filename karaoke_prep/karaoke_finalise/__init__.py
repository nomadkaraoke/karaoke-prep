"""
Legacy KaraokeFinalise module for backward compatibility.

This module is maintained for backward compatibility with existing code.
New code should use the DistributionService in karaoke_prep.services.distribution.
"""

from .karaoke_finalise import KaraokeFinalise

__all__ = ["KaraokeFinalise"]
