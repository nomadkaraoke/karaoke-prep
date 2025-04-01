import pytest
import os
import pickle
from unittest.mock import patch, MagicMock, mock_open, call, ANY

# Adjust the import path
from karaoke_prep.karaoke_finalise.karaoke_finalise import KaraokeFinalise
from .test_initialization import mock_logger, basic_finaliser, MINIMAL_CONFIG # Reuse fixtures
from .test_file_input_validation import BASE_NAME, ARTIST, TITLE, TITLE_JPG # Reuse constants
from .test_ffmpeg_commands import OUTPUT_FILES as FFMPEG_OUTPUT_FILES # Reuse constants

YOUTUBE_SECRETS_FILE = "client_secrets.json"
YOUTUBE_DESC_FILE = "youtube_description.txt"
YOUTUBE_TOKEN_FILE = "/tmp/karaoke-finalise-youtube-token.pickle"

# Define expected output filenames relevant to YouTube
OUTPUT_FILES_YT = {
    "final_karaoke_lossless_mkv": FFMPEG_OUTPUT_FILES["final_karaoke_lossless_mkv"],
}
INPUT_FILES_YT = {
    "title_jpg": TITLE_JPG,
}

@pytest.fixture
def finaliser_for_yt(mock_logger):
    """Fixture for a finaliser configured for YouTube tasks."""
    config = MINIMAL_CONFIG.copy()
    config.update({
        "youtube_client_secrets_file": YOUTUBE_SECRETS_FILE,
        "youtube_description_file": YOUTUBE_DESC_FILE,
    })
    with patch.object(KaraokeFinalise, 'detect_best_aac_codec', return_value='aac'):
        finaliser = KaraokeFinalise(logger=mock_logger, **config)
    # Manually enable features for testing specific methods
    finaliser.youtube_upload_enabled = True
    return finaliser

@pytest.fixture
def mock_youtube_service():
    """Fixture for a mocked YouTube service object."""
    mock_service = MagicMock()
    # Mock chained calls
    mock_service.channels.return_value.list.return_value.execute.return_value = {"items": [{"id": "UC_test_channel_id"}]}
    mock_service.search.return_value.list.return_value.execute.return_value = {"items": []} # Default: no search results
    mock_service.videos.return_value.delete.return_value.execute.return_value = {} # Default: delete success
    mock_service.videos.return_value.insert.return_value.execute.return_value = {"id": "new_video_id"} # Default: insert success
    mock_service.thumbnails.return_value.set.return_value.execute.return_value = {} # Default: thumbnail set success
    return mock_service

@pytest.fixture
def mock_google_auth():
    """Fixture to mock Google auth flow and build."""
    with patch('google_auth_oauthlib.flow.InstalledAppFlow') as mock_flow_cls, \
         patch('googleapiclient.discovery.build') as mock_build, \
         patch('pickle.dump') as mock_pickle_dump, \
         patch('pickle.load') as mock_pickle_load, \
         patch('os.path.exists') as mock_path_exists:

        mock_flow_instance = MagicMock()
        mock_flow_cls.from_client_secrets_file.return_value = mock_flow_instance
        mock_credentials = MagicMock()
        mock_credentials.valid = True # Assume valid by default
        mock_credentials.expired = False
        mock_credentials.refresh_token = "fake_refresh_token"
        mock_flow_instance.run_local_server.return_value = mock_credentials

        # Default: token file doesn't exist, build returns mock service
        mock_path_exists.return_value = False
        mock_pickle_load.side_effect = FileNotFoundError # If exists=True but load fails

        yield {
            "mock_flow_cls": mock_flow_cls,
            "mock_flow_instance": mock_flow_instance,
            "mock_build": mock_build,
            "mock_pickle_dump": mock_pickle_dump,
            "mock_pickle_load": mock_pickle_load,
            "mock_path_exists": mock_path_exists,
            "mock_credentials": mock_credentials,
        }

# --- Truncate Title Test ---
def test_truncate_to_nearest_word(basic_finaliser):
    """Test title truncation logic."""
    long_title = "This is a very long title that definitely exceeds the maximum length allowed"
    max_len = 50
    truncated = basic_finaliser.truncate_to_nearest_word(long_title, max_len)
    assert truncated == "This is a very long title that definitely exceeds ..."
    assert len(truncated) <= max_len + 4 # Allow for ellipsis

    short_title = "Short title"
    truncated_short = basic_finaliser.truncate_to_nearest_word(short_title, max_len)
    assert truncated_short == short_title

    exact_title = "Title exactly fifty characters long right here now!" # 50 chars
    truncated_exact = basic_finaliser.truncate_to_nearest_word(exact_title, max_len)
    # The current logic adds ellipsis even if it fits exactly after truncation before space
    assert truncated_exact == "Title exactly fifty characters long right here ..."

    title_with_no_space = "a"*60
    truncated_no_space = basic_finaliser.truncate_to_nearest_word(title_with_no_space, max_len)
    # If no space is found, it truncates to max_len and adds " ..."
    assert truncated_no_space == "a"*max_len + " ..."

# --- Authentication Tests ---

# Patch open for the secrets file read within the auth flow
@patch("builtins.open", new_callable=mock_open, read_data='{"installed": {"client_id": "test_id"}}')
def test_authenticate_youtube_new_token(mock_secrets_open, finaliser_for_yt, mock_google_auth, mock_youtube_service):
    """Test authentication flow when no token file exists."""
    mock_google_auth["mock_path_exists"].return_value = False # Token file doesn't exist
    mock_google_auth["mock_build"].return_value = mock_youtube_service

    # Mock open specifically for the pickle dump write at the end
    # Use a separate patch context for clarity
    with patch("builtins.open", mock_open()) as mock_pickle_open_write:
        service = finaliser_for_yt.authenticate_youtube()

    # Check secrets file was opened by from_client_secrets_file
    # This assertion might be tricky as the open happens inside the google lib call.
    # Let's trust the google lib mock (`mock_flow_cls`) covers this.
    # mock_secrets_open.assert_called_once_with(YOUTUBE_SECRETS_FILE, "r") # This mock might interfere

    mock_google_auth["mock_path_exists"].assert_called_once_with(YOUTUBE_TOKEN_FILE)
    mock_google_auth["mock_flow_cls"].from_client_secrets_file.assert_called_once_with(
        YOUTUBE_SECRETS_FILE, scopes=["https://www.googleapis.com/auth/youtube"]
    )
    mock_google_auth["mock_flow_instance"].run_local_server.assert_called_once_with(port=0)
    mock_google_auth["mock_pickle_dump"].assert_called_once()
    # Check that the credentials from the flow were saved
    assert mock_google_auth["mock_pickle_dump"].call_args[0][0] == mock_google_auth["mock_credentials"]
    mock_google_auth["mock_build"].assert_called_once_with("youtube", "v3", credentials=mock_google_auth["mock_credentials"])
    assert service == mock_youtube_service
    # Check pickle file was opened for writing
    mock_pickle_open_write.assert_called_once_with(YOUTUBE_TOKEN_FILE, "wb")


# Patch open for the pickle file read
@patch("builtins.open", new_callable=mock_open)
def test_authenticate_youtube_load_valid_token(mock_pickle_open, finaliser_for_yt, mock_google_auth, mock_youtube_service):
    """Test authentication using a valid existing token file."""
    mock_google_auth["mock_path_exists"].return_value = True # Token file exists
    mock_google_auth["mock_pickle_load"].return_value = mock_google_auth["mock_credentials"] # mock pickle.load
    mock_google_auth["mock_credentials"].valid = True # Token is valid
    mock_google_auth["mock_build"].return_value = mock_youtube_service

    # Ensure the mock_open context manager is used for the pickle read
    with mock_pickle_open:
        service = finaliser_for_yt.authenticate_youtube()

    mock_google_auth["mock_path_exists"].assert_called_once_with(YOUTUBE_TOKEN_FILE)
    # Check pickle file was opened for reading
    mock_pickle_open.assert_called_once_with(YOUTUBE_TOKEN_FILE, "rb")
    # Ensure pickle.load was called with the file handle returned by mock_open
    mock_google_auth["mock_pickle_load"].assert_called_once_with(mock_pickle_open())
    mock_google_auth["mock_flow_instance"].run_local_server.assert_not_called() # Should not run flow
    mock_google_auth["mock_pickle_dump"].assert_not_called() # Should not save token again
    mock_google_auth["mock_build"].assert_called_once_with("youtube", "v3", credentials=mock_google_auth["mock_credentials"])
    assert service == mock_youtube_service


# Patch open for both pickle read and write
@patch("builtins.open", new_callable=mock_open)
def test_authenticate_youtube_refresh_token(mock_pickle_open, finaliser_for_yt, mock_google_auth, mock_youtube_service):
    """Test authentication refreshing an expired token."""
    mock_google_auth["mock_path_exists"].return_value = True # Token file exists
    mock_google_auth["mock_pickle_load"].return_value = mock_google_auth["mock_credentials"] # mock pickle.load
    mock_google_auth["mock_credentials"].valid = False # Token is invalid
    mock_google_auth["mock_credentials"].expired = True # But expired
    mock_google_auth["mock_credentials"].refresh_token = "fake_refresh_token" # And has refresh token
    mock_google_auth["mock_build"].return_value = mock_youtube_service

    # Mock the refresh method
    with patch('google.auth.transport.requests.Request') as mock_request:
        mock_refresh = mock_google_auth["mock_credentials"].refresh
        service = finaliser_for_yt.authenticate_youtube()
        mock_refresh.assert_called_once_with(mock_request())

    mock_google_auth["mock_path_exists"].assert_called_once_with(YOUTUBE_TOKEN_FILE)
    # Check pickle file was opened for reading then writing
    mock_pickle_open.assert_has_calls([
        call(YOUTUBE_TOKEN_FILE, "rb"),
        call(YOUTUBE_TOKEN_FILE, "wb")
    ])
    # Ensure pickle.load was called with the file handle returned by mock_open for read
    mock_google_auth["mock_pickle_load"].assert_called_once_with(mock_pickle_open())
    mock_google_auth["mock_flow_instance"].run_local_server.assert_not_called() # Should not run flow
    # Ensure pickle.dump was called with the file handle returned by mock_open for write
    mock_google_auth["mock_pickle_dump"].assert_called_once_with(mock_google_auth["mock_credentials"], mock_pickle_open())
    mock_google_auth["mock_build"].assert_called_once_with("youtube", "v3", credentials=mock_google_auth["mock_credentials"])
    assert service == mock_youtube_service

# --- Channel ID / Video Check Tests ---

@patch.object(KaraokeFinalise, 'authenticate_youtube')
def test_get_channel_id(mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test getting the channel ID."""
    mock_auth.return_value = mock_youtube_service
    channel_id = finaliser_for_yt.get_channel_id()
    assert channel_id == "UC_test_channel_id"
    mock_youtube_service.channels().list.assert_called_once_with(part="snippet", mine=True)

@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch('thefuzz.fuzz.ratio')
@patch('builtins.input', return_value='y') # Confirm match
def test_check_if_video_title_exists_found_confirm(mock_input, mock_fuzz_ratio, mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test finding an existing video and confirming."""
    finaliser_for_yt.non_interactive = False # Ensure prompts are enabled
    mock_auth.return_value = mock_youtube_service
    youtube_title = f"{ARTIST} - {TITLE} (Karaoke)"
    found_video_id = "existing_video_id"
    found_video_title = f"{ARTIST} - {TITLE} (Karaoke) Official"
    mock_youtube_service.search.return_value.list.return_value.execute.return_value = {
        "items": [{"id": {"videoId": found_video_id}, "snippet": {"title": found_video_title}}]
    }
    mock_fuzz_ratio.return_value = 85 # High similarity

    exists = finaliser_for_yt.check_if_video_title_exists_on_youtube_channel(youtube_title)

    assert exists is True
    assert finaliser_for_yt.youtube_video_id == found_video_id
    assert finaliser_for_yt.youtube_url == f"https://www.youtube.com/watch?v={found_video_id}"
    assert finaliser_for_yt.skip_notifications is True # Should skip notifications if found
    mock_fuzz_ratio.assert_called_once_with(youtube_title.lower(), found_video_title.lower())
    mock_input.assert_called_once()

@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch('thefuzz.fuzz.ratio')
@patch('builtins.input', return_value='n') # Reject match
def test_check_if_video_title_exists_found_reject(mock_input, mock_fuzz_ratio, mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test finding an existing video but rejecting the match."""
    finaliser_for_yt.non_interactive = False # Ensure prompts are enabled
    mock_auth.return_value = mock_youtube_service
    youtube_title = f"{ARTIST} - {TITLE} (Karaoke)"
    found_video_id = "existing_video_id"
    found_video_title = f"{ARTIST} - {TITLE} (Karaoke) Official"
    mock_youtube_service.search.return_value.list.return_value.execute.return_value = {
        "items": [{"id": {"videoId": found_video_id}, "snippet": {"title": found_video_title}}]
    }
    mock_fuzz_ratio.return_value = 85

    exists = finaliser_for_yt.check_if_video_title_exists_on_youtube_channel(youtube_title)

    # The current code returns True but sets skip_notifications=True only on 'y'
    assert exists is True # Code returns True even on rejection
    assert finaliser_for_yt.youtube_video_id == found_video_id # ID is set regardless
    assert finaliser_for_yt.youtube_url is not None # URL is set regardless
    assert finaliser_for_yt.skip_notifications is False # Should remain False on rejection
    mock_input.assert_called_once()

@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch('thefuzz.fuzz.ratio')
def test_check_if_video_title_exists_low_similarity(mock_fuzz_ratio, mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test skipping a potential match due to low similarity."""
    mock_auth.return_value = mock_youtube_service
    youtube_title = f"{ARTIST} - {TITLE} (Karaoke)"
    found_video_id = "existing_video_id"
    found_video_title = "Completely Different Title"
    mock_youtube_service.search.return_value.list.return_value.execute.return_value = {
        "items": [{"id": {"videoId": found_video_id}, "snippet": {"title": found_video_title}}]
    }
    mock_fuzz_ratio.return_value = 30 # Low similarity

    exists = finaliser_for_yt.check_if_video_title_exists_on_youtube_channel(youtube_title)

    assert exists is False
    # youtube_video_id attribute is not set if no match found
    assert not hasattr(finaliser_for_yt, 'youtube_video_id')
    assert finaliser_for_yt.youtube_url is None # Check initial state remains None
    assert finaliser_for_yt.skip_notifications is False

@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch('thefuzz.fuzz.ratio')
@patch('builtins.input') # Should not be called
def test_check_if_video_title_exists_non_interactive(mock_input, mock_fuzz_ratio, mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test non-interactive confirmation of existing video."""
    finaliser_for_yt.non_interactive = True
    mock_auth.return_value = mock_youtube_service
    youtube_title = f"{ARTIST} - {TITLE} (Karaoke)"
    found_video_id = "existing_video_id"
    found_video_title = f"{ARTIST} - {TITLE} (Karaoke) Official"
    mock_youtube_service.search.return_value.list.return_value.execute.return_value = {
        "items": [{"id": {"videoId": found_video_id}, "snippet": {"title": found_video_title}}]
    }
    mock_fuzz_ratio.return_value = 85

    exists = finaliser_for_yt.check_if_video_title_exists_on_youtube_channel(youtube_title)

    assert exists is True
    assert finaliser_for_yt.youtube_video_id == found_video_id
    assert finaliser_for_yt.skip_notifications is True
    mock_input.assert_not_called() # No prompt in non-interactive

@patch.object(KaraokeFinalise, 'authenticate_youtube')
def test_check_if_video_title_exists_not_found(mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test when no video is found."""
    mock_auth.return_value = mock_youtube_service
    mock_youtube_service.search.return_value.list.return_value.execute.return_value = {"items": []} # No results
    youtube_title = f"{ARTIST} - {TITLE} (Karaoke)"

    exists = finaliser_for_yt.check_if_video_title_exists_on_youtube_channel(youtube_title)

    assert exists is False
    # youtube_video_id attribute is not set if no match found
    assert not hasattr(finaliser_for_yt, 'youtube_video_id')
    assert finaliser_for_yt.youtube_url is None # Check initial state remains None
    assert finaliser_for_yt.skip_notifications is False

# --- Delete / Upload Tests ---

@patch.object(KaraokeFinalise, 'authenticate_youtube')
def test_delete_youtube_video_success(mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test successful video deletion."""
    mock_auth.return_value = mock_youtube_service
    video_id = "video_to_delete"
    result = finaliser_for_yt.delete_youtube_video(video_id)
    assert result is True
    mock_youtube_service.videos().delete.assert_called_once_with(id=video_id)
    finaliser_for_yt.logger.info.assert_any_call(f"Successfully deleted YouTube video with ID: {video_id}")

@patch.object(KaraokeFinalise, 'authenticate_youtube')
def test_delete_youtube_video_failure(mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test failed video deletion."""
    mock_auth.return_value = mock_youtube_service
    video_id = "video_to_delete"
    mock_youtube_service.videos.return_value.delete.return_value.execute.side_effect = Exception("API Error")
    result = finaliser_for_yt.delete_youtube_video(video_id)
    assert result is False
    mock_youtube_service.videos().delete.assert_called_once_with(id=video_id)
    finaliser_for_yt.logger.error.assert_any_call(f"Failed to delete YouTube video with ID {video_id}: API Error")

@patch.object(KaraokeFinalise, 'authenticate_youtube')
def test_delete_youtube_video_dry_run(mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test video deletion dry run."""
    finaliser_for_yt.dry_run = True
    mock_auth.return_value = mock_youtube_service
    video_id = "video_to_delete"
    result = finaliser_for_yt.delete_youtube_video(video_id)
    assert result is True
    mock_youtube_service.videos().delete.assert_not_called()
    finaliser_for_yt.logger.info.assert_any_call(f"DRY RUN: Would delete YouTube video with ID: {video_id}")


@patch('builtins.open', new_callable=mock_open, read_data="Custom description from file")
# Patch the MediaFileUpload class where it's imported in the module under test
@patch('karaoke_prep.karaoke_finalise.karaoke_finalise.MediaFileUpload')
@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch.object(KaraokeFinalise, 'check_if_video_title_exists_on_youtube_channel', return_value=False) # Assume not exists
@patch.object(KaraokeFinalise, 'truncate_to_nearest_word', side_effect=lambda t, l: t) # Passthrough truncate
def test_upload_youtube_success(mock_truncate, mock_check_exists, mock_auth, mock_media_upload_cls, mock_open_desc, finaliser_for_yt, mock_youtube_service):
    """Test successful YouTube upload."""
    mock_auth.return_value = mock_youtube_service
    # Mock the instances returned by the MediaFileUpload constructor
    mock_video_media = MagicMock()
    mock_thumb_media = MagicMock()
    mock_media_upload_cls.side_effect = [mock_video_media, mock_thumb_media] # Return video then thumb mock

    finaliser_for_yt.upload_final_mp4_to_youtube_with_title_thumbnail(ARTIST, TITLE, INPUT_FILES_YT, OUTPUT_FILES_YT)

    expected_title = f"{ARTIST} - {TITLE} (Karaoke)"
    expected_keywords = ["karaoke", "music", "singing", "instrumental", "lyrics", ARTIST, TITLE]
    expected_description = "Custom description from file"
    expected_category_id = "10"
    expected_privacy = "public"

    mock_check_exists.assert_called_once_with(expected_title)
    mock_open_desc.assert_called_once_with(YOUTUBE_DESC_FILE, "r") # Corrected mock name
    mock_truncate.assert_called_once_with(expected_title, 95)

    # Check video insert call
    insert_call_args = mock_youtube_service.videos().insert.call_args
    assert insert_call_args[1]['part'] == "snippet,status"
    body = insert_call_args[1]['body']
    assert body['snippet']['title'] == expected_title
    assert body['snippet']['description'] == expected_description
    assert body['snippet']['tags'] == expected_keywords
    assert body['snippet']['categoryId'] == expected_category_id
    assert body['status']['privacyStatus'] == expected_privacy
    assert insert_call_args[1]['media_body'] == mock_video_media # Check correct mock instance used
    # Check MediaFileUpload constructor calls
    mock_media_upload_cls.assert_has_calls([
        call(OUTPUT_FILES_YT["final_karaoke_lossless_mkv"], mimetype="video/x-matroska", resumable=True),
        call(INPUT_FILES_YT["title_jpg"], mimetype="image/jpeg")
    ], any_order=True)

    # Check thumbnail set call
    mock_youtube_service.thumbnails().set.assert_called_once()
    thumb_call_args = mock_youtube_service.thumbnails().set.call_args
    assert thumb_call_args[1]['videoId'] == "new_video_id"
    # Ensure the media_body for thumbnail is the one created for the JPG
    assert thumb_call_args[1]['media_body'] == mock_thumb_media # Check correct mock instance used

    assert finaliser_for_yt.youtube_video_id == "new_video_id"
    assert finaliser_for_yt.youtube_url == f"https://www.youtube.com/watch?v=new_video_id"


@patch('karaoke_prep.karaoke_finalise.karaoke_finalise.MediaFileUpload')
@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch.object(KaraokeFinalise, 'check_if_video_title_exists_on_youtube_channel', return_value=True) # Assume exists
@patch.object(KaraokeFinalise, 'delete_youtube_video')
def test_upload_youtube_exists_skip(mock_delete, mock_check_exists, mock_auth, mock_media_upload_cls, finaliser_for_yt, mock_youtube_service):
    """Test skipping upload if video exists and replace_existing is False."""
    mock_auth.return_value = mock_youtube_service
    finaliser_for_yt.youtube_video_id = "existing_id" # Set by check_if_video_title_exists
    finaliser_for_yt.youtube_url = "http://youtube.com/existing_id"

    finaliser_for_yt.upload_final_mp4_to_youtube_with_title_thumbnail(ARTIST, TITLE, INPUT_FILES_YT, OUTPUT_FILES_YT, replace_existing=False)

    mock_check_exists.assert_called_once()
    mock_delete.assert_not_called()
    mock_youtube_service.videos().insert.assert_not_called()
    mock_youtube_service.thumbnails().set.assert_not_called()
    finaliser_for_yt.logger.warning.assert_called_with(f"Video already exists on YouTube, skipping upload: {finaliser_for_yt.youtube_url}")


@patch('builtins.open', new_callable=mock_open, read_data="Desc") # Mock open for description file
@patch('karaoke_prep.karaoke_finalise.karaoke_finalise.MediaFileUpload')
@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch.object(KaraokeFinalise, 'check_if_video_title_exists_on_youtube_channel', return_value=True) # Assume exists
@patch.object(KaraokeFinalise, 'delete_youtube_video', return_value=True) # Delete succeeds
def test_upload_youtube_exists_replace_success(mock_delete, mock_check_exists, mock_auth, mock_media_upload_cls, mock_open_desc, finaliser_for_yt, mock_youtube_service):
    """Test replacing an existing video successfully."""
    mock_auth.return_value = mock_youtube_service
    finaliser_for_yt.youtube_video_id = "existing_id" # Set by check_if_video_title_exists
    finaliser_for_yt.youtube_url = "http://youtube.com/existing_id"

    finaliser_for_yt.upload_final_mp4_to_youtube_with_title_thumbnail(ARTIST, TITLE, INPUT_FILES_YT, OUTPUT_FILES_YT, replace_existing=True)

    mock_check_exists.assert_called_once()
    mock_delete.assert_called_once_with("existing_id")
    # Check that video ID and URL were reset before upload attempt
    # (Difficult to check state mid-function, but ensure insert is called)
    mock_youtube_service.videos().insert.assert_called_once()
    mock_youtube_service.thumbnails().set.assert_called_once()
    # Check final state reflects the *new* video ID
    assert finaliser_for_yt.youtube_video_id == "new_video_id"
    assert finaliser_for_yt.youtube_url == f"https://www.youtube.com/watch?v=new_video_id"
    mock_open_desc.assert_called_once_with(YOUTUBE_DESC_FILE, "r") # Check desc file read


@patch('karaoke_prep.karaoke_finalise.karaoke_finalise.MediaFileUpload')
@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch.object(KaraokeFinalise, 'check_if_video_title_exists_on_youtube_channel', return_value=True) # Assume exists
@patch.object(KaraokeFinalise, 'delete_youtube_video', return_value=False) # Delete fails
def test_upload_youtube_exists_replace_delete_fails(mock_delete, mock_check_exists, mock_auth, mock_media_upload_cls, finaliser_for_yt, mock_youtube_service):
    """Test aborting replacement if deletion fails."""
    mock_auth.return_value = mock_youtube_service
    finaliser_for_yt.youtube_video_id = "existing_id"
    finaliser_for_yt.youtube_url = "http://youtube.com/existing_id"

    # Should not raise an exception, just log error and return
    finaliser_for_yt.upload_final_mp4_to_youtube_with_title_thumbnail(ARTIST, TITLE, INPUT_FILES_YT, OUTPUT_FILES_YT, replace_existing=True)

    mock_check_exists.assert_called_once()
    mock_delete.assert_called_once_with("existing_id")
    mock_youtube_service.videos().insert.assert_not_called() # Upload aborted
    mock_youtube_service.thumbnails().set.assert_not_called()
    finaliser_for_yt.logger.error.assert_called_with("Failed to delete existing video, aborting upload")
    # Video ID and URL should remain the old ones
    assert finaliser_for_yt.youtube_video_id == "existing_id"
    assert finaliser_for_yt.youtube_url == "http://youtube.com/existing_id"

@patch.object(KaraokeFinalise, 'authenticate_youtube')
@patch.object(KaraokeFinalise, 'check_if_video_title_exists_on_youtube_channel', return_value=False)
def test_upload_youtube_dry_run(mock_check_exists, mock_auth, finaliser_for_yt, mock_youtube_service):
    """Test YouTube upload dry run."""
    finaliser_for_yt.dry_run = True
    mock_auth.return_value = mock_youtube_service

    finaliser_for_yt.upload_final_mp4_to_youtube_with_title_thumbnail(ARTIST, TITLE, INPUT_FILES_YT, OUTPUT_FILES_YT)

    # Check should *not* happen in dry run for upload
    mock_check_exists.assert_not_called()
    mock_youtube_service.videos().insert.assert_not_called()
    mock_youtube_service.thumbnails().set.assert_not_called()
    # Check that the log message contains the expected dry run text
    dry_run_log_found = any("DRY RUN: Would upload" in call_args[0][0] for call_args in finaliser_for_yt.logger.info.call_args_list)
    assert dry_run_log_found, "Expected dry run log message for YouTube upload not found."
    assert finaliser_for_yt.youtube_video_id is None
    assert finaliser_for_yt.youtube_url is None
