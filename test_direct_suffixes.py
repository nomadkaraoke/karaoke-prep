#!/usr/bin/env python3

import unittest
import os

class TestDirectSuffixes(unittest.TestCase):
    def test_karaoke_finalise_has_suffixes(self):
        """Test that KaraokeFinalise class has suffixes attribute."""
        # Read the content of the KaraokeFinalise class implementation
        file_path = os.path.join('karaoke_prep', 'karaoke_finalise', 'karaoke_finalise.py')
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Check if the line assigning suffixes exists in __init__
        self.assertIn('self.suffixes = self.file_manager.suffixes', content, 
                     "KaraokeFinalise class should assign FileManager's suffixes")
        
        print("✅ KaraokeFinalise correctly assigns suffixes from FileManager")

if __name__ == '__main__':
    unittest.main() 