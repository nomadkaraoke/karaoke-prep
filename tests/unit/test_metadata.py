import pytest
from unittest.mock import MagicMock, patch
import yt_dlp.YoutubeDL as ydl
from karaoke_prep.karaoke_prep import KaraokePrep

class TestMetadata:
    def test_extract_info_for_online_media_with_url(self, basic_karaoke_prep):
        """Test extracting info from online media with a URL."""
        url = "https://example.com/video"
        mock_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": url
        }
        
        # Mock the yt_dlp.YoutubeDL context manager
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_info
        mock_ydl = MagicMock(return_value=mock_ydl_instance)
        
        with patch('yt_dlp.YoutubeDL', mock_ydl):
            # Mock the extract_info method to return the mock_info
            mock_ydl_instance.extract_info.return_value = mock_info
            
            # Call the method
            basic_karaoke_prep.extract_info_for_online_media(input_url=url)
            
            # Verify the extracted_info was set correctly
            assert basic_karaoke_prep.extracted_info == mock_info
            
            # Verify extract_info was called with correct arguments
            mock_ydl_instance.extract_info.assert_called_once_with(url, download=False)
            
            # Verify the extracted_info was set correctly
            assert basic_karaoke_prep.extracted_info == mock_info
    
    def test_extract_info_for_online_media_with_search(self, basic_karaoke_prep):
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
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_search_result
        mock_ydl = MagicMock(return_value=mock_ydl_instance)
        
        with patch('yt_dlp.YoutubeDL', mock_ydl):
            # Mock the extract_info method to return the mock_search_result
            mock_ydl_instance.extract_info.return_value = mock_search_result
            
            # Call the method
            basic_karaoke_prep.extract_info_for_online_media(input_artist=artist, input_title=title)
            
            # Verify the extracted_info was set correctly
            assert basic_karaoke_prep.extracted_info == mock_search_result["entries"][0]
            
            # Verify the extracted_info was set correctly
            assert basic_karaoke_prep.extracted_info == mock_search_result["entries"][0]
    
    def test_extract_info_for_online_media_no_results(self, basic_karaoke_prep):
        """Test extracting info from online media with no search results."""
        artist = "Test Artist"
        title = "Test Title"
        mock_search_result = {"entries": []}
        
        # Mock the yt_dlp.YoutubeDL context manager
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.extract_info.return_value = mock_search_result
        mock_ydl = MagicMock(return_value=mock_ydl_instance)
        
        with patch('yt_dlp.YoutubeDL', mock_ydl):
            # Mock the extract_info method to return the mock_search_result
            mock_ydl_instance.extract_info.return_value = mock_search_result
            
            # Call the method and expect an exception
            with pytest.raises(Exception, match=f"No search results found on YouTube for query: {artist} {title}"):
                basic_karaoke_prep.extract_info_for_online_media(input_artist=artist, input_title=title)
    
    def test_parse_single_track_metadata_complete(self, basic_karaoke_prep):
        """Test parsing metadata from extracted info with complete information."""
        basic_karaoke_prep.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        basic_karaoke_prep.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_prep.url == "https://example.com/video"
        assert basic_karaoke_prep.extractor == "Youtube"
        assert basic_karaoke_prep.media_id == "12345"
        assert basic_karaoke_prep.artist == "Test Artist"
        assert basic_karaoke_prep.title == "Test Title"
    
    def test_parse_single_track_metadata_with_input_values(self, basic_karaoke_prep):
        """Test parsing metadata with provided input values."""
        basic_karaoke_prep.extracted_info = {
            "title": "Wrong Artist - Wrong Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        input_artist = "Input Artist"
        input_title = "Input Title"
        
        basic_karaoke_prep.parse_single_track_metadata(input_artist, input_title)
        
        assert basic_karaoke_prep.url == "https://example.com/video"
        assert basic_karaoke_prep.extractor == "Youtube"
        assert basic_karaoke_prep.media_id == "12345"
        # Set the artist to a different value to verify it gets updated
        basic_karaoke_prep.artist = "Test Artist"
        
        # Call the method
        basic_karaoke_prep.parse_single_track_metadata(input_artist, input_title)
        
        # Verify the artist was updated
        assert basic_karaoke_prep.artist == input_artist
        assert basic_karaoke_prep.title == input_title
    
    def test_parse_single_track_metadata_with_persistent_artist(self, basic_karaoke_prep):
        """Test parsing metadata with persistent artist."""
        basic_karaoke_prep.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        basic_karaoke_prep.persistent_artist = "Persistent Artist"
        
        basic_karaoke_prep.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_prep.artist == "Persistent Artist"
        assert basic_karaoke_prep.title == "Test Title"
    
    def test_parse_single_track_metadata_with_ie_key(self, basic_karaoke_prep):
        """Test parsing metadata with ie_key instead of extractor_key."""
        basic_karaoke_prep.extracted_info = {
            "title": "Test Artist - Test Title",
            "ie_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        basic_karaoke_prep.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_prep.extractor == "Youtube"
    
    def test_parse_single_track_metadata_with_webpage_url(self, basic_karaoke_prep):
        """Test parsing metadata with webpage_url instead of url."""
        basic_karaoke_prep.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345",
            "webpage_url": "https://example.com/video"
        }
        
        basic_karaoke_prep.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_prep.url == "https://example.com/video"
    
    def test_parse_single_track_metadata_missing_url(self, basic_karaoke_prep):
        """Test parsing metadata with missing URL."""
        basic_karaoke_prep.extracted_info = {
            "title": "Test Artist - Test Title",
            "extractor_key": "Youtube",
            "id": "12345"
        }
        
        with pytest.raises(Exception, match="Failed to extract URL from input media metadata"):
            basic_karaoke_prep.parse_single_track_metadata(None, None)
    
    def test_parse_single_track_metadata_missing_extractor(self, basic_karaoke_prep):
        """Test parsing metadata with missing extractor."""
        basic_karaoke_prep.extracted_info = {
            "title": "Test Artist - Test Title",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        with pytest.raises(Exception, match="Failed to find extractor name from input media metadata"):
            basic_karaoke_prep.parse_single_track_metadata(None, None)
    
    def test_parse_single_track_metadata_with_uploader(self, basic_karaoke_prep):
        """Test parsing metadata with uploader as artist fallback."""
        basic_karaoke_prep.extracted_info = {
            "title": "Test Title",  # No artist in title
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video",
            "uploader": "Test Uploader"
        }
        
        basic_karaoke_prep.parse_single_track_metadata(None, None)
        
        assert basic_karaoke_prep.artist == "Test Uploader"
        assert basic_karaoke_prep.title == "Test Title"
    
    def test_parse_single_track_metadata_missing_artist_title(self, basic_karaoke_prep):
        """Test parsing metadata with missing artist and title."""
        basic_karaoke_prep.extracted_info = {
            "extractor_key": "Youtube",
            "id": "12345",
            "url": "https://example.com/video"
        }
        
        with pytest.raises(Exception, match="Failed to extract artist and title from the input media metadata"):
            basic_karaoke_prep.parse_single_track_metadata(None, None)
