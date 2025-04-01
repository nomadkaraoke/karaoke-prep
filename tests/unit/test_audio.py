import os
import pytest
import glob
import json
import tempfile
from unittest.mock import MagicMock, patch, call
from datetime import datetime
import fcntl
from pydub import AudioSegment
from karaoke_prep.karaoke_prep import KaraokePrep

class TestAudio:
    def test_separate_audio(self, basic_karaoke_prep, temp_dir):
        """Test separating audio into instrumental and vocals."""
        # Setup
        audio_file = os.path.join(temp_dir, "input.wav")
        with open(audio_file, "w") as f:
            f.write("mock audio content")
        
        model_name = "test_model.ckpt"
        artist_title = "Test Artist - Test Title"
        track_output_dir = temp_dir
        instrumental_path = os.path.join(temp_dir, f"{artist_title} (Instrumental {model_name}).flac")
        vocals_path = os.path.join(temp_dir, f"{artist_title} (Vocals {model_name}).flac")
        
        # Mock Separator
        mock_separator = MagicMock()
        mock_separator.load_model.return_value = None
        mock_separator.separate.return_value = [
            f"{artist_title} (Vocals)_test_model.flac",
            f"{artist_title} (Instrumental)_test_model.flac",
            f"{artist_title}_(Piano)_test_model.flac"
        ]
        
        # Mock dependencies
        with patch('audio_separator.separator.Separator', return_value=mock_separator), \
             patch('os.rename') as mock_rename:
            
            # Call the method
            basic_karaoke_prep.separate_audio(
                audio_file=audio_file,
                model_name=model_name,
                artist_title=artist_title,
                track_output_dir=track_output_dir,
                instrumental_path=instrumental_path,
                vocals_path=vocals_path
            )
            
            # Verify Separator.load_model was called with correct arguments
            mock_separator.load_model.assert_called_once_with(model_filename=model_name)
            
            # Verify Separator.separate was called with correct arguments
            mock_separator.separate.assert_called_once_with(audio_file)
            
            # Verify os.rename was called for each output file
            assert mock_rename.call_count == 3
            mock_rename.assert_any_call(
                f"{artist_title} (Vocals)_test_model.flac",
                vocals_path
            )
            mock_rename.assert_any_call(
                f"{artist_title} (Instrumental)_test_model.flac",
                instrumental_path
            )
    
    def test_separate_audio_invalid_audio_file(self, basic_karaoke_prep):
        """Test separating audio with an invalid audio file."""
        with pytest.raises(Exception, match="Error: Invalid audio source provided."):
            basic_karaoke_prep.separate_audio(
                audio_file=None,
                model_name="test_model.ckpt",
                artist_title="Test Artist - Test Title",
                track_output_dir="output_dir",
                instrumental_path="instrumental.flac",
                vocals_path="vocals.flac"
            )
    
    def test_process_audio_separation(self, basic_karaoke_prep, temp_dir):
        """Test the process_audio_separation method."""
        # Setup
        audio_file = os.path.join(temp_dir, "input.wav")
        with open(audio_file, "w") as f:
            f.write("mock audio content")
        
        artist_title = "Test Artist - Test Title"
        track_output_dir = temp_dir
        
        # Create stems directory
        stems_dir = os.path.join(track_output_dir, "stems")
        os.makedirs(stems_dir, exist_ok=True)
        
        # Mock Separator
        mock_separator = MagicMock()
        mock_separator.load_model.return_value = None
        
        # Mock output files for different models
        clean_model = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
        backing_model = "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
        other_model = "htdemucs_6s.yaml"
        
        # Clean instrumental separation output
        mock_separator.separate.side_effect = [
            # Clean instrumental model outputs
            [
                os.path.join(temp_dir, f"{artist_title} (Vocals)_{clean_model}.flac"),
                os.path.join(temp_dir, f"{artist_title} (Instrumental)_{clean_model}.flac")
            ],
            # Other stems model outputs
            [
                os.path.join(temp_dir, f"{artist_title}_(Piano)_{other_model}.flac"),
                os.path.join(temp_dir, f"{artist_title}_(Guitar)_{other_model}.flac")
            ],
            # Backing vocals model outputs
            [
                os.path.join(temp_dir, f"{artist_title} (Vocals)_{backing_model}.flac"),
                os.path.join(temp_dir, f"{artist_title} (Instrumental)_{backing_model}.flac")
            ]
        ]
        
        # Mock dependencies
        with patch('audio_separator.separator.Separator', return_value=mock_separator), \
             patch('os.rename'), \
             patch('os.path.exists', return_value=True), \
             patch('os.getpid', return_value=12345), \
             patch('datetime.now', return_value=datetime.fromisoformat("2023-01-01T12:00:00")), \
             patch('json.dump'), \
             patch('fcntl.flock'), \
             patch('os.remove'), \
             patch('os.system'), \
             patch('open', create=True) as mock_open, \
             patch.object(basic_karaoke_prep, '_normalize_audio') as mock_normalize_audio, \
             patch.object(basic_karaoke_prep, '_file_exists', return_value=False):
            
            # Mock the lock file
            mock_file = MagicMock()
            mock_open.return_value = mock_file
            
            # Call the method
            result = basic_karaoke_prep.process_audio_separation(
                audio_file=audio_file,
                artist_title=artist_title,
                track_output_dir=track_output_dir
            )
            
            # Verify the result structure
            assert "clean_instrumental" in result
            assert "other_stems" in result
            assert "backing_vocals" in result
            assert "combined_instrumentals" in result
            
            # Verify Separator.load_model was called for each model
            assert mock_separator.load_model.call_count == 3
            
            # Verify Separator.separate was called for each separation
            assert mock_separator.separate.call_count == 3
            
            # Verify _normalize_audio was called
            assert mock_normalize_audio.call_count > 0
    
    def test_process_audio_separation_with_skip_env_var(self, basic_karaoke_prep, temp_dir):
        """Test process_audio_separation with KARAOKE_PREP_SKIP_AUDIO_SEPARATION environment variable."""
        # Setup
        audio_file = os.path.join(temp_dir, "input.wav")
        with open(audio_file, "w") as f:
            f.write("mock audio content")
        
        artist_title = "Test Artist - Test Title"
        track_output_dir = temp_dir
        
        # Mock environment variable
        with patch.dict('os.environ', {'KARAOKE_PREP_SKIP_AUDIO_SEPARATION': '1'}), \
             patch('fcntl.flock'), \
             patch('open', create=True) as mock_open:
            
            # Mock the lock file
            mock_file = MagicMock()
            mock_open.return_value = mock_file
            
            # Call the method
            result = basic_karaoke_prep.process_audio_separation(
                audio_file=audio_file,
                artist_title=artist_title,
                track_output_dir=track_output_dir
            )
            
            # Verify the result structure
            assert "clean_instrumental" in result
            assert "other_stems" in result
            assert "backing_vocals" in result
            assert "combined_instrumentals" in result
            
            # Verify all result sections are empty
            assert result["clean_instrumental"] == {}
            assert result["other_stems"] == {}
            assert result["backing_vocals"] == {}
            assert result["combined_instrumentals"] == {}
    
    def test_normalize_audio(self, basic_karaoke_prep, temp_dir):
        """Test normalizing audio."""
        # Setup
        input_path = os.path.join(temp_dir, "input.flac")
        output_path = os.path.join(temp_dir, "output.flac")
        
        # Create a mock AudioSegment
        mock_audio = MagicMock(spec=AudioSegment)
        mock_audio.max_dBFS = -6.0
        mock_audio.apply_gain.return_value = mock_audio
        mock_audio.rms = 100  # Non-zero RMS
        
        # Mock dependencies
        with patch('pydub.AudioSegment.from_file', return_value=mock_audio):
            # Call the method
            basic_karaoke_prep._normalize_audio(input_path, output_path)
            
            # Verify AudioSegment.from_file was called with correct arguments
            AudioSegment.from_file.assert_called_once_with(input_path, format="flac")
            
            # Verify apply_gain was called with correct arguments (target_level - current_level)
            mock_audio.apply_gain.assert_called_once_with(0.0 - (-6.0))
            
            # Verify export was called with correct arguments
            mock_audio.export.assert_called_once_with(output_path, format="flac")
    
    def test_normalize_audio_silent_result(self, basic_karaoke_prep, temp_dir):
        """Test normalizing audio when the result would be silent."""
        # Setup
        input_path = os.path.join(temp_dir, "input.flac")
        output_path = os.path.join(temp_dir, "output.flac")
        
        # Create a mock AudioSegment
        mock_audio = MagicMock(spec=AudioSegment)
        mock_audio.max_dBFS = -6.0
        
        # First mock has RMS of 0 (silent)
        mock_normalized = MagicMock(spec=AudioSegment)
        mock_normalized.rms = 0
        
        mock_audio.apply_gain.return_value = mock_normalized
        
        # Mock dependencies
        with patch('pydub.AudioSegment.from_file', return_value=mock_audio):
            # Call the method
            basic_karaoke_prep._normalize_audio(input_path, output_path)
            
            # Verify AudioSegment.from_file was called with correct arguments
            AudioSegment.from_file.assert_called_once_with(input_path, format="flac")
            
            # Verify apply_gain was called with correct arguments
            mock_audio.apply_gain.assert_called_once_with(0.0 - (-6.0))
            
            # Verify export was called with the original audio (not the silent one)
            mock_audio.export.assert_called_once_with(output_path, format="flac")
    
    def test_file_exists(self, basic_karaoke_prep):
        """Test the _file_exists helper method."""
        # Test with existing file
        with patch('os.path.isfile', return_value=True):
            assert basic_karaoke_prep._file_exists("existing_file.txt") is True
        
        # Test with non-existing file
        with patch('os.path.isfile', return_value=False):
            assert basic_karaoke_prep._file_exists("non_existing_file.txt") is False
