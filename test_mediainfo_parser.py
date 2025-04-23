import sys
import unittest
from unittest.mock import patch, MagicMock

# Import the module directly
sys.path.insert(0, '.')
from karaoke_prep.karaoke_finalise.mediainfo_parser import MediaInfoParser

class TestMediaInfoParser(unittest.TestCase):
    def test_init(self):
        parser = MediaInfoParser()
        self.assertIsNotNone(parser)
        self.assertIsNotNone(parser.logger)

if __name__ == '__main__':
    unittest.main() 