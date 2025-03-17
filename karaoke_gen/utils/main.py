#!/usr/bin/env python
"""
Main entry point for the karaoke generator.

This file is maintained for backward compatibility.
New code should use the main entry point in karaoke_gen.cli.
"""

import warnings

warnings.warn(
    "Using karaoke_gen.utils.main is deprecated. "
    "Please use karaoke_gen.cli directly or run 'python -m karaoke_gen' instead.",
    DeprecationWarning,
    stacklevel=2
)

from karaoke_gen.cli import main

if __name__ == "__main__":
    main() 