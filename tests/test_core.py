"""
Tests for the core components.
"""

import unittest
from unittest.mock import MagicMock, patch

from karaoke_prep.core import ProjectConfig, Track, KaraokeGenError


class TestProjectConfig(unittest.TestCase):
    """Test ProjectConfig class."""
    
    def test_init_with_minimal_args(self):
        """Test initialization with minimal arguments."""
        config = ProjectConfig()
        
        # Check default values
        self.assertIsNone(config.artist)
        self.assertIsNone(config.title)
        self.assertIsNone(config.input_media)
        self.assertFalse(config.dry_run)
        self.assertEqual(config.output_dir, ".")
    
    def test_init_with_all_args(self):
        """Test initialization with all arguments."""
        logger = MagicMock()
        
        config = ProjectConfig(
            artist="Test Artist",
            title="Test Title",
            input_media="test.mp3",
            dry_run=True,
            logger=logger,
            output_dir="/tmp",
            create_track_subfolders=True,
        )
        
        # Check values
        self.assertEqual(config.artist, "Test Artist")
        self.assertEqual(config.title, "Test Title")
        self.assertEqual(config.input_media, "test.mp3")
        self.assertTrue(config.dry_run)
        self.assertEqual(config.logger, logger)
        self.assertEqual(config.output_dir, "/tmp")
        self.assertTrue(config.create_track_subfolders)


class TestTrack(unittest.TestCase):
    """Test Track class."""
    
    def test_init_with_minimal_args(self):
        """Test initialization with minimal arguments."""
        track = Track(artist="Test Artist", title="Test Title")
        
        # Check values
        self.assertEqual(track.artist, "Test Artist")
        self.assertEqual(track.title, "Test Title")
        self.assertIsNone(track.input_media)
    
    def test_init_with_all_args(self):
        """Test initialization with all arguments."""
        track = Track(
            artist="Test Artist",
            title="Test Title",
            input_media="test.mp3",
            input_audio_wav="test.wav",
            input_still_image="test.jpg",
            lyrics="Test lyrics",
        )
        
        # Check values
        self.assertEqual(track.artist, "Test Artist")
        self.assertEqual(track.title, "Test Title")
        self.assertEqual(track.input_media, "test.mp3")
        self.assertEqual(track.input_audio_wav, "test.wav")
        self.assertEqual(track.input_still_image, "test.jpg")
        self.assertEqual(track.lyrics, "Test lyrics")


class TestKaraokeGenError(unittest.TestCase):
    """Test KaraokeGenError class."""
    
    def test_error_message(self):
        """Test error message."""
        error = KaraokeGenError("Test error")
        self.assertEqual(str(error), "Test error")
    
    def test_error_with_cause(self):
        """Test error with cause."""
        cause = ValueError("Original error")
        error = KaraokeGenError("Test error", cause=cause)
        self.assertEqual(str(error), "Test error")
        self.assertEqual(error.__cause__, cause)


if __name__ == "__main__":
    unittest.main() 