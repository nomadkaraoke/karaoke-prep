import os
import pytest
from unittest.mock import MagicMock, patch, call, DEFAULT
import shutil
from karaoke_prep.karaoke_prep import KaraokePrep
from karaoke_prep.utils import sanitize_filename

class TestLyrics:
    def test_find_best_split_point_with_comma(self, basic_karaoke_prep):
        """Test finding the best split point with a comma near the middle."""
        line = "This is a test line, with a comma near the middle of the sentence"
        split_point = basic_karaoke_prep.lyrics_processor.find_best_split_point(line)
        
        # The split should be after the comma
        assert line[:split_point].strip() == "This is a test line,"
        assert line[split_point:].strip() == "with a comma near the middle of the sentence"
    
    def test_find_best_split_point_with_and(self, basic_karaoke_prep):
        """Test finding the best split point with 'and' near the middle."""
        line = "This is a test line and this is the second part of the sentence"
        split_point = basic_karaoke_prep.lyrics_processor.find_best_split_point(line)
        
        # The split should be after 'and'
        assert line[:split_point].strip() == "This is a test line and"
        assert line[split_point:].strip() == "this is the second part of the sentence"
    
    def test_find_best_split_point_at_middle_word(self, basic_karaoke_prep):
        """Test finding the best split point at the middle word."""
        line = "This is a test line without any good split points"
        split_point = basic_karaoke_prep.lyrics_processor.find_best_split_point(line)

        # The split should be at the middle word
        assert line[:split_point].strip() == "This is a test line"
        assert line[split_point:].strip() == "without any good split points"
    
    def test_find_best_split_point_forced_split(self, basic_karaoke_prep):
        """Test finding the best split point with forced split at max length."""
        # Create a very long line without good split points
        line = "Thisisaverylonglinewithoutanyspacesorpunctuationthatexceedsthemaximumlengthallowedforasingleline"
        split_point = basic_karaoke_prep.lyrics_processor.find_best_split_point(line)
        
        # The split should be at the maximum length (36)
        assert split_point == 36
        assert len(line[:split_point]) == 36
    
    def test_process_line_short(self, basic_karaoke_prep):
        """Test processing a line that's already short enough."""
        line = "This is a short line"
        processed = basic_karaoke_prep.lyrics_processor.process_line(line)
        
        assert processed == [line]
    
    def test_process_line_with_parentheses(self, basic_karaoke_prep):
        """Test processing a line with parentheses."""
        line = "This is a line with (some parenthetical text) that should be split"
        processed = basic_karaoke_prep.lyrics_processor.process_line(line)
        
        assert processed[0] == "This is a line with"
        assert processed[1] == "(some parenthetical text)"
        assert processed[2] == "that should be split"
    
    def test_process_line_with_parentheses_and_comma(self, basic_karaoke_prep):
        """Test processing a line with parentheses followed by a comma."""
        line = "This is a line with (some parenthetical text), that should be split"
        processed = basic_karaoke_prep.lyrics_processor.process_line(line)
        
        assert processed[0] == "This is a line with"
        assert processed[1] == "(some parenthetical text),"
        assert processed[2] == "that should be split"
    
    def test_process_line_long(self, basic_karaoke_prep):
        """Test processing a long line that needs multiple splits."""
        line = "This is a very long line that needs to be split into multiple lines because it exceeds the maximum length allowed for a single line"
        processed = basic_karaoke_prep.lyrics_processor.process_line(line)
        
        # Should be split into multiple lines
        assert len(processed) > 1
        # Each line should be 36 characters or less
        for p in processed:
            assert len(p) <= 36
    
    def test_transcribe_lyrics_existing_files_parent_dir(self, basic_karaoke_prep, temp_dir):
        """Test transcribing lyrics when files already exist in parent directory."""
        # Setup
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        # Create mock existing files
        artist = "Test Artist"
        title = "Test Title"
        sanitized_artist = sanitize_filename(artist)
        sanitized_title = sanitize_filename(title)
        
        parent_video_path = os.path.join(track_output_dir, f"{sanitized_artist} - {sanitized_title} (With Vocals).mkv")
        parent_lrc_path = os.path.join(track_output_dir, f"{sanitized_artist} - {sanitized_title} (Karaoke).lrc")
        
        # Create the files
        with open(parent_video_path, "w") as f:
            f.write("mock video content")
        with open(parent_lrc_path, "w") as f:
            f.write("mock lrc content")
        
        # Test with mocked os.path.exists
        with patch('os.path.exists', return_value=True):
            # Call the method on the lyrics_processor
            result = basic_karaoke_prep.lyrics_processor.transcribe_lyrics(None, artist, title, track_output_dir)
            
            # Verify
            assert result["lrc_filepath"] == parent_lrc_path
            assert result["ass_filepath"] == parent_video_path
    
    def test_transcribe_lyrics_existing_files_lyrics_dir(self, basic_karaoke_prep, temp_dir):
        """Test transcribing lyrics when files already exist in lyrics directory."""
        # Setup
        track_output_dir = os.path.join(temp_dir, "track")
        lyrics_dir = os.path.join(track_output_dir, "lyrics")
        os.makedirs(lyrics_dir, exist_ok=True)
        
        # Create mock existing files
        artist = "Test Artist"
        title = "Test Title"
        sanitized_artist = sanitize_filename(artist)
        sanitized_title = sanitize_filename(title)
        
        lyrics_video_path = os.path.join(lyrics_dir, f"{sanitized_artist} - {sanitized_title} (With Vocals).mkv")
        lyrics_lrc_path = os.path.join(lyrics_dir, f"{sanitized_artist} - {sanitized_title} (Karaoke).lrc")
        
        parent_video_path = os.path.join(track_output_dir, f"{sanitized_artist} - {sanitized_title} (With Vocals).mkv")
        parent_lrc_path = os.path.join(track_output_dir, f"{sanitized_artist} - {sanitized_title} (Karaoke).lrc")
        
        # Create the files
        with open(lyrics_video_path, "w") as f:
            f.write("mock video content")
        with open(lyrics_lrc_path, "w") as f:
            f.write("mock lrc content")
        
        # Test with mocked os.path.exists and shutil.copy2
        with patch('os.path.exists', side_effect=lambda path: path in [lyrics_video_path, lyrics_lrc_path]), \
             patch('shutil.copy2') as mock_copy2:
             # Call the method on the lyrics_processor
            result = basic_karaoke_prep.lyrics_processor.transcribe_lyrics(None, artist, title, track_output_dir)
            
            # Verify copy2 was called with correct arguments
            mock_copy2.assert_any_call(lyrics_video_path, parent_video_path)
            mock_copy2.assert_any_call(lyrics_lrc_path, parent_lrc_path)
            
            # Verify the correct file paths were returned
            assert result["lrc_filepath"] == parent_lrc_path
            assert result["ass_filepath"] == parent_video_path
    
    def test_transcribe_lyrics_new_transcription(self, basic_karaoke_prep, temp_dir):
        """Test transcribing lyrics with a new transcription."""
        # Setup
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        artist = "Test Artist"
        title = "Test Title"
        input_audio_wav = os.path.join(temp_dir, "input.wav")
        
        # Create mock input file
        with open(input_audio_wav, "w") as f:
            f.write("mock audio content")
        
        # Mock LyricsTranscriber
        mock_transcriber = MagicMock()
        mock_transcriber_instance = MagicMock()
        mock_transcriber.return_value = mock_transcriber_instance
        
        # Mock transcription results
        mock_results = MagicMock()
        mock_results.lrc_filepath = os.path.join(track_output_dir, "lyrics", "test.lrc")
        mock_results.ass_filepath = os.path.join(track_output_dir, "lyrics", "test.ass")
        mock_results.video_filepath = os.path.join(track_output_dir, "lyrics", "test.mkv")
        mock_results.corrected_txt = os.path.join(track_output_dir, "lyrics", "test.txt")
        mock_results.transcription_corrected = MagicMock()
        mock_results.transcription_corrected.corrected_segments = [
            MagicMock(text="Line 1"),
            MagicMock(text="Line 2")
        ]
        
        mock_transcriber_instance.process.return_value = mock_results
        
        # Mock environment variables
        mock_env = {
            "AUDIOSHAKE_API_TOKEN": "test_token",
            "GENIUS_API_TOKEN": "test_token",
            "SPOTIFY_COOKIE_SP_DC": "test_cookie",
            "RUNPOD_API_KEY": "test_key",
            "WHISPER_RUNPOD_ID": "test_id"
        }
        
        # Test with mocked dependencies
        with patch('karaoke_prep.lyrics_processor.LyricsTranscriber', mock_transcriber), \
             patch('os.makedirs'), \
             patch('os.path.exists', return_value=False), \
             patch('shutil.copy2') as mock_copy2, \
             patch('os.getenv', side_effect=lambda key: mock_env.get(key)), \
             patch('karaoke_prep.lyrics_processor.load_dotenv'):
            
            # Call the method on the lyrics_processor
            result = basic_karaoke_prep.lyrics_processor.transcribe_lyrics(input_audio_wav, artist, title, track_output_dir)
            
            # Verify LyricsTranscriber was initialized with correct arguments
            mock_transcriber.assert_called_once()
            call_args = mock_transcriber.call_args[1]
            assert call_args["audio_filepath"] == input_audio_wav
            assert call_args["artist"] == artist
            assert call_args["title"] == title
            
            # Verify process was called
            mock_transcriber_instance.process.assert_called_once()
            
            # Verify the correct file paths were returned
            assert result["lrc_filepath"] == mock_results.lrc_filepath
            assert result["ass_filepath"] == mock_results.ass_filepath
            assert result["corrected_lyrics_text"] == "Line 1\nLine 2"
            assert result["corrected_lyrics_text_filepath"] == mock_results.corrected_txt
    
    def test_backup_existing_outputs(self, basic_karaoke_prep, temp_dir):
        """Test backing up existing outputs."""
        # Setup
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        artist = "Test Artist"
        title = "Test Title"
        base_name = f"{artist} - {title}"
        
        # Create mock files to backup
        input_audio_wav = os.path.join(track_output_dir, f"{base_name}.wav")
        with_vocals_file = os.path.join(track_output_dir, f"{base_name} (With Vocals).mkv")
        karaoke_file = os.path.join(track_output_dir, f"{base_name} (Karaoke).lrc")
        final_karaoke_file = os.path.join(track_output_dir, f"{base_name} (Final Karaoke).mp4")
        
        # Create lyrics directory and files
        lyrics_dir = os.path.join(track_output_dir, "lyrics")
        os.makedirs(lyrics_dir, exist_ok=True)
        lyrics_file = os.path.join(lyrics_dir, "test.lrc")
        
        # Create the files
        for file_path in [input_audio_wav, with_vocals_file, karaoke_file, final_karaoke_file, lyrics_file]:
            with open(file_path, "w") as f:
                f.write(f"mock content for {os.path.basename(file_path)}")
        
        # Test with mocked shutil functions
        with patch('shutil.move') as mock_move, \
             patch('shutil.copytree') as mock_copytree, \
             patch('shutil.rmtree') as mock_rmtree:
            
            result = basic_karaoke_prep.file_handler.backup_existing_outputs(track_output_dir, artist, title)
            
            # Verify the correct input audio file was returned
            assert result == input_audio_wav
            
            # Verify version directory was created
            version_dir = os.path.join(track_output_dir, "version-1")
            
        # Verify files were moved to version directory
        if not basic_karaoke_prep.dry_run:
            mock_move.assert_any_call(with_vocals_file, os.path.join(version_dir, os.path.basename(with_vocals_file)))
            mock_move.assert_any_call(karaoke_file, os.path.join(version_dir, os.path.basename(karaoke_file)))
            mock_move.assert_any_call(final_karaoke_file, os.path.join(version_dir, os.path.basename(final_karaoke_file)))
            
            # Verify lyrics directory was copied and removed
            mock_copytree.assert_called_once_with(lyrics_dir, os.path.join(version_dir, "lyrics"))
            mock_rmtree.assert_called_once_with(lyrics_dir)
    
    def test_backup_existing_outputs_no_input_audio(self, basic_karaoke_prep, temp_dir):
        """Test backing up existing outputs when input audio file is not found."""
        # Setup
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        artist = "Test Artist"
        title = "Test Title"
        
        # Create an alternative WAV file
        alt_wav_file = os.path.join(track_output_dir, "alternative.wav")
        with open(alt_wav_file, "w") as f:
            f.write("mock audio content")
        
        # Test with mocked glob.glob
        with patch('glob.glob', return_value=[alt_wav_file]), \
             patch('shutil.move'), \
             patch('shutil.copytree'), \
             patch('shutil.rmtree'), \
             patch('os.path.exists', return_value=False):
            
            result = basic_karaoke_prep.file_handler.backup_existing_outputs(track_output_dir, artist, title)
            
            # Verify the alternative WAV file was returned
            assert result == alt_wav_file
    
    def test_backup_existing_outputs_no_wav_files(self, basic_karaoke_prep, temp_dir):
        """Test backing up existing outputs when no WAV files are found."""
        # Setup
        track_output_dir = os.path.join(temp_dir, "track")
        os.makedirs(track_output_dir, exist_ok=True)
        
        artist = "Test Artist"
        title = "Test Title"
        
        # Test with mocked glob.glob and os.path.exists
        with patch('glob.glob', return_value=[]), \
             patch('os.path.exists', return_value=False):
            
            with pytest.raises(Exception, match=f"No input audio file found in {track_output_dir}"):
                basic_karaoke_prep.file_handler.backup_existing_outputs(track_output_dir, artist, title)
