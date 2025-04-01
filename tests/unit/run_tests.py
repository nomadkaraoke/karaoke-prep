#!/usr/bin/env python3
"""
Test runner script for KaraokePrep unit tests.
"""

import os
import sys
import pytest

def main():
    """Run all unit tests for KaraokePrep."""
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Add the project root to the Python path
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    sys.path.insert(0, project_root)
    
    # Run pytest with appropriate arguments
    args = [
        script_dir,  # Run tests in the unit directory
        '-v',        # Verbose output
        '--cov=karaoke_prep',  # Measure code coverage for the karaoke_prep package
        '--cov-report=term',   # Display coverage report in the terminal
    ]
    
    # Add any command-line arguments
    args.extend(sys.argv[1:])
    
    # Run pytest
    return pytest.main(args)

if __name__ == '__main__':
    sys.exit(main())
