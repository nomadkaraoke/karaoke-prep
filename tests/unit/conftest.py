import os
import pytest
import tempfile
import logging
from unittest.mock import MagicMock
from karaoke_prep.karaoke_prep import KaraokePrep
import inspect

@pytest.fixture
def mock_logger():
    """Return a mock logger for testing."""
    return MagicMock(spec=logging.Logger)

@pytest.fixture
def mock_ffmpeg():
    """Return a mock for os.system to avoid executing ffmpeg commands."""
    return MagicMock()

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield temp_dir

@pytest.fixture
def basic_karaoke_prep(mock_logger, mock_ffmpeg):
    """Return a basic KaraokePrep instance for testing."""
    with MagicMock() as mock_os_system:
        # Create a KaraokePrep instance with a mock logger
        karaoke_prep = KaraokePrep(logger=mock_logger)
        
        # Replace the ffmpeg_base_command with a mock
        karaoke_prep.ffmpeg_base_command = "mock_ffmpeg"
        
        # Mock os.system to avoid executing commands
        karaoke_prep._os_system = mock_os_system
        
        yield karaoke_prep

def pytest_collection_modifyitems(items):
    """Mark async tests with asyncio marker."""
    for item in items:
        if inspect.iscoroutinefunction(item.obj):
            item.add_marker(pytest.mark.asyncio)
