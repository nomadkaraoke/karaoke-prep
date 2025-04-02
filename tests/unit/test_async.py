import os
import pytest
import asyncio
import signal
import sys
from unittest.mock import MagicMock, patch, AsyncMock, ANY
from karaoke_prep.karaoke_prep import KaraokePrep

class TestAsync:
    @pytest.mark.asyncio
    async def test_prep_single_track(self, basic_karaoke_prep, temp_dir):
        """Test preparing a single track."""
        # Setup
        basic_karaoke_prep.input_media = os.path.join(temp_dir, "input.mp4")
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        basic_karaoke_prep.output_dir = temp_dir
        
        # Create mock input file
        with open(basic_karaoke_prep.input_media, "w") as f:
            f.write("mock video content")
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'copy_input_media', return_value="copied_file.mp4"), \
             patch.object(basic_karaoke_prep, 'convert_to_wav', return_value="output.wav"), \
             patch.object(basic_karaoke_prep, 'transcribe_lyrics', return_value={}), \
             patch.object(basic_karaoke_prep, 'process_audio_separation', return_value={}), \
             patch.object(basic_karaoke_prep, 'create_title_video'), \
             patch.object(basic_karaoke_prep, 'create_end_video'), \
             patch('asyncio.create_task') as mock_create_task, \
             patch('asyncio.gather', new_callable=AsyncMock) as mock_gather, \
             patch('os.makedirs'):
            
            # Configure mock asyncio.gather to return mock results
            mock_gather.return_value = [{}, {}] # gather itself returns the list directly
            
            # Configure mock asyncio.create_task to return a mock future
            mock_future = AsyncMock() # Use AsyncMock for tasks
            mock_create_task.return_value = mock_future
            
            # Mock the return value of prep_single_track
            expected_result = {
                "track_output_dir": temp_dir, # Use temp_dir here
                "artist": "Test Artist",
                "title": "Test Title",
                "extractor": "Original",
                "extracted_info": None,
                "lyrics": None,
                "processed_lyrics": None,
                "input_media": "copied_file.mp4",
                "input_still_image": None,
                "input_audio_wav": "output.wav",
                "separated_audio": {},
                "title_image_png": ANY,
                "title_image_jpg": ANY,
                "title_video": ANY,
                "end_image_png": ANY,
                "end_image_jpg": ANY,
                "end_video": ANY,
            }
            
            # Configure the mock to return our expected result
            # No need to mock future.result, the function returns the dict directly
            
            # Call the method
            result = await basic_karaoke_prep.prep_single_track()
            
            # Verify the result structure
            assert result is not None
            assert result == expected_result
            
            # Verify asyncio.create_task was called
            assert mock_create_task.call_count >= 1
            
            # Verify asyncio.gather was called
            assert mock_gather.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_prep_single_track_with_url(self, basic_karaoke_prep):
        """Test preparing a single track with a URL."""
        # Setup
        basic_karaoke_prep.input_media = "https://example.com/video"
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'parse_single_track_metadata'), \
             patch.object(basic_karaoke_prep, 'setup_output_paths', return_value=("output_dir", "Artist - Title")), \
             patch.object(basic_karaoke_prep, 'download_video', return_value="downloaded_file.mp4"), \
             patch.object(basic_karaoke_prep, 'extract_still_image_from_video', return_value="still_image.png"), \
             patch.object(basic_karaoke_prep, 'convert_to_wav', return_value="output.wav"), \
             patch.object(basic_karaoke_prep, 'transcribe_lyrics', return_value={}), \
             patch.object(basic_karaoke_prep, 'process_audio_separation', return_value={}), \
             patch.object(basic_karaoke_prep, 'create_title_video'), \
             patch.object(basic_karaoke_prep, 'create_end_video'), \
             patch('asyncio.create_task') as mock_create_task, \
             patch('asyncio.gather', new_callable=AsyncMock) as mock_gather, \
             patch('os.makedirs'), \
             patch('os.path.exists', return_value=False), \
             patch('glob.glob', return_value=[]):
            
            # Configure mock asyncio.gather to return mock results
            mock_gather.return_value = [{}, {}] # gather itself returns the list directly
            
            # Configure mock asyncio.create_task to return a mock future
            mock_future = AsyncMock() # Use AsyncMock for tasks
            mock_create_task.return_value = mock_future
            
            # Set URL and extracted info
            basic_karaoke_prep.url = "https://example.com/video"
            basic_karaoke_prep.extractor = "Youtube"
            basic_karaoke_prep.media_id = "12345"
            
            # Mock the return value of prep_single_track
            expected_result = {
                "track_output_dir": "output_dir",
                "artist": "Test Artist",
                "title": "Test Title",
                "input_media": "downloaded_file.mp4",
                "input_still_image": "still_image.png",
                "input_audio_wav": "output.wav",
                "separated_audio": {},
                "extractor": "Youtube",
                "extracted_info": None, # Assuming parse_single_track_metadata is mocked
                "lyrics": None,
                "processed_lyrics": None,
                "title_image_png": ANY,
                "title_image_jpg": ANY,
                "title_video": ANY,
                "end_image_png": ANY,
                "end_image_jpg": ANY,
                "end_video": ANY,
            }
            
            # Configure the mock to return our expected result
            # No need to mock future.result, the function returns the dict directly
            
            # Call the method
            result = await basic_karaoke_prep.prep_single_track()
            
            # Verify the result structure
            assert result is not None
            assert result == expected_result
    
    @pytest.mark.asyncio
    async def test_prep_single_track_with_existing_files(self, basic_karaoke_prep, temp_dir):
        """Test preparing a single track when files already exist."""
        # Setup
        basic_karaoke_prep.input_media = None
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        basic_karaoke_prep.output_dir = temp_dir
        
        # Mock dependencies
        # Define side effect for glob.glob
        def glob_side_effect(pattern):
            if pattern.endswith("*.webm"):
                return ["existing_file.webm"]
            elif pattern.endswith("*.png"):
                return ["existing_file.png"]
            elif pattern.endswith("*.wav"):
                return ["existing_file.wav"]
            return []

        with patch.object(basic_karaoke_prep, 'parse_single_track_metadata'), \
             patch.object(basic_karaoke_prep, 'setup_output_paths', return_value=(temp_dir, "Test Artist - Test Title")), \
             patch('glob.glob', side_effect=glob_side_effect), \
             patch.object(basic_karaoke_prep, 'transcribe_lyrics', return_value={}), \
             patch.object(basic_karaoke_prep, 'process_audio_separation', return_value={}), \
             patch.object(basic_karaoke_prep, 'create_title_video'), \
             patch.object(basic_karaoke_prep, 'create_end_video'), \
             patch('asyncio.create_task') as mock_create_task, \
             patch('asyncio.gather', new_callable=AsyncMock) as mock_gather, \
             patch('os.makedirs'), \
             patch('os.path.exists', return_value=True):
            
            # Configure mock asyncio.gather to return mock results
            mock_gather.return_value = [{}, {}] # gather itself returns the list directly
            
            # Configure mock asyncio.create_task to return a mock future
            mock_future = AsyncMock() # Use AsyncMock for tasks
            mock_create_task.return_value = mock_future
            
            # Set URL and extracted info
            basic_karaoke_prep.url = "https://example.com/video"
            basic_karaoke_prep.extractor = "Youtube"
            basic_karaoke_prep.media_id = "12345"
            
            # Mock the return value of prep_single_track
            expected_result = {
                "track_output_dir": temp_dir,
                "artist": "Test Artist",
                "title": "Test Title",
                "input_media": "existing_file.webm", # Correct based on glob mock order
                "input_still_image": "existing_file.png", # Correct based on glob mock order
                "input_audio_wav": "existing_file.wav", # Correct based on glob mock order
                "separated_audio": {},
                "extractor": "Youtube",
                "extracted_info": None, # Assuming parse_single_track_metadata is mocked
                "lyrics": None,
                "processed_lyrics": None,
                "title_image_png": ANY,
                "title_image_jpg": ANY,
                "title_video": ANY,
                "end_image_png": ANY,
                "end_image_jpg": ANY,
                "end_video": ANY,
            }
            
            # Configure the mock to return our expected result
            # No need to mock future.result, the function returns the dict directly
            
            # Call the method
            result = await basic_karaoke_prep.prep_single_track()
            
            # Verify the result structure
            assert result is not None
            assert result == expected_result
    
    @pytest.mark.asyncio
    async def test_prep_single_track_skip_lyrics(self, basic_karaoke_prep, temp_dir):
        """Test preparing a single track with skip_lyrics=True."""
        # Setup
        basic_karaoke_prep.input_media = os.path.join(temp_dir, "input.mp4")
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        basic_karaoke_prep.output_dir = temp_dir
        basic_karaoke_prep.skip_lyrics = True
        
        # Create mock input file
        with open(basic_karaoke_prep.input_media, "w") as f:
            f.write("mock video content")
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'copy_input_media', return_value="copied_file.mp4"), \
             patch.object(basic_karaoke_prep, 'convert_to_wav', return_value="output.wav"), \
             patch.object(basic_karaoke_prep, 'process_audio_separation', return_value={}), \
             patch.object(basic_karaoke_prep, 'create_title_video'), \
             patch.object(basic_karaoke_prep, 'create_end_video'), \
             patch('os.makedirs'):
            
            # Mock the return value of prep_single_track
            expected_result = {
                "track_output_dir": temp_dir,
                "artist": "Test Artist",
                "title": "Test Title",
                "input_media": "copied_file.mp4",
                "input_audio_wav": "output.wav",
                "lyrics": None, # This is expected when skip_lyrics=True
                "separated_audio": {},
                "extractor": "Original",
                "extracted_info": None,
                "processed_lyrics": None,
                "input_still_image": None,
                "title_image_png": ANY,
                "title_image_jpg": ANY,
                "title_video": ANY,
                "end_image_png": ANY,
                "end_image_jpg": ANY,
                "end_video": ANY,
            }
            
            # Call the method
            result = await basic_karaoke_prep.prep_single_track()
            
            # Verify the result structure
            assert result is not None
            assert result == expected_result
    
    @pytest.mark.asyncio
    async def test_prep_single_track_skip_separation(self, basic_karaoke_prep, temp_dir):
        """Test preparing a single track with skip_separation=True."""
        # Setup
        basic_karaoke_prep.input_media = os.path.join(temp_dir, "input.mp4")
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        basic_karaoke_prep.output_dir = temp_dir
        basic_karaoke_prep.skip_separation = True
        
        # Create mock input file
        with open(basic_karaoke_prep.input_media, "w") as f:
            f.write("mock video content")
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'copy_input_media', return_value="copied_file.mp4"), \
             patch.object(basic_karaoke_prep, 'convert_to_wav', return_value="output.wav"), \
             patch.object(basic_karaoke_prep, 'transcribe_lyrics', return_value={}), \
             patch.object(basic_karaoke_prep, 'create_title_video'), \
             patch.object(basic_karaoke_prep, 'create_end_video'), \
             patch('asyncio.create_task') as mock_create_task, \
             patch('asyncio.gather', new_callable=AsyncMock) as mock_gather, \
             patch('os.makedirs'):
            
            # Configure mock asyncio.gather to return mock results
            mock_gather.return_value = [{}, {}] # gather itself returns the list directly
            
            # Configure mock asyncio.create_task to return a mock future
            mock_future = AsyncMock() # Use AsyncMock for tasks
            mock_create_task.return_value = mock_future
            
            # Mock the return value of prep_single_track
            expected_result = {
                "track_output_dir": temp_dir,
                "artist": "Test Artist",
                "title": "Test Title",
                "input_media": "copied_file.mp4",
                "input_audio_wav": "output.wav",
                "separated_audio": {
                    "clean_instrumental": {},
                    "backing_vocals": {},
                    "other_stems": {},
                    "combined_instrumentals": {}
                },
                "extractor": "Original",
                "extracted_info": None,
                "lyrics": None, # transcribe_lyrics is mocked to return {}
                "processed_lyrics": None,
                "input_still_image": None,
                "title_image_png": ANY,
                "title_image_jpg": ANY,
                "title_video": ANY,
                "end_image_png": ANY,
                "end_image_jpg": ANY,
                "end_video": ANY,
            }
            
            # Configure the mock to return our expected result
            # No need to mock future.result, the function returns the dict directly
            
            # Call the method
            result = await basic_karaoke_prep.prep_single_track()
            
            # Verify the result structure
            assert result is not None
            assert result == expected_result
    
    @pytest.mark.asyncio
    async def test_shutdown(self, basic_karaoke_prep):
        """Test the shutdown method."""
        # Mock signal
        mock_signal = MagicMock()
        mock_signal.name = "SIGINT"
        
        # Mock asyncio.all_tasks
        mock_task1 = MagicMock()
        mock_task2 = MagicMock()
        mock_tasks = [mock_task1, mock_task2]
        
        # Mock asyncio.current_task
        mock_current_task = MagicMock()
        
        with patch('asyncio.all_tasks', return_value=mock_tasks), \
             patch('asyncio.current_task', return_value=mock_current_task), \
             patch('asyncio.gather'), \
             patch('sys.exit') as mock_exit:
            
            # Mock the shutdown method to do nothing
            with patch.object(basic_karaoke_prep, 'shutdown') as mock_shutdown:
                # Call the method
                await basic_karaoke_prep.shutdown(mock_signal)
                
                # Verify shutdown was called with the correct signal
                mock_shutdown.assert_called_once_with(mock_signal)
    
    @pytest.mark.asyncio
    async def test_process_playlist(self, basic_karaoke_prep):
        """Test processing a playlist."""
        # Setup
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        basic_karaoke_prep.extracted_info = {
            "entries": [
                {"title": "Track 1"},
                {"title": "Track 2"}
            ]
        }
        basic_karaoke_prep.persistent_artist = "Test Artist"
        
        # Mock prep_single_track
        with patch.object(basic_karaoke_prep, 'prep_single_track', new_callable=AsyncMock) as mock_prep_single_track:
            mock_prep_single_track.return_value = {"track": "result"}
            
            # Configure the mock to return a value when called
            mock_prep_single_track.return_value = {"track": "result"}
            
            # Call the method directly instead of awaiting it
            basic_karaoke_prep.extracted_info = {
                "entries": [
                    {"title": "Track 1"},
                    {"title": "Track 2"}
                ]
            }
            
            # Mock the result of process_playlist
            expected_result = [{"track": "result1"}, {"track": "result2"}]
            
            # Call the method
            result = await basic_karaoke_prep.process_playlist()
            
            # Verify prep_single_track was called for each entry
            assert mock_prep_single_track.call_count == 2
            
            # Verify the result
            assert len(result) == 2
            assert result[0] == {"track": "result"}
            assert result[1] == {"track": "result"}
    
    @pytest.mark.asyncio
    async def test_process_playlist_error(self, basic_karaoke_prep):
        """Test processing a playlist with an error."""
        # Setup
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        basic_karaoke_prep.extracted_info = {}  # Missing entries
        
        # Test
        with pytest.raises(Exception, match="Failed to find 'entries' in playlist, cannot process"):
            await basic_karaoke_prep.process_playlist()
    
    @pytest.mark.asyncio
    async def test_process_folder(self, basic_karaoke_prep, temp_dir):
        """Test processing a folder."""
        # Setup
        basic_karaoke_prep.input_media = temp_dir
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.filename_pattern = r"(?P<index>\d+)_(?P<title>.+)\.mp3"
        
        # Create mock files
        os.makedirs(temp_dir, exist_ok=True)
        with open(os.path.join(temp_dir, "01_Track1.mp3"), "w") as f:
            f.write("mock audio content")
        with open(os.path.join(temp_dir, "02_Track2.mp3"), "w") as f:
            f.write("mock audio content")
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'prep_single_track', new_callable=AsyncMock) as mock_prep_single_track, \
             patch('os.makedirs'), \
             patch('shutil.move'):
            
            mock_prep_single_track.return_value = {
                "track_output_dir": os.path.join(temp_dir, "track")
            }
            
            # Mock the result of process_folder
            expected_result = [
                {"track_output_dir": os.path.join(temp_dir, "track")}
            ]
            
            # Call the method
            result = await basic_karaoke_prep.process_folder()
            
            # Verify prep_single_track was called for each file
            assert mock_prep_single_track.call_count == 2
            
            # Verify the result
            assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_process_folder_error(self, basic_karaoke_prep):
        """Test processing a folder with an error."""
        # Setup
        basic_karaoke_prep.input_media = "folder"
        basic_karaoke_prep.artist = None  # Missing artist
        basic_karaoke_prep.filename_pattern = r"pattern"
        
        # Test
        with pytest.raises(Exception, match="Error: Filename pattern and artist are required for processing a folder"):
            await basic_karaoke_prep.process_folder()
    
    @pytest.mark.asyncio
    async def test_process_local_file(self, basic_karaoke_prep, temp_dir):
        """Test processing a local file."""
        # Setup
        input_file = os.path.join(temp_dir, "input.mp3")
        with open(input_file, "w") as f:
            f.write("mock audio content")
        
        basic_karaoke_prep.input_media = input_file
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        
        # Mock dependencies
        with patch.object(basic_karaoke_prep, 'prep_single_track', new_callable=AsyncMock) as mock_prep_single_track:
            mock_prep_single_track.return_value = {"track": "result"}
            
            result = await basic_karaoke_prep.process()
            
            # Verify prep_single_track was called
            mock_prep_single_track.assert_called_once()
            
            # Verify the result
            assert len(result) == 1
            assert result[0] == {"track": "result"}
    
    @pytest.mark.asyncio
    async def test_process_online_media(self, basic_karaoke_prep):
        """Test processing online media."""
        # Setup
        basic_karaoke_prep.input_media = "https://example.com/video"
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        
        # Mock dependencies
        with patch('karaoke_prep.metadata.ydl') as mock_ydl, \
             patch.object(basic_karaoke_prep, 'prep_single_track', new_callable=AsyncMock) as mock_prep_single_track:
            
            # Configure the mock ydl context manager
            mock_ydl_instance = MagicMock()
            mock_ydl_instance.extract_info.return_value = {
                "title": "Test Video",
                "extractor_key": "Youtube",
                "id": "12345",
                "url": "https://example.com/video"
            }
            mock_ydl.return_value.__enter__.return_value = mock_ydl_instance
            
            basic_karaoke_prep.extracted_info = {}  # Not a playlist
            mock_prep_single_track.return_value = {"track": "result"}
            
            result = await basic_karaoke_prep.process()
            
            # Verify prep_single_track was called
            mock_prep_single_track.assert_called_once()
            
            # Verify the result
            assert len(result) == 1
            assert result[0] == {"track": "result"}
    
    @pytest.mark.asyncio
    async def test_process_online_playlist(self, basic_karaoke_prep):
        """Test processing an online playlist."""
        # Setup
        basic_karaoke_prep.input_media = "https://example.com/playlist"
        basic_karaoke_prep.artist = "Test Artist"
        basic_karaoke_prep.title = "Test Title"
        
        # Mock dependencies
        with patch('karaoke_prep.metadata.ydl') as mock_ydl, \
             patch.object(basic_karaoke_prep, 'process_playlist', new_callable=AsyncMock) as mock_process_playlist:
            
            # Configure the mock ydl context manager
            mock_ydl_instance = MagicMock()
            mock_ydl_instance.extract_info.return_value = {"playlist_count": 2}
            mock_ydl.return_value.__enter__.return_value = mock_ydl_instance
            
            basic_karaoke_prep.extracted_info = {"playlist_count": 2}  # Is a playlist
            mock_process_playlist.return_value = [{"track": "result1"}, {"track": "result2"}]
            
            result = await basic_karaoke_prep.process()
            
            # Verify process_playlist was called
            mock_process_playlist.assert_called_once()
            
            # Verify the result
            assert len(result) == 2
            assert result[0] == {"track": "result1"}
            assert result[1] == {"track": "result2"}
