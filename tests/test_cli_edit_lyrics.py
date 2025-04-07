import os
import pytest
import tempfile
import shutil
import subprocess
import sys
import json
import io
from karaoke_prep.karaoke_prep import KaraokePrep
from karaoke_prep.file_handler import FileHandler # Import FileHandler
from unittest.mock import MagicMock, call, patch, AsyncMock, ANY
from karaoke_prep.utils.gen_cli import async_main
import shlex
import asyncio
from googleapiclient.http import MediaFileUpload
from karaoke_prep.karaoke_finalise.karaoke_finalise import KaraokeFinalise
import pydub

# Register the asyncio marker
pytest.mark.asyncio = pytest.mark.asyncio

# Set the default event loop policy to 'auto'
pytest_configure = lambda config: config.addinivalue_line("markers", "asyncio: mark test as async")


@pytest.mark.asyncio
@pytest.mark.slow # Mark as slow like the full CLI test
async def test_cli_edit_lyrics_integration(tmp_path, mocker):
    """Tests the --edit-lyrics CLI workflow."""
    # --- 1. Setup Temporary Directories and Files for an *Existing* Track ---
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    organised_dir = tmp_path / "organised"
    organised_dir.mkdir() # Finalise needs this

    # Simulate the existing track directory
    artist = "Test Edit Artist"
    title = "Test Edit Title"
    brand_prefix = "EDIT"
    brand_code = f"{brand_prefix}-9999"
    existing_track_dir_name = f"{brand_code} - {artist} - {title}"
    existing_track_dir = tmp_path / existing_track_dir_name # Create alongside data/organised
    existing_track_dir.mkdir()
    base_name = f"{artist} - {title}"

    # Create essential files *inside* the existing track dir
    # Input WAV (most crucial)
    input_wav_path = existing_track_dir / f"{base_name} (Original).wav"
    with open(input_wav_path, 'wb') as f:
        f.write(b'RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00@\x1f\x00\x00\x01\x00\x08\x00data\x00\x00\x00\x00')

    # Dummy existing outputs to be backed up
    existing_outputs = [
        f"{base_name} (Karaoke).lrc",
        f"{base_name} (Final Karaoke Lossless 4k).mp4",
        f"{base_name} (Final Karaoke Lossy 4K).mp4",
        f"{base_name} (Title).mov",
        f"{base_name} (End).mov",
        f"{base_name} (Title).png",
        f"{base_name} (Title).jpg",
    ]
    for fname in existing_outputs:
        (existing_track_dir / fname).touch()

    # Create the expected input video file for the finalise step
    with_vocals_mkv_path = existing_track_dir / f"{base_name} (With Vocals).mkv"
    with_vocals_mkv_path.touch()

    # Create a dummy instrumental file needed by finalise
    # Copy the test instrumental if available, otherwise create a dummy valid one
    instrumental_flac_path = existing_track_dir / f"{base_name} (Instrumental mock_model).flac"
    source_instrumental_flac = "tests/data/Test Artist - Test Title (Instrumental).flac"
    if os.path.exists(source_instrumental_flac):
        shutil.copy2(source_instrumental_flac, instrumental_flac_path)
    else:
        # Create a minimal valid FLAC file if the source doesn't exist
        # (Header for a 1-second silent mono 44.1kHz 16-bit FLAC)
        # This avoids needing ffmpeg during test setup
        min_flac_header = bytes.fromhex(
            '664C6143'  # fLaC marker
            '80000022'  # METADATA_BLOCK_HEADER (last block, type 0 STREAMINFO, size 34)
            '10001000'  # STREAMINFO block_size_min/max (4096)
            '00000000'  # frame_size_min/max (0)
            '00AC4401'  # sample_rate (44100), channels-1 (0 -> 1), bits_per_sample-1 (15 -> 16)
            'A0000000'  # total_samples_in_stream (high 2 bits, low 34 bits -> 44100 = 0xAC44)
            'AC440000'
            '00000000'
            '00000000'  # MD5 signature (zeroes)
            '00000000'
            '00000000'
            '00000000'
            'FF F8 AC'  # FRAME_HEADER sync code, blocking strategy, block size, sample rate
            '0E 00 00'  # channel assignment, sample size, reserved, utf8 sample number
            '00'        # CRC-8
            # Add some silent subframes if needed, but header might be enough for pydub
            '08 00'     # SUBFRAME_HEADER (LPC, order 0, wasted bits 0)
            '00 00'     # Residual (zeros for silence)
            # Frame Footer
            '00 00'     # CRC-16 (zeros for dummy)
        )
        print(f"WARNING: Source instrumental {source_instrumental_flac} not found. Creating minimal dummy FLAC.")
        with open(instrumental_flac_path, 'wb') as f:
            f.write(min_flac_header)
        # Fallback: if the minimal header isn't enough, touch an empty file as before
        # instrumental_flac_path.touch()

    # Dummy existing lyrics directory (will be backed up)
    lyrics_dir = existing_track_dir / "lyrics"
    lyrics_dir.mkdir()
    (lyrics_dir / f"{base_name} (Karaoke).ass").touch()
    (lyrics_dir / f"{base_name} (Lyrics Corrected).txt").touch()

    # Copy/Create necessary config files into data_dir (reused by mocks)
    # Use real style params if available, otherwise create dummy
    source_style_params = "tests/data/styles.json"
    style_params_path = data_dir / os.path.basename(source_style_params)
    if os.path.exists(source_style_params):
        shutil.copy2(source_style_params, style_params_path)
    else:
        # Create a dummy style params file if the source doesn't exist
        dummy_styles = {
            "video_resolution": "3840x2160",
            "font_style": "Arial",
            "font_size": 70,
            "color_primary": "&H00FFFFFF",
            "color_secondary": "&H0000FFFF",
            "color_outline": "&H00000000",
            "color_shadow": "&H00000000",
            "outline_thickness": 2,
            "shadow_offset": 2
        }
        with open(style_params_path, "w") as f:
            json.dump(dummy_styles, f)

    yt_secrets_path = data_dir / "kgenclientsecret_edit.json"
    yt_secrets_content = {"installed": {"client_id": "dummy_edit", "client_secret": "dummy_edit"}}
    with open(yt_secrets_path, "w") as f:
        json.dump(yt_secrets_content, f)

    yt_desc_path = data_dir / "ytdesc_edit.txt"
    with open(yt_desc_path, "w") as f:
        f.write("Test Edit Desc {artist} - {title}")

    email_template_path = data_dir / "emailtemplate_edit.txt"
    with open(email_template_path, "w") as f:
        f.write("Subject: Test Edit Email\n\nYT: {youtube_url}\nDB: {dropbox_url}")

    # --- 2. Mock External Interactions (Reuse/Adapt from full test) ---
    # Mock YouTube API (simulating replacement)
    mock_youtube_service = MagicMock()
    # Simulate finding an existing video to replace (though finalise mock handles replace logic)
    mock_list_response = {'items': [{'id': 'existing_video_id'}]}
    mock_youtube_service.search().list().execute.return_value = mock_list_response
    mock_youtube_insert = MagicMock()
    mock_youtube_insert.execute.return_value = {'id': 'replaced_video_id'}
    mock_youtube_service.videos().insert.return_value = mock_youtube_insert
    mock_youtube_service.thumbnails().set().execute.return_value = {}
    mock_build = mocker.patch('googleapiclient.discovery.build', return_value=mock_youtube_service)

    mocker.patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file')
    # Mock check_if_video_title_exists to return True for edit mode
    mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.check_if_video_title_exists_on_youtube_channel', return_value='existing_video_id')
    # Mock upload - should still be called, even if replacing
    mock_upload = mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.upload_final_mp4_to_youtube_with_title_thumbnail')
    def upload_side_effect(*args, **kwargs):
        instance = args[0]
        instance.youtube_video_id = 'replaced_video_id'
        instance.youtube_url = f"https://youtu.be/replaced_video_id"
    mock_upload.side_effect = upload_side_effect
    mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.authenticate_youtube', return_value=mock_youtube_service)

    # Mock Gmail API
    mocker.patch('karaoke_prep.karaoke_finalise.karaoke_finalise.KaraokeFinalise.authenticate_gmail', return_value=mock_youtube_service)
    mock_draft_create = MagicMock()
    mock_draft_create.execute.return_value = {'id': 'mock_draft_id_edit'}
    mock_youtube_service.users().drafts().create.return_value = mock_draft_create

    # Mock Discord
    mock_requests_post = mocker.patch('requests.post')
    mock_requests_post.return_value.raise_for_status.return_value = None

    # Mock subprocess/os calls
    original_os_system = os.system
    original_subprocess_run = subprocess.run
    original_os_rename = os.rename

    # Define the rclone side effect function
    def rclone_side_effect_edit(*args, **kwargs):
        cmd_arg = args[0]
        cmd_str = cmd_arg if isinstance(cmd_arg, str) else " ".join(map(shlex.quote, cmd_arg))
        current_mocked_dir = mock_current_dir_state()
        is_os_system_call = kwargs.get('_os_system_call', False)

        # --- Intercept specific ffmpeg commands to create dummy outputs ---
        is_ffmpeg_command = (isinstance(cmd_arg, list) and cmd_arg and cmd_arg[0] == "ffmpeg") or \
                            (isinstance(cmd_arg, str) and cmd_arg.strip().startswith("ffmpeg"))

        if is_ffmpeg_command:
            # Determine the output file from the command arguments
            output_file = None
            if isinstance(cmd_arg, list):
                # Look backwards from the end for a potential output file
                for i in range(len(cmd_arg) - 1, 0, -1):
                    if not cmd_arg[i].startswith('-') and cmd_arg[i-1] != '-i':
                        output_file = cmd_arg[i]
                        break
            elif isinstance(cmd_arg, str):
                parts = shlex.split(cmd_arg)
                for i in range(len(parts) - 1, 0, -1):
                     if not parts[i].startswith('-') and parts[i-1] != '-i':
                        output_file = parts[i]
                        break

            if output_file:
                # Ensure output path is absolute based on mocked CWD
                abs_output_path = output_file if os.path.isabs(output_file) else os.path.abspath(os.path.join(current_mocked_dir, output_file))
                # Create dummy file if it matches expected final outputs
                expected_outputs = [
                    f"{base_name} (Karaoke).mp4",
                    f"{base_name} (With Vocals).mp4", # Intermediate
                    f"{base_name} (Final Karaoke Lossless 4k).mp4",
                    f"{base_name} (Final Karaoke Lossy 4k).mp4",
                    f"{base_name} (Final Karaoke Lossless 4k).mkv",
                    f"{base_name} (Final Karaoke Lossy 720p).mp4"
                ]
                if os.path.basename(abs_output_path) in expected_outputs:
                    print(f"SIDE_EFFECT_EDIT (ffmpeg mock): Creating dummy output file: {abs_output_path}")
                    os.makedirs(os.path.dirname(abs_output_path), exist_ok=True)
                    with open(abs_output_path, 'wb') as f:
                        f.write(b'dummy ffmpeg output')
                    # Return success (CompletedProcess or 0 based on caller)
                    return subprocess.CompletedProcess(args=cmd_arg if isinstance(cmd_arg, list) else [cmd_arg], returncode=0, stdout="", stderr="") if not is_os_system_call else 0
        # --- End ffmpeg interception ---

        # Original logic for allowing specific commands or mocking others
        execute_commands = ["ffprobe", "uname"] # Let ffprobe run (might be needed)
        should_execute = False
        if isinstance(cmd_arg, list) and cmd_arg and cmd_arg[0] in execute_commands:
            should_execute = True
        # Don't execute ffmpeg here anymore, handled above
        # elif isinstance(cmd_arg, str) and any(cmd in cmd_arg for cmd in execute_commands):
        #     if cmd_arg.strip().startswith("ffmpeg"):
        #         should_execute = True

        if should_execute:
            print(f"SIDE_EFFECT_EDIT: Executing original: {cmd_str}")
            print(f"SIDE_EFFECT_EDIT: Executing {cmd_arg[0]} in mocked CWD: {current_mocked_dir}")
            try:
                run_kwargs = kwargs.copy()
                if '_os_system_call' in run_kwargs:
                    del run_kwargs['_os_system_call']
                run_kwargs['capture_output'] = True
                run_kwargs['text'] = True
                result = original_subprocess_run(*args, shell=isinstance(cmd_arg, str), cwd=current_mocked_dir, **run_kwargs)
                print(f"SIDE_EFFECT_EDIT: Original {cmd_arg[0]} finished. RC={result.returncode}")
                if result.stderr:
                    print(f"SIDE_EFFECT_EDIT: {cmd_arg[0]} stderr: {result.stderr[:200]}...")
                return result
            except Exception as e:
                print(f"SIDE_EFFECT_EDIT: Error executing original '{cmd_str}': {e}")
                # Return failure (CompletedProcess or non-zero int based on caller)
                err_result = subprocess.CompletedProcess(args=cmd_arg if isinstance(cmd_arg, list) else [cmd_arg], returncode=1, stderr=str(e))
                return err_result if not is_os_system_call else 1

        # Mock Rclone link specifically for the *renamed* directory
        if (isinstance(cmd_arg, str) and cmd_arg.startswith('rclone link')) or \
           (isinstance(cmd_arg, list) and cmd_arg[0:2] == ['rclone', 'link']):
            target_path = cmd_arg.split()[-1] if isinstance(cmd_arg, str) else cmd_arg[-1]
            print(f"SIDE_EFFECT_EDIT: Mocking rclone link for: {target_path}")
            # Adjust link creation based on the *final* directory name after potential rename/move
            # For edit mode, it should use the existing_track_dir_name
            link_url = f"https://fake.sharing.link/{existing_track_dir_name}"

            if isinstance(cmd_arg, list):
                return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout=link_url, stderr="")
            else:
                # os.system returns 0 on success
                return 0

        # Mock Rclone sync
        if (isinstance(cmd_arg, str) and cmd_arg.startswith('rclone sync')) or \
           (isinstance(cmd_arg, list) and cmd_arg[0:2] == ['rclone', 'sync']):
            print(f"SIDE_EFFECT_EDIT: Mocking rclone sync: {cmd_str}")
            if isinstance(cmd_arg, list):
                return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="", stderr="")
            else:
                return 0

        print(f"SIDE_EFFECT_EDIT: Default mock for unhandled command: {cmd_str}")
        if isinstance(cmd_arg, list):
            if kwargs.get('check'):
                 raise subprocess.CalledProcessError(returncode=1, cmd=cmd_arg, stderr="Mocked process failed check")
            return subprocess.CompletedProcess(args=cmd_arg, returncode=0, stdout="", stderr="")
        else:
            return 0

    def os_system_wrapper_edit(*args, **kwargs):
        kwargs_copy = kwargs.copy()
        kwargs_copy['_os_system_call'] = True
        result = rclone_side_effect_edit(*args, **kwargs_copy)
        # Ensure return is int for os.system
        if isinstance(result, subprocess.CompletedProcess):
            return result.returncode
        return result # Should already be int

    def subprocess_run_wrapper_edit(*args, **kwargs):
        kwargs_copy = kwargs.copy()
        kwargs_copy['_os_system_call'] = False
        result = rclone_side_effect_edit(*args, **kwargs_copy)
        # Ensure return is CompletedProcess for subprocess.run
        if isinstance(result, int):
            print(f"WARN: subprocess.run mock received int ({result}), converting to CompletedProcess")
            # Reconstruct args properly for CompletedProcess
            cmd_for_cp = args[0]
            if isinstance(cmd_for_cp, str) and kwargs.get('shell') == True:
                pass
            elif isinstance(cmd_for_cp, str):
                 cmd_for_cp = shlex.split(cmd_for_cp)

            # Attempt to reconstruct stdout/stderr if the original mock logic for this command would have provided it
            stdout_val = None
            stderr_val = None
            cmd_arg_orig = args[0] # Original command arg before potential splitting
            if (isinstance(cmd_arg_orig, str) and cmd_arg_orig.startswith('rclone link')) or \
               (isinstance(cmd_arg_orig, list) and cmd_arg_orig[0:2] == ['rclone', 'link']):
                link_url = f"https://fake.sharing.link/{existing_track_dir_name}"
                stdout_val = link_url
                stderr_val = ""
            elif (isinstance(cmd_arg_orig, str) and cmd_arg_orig.startswith('rclone sync')) or \
                 (isinstance(cmd_arg_orig, list) and cmd_arg_orig[0:2] == ['rclone', 'sync']):
                 stdout_val = ""
                 stderr_val = ""
            # Add other cases if necessary

            return subprocess.CompletedProcess(args=cmd_for_cp, returncode=result, stdout=stdout_val, stderr=stderr_val)
        return result # Should already be CompletedProcess

    mocker.patch('os.system', side_effect=os_system_wrapper_edit)
    mocker.patch('subprocess.run', side_effect=subprocess_run_wrapper_edit)

    # Mock pydub's mediainfo_json to avoid running ffprobe via Popen
    def mock_mediainfo_json(filepath, read_ahead_limit=-1):
        print(f"MOCK pydub.audio_segment.mediainfo_json CALLED for: {filepath}")
        # Return info consistent with the minimal dummy FLAC
        return {
            "streams": [
                {
                    "index": 0,
                    "codec_name": "flac",
                    "codec_type": "audio",
                    "channels": 1,
                    "sample_rate": "44100",
                    "bits_per_sample": 16,
                    "sample_fmt": "s16"
                }
            ],
            "format": {
                # Provide a dummy duration, e.g., 1 second
                "duration": "1.000000"
            }
        }
    mocker.patch('pydub.audio_segment.mediainfo_json', side_effect=mock_mediainfo_json)

    # Mock AudioSegment.from_file to bypass ffmpeg for the dummy instrumental
    original_from_file = pydub.AudioSegment.from_file
    def mock_from_file(file, format=None, codec=None, parameters=None, start_second=None, duration=None, **kwargs):
        # Check if the file being loaded is our dummy instrumental
        # Need to handle both file path string and file-like object
        is_dummy_instrumental = False
        try:
            # If 'file' is a path string or pathlib.Path
            if isinstance(file, (str, os.PathLike)):
                if os.path.basename(file) == os.path.basename(instrumental_flac_path):
                    is_dummy_instrumental = True
            # If 'file' is a file-like object, check its name attribute
            elif hasattr(file, 'name') and os.path.basename(file.name) == os.path.basename(instrumental_flac_path):
                is_dummy_instrumental = True
        except Exception as e:
            print(f"WARN: Error checking file in mock_from_file: {e}")

        if is_dummy_instrumental:
            print(f"MOCK AudioSegment.from_file: Returning dummy silent segment for {file}")
            # Return a 1-second silent segment matching the dummy info
            return pydub.AudioSegment.silent(duration=1000, frame_rate=44100).set_channels(1).set_sample_width(2)
        else:
            print(f"MOCK AudioSegment.from_file: Calling original for {file}")
            # Call the original method directly - pytest-mock should handle binding
            return original_from_file(file=file, format=format, codec=codec, parameters=parameters, start_second=start_second, duration=duration, **kwargs)

    # Use side_effect for the function-based mock
    mocker.patch('pydub.AudioSegment.from_file', side_effect=mock_from_file)

    # Mock pyperclip
    mock_pyperclip = mocker.patch('pyperclip.copy')

    # Mock file system operations relative to the *existing track dir*
    original_os_getcwd = os.getcwd
    mock_cwd_state = [str(existing_track_dir)]
    def mock_current_dir_state():
        return mock_cwd_state[0]

    def chdir_side_effect_edit(path):
        abs_path = os.path.abspath(os.path.join(mock_cwd_state[0], path))
        print(f"MOCK os.chdir (EDIT): Setting mocked cwd state to: {abs_path}")
        mock_cwd_state[0] = abs_path

    mocker.patch('os.chdir', side_effect=chdir_side_effect_edit)
    mocker.patch('os.getcwd', new=mock_current_dir_state)

    mocker.patch('os.listdir') # Let mocker handle calling original

    mocker.patch('os.path.isfile') # Let mocker handle calling original

    original_os_path_exists = os.path.exists
    def exists_side_effect_edit(path):
        current_mocked_dir = mock_cwd_state[0]
        abs_path_to_check = path if os.path.isabs(path) else os.path.abspath(os.path.join(current_mocked_dir, path))
        # Keep special case for input wav during backup check?
        # Maybe not needed if creation is robust.
        # if abs_path_to_check == str(input_wav_path):
        #     return True
        # Rely on original exists
        return original_os_path_exists(abs_path_to_check)
    # Only patch exists if absolutely needed, maybe the special case isn't required
    # mocker.patch('os.path.exists', side_effect=exists_side_effect_edit)
    mocker.patch('os.path.exists') # Let mocker handle calling original

    original_builtin_open = open
    def open_side_effect_edit(file, mode='r', *args, **kwargs):
        if isinstance(file, int): return original_builtin_open(file, mode, *args, **kwargs)
        current_mocked_dir = mock_cwd_state[0]
        path_to_open = file if os.path.isabs(file) else os.path.abspath(os.path.join(current_mocked_dir, file))

        # Ensure dir exists for writing
        if 'w' in mode or 'a' in mode or 'x' in mode:
             os.makedirs(os.path.dirname(path_to_open), exist_ok=True)

        # Create dummy lyrics files when written by lyrics_processor or finaliser
        path_str = str(path_to_open)
        if path_str.endswith('(Lyrics Corrected).txt') and 'w' in mode:
            print(f"MOCK open (EDIT): Creating dummy corrected lyrics file: {path_to_open}")
            with original_builtin_open(path_to_open, 'w') as f:
                f.write("Edited lyrics line 1\nEdited lyrics line 2")
            return original_builtin_open(path_to_open, mode, *args, **kwargs)
        elif path_str.endswith('(Karaoke).lrc') and 'w' in mode:
            print(f"MOCK open (EDIT): Creating dummy karaoke LRC file: {path_to_open}")
            with original_builtin_open(path_to_open, 'w') as f:
                # Add MidiCo header for lyrics-converter compatibility
                f.write("[re:MidiCo]\n[00:01.000]Edited line 1\n[00:02.000]Edited line 2")
            return original_builtin_open(path_to_open, mode, *args, **kwargs)
        elif path_str.endswith('(Karaoke).ass') and 'w' in mode:
            print(f"MOCK open (EDIT): Creating dummy karaoke ASS file: {path_to_open}")
            # Create a minimal valid ASS structure
            with original_builtin_open(path_to_open, 'w') as f:
                f.write("[Script Info]\nTitle: Dummy ASS\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,20,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,2,10,10,10,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.000,0:00:02.000,Default,,0,0,0,,Edited line 1\nDialogue: 0,0:00:02.000,0:00:03.000,Default,,0,0,0,,Edited line 2\n")
            return original_builtin_open(path_to_open, mode, *args, **kwargs)

        # Fallback to original open for reading or unhandled writes
        return original_builtin_open(path_to_open, mode, *args, **kwargs)
    mocker.patch('builtins.open', side_effect=open_side_effect_edit)
    mocker.patch('io.open', side_effect=open_side_effect_edit)

    original_os_stat = os.stat
    def stat_side_effect_edit(path, *args, **kwargs):
        current_mocked_dir = mock_cwd_state[0]
        path_to_stat = path if os.path.isabs(path) else os.path.abspath(os.path.join(current_mocked_dir, path))
        return original_os_stat(path_to_stat, *args, **kwargs)
    mocker.patch('os.stat', side_effect=stat_side_effect_edit)

    original_os_remove = os.remove
    def remove_side_effect_edit(path):
        current_mocked_dir = mock_cwd_state[0]
        path_to_remove = path if os.path.isabs(path) else os.path.abspath(os.path.join(current_mocked_dir, path))
        return original_os_remove(path_to_remove)
    mocker.patch('os.remove', side_effect=remove_side_effect_edit)

    # Mock shutil.move for backup process
    original_shutil_move = shutil.move
    backup_dir_path = None
    moved_to_backup = []
    def move_side_effect_edit(src, dst):
        nonlocal backup_dir_path
        # Check if the destination *directory* is a backup directory
        dst_dir_basename = os.path.basename(os.path.dirname(dst))
        is_backup_dest = dst_dir_basename.startswith('backup_') or dst_dir_basename.startswith('version-')

        if is_backup_dest:
             # Special case for the test: Don't move the (With Vocals).mkv needed by finalise
             if os.path.basename(src) == os.path.basename(with_vocals_mkv_path):
                 print(f"MOCK shutil.move (EDIT): Skipping move of '{os.path.basename(src)}' to backup dir '{dst}' for test purposes.")
                 # Don't add to moved_to_backup list, don't perform move
                 # Ensure the destination directory exists even if we skip the move
                 os.makedirs(os.path.dirname(dst), exist_ok=True)
                 return dst # Return dst as if move was successful
             else:
                 backup_dir_path = os.path.dirname(dst) # Capture the backup dir path
                 print(f"MOCK shutil.move (EDIT): Moving '{os.path.basename(src)}' to backup dir '{backup_dir_path}'")
                 moved_to_backup.append(os.path.basename(src))
                 os.makedirs(os.path.dirname(dst), exist_ok=True)
                 return original_shutil_move(src, dst)
        # Check if moving the processed dir *into* the organised dir
        elif os.path.dirname(dst) == str(organised_dir):
             print(f"MOCK shutil.move (EDIT): Moving final dir '{os.path.basename(src)}' to organised dir parent '{os.path.dirname(dst)}'")
             print(f"MOCK shutil.move (EDIT): src = {src}")
             print(f"MOCK shutil.move (EDIT): dst = {dst}")
             # Ensure organised_dir exists
             os.makedirs(str(organised_dir), exist_ok=True)
             # Try original shutil.move again
             try:
                print(f"MOCK shutil.move (EDIT): Calling original_shutil_move('{src}', '{dst}')")
                result = original_shutil_move(src, dst)
                print(f"MOCK shutil.move (EDIT): original_shutil_move result: {result}")
                return result
             except Exception as e:
                print(f"MOCK shutil.move (EDIT): original_shutil_move failed: {e}")
                # Re-raise the error to fail the test if move doesn't work
                raise
        else:
             print(f"MOCK shutil.move (EDIT): Default move '{src}' -> '{dst}'")
             # Ensure parent dir exists for default moves too
             if os.path.dirname(dst):
                 os.makedirs(os.path.dirname(dst), exist_ok=True)
             return original_shutil_move(src, dst)
    mocker.patch('shutil.move', side_effect=move_side_effect_edit)

    # Mock shutil.copytree for lyrics backup
    original_shutil_copytree = shutil.copytree
    lyrics_copied_to_backup = False
    def copytree_side_effect_edit(src, dst, **kwargs):
        nonlocal lyrics_copied_to_backup
        # Ensure src/dst are strings
        src_str = str(src)
        dst_str = str(dst)
        # Check if backing up the 'lyrics' dir to a versioned/backup destination dir
        dst_dir = os.path.dirname(dst_str)
        dst_dir_basename = os.path.basename(dst_dir) if dst_dir else ''
        is_lyrics_backup = os.path.basename(src_str) == 'lyrics' and \
                           (dst_dir_basename.startswith('backup_') or dst_dir_basename.startswith('version-'))

        if is_lyrics_backup:
            print(f"MOCK copytree (EDIT): Copying '{src_str}' to backup location '{dst_str}'")
            lyrics_copied_to_backup = True
            # Let original handle the copy
            return original_shutil_copytree(src_str, dst_str, **kwargs)
        else:
            print(f"MOCK copytree (EDIT): Default copytree '{src_str}' -> '{dst_str}'")
            return original_shutil_copytree(src_str, dst_str, **kwargs)
    mocker.patch('shutil.copytree', side_effect=copytree_side_effect_edit)

    # Mock shutil.rmtree for removing original lyrics dir after backup
    original_shutil_rmtree = shutil.rmtree
    lyrics_removed_after_backup = False
    def rmtree_side_effect_edit(path, **kwargs):
        nonlocal lyrics_removed_after_backup
        if os.path.basename(path) == 'lyrics' and lyrics_copied_to_backup:
            lyrics_removed_after_backup = True
            return original_shutil_rmtree(path, **kwargs)
        else:
            return original_shutil_rmtree(path, **kwargs)
    mocker.patch('shutil.rmtree', side_effect=rmtree_side_effect_edit)

    # Mock LyricsProcessor.transcribe_lyrics with a side effect to create files
    def transcribe_side_effect(*args, **kwargs):
        # Simulate file creation within the mocked CWD
        current_mocked_dir = mock_current_dir_state()
        lrc_path = os.path.join(current_mocked_dir, f"{base_name} (Karaoke).lrc")
        ass_path = os.path.join(current_mocked_dir, f"{base_name} (Karaoke).ass")
        txt_path = os.path.join(current_mocked_dir, f"{base_name} (Lyrics Corrected).txt")
        lyrics_output_dir_path = os.path.join(current_mocked_dir, "lyrics") # Path where lyrics processor might create dir

        os.makedirs(lyrics_output_dir_path, exist_ok=True)

        print(f"MOCK transcribe_lyrics: Creating dummy LRC file: {lrc_path}")
        with original_builtin_open(lrc_path, 'w') as f:
            # Add MidiCo header for lyrics-converter compatibility
            f.write("[re:MidiCo]\n[00:01.000]Edited line 1\n[00:02.000]Edited line 2")

        print(f"MOCK transcribe_lyrics: Creating dummy ASS file: {ass_path}")
        with original_builtin_open(ass_path, 'w') as f:
             f.write("[Script Info]\nTitle: Dummy ASS\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,20,&H00FFFFFF,&H0000FFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,2,10,10,10,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\nDialogue: 0,0:00:01.000,0:00:02.000,Default,,0,0,0,,Edited line 1\nDialogue: 0,0:00:02.000,0:00:03.000,Default,,0,0,0,,Edited line 2\n")

        print(f"MOCK transcribe_lyrics: Creating dummy TXT file: {txt_path}")
        with original_builtin_open(txt_path, 'w') as f:
            f.write("Edited lyrics line 1\nEdited lyrics line 2")

        # Return the expected dictionary structure
        return {
            'corrected_lyrics_text': 'Edited lyrics line 1\nEdited lyrics line 2',
            'corrected_lyrics_text_filepath': txt_path,
            'lyrics_output_dir': lyrics_output_dir_path,
            'lrc_file': lrc_path,
            'ass_file': ass_path,
        }

    mock_transcribe = mocker.patch(
        'karaoke_prep.lyrics_processor.LyricsProcessor.transcribe_lyrics',
        side_effect=transcribe_side_effect
    )

    # Mock ReviewServer.start
    def mock_start_return_self_correction_result(mock_instance):
        return mock_instance.correction_result
    mocker.patch(
        'lyrics_transcriber.review.server.ReviewServer.start',
        side_effect=mock_start_return_self_correction_result,
        autospec=True
    )

    # Mock builtins.input for safety
    mocker.patch('builtins.input', return_value="unexpected_input_response_edit")

    # --- 3. Construct Args and Call async_main ---
    discord_webhook_url = "https://discord.com/api/webhooks/FAKE/EDIT_URL"
    rclone_destination = "googledrive:TestNomadKaraokeEdit"
    public_share_dir_path = tmp_path / "public_share_edit"
    public_share_dir_path.mkdir() # Create public share dir
    # Create required subdirectories within public_share_dir
    (public_share_dir_path / "MP4").mkdir()
    (public_share_dir_path / "MP4-720p").mkdir()
    (public_share_dir_path / "CDG").mkdir()

    test_argv = [
        "gen_cli.py",
        "--edit-lyrics",
        "--style_params_json", str(style_params_path),
        "--enable_cdg",
        "--enable_txt",
        "--organised_dir", str(organised_dir),
        "--organised_dir_rclone_root", f"andrewdropboxfull:{organised_dir.name}",
        "--public_share_dir", str(public_share_dir_path),
        "--brand_prefix", brand_prefix,
        "--youtube_client_secrets_file", str(yt_secrets_path),
        "--rclone_destination", rclone_destination,
        "--youtube_description_file", str(yt_desc_path),
        "--discord_webhook_url", discord_webhook_url,
        "--email_template_file", str(email_template_path),
        "-y",
    ]

    mocker.patch.object(sys, 'argv', test_argv)

    # Capture specific calls using spies
    prep_init_spy = mocker.spy(KaraokePrep, '__init__')
    finalise_init_spy = mocker.spy(KaraokeFinalise, '__init__')
    prep_process_spy = mocker.spy(KaraokePrep, 'process')
    finalise_process_spy = mocker.spy(KaraokeFinalise, 'process')
    backup_spy = mocker.spy(FileHandler, 'backup_existing_outputs')

    print("--- Calling async_main (edit-lyrics) ---")
    await async_main()
    print("--- async_main finished (edit-lyrics) ---")

    # --- 4. Assertions ---
    # Verify __init__ calls
    prep_init_spy.assert_called_once()
    _, prep_kwargs = prep_init_spy.call_args
    assert prep_kwargs.get('artist') == artist
    assert prep_kwargs.get('title') == title
    assert prep_kwargs.get('skip_separation') is True
    assert prep_kwargs.get('create_track_subfolders') is False

    finalise_init_spy.assert_called_once()
    _, finalise_kwargs = finalise_init_spy.call_args
    assert finalise_kwargs.get('keep_brand_code') is True
    assert finalise_kwargs.get('non_interactive') is True

    # Verify backup was called
    backup_spy.assert_called_once_with(ANY, str(existing_track_dir), artist, title)

    # Verify process calls
    prep_process_spy.assert_called_once()
    mock_transcribe.assert_called_once()
    finalise_process_spy.assert_called_once()
    _, finalise_kwargs = finalise_process_spy.call_args
    assert finalise_kwargs.get('replace_existing') is True

    # Verify backup happened
    assert backup_dir_path is not None
    assert os.path.isdir(backup_dir_path)
    assert f"{base_name} (Karaoke).lrc" in moved_to_backup
    assert f"{base_name} (Final Karaoke Lossless 4k).mp4" in moved_to_backup
    assert lyrics_copied_to_backup
    assert lyrics_removed_after_backup

    # Verify new lyrics file
    new_lyrics_file = existing_track_dir / f"{base_name} (Lyrics Corrected).txt"
    assert new_lyrics_file.is_file()
    content = new_lyrics_file.read_text()
    assert "Edited lyrics line 1" in content

    # Verify final directory move
    final_branded_dir_path_in_organised = organised_dir / existing_track_dir_name
    assert final_branded_dir_path_in_organised.is_dir()

    # Verify external calls
    mock_upload.assert_called_once()
    _, upload_kwargs = mock_upload.call_args
    assert upload_kwargs.get('video_title') == f"{brand_code} - {artist} - {title}"
    assert upload_kwargs.get('existing_video_id') == 'existing_video_id'

    mock_requests_post.assert_called_once()
    _, post_kwargs = mock_requests_post.call_args
    assert post_kwargs.get('url') == discord_webhook_url
    assert artist in post_kwargs['json']['content']
    assert "youtu.be/replaced_video_id" in post_kwargs['json']['content']

    mock_draft_create.assert_called_once()

    # Verify clipboard calls
    assert call(f"https://fake.sharing.link/{existing_track_dir_name}") in mock_pyperclip.call_args_list
    assert call("https://youtu.be/replaced_video_id") in mock_pyperclip.call_args_list 