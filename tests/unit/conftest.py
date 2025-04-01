import os
import pytest
import logging
import tempfile
from unittest.mock import MagicMock, patch
from karaoke_prep.karaoke_prep import KaraokePrep

@pytest.fixture
def mock_logger():
    """Fixture to provide a mock logger."""
    logger = MagicMock(spec=logging.Logger)
    return logger

@pytest.fixture
def temp_dir():
    """Fixture to provide a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname

@pytest.fixture
def basic_karaoke_prep(mock_logger):
    """Fixture to provide a basic KaraokePrep instance with mocked logger."""
    return KaraokePrep(
        input_media=None,
        artist="Test Artist",
        title="Test Title",
        logger=mock_logger,
        dry_run=True
    )

@pytest.fixture
def mock_ffmpeg():
    """Fixture to mock ffmpeg commands."""
    with patch('os.system') as mock_system:
        mock_system.return_value = 0
        yield mock_system
