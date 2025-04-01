import os
import pytest
import glob
import shutil
from unittest.mock import MagicMock, patch, mock_open
from karaoke_prep.karaoke_prep import KaraokePrep

class TestFileOperations:
    def test_copy_input_media(self, basic_karaoke_prep, temp_dir):
        """Test copying input media to a new location."""
        # Setup
        source_file = os.path.join(temp_dir, "source.mp4")
        with open(source_file, "w") as f:
            f.write("test content")
        
        output_filename = os.path.join(temp_dir, "output")
        
        # Test with mocked shutil.copy2
        with patch('shutil.copy2') as mock_copy:
            result = basic_karaoke_prep.copy_input_media(source_file, output_filename)
            
            # Verify the correct file path was returned
            assert result == output_filename + ".mp4"
            
            # Verify shutil.copy2 was called with correct arguments
            mock_copy.assert_called_once_with(source_file, output_filename + ".mp4")
    
    def test_copy_input_media_same_file(self, basic_karaoke_prep, temp_dir):
        """Test copying input media when source and destination are the same."""
        # Setup
        file_path = os.path.join(temp_dir, "file.mp4")
        with open(file_path, "w") as f:
            f.write("test content")
        
        # Test with mocked os.path.abspath to simulate same file
        with patch('os.path.abspath', side_effect=lambda x: x):
            result = basic_karaoke_prep.copy_input_media(file_path, file_path[:-4])
            
            # Verify the correct file path was returned
            assert result == file_path
    
    def test_download_video(self, basic_karaoke_prep, temp_dir):
        """Test downloading a video from a URL."""
        url = "https://example.com/video"
        output_filename = os.path.join(temp_dir, "output")
        downloaded_file = output_filename + ".mp4"
        
        # Mock the yt_dlp.YoutubeDL context manager
        mock_ydl_instance = MagicMock()
        mock_ydl = MagicMock(return_value=mock_ydl_instance)
        
        # Mock glob.glob to return our "downloaded" file
        mock_glob_result = [downloaded_file]
        
        with patch('yt_dlp.YoutubeDL', mock_ydl), \
             patch('glob.glob', return_value=mock_glob_result):
            
            # Create the file that glob will "find"
            os.makedirs(os.path.dirname(downloaded_file), exist_ok=True)
            with open(downloaded_file, "w") as f:
                f.write("test video content")
            
            # Configure mock_ydl_instance.download to do nothing
            mock_ydl_instance.download.return_value = None
            
            result = basic_karaoke_prep.download_video(url, output_filename)
            
            # Verify the correct file path was returned
            assert result == downloaded_file
            
            # Verify yt_dlp was called with correct arguments
            mock_ydl_instance.download.assert_called_once_with([url])
    
    def test_download_video_no_files_found(self, basic_karaoke_prep):
        """Test downloading a video when no files are found after download."""
        url = "https://example.com/video"
        output_filename = "output"
        
        # Mock the yt_dlp.YoutubeDL context manager
        mock_ydl_instance = MagicMock()
        mock_ydl = MagicMock(return_value=mock_ydl_instance)
        
        # Mock glob.glob to return empty list (no files found)
        with patch('yt_dlp.YoutubeDL', mock_ydl), \
             patch('glob.glob', return_value=[]):
            
            # Configure mock_ydl_instance.download to do nothing
            mock_ydl_instance.download.return_value = None
            
            result = basic_karaoke_prep.download_video(url, output_filename)
            
            # Verify None was returned
            assert result is None
            
            # Verify yt_dlp was called with correct arguments
            mock_ydl_instance.download.assert_called_once_with([url])
    
    def test_extract_still_image_from_video(self, basic_karaoke_prep, mock_ffmpeg):
        """Test extracting a still image from a video."""
        input_filename = "input.mp4"
        output_filename = "output"
        
        result = basic_karaoke_prep.extract_still_image_from_video(input_filename, output_filename)
        
        # Verify the correct file path was returned
        assert result == output_filename + ".png"
        
        # Verify ffmpeg was called with correct arguments
        expected_command = f'{basic_karaoke_prep.ffmpeg_base_command} -i "{input_filename}" -ss 00:00:30 -vframes 1 "{output_filename}.png"'
        mock_ffmpeg.assert_called_once_with(expected_command)
    
    def test_convert_to_wav_success(self, basic_karaoke_prep, mock_ffmpeg, temp_dir):
        """Test converting input audio to WAV format successfully."""
        # Create a test input file
        input_filename = os.path.join(temp_dir, "input.mp3")
        with open(input_filename, "w") as f:
            f.write("test audio content")
        
        # Mock os.path.isfile and os.path.getsize
        with patch('os.path.isfile', return_value=True), \
             patch('os.path.getsize', return_value=100), \
             patch('os.popen') as mock_popen:
            
            # Mock the ffprobe output
            mock_popen.return_value.read.return_value = "codec_type=audio"
            
            output_filename = os.path.join(temp_dir, "output")
            
            # Configure mock_ffmpeg to do nothing
            mock_ffmpeg.return_value = 0
            
            result = basic_karaoke_prep.convert_to_wav(input_filename, output_filename)
            
            # Verify the correct file path was returned
            assert result == output_filename + ".wav"
    
    def test_convert_to_wav_file_not_found(self, basic_karaoke_prep):
        """Test converting input audio when the file is not found."""
        input_filename = "nonexistent.mp3"
        output_filename = "output"
        
        # Mock os.path.isfile to return False
        with patch('os.path.isfile', return_value=False):
            with pytest.raises(Exception, match=f"Input audio file not found: {input_filename}"):
                basic_karaoke_prep.convert_to_wav(input_filename, output_filename)
    
    def test_convert_to_wav_empty_file(self, basic_karaoke_prep):
        """Test converting input audio when the file is empty."""
        input_filename = "empty.mp3"
        output_filename = "output"
        
        # Mock os.path.isfile to return True and os.path.getsize to return 0
        with patch('os.path.isfile', return_value=True), \
             patch('os.path.getsize', return_value=0):
            with pytest.raises(Exception, match=f"Input audio file is empty: {input_filename}"):
                basic_karaoke_prep.convert_to_wav(input_filename, output_filename)
    
    def test_convert_to_wav_no_audio_stream(self, basic_karaoke_prep):
        """Test converting input audio when no audio stream is found."""
        input_filename = "no_audio.mp4"
        output_filename = "output"
        
        # Mock os.path.isfile, os.path.getsize, and os.popen
        with patch('os.path.isfile', return_value=True), \
             patch('os.path.getsize', return_value=100), \
             patch('os.popen') as mock_popen:
            
            # Mock the ffprobe output to indicate no audio stream
            mock_popen.return_value.read.return_value = "codec_type=video"
            
            with pytest.raises(Exception, match=f"No valid audio stream found in file: {input_filename}"):
                basic_karaoke_prep.convert_to_wav(input_filename, output_filename)
    
    def test_sanitize_filename(self, basic_karaoke_prep):
        """Test sanitizing filenames."""
        # Test with various problematic characters
        assert basic_karaoke_prep.sanitize_filename('file/with\\chars:*?"<>|') == 'file_with_chars_______'
        
        # Test with trailing spaces
        assert basic_karaoke_prep.sanitize_filename('file with spaces   ') == 'file with spaces'
    
    def test_setup_output_paths(self, basic_karaoke_prep, temp_dir):
        """Test setting up output paths."""
        # Test with both artist and title
        with patch('os.makedirs') as mock_makedirs:
            basic_karaoke_prep.output_dir = temp_dir
            track_output_dir, artist_title = basic_karaoke_prep.setup_output_paths("Test Artist", "Test Title")
            
            assert artist_title == "Test Artist - Test Title"
            assert track_output_dir == temp_dir
            
            # Test with create_track_subfolders=True
            basic_karaoke_prep.create_track_subfolders = True
            track_output_dir, artist_title = basic_karaoke_prep.setup_output_paths("Test Artist", "Test Title")
            
            expected_dir = os.path.join(temp_dir, "Test Artist - Test Title")
            assert track_output_dir == expected_dir
            mock_makedirs.assert_called_with(expected_dir)
    
    def test_setup_output_paths_title_only(self, basic_karaoke_prep, temp_dir):
        """Test setting up output paths with only title."""
        with patch('os.makedirs'):
            basic_karaoke_prep.output_dir = temp_dir
            track_output_dir, artist_title = basic_karaoke_prep.setup_output_paths(None, "Test Title")
            
            assert artist_title == "Test Title"
            assert track_output_dir == temp_dir
    
    def test_setup_output_paths_no_inputs(self, basic_karaoke_prep):
        """Test setting up output paths with no inputs."""
        with pytest.raises(ValueError, match="Error: At least title or artist must be provided"):
            basic_karaoke_prep.setup_output_paths(None, None)
