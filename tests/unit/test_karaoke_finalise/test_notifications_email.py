import pytest
import os
import pickle
import base64
from email.mime.text import MIMEText
from unittest.mock import patch, MagicMock, mock_open, call, ANY
import requests # For requests.exceptions.RequestException

# Adjust the import path
from karaoke_gen.karaoke_finalise.karaoke_finalise import KaraokeFinalise
from .test_initialization import mock_logger, basic_finaliser, MINIMAL_CONFIG # Reuse fixtures
from .test_file_input_validation import ARTIST, TITLE # Reuse constants
from .test_youtube_integration import mock_google_auth # Reuse Gmail auth mocks structure

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/123/abc"
EMAIL_TEMPLATE_FILE = "email_template.txt"
GMAIL_TOKEN_FILE = "/tmp/karaoke-finalise-gmail-token.pickle"
YOUTUBE_SECRETS_FILE_GMAIL = "client_secrets_gmail.json" # Assume separate secrets for Gmail scope if needed

@pytest.fixture
def finaliser_for_notify(mock_logger):
    """Fixture for a finaliser configured for notification/email tasks."""
    config = MINIMAL_CONFIG.copy()
    config.update({
        "discord_webhook_url": DISCORD_WEBHOOK_URL,
        "email_template_file": EMAIL_TEMPLATE_FILE,
        # Need youtube secrets for Gmail auth as well in the original code
        "youtube_client_secrets_file": YOUTUBE_SECRETS_FILE_GMAIL,
        "brand_prefix": "TEST", # Needed for email subject brand code
    })
    with patch.object(KaraokeFinalise, 'detect_best_aac_codec', return_value='aac'):
        finaliser = KaraokeFinalise(logger=mock_logger, **config)
    # Manually enable features for testing specific methods
    finaliser.discord_notication_enabled = True
    # Set some state needed for notifications/email
    finaliser.youtube_url = "https://www.youtube.com/watch?v=test_vid"
    finaliser.brand_code = "TEST-0001"
    finaliser.brand_code_dir_sharing_link = "https://dropbox.com/share/link"
    return finaliser

@pytest.fixture
def mock_gmail_service():
    """Fixture for a mocked Gmail service object."""
    mock_service = MagicMock()
    mock_service.users.return_value.drafts.return_value.create.return_value.execute.return_value = {"id": "draft_123"}
    return mock_service

# --- Discord Notification Tests ---

@patch('requests.post')
def test_post_discord_message_success(mock_post, finaliser_for_notify):
    """Test successful posting to Discord."""
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None # No error
    mock_post.return_value = mock_response
    message = "Test message"

    finaliser_for_notify.post_discord_message(message, DISCORD_WEBHOOK_URL)

    mock_post.assert_called_once_with(DISCORD_WEBHOOK_URL, json={"content": message})
    mock_response.raise_for_status.assert_called_once()
    finaliser_for_notify.logger.info.assert_called_with("Message posted to Discord")

@patch('requests.post')
def test_post_discord_message_failure(mock_post, finaliser_for_notify):
    """Test handling failure when posting to Discord."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = requests.exceptions.RequestException("API Error")
    mock_post.return_value = mock_response
    message = "Test message"

    with pytest.raises(requests.exceptions.RequestException, match="API Error"):
        finaliser_for_notify.post_discord_message(message, DISCORD_WEBHOOK_URL)

    mock_post.assert_called_once_with(DISCORD_WEBHOOK_URL, json={"content": message})
    mock_response.raise_for_status.assert_called_once()

@patch.object(KaraokeFinalise, 'post_discord_message')
def test_post_discord_notification_sends(mock_post_msg, finaliser_for_notify):
    """Test that post_discord_notification calls post_discord_message."""
    finaliser_for_notify.skip_notifications = False
    expected_message = f"New upload: {finaliser_for_notify.youtube_url}"

    finaliser_for_notify.post_discord_notification()

    mock_post_msg.assert_called_once_with(expected_message, DISCORD_WEBHOOK_URL)

@patch.object(KaraokeFinalise, 'post_discord_message')
def test_post_discord_notification_skipped(mock_post_msg, finaliser_for_notify):
    """Test that post_discord_notification skips if flag is set."""
    finaliser_for_notify.skip_notifications = True

    finaliser_for_notify.post_discord_notification()

    mock_post_msg.assert_not_called()
    finaliser_for_notify.logger.info.assert_called_with("Skipping Discord notification as video was previously uploaded to YouTube")

@patch.object(KaraokeFinalise, 'post_discord_message')
def test_post_discord_notification_dry_run(mock_post_msg, finaliser_for_notify):
    """Test post_discord_notification dry run."""
    finaliser_for_notify.dry_run = True
    finaliser_for_notify.skip_notifications = False

    finaliser_for_notify.post_discord_notification()

    mock_post_msg.assert_not_called()
    finaliser_for_notify.logger.info.assert_called_with(
        f"DRY RUN: Would post Discord notification for youtube URL {finaliser_for_notify.youtube_url} using webhook URL: {DISCORD_WEBHOOK_URL}"
    )

# --- Gmail Authentication Tests ---

# Patch open for token write.
# Patch the from_client_secrets_file method to control the flow instance.
@patch('karaoke_gen.karaoke_finalise.karaoke_finalise.InstalledAppFlow.from_client_secrets_file')
@patch("builtins.open")
def test_authenticate_gmail_new_token(mock_open, mock_from_secrets, finaliser_for_notify, mock_google_auth, mock_gmail_service):
    """Test Gmail authentication flow when no token file exists."""
    mock_google_auth["mock_path_exists"].return_value = False # Token file doesn't exist
    mock_google_auth["mock_build"].return_value = mock_gmail_service

    # Configure mock_open side_effect to handle both secrets read and token write
    mock_token_handle = mock_open().return_value
    def open_side_effect(file, mode='r', *args, **kwargs):
        if file == GMAIL_TOKEN_FILE and mode == 'wb':
            return mock_token_handle
        # For the secrets file read, return a default mock handle
        # (the content doesn't matter as from_client_secrets_file is mocked)
        elif file == YOUTUBE_SECRETS_FILE_GMAIL and mode == 'r':
             return mock_open().return_value # Default mock handle
        # Raise error for unexpected calls
        raise ValueError(f"Unexpected call to open: {file}, {mode}")
    mock_open.side_effect = open_side_effect

    # Mock the flow instance that from_client_secrets_file returns
    mock_flow_instance = MagicMock()
    # Crucially, mock the run_local_server method ON THIS INSTANCE
    mock_flow_instance.run_local_server.return_value = mock_google_auth["mock_credentials"]
    mock_from_secrets.return_value = mock_flow_instance

    # Run the authentication
    service = finaliser_for_notify.authenticate_gmail()

    # Assertions
    # Check open was called for the token write
    mock_open.assert_any_call(GMAIL_TOKEN_FILE, "wb")
    # Ensure it wasn't called unnecessarily otherwise (implicitly checked by side_effect)

    # Check flow setup and execution
    mock_from_secrets.assert_called_once_with(
        YOUTUBE_SECRETS_FILE_GMAIL, ["https://www.googleapis.com/auth/gmail.compose"]
    )
    mock_google_auth["mock_path_exists"].assert_called_once_with(GMAIL_TOKEN_FILE)
    mock_flow_instance.run_local_server.assert_called_once_with(port=0)
    # Check token saving - use the result of the context manager __enter__
    mock_google_auth["mock_pickle_dump"].assert_called_once_with(
        mock_google_auth["mock_credentials"], mock_token_handle.__enter__()
    )
    # Check service build
    mock_google_auth["mock_build"].assert_called_once_with("gmail", "v1", credentials=mock_google_auth["mock_credentials"])
    assert service == mock_gmail_service


# No patch for open needed here for read, rely on pickle.load patch from fixture
def test_authenticate_gmail_load_valid_token(finaliser_for_notify, mock_google_auth, mock_gmail_service):
    """Test Gmail authentication using a valid existing token file."""
    mock_google_auth["mock_path_exists"].return_value = True # Token file exists
    # Configure pickle.load to return credentials when path exists
    mock_google_auth["mock_pickle_load"].side_effect = None # Remove FileNotFoundError side effect
    mock_google_auth["mock_pickle_load"].return_value = mock_google_auth["mock_credentials"]
    mock_google_auth["mock_credentials"].valid = True # Token is valid
    mock_google_auth["mock_build"].return_value = mock_gmail_service

    # Use mock_open for the read operation context manager
    with patch("builtins.open", mock_open()) as mock_pickle_open_read:
        # Call the function
        service = finaliser_for_notify.authenticate_gmail()

    # Check the file was opened for reading
    mock_pickle_open_read.assert_called_once_with(GMAIL_TOKEN_FILE, "rb")
    # REMOVE duplicate call: service = finaliser_for_notify.authenticate_gmail()

    mock_google_auth["mock_path_exists"].assert_called_once_with(GMAIL_TOKEN_FILE)
    # Ensure pickle.load was called
    mock_google_auth["mock_pickle_load"].assert_called_once()
    # mock_google_auth["mock_flow_instance"].run_local_server.assert_not_called() # REMOVED: mock_flow_instance not available here
    mock_google_auth["mock_pickle_dump"].assert_not_called() # Should not save token again
    mock_google_auth["mock_build"].assert_called_once_with("gmail", "v1", credentials=mock_google_auth["mock_credentials"])
    assert service == mock_gmail_service


# No patch for open needed for read, patch only for write
def test_authenticate_gmail_refresh_token(finaliser_for_notify, mock_google_auth, mock_gmail_service):
    """Test Gmail authentication refreshing an expired token."""
    mock_google_auth["mock_path_exists"].return_value = True # Token file exists
    # Configure pickle.load to return credentials when path exists
    mock_google_auth["mock_pickle_load"].side_effect = None # Remove FileNotFoundError side effect
    mock_google_auth["mock_pickle_load"].return_value = mock_google_auth["mock_credentials"]
    mock_google_auth["mock_credentials"].valid = False # Token is invalid
    mock_google_auth["mock_credentials"].expired = True # But expired
    mock_google_auth["mock_credentials"].refresh_token = "fake_refresh_token" # And has refresh token
    mock_google_auth["mock_build"].return_value = mock_gmail_service

    # Use mock_open for both read and write operations
    mock_file_handles = [mock_open().return_value, mock_open().return_value]
    with patch("builtins.open", side_effect=mock_file_handles) as mock_multi_open:
        # Get the refresh mock from the centrally mocked credentials
        mock_refresh = mock_google_auth["mock_credentials"].refresh
        service = finaliser_for_notify.authenticate_gmail()
        # Use ANY because the actual Request object is created internally
        mock_refresh.assert_called_once_with(ANY)

    mock_google_auth["mock_path_exists"].assert_called_once_with(GMAIL_TOKEN_FILE)
    # Ensure pickle.load was called
    mock_google_auth["mock_pickle_load"].assert_called_once()
    # Check open calls: first read ('rb'), then write ('wb')
    mock_multi_open.assert_has_calls([
        call(GMAIL_TOKEN_FILE, "rb"),
        call(GMAIL_TOKEN_FILE, "wb")
    ])
    # mock_google_auth["mock_flow_instance"].run_local_server.assert_not_called() # REMOVED: mock_flow_instance not available here
    # Ensure pickle.dump was called and the file was opened for writing
    mock_google_auth["mock_pickle_dump"].assert_called_once()
    # Assert on the write call using the mock_multi_open context manager
    assert mock_multi_open.call_args_list[-1] == call(GMAIL_TOKEN_FILE, "wb") # Check last call was write
    assert mock_google_auth["mock_pickle_dump"].call_args[0][0] == mock_google_auth["mock_credentials"] # Check correct object dumped
    mock_google_auth["mock_build"].assert_called_once_with("gmail", "v1", credentials=mock_google_auth["mock_credentials"])
    assert service == mock_gmail_service

# --- Gmail Draft Creation Tests ---

# Patch open for the template read
@patch('builtins.open', new_callable=mock_open, read_data="YT: {youtube_url}\nDB: {dropbox_url}")
@patch.object(KaraokeFinalise, 'authenticate_gmail')
# Patch MIMEText where it's used inside the karaoke_finalise module
@patch('karaoke_gen.karaoke_finalise.karaoke_finalise.MIMEText', return_value=MagicMock(spec=MIMEText))
@patch('base64.urlsafe_b64encode')
def test_draft_completion_email_success(mock_b64encode, mock_mime_text_cls, mock_auth_gmail, mock_open_template, finaliser_for_notify, mock_gmail_service):
    """Test successful email draft creation."""
    finaliser_for_notify.dry_run = False # Ensure not in dry run
    mock_auth_gmail.return_value = mock_gmail_service
    # Mock the result of as_bytes() on the MIMEText instance
    mock_mime_instance = mock_mime_text_cls.return_value
    mock_mime_instance.as_bytes.return_value = b"raw email bytes"
    mock_b64encode.return_value = b"encoded_raw_email"

    finaliser_for_notify.draft_completion_email(ARTIST, TITLE, finaliser_for_notify.youtube_url, finaliser_for_notify.brand_code_dir_sharing_link)

    mock_open_template.assert_called_once_with(EMAIL_TEMPLATE_FILE, "r")
    expected_body = f"YT: {finaliser_for_notify.youtube_url}\nDB: {finaliser_for_notify.brand_code_dir_sharing_link}"
    mock_mime_text_cls.assert_called_once_with(expected_body)

    expected_subject = f"{finaliser_for_notify.brand_code}: {ARTIST} - {TITLE}"
    assert mock_mime_instance.__setitem__.call_args_list == [call('subject', expected_subject)]

    mock_b64encode.assert_called_once_with(b"raw email bytes")
    mock_auth_gmail.assert_called_once() # Ensure auth was called
    assert finaliser_for_notify.gmail_service == mock_gmail_service # Check service was stored

    # Check the API call to create draft
    mock_gmail_service.users().drafts().create.assert_called_once_with(
        userId="me", body={"message": {"raw": "encoded_raw_email"}}
    )
    finaliser_for_notify.logger.info.assert_called_with("Email draft created with ID: draft_123")


def test_draft_completion_email_no_template_file(finaliser_for_notify):
    """Test skipping email draft if template file is not set."""
    finaliser_for_notify.email_template_file = None
    with patch.object(KaraokeFinalise, 'authenticate_gmail') as mock_auth_gmail:
        finaliser_for_notify.draft_completion_email(ARTIST, TITLE, "yt_url", "db_url")
        mock_auth_gmail.assert_not_called()
        finaliser_for_notify.logger.info.assert_called_with("Email template file not provided, skipping email draft creation.")

@patch('builtins.open', new_callable=mock_open, read_data="Template")
@patch.object(KaraokeFinalise, 'authenticate_gmail')
def test_draft_completion_email_dry_run(mock_auth_gmail, mock_open_template, finaliser_for_notify):
    """Test email draft dry run."""
    finaliser_for_notify.dry_run = True

    finaliser_for_notify.draft_completion_email(ARTIST, TITLE, finaliser_for_notify.youtube_url, finaliser_for_notify.brand_code_dir_sharing_link)

    mock_open_template.assert_called_once_with(EMAIL_TEMPLATE_FILE, "r")
    mock_auth_gmail.assert_not_called() # Auth not needed for dry run
    expected_subject = f"{finaliser_for_notify.brand_code}: {ARTIST} - {TITLE}"
    finaliser_for_notify.logger.info.assert_any_call(f"DRY RUN: Would create email draft with subject: {expected_subject}")
    # Check that the log message contains the expected dry run text for the body
    body_log_found = any("DRY RUN: Email body:" in call_args[0][0] for call_args in finaliser_for_notify.logger.info.call_args_list)
    assert body_log_found, "Expected dry run log message for email body not found."


@patch.object(KaraokeFinalise, 'draft_completion_email')
def test_test_email_template(mock_draft_email, finaliser_for_notify):
    """Test the test_email_template method calls draft_completion_email correctly."""
    finaliser_for_notify.test_email_template()

    expected_artist = "Test Artist"
    expected_title = "Test Song"
    expected_youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    expected_dropbox_url = "https://www.dropbox.com/sh/fake/folder/link"
    expected_brand_code = "TEST-0001" # Set within the test method

    # Check brand_code was set correctly before calling draft
    assert finaliser_for_notify.brand_code == expected_brand_code
    mock_draft_email.assert_called_once_with(expected_artist, expected_title, expected_youtube_url, expected_dropbox_url)
    finaliser_for_notify.logger.info.assert_called_with("Email template test complete. Check your Gmail drafts for the test email.")

def test_test_email_template_no_file(finaliser_for_notify):
    """Test test_email_template when no template file is configured."""
    finaliser_for_notify.email_template_file = None
    with patch.object(KaraokeFinalise, 'draft_completion_email') as mock_draft_email:
        finaliser_for_notify.test_email_template()
        mock_draft_email.assert_not_called()
        finaliser_for_notify.logger.error.assert_called_with("Email template file not provided. Use --email_template_file to specify the file path.")
