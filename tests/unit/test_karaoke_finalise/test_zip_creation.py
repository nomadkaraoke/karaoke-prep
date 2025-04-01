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
    with patch('os.rename') as mock_rename, \
         patch('os.path.isfile', side_effect=lambda f: f == generated_zip or f == OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"]): # Make zip exist after rename

        basic_finaliser.create_cdg_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP, ARTIST, TITLE)

    mock_prompt.assert_called_once_with(f"Found existing CDG ZIP file: {OUTPUT_FILES_ZIP['final_karaoke_cdg_zip']}. Overwrite (y) or skip (n)?")
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
    mock_zipfile.assert_any_call(OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"], "r")
    zip_instance_mock = mock_zipfile.return_value.__enter__.return_value
    zip_instance_mock.extractall.assert_called_once_with()


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
    mock_zipfile.assert_any_call(OUTPUT_FILES_ZIP["final_karaoke_cdg_zip"], "r")
    zip_instance_mock_read = mock_zipfile.return_value.__enter__.return_value
    zip_instance_mock_read.extractall.assert_called_once_with()


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

    with patch('os.rename'), \
         patch('os.path.isfile', return_value=False), \
         patch('os.listdir', return_value=[]), \
         pytest.raises(Exception, match="Failed to create CDG ZIP file"):
        basic_finaliser.create_cdg_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP, ARTIST, TITLE)


# --- TXT ZIP Creation Tests ---

@patch('os.path.isfile')
@patch('zipfile.ZipFile')
@patch('lyrics_converter.LyricsConverter')
@patch('builtins.open', new_callable=mock_open)
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True) # Confirm overwrite
def test_create_txt_zip_generate_new(mock_prompt, mock_open_file, mock_lyrics_converter_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test generating new TXT file and zipping."""
    # Simulate no existing TXT zip, but MP3 exists (assumed from CDG step)
    mock_isfile.side_effect = lambda f: f == OUTPUT_FILES_ZIP["karaoke_mp3"] or f == OUTPUT_FILES_ZIP["final_karaoke_txt_zip"]

    # Mock LyricsConverter
    mock_converter_instance = MagicMock()
    mock_lyrics_converter_cls.return_value = mock_converter_instance
    converted_text = "[00:01.00]Line 1\n[00:02.00]Line 2"
    mock_converter_instance.convert_file.return_value = converted_text

    basic_finaliser.create_txt_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP)

    mock_prompt.assert_called_once_with(f"Found existing TXT ZIP file: {OUTPUT_FILES_ZIP['final_karaoke_txt_zip']}. Overwrite (y) or skip (n)?")
    mock_lyrics_converter_cls.assert_called_once_with(output_format="txt", filepath=INPUT_FILES_ZIP["karaoke_lrc"])
    mock_converter_instance.convert_file.assert_called_once()
    # Check TXT file write
    mock_open_file.assert_called_once_with(OUTPUT_FILES_ZIP["karaoke_txt"], "w")
    mock_open_file().write.assert_called_once_with(converted_text)
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
@patch('lyrics_converter.LyricsConverter')
@patch('builtins.open', new_callable=mock_open)
@patch.object(KaraokeFinalise, 'prompt_user_bool', return_value=True)
def test_create_txt_zip_creation_fails(mock_prompt, mock_open_file, mock_lyrics_converter_cls, mock_zipfile, mock_isfile, basic_finaliser):
    """Test handling exception during TXT ZIP creation."""
    mock_isfile.return_value = False # No existing zip
    mock_converter_instance = MagicMock()
    mock_lyrics_converter_cls.return_value = mock_converter_instance
    mock_converter_instance.convert_file.return_value = "text"

    with pytest.raises(Exception, match="Zip creation failed"):
         basic_finaliser.create_txt_zip_file(INPUT_FILES_ZIP, OUTPUT_FILES_ZIP)

    # Ensure previous steps were attempted
    mock_lyrics_converter_cls.assert_called_once()
    mock_open_file.assert_called_once_with(OUTPUT_FILES_ZIP["karaoke_txt"], "w")
    mock_zipfile.assert_called_once() # Attempted to create zip
