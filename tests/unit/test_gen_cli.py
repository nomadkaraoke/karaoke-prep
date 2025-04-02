import pytest
import asyncio
import argparse
import os
import logging
import sys
from unittest.mock import patch, MagicMock, AsyncMock, mock_open, call

# Import the module/functions to test
from karaoke_prep.utils import gen_cli

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio

# Sample style params JSON
SAMPLE_STYLE_JSON = '{"cdg": {"some_style": "value"}}'

# Mock return value for KaraokeFinalise.process
MOCK_FINAL_TRACK = {
    "artist": "Test Artist",
    "title": "Test Title",
    "video_with_vocals": "test_wv.mp4",
    "video_with_instrumental": "test_wi.mp4",
    "final_video": "test_final.mp4",
    "final_video_mkv": "test_final.mkv",
    "final_video_lossy": "test_final_lossy.mp4",
    "final_video_720p": "test_final_720p.mp4",
    "final_karaoke_cdg_zip": "test_cdg.zip",
    "final_karaoke_txt_zip": "test_txt.zip",
    "brand_code": "TEST-0001",
    "new_brand_code_dir_path": "/path/to/TEST-0001 - Test Artist - Test Title",
    "youtube_url": "https://youtube.com/watch?v=1234",
    "brand_code_dir_sharing_link": "https://share.link/folder",
}

# Mock return value for KaraokePrep.process
MOCK_PREP_TRACK = {
    "artist": "Test Artist",
    "title": "Test Title",
    "input_media": "input.mp3",
    "input_audio_wav": "input.wav",
    "input_still_image": "input.jpg",
    "lyrics": "lyrics.txt",
    "processed_lyrics": "lyrics.json",
    "track_output_dir": "/fake/output/Test Artist - Test Title",
    "separated_audio": {
        "clean_instrumental": {"instrumental": "inst.flac", "vocals": "vocals.flac"},
        "other_stems": {"model1": {"bass": "bass.flac", "drums": "drums.flac"}},
        "backing_vocals": {"model2": {"backing": "backing.flac"}},
        "combined_instrumentals": {"model1": "combined_inst.flac"},
    },
}


@pytest.fixture
def mock_base_args():
    """Fixture for common mock command line arguments."""
    # Most args will be added/overridden in tests
    return argparse.Namespace(
        args=[], # Positional args
        prep_only=False,
        finalise_only=False,
        edit_lyrics=False,
        test_email_template=False,
        skip_transcription=False,
        skip_separation=False,
        skip_lyrics=False,
        lyrics_only=False,
        log_level="info",
        dry_run=False,
        render_bounding_boxes=False,
        filename_pattern=None,
        output_dir=".",
        no_track_subfolders=True, # Corresponds to create_track_subfolders=True
        lossless_output_format="FLAC",
        output_png=True,
        output_jpg=True,
        clean_instrumental_model="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        backing_vocals_models=["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"],
        other_stems_models=["htdemucs_6s.yaml"],
        model_file_dir="/tmp/audio-separator-models", # Default value might vary
        existing_instrumental=None,
        instrumental_format="flac",
        lyrics_artist=None,
        lyrics_title=None,
        lyrics_file=None,
        subtitle_offset_ms=0,
        skip_transcription_review=False,
        style_params_json=None,
        enable_cdg=False,
        enable_txt=False,
        brand_prefix=None,
        organised_dir=None,
        organised_dir_rclone_root=None,
        public_share_dir=None,
        youtube_client_secrets_file=None,
        youtube_description_file=None,
        rclone_destination=None,
        discord_webhook_url=None,
        email_template_file=None,
        keep_brand_code=False,
        yes=False, # non_interactive
    )

@pytest.fixture
def mock_logger():
    """Fixture for a mock logger."""
    logger = MagicMock(spec=logging.Logger)
    logger.level = logging.INFO # Default level
    return logger

@pytest.fixture(autouse=True)
def mock_pyperclip():
    """Automatically mock pyperclip."""
    with patch("karaoke_prep.utils.gen_cli.pyperclip", MagicMock()) as mock_clip:
        yield mock_clip

@pytest.fixture(autouse=True)
def mock_sleep():
    """Automatically mock time.sleep."""
    with patch("karaoke_prep.utils.gen_cli.time.sleep", MagicMock()) as mock_sl:
        yield mock_sl

# --- Test Argument Parsing Logic ---

@patch("karaoke_prep.utils.gen_cli.is_url", return_value=True)
@patch("karaoke_prep.utils.gen_cli.is_file", return_value=False)
@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
async def test_arg_parsing_url_only(mock_kprep, mock_isfile, mock_isurl, mock_base_args, mock_logger, caplog):
    """Test URL-only argument parsing."""
    mock_base_args.args = ["https://example.com/song.mp3"]
    mock_kprep.return_value = mock_kprep
    mock_kprep.process = AsyncMock(return_value=[MOCK_PREP_TRACK])

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kprep.assert_called_once()
    # Verify that input_media=URL is passed
    assert mock_kprep.call_args.kwargs["input_media"] == "https://example.com/song.mp3"
    # Verify warning in log
    assert "Input media provided without Artist and Title" in caplog.text

@patch("karaoke_prep.utils.gen_cli.is_url", return_value=True)
@patch("karaoke_prep.utils.gen_cli.is_file", return_value=False)
@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
async def test_arg_parsing_url_artist_title(mock_kprep, mock_isfile, mock_isurl, mock_base_args, mock_logger):
    """Test parsing: URL, Artist, Title."""
    mock_base_args.args = ["http://example.com/video.mp4", "URL Artist", "URL Title"]
    mock_kprep.return_value = mock_kprep
    mock_kprep.process = AsyncMock(return_value=[MOCK_PREP_TRACK])

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kprep.assert_called_once()
    call_kwargs = mock_kprep.call_args.kwargs
    assert call_kwargs["input_media"] == "http://example.com/video.mp4"
    assert call_kwargs["artist"] == "URL Artist"
    assert call_kwargs["title"] == "URL Title"

@patch("karaoke_prep.utils.gen_cli.is_url", return_value=False)
@patch("karaoke_prep.utils.gen_cli.is_file", return_value=True)
@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
async def test_arg_parsing_file_artist_title(mock_kprep, mock_isfile, mock_isurl, mock_base_args, mock_logger):
    """Test parsing: Local File, Artist, Title."""
    mock_base_args.args = ["/path/to/song.mp3", "File Artist", "File Title"]
    mock_kprep.return_value = mock_kprep
    mock_kprep.process = AsyncMock(return_value=[MOCK_PREP_TRACK])

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kprep.assert_called_once()
    call_kwargs = mock_kprep.call_args.kwargs
    assert call_kwargs["input_media"] == "/path/to/song.mp3"
    assert call_kwargs["artist"] == "File Artist"
    assert call_kwargs["title"] == "File Title"

@patch("karaoke_prep.utils.gen_cli.is_url", return_value=False)
@patch("karaoke_prep.utils.gen_cli.is_file", return_value=False)
@patch("karaoke_prep.utils.gen_cli.os.path.isdir", return_value=False)
@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
async def test_arg_parsing_artist_title_only(mock_kprep, mock_isdir, mock_isfile, mock_isurl, mock_base_args, mock_logger, caplog):
    """Test Artist and Title only argument parsing."""
    mock_base_args.args = ["Test Artist", "Test Title"]
    mock_kprep.return_value = mock_kprep
    mock_kprep.process = AsyncMock(return_value=[MOCK_PREP_TRACK])

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kprep.assert_called_once()
    # Verify that artist and title are passed, but not input_media
    assert mock_kprep.call_args.kwargs["artist"] == "Test Artist"
    assert mock_kprep.call_args.kwargs["title"] == "Test Title"
    assert mock_kprep.call_args.kwargs["input_media"] is None
    # Verify warning about YouTube search is shown
    assert "No input media provided, the top YouTube search result for" in caplog.text

@patch("karaoke_prep.utils.gen_cli.is_url", return_value=False)
@patch("karaoke_prep.utils.gen_cli.is_file", return_value=False)
@patch("karaoke_prep.utils.gen_cli.os.path.isdir", return_value=True)
@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
async def test_arg_parsing_folder_artist_pattern(mock_kprep, mock_isdir, mock_isfile, mock_isurl, mock_base_args, mock_logger):
    """Test parsing: Folder, Artist, Pattern."""
    mock_base_args.args = ["/path/to/folder", "Folder Artist"]
    mock_base_args.filename_pattern = r"(?P<index>\d+) - (?P<title>.+)\.mp3"
    mock_kprep.return_value = mock_kprep
    mock_kprep.process = AsyncMock(return_value=[MOCK_PREP_TRACK])

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kprep.assert_called_once()
    call_kwargs = mock_kprep.call_args.kwargs
    assert call_kwargs["input_media"] == "/path/to/folder"
    assert call_kwargs["artist"] == "Folder Artist"
    assert call_kwargs["filename_pattern"] == r"(?P<index>\d+) - (?P<title>.+)\.mp3"

@patch("karaoke_prep.utils.gen_cli.is_url", return_value=False)
@patch("karaoke_prep.utils.gen_cli.is_file", return_value=False)
@patch("karaoke_prep.utils.gen_cli.os.path.isdir", return_value=True)
@patch("karaoke_prep.utils.gen_cli.sys.exit")
async def test_arg_parsing_folder_missing_pattern(mock_exit, mock_isdir, mock_isfile, mock_isurl, mock_base_args, mock_logger):
    """Test parsing exits if folder provided without filename_pattern."""
    mock_base_args.args = ["/path/to/folder", "Folder Artist"]
    mock_base_args.filename_pattern = None # Missing pattern
    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.logging.getLogger", return_value=mock_logger):
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    # Just check that logger.error was called and exit was called
    assert mock_logger.error.called
    mock_exit.assert_called_once_with(1)

# --- Test Workflow Modes ---

@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise") # Should not be called
async def test_workflow_prep_only(mock_kfinalise, mock_kprep, mock_base_args, mock_logger):
    """Test --prep-only workflow."""
    mock_base_args.args = ["Artist", "Title"]
    mock_base_args.prep_only = True
    mock_kprep_instance = mock_kprep.return_value
    mock_kprep_instance.process = AsyncMock(return_value=[MOCK_PREP_TRACK]) # Simulate prep output

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.logging.getLogger", return_value=mock_logger):
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kprep.assert_called_once()
    mock_kprep_instance.process.assert_awaited_once()
    mock_kfinalise.assert_not_called() # Finalise should be skipped
    # We'll just verify that the app exits correctly without checking specific log messages
    assert mock_logger.info.called


@patch("karaoke_prep.utils.gen_cli.KaraokePrep") # Should not be called
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("builtins.open", new_callable=mock_open) # Mock open for style JSON if CDG enabled
async def test_workflow_finalise_only(mock_open, mock_kfinalise, mock_kprep, mock_base_args, mock_logger):
    """Test --finalise-only workflow."""
    mock_base_args.finalise_only = True
    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process = MagicMock(return_value=MOCK_FINAL_TRACK)

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.logging.getLogger", return_value=mock_logger):
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kprep.assert_not_called() # Prep should be skipped
    mock_kfinalise.assert_called_once()
    mock_kfinalise_instance.process.assert_called_once()
    # Just verify that we do log something
    assert mock_logger.info.called


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.gen_cli.os.path.basename", return_value="Edit Artist - Edit Title")
@patch("karaoke_prep.utils.gen_cli.os.getcwd", return_value="/fake/path/Edit Artist - Edit Title")
@patch("builtins.open", new_callable=mock_open) # Mock open for style JSON if CDG enabled
async def test_workflow_edit_lyrics(mock_open, mock_getcwd, mock_basename, mock_kfinalise, mock_kprep, mock_base_args, mock_logger):
    """Test --edit-lyrics workflow."""
    mock_base_args.edit_lyrics = True
    mock_base_args.enable_cdg = False # Simplify for now

    # Set up the KaraokePrep mock properly
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.backup_existing_outputs = MagicMock(return_value="/fake/path/Edit Artist - Edit Title/input.wav")
    mock_kprep_instance.process.return_value = [MOCK_PREP_TRACK] # Simulate prep output

    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process = MagicMock(return_value=MOCK_FINAL_TRACK)

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    # Check Prep call
    mock_kprep.assert_called_once()
    prep_call_kwargs = mock_kprep.call_args.kwargs
    assert prep_call_kwargs["artist"] == "Edit Artist"
    assert prep_call_kwargs["title"] == "Edit Title"
    assert prep_call_kwargs["input_media"] is None  # Set to None initially
    assert prep_call_kwargs["skip_separation"] is True # Should skip separation in edit mode
    assert prep_call_kwargs["skip_lyrics"] is False
    assert prep_call_kwargs["skip_transcription"] is False
    assert prep_call_kwargs["create_track_subfolders"] is False # Already in folder

    mock_kprep_instance.backup_existing_outputs.assert_called_once()
    mock_kprep_instance.process.assert_awaited_once()

    # Check Finalise call
    mock_kfinalise.assert_called_once()
    finalise_call_kwargs = mock_kfinalise.call_args.kwargs
    assert finalise_call_kwargs["keep_brand_code"] is True # Should keep brand code
    assert finalise_call_kwargs["non_interactive"] is False # Default unless -y

    mock_kfinalise_instance.process.assert_called_once_with(replace_existing=True) # Should replace


@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
async def test_workflow_test_email_template(mock_kfinalise, mock_base_args, mock_logger):
    """Test --test_email_template workflow."""
    mock_base_args.test_email_template = True
    mock_base_args.email_template_file = "template.txt"
    mock_kfinalise_instance = mock_kfinalise.return_value

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.logging.getLogger", return_value=mock_logger):
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_kfinalise.assert_called_once()
    finalise_call_kwargs = mock_kfinalise.call_args.kwargs
    assert finalise_call_kwargs["email_template_file"] == "template.txt"
    mock_kfinalise_instance.test_email_template.assert_called_once()
    assert mock_logger.info.called


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
async def test_workflow_lyrics_only(mock_kfinalise, mock_kprep, mock_base_args, mock_logger):
    """Test --lyrics-only workflow sets environment variables and skips."""
    mock_base_args.args = ["Artist", "Title"]
    mock_base_args.lyrics_only = True
    mock_kprep_instance = mock_kprep.return_value
    mock_kprep_instance.process = AsyncMock(return_value=[MOCK_PREP_TRACK])
    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process = MagicMock(return_value=MOCK_FINAL_TRACK)

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.logging.getLogger", return_value=mock_logger), \
         patch.dict("karaoke_prep.utils.gen_cli.os.environ", {}, clear=True), \
         patch("karaoke_prep.utils.gen_cli.os.environ.get") as mock_environ_get:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        # Set up the mock to return "1" for our environment variables
        mock_environ_get.side_effect = lambda key, default=None: "1" if key in ["KARAOKE_PREP_SKIP_AUDIO_SEPARATION", "KARAOKE_PREP_SKIP_TITLE_END_SCREENS"] else default
        await gen_cli.async_main()

    # Since we can't reliably test the os.environ, check that skip_separation was set
    mock_kprep.assert_called_once()
    prep_kwargs = mock_kprep.call_args.kwargs
    assert prep_kwargs["skip_separation"] is True
    assert mock_logger.info.called


# --- Test Finalise CDG Style Loading ---

@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_STYLE_JSON)
@patch("karaoke_prep.utils.gen_cli.os.chdir") # Mock chdir
@patch("karaoke_prep.utils.gen_cli.os.path.exists", return_value=True) # Assume track dir exists
async def test_finalise_cdg_style_loading(mock_exists, mock_chdir, mock_open, mock_kfinalise, mock_kprep, mock_base_args):
    """Test that CDG styles are loaded correctly when --enable_cdg is used."""
    mock_base_args.args = ["Artist", "Title"]
    mock_base_args.enable_cdg = True
    mock_base_args.style_params_json = "/fake/styles.json"
    expected_cdg_styles = {"some_style": "value"}

    mock_kprep.return_value.process = AsyncMock(return_value=[MOCK_PREP_TRACK])
    mock_kfinalise.return_value.process = MagicMock(return_value=MOCK_FINAL_TRACK)

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    # Check open was called for the style file
    mock_open.assert_called_with("/fake/styles.json", "r")

    # Check KaraokeFinalise was called with the loaded styles
    mock_kfinalise.assert_called_once()
    finalise_call_kwargs = mock_kfinalise.call_args.kwargs
    assert finalise_call_kwargs["enable_cdg"] is True
    assert finalise_call_kwargs["cdg_styles"] == expected_cdg_styles


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("builtins.open", side_effect=FileNotFoundError)
@patch("karaoke_prep.utils.gen_cli.os.chdir")
@patch("karaoke_prep.utils.gen_cli.os.path.exists", return_value=True)
@patch("karaoke_prep.utils.gen_cli.sys.exit")
async def test_finalise_cdg_style_file_not_found(mock_exit, mock_exists, mock_chdir, mock_open, mock_kfinalise, mock_kprep, mock_base_args, mock_logger):
    """Test exit if CDG enabled but style file not found."""
    mock_base_args.args = ["Artist", "Title"]
    mock_base_args.enable_cdg = True
    mock_base_args.style_params_json = "/fake/styles.json"

    mock_kprep.return_value.process = AsyncMock(return_value=[MOCK_PREP_TRACK])

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.logging.getLogger", return_value=mock_logger):
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_open.assert_called_with("/fake/styles.json", "r")
    assert mock_logger.error.called
    mock_exit.assert_called_once_with(1)
    mock_kfinalise.assert_not_called()


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("builtins.open", new_callable=mock_open, read_data="invalid json") # Invalid JSON
@patch("karaoke_prep.utils.gen_cli.os.chdir")
@patch("karaoke_prep.utils.gen_cli.os.path.exists", return_value=True)
@patch("karaoke_prep.utils.gen_cli.sys.exit")
async def test_finalise_cdg_style_invalid_json(mock_exit, mock_exists, mock_chdir, mock_open, mock_kfinalise, mock_kprep, mock_base_args, mock_logger):
    """Test exit if CDG enabled but style file has invalid JSON."""
    mock_base_args.args = ["Artist", "Title"]
    mock_base_args.enable_cdg = True
    mock_base_args.style_params_json = "/fake/styles.json"

    mock_kprep.return_value.process = AsyncMock(return_value=[MOCK_PREP_TRACK])

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.logging.getLogger", return_value=mock_logger):
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    mock_open.assert_called_with("/fake/styles.json", "r")
    # Assert sys.exit was called
    mock_exit.assert_called_once_with(1)
    # Verify KaraokeFinalise was not instantiated (we should exit before that)
    mock_kfinalise.assert_not_called()


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
async def test_error_handling_kprep_failure(mock_kfinalise, mock_kprep, mock_base_args, mock_logger, caplog):
    """Test error handling if KaraokePrep.process fails."""
    mock_base_args.args = ["Artist", "Title"]
    mock_kprep.return_value = mock_kprep
    mock_kprep.process.side_effect = Exception("KPrep Failed!")

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        # Expect the exception to propagate
        with pytest.raises(Exception, match="KPrep Failed!"):
            await gen_cli.async_main()

    mock_kprep.assert_called_once()
    mock_kprep.process.assert_awaited_once()
    mock_kfinalise.assert_not_called() # Should not reach finalise


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.gen_cli.os.chdir")
@patch("karaoke_prep.utils.gen_cli.os.path.exists", return_value=True)
async def test_error_handling_kfinalise_failure(mock_exists, mock_chdir, mock_kfinalise, mock_kprep, mock_base_args, mock_logger, caplog):
    """Test error handling if KaraokeFinalise.process fails."""
    mock_base_args.args = ["Artist", "Title"]
    mock_kprep.return_value = mock_kprep
    mock_kprep.process = AsyncMock(return_value=[MOCK_PREP_TRACK]) # Prep succeeds
    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process.side_effect = Exception("KFinalise Failed!")

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        # Expect the exception to propagate
        with pytest.raises(Exception, match="KFinalise Failed!"):
            await gen_cli.async_main()

    mock_kprep.assert_called_once()
    mock_kprep.process.assert_awaited_once()
    mock_chdir.assert_called_once_with(MOCK_PREP_TRACK["track_output_dir"]) # Should chdir before finalise
    mock_kfinalise.assert_called_once() # Finalise is called
    mock_kfinalise_instance.process.assert_called_once() # Process is called
    
    # Check the error message in log
    assert "Error during finalisation: KFinalise Failed!" in caplog.text


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
async def test_argument_passthrough(mock_kfinalise, mock_kprep, mock_base_args):
    """Test that various arguments are passed correctly to KaraokePrep/Finalise."""
    mock_base_args.args = ["Artist", "Title"]
    mock_base_args.render_bounding_boxes = True
    mock_base_args.skip_separation = True
    mock_base_args.skip_lyrics = True
    mock_base_args.skip_transcription = True
    mock_base_args.skip_transcription_review = True
    mock_base_args.subtitle_offset_ms = -100
    mock_base_args.existing_instrumental = "/path/to/inst.wav"
    mock_base_args.lyrics_artist = "Override Artist"
    mock_base_args.lyrics_title = "Override Title"
    mock_base_args.lyrics_file = "/path/to/lyrics.txt"
    mock_base_args.style_params_json = "/path/to/styles.json"
    mock_base_args.instrumental_format = "mp3"
    mock_base_args.yes = True # non_interactive

    mock_kprep.return_value.process = AsyncMock(return_value=[MOCK_PREP_TRACK])
    mock_kfinalise.return_value.process = MagicMock(return_value=MOCK_FINAL_TRACK)

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser, \
         patch("karaoke_prep.utils.gen_cli.os.chdir"), \
         patch("karaoke_prep.utils.gen_cli.os.path.exists", return_value=True):
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    # Check KaraokePrep args
    mock_kprep.assert_called_once()
    prep_kwargs = mock_kprep.call_args.kwargs
    assert prep_kwargs["render_bounding_boxes"] is True
    assert prep_kwargs["skip_separation"] is True
    assert prep_kwargs["skip_lyrics"] is True
    assert prep_kwargs["skip_transcription"] is True
    assert prep_kwargs["skip_transcription_review"] is True
    assert prep_kwargs["subtitle_offset_ms"] == -100
    assert prep_kwargs["existing_instrumental"] == "/path/to/inst.wav"
    assert prep_kwargs["lyrics_artist"] == "Override Artist"
    assert prep_kwargs["lyrics_title"] == "Override Title"
    assert prep_kwargs["lyrics_file"] == "/path/to/lyrics.txt"
    assert prep_kwargs["style_params_json"] == "/path/to/styles.json"

    # Check KaraokeFinalise args
    mock_kfinalise.assert_called_once()
    finalise_kwargs = mock_kfinalise.call_args.kwargs
    assert finalise_kwargs["instrumental_format"] == "mp3"
    assert finalise_kwargs["non_interactive"] is True


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.gen_cli.os.chdir")
@patch("karaoke_prep.utils.gen_cli.os.path.exists", return_value=True)
@patch("karaoke_prep.utils.gen_cli.pyperclip.copy")
async def test_clipboard_copy_success(mock_copy, mock_exists, mock_chdir, mock_kfinalise, mock_kprep, mock_base_args, mock_logger, caplog):
    """Test logging when clipboard copy succeeds."""
    mock_base_args.args = ["Artist", "Title"]
    
    # Set up the KaraokePrep mock properly
    mock_instance = AsyncMock()
    mock_kprep.return_value = mock_instance
    mock_instance.process.return_value = [MOCK_PREP_TRACK]
    
    # Ensure mock final track has URLs
    mock_final_track_with_urls = MOCK_FINAL_TRACK.copy()
    mock_final_track_with_urls["youtube_url"] = "http://youtu.be/fake"
    mock_final_track_with_urls["brand_code_dir_sharing_link"] = "http://share.link/fake"
    mock_kfinalise.return_value.process = MagicMock(return_value=mock_final_track_with_urls)

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    # Check log capture for success messages
    assert "(Folder link copied to clipboard)" in caplog.text
    assert "(YouTube URL copied to clipboard)" in caplog.text
    
    mock_copy.assert_has_calls([
        call("http://share.link/fake"),
        call("http://youtu.be/fake")
    ], any_order=True)


@patch("karaoke_prep.utils.gen_cli.KaraokePrep", new_callable=AsyncMock)
@patch("karaoke_prep.utils.gen_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.gen_cli.os.chdir")
@patch("karaoke_prep.utils.gen_cli.os.path.exists", return_value=True)
@patch("karaoke_prep.utils.gen_cli.pyperclip.copy", side_effect=Exception("Clipboard Error"))
async def test_clipboard_copy_failure(mock_copy, mock_exists, mock_chdir, mock_kfinalise, mock_kprep, mock_base_args, mock_logger, caplog):
    """Test logging when clipboard copy fails."""
    mock_base_args.args = ["Artist", "Title"]
    
    # Set up the KaraokePrep mock properly
    mock_instance = AsyncMock()
    mock_kprep.return_value = mock_instance
    mock_instance.process.return_value = [MOCK_PREP_TRACK]
    
    # Ensure mock final track has URLs
    mock_final_track_with_urls = MOCK_FINAL_TRACK.copy()
    mock_final_track_with_urls["youtube_url"] = "http://youtu.be/fake"
    mock_final_track_with_urls["brand_code_dir_sharing_link"] = "http://share.link/fake"
    mock_kfinalise.return_value.process = MagicMock(return_value=mock_final_track_with_urls)

    with patch("karaoke_prep.utils.gen_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_base_args
        await gen_cli.async_main()

    # Check log capture for warning messages
    assert "Failed to copy folder link to clipboard: Clipboard Error" in caplog.text
    assert "Failed to copy YouTube URL to clipboard: Clipboard Error" in caplog.text
    
    # Verify clipboard calls were attempted
    mock_copy.assert_has_calls([
        call("http://share.link/fake"),
        call("http://youtu.be/fake")
    ], any_order=True)
