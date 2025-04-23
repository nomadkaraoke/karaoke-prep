import sys
import unittest
import logging
import os
import json
import subprocess
import xml.etree.ElementTree as ET
from unittest.mock import patch, MagicMock

# Copy the MediaInfoParser implementation directly
class MediaInfoParser:
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
    
    def get_mediainfo_xml(self, file_path):
        try:
            result = subprocess.run(
                ["mediainfo", "--Output=XML", file_path],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except FileNotFoundError as e:
            if "mediainfo" in str(e):
                raise RuntimeError("MediaInfo not found. Please install MediaInfo.") from e
            raise
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"MediaInfo command failed with return code {e.returncode}: {e.stderr}") from e

class TestMediaInfoParser(unittest.TestCase):
    def setUp(self):
        self.logger = MagicMock()
        self.parser = MediaInfoParser(logger=self.logger)
    
    def test_init(self):
        self.assertIsNotNone(self.parser)
        self.assertEqual(self.parser.logger, self.logger)
    
    def test_init_default_logger(self):
        parser = MediaInfoParser()
        self.assertIsNotNone(parser.logger)

if __name__ == '__main__':
    unittest.main() 