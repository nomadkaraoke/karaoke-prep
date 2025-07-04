import pytest
from unittest.mock import MagicMock, patch, call
# Import the specific class for patching is not needed if we patch the target correctly
# from yt_dlp import YoutubeDL 
from karaoke_gen.karaoke_gen import KaraokePrep

class TestMetadata:
    def test_extract_info_for_online_media_with_url(self, basic_karaoke_gen):
        """Test extracting info from online media with a URL."""
        url = "https://example.com/video"
        mock_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": url
        }
        
        # Mock the yt_dlp.YoutubeDL context manager
        
        # Mock the yt_dlp.YoutubeDL context manager and its extract_info method
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_info
        
        # Patch the 'ydl' alias used in metadata.py
        with patch('karaoke_gen.metadata.ydl') as mock_ydl_context:
            # Configure the context manager mock
            mock_ydl_context.return_value.__enter__.return_value = mock_ydl_instance
            
            # Call the method
            basic_karaoke_gen.extract_info_for_online_media(input_url=url)
            
            # Verify ydl was instantiated (implicitly checks context manager usage)
            expected_ydl_opts = {
                "quiet": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "referer": "https://www.youtube.com/",
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "fragment_retries": 3,
                "extractor_retries": 3,
                "retries": 3,
                "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-us,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
            }
            mock_ydl_context.assert_called_once_with(expected_ydl_opts)
            
            # Verify extract_info was called on the instance
            mock_ydl_instance.extract_info.assert_called_once_with(url, download=False)
            
            # Verify the extracted_info was set correctly
            assert basic_karaoke_gen.extracted_info == mock_info
    
    def test_extract_info_for_online_media_with_search(self, basic_karaoke_gen):
        """Test extracting info from online media with artist and title search."""
        artist = "Test Artist"
        title = "Test Title"
        mock_search_result = {
            "entries": [
                {
                    "title": "Test Artist - Test Title",
                    "extractor_key": "Youtube",
                    "id": "12345",
                    "url": "https://example.com/video"
                }
            ]
        }
        
        # Mock the yt_dlp.YoutubeDL context manager
        
        # Mock the yt_dlp.YoutubeDL context manager and its extract_info method
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_search_result
        
        # Patch the 'ydl' alias used in metadata.py
        with patch('karaoke_gen.metadata.ydl') as mock_ydl_context:
            # Configure the context manager mock
            mock_ydl_context.return_value.__enter__.return_value = mock_ydl_instance
            
            # Call the method
            basic_karaoke_gen.extract_info_for_online_media(input_artist=artist, input_title=title)
            
            # Verify ydl was instantiated with correct options
            expected_ydl_opts = {
                "quiet": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "referer": "https://www.youtube.com/",
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "fragment_retries": 3,
                "extractor_retries": 3,
                "retries": 3,
                "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-us,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
                "format": "bestaudio", 
                "noplaylist": "True", 
                "extract_flat": True
            }
            mock_ydl_context.assert_called_once_with(expected_ydl_opts)
            
            # Verify extract_info was called with the correct arguments
            expected_query = f"ytsearch1:{artist} {title}"
            mock_ydl_instance.extract_info.assert_called_once_with(expected_query, download=False)
            
            # Verify the extracted_info was set correctly
            assert basic_karaoke_gen.extracted_info == mock_search_result["entries"][0]
    
    def test_extract_info_for_online_media_no_results(self, basic_karaoke_gen):
        """Test extracting info from online media with no search results."""
        artist = "Test Artist"
        title = "Test Title"
        mock_search_result = {"entries": []}
        
        # Mock the yt_dlp.YoutubeDL context manager
        
        # Mock the yt_dlp.YoutubeDL context manager and its extract_info method
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_search_result
        
        # Patch the 'ydl' alias used in metadata.py
        with patch('karaoke_gen.metadata.ydl') as mock_ydl_context:
            # Configure the context manager mock
            mock_ydl_context.return_value.__enter__.return_value = mock_ydl_instance

            # Assert that calling the method with no results raises an IndexError
            with pytest.raises(IndexError):
                basic_karaoke_gen.extract_info_for_online_media(input_artist=artist, input_title=title)

            # Verify ydl was instantiated with correct options
            expected_ydl_opts = {
                "quiet": True,
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "referer": "https://www.youtube.com/",
                "sleep_interval": 1,
                "max_sleep_interval": 3,
                "fragment_retries": 3,
                "extractor_retries": 3,
                "retries": 3,
                "http_headers": {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-us,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
                "format": "bestaudio", 
                "noplaylist": "True", 
                "extract_flat": True
            }
            mock_ydl_context.assert_called_once_with(expected_ydl_opts)

            # Verify extract_info was called with the correct arguments
            expected_query = f"ytsearch1:{artist} {title}"
            mock_ydl_instance.extract_info.assert_called_once_with(expected_query, download=False)

    def test_parse_single_track_metadata_complete(self, basic_karaoke_gen):
        """Test parsing metadata from extracted info with complete information."""
        basic_karaoke_gen.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        basic_karaoke_gen.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_gen.url == "https://example.com/video"
        assert basic_karaoke_gen.extractor == "Youtube"
        assert basic_karaoke_gen.media_id == "12345"
        assert basic_karaoke_gen.artist == "Test Artist"
        assert basic_karaoke_gen.title == "Test Title"
    
    def test_parse_single_track_metadata_with_input_values(self, basic_karaoke_gen):
        """Test parsing metadata with provided input values."""
        basic_karaoke_gen.extracted_info = {
            "title": "Wrong Artist - Wrong Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        input_artist = "Input Artist"
        input_title = "Input Title"
        
        # Set artist and title on the instance *before* calling parse,
        # because the method uses these values in its final check.
        basic_karaoke_gen.artist = input_artist
        basic_karaoke_gen.title = input_title
        
        # Call the method
        basic_karaoke_gen.parse_single_track_metadata(input_artist, input_title)
        
        # Verify URL, extractor, and ID are parsed correctly
        assert basic_karaoke_gen.url == "https://example.com/video"
        assert basic_karaoke_gen.extractor == "Youtube"
        assert basic_karaoke_gen.media_id == "12345"
        
        # Verify the artist and title remain the input values
        assert basic_karaoke_gen.artist == input_artist
        assert basic_karaoke_gen.title == input_title
    
    def test_parse_single_track_metadata_with_persistent_artist(self, basic_karaoke_gen):
        """Test parsing metadata with persistent artist."""
        basic_karaoke_gen.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        basic_karaoke_gen.persistent_artist = "Persistent Artist"
        
        basic_karaoke_gen.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_gen.artist == "Persistent Artist"
        assert basic_karaoke_gen.title == "Test Title"
    
    def test_parse_single_track_metadata_with_ie_key(self, basic_karaoke_gen):
        """Test parsing metadata with ie_key instead of extractor_key."""
        basic_karaoke_gen.extracted_info = {
            "title": "Test Artist - Test Title",
            "ie_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        basic_karaoke_gen.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_gen.extractor == "Youtube"
    
    def test_parse_single_track_metadata_with_webpage_url(self, basic_karaoke_gen):
        """Test parsing metadata with webpage_url instead of url."""
        basic_karaoke_gen.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "webpage_url": "https://example.com/video"
        }
        
        basic_karaoke_gen.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_gen.url == "https://example.com/video"
    
    def test_parse_single_track_metadata_missing_url(self, basic_karaoke_gen):
        """Test parsing metadata with missing URL."""
        basic_karaoke_gen.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345"
        }
        
        with pytest.raises(Exception, match="Failed to extract URL from input media metadata"):
            basic_karaoke_gen.parse_single_track_metadata(None, None)
    
    def test_parse_single_track_metadata_missing_extractor(self, basic_karaoke_gen):
        """Test parsing metadata with missing extractor."""
        basic_karaoke_gen.extracted_info = {
            "title": "Test Artist - Test Title",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        with pytest.raises(Exception, match="Failed to find extractor name from input media metadata"):
            basic_karaoke_gen.parse_single_track_metadata(None, None)
    
    def test_parse_single_track_metadata_with_uploader(self, basic_karaoke_gen):
        """Test parsing metadata with uploader as artist fallback."""
        basic_karaoke_gen.extracted_info = {
            "title": "Test Title",  # No artist in title
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video",
            "uploader": "Test Uploader"
        }
        
        basic_karaoke_gen.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_gen.artist == "Test Uploader"
        assert basic_karaoke_gen.title == "Test Title"
    
    def test_parse_single_track_metadata_missing_artist_title(self, basic_karaoke_gen):
        """Test parsing metadata with missing artist and title."""
        basic_karaoke_gen.extracted_info = {
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        with pytest.raises(Exception, match="Failed to extract artist and title from the input media metadata"):
            basic_karaoke_gen.parse_single_track_metadata(None, None)
