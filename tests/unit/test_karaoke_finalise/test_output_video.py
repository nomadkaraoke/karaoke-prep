import pytest
from unittest.mock import MagicMock, patch, call
import tempfile
import os
import shutil

from karaoke_prep.karaoke_finalise.media_processor import MediaProcessor
from karaoke_prep.karaoke_finalise.mediainfo_parser import MediaInfoParser

# Constants for testing
TEST_VIDEO_PATH = "test_video.mp4"
TEST_OVERLAY_PATH = "test_overlay.png"
TEST_OUTPUT_PATH = "output_video.mp4"
TEST_DIMENSIONS = (1920, 1080)
TEST_DURATION = 180.5
TEST_CROP_PARAMS = {
    "top": 10,
    "bottom": 10,
    "left": 10,
    "right": 10
}

@pytest.fixture
def mock_logger():
    """Fixture for a mocked logger."""
    return MagicMock()

@pytest.fixture
def mock_mediainfo_parser():
    """Fixture for a mocked MediaInfoParser."""
    parser = MagicMock(spec=MediaInfoParser)
    parser.get_video_resolution.return_value = TEST_DIMENSIONS
    parser.get_video_duration.return_value = TEST_DURATION
    return parser

@pytest.fixture
def media_processor(mock_logger, mock_mediainfo_parser):
    """Fixture for MediaProcessor instance."""
    processor = MediaProcessor(logger=mock_logger)
    processor.mediainfo_parser = mock_mediainfo_parser
    return processor

@patch('subprocess.run')
def test_crop_video(mock_subprocess_run, media_processor):
    """Test cropping video with FFmpeg."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess_run.return_value = mock_process
    
    # Execute
    media_processor.crop_video(
        TEST_VIDEO_PATH, 
        TEST_OUTPUT_PATH, 
        TEST_CROP_PARAMS
    )
    
    # Verify
    mock_subprocess_run.assert_called_once()
    cmd_args = mock_subprocess_run.call_args[0][0]
    
    # Check that ffmpeg command includes crop filter with correct parameters
    assert "ffmpeg" in cmd_args[0]
    crop_filter_found = False
    for i, arg in enumerate(cmd_args):
        if arg == "-vf" and i + 1 < len(cmd_args):
            if "crop=" in cmd_args[i + 1]:
                crop_filter_found = True
                crop_arg = cmd_args[i + 1]
                # Verify crop parameters are applied correctly
                assert f"crop=in_w-{TEST_CROP_PARAMS['left']}-{TEST_CROP_PARAMS['right']}:in_h-{TEST_CROP_PARAMS['top']}-{TEST_CROP_PARAMS['bottom']}:{TEST_CROP_PARAMS['left']}:{TEST_CROP_PARAMS['top']}" in crop_arg
                break
    
    assert crop_filter_found, "Crop filter not found in ffmpeg command"
    assert TEST_OUTPUT_PATH in cmd_args

@patch('subprocess.run')
def test_crop_video_error_handling(mock_subprocess_run, media_processor):
    """Test error handling when FFmpeg cropping fails."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = b"Error: something went wrong"
    mock_subprocess_run.return_value = mock_process
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        media_processor.crop_video(
            TEST_VIDEO_PATH, 
            TEST_OUTPUT_PATH, 
            TEST_CROP_PARAMS
        )
    
    assert "FFmpeg command failed" in str(excinfo.value)
    assert mock_logger.error.called

@patch('subprocess.run')
def test_overlay_image(mock_subprocess_run, media_processor):
    """Test overlaying an image on video with FFmpeg."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess_run.return_value = mock_process
    
    # Execute
    media_processor.overlay_image(
        TEST_VIDEO_PATH, 
        TEST_OVERLAY_PATH,
        TEST_OUTPUT_PATH
    )
    
    # Verify
    mock_subprocess_run.assert_called_once()
    cmd_args = mock_subprocess_run.call_args[0][0]
    
    # Check that ffmpeg command includes overlay filter
    assert "ffmpeg" in cmd_args[0]
    overlay_filter_found = False
    for i, arg in enumerate(cmd_args):
        if arg == "-filter_complex" and i + 1 < len(cmd_args):
            if "overlay" in cmd_args[i + 1]:
                overlay_filter_found = True
                break
    
    assert overlay_filter_found, "Overlay filter not found in ffmpeg command"
    assert TEST_OUTPUT_PATH in cmd_args

@patch('subprocess.run')
def test_overlay_image_error_handling(mock_subprocess_run, media_processor):
    """Test error handling when FFmpeg overlay fails."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = b"Error: something went wrong"
    mock_subprocess_run.return_value = mock_process
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        media_processor.overlay_image(
            TEST_VIDEO_PATH, 
            TEST_OVERLAY_PATH,
            TEST_OUTPUT_PATH
        )
    
    assert "FFmpeg command failed" in str(excinfo.value)
    assert mock_logger.error.called

@patch('subprocess.run')
def test_create_video_thumbnail(mock_subprocess_run, media_processor):
    """Test creating a thumbnail from video with FFmpeg."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess_run.return_value = mock_process
    thumbnail_path = "thumbnail.jpg"
    
    # Execute
    media_processor.create_video_thumbnail(
        TEST_VIDEO_PATH, 
        thumbnail_path
    )
    
    # Verify
    mock_subprocess_run.assert_called_once()
    cmd_args = mock_subprocess_run.call_args[0][0]
    
    # Check that ffmpeg command is correct for thumbnail creation
    assert "ffmpeg" in cmd_args[0]
    assert "-ss" in cmd_args
    assert thumbnail_path in cmd_args

@patch('subprocess.run')
def test_create_video_thumbnail_error_handling(mock_subprocess_run, media_processor):
    """Test error handling when FFmpeg thumbnail creation fails."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = b"Error: something went wrong"
    mock_subprocess_run.return_value = mock_process
    thumbnail_path = "thumbnail.jpg"
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        media_processor.create_video_thumbnail(
            TEST_VIDEO_PATH, 
            thumbnail_path
        )
    
    assert "FFmpeg command failed" in str(excinfo.value)
    assert mock_logger.error.called

@patch('subprocess.run')
def test_extract_audio(mock_subprocess_run, media_processor):
    """Test extracting audio from video with FFmpeg."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess_run.return_value = mock_process
    audio_path = "audio.mp3"
    
    # Execute
    media_processor.extract_audio(
        TEST_VIDEO_PATH, 
        audio_path
    )
    
    # Verify
    mock_subprocess_run.assert_called_once()
    cmd_args = mock_subprocess_run.call_args[0][0]
    
    # Check that ffmpeg command is correct for audio extraction
    assert "ffmpeg" in cmd_args[0]
    assert "-vn" in cmd_args
    assert audio_path in cmd_args

@patch('subprocess.run')
def test_extract_audio_error_handling(mock_subprocess_run, media_processor):
    """Test error handling when FFmpeg audio extraction fails."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = b"Error: something went wrong"
    mock_subprocess_run.return_value = mock_process
    audio_path = "audio.mp3"
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        media_processor.extract_audio(
            TEST_VIDEO_PATH, 
            audio_path
        )
    
    assert "FFmpeg command failed" in str(excinfo.value)
    assert mock_logger.error.called

@patch('subprocess.run')
def test_scale_video(mock_subprocess_run, media_processor):
    """Test scaling video with FFmpeg."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess_run.return_value = mock_process
    target_resolution = (1280, 720)
    
    # Execute
    media_processor.scale_video(
        TEST_VIDEO_PATH, 
        TEST_OUTPUT_PATH,
        target_resolution
    )
    
    # Verify
    mock_subprocess_run.assert_called_once()
    cmd_args = mock_subprocess_run.call_args[0][0]
    
    # Check that ffmpeg command includes scale filter with correct parameters
    assert "ffmpeg" in cmd_args[0]
    scale_filter_found = False
    for i, arg in enumerate(cmd_args):
        if arg == "-vf" and i + 1 < len(cmd_args):
            if "scale=" in cmd_args[i + 1]:
                scale_filter_found = True
                scale_arg = cmd_args[i + 1]
                # Verify scale parameters are applied correctly
                assert f"scale={target_resolution[0]}:{target_resolution[1]}" in scale_arg
                break
    
    assert scale_filter_found, "Scale filter not found in ffmpeg command"
    assert TEST_OUTPUT_PATH in cmd_args

@patch('subprocess.run')
def test_scale_video_error_handling(mock_subprocess_run, media_processor):
    """Test error handling when FFmpeg scaling fails."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = b"Error: something went wrong"
    mock_subprocess_run.return_value = mock_process
    target_resolution = (1280, 720)
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        media_processor.scale_video(
            TEST_VIDEO_PATH, 
            TEST_OUTPUT_PATH,
            target_resolution
        )
    
    assert "FFmpeg command failed" in str(excinfo.value)
    assert mock_logger.error.called

@patch('subprocess.run')
def test_overlay_text(mock_subprocess_run, media_processor):
    """Test overlaying text on video with FFmpeg."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess_run.return_value = mock_process
    text = "Test Text"
    position = (100, 100)
    font_size = 24
    font_color = "white"
    
    # Execute
    media_processor.overlay_text(
        TEST_VIDEO_PATH, 
        TEST_OUTPUT_PATH,
        text,
        position,
        font_size,
        font_color
    )
    
    # Verify
    mock_subprocess_run.assert_called_once()
    cmd_args = mock_subprocess_run.call_args[0][0]
    
    # Check that ffmpeg command includes drawtext filter
    assert "ffmpeg" in cmd_args[0]
    drawtext_filter_found = False
    for i, arg in enumerate(cmd_args):
        if arg == "-vf" and i + 1 < len(cmd_args):
            if "drawtext=" in cmd_args[i + 1]:
                drawtext_filter_found = True
                drawtext_arg = cmd_args[i + 1]
                # Verify drawtext parameters are applied correctly
                assert f"text='{text}'" in drawtext_arg
                assert f"x={position[0]}" in drawtext_arg
                assert f"y={position[1]}" in drawtext_arg
                assert f"fontsize={font_size}" in drawtext_arg
                assert f"fontcolor={font_color}" in drawtext_arg
                break
    
    assert drawtext_filter_found, "Drawtext filter not found in ffmpeg command"
    assert TEST_OUTPUT_PATH in cmd_args

@patch('subprocess.run')
def test_overlay_text_error_handling(mock_subprocess_run, media_processor):
    """Test error handling when FFmpeg text overlay fails."""
    # Setup
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_process.stderr = b"Error: something went wrong"
    mock_subprocess_run.return_value = mock_process
    text = "Test Text"
    position = (100, 100)
    font_size = 24
    font_color = "white"
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        media_processor.overlay_text(
            TEST_VIDEO_PATH, 
            TEST_OUTPUT_PATH,
            text,
            position,
            font_size,
            font_color
        )
    
    assert "FFmpeg command failed" in str(excinfo.value)
    assert mock_logger.error.called

def test_get_video_info(media_processor, mock_mediainfo_parser):
    """Test getting video information through the MediaInfoParser."""
    # Execute
    dimensions = media_processor.get_video_dimensions(TEST_VIDEO_PATH)
    duration = media_processor.get_video_duration(TEST_VIDEO_PATH)
    
    # Verify
    assert dimensions == TEST_DIMENSIONS
    assert duration == TEST_DURATION
    mock_mediainfo_parser.get_video_resolution.assert_called_once_with(TEST_VIDEO_PATH)
    mock_mediainfo_parser.get_video_duration.assert_called_once_with(TEST_VIDEO_PATH)

@patch('tempfile.NamedTemporaryFile')
@patch.object(MediaProcessor, 'crop_video')
@patch.object(MediaProcessor, 'overlay_image')
def test_process_video_with_overlay(mock_overlay_image, mock_crop_video, mock_temp_file, media_processor):
    """Test full video processing workflow with cropping and overlay."""
    # Setup
    mock_temp = MagicMock()
    mock_temp.name = "temp_file.mp4"
    mock_temp_file.return_value.__enter__.return_value = mock_temp
    
    # Execute
    media_processor.process_video(
        TEST_VIDEO_PATH,
        TEST_OUTPUT_PATH,
        crop_params=TEST_CROP_PARAMS,
        overlay_path=TEST_OVERLAY_PATH
    )
    
    # Verify
    mock_crop_video.assert_called_once_with(
        TEST_VIDEO_PATH, 
        mock_temp.name, 
        TEST_CROP_PARAMS
    )
    mock_overlay_image.assert_called_once_with(
        mock_temp.name, 
        TEST_OVERLAY_PATH, 
        TEST_OUTPUT_PATH
    )

@patch.object(MediaProcessor, 'crop_video')
@patch.object(MediaProcessor, 'overlay_image')
def test_process_video_crop_only(mock_overlay_image, mock_crop_video, media_processor):
    """Test video processing with only cropping."""
    # Execute
    media_processor.process_video(
        TEST_VIDEO_PATH,
        TEST_OUTPUT_PATH,
        crop_params=TEST_CROP_PARAMS,
        overlay_path=None
    )
    
    # Verify
    mock_crop_video.assert_called_once_with(
        TEST_VIDEO_PATH, 
        TEST_OUTPUT_PATH, 
        TEST_CROP_PARAMS
    )
    mock_overlay_image.assert_not_called()

@patch.object(MediaProcessor, 'crop_video')
@patch.object(MediaProcessor, 'overlay_image')
def test_process_video_overlay_only(mock_overlay_image, mock_crop_video, media_processor):
    """Test video processing with only overlay."""
    # Execute
    media_processor.process_video(
        TEST_VIDEO_PATH,
        TEST_OUTPUT_PATH,
        crop_params=None,
        overlay_path=TEST_OVERLAY_PATH
    )
    
    # Verify
    mock_crop_video.assert_not_called()
    mock_overlay_image.assert_called_once_with(
        TEST_VIDEO_PATH, 
        TEST_OVERLAY_PATH, 
        TEST_OUTPUT_PATH
    )

@patch.object(MediaProcessor, 'crop_video')
@patch.object(MediaProcessor, 'overlay_image')
def test_process_video_no_operations(mock_overlay_image, mock_crop_video, media_processor):
    """Test video processing with no operations (just copying)."""
    # Setup
    with patch('shutil.copy') as mock_copy:
        # Execute
        media_processor.process_video(
            TEST_VIDEO_PATH,
            TEST_OUTPUT_PATH,
            crop_params=None,
            overlay_path=None
        )
        
        # Verify
        mock_crop_video.assert_not_called()
        mock_overlay_image.assert_not_called()
        mock_copy.assert_called_once_with(TEST_VIDEO_PATH, TEST_OUTPUT_PATH) 