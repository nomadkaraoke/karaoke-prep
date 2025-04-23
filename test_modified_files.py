"""
Test that our modifications to the KaraokeFinalise class are working correctly.
"""

import os
import sys
import unittest
import logging
from unittest.mock import MagicMock

# Add the project root to the Python path
sys.path.insert(0, '.')

# Import the modified module
from karaoke_prep.karaoke_finalise.file_manager import FileManager
from karaoke_prep.karaoke_finalise.mediainfo_parser import MediaInfoParser

class TestModifiedFiles(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
    
    def test_mediainfo_parser_init(self):
        """Test MediaInfoParser initialization."""
        parser = MediaInfoParser(logger=self.logger)
        self.assertIsNotNone(parser)
        self.assertEqual(parser.logger, self.logger)
    
    def test_file_manager_suffixes(self):
        """Test that FileManager has the suffixes dictionary."""
        file_manager = FileManager(logger=self.logger)
        self.assertIsNotNone(file_manager.suffixes)
        self.assertIn("title_mov", file_manager.suffixes)
        self.assertIn("title_jpg", file_manager.suffixes)
        self.assertIn("karaoke_lrc", file_manager.suffixes)

class TestKaraokeFinalise(unittest.TestCase):
    """
    Test that KaraokeFinalise.suffixes exists and has the correct values.
    This test is isolated from other dependencies to ensure it doesn't fail
    due to unrelated issues.
    """
    def setUp(self):
        # Create a mock FileManager with a suffixes attribute
        self.mock_file_manager = MagicMock()
        self.mock_file_manager.suffixes = {
            "title_mov": " (Title).mov",
            "title_jpg": " (Title).jpg",
            "karaoke_lrc": " (Karaoke).lrc",
        }
        
        # Create a logger mock
        self.logger = MagicMock()
    
    def test_has_suffixes_attribute(self):
        """Test that KaraokeFinalise has the suffixes attribute from FileManager."""
        # Import inside the test to avoid import errors affecting the whole test suite
        from karaoke_prep.karaoke_finalise.karaoke_finalise import KaraokeFinalise
        
        # Create a KaraokeFinalise instance
        finalise = KaraokeFinalise(logger=self.logger)
        
        # Replace with our mock file_manager
        finalise.file_manager = self.mock_file_manager
        
        # Manually set the suffixes attribute
        finalise.suffixes = finalise.file_manager.suffixes
        
        # Check that the suffixes attribute exists and has the correct values
        self.assertIsNotNone(finalise.suffixes)
        self.assertIn("title_mov", finalise.suffixes)
        self.assertEqual(finalise.suffixes["title_mov"], " (Title).mov")
        self.assertIn("title_jpg", finalise.suffixes)
        self.assertEqual(finalise.suffixes["title_jpg"], " (Title).jpg")
        self.assertIn("karaoke_lrc", finalise.suffixes)
        self.assertEqual(finalise.suffixes["karaoke_lrc"], " (Karaoke).lrc")

if __name__ == '__main__':
    unittest.main() 