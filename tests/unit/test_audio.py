import os
import pytest
import json
import tempfile
import fcntl
from unittest.mock import MagicMock, patch, mock_open
from karaoke_prep.karaoke_prep import KaraokePrep

class TestAudio:
    def test_separate_audio(self, basic_karaoke_prep, temp_dir):
        """Test separating audio into components."""
        # Setup
        audio_file = os.path.join(temp_dir, "input.wav")
        with open(audio_file, "w") as f:
            f.write("mock audio content")
        
        model_name = "test_model.ckpt"
        artist_title = "Test Artist - Test Title"
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        instrumental_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental {model_name}).flac")
        vocals_path = os.path.join(track_output_dir, f"{artist_title} (Vocals {model_name}).flac")
        
        # Mock Separator
        mock_separator = MagicMock()
        mock_separator_instance = MagicMock()
        mock_separator.return_value = mock_separator_instance
        
        # Mock output files
        mock_output_files = [
            f"{artist_title} (Vocals)_test_model.flac",
            f"{artist_title} (Instrumental)_test_model.flac"
        ]
        mock_separator_instance.separate.return_value = mock_output_files
        
        # Test with mocked dependencies
        with patch('audio_separator.separator.Separator', mock_separator), \
             patch('os.rename') as mock_rename:
            
            basic_karaoke_prep.separate_audio(audio_file, model_name, artist_title, track_output_dir, instrumental_path, vocals_path)
            
            # Verify Separator was initialized with correct arguments
            mock_separator.assert_called_once_with(
                log_level=basic_karaoke_prep.log_level,
                log_formatter=basic_karaoke_prep.log_formatter,
                model_file_dir=basic_karaoke_prep.model_file_dir,
                output_format=basic_karaoke_prep.lossless_output_format
            )
            
            # Verify load_model was called with correct arguments
            mock_separator_instance.load_model.assert_called_once_with(model_filename=model_name)
            
            # Verify separate was called with correct arguments
            mock_separator_instance.separate.assert_called_once_with(audio_file)
            
            # Verify files were renamed correctly
            mock_rename.assert_any_call(mock_output_files[0], vocals_path)
            mock_rename.assert_any_call(mock_output_files[1], instrumental_path)
    
    def test_separate_audio_invalid_file(self, basic_karaoke_prep):
        """Test separating audio with an invalid file."""
        with pytest.raises(Exception, match="Error: Invalid audio source provided."):
            basic_karaoke_prep.separate_audio(None, "model.ckpt", "Artist - Title", "output_dir", "instrumental.flac", "vocals.flac")
    
    def test_process_audio_separation(self, basic_karaoke_prep, temp_dir):
        """Test the process_audio_separation method."""
        # Setup
        audio_file = os.path.join(temp_dir, "input.wav")
        with open(audio_file, "w") as f:
            f.write("mock audio content")
        
        artist_title = "Test Artist - Test Title"
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        # Create stems directory
        stems_dir = os.path.join(track_output_dir, "stems")
        
        # Mock Separator
        mock_separator = MagicMock()
        mock_separator_instance = MagicMock()
        mock_separator.return_value = mock_separator_instance
        
        # Mock clean instrumental output files
        clean_model = basic_karaoke_prep.clean_instrumental_model
        clean_instrumental_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental {clean_model}).flac")
        clean_vocals_path = os.path.join(stems_dir, f"{artist_title} (Vocals {clean_model}).flac")
        
        mock_clean_output_files = [
            f"{artist_title} (Vocals)_{clean_model}.flac",
            f"{artist_title} (Instrumental)_{clean_model}.flac"
        ]
        
        # Mock other stems output files
        other_model = basic_karaoke_prep.other_stems_models[0]
        other_stem_path = os.path.join(stems_dir, f"{artist_title} (Piano {other_model}).flac")
        
        mock_other_output_files = [
            f"{artist_title}_(Piano)_{other_model}.flac"
        ]
        
        # Mock backing vocals output files
        backing_model = basic_karaoke_prep.backing_vocals_models[0]
        lead_vocals_path = os.path.join(stems_dir, f"{artist_title} (Lead Vocals {backing_model}).flac")
        backing_vocals_path = os.path.join(stems_dir, f"{artist_title} (Backing Vocals {backing_model}).flac")
        
        mock_backing_output_files = [
            f"{artist_title} (Vocals)_{backing_model}.flac",
            f"{artist_title} (Instrumental)_{backing_model}.flac"
        ]
        
        # Mock combined instrumental path
        combined_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental +BV {backing_model}).flac")
        
        # Configure mock separator to return different outputs for different models
        def mock_separate(input_file):
            if mock_separator_instance.load_model.call_args[1]["model_filename"] == clean_model:
                return mock_clean_output_files
            elif mock_separator_instance.load_model.call_args[1]["model_filename"] == other_model:
                return mock_other_output_files
            elif mock_separator_instance.load_model.call_args[1]["model_filename"] == backing_model:
                return mock_backing_output_files
            return []
        
        mock_separator_instance.separate.side_effect = mock_separate
        
        # Test with mocked dependencies
        with patch('audio_separator.separator.Separator', mock_separator), \
             patch('os.makedirs') as mock_makedirs, \
             patch('os.rename') as mock_rename, \
             patch('os.system') as mock_system, \
             patch('os.path.exists', return_value=False), \
             patch('fcntl.flock') as mock_flock, \
             patch('builtins.open', mock_open()) as mock_file, \
             patch('json.dump') as mock_json_dump:
            
            result = basic_karaoke_prep.process_audio_separation(audio_file, artist_title, track_output_dir)
            
            # Verify stems directory was created
            mock_makedirs.assert_any_call(stems_dir, exist_ok=True)
            
            # Verify Separator was initialized
            mock_separator.assert_called_once()
            
            # Verify load_model was called for each model
            assert mock_separator_instance.load_model.call_count >= 3
            
            # Verify separate was called for each model
            assert mock_separator_instance.separate.call_count >= 3
            
            # Verify files were renamed
            mock_rename.assert_any_call(mock_clean_output_files[0], clean_vocals_path)
            mock_rename.assert_any_call(mock_clean_output_files[1], clean_instrumental_path)
            
            # Verify ffmpeg was called to combine instrumental and backing vocals
            assert mock_system.call_count >= 1
            
            # Verify the result structure
            assert "clean_instrumental" in result
            assert "other_stems" in result
            assert "backing_vocals" in result
            assert "combined_instrumentals" in result
    
    def test_process_audio_separation_with_lock(self, basic_karaoke_prep, temp_dir):
        """Test process_audio_separation with lock handling."""
        # Setup
        audio_file = os.path.join(temp_dir, "input.wav")
        with open(audio_file, "w") as f:
            f.write("mock audio content")
        
        artist_title = "Test Artist - Test Title"
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        # Mock lock file
        lock_file_path = os.path.join(tempfile.gettempdir(), "audio_separator.lock")
        
        # Mock lock data
        lock_data = {
            "pid": 12345,
            "start_time": "2023-01-01T00:00:00",
            "track": "Another Track"
        }
        
        # Test with mocked dependencies
        with patch('tempfile.gettempdir', return_value=temp_dir), \
             patch('os.path.exists', return_value=True), \
             patch('builtins.open', mock_open(read_data=json.dumps(lock_data))) as mock_file, \
             patch('fcntl.flock') as mock_flock, \
             patch('json.load', return_value=lock_data), \
             patch('json.dump') as mock_json_dump, \
             patch('psutil.pid_exists', return_value=False), \
             patch('os.remove') as mock_remove, \
             patch('audio_separator.separator.Separator') as mock_separator, \
             patch('os.makedirs'), \
             patch('os.rename'), \
             patch('os.system'):
            
            # Configure mock separator
            mock_separator_instance = MagicMock()
            mock_separator.return_value = mock_separator_instance
            mock_separator_instance.separate.return_value = []
            
            result = basic_karaoke_prep.process_audio_separation(audio_file, artist_title, track_output_dir)
            
            # Verify stale lock was removed
            mock_remove.assert_called_once_with(os.path.join(temp_dir, "audio_separator.lock"))
            
            # Verify lock was acquired and released
            assert mock_flock.call_count >= 2
    
    def test_normalize_audio(self, basic_karaoke_prep):
        """Test normalizing audio."""
        # Mock AudioSegment
        mock_audio = MagicMock()
        mock_audio.max_dBFS = -6.0
        mock_audio.apply_gain.return_value = mock_audio
        mock_audio.rms = 100  # Non-zero RMS to avoid silent audio check
        
        # Mock AudioSegment.from_file
        mock_from_file = MagicMock(return_value=mock_audio)
        
        # Test with mocked dependencies
        with patch('karaoke_prep.karaoke_prep.AudioSegment.from_file', mock_from_file):
            basic_karaoke_prep._normalize_audio("input.flac", "output.flac")
            
            # Verify AudioSegment.from_file was called with correct arguments
            mock_from_file.assert_called_once_with("input.flac", format="flac")
            
            # Verify apply_gain was called with correct gain value (0 - (-6) = 6)
            mock_audio.apply_gain.assert_called_once_with(6.0)
            
            # Verify export was called
            mock_audio.export.assert_called_once_with("output.flac", format="flac")
    
    def test_normalize_audio_silent_result(self, basic_karaoke_prep):
        """Test normalizing audio when the result would be silent."""
        # Mock AudioSegment
        mock_audio = MagicMock()
        mock_audio.max_dBFS = -6.0
        
        # Create a silent normalized audio
        mock_normalized_audio = MagicMock()
        mock_normalized_audio.rms = 0  # Zero RMS indicates silent audio
        
        mock_audio.apply_gain.return_value = mock_normalized_audio
        
        # Mock AudioSegment.from_file
        mock_from_file = MagicMock(return_value=mock_audio)
        
        # Test with mocked dependencies
        with patch('karaoke_prep.karaoke_prep.AudioSegment.from_file', mock_from_file):
            basic_karaoke_prep._normalize_audio("input.flac", "output.flac")
            
            # Verify export was called with the original audio instead
            mock_audio.export.assert_called_once_with("output.flac", format="flac")
    
    def test_normalize_audio_files(self, basic_karaoke_prep):
        """Test normalizing multiple audio files."""
        # Setup
        separation_result = {
            "clean_instrumental": {
                "instrumental": "instrumental.flac"
            },
            "combined_instrumentals": {
                "model1": "combined1.flac",
                "model2": "combined2.flac"
            }
        }
        
        # Test with mocked dependencies
        with patch.object(basic_karaoke_prep, '_normalize_audio') as mock_normalize, \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1000):
            
            basic_karaoke_prep._normalize_audio_files(separation_result, "Artist - Title", "output_dir")
            
            # Verify _normalize_audio was called for each file
            assert mock_normalize.call_count == 3
            mock_normalize.assert_any_call("instrumental.flac", "instrumental.flac")
            mock_normalize.assert_any_call("combined1.flac", "combined1.flac")
            mock_normalize.assert_any_call("combined2.flac", "combined2.flac")
    
    def test_normalize_audio_files_missing_file(self, basic_karaoke_prep):
        """Test normalizing audio files when a file is missing."""
        # Setup
        separation_result = {
            "clean_instrumental": {
                "instrumental": "instrumental.flac"
            },
            "combined_instrumentals": {
                "model1": "combined1.flac",
                "model2": "combined2.flac"
            }
        }
        
        # Test with mocked dependencies
        with patch.object(basic_karaoke_prep, '_normalize_audio') as mock_normalize, \
             patch('os.path.exists', side_effect=lambda path: path != "combined1.flac"), \
             patch('os.path.getsize', return_value=1000):
            
            basic_karaoke_prep._normalize_audio_files(separation_result, "Artist - Title", "output_dir")
            
            # Verify _normalize_audio was called only for existing files
            assert mock_normalize.call_count == 2
            mock_normalize.assert_any_call("instrumental.flac", "instrumental.flac")
            mock_normalize.assert_any_call("combined2.flac", "combined2.flac")
    
    def test_normalize_audio_files_normalization_error(self, basic_karaoke_prep):
        """Test normalizing audio files when normalization fails."""
        # Setup
        separation_result = {
            "clean_instrumental": {
                "instrumental": "instrumental.flac"
            },
            "combined_instrumentals": {
                "model1": "combined1.flac"
            }
        }
        
        # Test with mocked dependencies
        with patch.object(basic_karaoke_prep, '_normalize_audio', side_effect=Exception("Normalization error")), \
             patch('os.path.exists', return_value=True), \
             patch('os.path.getsize', return_value=1000):
            
            # Should not raise an exception
            basic_karaoke_prep._normalize_audio_files(separation_result, "Artist - Title", "output_dir")
    
    def test_file_exists(self, basic_karaoke_prep):
        """Test the _file_exists helper method."""
        # Test with existing file
        with patch('os.path.isfile', return_value=True):
            assert basic_karaoke_prep._file_exists("existing.file") is True
        
        # Test with non-existing file
        with patch('os.path.isfile', return_value=False):
            assert basic_karaoke_prep._file_exists("nonexistent.file") is False
