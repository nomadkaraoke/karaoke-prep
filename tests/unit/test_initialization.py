import os
import pytest
from unittest.mock import MagicMock, patch
import json
import logging
from karaoke_prep.karaoke_prep import KaraokePrep
import tempfile

class TestInitialization:
    def test_init_with_defaults(self, mock_logger):
        """Test initialization with default parameters."""
        karaoke_prep = KaraokePrep(logger=mock_logger)
        
        assert karaoke_prep.input_media is None
        assert karaoke_prep.artist is None
        assert karaoke_prep.title is None
        assert karaoke_prep.dry_run is False
        assert karaoke_prep.logger is mock_logger
        assert karaoke_prep.output_dir == "."
        assert karaoke_prep.lossless_output_format == "flac"
        assert karaoke_prep.create_track_subfolders is False
        
    def test_init_with_custom_params(self, mock_logger):
        """Test initialization with custom parameters."""
        with patch('os.makedirs'):
            karaoke_prep = KaraokePrep(
                input_media="test_media.mp4",
                artist="Test Artist",
                title="Test Title",
                dry_run=True,
                logger=mock_logger,
                output_dir="test_output",
                lossless_output_format="WAV",
                create_track_subfolders=True
            )
        
        assert karaoke_prep.input_media == "test_media.mp4"
        assert karaoke_prep.artist == "Test Artist"
        assert karaoke_prep.title == "Test Title"
        assert karaoke_prep.dry_run is True
        assert karaoke_prep.logger is mock_logger
        assert karaoke_prep.output_dir == "test_output"
        assert karaoke_prep.lossless_output_format == "wav"
        assert karaoke_prep.create_track_subfolders is True
    
    def test_init_creates_output_dir(self, mock_logger, temp_dir):
        """Test that initialization creates the output directory if it doesn't exist."""
        output_dir = os.path.join(temp_dir, "new_dir")
        
        with patch('os.makedirs') as mock_makedirs:
            karaoke_prep = KaraokePrep(
                logger=mock_logger,
                output_dir=output_dir
            )
            mock_makedirs.assert_called_once_with(output_dir)
    
    def test_init_with_custom_style_params(self, mock_logger, temp_dir):
        """Test initialization with custom style parameters."""
        # Create a temporary style params file
        style_params = {
            "intro": {
                "video_duration": 10,
                "background_color": "#FF0000",
                "background_image": None,
                "existing_image": None,
                "font": "CustomFont.ttf",
                "artist_color": "#ffffff",
                "title_color": "#ffffff",
                "extra_text": None,
                "extra_text_color": "#ffffff",
                "title_region": "10, 10, 100, 50",
                "artist_region": "10, 70, 100, 50",
                "extra_text_region": "10, 130, 100, 50",
                "title_text_transform": None,
                "artist_text_transform": None
            },
            "end": {
                "video_duration": 8,
                "background_color": "#0000FF",
                "background_image": None,
                "existing_image": None,
                "font": "CustomFont.ttf",
                "artist_color": "#ffffff",
                "title_color": "#ffffff",
                "extra_text": "Thank you!",
                "extra_text_color": "#ffffff",
                "title_region": None,
                "artist_region": None,
                "extra_text_region": None,
                "title_text_transform": None,
                "artist_text_transform": None
            }
        }
        
        style_params_path = os.path.join(temp_dir, "style_params.json")
        
        with open(style_params_path, "w") as f:
            json.dump(style_params, f)
        
        karaoke_prep = KaraokePrep(
            logger=mock_logger,
            style_params_json=style_params_path
        )
        
        assert karaoke_prep.intro_video_duration == 10
        assert karaoke_prep.end_video_duration == 8
        assert karaoke_prep.title_format["background_color"] == "#FF0000"
        assert karaoke_prep.end_format["background_color"] == "#0000FF"
    
    def test_init_with_invalid_style_params_file(self, mock_logger):
        """Test initialization with an invalid style params file path."""
        with pytest.raises(SystemExit):
            KaraokePrep(
                logger=mock_logger,
                style_params_json="/nonexistent/path.json"
            )
    
    def test_init_with_invalid_style_params_json(self, mock_logger, temp_dir):
        """Test initialization with invalid JSON in style params file."""
        # Create a file with invalid JSON
        style_params_path = os.path.join(temp_dir, "invalid_style_params.json")
        
        with open(style_params_path, "w") as f:
            f.write("This is not valid JSON")
        
        with pytest.raises(SystemExit):
            KaraokePrep(
                logger=mock_logger,
                style_params_json=style_params_path
            )
    
    def test_parse_region(self):
        """Test the parse_region static method."""
        # Instantiate a basic KaraokePrep to access video_generator
        kp = KaraokePrep(logger=MagicMock())
        # Test valid region string
        # Call on video_generator
        region = kp.video_generator.parse_region("10,20,300,400")
        assert region == (10, 20, 300, 400)

        # Test None input
        assert kp.video_generator.parse_region(None) is None

        # Test invalid format
        with pytest.raises(ValueError, match="Invalid region format: 10,20,300. Expected 4 elements: 'x,y,width,height'"):
            kp.video_generator.parse_region("10,20,300")
        with pytest.raises(ValueError, match="Invalid region format: 10,twenty,300,400. Could not convert to integers. Expected format: 'x,y,width,height'"):
            kp.video_generator.parse_region("10,twenty,300,400")
