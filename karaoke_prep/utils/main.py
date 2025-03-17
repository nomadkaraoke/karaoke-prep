#!/usr/bin/env python
"""
Main entry point for the karaoke generator.

This file is maintained for backward compatibility.
New code should use the main entry point in karaoke_prep.cli.
"""

import warnings

warnings.warn(
    "Using karaoke_prep.utils.main is deprecated. "
    "Please use karaoke_prep.cli directly or run 'python -m karaoke_prep' instead.",
    DeprecationWarning,
    stacklevel=2
)

from karaoke_prep.cli import main

if __name__ == "__main__":
    main() 