#!/usr/bin/env python3

import sys
import os
import unittest

# Add the project root to the path so we can import directly
sys.path.insert(0, os.path.abspath('.'))

class TestSuffixesFix(unittest.TestCase):
    
    def test_karaoke_finalise_has_suffixes(self):
        """Test that KaraokeFinalise correctly gets suffixes from FileManager."""
        from karaoke_prep.karaoke_finalise.karaoke_finalise import KaraokeFinalise
        
        # Create a KaraokeFinalise instance with minimal dependencies
        kf = KaraokeFinalise(
            input_dir="dummy_input",
            output_dir="dummy_output"
        )
        
        # Check that suffixes attribute exists and matches the file_manager's suffixes
        self.assertTrue(hasattr(kf, 'suffixes'), "KaraokeFinalise should have a 'suffixes' attribute")
        self.assertEqual(kf.suffixes, kf.file_manager.suffixes, 
                        "KaraokeFinalise.suffixes should match FileManager.suffixes")
        
        # Print the values for debugging
        print(f"FileManager suffixes: {kf.file_manager.suffixes}")
        print(f"KaraokeFinalise suffixes: {kf.suffixes}")

if __name__ == '__main__':
    unittest.main() 