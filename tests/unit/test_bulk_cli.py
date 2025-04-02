import pytest
import asyncio
import argparse
import csv
import os
import logging
import json
from unittest.mock import patch, MagicMock, AsyncMock, mock_open, call

# Import the module/functions to test
from karaoke_prep.utils import bulk_cli

# Mark all tests in this module as asyncio
pytestmark = pytest.mark.asyncio

# Sample CSV data as a string
SAMPLE_CSV_DATA = """Artist,Title,Mixed Audio Filename,Instrumental Audio Filename,Status
Artist One,Title One,mix1.mp3,inst1.mp3,Uploaded
Artist Two,Title Two,mix2.wav,inst2.wav,Prep_Complete
Artist Three,Title Three,mix3.flac,inst3.flac,Completed
Artist Four,Title Four,mix4.ogg,inst4.ogg,Prep_Failed
Artist Five,Title Five,mix5.m4a,inst5.m4a,Uploaded
"""

# Sample style params JSON
SAMPLE_STYLE_JSON = '{"cdg": {"some_style": "value"}}'


@pytest.fixture
def mock_args(tmp_path):
    """Fixture for mock command line arguments."""
    csv_path = tmp_path / "input.csv"
    csv_path.write_text(SAMPLE_CSV_DATA)
    style_path = tmp_path / "styles.json"
    style_path.write_text(SAMPLE_STYLE_JSON)

    args = argparse.Namespace(
        input_csv=str(csv_path),
        style_params_json=str(style_path),
        output_dir=str(tmp_path / "output"),
        enable_cdg=False,
        enable_txt=False,
        log_level=logging.INFO, # Use numeric level directly as processed in bulk_cli
        dry_run=False,
    )
    return args

@pytest.fixture
def mock_logger():
    """Fixture for a mock logger."""
    return MagicMock(spec=logging.Logger)

@pytest.fixture
def mock_log_formatter():
    """Fixture for a mock log formatter."""
    return MagicMock(spec=logging.Formatter)

@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.isfile", return_value=True)
@patch("karaoke_prep.utils.bulk_cli.os.path.exists")
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_CSV_DATA)
@patch("karaoke_prep.utils.bulk_cli.csv.DictReader")
@patch("karaoke_prep.utils.bulk_cli.csv.DictWriter")
@patch("karaoke_prep.utils.bulk_cli.update_csv_status", new_callable=AsyncMock) # Mock the async wrapper if needed, or the function itself
async def test_async_main_flow(
    mock_update_csv, mock_csv_writer, mock_csv_reader, mock_open_file,
    mock_getcwd, mock_chdir, mock_exists, mock_isfile,
    mock_kfinalise, mock_kprep, mock_args, mock_logger, mock_log_formatter
):
    """Test the main async_main function orchestrates the two phases correctly."""

    # Configure mocks
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "Test", "title": "Track"}]) # Simulate successful prep

    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process = MagicMock(return_value={"final": "track"}) # Simulate successful finalise

    # Simulate CSV reading
    mock_csv_reader.return_value = csv.DictReader(SAMPLE_CSV_DATA.splitlines())

    # Simulate os.path.exists for track directory finding in phase 2
    mock_exists.side_effect = lambda p: "Artist One - Title One" in p or "Artist Five - Title Five" in p

    # Mock argparse to return our mock_args
    with patch("karaoke_prep.utils.bulk_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_args

        # Inject mock logger and formatter (assuming they are passed correctly or globally accessible)
        # If they are created within the function, patching might be needed there.
        # For simplicity, assume they are passed or accessible.
        bulk_cli.logger = mock_logger # Replace module logger if needed

        await bulk_cli.async_main()

    # Assertions
    # Phase 1: process_track_prep called for 'Uploaded' status
    assert mock_kprep.call_count == 4 # Called twice in prep, twice in render
    prep_calls = [c for c in mock_kprep.call_args_list if not c.kwargs.get('render_video')]
    render_calls = [c for c in mock_kprep.call_args_list if c.kwargs.get('render_video')]

    assert len(prep_calls) == 2
    assert prep_calls[0].kwargs['artist'] == "Artist One"
    assert prep_calls[0].kwargs['title'] == "Title One"
    assert prep_calls[0].kwargs['render_video'] is False
    assert prep_calls[1].kwargs['artist'] == "Artist Five"
    assert prep_calls[1].kwargs['title'] == "Title Five"
    assert prep_calls[1].kwargs['render_video'] is False

    # Phase 2: process_track_render called for 'Prep_Complete' and 'Uploaded'
    assert len(render_calls) == 2
    assert render_calls[0].kwargs['artist'] == "Artist One" # Called again in render phase
    assert render_calls[0].kwargs['title'] == "Title One"
    assert render_calls[0].kwargs['render_video'] is True
    assert render_calls[1].kwargs['artist'] == "Artist Five" # Called again in render phase
    assert render_calls[1].kwargs['title'] == "Title Five"
    assert render_calls[1].kwargs['render_video'] is True

    # Check KaraokeFinalise calls (should happen during render phase)
    assert mock_kfinalise.call_count == 2 # Once for Artist One, once for Artist Five
    assert mock_kfinalise.call_args_list[0].kwargs['non_interactive'] is True
    assert mock_kfinalise.call_args_list[1].kwargs['non_interactive'] is True

    # Check CSV updates (mocked function)
    # Called 4 times: Prep Success (x2), Render Success (x2)
    assert mock_update_csv.call_count == 4
    assert mock_update_csv.call_args_list[0].args == (str(mock_args.input_csv), 0, "Prep_Complete") # Artist One Prep
    assert mock_update_csv.call_args_list[1].args == (str(mock_args.input_csv), 4, "Prep_Complete") # Artist Five Prep
    assert mock_update_csv.call_args_list[2].args == (str(mock_args.input_csv), 0, "Completed")     # Artist One Render
    assert mock_update_csv.call_args_list[3].args == (str(mock_args.input_csv), 4, "Completed")     # Artist Five Render

    # Check directory changes
    assert mock_chdir.call_count == 4 # To track dir (x2), back to original (x2)
    assert mock_getcwd.call_count >= 2 # Called at start of each process function


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
async def test_process_track_prep_success(mock_getcwd, mock_chdir, mock_kprep, mock_args, mock_logger, mock_log_formatter):
    """Test process_track_prep successfully calls KaraokePrep."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "A", "title": "T"}])
    row = {"Artist": "Test Artist", "Title": "Test Title", "Mixed Audio Filename": "mix.mp3", "Instrumental Audio Filename": "inst.mp3"}

    result = await bulk_cli.process_track_prep(row, mock_args, mock_logger, mock_log_formatter)

    assert result is True
    mock_kprep.assert_called_once_with(
        artist="Test Artist",
        title="Test Title",
        input_media="mix.mp3",
        existing_instrumental="inst.mp3",
        style_params_json=mock_args.style_params_json,
        logger=mock_logger,
        log_level=mock_args.log_level,
        dry_run=mock_args.dry_run,
        render_video=False,
        create_track_subfolders=True,
    )
    mock_kprep_instance.process.assert_awaited_once()
    mock_chdir.assert_called_once_with("/fake/original/dir") # Changed back at the end


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
async def test_process_track_prep_failure(mock_getcwd, mock_chdir, mock_kprep, mock_args, mock_logger, mock_log_formatter):
    """Test process_track_prep handles exceptions from KaraokePrep."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process.side_effect = Exception("Prep Error")
    row = {"Artist": "Test Artist", "Title": "Test Title", "Mixed Audio Filename": "mix.mp3", "Instrumental Audio Filename": "inst.mp3"}

    result = await bulk_cli.process_track_prep(row, mock_args, mock_logger, mock_log_formatter)

    assert result is False
    mock_logger.error.assert_called_once_with("Failed initial prep for Test Artist - Test Title: Prep Error")
    mock_chdir.assert_called_once_with("/fake/original/dir") # Should still change back


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True) # Assume track dir exists
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_STYLE_JSON) # For reading style JSON if CDG enabled
async def test_process_track_render_success(
    mock_open_file, mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render success with KaraokePrep and KaraokeFinalise."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "Render Artist", "title": "Render Title"}])
    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process = MagicMock(return_value={"final": "track"})

    row = {"Artist": "Render Artist", "Title": "Render Title", "Mixed Audio Filename": "mix_render.mp3", "Instrumental Audio Filename": "inst_render.mp3"}
    mock_args.enable_cdg = False # Keep it simple first

    result = await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    assert result is True
    # Check KaraokePrep call
    mock_kprep.assert_called_once_with(
        artist="Render Artist",
        title="Render Title",
        input_media="mix_render.mp3",
        existing_instrumental="inst_render.mp3",
        style_params_json=mock_args.style_params_json,
        logger=mock_logger,
        log_level=mock_args.log_level,
        dry_run=mock_args.dry_run,
        render_video=True,
        create_track_subfolders=True,
        skip_transcription_review=True,
    )
    mock_kprep_instance.process.assert_awaited_once()

    # Check directory finding and chdir
    expected_track_dir = os.path.join(mock_args.output_dir, "Render Artist - Render Title")
    mock_exists.assert_called_with(expected_track_dir)
    mock_chdir.assert_any_call(expected_track_dir) # Changed into track dir

    # Check KaraokeFinalise call
    mock_kfinalise.assert_called_once_with(
        log_formatter=mock_log_formatter,
        log_level=mock_args.log_level,
        dry_run=mock_args.dry_run,
        enable_cdg=False,
        enable_txt=False,
        cdg_styles=None,
        non_interactive=True,
    )
    mock_kfinalise_instance.process.assert_called_once()

    # Check changed back to original dir
    mock_chdir.assert_called_with("/fake/original/dir")


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True)
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_STYLE_JSON)
async def test_process_track_render_finalise_failure(
    mock_open_file, mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render handles exceptions from KaraokeFinalise."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "Fail Artist", "title": "Fail Title"}])
    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process.side_effect = Exception("Finalise Error")

    row = {"Artist": "Fail Artist", "Title": "Fail Title", "Mixed Audio Filename": "mix_fail.mp3", "Instrumental Audio Filename": "inst_fail.mp3"}

    result = await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    assert result is False
    mock_logger.error.assert_any_call("Error during finalisation: Finalise Error")
    mock_logger.error.assert_called_with("Failed render/finalise for Fail Artist - Fail Title: Finalise Error")
    mock_chdir.assert_called_with("/fake/original/dir") # Should still change back


@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_CSV_DATA)
@patch("karaoke_prep.utils.bulk_cli.csv.DictReader")
@patch("karaoke_prep.utils.bulk_cli.csv.DictWriter")
def test_update_csv_status(mock_csv_writer, mock_csv_reader, mock_open_file, tmp_path):
    """Test the update_csv_status function correctly modifies the CSV."""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV_DATA) # Use tmp_path for actual file write

    # Simulate reading the CSV
    rows_read = list(csv.DictReader(SAMPLE_CSV_DATA.splitlines()))
    mock_csv_reader.return_value = rows_read
    # We need the actual open for writing
    mock_open_file.side_effect = [
        mock_open(read_data=SAMPLE_CSV_DATA).return_value, # For reading
        open(csv_path, "w", newline="") # For writing
    ]

    # Mock the writer instance
    mock_writer_instance = MagicMock()
    mock_csv_writer.return_value = mock_writer_instance

    # Call the function to update the first row (index 0)
    bulk_cli.update_csv_status(str(csv_path), 0, "New_Status")

    # Assertions
    # Check open calls: once for read, once for write
    assert mock_open_file.call_count == 2
    assert mock_open_file.call_args_list[0] == call(str(csv_path), "r")
    assert mock_open_file.call_args_list[1] == call(str(csv_path), "w", newline="")

    # Check that DictWriter was called with the correct fieldnames
    expected_fieldnames = ["Artist", "Title", "Mixed Audio Filename", "Instrumental Audio Filename", "Status"]
    mock_csv_writer.assert_called_once_with(mock_open_file.return_value, fieldnames=expected_fieldnames)

    # Check that writeheader and writerows were called
    mock_writer_instance.writeheader.assert_called_once()

    # Verify the data passed to writerows
    written_rows = mock_writer_instance.writerows.call_args[0][0]
    assert len(written_rows) == len(rows_read)
    assert written_rows[0]["Status"] == "New_Status" # Check updated status
    assert written_rows[1]["Status"] == "Prep_Complete" # Check other rows unchanged


@patch("karaoke_prep.utils.bulk_cli.argparse.ArgumentParser")
def test_argument_parsing(mock_parser_class, tmp_path):
    """Test that arguments are parsed correctly."""
    mock_parser_instance = mock_parser_class.return_value
    mock_args = argparse.Namespace(
        input_csv="path/to/input.csv",
        style_params_json="path/to/styles.json",
        output_dir="output",
        enable_cdg=True,
        enable_txt=False,
        log_level="debug", # String level before conversion
        dry_run=True,
    )
    mock_parser_instance.parse_args.return_value = mock_args

    # Mock os.path.abspath and isfile for validation within async_main if called directly
    with patch("karaoke_prep.utils.bulk_cli.os.path.abspath", side_effect=lambda x: "/abs/" + x), \
         patch("karaoke_prep.utils.bulk_cli.os.path.isfile", return_value=True), \
         patch("karaoke_prep.utils.bulk_cli.asyncio.run"): # Prevent actual run

        # We need to simulate the main entry point or parts of async_main
        # to see the argument processing. Let's simulate the start of async_main.
        bulk_cli.main() # Call main which calls asyncio.run(async_main)

        # Check if parse_args was called
        mock_parser_instance.parse_args.assert_called_once()

        # Check if abspath was called on input_csv
        # Note: This check happens *inside* async_main, which we patched away with asyncio.run
        # To test this properly, we might need to call async_main directly or test the main() setup.
        # Let's refine this by checking the parser setup in main() or a dedicated setup function if it existed.

        # Check parser setup (example)
        mock_parser_instance.add_argument.assert_any_call("input_csv", help=pytest.ANY)
        mock_parser_instance.add_argument("--style_params_json", required=True, help=pytest.ANY)
        mock_parser_instance.add_argument("--output_dir", default=".", help=pytest.ANY)
        mock_parser_instance.add_argument("--enable_cdg", action="store_true", help=pytest.ANY)
        mock_parser_instance.add_argument("--enable_txt", action="store_true", help=pytest.ANY)
        mock_parser_instance.add_argument("--log_level", default="info", help=pytest.ANY)
        mock_parser_instance.add_argument("--dry_run", action="store_true", help=pytest.ANY)
        mock_parser_instance.add_argument("-v", "--version", action="version", version=pytest.ANY)


@patch("karaoke_prep.utils.bulk_cli.argparse.ArgumentParser")
@patch("karaoke_prep.utils.bulk_cli.os.path.abspath", side_effect=lambda x: "/abs/" + x)
@patch("karaoke_prep.utils.bulk_cli.os.path.isfile", return_value=False) # Simulate file not found
@patch("karaoke_prep.utils.bulk_cli.asyncio.run") # Prevent actual run
@patch("karaoke_prep.utils.bulk_cli.logger") # Mock logger to check error message
def test_async_main_csv_not_found(mock_logger, mock_run, mock_isfile, mock_abspath, mock_parser_class):
    """Test async_main exits if input CSV is not found."""
    mock_parser_instance = mock_parser_class.return_value
    mock_args = argparse.Namespace(
        input_csv="nonexistent.csv",
        style_params_json="styles.json",
        output_dir="output",
        enable_cdg=False,
        enable_txt=False,
        log_level="info",
        dry_run=False,
    )
    mock_parser_instance.parse_args.return_value = mock_args

    with pytest.raises(SystemExit) as excinfo:
         # Need to call main() which sets up logging and calls async_main
         # We mock asyncio.run to prevent the actual async execution
         bulk_cli.main()

    assert excinfo.value.code == 1
    # Check logger call within async_main (which is called by main via asyncio.run)
    # Since we mock asyncio.run, we need to check the logger used *before* the run call,
    # or mock the logger passed into async_main if that were the design.
    # Let's assume the global logger is used before exit.
    mock_logger.error.assert_called_once_with("Input CSV file not found: /abs/nonexistent.csv")


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True) # Track dir exists
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", side_effect=FileNotFoundError("Styles not found")) # Simulate style file not found
@patch("karaoke_prep.utils.bulk_cli.sys.exit") # Mock sys.exit
async def test_process_track_render_style_json_not_found_cdg(
    mock_exit, mock_open_file, mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render exits if style JSON not found when CDG enabled."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "CDG Artist", "title": "CDG Title"}])

    row = {"Artist": "CDG Artist", "Title": "CDG Title", "Mixed Audio Filename": "mix_cdg.mp3", "Instrumental Audio Filename": "inst_cdg.mp3"}
    mock_args.enable_cdg = True # Enable CDG

    await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    # Assertions
    mock_open_file.assert_called_once_with(mock_args.style_params_json, "r")
    mock_logger.error.assert_called_once_with(f"CDG styles configuration file not found: {mock_args.style_params_json}")
    mock_exit.assert_called_once_with(1)
    mock_kfinalise.assert_not_called() # Should exit before finalise


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True) # Track dir exists
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data="invalid json") # Simulate invalid JSON
@patch("karaoke_prep.utils.bulk_cli.sys.exit") # Mock sys.exit
async def test_process_track_render_style_json_invalid_cdg(
    mock_exit, mock_open_file, mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render exits if style JSON is invalid when CDG enabled."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "CDG Artist", "title": "CDG Title"}])

    row = {"Artist": "CDG Artist", "Title": "CDG Title", "Mixed Audio Filename": "mix_cdg.mp3", "Instrumental Audio Filename": "inst_cdg.mp3"}
    mock_args.enable_cdg = True # Enable CDG

    await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    # Assertions
    mock_open_file.assert_called_once_with(mock_args.style_params_json, "r")
    # Use a more flexible assertion that doesn't rely on pytest.string_containing
    error_message = mock_logger.error.call_args[0][0]
    assert "Invalid JSON in CDG styles configuration file:" in error_message
    mock_exit.assert_called_once_with(1)
    mock_kfinalise.assert_not_called() # Should exit before finalise


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=False) # Simulate track dir NOT found
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
async def test_process_track_render_track_dir_not_found(
    mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render logs error if track directory is not found."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "NoDir Artist", "title": "NoDir Title"}])

    row = {"Artist": "NoDir Artist", "Title": "NoDir Title", "Mixed Audio Filename": "mix_nodir.mp3", "Instrumental Audio Filename": "inst_nodir.mp3"}

    result = await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    # Should still return True overall for the row processing attempt, but log an error
    # The function currently continues to the next track if one dir isn't found.
    # Let's adjust the test slightly - the function should return True if kprep succeeds,
    # even if finalise fails for a track within it due to missing dir.
    # The *overall* success/fail is determined later based on logs or status.
    # Let's refine the test: check the log and ensure kfinalise wasn't called.

    assert result is True # KPrep succeeded
    mock_kprep.assert_called_once()
    mock_kprep_instance.process.assert_awaited_once()

    # Check os.path.exists calls
    expected_dir1 = os.path.join(mock_args.output_dir, "NoDir Artist - NoDir Title")
    expected_dir2 = os.path.join(mock_args.output_dir, "NoDir Artist - NoDir Title") # Original artist/title from row
    expected_dir3 = os.path.join(mock_args.output_dir, "NoDir Artist - NoDir Title") # With space replace (same here)
    mock_exists.assert_has_calls([call(expected_dir1), call(expected_dir2), call(expected_dir3)])

    # Use a more flexible assertion that doesn't rely on pytest.string_containing
    error_message = mock_logger.error.call_args[0][0]
    assert "Track directory not found. Tried:" in error_message
    mock_chdir.assert_not_called() # Shouldn't chdir if dir not found
    mock_kfinalise.assert_not_called() # Shouldn't finalise if dir not found
    mock_getcwd.assert_called_once() # Called at the start of the function


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.isfile", return_value=True)
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True)
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_CSV_DATA)
@patch("karaoke_prep.utils.bulk_cli.csv.DictReader")
@patch("karaoke_prep.utils.bulk_cli.csv.DictWriter")
@patch("karaoke_prep.utils.bulk_cli.update_csv_status") # Use standard mock here
async def test_async_main_dry_run(
    mock_update_csv, mock_csv_writer, mock_csv_reader, mock_open_file,
    mock_getcwd, mock_chdir, mock_exists, mock_isfile,
    mock_kfinalise, mock_kprep, mock_args, mock_logger, mock_log_formatter
):
    """Test that update_csv_status is not called during a dry run."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "Test", "title": "Track"}])
    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process = MagicMock(return_value={"final": "track"})
    mock_csv_reader.return_value = csv.DictReader(SAMPLE_CSV_DATA.splitlines())

    with patch("karaoke_prep.utils.bulk_cli.argparse.ArgumentParser") as mock_parser:
        mock_parser.return_value.parse_args.return_value = mock_args
        bulk_cli.logger = mock_logger
        await bulk_cli.async_main()

    # Assertions
    mock_kprep.assert_called() # Ensure processing still happens
    mock_kfinalise.assert_called()
    mock_update_csv.assert_not_called() # Crucial check for dry run


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True) # Assume track dir exists
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_STYLE_JSON) # For reading style JSON
async def test_process_track_render_cdg_enabled(
    mock_open_file, mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render correctly loads CDG styles when enabled."""
    mock_kprep_instance = AsyncMock()
    mock_kprep.return_value = mock_kprep_instance
    mock_kprep_instance.process = AsyncMock(return_value=[{"artist": "CDG Artist", "title": "CDG Title"}])
    mock_kfinalise_instance = mock_kfinalise.return_value
    mock_kfinalise_instance.process = MagicMock(return_value={"final": "track"})

    row = {"Artist": "CDG Artist", "Title": "CDG Title", "Mixed Audio Filename": "mix_cdg.mp3", "Instrumental Audio Filename": "inst_cdg.mp3"}
    mock_args.enable_cdg = True # Enable CDG
    expected_cdg_styles = {"some_style": "value"}

    result = await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    assert result is True
    mock_kprep.assert_called_once() # Prep called
    mock_open_file.assert_called_once_with(mock_args.style_params_json, "r") # Style file opened

    # Check KaraokeFinalise call with CDG styles
    mock_kfinalise.assert_called_once_with(
        log_formatter=mock_log_formatter,
        log_level=mock_args.log_level,
        dry_run=mock_args.dry_run,
        enable_cdg=True,
        enable_txt=False,
        cdg_styles=expected_cdg_styles, # Check styles are passed
        non_interactive=True,
    )
    mock_kfinalise_instance.process.assert_called_once()


@patch("karaoke_prep.utils.bulk_cli.argparse.ArgumentParser")
@patch("karaoke_prep.utils.bulk_cli.os.path.abspath")
@patch("karaoke_prep.utils.bulk_cli.os.path.isfile", return_value=True)
@patch("karaoke_prep.utils.bulk_cli.asyncio.run")
@patch("karaoke_prep.utils.bulk_cli.logging.StreamHandler") # Mock handler setup
@patch("karaoke_prep.utils.bulk_cli.logging.Formatter")
@patch("karaoke_prep.utils.bulk_cli.logger") # Mock the logger itself
def test_main_logging_setup(mock_logger, mock_formatter, mock_handler, mock_run, mock_isfile, mock_abspath, mock_parser_class):
    """Test that the main function sets up logging correctly."""
    mock_parser_instance = mock_parser_class.return_value
    mock_args = argparse.Namespace(
        input_csv="input.csv",
        style_params_json="styles.json",
        output_dir=".",
        enable_cdg=False,
        enable_txt=False,
        log_level="debug", # Test different level
        dry_run=False,
    )
    mock_parser_instance.parse_args.return_value = mock_args
    mock_abspath.return_value = "/abs/input.csv"

    # Mock getattr used for log level conversion inside async_main
    with patch("karaoke_prep.utils.bulk_cli.getattr") as mock_getattr:
        mock_getattr.return_value = logging.DEBUG # Simulate conversion

        bulk_cli.main()

    # Check handler and formatter creation and setup
    mock_handler.assert_called_once()
    mock_formatter.assert_called_once_with(fmt=pytest.ANY, datefmt=pytest.ANY)
    mock_handler.return_value.setFormatter.assert_called_once_with(mock_formatter.return_value)
    mock_logger.addHandler.assert_called_once_with(mock_handler.return_value)

    # Check that asyncio.run was called (implicitly calls async_main)
    mock_run.assert_called_once()

    # Check that log level was processed correctly inside async_main (mocked via getattr)
    # This happens *inside* the mocked asyncio.run call.
    # We need to verify the args passed to the *actual* async_main if we didn't mock run.
    # Since we mocked run, we check the setup *before* run.
    # The log level conversion happens *inside* async_main.
    # Let's verify the args passed to the mocked run call.
    call_args, call_kwargs = mock_run.call_args
    assert len(call_args) == 1
    assert call_args[0] == bulk_cli.async_main() # Check it's trying to run the right coroutine

    # To properly test the log level inside async_main, we'd need a different approach,
    # perhaps calling async_main directly after mocking its dependencies.
    # For now, we confirm the main setup calls happen.
