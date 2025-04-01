import os
import pytest
from unittest.mock import MagicMock, patch, call
from PIL import Image, ImageDraw, ImageFont
import json
from karaoke_prep.karaoke_prep import KaraokePrep

class TestVideo:
    def test_create_video_with_defaults(self, basic_karaoke_prep, temp_dir):
        """Test creating a video with default parameters."""
        # Setup
        output_image_filepath_noext = os.path.join(temp_dir, "output")
        output_video_filepath = os.path.join(temp_dir, "output.mov")
        
        # Mock dependencies
        with patch('PIL.Image.new') as mock_image_new, \
             patch('PIL.ImageDraw.Draw') as mock_draw, \
             patch('PIL.Image.open'), \
             patch('PIL.ImageFont.truetype'), \
             patch('os.system'):
            
            # Configure mock_image_new to return a mock image
            mock_image = MagicMock()
            mock_image_new.return_value = mock_image
            mock_image.resize.return_value = mock_image
            
            # Configure mock_draw to return a mock draw object
            mock_draw_obj = MagicMock()
            mock_draw.return_value = mock_draw_obj
            
            # Call the method
            basic_karaoke_prep.create_video(
                extra_text="Extra Text",
                title_text="Test Title",
                artist_text="Test Artist",
                format=basic_karaoke_prep.title_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath,
                duration=5
            )
            
            # Verify Image.new was called with correct arguments
            mock_image_new.assert_called_once()
            
            # Verify image.save was called for both PNG and JPG
            assert mock_image.save.call_count == 2
            
            # Verify os.system was called to create the video
            assert basic_karaoke_prep._os_system.call_count == 1
    
    def test_create_video_with_existing_image(self, basic_karaoke_prep, temp_dir):
        """Test creating a video with an existing image."""
        # Setup
        existing_image = os.path.join(temp_dir, "existing.png")
        output_image_filepath_noext = os.path.join(temp_dir, "output")
        output_video_filepath = os.path.join(temp_dir, "output.mov")
        
        # Create the existing image file
        with open(existing_image, "w") as f:
            f.write("mock image content")
        
        # Mock dependencies
        with patch('PIL.Image.open') as mock_image_open, \
             patch('shutil.copy2') as mock_copy, \
             patch('os.system'):
            
            # Configure mock_image_open to return a mock image
            mock_image = MagicMock()
            mock_image_open.return_value = mock_image
            mock_image.mode = "RGBA"
            
            # Call the method
            basic_karaoke_prep.create_video(
                extra_text=None,
                title_text=None,
                artist_text=None,
                format=basic_karaoke_prep.title_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath,
                existing_image=existing_image,
                duration=5
            )
            
            # Verify shutil.copy2 was called with correct arguments
            mock_copy.assert_called_once_with(existing_image, output_image_filepath_noext + ".png")
            
            # Verify os.system was called to create the video
            assert basic_karaoke_prep._os_system.call_count == 1
    
    def test_create_video_with_background_image(self, basic_karaoke_prep, temp_dir):
        """Test creating a video with a background image."""
        # Setup
        background_image = os.path.join(temp_dir, "background.png")
        output_image_filepath_noext = os.path.join(temp_dir, "output")
        output_video_filepath = os.path.join(temp_dir, "output.mov")
        
        # Create the background image file
        with open(background_image, "w") as f:
            f.write("mock background image content")
        
        # Create a format with background image
        format = basic_karaoke_prep.title_format.copy()
        format["background_image"] = background_image
        
        # Mock dependencies
        with patch('PIL.Image.open') as mock_image_open, \
             patch('PIL.ImageDraw.Draw'), \
             patch('PIL.ImageFont.truetype'), \
             patch('os.path.exists', return_value=True), \
             patch('os.system'):
            
            # Configure mock_image_open to return a mock image
            mock_image = MagicMock()
            mock_image_open.return_value = mock_image
            mock_image.resize.return_value = mock_image
            
            # Call the method
            basic_karaoke_prep.create_video(
                extra_text="Extra Text",
                title_text="Test Title",
                artist_text="Test Artist",
                format=format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath,
                duration=5
            )
            
            # Verify Image.open was called with the background image
            mock_image_open.assert_called_once_with(background_image)
            
            # Verify image.save was called for both PNG and JPG
            assert mock_image.save.call_count == 2
            
            # Verify os.system was called to create the video
            assert basic_karaoke_prep._os_system.call_count == 1
    
    def test_create_video_with_no_output_images(self, basic_karaoke_prep, temp_dir):
        """Test creating a video without saving output images."""
        # Setup
        output_image_filepath_noext = os.path.join(temp_dir, "output")
        output_video_filepath = os.path.join(temp_dir, "output.mov")
        
        # Mock dependencies
        with patch('PIL.Image.new') as mock_image_new, \
             patch('PIL.ImageDraw.Draw'), \
             patch('PIL.ImageFont.truetype'), \
             patch('os.system'):
            
            # Configure mock_image_new to return a mock image
            mock_image = MagicMock()
            mock_image_new.return_value = mock_image
            mock_image.resize.return_value = mock_image
            
            # Call the method
            basic_karaoke_prep.create_video(
                extra_text="Extra Text",
                title_text="Test Title",
                artist_text="Test Artist",
                format=basic_karaoke_prep.title_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath,
                output_png=False,
                output_jpg=False,
                duration=5
            )
            
            # Verify image.save was not called
            assert mock_image.save.call_count == 0
            
            # Verify os.system was called to create the video
            assert basic_karaoke_prep._os_system.call_count == 1
    
    def test_create_video_with_zero_duration(self, basic_karaoke_prep, temp_dir):
        """Test creating a video with zero duration (no video, just images)."""
        # Setup
        output_image_filepath_noext = os.path.join(temp_dir, "output")
        output_video_filepath = os.path.join(temp_dir, "output.mov")
        
        # Mock dependencies
        with patch('PIL.Image.new') as mock_image_new, \
             patch('PIL.ImageDraw.Draw'), \
             patch('PIL.ImageFont.truetype'), \
             patch('os.system'):
            
            # Configure mock_image_new to return a mock image
            mock_image = MagicMock()
            mock_image_new.return_value = mock_image
            mock_image.resize.return_value = mock_image
            
            # Call the method
            basic_karaoke_prep.create_video(
                extra_text="Extra Text",
                title_text="Test Title",
                artist_text="Test Artist",
                format=basic_karaoke_prep.title_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath,
                duration=0
            )
            
            # Verify image.save was called for both PNG and JPG
            assert mock_image.save.call_count == 2
            
            # Verify os.system was not called to create the video
            assert basic_karaoke_prep._os_system.call_count == 0
    
    def test_create_title_video(self, basic_karaoke_prep, temp_dir):
        """Test creating a title video."""
        # Setup
        output_image_filepath_noext = os.path.join(temp_dir, "output")
        output_video_filepath = os.path.join(temp_dir, "output.mov")
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'create_video') as mock_create_video:
            # Call the method
            basic_karaoke_prep.create_title_video(
                artist="Test Artist",
                title="Test Title",
                format=basic_karaoke_prep.title_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath
            )
            
            # Verify create_video was called with correct arguments
            mock_create_video.assert_called_once_with(
                title_text="Test Title",
                artist_text="Test Artist",
                extra_text=basic_karaoke_prep.title_format["extra_text"],
                format=basic_karaoke_prep.title_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath,
                existing_image=basic_karaoke_prep.existing_title_image,
                duration=basic_karaoke_prep.intro_video_duration,
                render_bounding_boxes=basic_karaoke_prep.render_bounding_boxes,
                output_png=basic_karaoke_prep.output_png,
                output_jpg=basic_karaoke_prep.output_jpg
            )
    
    def test_create_end_video(self, basic_karaoke_prep, temp_dir):
        """Test creating an end video."""
        # Setup
        output_image_filepath_noext = os.path.join(temp_dir, "output")
        output_video_filepath = os.path.join(temp_dir, "output.mov")
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'create_video') as mock_create_video:
            # Call the method
            basic_karaoke_prep.create_end_video(
                artist="Test Artist",
                title="Test Title",
                format=basic_karaoke_prep.end_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath
            )
            
            # Verify create_video was called with correct arguments
            mock_create_video.assert_called_once_with(
                title_text="Test Title",
                artist_text="Test Artist",
                extra_text=basic_karaoke_prep.end_format["extra_text"],
                format=basic_karaoke_prep.end_format,
                output_image_filepath_noext=output_image_filepath_noext,
                output_video_filepath=output_video_filepath,
                existing_image=basic_karaoke_prep.existing_end_image,
                duration=basic_karaoke_prep.end_video_duration,
                render_bounding_boxes=basic_karaoke_prep.render_bounding_boxes,
                output_png=basic_karaoke_prep.output_png,
                output_jpg=basic_karaoke_prep.output_jpg
            )
    
    def test_hex_to_rgb(self, basic_karaoke_prep):
        """Test converting hex color to RGB tuple."""
        # Test with hash prefix
        assert basic_karaoke_prep.hex_to_rgb("#FF0000") == (255, 0, 0)
        
        # Test without hash prefix
        assert basic_karaoke_prep.hex_to_rgb("00FF00") == (0, 255, 0)
        
        # Test with lowercase
        assert basic_karaoke_prep.hex_to_rgb("#0000ff") == (0, 0, 255)
    
    def test_transform_text(self, basic_karaoke_prep):
        """Test transforming text based on specified type."""
        # Test uppercase
        assert basic_karaoke_prep._transform_text("test", "uppercase") == "TEST"
        
        # Test lowercase
        assert basic_karaoke_prep._transform_text("TEST", "lowercase") == "test"
        
        # Test propercase
        assert basic_karaoke_prep._transform_text("test title", "propercase") == "Test Title"
        
        # Test none
        assert basic_karaoke_prep._transform_text("Test", "none") == "Test"
        
        # Test invalid transform type
        assert basic_karaoke_prep._transform_text("Test", "invalid") == "Test"
