#!/usr/bin/env python3
import os
import sys
import pytest

if __name__ == "__main__":
    # Add the project root to the Python path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    sys.path.insert(0, project_root)
    
    # Run pytest with coverage
    sys.exit(pytest.main([
        "--cov=karaoke_prep",
        "--cov-report=term",
        "-v",
        os.path.dirname(__file__)
    ]))
