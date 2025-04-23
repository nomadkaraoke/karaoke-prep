import pytest
import os
import json
from unittest.mock import patch, MagicMock, mock_open, call

# Adjust the import paths to use the refactored classes
from karaoke_prep.karaoke_finalise.file_manager import FileManager
from karaoke_prep.karaoke_finalise.user_interface import UserInterface
from .test_initialization import mock_logger, MINIMAL_CONFIG  # Reuse fixtures

# Define constants for testing
BASE_NAME = "Artist - Title"
ARTIST = "Artist"
TITLE = "Title"
WITH_VOCALS_MOV = f"{BASE_NAME} (With Vocals).mov"
WITH_VOCALS_MP4 = f"{BASE_NAME} (With Vocals).mp4"
INSTRUMENTAL_FLAC = f"{BASE_NAME} (Instrumental).flac"
INSTRUMENTAL_MP3 = f"{BASE_NAME} (Instrumental).mp3"
INSTRUMENTAL_WAV = f"{BASE_NAME} (Instrumental).wav"
TITLE_MOV = f"{BASE_NAME} (Title).mov"
TITLE_JPG = f"{BASE_NAME} (Title).jpg"
END_MOV = f"{BASE_NAME} (End).mov"
END_JPG = f"{BASE_NAME} (End).jpg"
KARAOKE_LRC = f"{BASE_NAME} (Karaoke).lrc"
KARAOKE_MOV_MISNAMED = f"{BASE_NAME} (Karaoke).mov"

@pytest.fixture
def file_manager(mock_logger):
    """Fixture for a FileManager instance."""
    return FileManager(
        logger=mock_logger,
        dry_run=False,
        brand_prefix=None,
        organised_dir=None,
        public_share_dir=None,
        keep_brand_code=False
    )

@pytest.fixture
def ui_manager(mock_logger):
    """Fixture for a UserInterface instance."""
    return UserInterface(
        logger=mock_logger,
        non_interactive=False
    )

# --- File Existence and Preparation Tests ---

@patch('os.path.isfile')
def test_check_input_files_exist_success(mock_isfile, file_manager):
    """Test check_input_files_exist succeeds when all required files exist."""
    mock_isfile.return_value = True
    # Add required suffixes for testing
    file_manager.suffixes = {
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "with_vocals_mov": " (With Vocals).mov",
        "karaoke_lrc": " (Karaoke).lrc",
        "end_mov": " (End).mov",
        "end_jpg": " (End).jpg",
    }

    input_files = file_manager.check_input_files_exist(BASE_NAME, WITH_VOCALS_MOV, INSTRUMENTAL_FLAC, enable_cdg=True, enable_txt=False)

    expected_files = {
        "title_mov": TITLE_MOV,
        "title_jpg": TITLE_JPG,
        "instrumental_audio": INSTRUMENTAL_FLAC,
        "with_vocals_mov": WITH_VOCALS_MOV,
        "karaoke_lrc": KARAOKE_LRC,
        "end_mov": END_MOV, # Optional, mocked as existing
        "end_jpg": END_JPG, # Optional, mocked as existing
    }
    assert input_files == expected_files
    mock_isfile.assert_has_calls([
        call(TITLE_MOV),
        call(TITLE_JPG),
        call(INSTRUMENTAL_FLAC),
        call(WITH_VOCALS_MOV),
        call(KARAOKE_LRC),
        call(END_MOV), # Checks optional file
        call(END_JPG), # Checks optional file
    ], any_order=True)

@patch('os.path.isfile')
def test_check_input_files_exist_missing_required(mock_isfile, file_manager):
    """Test check_input_files_exist raises exception for missing required file."""
    # Make title_mov missing
    mock_isfile.side_effect = lambda f: f != TITLE_MOV
    # Add required suffixes for testing
    file_manager.suffixes = {
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "with_vocals_mov": " (With Vocals).mov",
        "karaoke_lrc": " (Karaoke).lrc",
        "end_mov": " (End).mov",
        "end_jpg": " (End).jpg",
    }

    # Test should raise an exception
    with pytest.raises(Exception):
        file_manager.check_input_files_exist(BASE_NAME, WITH_VOCALS_MOV, INSTRUMENTAL_FLAC, enable_cdg=False, enable_txt=False)

@patch('os.path.isfile')
def test_check_input_files_exist_missing_optional(mock_isfile, file_manager):
    """Test check_input_files_exist succeeds when optional files are missing."""
    # Make optional files missing, required files exist
    mock_isfile.side_effect = lambda f: f not in [END_MOV, END_JPG]
    # Add required suffixes for testing
    file_manager.suffixes = {
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "with_vocals_mov": " (With Vocals).mov",
        "karaoke_lrc": " (Karaoke).lrc",
        "end_mov": " (End).mov",
        "end_jpg": " (End).jpg",
    }

    input_files = file_manager.check_input_files_exist(BASE_NAME, WITH_VOCALS_MOV, INSTRUMENTAL_FLAC, enable_cdg=False, enable_txt=False)

    expected_files = {
        "title_mov": TITLE_MOV,
        "title_jpg": TITLE_JPG,
        "instrumental_audio": INSTRUMENTAL_FLAC,
        "with_vocals_mov": WITH_VOCALS_MOV,
        # The code adds optional files even if missing, just logs it. Test reflects this.
        "end_mov": END_MOV,
        "end_jpg": END_JPG,
    }
    assert input_files == expected_files
    # Ensure optional files were checked
    mock_isfile.assert_has_calls([call(END_MOV), call(END_JPG)], any_order=True)

@patch('os.path.isfile')
def test_check_input_files_exist_lrc_required(mock_isfile, file_manager):
    """Test check_input_files_exist requires LRC when CDG or TXT enabled."""
    mock_isfile.side_effect = lambda f: f != KARAOKE_LRC # Make LRC missing
    # Add required suffixes for testing
    file_manager.suffixes = {
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "with_vocals_mov": " (With Vocals).mov",
        "karaoke_lrc": " (Karaoke).lrc",
        "end_mov": " (End).mov",
        "end_jpg": " (End).jpg",
    }

    # Test CDG enabled
    with pytest.raises(Exception):
        file_manager.check_input_files_exist(BASE_NAME, WITH_VOCALS_MOV, INSTRUMENTAL_FLAC, enable_cdg=True, enable_txt=False)

    # Test TXT enabled
    with pytest.raises(Exception):
        file_manager.check_input_files_exist(BASE_NAME, WITH_VOCALS_MOV, INSTRUMENTAL_FLAC, enable_cdg=False, enable_txt=True)

def test_prepare_output_filenames(file_manager):
    """Test prepare_output_filenames generates correct names."""
    # Add expected suffixes
    file_manager.suffixes = {
        "karaoke_mp4": " (Karaoke).mp4",
        "karaoke_mp3": " (Karaoke).mp3",
        "karaoke_cdg": " (Karaoke).cdg",
        "with_vocals_mp4": " (With Vocals).mp4",
        "final_karaoke_lossless_mp4": " (Final Karaoke Lossless 4k).mp4",
        "final_karaoke_lossless_mkv": " (Final Karaoke Lossless 4k).mkv",
        "final_karaoke_lossy_mp4": " (Final Karaoke Lossy 4k).mp4",
        "final_karaoke_lossy_720p_mp4": " (Final Karaoke Lossy 720p).mp4",
        "final_karaoke_cdg_zip": " (Final Karaoke CDG).zip",
        "karaoke_txt": " (Karaoke).txt",
        "final_karaoke_txt_zip": " (Final Karaoke TXT).zip",
    }

    # Call with both CDG and TXT enabled
    output_files = file_manager.prepare_output_filenames(BASE_NAME, enable_cdg=True, enable_txt=True)

    expected_suffixes = {
        "karaoke_mp4": " (Karaoke).mp4",
        "karaoke_mp3": " (Karaoke).mp3",
        "karaoke_cdg": " (Karaoke).cdg",
        "with_vocals_mp4": " (With Vocals).mp4",
        "final_karaoke_lossless_mp4": " (Final Karaoke Lossless 4k).mp4",
        "final_karaoke_lossless_mkv": " (Final Karaoke Lossless 4k).mkv",
        "final_karaoke_lossy_mp4": " (Final Karaoke Lossy 4k).mp4",
        "final_karaoke_lossy_720p_mp4": " (Final Karaoke Lossy 720p).mp4",
        "final_karaoke_cdg_zip": " (Final Karaoke CDG).zip", # Enabled
        "karaoke_txt": " (Karaoke).txt", # Enabled
        "final_karaoke_txt_zip": " (Final Karaoke TXT).zip", # Enabled
    }

    assert len(output_files) == len(expected_suffixes)
    for key, suffix in expected_suffixes.items():
        assert key in output_files
        assert output_files[key] == f"{BASE_NAME}{suffix}"

def test_prepare_output_filenames_cdg_txt_disabled(file_manager):
    """Test prepare_output_filenames excludes CDG/TXT when disabled."""
    # Add expected suffixes
    file_manager.suffixes = {
        "karaoke_mp4": " (Karaoke).mp4",
        "karaoke_mp3": " (Karaoke).mp3",
        "karaoke_cdg": " (Karaoke).cdg",
        "with_vocals_mp4": " (With Vocals).mp4",
        "final_karaoke_lossless_mp4": " (Final Karaoke Lossless 4k).mp4",
        "final_karaoke_lossless_mkv": " (Final Karaoke Lossless 4k).mkv",
        "final_karaoke_lossy_mp4": " (Final Karaoke Lossy 4k).mp4",
        "final_karaoke_lossy_720p_mp4": " (Final Karaoke Lossy 720p).mp4",
        "final_karaoke_cdg_zip": " (Final Karaoke CDG).zip",
        "karaoke_txt": " (Karaoke).txt",
        "final_karaoke_txt_zip": " (Final Karaoke TXT).zip",
    }

    # Call with both CDG and TXT disabled
    output_files = file_manager.prepare_output_filenames(BASE_NAME, enable_cdg=False, enable_txt=False)

    assert "final_karaoke_cdg_zip" not in output_files
    assert "karaoke_txt" not in output_files
    assert "final_karaoke_txt_zip" not in output_files


# --- Feature Validation Tests ---

@patch('os.path.isfile')
@patch('os.path.isdir')
@patch('builtins.open', new_callable=mock_open, read_data='{"installed": {"client_id": "test"}}')
@patch('json.load')
@patch('builtins.input', return_value='y') # Auto-confirm prompt
def test_validate_input_parameters_all_features_enabled(mock_input, mock_json_load, mock_open_file, mock_isdir, mock_isfile, ui_manager):
    """Test validation enables all features with correct inputs."""
    mock_isfile.return_value = True # All files exist
    mock_isdir.return_value = True # All dirs exist

    features = ui_manager.validate_input_parameters_for_features(
        youtube_client_secrets_file="secrets.json",
        youtube_description_file="desc.txt",
        discord_webhook_url="https://discord.com/api/webhooks/123/abc",
        brand_prefix="TEST",
        organised_dir="/path/to/organised",
        public_share_dir="/path/to/public",
        rclone_destination="remote:backup",
        enable_cdg=True,
        enable_txt=True
    )

    assert features["youtube_upload_enabled"]
    assert features["discord_notication_enabled"]
    assert features["folder_organisation_enabled"]
    assert features["public_share_copy_enabled"]
    assert features["public_share_rclone_enabled"]
    mock_isfile.assert_any_call("secrets.json")
    mock_isfile.assert_any_call("desc.txt")
    mock_open_file.assert_called_once_with("secrets.json", "r")
    mock_json_load.assert_called_once()
    mock_isdir.assert_any_call("/path/to/organised")
    mock_isdir.assert_any_call("/path/to/public")
    mock_isdir.assert_any_call("/path/to/public/MP4")
    mock_isdir.assert_any_call("/path/to/public/CDG")
    # ui_manager is non-interactive by default, so prompt is not called
    mock_input.assert_not_called()

@patch('os.path.isfile', return_value=False)
@patch('builtins.input', return_value='y')
def test_validate_youtube_secrets_missing(mock_input, mock_isfile, ui_manager):
    """Test validation fails if YouTube secrets file is missing."""
    with pytest.raises(Exception, match="YouTube client secrets file does not exist"):
        ui_manager.validate_input_parameters_for_features(
            youtube_client_secrets_file="secrets.json",
            youtube_description_file="desc.txt"
        )

@patch('os.path.isfile', return_value=True)
@patch('builtins.open', new_callable=mock_open, read_data='invalid json')
@patch('json.load', side_effect=json.JSONDecodeError("Expecting value", "invalid json", 0))
@patch('builtins.input', return_value='y')
def test_validate_youtube_secrets_invalid_json(mock_input, mock_json_load, mock_open_file, mock_isfile, ui_manager):
    """Test validation fails if YouTube secrets file is invalid JSON."""
    with pytest.raises(Exception, match="YouTube client secrets file is not valid JSON"):
        ui_manager.validate_input_parameters_for_features(
            youtube_client_secrets_file="secrets.json",
            youtube_description_file="desc.txt"
        )

@patch('builtins.input', return_value='y')
def test_validate_discord_url_invalid(mock_input, ui_manager):
    """Test validation fails with invalid Discord webhook URL."""
    with pytest.raises(Exception, match="Discord webhook URL is not valid"):
        ui_manager.validate_input_parameters_for_features(
            discord_webhook_url="http://invalid.com"
        )

@patch('os.path.isdir', return_value=False)
@patch('builtins.input', return_value='y')
def test_validate_organised_dir_missing(mock_input, mock_isdir, ui_manager):
    """Test validation fails if organised_dir is missing."""
    with pytest.raises(Exception, match="Target directory does not exist"):
        ui_manager.validate_input_parameters_for_features(
            brand_prefix="TEST",
            organised_dir="/missing/dir"
        )

@patch('os.path.isdir')
@patch('builtins.input', return_value='y')
def test_validate_public_share_dir_missing_subdirs(mock_input, mock_isdir, ui_manager):
    """Test validation fails if public_share_dir is missing subdirectories."""
    # Simulate missing MP4 subdir
    mock_isdir.side_effect = lambda p: p != "/public/share/MP4"

    with pytest.raises(Exception, match="Public share directory does not contain MP4 subdirectory"):
        ui_manager.validate_input_parameters_for_features(
            public_share_dir="/public/share"
        )

    # Simulate missing CDG subdir
    mock_isdir.side_effect = lambda p: p != "/public/share/CDG"
    with pytest.raises(Exception, match="Public share directory does not contain CDG subdirectory"):
        ui_manager.validate_input_parameters_for_features(
            public_share_dir="/public/share"
        )

@patch('builtins.input', return_value='n') # User rejects confirmation
def test_validate_user_rejects_confirmation(mock_input, ui_manager):
    """Test validation fails if user rejects the confirmation prompt."""
    # Enable prompts for this test
    ui_manager.non_interactive = False
    
    # Setup minimal valid config for some features to be enabled
    with pytest.raises(Exception):
        ui_manager.validate_input_parameters_for_features(
            rclone_destination="remote:dest"
        )
    mock_input.assert_called_once() # Ensure prompt was actually called

# --- File Finding/Choosing Tests ---

@patch('os.listdir')
def test_find_with_vocals_file_mov_exists(mock_listdir, file_manager, ui_manager):
    """Test finding a .mov with vocals file."""
    mock_listdir.return_value = ["other.txt", WITH_VOCALS_MOV, TITLE_MOV]
    # Add all required suffixes, not just the one being tested
    file_manager.suffixes = {
        "with_vocals_mov": " (With Vocals).mov",
        "with_vocals_mp4": " (With Vocals).mp4",
        "with_vocals_mkv": " (With Vocals).mkv",
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "karaoke_lrc": " (Karaoke).lrc"
    }
    
    found_file = file_manager.find_with_vocals_file(user_interface=ui_manager)
    assert found_file == WITH_VOCALS_MOV

@patch('os.listdir')
def test_find_with_vocals_file_mp4_exists(mock_listdir, file_manager, ui_manager):
    """Test finding a .mp4 with vocals file."""
    mock_listdir.return_value = ["other.txt", WITH_VOCALS_MP4, TITLE_MOV]
    # Add all required suffixes, not just the one being tested
    file_manager.suffixes = {
        "with_vocals_mov": " (With Vocals).mov",
        "with_vocals_mp4": " (With Vocals).mp4",
        "with_vocals_mkv": " (With Vocals).mkv",
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "karaoke_lrc": " (Karaoke).lrc"
    }
    
    found_file = file_manager.find_with_vocals_file(user_interface=ui_manager)
    assert found_file == WITH_VOCALS_MP4

@patch('os.listdir')
@patch('os.rename')
@patch('builtins.input', return_value='y') # Confirm rename
def test_find_with_vocals_file_rename_karaoke_mov(mock_input, mock_rename, mock_listdir, file_manager, ui_manager):
    """Test renaming a misnamed (Karaoke).mov file."""
    mock_listdir.return_value = ["other.txt", KARAOKE_MOV_MISNAMED, TITLE_MOV]
    # Add all required suffixes
    file_manager.suffixes = {
        "with_vocals_mov": " (With Vocals).mov",
        "with_vocals_mp4": " (With Vocals).mp4",
        "with_vocals_mkv": " (With Vocals).mkv",
        "karaoke_mov": " (Karaoke).mov",
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "karaoke_lrc": " (Karaoke).lrc"
    }
    ui_manager.non_interactive = False # Enable prompts for this test
    
    found_file = file_manager.find_with_vocals_file(user_interface=ui_manager)
    assert found_file == WITH_VOCALS_MOV
    mock_rename.assert_called_once_with(KARAOKE_MOV_MISNAMED, WITH_VOCALS_MOV)
    mock_input.assert_called_once() # Ensure prompt was called

@patch('os.listdir')
@patch('os.rename')
@patch('builtins.input', return_value='n') # Reject rename
def test_find_with_vocals_file_reject_rename(mock_input, mock_rename, mock_listdir, file_manager, ui_manager):
    """Test exception raised if user rejects renaming."""
    mock_listdir.return_value = ["other.txt", KARAOKE_MOV_MISNAMED, TITLE_MOV]
    # Add all required suffixes
    file_manager.suffixes = {
        "with_vocals_mov": " (With Vocals).mov",
        "with_vocals_mp4": " (With Vocals).mp4",
        "with_vocals_mkv": " (With Vocals).mkv",
        "karaoke_mov": " (Karaoke).mov",
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "karaoke_lrc": " (Karaoke).lrc"
    }
    ui_manager.non_interactive = False # Enable prompts for this test
    ui_manager.prompt_user_confirmation_or_raise_exception = MagicMock(side_effect=Exception("User rejected rename"))
    
    with pytest.raises(Exception):
        file_manager.find_with_vocals_file(user_interface=ui_manager)
    mock_rename.assert_not_called()
    # Ensure the confirmation was called
    ui_manager.prompt_user_confirmation_or_raise_exception.assert_called_once()

@patch('os.listdir', return_value=["other.txt", TITLE_MOV])
def test_find_with_vocals_file_not_found(mock_listdir, file_manager, ui_manager):
    """Test exception raised if no suitable file is found."""
    # Add all required suffixes
    file_manager.suffixes = {
        "with_vocals_mov": " (With Vocals).mov",
        "with_vocals_mp4": " (With Vocals).mp4",
        "with_vocals_mkv": " (With Vocals).mkv",
        "title_mov": " (Title).mov",
        "title_jpg": " (Title).jpg",
        "karaoke_lrc": " (Karaoke).lrc"
    }
    
    with pytest.raises(Exception, match="No suitable files found for processing"):
        file_manager.find_with_vocals_file(user_interface=ui_manager)

@patch('os.listdir')
def test_choose_instrumental_audio_file_only_flac(mock_listdir, file_manager, ui_manager):
    """Test choosing the only instrumental file (FLAC)."""
    mock_listdir.return_value = [INSTRUMENTAL_FLAC, "other.txt"]
    
    chosen_file = file_manager.choose_instrumental_audio_file(BASE_NAME, non_interactive=False)
    assert chosen_file == INSTRUMENTAL_FLAC

@patch('os.listdir')
def test_choose_instrumental_audio_file_prefer_flac(mock_listdir, file_manager, ui_manager):
    """Test preferring FLAC over MP3 and WAV."""
    mock_listdir.return_value = [INSTRUMENTAL_MP3, INSTRUMENTAL_FLAC, INSTRUMENTAL_WAV, "other.txt"]
    
    chosen_file = file_manager.choose_instrumental_audio_file(BASE_NAME, non_interactive=False)
    assert chosen_file == INSTRUMENTAL_FLAC

@patch('os.listdir')
def test_choose_instrumental_audio_file_prefer_wav_over_mp3(mock_listdir, file_manager, ui_manager):
    """Test preferring WAV over MP3 when FLAC is absent."""
    mock_listdir.return_value = [INSTRUMENTAL_MP3, INSTRUMENTAL_WAV, "other.txt"]
    
    chosen_file = file_manager.choose_instrumental_audio_file(BASE_NAME, non_interactive=False)
    assert chosen_file == INSTRUMENTAL_WAV

@patch('os.listdir')
@patch('builtins.input', return_value='2') # Choose second option
def test_choose_instrumental_audio_file_multiple_prompt(mock_input, mock_listdir, file_manager, ui_manager):
    """Test prompting user when multiple valid files exist."""
    files = [f"{BASE_NAME} (Instrumental Mix 1).flac", f"{BASE_NAME} (Instrumental Mix 2).flac"]
    mock_listdir.return_value = files
    # Sort order expected by the prompt (reverse alphabetical)
    expected_prompt_order = sorted(files, reverse=True)
    ui_manager.prompt_user_choice = MagicMock(return_value=expected_prompt_order[1])

    chosen_file = file_manager.choose_instrumental_audio_file(BASE_NAME, non_interactive=False, user_interface=ui_manager)

    assert chosen_file == expected_prompt_order[1]
    ui_manager.prompt_user_choice.assert_called_once()

@patch('os.listdir')
def test_choose_instrumental_audio_file_multiple_non_interactive(mock_listdir, file_manager):
    """Test choosing the first option non-interactively."""
    files = [f"{BASE_NAME} (Instrumental Mix 1).flac", f"{BASE_NAME} (Instrumental Mix 2).flac"]
    mock_listdir.return_value = files
    # Non-interactive chooses the first item from the *filtered* list before sorting
    expected_choice = files[0]

    chosen_file = file_manager.choose_instrumental_audio_file(BASE_NAME, non_interactive=True)
    assert chosen_file == expected_choice

@patch('os.listdir', return_value=["other.txt"])
def test_choose_instrumental_audio_file_not_found(mock_listdir, file_manager):
    """Test exception raised if no instrumental files are found."""
    with pytest.raises(Exception, match="No instrumental audio files found"):
        file_manager.choose_instrumental_audio_file(BASE_NAME, non_interactive=False)

# --- Name Extraction Tests ---

def test_get_names_from_withvocals_mov(file_manager):
    """Test extracting names from a .mov file."""
    file_manager.suffixes = {"with_vocals_mov": " (With Vocals).mov"}
    
    base, artist, title = file_manager.get_names_from_withvocals(WITH_VOCALS_MOV)
    assert base == BASE_NAME
    assert artist == "Artist"
    assert title == "Title"

def test_get_names_from_withvocals_mp4(file_manager):
    """Test extracting names from a .mp4 file."""
    file_manager.suffixes = {"with_vocals_mp4": " (With Vocals).mp4"}
    
    base, artist, title = file_manager.get_names_from_withvocals(WITH_VOCALS_MP4)
    assert base == BASE_NAME
    assert artist == "Artist"
    assert title == "Title"

def test_get_names_from_withvocals_mkv(file_manager):
    """Test extracting names from a .mkv file."""
    mkv_file = f"{BASE_NAME} (With Vocals).mkv"
    file_manager.suffixes = {"with_vocals_mkv": " (With Vocals).mkv"}
    
    base, artist, title = file_manager.get_names_from_withvocals(mkv_file)
    assert base == BASE_NAME
    assert artist == "Artist"
    assert title == "Title"

def test_get_names_from_withvocals_no_suffix(file_manager):
    """Test extracting names when suffix is missing (falls back to removing extension)."""
    file_no_suffix = f"{BASE_NAME}.mov"
    
    base, artist, title = file_manager.get_names_from_withvocals(file_no_suffix)
    assert base == BASE_NAME
    assert artist == "Artist"
    assert title == "Title"

def test_get_names_from_withvocals_complex_title(file_manager):
    """Test extracting names with complex title including hyphens."""
    complex_base = "Some Artist - A Song - With Hyphens - And Stuff"
    complex_file = f"{complex_base} (With Vocals).mp4"
    file_manager.suffixes = {"with_vocals_mp4": " (With Vocals).mp4"}
    
    base, artist, title = file_manager.get_names_from_withvocals(complex_file)
    assert base == complex_base
    assert artist == "Some Artist"
    assert title == "A Song - With Hyphens - And Stuff"
