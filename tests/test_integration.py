import os
import pytest
import tempfile
import shutil
import subprocess
import sys
import json
from karaoke_prep.karaoke_prep import KaraokePrep
from unittest.mock import MagicMock, call, patch, AsyncMock, ANY
from karaoke_prep.utils.gen_cli import async_main
import shlex
import asyncio
from googleapiclient.http import MediaFileUpload
from karaoke_prep.karaoke_finalise.karaoke_finalise import KaraokeFinalise

# Register the asyncio marker
pytest.mark.asyncio = pytest.mark.asyncio

# Set the default event loop policy to 'auto'
pytest_configure = lambda config: config.addinivalue_line("markers", "asyncio: mark test as async")


@pytest.mark.asyncio
async def test_karaoke_prep_integration():
    # Create a temporary directory for test outputs
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create a dummy input file (e.g., a small WAV file)
        input_file = os.path.join(temp_dir, "input.wav")
        # Use ffmpeg to generate a small WAV file with a sine wave
        subprocess.run(["ffmpeg", "-f", "lavfi", "-i", "sine=frequency=1000:duration=1", input_file], check=True)

        # Instantiate KaraokePrep with the dummy input file
        kp = KaraokePrep(
            input_media=input_file,
            artist="Test Artist",
            title="Test Title",
            output_dir=temp_dir,
            skip_lyrics=True,  # Skip lyrics processing for this test
            skip_separation=True,  # Skip audio separation for this test
            dry_run=False,
            log_level="INFO"
        )

        # Function to simulate file creation
        def create_dummy_files(output_image_filepath_noext, output_video_filepath, **kwargs):
            # Create empty files for PNG, JPG, and MOV
            for ext in ['.png', '.jpg']:
                try:
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(f"{output_image_filepath_noext}{ext}"), exist_ok=True)
                    with open(f"{output_image_filepath_noext}{ext}", 'w') as f:
                        f.write('dummy') # Write something small
                except Exception as e:
                     print(f"Error creating dummy file {output_image_filepath_noext}{ext}: {e}") # Debug print
            try:
                # Ensure directory exists
                os.makedirs(os.path.dirname(output_video_filepath), exist_ok=True)
                with open(output_video_filepath, 'w') as f:
                    f.write('dummy') # Write something small
            except Exception as e:
                print(f"Error creating dummy file {output_video_filepath}: {e}") # Debug print

        # Function to simulate WAV creation
        def create_dummy_wav(input_media_path, output_filename_no_extension):
            wav_path = f"{output_filename_no_extension} ({kp.extractor}).wav" # Construct expected path
            try:
                os.makedirs(os.path.dirname(wav_path), exist_ok=True)
                with open(wav_path, 'w') as f:
                    f.write('dummy_wav') # Write something small
                return wav_path # Return the created path
            except Exception as e:
                print(f"Error creating dummy WAV file {wav_path}: {e}")
                return None # Indicate failure

        # Mock external dependencies and handler methods
        with patch('karaoke_prep.metadata.extract_info_for_online_media') as mock_extract, \
             patch('karaoke_prep.metadata.parse_track_metadata') as mock_parse, \
             patch.object(kp.file_handler, 'setup_output_paths', return_value=(os.path.join(temp_dir, "Test Artist - Test Title"), "Test Artist - Test Title")) as mock_setup_paths, \
             patch.object(kp.file_handler, 'copy_input_media', return_value="copied.mp4") as mock_copy, \
             patch.object(kp.file_handler, 'convert_to_wav', side_effect=create_dummy_wav) as mock_convert, \
             patch.object(kp.file_handler, 'download_video') as mock_download, \
             patch.object(kp.file_handler, 'extract_still_image_from_video') as mock_extract_image, \
             patch.object(kp.file_handler, '_file_exists', return_value=False) as mock_file_exists, \
             patch.object(kp.lyrics_processor, 'transcribe_lyrics', AsyncMock(return_value={'corrected_lyrics_text': 'lyrics text', 'corrected_lyrics_text_filepath': 'lyrics.txt'})) as mock_transcribe, \
             patch.object(kp.audio_processor, 'process_audio_separation', AsyncMock(return_value={})) as mock_separate, \
             patch.object(kp.video_generator, 'create_title_video', side_effect=create_dummy_files) as mock_create_title, \
             patch.object(kp.video_generator, 'create_end_video', side_effect=create_dummy_files) as mock_create_end, \
             patch('os.system') as mock_os_system:

            # Run the process
            results = await kp.process()

        # Verify that the result is a list (even for a single track)
        assert isinstance(results, list)
        assert len(results) > 0

        # Get the first track result
        track = results[0]
        assert isinstance(track, dict)
        assert "track_output_dir" in track
        assert "artist" in track
        assert "title" in track

        # Verify mocks were called as expected
        mock_transcribe.assert_not_called()
        mock_separate.assert_not_called()
        mock_create_title.assert_called_once() # Check if video creation was called
        mock_create_end.assert_called_once()   # Check if video creation was called

        # Verify that the expected output files exist and have non-zero sizes
        expected_files = [
            os.path.join(track["track_output_dir"], f"{track['artist']} - {track['title']} (Title).mov"),
            os.path.join(track["track_output_dir"], f"{track['artist']} - {track['title']} (End).mov"),
            os.path.join(track["track_output_dir"], f"{track['artist']} - {track['title']} (Title).png"),
            os.path.join(track["track_output_dir"], f"{track['artist']} - {track['title']} (Title).jpg"),
            os.path.join(track["track_output_dir"], f"{track['artist']} - {track['title']} (End).png"),
            os.path.join(track["track_output_dir"], f"{track['artist']} - {track['title']} (End).jpg")
        ]

        for file_path in expected_files:
            assert os.path.exists(file_path), f"Expected file {file_path} does not exist."
            assert os.path.getsize(file_path) > 0, f"Expected file {file_path} is empty."

        # Optional: Verify that the input audio WAV file was created
        input_wav = track.get("input_audio_wav")
        if input_wav:
            assert os.path.exists(input_wav), f"Input WAV file {input_wav} does not exist."
            assert os.path.getsize(input_wav) > 0, f"Input WAV file {input_wav} is empty."

        # Optional: Verify that the separated audio files exist (if not skipped)
        if not kp.skip_separation:
            separated_audio = track.get("separated_audio", {})
            for category, files in separated_audio.items():
                if isinstance(files, dict):
                    for file_path in files.values():
                        if file_path:
                            assert os.path.exists(file_path), f"Separated audio file {file_path} does not exist."
                            assert os.path.getsize(file_path) > 0, f"Separated audio file {file_path} is empty."

        # Optional: Verify that the lyrics file exists (if not skipped)
        if not kp.skip_lyrics:
            lyrics_file = track.get("lyrics")
            if lyrics_file:
                assert os.path.exists(lyrics_file), f"Lyrics file {lyrics_file} does not exist."
                assert os.path.getsize(lyrics_file) > 0, f"Lyrics file {lyrics_file} is empty."

        # Clean up the temporary directory (optional, as it will be removed automatically)
        # shutil.rmtree(temp_dir) 


@pytest.mark.asyncio
@pytest.mark.slow
async def test_full_cli_integration(tmp_path, mocker):
    """Tests the full CLI workflow by calling async_main directly with mocked sys.argv."""

    # --- 1. Setup Temporary Directories and Files ---
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # output_dir = tmp_path / "output" # KaraokePrep will create this based on args
    # output_dir.mkdir()
    organised_dir = tmp_path / "organised"
    organised_dir.mkdir()
    public_share_dir = tmp_path / "public_share"
    public_share_dir.mkdir()
    public_share_mp4_dir = public_share_dir / "MP4"
    public_share_mp4_dir.mkdir()
    public_share_720p_dir = public_share_dir / "MP4-720p"
    public_share_720p_dir.mkdir()
    public_share_cdg_dir = public_share_dir / "CDG"
    public_share_cdg_dir.mkdir()

    # Copy input audio
    source_audio = "tests/data/waterloo10sec.flac"
    input_audio = data_dir / os.path.basename(source_audio)
    shutil.copy2(source_audio, input_audio)

    # Copy real style params file instead of creating dummy
    source_style_params = "tests/data/styles.json"
    style_params_path = data_dir / os.path.basename(source_style_params)
    shutil.copy2(source_style_params, style_params_path)

    # Create dummy youtube client secrets file
    yt_secrets_path = data_dir / "kgenclientsecret.json"
    yt_secrets_content = {"installed": {"client_id": "dummy", "client_secret": "dummy"}}
    with open(yt_secrets_path, "w") as f:
        json.dump(yt_secrets_content, f)

    # Create dummy youtube description file
    yt_desc_path = data_dir / "ytdesc.txt"
    with open(yt_desc_path, "w") as f:
        f.write("Test Description {artist} - {title}")

    # Create dummy email template file
    email_template_path = data_dir / "emailtemplate.txt"
    with open(email_template_path, "w") as f:
        f.write("Subject: Test Email\n\nYT: {youtube_url}\nDB: {dropbox_url}")

    # --- 2. Mock External Interactions ---
    # Mock YouTube API
    mock_youtube_service = MagicMock()
    mock_youtube_insert = MagicMock()
    mock_youtube_insert.execute.return_value = {'id': 'mock_video_id'}
    mock_youtube_service.videos().insert.return_value = mock_youtube_insert
    mock_youtube_service.thumbnails().set().execute.return_value = {}
    mock_build = mocker.patch('googleapiclient.discovery.build', return_value=mock_youtube_service)

    # Mock YouTube credential flow and existing video check
    mocker.patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.check_if_video_title_exists_on_youtube_channel', return_value=False)
    
    # Mock the upload_final_mp4_to_youtube_with_title_thumbnail method to directly return mock_video_id to bypass YouTube API issues
    mock_upload = mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.upload_final_mp4_to_youtube_with_title_thumbnail')
    # Set video_id and url attributes that would normally be set during upload
    def side_effect(*args, **kwargs):
        instance = args[0]  # First arg is self
        instance.youtube_video_id = 'manual_mock_video_id'
        instance.youtube_url = f"https://youtu.be/manual_mock_video_id"
    mock_upload.side_effect = side_effect
    
    # Keep the authenticate_youtube mock to return the service
    mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.authenticate_youtube', return_value=mock_youtube_service)

    # Mock Gmail API (reuse youtube mock for simplicity, just check call)
    mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.authenticate_gmail', return_value=mock_youtube_service)
    mock_draft_create = MagicMock()
    mock_draft_create.execute.return_value = {'id': 'mock_draft_id'}
    mock_youtube_service.users().drafts().create.return_value = mock_draft_create

    # Mock Discord requests
    mock_requests_post = mocker.patch('requests.post')
    mock_requests_post.return_value.raise_for_status.return_value = None

    # Store original functions needed for mocks
    original_os_system = os.system
    original_subprocess_run = subprocess.run
    original_os_chdir = os.chdir
    original_os_getcwd = os.getcwd
    original_os_listdir = os.listdir
    original_os_rename = os.rename

    # Mock os.system and subprocess.run for external calls (Rclone, ffmpeg etc)
    mock_os_system = mocker.patch('os.system')
    mock_subprocess_run = mocker.patch('subprocess.run')
    def rclone_side_effect(*args, **kwargs):
        # args[0] is the command (either string for os.system or list for subprocess.run)
        cmd_arg = args[0]
        cmd_str = cmd_arg if isinstance(cmd_arg, str) else " ".join(map(shlex.quote, cmd_arg))

        # --- Commands to execute with original subprocess ---
        execute_commands = ["ffmpeg", "ffprobe", "uname"]
        should_execute = False
        if isinstance(cmd_arg, list) and cmd_arg and cmd_arg[0] in execute_commands:
            should_execute = True
        elif isinstance(cmd_arg, str) and any(cmd in cmd_arg for cmd in execute_commands):
             # Be a bit careful with string matching for execute commands
             # Only execute if it clearly starts with ffmpeg etc.
             # This covers the os.system call for ffmpeg
             if cmd_arg.strip().startswith("ffmpeg"):
                 should_execute = True

        # Special handling for ffmpeg WAV conversion command - simulate creating WAV file instead of running actual ffmpeg
        if isinstance(cmd_arg, list) and len(cmd_arg) > 3 and cmd_arg[0] == "ffmpeg" and any(".wav" in arg for arg in cmd_arg):
            print(f"SIDE_EFFECT: Simulating ffmpeg WAV conversion instead of executing: {cmd_str}")
            # Extract the output WAV path
            output_wav_path = None
            for i, arg in enumerate(cmd_arg):
                if arg.endswith(".wav") and i > 0 and cmd_arg[i-1] != "-i":
                    output_wav_path = arg
                    break
                
            if output_wav_path:
                # Create the output directory if it doesn't exist
                os.makedirs(os.path.dirname(output_wav_path), exist_ok=True)
                # Create a dummy WAV file with minimal header (44 bytes, 8000Hz, mono, PCM)
                with open(output_wav_path, 'wb') as f:
                    # Simple WAV header + minimal audio data
                    f.write(b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00')
                    # Add some silence (1 second at 8000Hz)
                    f.write(b'\x80' * 8000)
                print(f"SIDE_EFFECT: Created dummy WAV file at {output_wav_path}")
                return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="", stderr="")
        
        # For other ffmpeg commands, or if we couldn't extract the WAV path, proceed to normal execution
        if should_execute:
            print(f"SIDE_EFFECT: Executing original: {cmd_str}")
            # Pass original args and kwargs to the original function
            # Use shell=True only if the original command was a string (likely from os.system)
            use_shell = isinstance(cmd_arg, str)
            result = None
            try:
                # Use original_subprocess_run for consistency, handling shell arg
                run_kwargs = kwargs.copy() # Copy kwargs to avoid modifying original

                # Remove our custom flag that subprocess.run doesn't understand
                if '_os_system_call' in run_kwargs:
                    del run_kwargs['_os_system_call']

                # Determine if output should be captured based on original kwargs or if it's ffmpeg/ffprobe
                should_capture = False
                if isinstance(cmd_arg, list) and cmd_arg[0] in ["ffmpeg", "ffprobe"]:
                    # Check if the original call already requested capture
                    if run_kwargs.get('stdout') == subprocess.PIPE or run_kwargs.get('stderr') == subprocess.PIPE or run_kwargs.get('capture_output'):
                        should_capture = True # Original call wants capture, let it happen
                        # Ensure we don't add capture_output=True if stdout/stderr are set
                        run_kwargs.pop('capture_output', None)
                    else:
                        # Original call didn't request capture, but we want to for logging
                        should_capture = True
                        run_kwargs['capture_output'] = True
                        run_kwargs['text'] = True # Assume text if we're capturing
                
                # Adjust run_kwargs based on capture decision
                if should_capture and 'capture_output' not in run_kwargs:
                    # If original used stdout/stderr=PIPE, we need text=True to decode
                    if run_kwargs.get('stdout') == subprocess.PIPE or run_kwargs.get('stderr') == subprocess.PIPE:
                         run_kwargs['text'] = True 

                # Get the mocked CWD for ffmpeg/ffprobe execution
                current_mocked_dir = mock_current_dir_state()
                print(f"SIDE_EFFECT: Executing {cmd_arg[0]} in mocked CWD: {current_mocked_dir}")

                # Call the original subprocess run within the mocked CWD
                result = original_subprocess_run(*args, shell=use_shell, cwd=current_mocked_dir, **run_kwargs)

                # Log results if captured
                if should_capture and hasattr(result, 'returncode'): # Check if it's a CompletedProcess
                    is_ffmpeg_or_probe = isinstance(cmd_arg, list) and cmd_arg[0] in ["ffmpeg", "ffprobe"]
                    
                    print(f"SIDE_EFFECT: Original {cmd_arg[0]} command finished. Return Code: {result.returncode}")
                    
                    # Print full ffmpeg/ffprobe args for debugging
                    if is_ffmpeg_or_probe:
                            print(f"SIDE_EFFECT: Full {cmd_arg[0]} Args: {cmd_arg}")

                    # Print stdout/stderr for ffmpeg/ffprobe even on success for detailed debugging
                    if is_ffmpeg_or_probe and result.stdout:
                         print(f"SIDE_EFFECT: {cmd_arg[0]} stdout (first 500 chars):\n{result.stdout[:500]}...")
                    if result.stderr: # Always print stderr if it exists
                         print(f"SIDE_EFFECT: {cmd_arg[0]} stderr (first 500 chars):\n{result.stderr[:500]}...")
                    elif result.returncode == 0 and not is_ffmpeg_or_probe:
                         print(f"SIDE_EFFECT: Original {cmd_arg[0]} executed successfully (No stderr).")
                     
                return result

            except Exception as e:
                print(f"SIDE_EFFECT: Error executing original command '{cmd_str}': {e}")
                # Log traceback for unexpected errors during subprocess execution
                import traceback
                print(traceback.format_exc())
                # Reraise or return an error code/object depending on context
                if isinstance(cmd_arg, str):
                    return 1
                else: # For subprocess.run mocks
                    return subprocess.CompletedProcess(args=cmd_arg if isinstance(cmd_arg, list) else [cmd_arg], returncode=1, stderr=str(e))

        # --- Rclone commands to mock ---
        # Rclone link (string from os.system OR subprocess.run with shell=True)
        if isinstance(cmd_arg, str) and cmd_arg.startswith('rclone link'):
            print(f"SIDE_EFFECT: Mocking rclone link (string cmd): {cmd_str}")
            # Return CompletedProcess even for string command if subprocess.run was likely used
            # Check if original call used subprocess.run (we can guess based on kwargs)
            is_subprocess_run = not kwargs.get('_os_system_call', False) # Add a flag or check args
            if is_subprocess_run:
                return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="https://fake.sharing.link/mock_folder", stderr="")
            else: # Assume os.system call
                return 0 # Simulate success code

        # Rclone link (list from subprocess.run without shell=True)
        elif isinstance(cmd_arg, list) and cmd_arg[0:2] == ['rclone', 'link']:
             print(f"SIDE_EFFECT: Mocking rclone link (list cmd): {cmd_str}")
             return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="https://fake.sharing.link/mock_folder", stderr="")

        # Rclone sync (string for os.system OR subprocess.run with shell=True)
        elif isinstance(cmd_arg, str) and cmd_arg.startswith('rclone sync'):
             print(f"SIDE_EFFECT: Mocking rclone sync (string cmd): {cmd_str}")
             is_subprocess_run = not kwargs.get('_os_system_call', False)
             if is_subprocess_run:
                return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="", stderr="")
             else: # Assume os.system call
                return 0 # Simulate success code

        # Rclone sync (list for subprocess.run without shell=True)
        elif isinstance(cmd_arg, list) and cmd_arg[0:2] == ['rclone', 'sync']:
             print(f"SIDE_EFFECT: Mocking rclone sync (list cmd): {cmd_str}")
             return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="", stderr="")

        # --- Default mock behavior for other commands (like 'open -a Audacity') ---
        print(f"SIDE_EFFECT: Default mock return for unhandled command: {cmd_str}")
        if isinstance(cmd_arg, list): # Likely from subprocess.run
            # Check if check=True was passed, raise if so, otherwise return success
            if kwargs.get('check'):
                 raise subprocess.CalledProcessError(returncode=1, cmd=cmd_arg, stderr="Mocked process failed check")
            return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="", stderr="")
        else: # Likely from os.system
            return 0 # Default success code

    # We need to differentiate calls to the side effect from os.system vs subprocess.run
    # A simple way is to wrap the side effect
    def os_system_wrapper(*args, **kwargs):
        # Create a copy of kwargs to avoid modifying the original
        kwargs_copy = kwargs.copy()
        kwargs_copy['_os_system_call'] = True
        return rclone_side_effect(*args, **kwargs_copy)

    def subprocess_run_wrapper(*args, **kwargs):
        # Create a copy of kwargs to avoid modifying the original
        kwargs_copy = kwargs.copy()
        kwargs_copy['_os_system_call'] = False
        return rclone_side_effect(*args, **kwargs_copy)

    mock_os_system.side_effect = os_system_wrapper
    mock_subprocess_run.side_effect = subprocess_run_wrapper

    # Mock pyperclip
    mock_pyperclip = mocker.patch('pyperclip.copy')

    # Mock os.chdir, os.getcwd, os.listdir, os.rename to simulate directory structure
    final_track_output_dir = tmp_path / "ABBA - Waterloo" # Predict the output dir path
    # Define base_name early so we can use it in the MediaFileUpload mock
    artist = "ABBA"
    title = "Waterloo"
    base_name = f"{artist} - {title}"
    
    # Create a simple mock for MediaFileUpload since we're bypassing the upload method
    mock_media_file_upload = MagicMock()
    mock_media_file_upload.filename.return_value = str(final_track_output_dir / f"{base_name} (Final Karaoke Lossless 4k).mkv")
    mocker.patch('googleapiclient.http.MediaFileUpload', return_value=mock_media_file_upload)
    
    # Use a separate mock object to hold the mocked current directory state
    # Initialize it with the actual starting CWD
    mock_current_dir_state = mocker.Mock(return_value=original_os_getcwd())

    def chdir_side_effect(path):
        abs_path = os.path.abspath(path) # Ensure consistent path format
        print(f"MOCK os.chdir: Setting mocked cwd state to: {abs_path}")
        mock_current_dir_state.return_value = abs_path
        # No actual chdir occurs

    def listdir_side_effect(path="."):
        # Get the *mocked* current directory
        current_mocked_dir = mock_current_dir_state()
        # Resolve the path relative to the mocked directory
        abs_list_path = os.path.abspath(os.path.join(current_mocked_dir, path))
        print(f"MOCK os.listdir: Requested list path='{path}', Resolved to abs='{abs_list_path}', Mocked CWD='{current_mocked_dir}'")

        if abs_list_path == str(final_track_output_dir):
            # Simulate the key file needed by KaraokeFinalise in the main track dir
            print(f"MOCK os.listdir: Returning mocked content for {final_track_output_dir}")
            # Include other files/dirs created by KaraokePrep phase if needed by later steps
            
            # Create the lyrics directory if it doesn't exist yet
            lyrics_dir = os.path.join(str(final_track_output_dir), "lyrics")
            os.makedirs(lyrics_dir, exist_ok=True)
            # Create a dummy LRC file needed for the test
            lrc_file = os.path.join(str(final_track_output_dir), "ABBA - Waterloo (Karaoke).lrc")
            if not os.path.exists(lrc_file):
                with open(lrc_file, "w") as f:
                    f.write("[00:00.00]Waterloo - ABBA\n[00:05.00]My my\n[00:10.00]Waterloo")
            
            return [
                'ABBA - Waterloo (With Vocals).mkv',
                'ABBA - Waterloo (Karaoke).lrc',
                'ABBA - Waterloo (Title).mov',
                'ABBA - Waterloo (End).mov',
                'ABBA - Waterloo (Title).png',
                'ABBA - Waterloo (End).png',
                'ABBA - Waterloo (Title).jpg',
                'ABBA - Waterloo (End).jpg',
                'ABBA - Waterloo (Original).wav',
                'ABBA - Waterloo (Original).flac', # Copied input
                'ABBA - Waterloo (Instrumental model_bs_roformer_ep_317_sdr_12.9755.ckpt).flac',
                'ABBA - Waterloo (Instrumental +BV mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt).flac',
                'stems', # Stems directory
                'lyrics' # Lyrics directory (even though files moved out)
            ]
        elif abs_list_path == str(final_track_output_dir / "lyrics"):
             # Simulate contents of lyrics dir *before* files are moved out by KaraokePrep
             # KaraokeFinalise doesn't look here, but good practice
            print(f"MOCK os.listdir: Returning mocked content for {final_track_output_dir / 'lyrics'}")
            
            # Create the necessary files in the lyrics directory
            lyrics_dir = os.path.join(str(final_track_output_dir), "lyrics")
            os.makedirs(lyrics_dir, exist_ok=True)
            
            # Create a dummy CDG file
            cdg_file = os.path.join(lyrics_dir, "ABBA - Waterloo (Karaoke).cdg")
            if not os.path.exists(cdg_file):
                with open(cdg_file, "wb") as f:
                    # Simple CDG header
                    f.write(b'\x00' * 96)  # CDG command
            
            # Create a dummy MP3 file
            mp3_file = os.path.join(lyrics_dir, "ABBA - Waterloo (Karaoke).mp3") 
            if not os.path.exists(mp3_file):
                with open(mp3_file, "wb") as f:
                    # Simple MP3 header
                    f.write(b'ID3\x03\x00\x00\x00\x00\x00\x00')
            
            # Create a dummy With Vocals MKV file
            mkv_file = os.path.join(lyrics_dir, "ABBA - Waterloo (With Vocals).mkv")
            if not os.path.exists(mkv_file):
                with open(mkv_file, "wb") as f:
                    # Simple MKV header
                    f.write(b'\x1A\x45\xDF\xA3')
            
            return [
                'ABBA - Waterloo (Karaoke).ass',
                'ABBA - Waterloo (Karaoke).cdg',
                'ABBA - Waterloo (Karaoke).lrc', # Original location
                'ABBA - Waterloo (Karaoke).mp3',
                'ABBA - Waterloo (Karaoke).toml',
                'ABBA - Waterloo (Karaoke).zip',
                'ABBA - Waterloo (Lyrics Corrected).txt',
                'ABBA - Waterloo (Lyrics Corrections).json',
                'ABBA - Waterloo (Lyrics Genius).txt',
                'ABBA - Waterloo (Lyrics Uncorrected).txt',
                'ABBA - Waterloo (With Vocals).mkv' # Original location
            ]
        elif abs_list_path == str(final_track_output_dir / "stems"):
             # Simulate contents of stems dir
             print(f"MOCK os.listdir: Returning mocked content for {final_track_output_dir / 'stems'}")
             return [
                'ABBA - Waterloo (Audacity).lof',
                'ABBA - Waterloo (Backing Vocals mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt).flac',
                'ABBA - Waterloo (Bass htdemucs_6s).flac',
                'ABBA - Waterloo (Drums htdemucs_6s).flac',
                'ABBA - Waterloo (Guitar htdemucs_6s).flac',
                'ABBA - Waterloo (Lead Vocals mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt).flac',
                'ABBA - Waterloo (Other htdemucs_6s).flac',
                'ABBA - Waterloo (Piano htdemucs_6s).flac',
                'ABBA - Waterloo (Vocals htdemucs_6s).flac',
                'ABBA - Waterloo (Vocals model_bs_roformer_ep_317_sdr_12.9755.ckpt).flac'
             ]

        else:
            # For any other path, try calling the original listdir relative to the *actual* CWD
            actual_list_path = path if os.path.isabs(path) else os.path.join(original_os_getcwd(), path)
            print(f"MOCK os.listdir: Calling original os.listdir for actual path '{actual_list_path}'")
            try:
                return original_os_listdir(actual_list_path)
            except FileNotFoundError:
                 print(f"MOCK os.listdir: Original call failed (FileNotFound) for {actual_list_path}, returning empty list.")
                 return [] # Return empty if original fails

    def rename_side_effect(src, dst):
        # src is likely relative filename, dst is likely absolute path in temp dir
        current_mocked_dir = mock_current_dir_state()
        # Resolve src relative to the *mocked* CWD to get the actual source path
        # This assumes the file was created in the mocked CWD
        # Resolve src relative to mocked CWD if it's not absolute
        actual_src_path = src if os.path.isabs(src) else os.path.abspath(os.path.join(current_mocked_dir, src))
        # Resolve dst relative to mocked CWD if it's not absolute
        actual_dst_path = dst if os.path.isabs(dst) else os.path.abspath(os.path.join(current_mocked_dir, dst))

        print(f"MOCK os.rename: Called with src='{src}', dst='{dst}'. Mocked CWD='{current_mocked_dir}'")
        print(f"MOCK os.rename: Resolved actual paths: src='{actual_src_path}', dst='{actual_dst_path}'.")

        try:
            # Check if source file actually exists before attempting rename
            # Note: This check uses the *real* filesystem
            if os.path.exists(actual_src_path):
                print(f"MOCK os.rename: Source file '{actual_src_path}' exists. Attempting rename...")
                # Ensure the destination directory exists (e.g., the 'stems' dir)
                os.makedirs(os.path.dirname(actual_dst_path), exist_ok=True)
                original_os_rename(actual_src_path, actual_dst_path)
                print(f"MOCK os.rename: Actual rename successful.")
            else:
                # This can happen if the file creation step failed or was skipped.
                print(f"MOCK os.rename: Source file '{actual_src_path}' does NOT exist. Skipping actual rename.")
                # In a test, if the file *should* exist, this indicates a problem earlier
                # or a flaw in the mocking logic for where files are created.

        except Exception as e:
            print(f"MOCK os.rename: Actual rename failed for src='{actual_src_path}', dst='{actual_dst_path}': {e}")
            # Optionally re-raise if the rename failure should fail the test
            # raise e

        return None

    mocker.patch('os.chdir', side_effect=chdir_side_effect)
    # Patch getcwd to always return the value our mock state holder has
    mocker.patch('os.getcwd', new=mock_current_dir_state)
    mocker.patch('os.listdir', side_effect=listdir_side_effect)
    mocker.patch('os.rename', side_effect=rename_side_effect)

    # Mock os.path.isfile to use the mocked CWD
    original_os_path_isfile = os.path.isfile
    def isfile_side_effect(path):
        current_mocked_dir = mock_current_dir_state()
        # Resolve path relative to mocked CWD if it's not absolute
        abs_path_to_check = path if os.path.isabs(path) else os.path.abspath(os.path.join(current_mocked_dir, path))
        print(f"MOCK os.path.isfile: Checking path='{path}'. Mocked CWD='{current_mocked_dir}'. Resolved='{abs_path_to_check}'")
        # Call the *original* isfile on the resolved absolute path in the temp FS
        exists = original_os_path_isfile(abs_path_to_check)
        print(f"MOCK os.path.isfile: Original check returned: {exists}")
        return exists
    mocker.patch('os.path.isfile', side_effect=isfile_side_effect)

    # Mock os.path.exists to use the mocked CWD
    original_os_path_exists = os.path.exists
    def exists_side_effect(path):
        current_mocked_dir = mock_current_dir_state()
        # Resolve path relative to mocked CWD if it's not absolute
        abs_path_to_check = path if os.path.isabs(path) else os.path.abspath(os.path.join(current_mocked_dir, path))
        print(f"MOCK os.path.exists: Checking path='{path}'. Mocked CWD='{current_mocked_dir}'. Resolved='{abs_path_to_check}'")
        # Call the *original* exists on the resolved absolute path in the temp FS
        exists = original_os_path_exists(abs_path_to_check)
        print(f"MOCK os.path.exists: Original check returned: {exists}")
        return exists
    mocker.patch('os.path.exists', side_effect=exists_side_effect)

    # Mock builtins.open to use the mocked CWD
    original_builtin_open = open
    def open_side_effect(file, mode='r', *args, **kwargs):
        # Check if 'file' is an integer (file descriptor)
        if isinstance(file, int):
            print(f"MOCK builtins/io.open: Received integer FD={file}. Calling original open.")
            return original_builtin_open(file, mode, *args, **kwargs)

        # If it's not an int, assume it's a path and proceed with path resolution
        current_mocked_dir = mock_current_dir_state()
        # Resolve file path relative to mocked CWD if it's not absolute
        path_to_open = file if os.path.isabs(file) else os.path.abspath(os.path.join(current_mocked_dir, file))
        print(f"MOCK builtins/io.open: Requested path='{file}', Mode='{mode}'. Mocked CWD='{current_mocked_dir}'. Resolved='{path_to_open}'")
        # Call the *original* open on the resolved absolute path in the temp FS
        try:
            # Ensure the directory exists if opening for writing
            if 'w' in mode or 'a' in mode or 'x' in mode:
                 os.makedirs(os.path.dirname(path_to_open), exist_ok=True)
            return original_builtin_open(path_to_open, mode, *args, **kwargs)
        except FileNotFoundError as e:
            print(f"MOCK builtins.open: Original open FAILED for path '{path_to_open}': {e}")
            # Re-raise the exception so the calling code sees it
            raise e
        except Exception as e:
            print(f"MOCK builtins.open: Original open FAILED unexpectedly for path '{path_to_open}': {e}")
            raise e
    mocker.patch('builtins.open', side_effect=open_side_effect)
    # Also mock io.open as zipfile might use it directly
    mocker.patch('io.open', side_effect=open_side_effect)

    # Mock os.stat to use the mocked CWD
    original_os_stat = os.stat
    def stat_side_effect(path, *args, **kwargs):
        current_mocked_dir = mock_current_dir_state()
        # Resolve path relative to mocked CWD if it's not absolute
        path_to_stat = path if os.path.isabs(path) else os.path.abspath(os.path.join(current_mocked_dir, path))
        print(f"MOCK os.stat: Requested path='{path}'. Mocked CWD='{current_mocked_dir}'. Resolved='{path_to_stat}'")
        # Call the *original* stat on the resolved absolute path in the temp FS
        try:
            return original_os_stat(path_to_stat, *args, **kwargs)
        except FileNotFoundError as e:
            print(f"MOCK os.stat: Original stat FAILED for path '{path_to_stat}': {e}")
            raise e # Re-raise the exception
        except Exception as e:
            print(f"MOCK os.stat: Original stat FAILED unexpectedly for path '{path_to_stat}': {e}")
            raise e
    mocker.patch('os.stat', side_effect=stat_side_effect)

    # Mock os.remove to use the mocked CWD
    original_os_remove = os.remove
    def remove_side_effect(path):
        current_mocked_dir = mock_current_dir_state()
        # Resolve path relative to mocked CWD if it's not absolute
        path_to_remove = path if os.path.isabs(path) else os.path.abspath(os.path.join(current_mocked_dir, path))
        print(f"MOCK os.remove: Requested path='{path}'. Mocked CWD='{current_mocked_dir}'. Resolved='{path_to_remove}'")
        # Call the *original* remove on the resolved absolute path in the temp FS
        try:
            return original_os_remove(path_to_remove)
        except FileNotFoundError as e:
            print(f"MOCK os.remove: Original remove FAILED for path '{path_to_remove}': {e}")
            raise e # Re-raise the exception
        except Exception as e:
            print(f"MOCK os.remove: Original remove FAILED unexpectedly for path '{path_to_remove}': {e}")
            raise e
    mocker.patch('os.remove', side_effect=remove_side_effect)

    # Mock ReviewServer.start to return the correction_result stored on the instance
    def mock_start_return_self_correction_result(mock_instance):
        print("MOCK ReviewServer.start: Bypassing UI, returning instance's correction_result.")
        # Assuming the ReviewServer instance stores the result in an attribute like 'correction_result'
        # We access it via the 'mock_instance' passed to the side_effect
        # The actual attribute name might differ, adjust if needed based on ReviewServer implementation
        return mock_instance.correction_result # Access the attribute on the mocked instance

    # Patch the 'start' method where ReviewServer is defined
    mocker.patch(
        'lyrics_transcriber.review.server.ReviewServer.start',
        side_effect=mock_start_return_self_correction_result,
        autospec=True
    )

    # Mock builtins.input to handle unexpected prompts
    def mock_input_side_effect(prompt=""):
        print(f"MOCK input: Received prompt: '{prompt}'")
        if "Enter the manually uploaded YouTube video ID:" in prompt:
            print("MOCK input: Returning dummy YouTube ID.")
            return "manual_mock_video_id"
        # Handle other potential prompts if necessary, or raise error
        print(f"MOCK input: WARNING - Unexpected prompt received!")
        return "unexpected_input_response" # Or raise an exception
    mocker.patch('builtins.input', side_effect=mock_input_side_effect)

    # --- 3. Construct Args and Call async_main ---
    # Reusing artist and title variables defined earlier
    brand_prefix = "NOMAD"
    expected_brand_code = f"{brand_prefix}-0001"
    discord_webhook_url = "https://discord.com/api/webhooks/FAKE/URL"
    rclone_destination = "googledrive:TestNomadKaraoke"

    # Simulate sys.argv (note: first element is script name, irrelevant here)
    test_argv = [
        "gen_cli.py", # Script name placeholder
        "--style_params_json", str(style_params_path),
        "--enable_cdg",
        "--enable_txt",
        "--output_dir", str(tmp_path), # Set output base to tmp_path
        "--organised_dir", str(organised_dir),
        "--organised_dir_rclone_root", f"andrewdropboxfull:{organised_dir.name}",
        "--public_share_dir", str(public_share_dir),
        "--brand_prefix", brand_prefix,
        "--youtube_client_secrets_file", str(yt_secrets_path),
        "--rclone_destination", rclone_destination,
        "--youtube_description_file", str(yt_desc_path),
        "--discord_webhook_url", discord_webhook_url,
        "--email_template_file", str(email_template_path),
        "-y", # Non-interactive
        str(input_audio),
        artist,
        title,
    ]

    # Patch sys.argv and run the main function
    mocker.patch.object(sys, 'argv', test_argv)

    print("--- Calling async_main ---")
    await async_main() # Call the imported function
    print("--- async_main finished ---")

    # --- 4. Assert Local File Outputs ---
    final_branded_dir_name = f"{expected_brand_code} - {artist} - {title}"
    final_branded_dir_path = organised_dir / final_branded_dir_name
    base_name = f"{artist} - {title}"
    final_base_name = f"{expected_brand_code} - {base_name}"

    assert final_branded_dir_path.is_dir(), f"Expected branded directory not found: {final_branded_dir_path}"

    # Check files in the final branded directory
    expected_files_in_branded_dir = [
        f"{base_name} (Final Karaoke Lossless 4k).mp4",
        f"{base_name} (Final Karaoke Lossless 4k).mkv",
        f"{base_name} (Final Karaoke Lossy 4k).mp4",
        f"{base_name} (Final Karaoke Lossy 720p).mp4",
        f"{base_name} (Final Karaoke CDG).zip",
        f"{base_name} (Final Karaoke TXT).zip",
        f"{base_name} (Karaoke).mp3", # Extracted from zip
        f"{base_name} (Karaoke).cdg", # Extracted from zip
        f"{base_name} (Karaoke).txt", # Created for zip
    ]
    for filename in expected_files_in_branded_dir:
        filepath = final_branded_dir_path / filename
        assert filepath.is_file(), f"Expected file not found in branded dir: {filepath}"
        assert filepath.stat().st_size > 0, f"File is empty: {filepath}"

    # Check files copied to public share
    expected_public_mp4 = public_share_mp4_dir / f"{final_base_name}.mp4"
    expected_public_720p = public_share_720p_dir / f"{final_base_name}.mp4"
    expected_public_cdg = public_share_cdg_dir / f"{final_base_name}.zip"

    assert expected_public_mp4.is_file(), f"Expected file not found in public share MP4: {expected_public_mp4}"
    assert expected_public_mp4.stat().st_size > 0
    assert expected_public_720p.is_file(), f"Expected file not found in public share 720p: {expected_public_720p}"
    assert expected_public_720p.stat().st_size > 0
    assert expected_public_cdg.is_file(), f"Expected file not found in public share CDG: {expected_public_cdg}"
    assert expected_public_cdg.stat().st_size > 0

    # --- 5. Assert Mock Calls ---
    # YouTube Upload - we're checking that upload_final_mp4_to_youtube_with_title_thumbnail was called
    assert mock_upload.called
    assert mock_requests_post.call_args.kwargs['json']['content'].find('manual_mock_video_id') != -1
    
    # Discord Notification
    mock_requests_post.assert_called_once_with(discord_webhook_url, json=mocker.ANY)
    assert 'https://www.youtube.com/watch?v=manual_mock_video_id' in mock_requests_post.call_args[1]['json']['content']

    # Rclone Sync and Link (using os.system mock)
    assert any(f"rclone sync -v \'{str(public_share_dir)}\' \'{rclone_destination}\'" in call_args[0][0] for call_args in mock_os_system.call_args_list), "rclone sync not called"
    
    # Debug all os.system calls
    print("\n--- Debug: ALL mock_os_system calls ---")
    for i, call_args in enumerate(mock_os_system.call_args_list):
        print(f"Call {i}: {call_args[0][0]}")
    
    # Look specifically at the rclone mock side effect in the code
    print("\n--- Important: How the mock captures rclone calls ---")
    print("The mock captures exact strings for os.system calls.")
    
    # Print all os.system calls for debugging
    print("\n--- ALL mock_os_system.call_args_list calls ---")
    all_calls = []
    for i, call_args in enumerate(mock_os_system.call_args_list):
        command = call_args[0][0]
        all_calls.append(command)
        print(f"Call {i}: '{command}'")
    
    # Extract the command from the finalise.py implementation for debugging
    expected_rclone_link_prefix = "rclone link"
    organised_dir_folder = "andrewdropboxfull:organised/NOMAD-0001 - ABBA - Waterloo"
    
    # Also look for the command in subprocess_run calls (used by the finalise.py implementation)
    print("\n--- ALL mock_subprocess_run.call_args_list calls ---")
    subprocess_all_calls = []
    for i, call_args in enumerate(mock_subprocess_run.call_args_list):
        if call_args[0]: # Check if there are positional args
            command = call_args[0][0]
            subprocess_all_calls.append(command)
            print(f"Call {i}: '{command}'")
    
    # Check for rclone link command in both os.system and subprocess.run calls
    all_system_commands = all_calls + subprocess_all_calls
    
    # Look for rclone link in all calls
    found_rclone_link = False
    matching_command = None
    
    for command in all_system_commands:
        if isinstance(command, str) and expected_rclone_link_prefix in command and organised_dir_folder in command:
            found_rclone_link = True
            matching_command = command
            print(f"\nSUCCESS: Found matching command: '{command}'")
            break
        elif isinstance(command, list) and len(command) >= 3 and command[0] == "rclone" and command[1] == "link" and organised_dir_folder in " ".join(command):
            found_rclone_link = True
            matching_command = command
            print(f"\nSUCCESS: Found matching command (list): {command}")
            break
    
    if not found_rclone_link:
        # Try to find partial matches for better error messages
        print("\nSearching for partial matches...")
        
        # For string commands
        rclone_matches = [cmd for cmd in all_system_commands if isinstance(cmd, str) and expected_rclone_link_prefix in cmd]
        if rclone_matches:
            print("\nFound commands with 'rclone link' but missing correct path:")
            for cmd in rclone_matches:
                print(f"- '{cmd}'")
        else:
            print("\nNo string commands found containing 'rclone link'")
        
        # For list commands
        rclone_list_matches = [cmd for cmd in all_system_commands if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "rclone" and cmd[1] == "link"]
        if rclone_list_matches:
            print("\nFound list commands with 'rclone link' but missing correct path:")
            for cmd in rclone_list_matches:
                print(f"- {cmd}")
        
        # Check for the path fragment
        path_matches = [cmd for cmd in all_system_commands if isinstance(cmd, str) and organised_dir_folder in cmd]
        if path_matches:
            print("\nFound commands with the correct path but not 'rclone link':")
            for cmd in path_matches:
                print(f"- '{cmd}'")
        
        # Final assertion with clear error message
        # Check if the command was logged in the output for debugging
        log_lines = [line for line in mock_os_system.mock_calls if "rclone link" in str(line)]
        if log_lines:
            print("\nFound logged rclone link commands in mock calls:")
            for line in log_lines:
                print(f"- {line}")
        
        error_message = f"No command found containing both '{expected_rclone_link_prefix}' and '{organised_dir_folder}'"
        print(f"\nASSERTION ERROR: {error_message}")
        assert False, error_message
    
    # Gmail Draft
    mock_youtube_service.users().drafts().create.assert_called_once()
    draft_args, draft_kwargs = mock_youtube_service.users().drafts().create.call_args
    assert draft_kwargs['userId'] == 'me'

    # Pyperclip
    # Check if it was called at least once (exact calls can be tricky with multiple potential copies)
    assert mock_pyperclip.call_count >= 1 