import pytest
from unittest.mock import MagicMock, patch, mock_open
import os
import json

# Update imports to use the refactored module
from karaoke_prep.karaoke_finalise.mediainfo_parser import MediaInfoParser

# Sample mediainfo JSON output for testing
SAMPLE_MEDIAINFO_JSON = {
    "media": {
        "track": [
            {
                "@type": "General",
                "Duration": "180.123"
            },
            {
                "@type": "Video",
                "Width": "1920",
                "Height": "1080",
                "FrameRate": "29.97",
                "Duration": "180.123"
            },
            {
                "@type": "Audio",
                "SamplingRate": "48000",
                "Channels": "2",
                "Duration": "180.123"
            }
        ]
    }
}

# Sample mediainfo XML output for testing
SAMPLE_MEDIAINFO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<MediaInfo>
    <File>
        <track type="General">
            <Duration>180.123</Duration>
        </track>
        <track type="Video">
            <Width>1920</Width>
            <Height>1080</Height>
            <FrameRate>29.97</FrameRate>
            <Duration>180.123</Duration>
        </track>
        <track type="Audio">
            <SamplingRate>48000</SamplingRate>
            <Channels>2</Channels>
            <Duration>180.123</Duration>
        </track>
    </File>
</MediaInfo>
"""

@pytest.fixture
def mock_logger():
    """Fixture for a mocked logger."""
    return MagicMock()

@pytest.fixture
def mediainfo_parser(mock_logger):
    """Fixture for MediaInfoParser instance."""
    return MediaInfoParser(logger=mock_logger)

@patch('subprocess.run')
def test_get_mediainfo_xml(mock_subprocess_run, mediainfo_parser):
    """Test getting mediainfo in XML format."""
    # Setup
    process_mock = MagicMock()
    process_mock.stdout = SAMPLE_MEDIAINFO_XML
    process_mock.returncode = 0
    mock_subprocess_run.return_value = process_mock
    
    # Execute
    result = mediainfo_parser.get_mediainfo_xml("test_file.mp4")
    
    # Verify
    mock_subprocess_run.assert_called_once()
    assert result == SAMPLE_MEDIAINFO_XML
    assert mock_subprocess_run.call_args[0][0][0] == "mediainfo"
    assert "--Output=XML" in mock_subprocess_run.call_args[0][0]
    assert "test_file.mp4" in mock_subprocess_run.call_args[0][0]

@patch('subprocess.run')
def test_get_mediainfo_json(mock_subprocess_run, mediainfo_parser):
    """Test getting mediainfo in JSON format."""
    # Setup
    process_mock = MagicMock()
    process_mock.stdout = json.dumps(SAMPLE_MEDIAINFO_JSON)
    process_mock.returncode = 0
    mock_subprocess_run.return_value = process_mock
    
    # Execute
    result = mediainfo_parser.get_mediainfo_json("test_file.mp4")
    
    # Verify
    mock_subprocess_run.assert_called_once()
    assert result == SAMPLE_MEDIAINFO_JSON
    assert mock_subprocess_run.call_args[0][0][0] == "mediainfo"
    assert "--Output=JSON" in mock_subprocess_run.call_args[0][0]
    assert "test_file.mp4" in mock_subprocess_run.call_args[0][0]

@patch('subprocess.run')
def test_get_mediainfo_error(mock_subprocess_run, mediainfo_parser):
    """Test error handling when mediainfo command fails."""
    # Setup
    process_mock = MagicMock()
    process_mock.returncode = 1
    process_mock.stderr = "Error: file not found"
    mock_subprocess_run.return_value = process_mock
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        mediainfo_parser.get_mediainfo_json("nonexistent_file.mp4")
    
    assert "failed with return code 1" in str(excinfo.value)

def test_get_video_duration_json(mediainfo_parser):
    """Test extracting video duration from mediainfo JSON output."""
    # Setup
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=SAMPLE_MEDIAINFO_JSON)
    
    # Execute
    duration = mediainfo_parser.get_video_duration("test_file.mp4")
    
    # Verify
    assert duration == 180.123
    mediainfo_parser.get_mediainfo_json.assert_called_once_with("test_file.mp4")

def test_get_video_resolution_json(mediainfo_parser):
    """Test extracting video resolution from mediainfo JSON output."""
    # Setup
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=SAMPLE_MEDIAINFO_JSON)
    
    # Execute
    width, height = mediainfo_parser.get_video_resolution("test_file.mp4")
    
    # Verify
    assert width == 1920
    assert height == 1080
    mediainfo_parser.get_mediainfo_json.assert_called_once_with("test_file.mp4")

def test_get_video_framerate_json(mediainfo_parser):
    """Test extracting video framerate from mediainfo JSON output."""
    # Setup
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=SAMPLE_MEDIAINFO_JSON)
    
    # Execute
    framerate = mediainfo_parser.get_video_framerate("test_file.mp4")
    
    # Verify
    assert framerate == 29.97
    mediainfo_parser.get_mediainfo_json.assert_called_once_with("test_file.mp4")

def test_get_audio_properties_json(mediainfo_parser):
    """Test extracting audio properties from mediainfo JSON output."""
    # Setup
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=SAMPLE_MEDIAINFO_JSON)
    
    # Execute
    sample_rate, channels = mediainfo_parser.get_audio_properties("test_file.mp4")
    
    # Verify
    assert sample_rate == 48000
    assert channels == 2
    mediainfo_parser.get_mediainfo_json.assert_called_once_with("test_file.mp4")

def test_get_video_duration_fallback_to_xml(mediainfo_parser):
    """Test fallback to XML format when JSON parsing fails."""
    # Setup
    mediainfo_parser.get_mediainfo_json = MagicMock(side_effect=Exception("JSON parsing failed"))
    mediainfo_parser.get_mediainfo_xml = MagicMock(return_value=SAMPLE_MEDIAINFO_XML)
    
    # Execute
    with patch('xml.etree.ElementTree.fromstring'):
        # We're not testing the XML parsing here, just the fallback mechanism
        mediainfo_parser.get_video_duration("test_file.mp4")
    
    # Verify
    mediainfo_parser.get_mediainfo_json.assert_called_once_with("test_file.mp4")
    mediainfo_parser.get_mediainfo_xml.assert_called_once_with("test_file.mp4")

def test_mediainfo_not_found(mediainfo_parser):
    """Test handling of missing mediainfo executable."""
    # Setup
    error_msg = "[Errno 2] No such file or directory: 'mediainfo'"
    mediainfo_parser.get_mediainfo_json = MagicMock(side_effect=FileNotFoundError(error_msg))
    
    # Execute and verify
    with pytest.raises(RuntimeError) as excinfo:
        mediainfo_parser.get_video_duration("test_file.mp4")
    
    assert "MediaInfo not found" in str(excinfo.value)

def test_get_duration_handles_missing_video_track(mediainfo_parser):
    """Test duration calculation when video track is missing."""
    # Setup - create JSON without video track
    mediainfo_json = {
        "media": {
            "track": [
                {
                    "@type": "General",
                    "Duration": "180.123"
                },
                {
                    "@type": "Audio",
                    "Duration": "180.123"
                }
            ]
        }
    }
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=mediainfo_json)
    
    # Execute
    duration = mediainfo_parser.get_video_duration("test_file.mp4")
    
    # Verify - should fall back to General track duration
    assert duration == 180.123

def test_get_duration_handles_missing_duration(mediainfo_parser):
    """Test duration calculation when Duration attribute is missing."""
    # Setup - create JSON without Duration attribute
    mediainfo_json = {
        "media": {
            "track": [
                {
                    "@type": "General"
                },
                {
                    "@type": "Video",
                    "Width": "1920",
                    "Height": "1080"
                }
            ]
        }
    }
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=mediainfo_json)
    
    # Execute and verify
    with pytest.raises(ValueError) as excinfo:
        mediainfo_parser.get_video_duration("test_file.mp4")
    
    assert "Could not find Duration" in str(excinfo.value)

def test_get_resolution_handles_missing_video_track(mediainfo_parser):
    """Test resolution extraction when video track is missing."""
    # Setup - create JSON without video track
    mediainfo_json = {
        "media": {
            "track": [
                {
                    "@type": "General"
                },
                {
                    "@type": "Audio"
                }
            ]
        }
    }
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=mediainfo_json)
    
    # Execute and verify
    with pytest.raises(ValueError) as excinfo:
        mediainfo_parser.get_video_resolution("test_file.mp4")
    
    assert "Could not find Video track" in str(excinfo.value)

def test_get_framerate_handles_missing_video_track(mediainfo_parser):
    """Test framerate extraction when video track is missing."""
    # Setup - create JSON without video track
    mediainfo_json = {
        "media": {
            "track": [
                {
                    "@type": "General"
                },
                {
                    "@type": "Audio"
                }
            ]
        }
    }
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=mediainfo_json)
    
    # Execute and verify
    with pytest.raises(ValueError) as excinfo:
        mediainfo_parser.get_video_framerate("test_file.mp4")
    
    assert "Could not find Video track" in str(excinfo.value)

def test_get_audio_properties_handles_missing_audio_track(mediainfo_parser):
    """Test audio properties extraction when audio track is missing."""
    # Setup - create JSON without audio track
    mediainfo_json = {
        "media": {
            "track": [
                {
                    "@type": "General"
                },
                {
                    "@type": "Video"
                }
            ]
        }
    }
    mediainfo_parser.get_mediainfo_json = MagicMock(return_value=mediainfo_json)
    
    # Execute and verify
    with pytest.raises(ValueError) as excinfo:
        mediainfo_parser.get_audio_properties("test_file.mp4")
    
    assert "Could not find Audio track" in str(excinfo.value) 