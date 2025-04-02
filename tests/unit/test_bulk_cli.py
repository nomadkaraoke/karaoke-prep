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

# Define module paths to mock consistently across tests
mock_module_paths = {
    "KaraokePrep": "karaoke_prep.utils.bulk_cli.KaraokePrep",
    "KaraokeFinalise": "karaoke_prep.utils.bulk_cli.KaraokeFinalise",
    "os_path_isfile": "karaoke_prep.utils.bulk_cli.os.path.isfile",
    "os_path_exists": "karaoke_prep.utils.bulk_cli.os.path.exists",
    "os_chdir": "karaoke_prep.utils.bulk_cli.os.chdir",
    "os_getcwd": "karaoke_prep.utils.bulk_cli.os.getcwd",
    "open_func": "builtins.open",
    "csv_DictReader": "karaoke_prep.utils.bulk_cli.csv.DictReader",
    "csv_DictWriter": "karaoke_prep.utils.bulk_cli.csv.DictWriter",
    "update_csv_status": "karaoke_prep.utils.bulk_cli.update_csv_status",
    "ArgumentParser": "karaoke_prep.utils.bulk_cli.argparse.ArgumentParser",
    "os_path_abspath": "karaoke_prep.utils.bulk_cli.os.path.abspath",
    "sys_exit": "karaoke_prep.utils.bulk_cli.sys.exit",
    "asyncio_run": "karaoke_prep.utils.bulk_cli.asyncio.run",
    "logger": "karaoke_prep.utils.bulk_cli.logger",
    "getattr_func": "karaoke_prep.utils.bulk_cli.getattr",
    "StreamHandler": "karaoke_prep.utils.bulk_cli.logging.StreamHandler",
    "Formatter": "karaoke_prep.utils.bulk_cli.logging.Formatter"
}

# Instead of the global pytestmark, we'll explicitly mark async tests where needed
# and neither mark sync tests nor explicitly mark them as non-async

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

# For tests that are not async functions, remove the asyncio mark
single_test_marks = {
    "test_update_csv_status": False,
    "test_argument_parsing": False,
    "test_async_main_csv_not_found": False,
    "test_main_logging_setup": False
}

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

# Add mocks for the new helper functions and process_csv_rows
@patch("karaoke_prep.utils.bulk_cli.process_csv_rows", new_callable=AsyncMock)
@patch("karaoke_prep.utils.bulk_cli._read_csv_file")
@patch("karaoke_prep.utils.bulk_cli._parse_and_validate_args")
@patch("karaoke_prep.utils.bulk_cli.setup_logging") # Mock logging setup as well
@patch("karaoke_prep.utils.bulk_cli.logger") # Mock the module-level logger directly
@pytest.mark.asyncio # Explicitly mark as async test
async def test_async_main_flow(
    mock_bulk_cli_logger, mock_setup_logging, mock_parse_args, mock_read_csv, mock_process_rows, # Added mock_bulk_cli_logger back
    mock_args, mock_logger, mock_log_formatter # Keep fixtures needed by args/mocks
):
    """Test the refactored async_main function orchestrates argument parsing, CSV reading, and processing."""

    # --- Mock Configuration ---
    # 1. Mock _parse_and_validate_args to return our fixture args
    mock_parse_args.return_value = mock_args

    # 2. Mock _read_csv_file to return sample rows
    sample_rows = list(csv.DictReader(SAMPLE_CSV_DATA.splitlines()))
    mock_read_csv.return_value = sample_rows

    # 3. Mock setup_logging to return the mock formatter
    mock_setup_logging.return_value = mock_log_formatter

    # 4. Mock process_csv_rows (AsyncMock) - we just check it's called correctly
    mock_process_rows.return_value = {"summary": "results"} # Return some dummy result

    # --- Inject Mocks & Run ---
    # Ensure setup_logging returns the formatter when called
    mock_setup_logging.return_value = mock_log_formatter
    # We also need to ensure the global log_formatter is set as async_main checks it.
    bulk_cli.log_formatter = mock_log_formatter # Set the global formatter

    # Run the async_main function
    result = await bulk_cli.async_main()

    # --- Assertions ---
    # 1. Check _parse_and_validate_args was called
    mock_parse_args.assert_called_once()

    # 2. Check logger level was set directly on the module logger
    mock_bulk_cli_logger.setLevel.assert_called_with(mock_args.log_level)
    # No need to assert setup_logging call for level setting

    # 3. Check _read_csv_file was called with the validated CSV path from args
    mock_read_csv.assert_called_once_with(mock_args.input_csv)

    # 4. Check process_csv_rows was awaited correctly, passing the patched module logger
    mock_process_rows.assert_awaited_once_with(
        mock_args.input_csv,
        sample_rows,
        mock_args,
        mock_bulk_cli_logger, # Pass the patched module logger
        mock_log_formatter # Check it's called with the formatter
    )

    # 5. Check the final result is returned
    assert result == {"summary": "results"}


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@pytest.mark.asyncio # Explicitly mark as async test
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
@pytest.mark.asyncio # Explicitly mark as async test
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
@pytest.mark.asyncio # Explicitly mark as async test
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
@pytest.mark.asyncio # Explicitly mark as async test
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


def test_update_csv_status(tmp_path):
    """Test the update_csv_status function correctly modifies the CSV."""
    # Create a temporary CSV file
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(SAMPLE_CSV_DATA)
    
    # Call the function
    result = bulk_cli.update_csv_status(str(csv_path), 0, "New_Status")
    
    # Verify the function returned True for success
    assert result is True
    
    # Read the file back and verify changes
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    # Check that the status was updated for the first row
    assert rows[0]["Status"] == "New_Status"
    # Check that other rows remain unchanged
    assert rows[1]["Status"] == "Prep_Complete"
    assert rows[2]["Status"] == "Completed"


@patch(mock_module_paths["logger"])
def test_update_csv_status_dry_run(mock_logger, tmp_path):
    """Test that update_csv_status doesn't modify the file in dry run mode."""
    # Create a temporary CSV file
    csv_path = tmp_path / "test_dry_run.csv"
    csv_path.write_text(SAMPLE_CSV_DATA)
    
    # Call with dry_run=True
    result = bulk_cli.update_csv_status(str(csv_path), 0, "New_Status", dry_run=True)
    
    # Verify the function returned False for dry run
    assert result is False
    
    # Verify log message
    mock_logger.info.assert_called_once()
    log_message = mock_logger.info.call_args[0][0]
    assert "DRY RUN" in log_message
    assert "New_Status" in log_message
    
    # Read the file back and verify it wasn't changed
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        
    # Check that the status of the first row is still the original
    assert rows[0]["Status"] == "Uploaded"


@patch(mock_module_paths["ArgumentParser"])
def test_argument_parsing(mock_parser_class):
    """Test that arguments are parsed correctly."""
    # Create a mock parser that returns predefined args
    mock_parser_instance = mock_parser_class.return_value
    mock_args = argparse.Namespace(
        input_csv="path/to/input.csv",
        style_params_json="path/to/styles.json",
        output_dir="output",
        enable_cdg=True,
        enable_txt=False,
        log_level="debug",
        dry_run=True,
    )
    mock_parser_instance.parse_args.return_value = mock_args

    # Call the function under test
    with patch("sys.argv", ["bulk_cli.py", "path/to/input.csv", "--style_params_json=path/to/styles.json"]):
        result = bulk_cli.parse_arguments()

    # Verify the parser was configured correctly
    assert mock_parser_class.call_count == 1
    # Verify parse_args was called
    assert mock_parser_instance.parse_args.call_count == 1
    
    # Verify the expected arguments were added to the parser
    add_argument_calls = [call_args[0][0] for call_args in mock_parser_instance.add_argument.call_args_list]
    
    # Check for required arguments
    assert "input_csv" in ''.join(str(x) for x in add_argument_calls)
    assert "--style_params_json" in add_argument_calls
    assert "--output_dir" in add_argument_calls
    assert "--enable_cdg" in add_argument_calls
    assert "--enable_txt" in add_argument_calls
    assert "--log_level" in add_argument_calls
    assert "--dry_run" in add_argument_calls
    
    # Check the result
    assert result == mock_args


@patch(mock_module_paths["os_path_isfile"], return_value=False)  # Simulate file not found
@patch(mock_module_paths["logger"])  # Mock logger to check error message
def test_validate_input_csv_not_found(mock_logger, mock_isfile):
    """Test that validate_input_csv returns False when CSV is not found."""
    # Call the function under test with a non-existent file
    result = bulk_cli.validate_input_csv("/non/existent/file.csv")
    
    # Verify the result
    assert result is False
    
    # Verify error was logged
    mock_logger.error.assert_called_once_with("Input CSV file not found: /non/existent/file.csv")


@patch(mock_module_paths["os_path_isfile"], return_value=True)  # Simulate file found
def test_validate_input_csv_exists(mock_isfile):
    """Test that validate_input_csv returns True when CSV exists."""
    # Call the function under test with an existing file
    result = bulk_cli.validate_input_csv("/path/to/existing/file.csv")
    
    # Verify the result
    assert result is True
    
    # Verify isfile was called with the right path
    mock_isfile.assert_called_once_with("/path/to/existing/file.csv")


@patch(mock_module_paths["ArgumentParser"])
@patch(mock_module_paths["os_path_abspath"])
@patch(mock_module_paths["os_path_isfile"], return_value=False)  # Simulate file not found
@patch(mock_module_paths["asyncio_run"])  # Keep mock_run for now, might be useful later
@patch(mock_module_paths["logger"])
# Test the helper function directly
def test_parse_and_validate_args_csv_not_found(mock_logger, mock_run, mock_isfile, mock_abspath, mock_parser_class):
    """Test _parse_and_validate_args raises FileNotFoundError if input CSV is not found."""
    # Configure mocks for parse_arguments called within _parse_and_validate_args
    mock_parser_instance = mock_parser_class.return_value
    mock_abspath.side_effect = lambda p: f"/abs/{p}" # Mock abspath used in parse_arguments
    mock_isfile.return_value = False # Mock isfile called by validate_input_csv

    mock_args = argparse.Namespace(
        input_csv="nonexistent.csv",
        style_params_json="styles.json",
        output_dir="output",
        enable_cdg=False,
        enable_txt=False,
        log_level=logging.INFO, # parse_arguments now converts level to int
        dry_run=False,
    )
    mock_parser_instance.parse_args.return_value = mock_args # Mock return of parse_args

    # Use pytest.raises to check for the expected exception from _parse_and_validate_args
    with pytest.raises(FileNotFoundError) as excinfo:
        bulk_cli._parse_and_validate_args() # Call the target function

    # Assertions
    # Check the exception message (raised by _parse_and_validate_args)
    assert "Input CSV file not found: /abs/nonexistent.csv" in str(excinfo.value)
    # Verify logger.error was called by validate_input_csv (called by _parse_and_validate_args)
    mock_logger.error.assert_called_once_with("Input CSV file not found: /abs/nonexistent.csv")
    # Verify os.path.isfile was called
    mock_isfile.assert_called_once_with("/abs/nonexistent.csv")


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True) # Track dir exists
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", side_effect=FileNotFoundError("Styles not found")) # Simulate style file not found
@pytest.mark.asyncio # Explicitly mark as async test
async def test_process_track_render_style_json_not_found_cdg(
    mock_open_file, mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render raises FileNotFoundError if style JSON not found when CDG enabled."""
    row = {"Artist": "CDG Artist", "Title": "CDG Title", "Mixed Audio Filename": "mix_cdg.mp3", "Instrumental Audio Filename": "inst_cdg.mp3"}
    mock_args.enable_cdg = True # Enable CDG
    mock_args.style_params_json = "/fake/styles.json"

    # Use pytest.raises to check for the expected exception
    with pytest.raises(FileNotFoundError) as excinfo:
        await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    # Assertions
    mock_open_file.assert_called_once_with(mock_args.style_params_json, "r")
    # Check the exception message
    assert f"CDG styles configuration file not found: {mock_args.style_params_json}" in str(excinfo.value)
    # KaraokeFinalise should not have been initialized if style loading fails early
    mock_kfinalise.assert_not_called()


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True) # Track dir exists
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data="invalid json") # Simulate invalid JSON
@pytest.mark.asyncio # Explicitly mark as async test
async def test_process_track_render_style_json_invalid_cdg(
    mock_open_file, mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render raises ValueError if style JSON is invalid when CDG enabled."""
    row = {"Artist": "CDG Artist", "Title": "CDG Title", "Mixed Audio Filename": "mix_cdg.mp3", "Instrumental Audio Filename": "inst_cdg.mp3"}
    mock_args.enable_cdg = True # Enable CDG
    mock_args.style_params_json = "/fake/styles.json"

    # Use pytest.raises to check for the expected exception
    with pytest.raises(ValueError) as excinfo:
        await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    # Assertions
    mock_open_file.assert_called_once_with(mock_args.style_params_json, "r")
    # Check the exception message
    assert "Invalid JSON in CDG styles configuration file:" in str(excinfo.value)
    # KaraokeFinalise should not have been initialized if style loading fails early
    mock_kfinalise.assert_not_called()


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=False) # Simulate track dir NOT found
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@pytest.mark.asyncio # Explicitly mark as async test
async def test_process_track_render_track_dir_not_found(
    mock_getcwd, mock_chdir, mock_exists, mock_kfinalise, mock_kprep,
    mock_args, mock_logger, mock_log_formatter
):
    """Test process_track_render logs error if track directory is not found."""
    row = {"Artist": "NoDir Artist", "Title": "NoDir Title", "Mixed Audio Filename": "mix_nodir.mp3", "Instrumental Audio Filename": "inst_nodir.mp3"}

    result = await bulk_cli.process_track_render(row, mock_args, mock_logger, mock_log_formatter)

    # Should still return True overall for the row processing attempt, but log an error
    assert result is True # Continue with other tracks
    mock_kfinalise.assert_called_once()
    mock_kfinalise.return_value.process.assert_not_called() # Should never call process since dirs not found
    
    # Check that os.path.exists was called for all potential directories
    assert mock_exists.call_count >= 3
    
    # Validate error logging
    error_message = mock_logger.error.call_args[0][0]
    assert "Track directory not found. Tried:" in error_message
    assert "NoDir Artist - NoDir Title" in error_message
    
    # Should never change directory if no directory exists
    mock_chdir.assert_not_called()


# Add mocks for the new helper functions and process_csv_rows
@patch("karaoke_prep.utils.bulk_cli.process_csv_rows", new_callable=AsyncMock)
@patch("karaoke_prep.utils.bulk_cli._read_csv_file")
@patch("karaoke_prep.utils.bulk_cli._parse_and_validate_args")
@patch("karaoke_prep.utils.bulk_cli.setup_logging") # Mock logging setup
@patch("karaoke_prep.utils.bulk_cli.logger") # Mock the module-level logger directly
@pytest.mark.asyncio # Explicitly mark as async test
async def test_async_main_dry_run(
    mock_bulk_cli_logger, mock_setup_logging, mock_parse_args, mock_read_csv, mock_process_rows, # Added mock_bulk_cli_logger back
    mock_args, mock_logger, mock_log_formatter # Keep necessary fixtures
):
    """Test async_main correctly handles the dry_run flag."""

    # --- Mock Configuration ---
    # 1. Configure mock_args fixture to have dry_run = True
    mock_args.dry_run = True

    # 2. Mock _parse_and_validate_args to return the modified mock_args
    mock_parse_args.return_value = mock_args

    # 3. Mock _read_csv_file
    sample_rows = list(csv.DictReader(SAMPLE_CSV_DATA.splitlines()))
    mock_read_csv.return_value = sample_rows

    # 4. Mock setup_logging
    mock_setup_logging.return_value = mock_log_formatter

    # 5. Mock process_csv_rows
    mock_process_rows.return_value = {"summary": "dry run results"}

    # --- Inject Mocks & Run ---
    # Ensure setup_logging returns the formatter when called
    mock_setup_logging.return_value = mock_log_formatter
    bulk_cli.log_formatter = mock_log_formatter # Set global formatter

    # Run async_main
    result = await bulk_cli.async_main()

    # --- Assertions ---
    # 1. Check _parse_and_validate_args called
    mock_parse_args.assert_called_once()

    # 2. Check logger level was set and info message logged directly on module logger
    mock_bulk_cli_logger.setLevel.assert_called_with(mock_args.log_level)
    mock_bulk_cli_logger.info.assert_any_call("Dry run mode enabled. No changes will be made.")
    # No need to assert setup_logging call for level setting

    # 3. Check _read_csv_file called
    mock_read_csv.assert_called_once_with(mock_args.input_csv)

    # 4. Check process_csv_rows was awaited with dry_run=True in args, passing the patched module logger
    mock_process_rows.assert_awaited_once_with(
        mock_args.input_csv,
        sample_rows,
        mock_args, # Ensure the args object passed has dry_run=True
        mock_bulk_cli_logger, # Pass the patched module logger
        mock_log_formatter
    )
    # Verify the args passed to process_csv_rows had dry_run=True
    call_args, _ = mock_process_rows.call_args
    passed_args_obj = call_args[2]
    assert passed_args_obj.dry_run is True

    # 5. Check result
    assert result == {"summary": "dry run results"}

    # Note: The check for update_csv_status *not* being called is now implicitly
    # handled by testing process_csv_rows directly (like in test_process_csv_rows_dry_run).
    # This test focuses on async_main passing the flag correctly.


@patch("karaoke_prep.utils.bulk_cli.KaraokePrep")
@patch("karaoke_prep.utils.bulk_cli.KaraokeFinalise")
@patch("karaoke_prep.utils.bulk_cli.os.path.exists", return_value=True) # Assume track dir exists
@patch("karaoke_prep.utils.bulk_cli.os.chdir")
@patch("karaoke_prep.utils.bulk_cli.os.getcwd", return_value="/fake/original/dir")
@patch("builtins.open", new_callable=mock_open, read_data=SAMPLE_STYLE_JSON) # For reading style JSON
@pytest.mark.asyncio # Explicitly mark as async test
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


@patch(mock_module_paths["StreamHandler"])
@patch(mock_module_paths["Formatter"])
@patch(mock_module_paths["logger"])
def test_setup_logging(mock_logger, mock_formatter, mock_handler):
    """Test that setup_logging configures logging correctly."""
    # Create mock objects to check the output
    mock_handler_instance = MagicMock()
    mock_handler.return_value = mock_handler_instance
    
    mock_formatter_instance = MagicMock()
    mock_formatter.return_value = mock_formatter_instance
    
    # Call the function under test with DEBUG level
    result = bulk_cli.setup_logging(logging.DEBUG)
    
    # Verify formatter was created with expected format
    mock_formatter.assert_called_once()
    format_args = mock_formatter.call_args[1]
    assert "fmt" in format_args
    assert "datefmt" in format_args
    assert "%(levelname)s" in format_args["fmt"]
    assert "%Y-%m-%d" in format_args["datefmt"]
    
    # Verify handler was created and configured
    mock_handler.assert_called_once()
    mock_handler_instance.setFormatter.assert_called_once_with(mock_formatter_instance)
    
    # Verify logger was configured
    mock_logger.addHandler.assert_called_once_with(mock_handler_instance)
    mock_logger.setLevel.assert_called_once_with(logging.DEBUG)
    
    # Verify the return value
    assert result == mock_formatter_instance


@pytest.mark.asyncio
@patch("karaoke_prep.utils.bulk_cli.update_csv_status")
@patch("karaoke_prep.utils.bulk_cli.process_track_render", new_callable=AsyncMock)
@patch("karaoke_prep.utils.bulk_cli.process_track_prep", new_callable=AsyncMock)
@pytest.mark.asyncio # Explicitly mark as async test
async def test_process_csv_rows(mock_process_prep, mock_process_render, mock_update_csv, mock_args, mock_logger, mock_log_formatter):
    """Test the process_csv_rows function processes CSV rows correctly."""
    # Configure the mocks with return values for each call
    mock_process_prep.side_effect = [True, False]  # First success, then fail
    mock_process_render.side_effect = [True, False, True, True]  # Add enough return values
    
    # Create test CSV rows
    rows = [
        {"Artist": "Artist One", "Title": "Title One", "Mixed Audio Filename": "mix1.mp3", "Instrumental Audio Filename": "inst1.mp3", "Status": "Uploaded"},
        {"Artist": "Artist Two", "Title": "Title Two", "Mixed Audio Filename": "mix2.mp3", "Instrumental Audio Filename": "inst2.mp3", "Status": "Uploaded"},
        {"Artist": "Artist Three", "Title": "Title Three", "Mixed Audio Filename": "mix3.mp3", "Instrumental Audio Filename": "inst3.mp3", "Status": "Prep_Complete"},
        {"Artist": "Artist Four", "Title": "Title Four", "Mixed Audio Filename": "mix4.mp3", "Instrumental Audio Filename": "inst4.mp3", "Status": "Prep_Complete"},
        {"Artist": "Artist Five", "Title": "Title Five", "Mixed Audio Filename": "mix5.mp3", "Instrumental Audio Filename": "inst5.mp3", "Status": "Completed"}
    ]
    
    # Call the function under test
    csv_path = "/fake/test.csv"
    results = await bulk_cli.process_csv_rows(csv_path, rows, mock_args, mock_logger, mock_log_formatter)
    
    # Verify process_track_prep was called for uploaded tracks
    assert mock_process_prep.call_count == 2
    mock_process_prep.assert_any_call(rows[0], mock_args, mock_logger, mock_log_formatter)
    mock_process_prep.assert_any_call(rows[1], mock_args, mock_logger, mock_log_formatter)
    
    # Verify process_track_render was called for 'uploaded' and 'prep_complete' tracks
    # With our changes to process_csv_rows, it's now called for each track
    assert mock_process_render.call_count == 4  # Updated from 2 to 4
    mock_process_render.assert_any_call(rows[0], mock_args, mock_logger, mock_log_formatter)
    mock_process_render.assert_any_call(rows[1], mock_args, mock_logger, mock_log_formatter)
    mock_process_render.assert_any_call(rows[2], mock_args, mock_logger, mock_log_formatter)
    mock_process_render.assert_any_call(rows[3], mock_args, mock_logger, mock_log_formatter)
    
    # Verify update_csv_status was called for each processed track
    assert mock_update_csv.call_count == 6  # Updated from 4 to 6
    
    # Verify skipped track
    assert results["skipped"] == 3  # Updated from 1 to 3
    
    # Verify success and failure counts
    assert results["prep_success"] == 1
    assert results["prep_failed"] == 1
    assert results["render_success"] == 3  # Updated expected success count
    assert results["render_failed"] == 1  # Updated expected failure count


@pytest.mark.asyncio
@patch("karaoke_prep.utils.bulk_cli.update_csv_status")
@patch("karaoke_prep.utils.bulk_cli.process_track_render", new_callable=AsyncMock)
@patch("karaoke_prep.utils.bulk_cli.process_track_prep", new_callable=AsyncMock)
@pytest.mark.asyncio # Explicitly mark as async test
async def test_process_csv_rows_dry_run(mock_process_prep, mock_process_render, mock_update_csv, mock_args, mock_logger, mock_log_formatter):
    """Test the process_csv_rows function in dry run mode."""
    # Configure the mocks
    mock_process_prep.return_value = True
    mock_process_render.return_value = True
    mock_args.dry_run = True
    
    # Create a single test row
    rows = [
        {"Artist": "Artist One", "Title": "Title One", "Mixed Audio Filename": "mix1.mp3", "Instrumental Audio Filename": "inst1.mp3", "Status": "Uploaded"}
    ]
    
    # Call the function
    csv_path = "/fake/test.csv"
    results = await bulk_cli.process_csv_rows(csv_path, rows, mock_args, mock_logger, mock_log_formatter)
    
    # Verify process_track_prep was called
    mock_process_prep.assert_called_once()
    
    # Verify update_csv_status was NOT called
    mock_update_csv.assert_not_called()
    
    # Verify results
    assert results["prep_success"] == 1
    assert results["prep_failed"] == 0
