import pytest
import os
import shlex
from unittest.mock import patch, MagicMock, call

# Update imports to use the new MediaProcessor class
from karaoke_prep.karaoke_finalise.media_processor import MediaProcessor
from .test_initialization import mock_logger, MINIMAL_CONFIG # Reuse fixtures
from .test_file_input_validation import BASE_NAME, TITLE_MOV, END_MOV, WITH_VOCALS_MOV, INSTRUMENTAL_FLAC # Reuse constants

# Define expected output filenames for convenience
OUTPUT_FILES = {
    "karaoke_mp4": f"{BASE_NAME} (Karaoke).mp4",
    "with_vocals_mp4": f"{BASE_NAME} (With Vocals).mp4",
    "final_karaoke_lossless_mp4": f"{BASE_NAME} (Final Karaoke Lossless 4k).mp4",
    "final_karaoke_lossless_mkv": f"{BASE_NAME} (Final Karaoke Lossless 4k).mkv",
    "final_karaoke_lossy_mp4": f"{BASE_NAME} (Final Karaoke Lossy 4k).mp4",
    "final_karaoke_lossy_720p_mp4": f"{BASE_NAME} (Final Karaoke Lossy 720p).mp4",
}

INPUT_FILES = {
    "title_mov": TITLE_MOV,
    "instrumental_audio": INSTRUMENTAL_FLAC,
    # end_mov is added conditionally in tests
}

@pytest.fixture
def processor_with_aac(mock_logger):
    """Fixture for a MediaProcessor specifically with 'aac' codec."""
    with patch.object(MediaProcessor, 'detect_best_aac_codec', return_value='aac'):
        processor = MediaProcessor(logger=mock_logger, dry_run=MINIMAL_CONFIG["dry_run"], non_interactive=MINIMAL_CONFIG["non_interactive"])
    return processor

@pytest.fixture
def processor_with_aac_at(mock_logger):
    """Fixture for a MediaProcessor specifically with 'aac_at' codec."""
    with patch.object(MediaProcessor, 'detect_best_aac_codec', return_value='aac_at'):
        processor = MediaProcessor(logger=mock_logger, dry_run=MINIMAL_CONFIG["dry_run"], non_interactive=MINIMAL_CONFIG["non_interactive"])
    return processor

# --- execute_command Tests ---

@patch('os.system')
def test_execute_command_runs_command(mock_system, processor_with_aac):
    """Test execute_command calls os.system."""
    command = "echo 'test'"
    description = "Running test command"
    processor_with_aac.execute_command(command, description)
    mock_system.assert_called_once_with(command)
    processor_with_aac.logger.info.assert_any_call(description)
    processor_with_aac.logger.info.assert_any_call(f"Running command: {command}")

@patch('os.system')
def test_execute_command_dry_run(mock_system, processor_with_aac):
    """Test execute_command logs but doesn't run in dry run mode."""
    processor_with_aac.dry_run = True
    command = "echo 'test'"
    description = "Running test command"
    processor_with_aac.execute_command(command, description)
    mock_system.assert_not_called()
    processor_with_aac.logger.info.assert_any_call(description)
    processor_with_aac.logger.info.assert_any_call(f"DRY RUN: Would run command: {command}")

# --- prepare_concat_filter Tests ---

@patch('os.path.isfile', return_value=False)
def test_prepare_concat_filter_no_end_mov(mock_isfile, processor_with_aac):
    """Test concat filter without end_mov."""
    input_files_no_end = INPUT_FILES.copy()
    env_mov_input, ffmpeg_filter = processor_with_aac.prepare_concat_filter(input_files_no_end)
    assert env_mov_input == ""
    assert ffmpeg_filter == '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]"'
    mock_isfile.assert_not_called() # Should not check if key not present

@patch('os.path.isfile', return_value=True)
@patch('shlex.quote', side_effect=lambda x: f"'{x}'") # Simple quote mock
@patch('os.path.abspath', side_effect=lambda x: f"/abs/path/{x}") # Simple abspath mock
def test_prepare_concat_filter_with_end_mov(mock_abspath, mock_quote, mock_isfile, processor_with_aac):
    """Test concat filter with end_mov."""
    input_files_with_end = INPUT_FILES.copy()
    input_files_with_end["end_mov"] = END_MOV

    env_mov_input, ffmpeg_filter = processor_with_aac.prepare_concat_filter(input_files_with_end)

    expected_end_mov_path = '/abs/path/' + END_MOV
    mock_isfile.assert_called_once_with(END_MOV)
    mock_abspath.assert_called_once_with(END_MOV)
    mock_quote.assert_called_once_with(expected_end_mov_path)

    assert env_mov_input == f"-i '{expected_end_mov_path}'"
    assert ffmpeg_filter == '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0][2:v:0][2:a:0]concat=n=3:v=1:a=1[outv][outa]"'
    processor_with_aac.logger.info.assert_called_with(f"Found end_mov file: {END_MOV}, including in final MP4")


# --- Individual Encoding Method Tests ---

@patch.object(MediaProcessor, 'execute_command')
def test_remux_with_instrumental(mock_execute, processor_with_aac):
    """Test remux_with_instrumental command."""
    processor_with_aac.remux_with_instrumental(WITH_VOCALS_MOV, INSTRUMENTAL_FLAC, OUTPUT_FILES["karaoke_mp4"])
    expected_cmd = (
        f'{processor_with_aac.ffmpeg_base_command} -an -i "{WITH_VOCALS_MOV}" '
        f'-vn -i "{INSTRUMENTAL_FLAC}" -c:v copy -c:a pcm_s16le "{OUTPUT_FILES["karaoke_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Remuxing video with instrumental audio")

@patch.object(MediaProcessor, 'execute_command')
def test_convert_mov_to_mp4_aac(mock_execute, processor_with_aac):
    """Test convert_mov_to_mp4 command with basic aac codec."""
    processor_with_aac.convert_mov_to_mp4(WITH_VOCALS_MOV, OUTPUT_FILES["with_vocals_mp4"])
    expected_cmd = (
        f'{processor_with_aac.ffmpeg_base_command} -i "{WITH_VOCALS_MOV}" '
        f'-c:v libx264 -c:a aac {processor_with_aac.mp4_flags} "{OUTPUT_FILES["with_vocals_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Converting MOV video to MP4")

@patch.object(MediaProcessor, 'execute_command')
def test_convert_mov_to_mp4_aac_at(mock_execute, processor_with_aac_at):
    """Test convert_mov_to_mp4 command with aac_at codec."""
    processor_with_aac_at.convert_mov_to_mp4(WITH_VOCALS_MOV, OUTPUT_FILES["with_vocals_mp4"])
    expected_cmd = (
        f'{processor_with_aac_at.ffmpeg_base_command} -i "{WITH_VOCALS_MOV}" '
        f'-c:v libx264 -c:a aac_at {processor_with_aac_at.mp4_flags} "{OUTPUT_FILES["with_vocals_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Converting MOV video to MP4")

@patch.object(MediaProcessor, 'execute_command')
@patch('shlex.quote', side_effect=lambda x: f"'{x}'") # Mock quoting for consistency
def test_encode_lossless_mp4(mock_quote, mock_execute, processor_with_aac):
    """Test encode_lossless_mp4 command."""
    # Simulate how paths would be prepared by the calling function
    quoted_title_mov = shlex.quote(TITLE_MOV)
    quoted_karaoke_mp4 = shlex.quote(OUTPUT_FILES["karaoke_mp4"])
    env_mov_input = "-i 'end.mov'" # Assume end mov path is already prepared/quoted if present
    ffmpeg_filter = '-filter_complex "[concat]"'

    processor_with_aac.encode_lossless_mp4(
        quoted_title_mov, quoted_karaoke_mp4, env_mov_input, ffmpeg_filter, OUTPUT_FILES["final_karaoke_lossless_mp4"]
    )
    # Construct expected command using the quoted paths
    expected_cmd = (
        f"{processor_with_aac.ffmpeg_base_command} -i {quoted_title_mov} -i {quoted_karaoke_mp4} {env_mov_input} "
        f'{ffmpeg_filter} -map "[outv]" -map "[outa]" -c:v libx264 -c:a pcm_s16le '
        f'{processor_with_aac.mp4_flags} "{OUTPUT_FILES["final_karaoke_lossless_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Creating MP4 version with PCM audio")

@patch.object(MediaProcessor, 'execute_command')
def test_encode_lossy_mp4_aac(mock_execute, processor_with_aac):
    """Test encode_lossy_mp4 command with basic aac."""
    processor_with_aac.encode_lossy_mp4(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossy_mp4"])
    expected_cmd = (
        f'{processor_with_aac.ffmpeg_base_command} -i "{OUTPUT_FILES["final_karaoke_lossless_mp4"]}" '
        f'-c:v copy -c:a aac -b:a 320k {processor_with_aac.mp4_flags} "{OUTPUT_FILES["final_karaoke_lossy_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Creating MP4 version with AAC audio")

@patch.object(MediaProcessor, 'execute_command')
def test_encode_lossy_mp4_aac_at(mock_execute, processor_with_aac_at):
    """Test encode_lossy_mp4 command with aac_at."""
    processor_with_aac_at.encode_lossy_mp4(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossy_mp4"])
    expected_cmd = (
        f'{processor_with_aac_at.ffmpeg_base_command} -i "{OUTPUT_FILES["final_karaoke_lossless_mp4"]}" '
        f'-c:v copy -c:a aac_at -b:a 320k {processor_with_aac_at.mp4_flags} "{OUTPUT_FILES["final_karaoke_lossy_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Creating MP4 version with AAC audio")

@patch.object(MediaProcessor, 'execute_command')
def test_encode_lossless_mkv(mock_execute, processor_with_aac):
    """Test encode_lossless_mkv command."""
    processor_with_aac.encode_lossless_mkv(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossless_mkv"])
    expected_cmd = (
        f'{processor_with_aac.ffmpeg_base_command} -i "{OUTPUT_FILES["final_karaoke_lossless_mp4"]}" '
        f'-c:v copy -c:a flac "{OUTPUT_FILES["final_karaoke_lossless_mkv"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Creating MKV version with FLAC audio for YouTube")

@patch.object(MediaProcessor, 'execute_command')
def test_encode_720p_version_aac(mock_execute, processor_with_aac):
    """Test encode_720p_version command with basic aac."""
    processor_with_aac.encode_720p_version(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossy_720p_mp4"])
    expected_cmd = (
        f'{processor_with_aac.ffmpeg_base_command} -i "{OUTPUT_FILES["final_karaoke_lossless_mp4"]}" '
        f'-c:v libx264 -vf "scale=1280:720" -b:v 200k -preset medium -tune animation '
        f'-c:a aac -b:a 128k {processor_with_aac.mp4_flags} "{OUTPUT_FILES["final_karaoke_lossy_720p_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Encoding 720p version of the final video")

@patch.object(MediaProcessor, 'execute_command')
def test_encode_720p_version_aac_at(mock_execute, processor_with_aac_at):
    """Test encode_720p_version command with aac_at."""
    processor_with_aac_at.encode_720p_version(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossy_720p_mp4"])
    expected_cmd = (
        f'{processor_with_aac_at.ffmpeg_base_command} -i "{OUTPUT_FILES["final_karaoke_lossless_mp4"]}" '
        f'-c:v libx264 -vf "scale=1280:720" -b:v 200k -preset medium -tune animation '
        f'-c:a aac_at -b:a 128k {processor_with_aac_at.mp4_flags} "{OUTPUT_FILES["final_karaoke_lossy_720p_mp4"]}"'
    )
    mock_execute.assert_called_once_with(expected_cmd, "Encoding 720p version of the final video")


# --- remux_and_encode_output_video_files Tests ---

@patch('os.path.isfile')
@patch('os.remove')
@patch('shlex.quote', side_effect=lambda x: f"'{x}'")
@patch('os.path.abspath', side_effect=lambda x: f"/abs/path/{x}")
@patch.object(MediaProcessor, 'remux_with_instrumental')
@patch.object(MediaProcessor, 'convert_mov_to_mp4')
@patch.object(MediaProcessor, 'prepare_concat_filter')
@patch.object(MediaProcessor, 'encode_lossless_mp4')
@patch.object(MediaProcessor, 'encode_lossy_mp4')
@patch.object(MediaProcessor, 'encode_lossless_mkv')
@patch.object(MediaProcessor, 'encode_720p_version')
def test_remux_and_encode_all_steps_mov_input(
    mock_encode_720p, mock_encode_mkv, mock_encode_lossy,
    mock_encode_lossless, mock_prepare_filter, mock_convert_mov, mock_remux,
    mock_abspath, mock_quote, mock_remove, mock_isfile, processor_with_aac):
    """Test the full remux/encode process with a .mov input requiring conversion."""

    # Create a mock UserInterface that returns True for all prompts
    mock_user_interface = MagicMock()
    mock_user_interface.prompt_user_bool.return_value = True
    mock_user_interface.prompt_user_confirmation_or_raise_exception.return_value = True

    # Simulate output files exist to trigger overwrite prompt
    mock_isfile.side_effect = lambda f: f in [
        OUTPUT_FILES["final_karaoke_lossless_mp4"],
        OUTPUT_FILES["final_karaoke_lossless_mkv"],
        INPUT_FILES["title_mov"],
        END_MOV,
        WITH_VOCALS_MOV
    ]

    # Mock prepare_concat_filter to return specific values
    mock_env_mov_input = f"-i '/abs/path/{END_MOV}'"
    mock_ffmpeg_filter = '-filter_complex "[concat_3]"'
    mock_prepare_filter.return_value = (mock_env_mov_input, mock_ffmpeg_filter)

    input_files_with_end = INPUT_FILES.copy()
    input_files_with_end["end_mov"] = END_MOV

    processor_with_aac.remux_and_encode_output_video_files(WITH_VOCALS_MOV, input_files_with_end, OUTPUT_FILES, user_interface=mock_user_interface)

    # Check file existence check
    mock_isfile.assert_any_call(OUTPUT_FILES["final_karaoke_lossless_mp4"])
    mock_isfile.assert_any_call(OUTPUT_FILES["final_karaoke_lossless_mkv"])
    
    # Verify prompt was called
    mock_user_interface.prompt_user_bool.assert_called_once()

    # Check steps called in order
    mock_remux.assert_called_once_with(WITH_VOCALS_MOV, input_files_with_end["instrumental_audio"], OUTPUT_FILES["karaoke_mp4"])
    mock_convert_mov.assert_called_once_with(WITH_VOCALS_MOV, OUTPUT_FILES["with_vocals_mp4"])
    mock_remove.assert_called_once_with(WITH_VOCALS_MOV) # Original MOV deleted
    mock_prepare_filter.assert_called_once_with(input_files_with_end)

    # Explicitly define expected quoted paths based on mocks
    expected_quoted_title_mov = f"'/abs/path/{INPUT_FILES['title_mov']}'"
    expected_quoted_karaoke_mp4 = f"'/abs/path/{OUTPUT_FILES['karaoke_mp4']}'"

    mock_encode_lossless.assert_called_once_with(
        expected_quoted_title_mov,
        expected_quoted_karaoke_mp4,
        mock_env_mov_input,
        mock_ffmpeg_filter,
        OUTPUT_FILES["final_karaoke_lossless_mp4"]
    )
    mock_encode_lossy.assert_called_once_with(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossy_mp4"])
    mock_encode_mkv.assert_called_once_with(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossless_mkv"])
    mock_encode_720p.assert_called_once_with(OUTPUT_FILES["final_karaoke_lossless_mp4"], OUTPUT_FILES["final_karaoke_lossy_720p_mp4"])
    mock_user_interface.prompt_user_confirmation_or_raise_exception.assert_called_once() # Final check prompt

@patch('os.path.isfile')
@patch('os.remove')
@patch.object(MediaProcessor, 'remux_with_instrumental')
@patch.object(MediaProcessor, 'convert_mov_to_mp4')
def test_remux_and_encode_mp4_input(
    mock_convert_mov, mock_remux, mock_remove, mock_isfile, processor_with_aac):
    """Test the remux/encode process skips conversion for .mp4 input."""
    # Create a mock UserInterface
    mock_user_interface = MagicMock()
    mock_user_interface.prompt_user_bool.return_value = True
    mock_user_interface.prompt_user_confirmation_or_raise_exception.return_value = True
    
    mock_isfile.return_value = False # Output files don't exist

    # Use MP4 as input
    with_vocals_mp4 = f"{BASE_NAME} (With Vocals).mp4"

    # Patch all the encoding methods
    with patch.object(MediaProcessor, 'prepare_concat_filter', return_value=("", "-filter")) as mock_prepare,\
         patch.object(MediaProcessor, 'encode_lossless_mp4') as mock_lossless,\
         patch.object(MediaProcessor, 'encode_lossy_mp4') as mock_lossy,\
         patch.object(MediaProcessor, 'encode_lossless_mkv') as mock_mkv,\
         patch.object(MediaProcessor, 'encode_720p_version') as mock_720p:
        
        processor_with_aac.remux_and_encode_output_video_files(with_vocals_mp4, INPUT_FILES, OUTPUT_FILES, user_interface=mock_user_interface)

    mock_remux.assert_called_once()
    mock_convert_mov.assert_not_called() # Should skip conversion
    mock_remove.assert_not_called() # Should not delete input MP4

@patch('os.path.isfile', return_value=True) # Files exist
@patch.object(MediaProcessor, 'remux_with_instrumental')
@patch.object(MediaProcessor, 'convert_mov_to_mp4')
@patch.object(MediaProcessor, 'encode_lossless_mp4')
@patch.object(MediaProcessor, 'encode_lossy_mp4')
@patch.object(MediaProcessor, 'encode_lossless_mkv')
@patch.object(MediaProcessor, 'encode_720p_version')
def test_remux_and_encode_skip_overwrite(
    mock_encode_720p, mock_encode_mkv, mock_encode_lossy, mock_encode_lossless,
    mock_convert_mov, mock_remux, mock_isfile, processor_with_aac):
    """Test skipping encoding steps if user chooses not to overwrite."""
    
    # Create a mock UserInterface that returns False for the overwrite prompt
    mock_user_interface = MagicMock()
    mock_user_interface.prompt_user_bool.return_value = False
    
    processor_with_aac.remux_and_encode_output_video_files(WITH_VOCALS_MOV, INPUT_FILES, OUTPUT_FILES, user_interface=mock_user_interface)

    mock_isfile.assert_any_call(OUTPUT_FILES["final_karaoke_lossless_mp4"])
    mock_isfile.assert_any_call(OUTPUT_FILES["final_karaoke_lossless_mkv"])
    mock_user_interface.prompt_user_bool.assert_called_once() # Asked to overwrite
    
    # Ensure no encoding steps were called
    mock_remux.assert_not_called()
    mock_convert_mov.assert_not_called()
    mock_encode_lossless.assert_not_called()
    mock_encode_lossy.assert_not_called()
    mock_encode_mkv.assert_not_called()
    mock_encode_720p.assert_not_called()

# --- AAC Codec Detection Tests ---

@patch('os.popen')
def test_detect_best_aac_codec_aac_at(mock_popen, mock_logger):
    """Test detection of aac_at codec."""
    mock_popen.return_value.read.return_value = "Codecs:\n D..... aac\n DEA.L. aac_at\n D..... libfdk_aac"
    processor = MediaProcessor(logger=mock_logger, dry_run=MINIMAL_CONFIG["dry_run"], non_interactive=MINIMAL_CONFIG["non_interactive"])
    assert processor.aac_codec == "aac_at"
    mock_logger.info.assert_any_call("Using aac_at codec (best quality)")

@patch('os.popen')
def test_detect_best_aac_codec_libfdk_aac(mock_popen, mock_logger):
    """Test detection of libfdk_aac codec when aac_at is not present."""
    mock_popen.return_value.read.return_value = "Codecs:\n D..... aac\n D..... libfdk_aac"
    processor = MediaProcessor(logger=mock_logger, dry_run=MINIMAL_CONFIG["dry_run"], non_interactive=MINIMAL_CONFIG["non_interactive"])
    assert processor.aac_codec == "libfdk_aac"
    mock_logger.info.assert_any_call("Using libfdk_aac codec (good quality)")

@patch('os.popen')
def test_detect_best_aac_codec_aac_default(mock_popen, mock_logger):
    """Test detection falls back to basic aac codec."""
    mock_popen.return_value.read.return_value = "Codecs:\n D..... aac"
    processor = MediaProcessor(logger=mock_logger, dry_run=MINIMAL_CONFIG["dry_run"], non_interactive=MINIMAL_CONFIG["non_interactive"])
    assert processor.aac_codec == "aac"
    mock_logger.info.assert_any_call("Using built-in aac codec (basic quality)")

@patch('os.popen')
def test_detect_best_aac_codec_none_found(mock_popen, mock_logger):
    """Test detection falls back to basic aac when no AAC codecs are listed."""
    mock_popen.return_value.read.return_value = "Codecs:\n D..... mp3\n D..... flac"
    processor = MediaProcessor(logger=mock_logger, dry_run=MINIMAL_CONFIG["dry_run"], non_interactive=MINIMAL_CONFIG["non_interactive"])
    assert processor.aac_codec == "aac"
    mock_logger.info.assert_any_call("Using built-in aac codec (basic quality)")
