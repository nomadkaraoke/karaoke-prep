"""
Tests for the utility functions.
"""

import os
import tempfile
import unittest
from pathlib import Path

from karaoke_gen.utils import (
    # File utilities
    sanitize_filename,
    ensure_directory_exists,
    file_exists,
    
    # Path utilities
    normalize_path,
    join_paths,
    get_absolute_path,
    get_relative_path,
    get_filename,
    get_filename_without_extension,
    get_file_extension,
    
    # String utilities
    slugify,
    truncate_string,
    extract_artist_and_title,
    format_duration,
    format_filesize,
)


class TestFileUtils(unittest.TestCase):
    """Test file utility functions."""
    
    def test_sanitize_filename(self):
        """Test sanitize_filename function."""
        # Test with invalid characters
        self.assertEqual(sanitize_filename("file/with\\invalid:chars"), "file_with_invalid_chars")
        
        # Test with leading/trailing spaces and dots
        self.assertEqual(sanitize_filename(" file.with.spaces. "), "file.with.spaces")
        
        # Test with empty string
        self.assertEqual(sanitize_filename(""), "unnamed")
    
    def test_ensure_directory_exists(self):
        """Test ensure_directory_exists function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            test_dir = os.path.join(temp_dir, "test_dir")
            
            # Directory should not exist initially
            self.assertFalse(os.path.exists(test_dir))
            
            # Create directory
            ensure_directory_exists(test_dir)
            
            # Directory should exist now
            self.assertTrue(os.path.exists(test_dir))
            
            # Should not raise exception when called on existing directory
            ensure_directory_exists(test_dir)
    
    def test_file_exists(self):
        """Test file_exists function."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a test file
            test_file = os.path.join(temp_dir, "test_file.txt")
            with open(test_file, "w") as f:
                f.write("test")
            
            # Test with existing file
            self.assertTrue(file_exists(test_file))
            
            # Test with non-existing file
            self.assertFalse(file_exists(os.path.join(temp_dir, "non_existing_file.txt")))


class TestPathUtils(unittest.TestCase):
    """Test path utility functions."""
    
    def test_normalize_path(self):
        """Test normalize_path function."""
        # Test with mixed separators
        self.assertEqual(normalize_path("path/to\\file"), os.path.normpath("path/to/file"))
    
    def test_join_paths(self):
        """Test join_paths function."""
        # Test joining paths
        self.assertEqual(join_paths("path", "to", "file"), os.path.join("path", "to", "file"))
    
    def test_get_absolute_path(self):
        """Test get_absolute_path function."""
        # Test with relative path
        self.assertEqual(get_absolute_path("."), os.path.abspath("."))
    
    def test_get_relative_path(self):
        """Test get_relative_path function."""
        # Test with absolute path
        abs_path = os.path.abspath(".")
        self.assertEqual(get_relative_path(abs_path, os.path.dirname(abs_path)), os.path.basename(abs_path))
    
    def test_get_filename(self):
        """Test get_filename function."""
        # Test with path
        self.assertEqual(get_filename("/path/to/file.txt"), "file.txt")
    
    def test_get_filename_without_extension(self):
        """Test get_filename_without_extension function."""
        # Test with path and extension
        self.assertEqual(get_filename_without_extension("/path/to/file.txt"), "file")
    
    def test_get_file_extension(self):
        """Test get_file_extension function."""
        # Test with path and extension
        self.assertEqual(get_file_extension("/path/to/file.txt"), ".txt")


class TestStringUtils(unittest.TestCase):
    """Test string utility functions."""
    
    def test_slugify(self):
        """Test slugify function."""
        # Test with spaces and special characters
        self.assertEqual(slugify("Hello World!"), "hello-world")
        
        # Test with unicode characters
        self.assertEqual(slugify("Héllö Wörld"), "hello-world")
    
    def test_truncate_string(self):
        """Test truncate_string function."""
        # Test with string shorter than max length
        self.assertEqual(truncate_string("Hello", 10), "Hello")
        
        # Test with string longer than max length
        self.assertEqual(truncate_string("Hello World", 8), "Hello...")
    
    def test_extract_artist_and_title(self):
        """Test extract_artist_and_title function."""
        # Test with standard format
        self.assertEqual(
            extract_artist_and_title("Artist - Title.mp3"),
            {"artist": "Artist", "title": "Title"}
        )
        
        # Test with no separator
        self.assertEqual(
            extract_artist_and_title("Title.mp3"),
            {"artist": "", "title": "Title"}
        )
    
    def test_format_duration(self):
        """Test format_duration function."""
        # Test with seconds
        self.assertEqual(format_duration(65), "01:05")
        
        # Test with minutes
        self.assertEqual(format_duration(125), "02:05")
    
    def test_format_filesize(self):
        """Test format_filesize function."""
        # Test with bytes
        self.assertEqual(format_filesize(500), "500 B")
        
        # Test with kilobytes
        self.assertEqual(format_filesize(1500), "1.5 KB")
        
        # Test with megabytes
        self.assertEqual(format_filesize(1500000), "1.4 MB")


if __name__ == "__main__":
    unittest.main() 