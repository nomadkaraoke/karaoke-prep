import pytest
import os
import zipfile
from unittest.mock import patch, MagicMock, mock_open, call

# Adjust the import path
from karaoke_prep.karaoke_finalise.karaoke_finalise import KaraokeFinalise
from .test_initialization import mock_logger, basic_finaliser, MINIMAL_CONFIG # Reuse fixtures
from .test_file_input_validation import BASE_NAME, KARAOKE_LRC, INSTRUMENTAL_FLAC # Reuse constants

# Define expected output filenames for convenience
OUTPUT_FILES_ZIP = {
    "karaoke_mp3": f"{BASE_NAME} (Karaoke).mp3",
    "karaoke_cdg": f"{BASE_NAME} (Karaoke).cdg",
    "karaoke_txt": f"{BASE_NAME} (Karaoke).txt",
    "final_karaoke_cdg_zip": f"{BASE_NAME} (Final Karaoke CDG).zip",
    "final_karaoke_txt_zip": f"{BASE_NAME} (Final Karaoke TXT).zip",
}

INPUT_FILES_ZIP = {
    "karaoke_lrc": KARAOKE_LRC,
    "instrumental_audio": INSTRUMENTAL_FLAC,
}

ARTIST = "Artist"
TITLE = "Title"
CDG_STYLES_CONFIG = {"style_name": "default"} # Dummy config

# --- CDG ZIP Creation Tests ---

@patch('os.path.isfile')
@patch('zipfile.ZipFile')
@patch('lyrics_transcriber.output.cdg.CDGGenerator')
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True) # Confirm overwrite
def test_create_cdg_zip_generate_new(mock_prompt, mock_cdg_gen_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test generating new CDG/MP3 files and zipping."""
    # Simulate no existing files
    mock_isfile.return_value = False
    basic_finaliser.cdg_styles = CDG_STYLES_CONFIG

    # Mock CDGGenerator instance and its method
    mock_generator_instance = MagicMock()
    mock_cdg_gen_cls.return_value = mock_generator_instance
    generated_cdg = "temp_cdg_file.cdg"
    generated_mp3 = "temp_mp3_file.mp3"
    generated_zip = "temp_zip_file.zip"
    mock_generator_instance.generate_cdg_from_lrc.return_value = (generated_cdg, generated_mp3, generated_zip)

    # Mock os.rename and os.path.isfile for the rename check
    # Also mock open for the LRC read inside CDGGenerator - provide more valid content
    lrc_content = "[ar:Artist]\n[ti:Title]\n[00:01.234]Line 1\n[00:02.345]Line 2"
    with patch('os.rename') as mock_rename, \
         patch('builtins.open', mock_open(read_data=lrc_content)), \
         patch('os.path.isfile', side_effect=lambda f: f == generated_zip or f == OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"]): # Make zip exist after rename

        basic_finaliser.create_cdg_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP, ARTIST, TITLE)

    # Prompt is *not* called because isfile returns False initially for the zip
    mock_prompt.assert_not_called() # Should not be called as zip doesn't exist initially
    mock_cdg_gen_cls.assert_called_once_with(output_dir=os.getcwd(), logger=basic_finaliser.logger)
    mock_generator_instance.generate_cdg_from_lrc.assert_called_once_with(
        lrc_file=INPUT_FILES_ZIP["karaoke_lrc"],
        audio_file=INPUT_FILES_ZIP["instrumental_audio"],
        title=TITLE,
        artist=ARTIST,
        cdg_styles=CDG_STYLES_CONFIG,
    )
    mock_rename.assert_called_once_with(generated_zip, OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"])
    # Check extraction call
    # The mock_zipfile is called twice: once for 'w' (implicitly by generator rename) and once for 'r' (explicitly for extraction)
    # We need to ensure the mock handles this. Let's check the 'r' call specifically.
    read_call_found = False
    for c in mock_zipfile.call_args_list:
        if c == call(OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"], "r"):
            read_call_found = True
            break
    assert read_call_found, f"Expected call ZipFile('{OUTPUT_FILES_ZIP['final_karaoke_cdg_zip']}', 'r') not found"

    # Check extractall was called on the instance returned by the 'r' call context manager
    # This requires a more sophisticated mock if the instance differs between calls.
    # Assuming the default MagicMock behavior works here for simplicity.
    zip_instance_mock = mock_zipfile.return_value.__enter__.return_value
    # Check if extractall was called *at least once* (could be called after 'w' or 'r')
    zip_instance_mock.extractall.assert_called()


@patch('os.path.isfile')
@patch('zipfile.ZipFile')
@patch('lyrics_transcriber.output.cdg.CDGGenerator')
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True) # Confirm overwrite
def test_create_cdg_zip_use_existing_mp3_cdg(mock_prompt, mock_cdg_gen_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test creating ZIP from existing MP3 and CDG files."""
    # Simulate existing MP3 and CDG, but not the final ZIP initially
    mock_isfile.side_effect = lambda f: f == OUTPUT_FILES_ZIP["karaoke_mp3"] or \
                                        f == OUTPUT_FILES_ZIP["karaoke_cdg"] or \
                                        f == OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"] # Make zip exist for overwrite check and extraction

    basic_finaliser.create_cdg_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP, ARTIST, TITLE)

    mock_prompt.assert_called_once() # Overwrite prompt
    mock_cdg_gen_cls.assert_not_called() # Should not generate
    # Check zip creation call
    mock_zipfile.assert_any_call(OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"], "w")
    zip_instance_mock = mock_zipfile.return_value.__enter__.return_value
    zip_instance_mock.write.assert_has_calls([
        call(OUTPUT_FILES_ZIP["karaoke_mp3"], os.path.basename(OUTPUT_FILES_ZIP["karaoke_mp3"])),
        call(OUTPUT_FILES_ZIP["karaoke_cdg"], os.path.basename(OUTPUT_FILES_ZIP["karaoke_cdg"])),
    ], any_order=True)
    # Check extraction call
    # Check the 'r' call specifically
    read_call_found = False
    for c in mock_zipfile.call_args_list:
        if c == call(OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"], "r"):
            read_call_found = True
            break
    assert read_call_found, f"Expected call ZipFile('{OUTPUT_FILES_ZIP['final_karaoke_cdg_zip']}', 'r') not found"
    # Check extractall was called on the instance returned by the 'r' call context manager
    zip_instance_mock = mock_zipfile.return_value.__enter__.return_value
    zip_instance_mock.extractall.assert_called()


@patch('os.path.isfile', return_value=True) # ZIP exists
@patch('zipfile.ZipFile')
@patch('lyrics_transcriber.output.cdg.CDGGenerator')
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=False) # Skip overwrite
def test_create_cdg_zip_skip_overwrite(mock_prompt, mock_cdg_gen_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test skipping CDG ZIP creation if user chooses not to overwrite."""
    basic_finaliser.create_cdg_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP, ARTIST, TITLE)

    mock_prompt.assert_called_once()
    mock_cdg_gen_cls.assert_not_called()
    mock_zipfile.assert_not_called() # No zip creation or extraction

def test_create_cdg_zip_missing_styles(basic_finaliser):
    """Test error raised if cdg_styles is missing."""
    basic_finaliser.cdg_styles = None
    with patch('os.path.isfile', return_value=False), \
         pytest.raises(ValueError, match="CDG styles configuration is required"):
        basic_finaliser.create_cdg_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP, ARTIST, TITLE)

@patch('os.path.isfile', return_value=False) # No existing files
@patch('zipfile.ZipFile')
@patch('lyrics_transcriber.output.cdg.CDGGenerator')
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True)
def test_create_cdg_zip_generation_fails_to_create_zip(mock_prompt, mock_cdg_gen_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test error if CDGGenerator runs but zip isn't found afterwards."""
    basic_finaliser.cdg_styles = CDG_STYLES_CONFIG
    mock_generator_instance = MagicMock()
    mock_cdg_gen_cls.return_value = mock_generator_instance
    # Simulate generator returning paths but the zip file doesn't actually appear
    mock_generator_instance.generate_cdg_from_lrc.return_value = ("file.cdg", "file.mp3", "temp.zip")

    # Mock open for the LRC read inside CDGGenerator
    with patch('os.rename'), \
         patch('builtins.open', mock_open(read_data="[ti:Title]\n[00:01.00]Test")), \
         patch('os.path.isfile', return_value=False), \
         patch('os.listdir', return_value=[]), \
         pytest.raises(Exception): # Remove match
        basic_finaliser.create_cdg_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP, ARTIST, TITLE)


# --- TXT ZIP Creation Tests ---

@patch('os.path.isfile')
@patch('zipfile.ZipFile')
# Patch the converter where it's imported in the target module
@patch('karaoke_prep.karaoke_finalise.karaoke_finalise.LyricsConverter')
@patch('builtins.open', new_callable=mock_open) # For the TXT write
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True) # Confirm overwrite
def test_create_txt_zip_generate_new(mock_prompt, mock_open_txt_write, mock_lyrics_converter_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test generating new TXT file and zipping."""
    # Simulate no existing TXT zip, but MP3 exists (assumed from CDG step)
    mock_isfile.side_effect = lambda f: f == OUTPUT_FILES_ZIP["karaoke_mp3"] or f == OUTPUT_FILES_ZIP["final_karaoke_txt_zip"]

    # Mock LyricsConverter instance and its convert_file method
    mock_converter_instance = MagicMock()
    mock_lyrics_converter_cls.return_value = mock_converter_instance
    converted_text = "[00:01.00]Line 1\n[00:02.00]Line 2"
    mock_converter_instance.convert_file.return_value = converted_text

    basic_finaliser.create_txt_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP)

    # Prompt is called because isfile returns True for the zip
    mock_prompt.assert_called_once_with(f"Found existing TXT ZIP file: {OUTPUT_FILES_ZIP['final_karaoke_txt_zip']}. Overwrite (y) or skip (n)?")
    mock_lyrics_converter_cls.assert_called_once_with(output_format="txt", filepath=INPUT_FILES_ZIP["karaoke_lrc"])
    mock_converter_instance.convert_file.assert_called_once()
    # Check TXT file write
    mock_open_txt_write.assert_called_once_with(OUTPUT_FILES_ZIP["karaoke_txt"], "w")
    mock_open_txt_write().write.assert_called_once_with(converted_text)
    # Check zip creation
    mock_zipfile.assert_called_once_with(OUTPUT_FILES_ZIP["final_karaoke_txt_zip"], "w")
    zip_instance_mock = mock_zipfile.return_value.__enter__.return_value
    zip_instance_mock.write.assert_has_calls([
        call(OUTPUT_FILES_ZIP["karaoke_mp3"], os.path.basename(OUTPUT_FILES_ZIP["karaoke_mp3"])),
        call(OUTPUT_FILES_ZIP["karaoke_txt"], os.path.basename(OUTPUT_FILES_ZIP["karaoke_txt"])),
    ], any_order=True)

@patch('os.path.isfile', return_value=True) # ZIP exists
@patch('zipfile.ZipFile')
@patch('lyrics_converter.LyricsConverter')
@patch('builtins.open', new_callable=mock_open)
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=False) # Skip overwrite
def test_create_txt_zip_skip_overwrite(mock_prompt, mock_open_file, mock_lyrics_converter_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test skipping TXT ZIP creation if user chooses not to overwrite."""
    basic_finaliser.create_txt_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP)

    mock_prompt.assert_called_once()
    mock_lyrics_converter_cls.assert_not_called()
    mock_open_file.assert_not_called()
    mock_zipfile.assert_not_called()

@patch('os.path.isfile')
@patch('zipfile.ZipFile', side_effect=Exception("Zip creation failed")) # Simulate zip error
@patch('karaoke_prep.karaoke_finalise.karaoke_finalise.LyricsConverter')
@patch('builtins.open', new_callable=mock_open) # For the TXT write
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True)
def test_create_txt_zip_creation_fails(mock_prompt, mock_open_txt_write, mock_lyrics_converter_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test handling exception during TXT ZIP creation."""
    mock_isfile.return_value = False # No existing zip
    mock_converter_instance = MagicMock()
    mock_lyrics_converter_cls.return_value = mock_converter_instance
    mock_converter_instance.convert_file.return_value = "text" # Mock the conversion result

    with pytest.raises(Exception): # Remove match
         basic_finaliser.create_txt_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP)

    # Ensure previous steps were attempted
    mock_lyrics_converter_cls.assert_called_once()
    mock_converter_instance.convert_file.assert_called_once() # Ensure conversion was attempted
    mock_open_txt_write.assert_called_once_with(OUTPUT_FILES_ZIP["karaoke_txt"], "w") # Ensure TXT write was attempted
    mock_zipfile.assert_called_once() # Attempted to create zip
