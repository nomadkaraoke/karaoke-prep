import os
import pytest
import tempfile
import shutil
import subprocess
from karaoke_prep.karaoke_prep import KaraokePrep

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

        # Call process() and await the result
        result = await kp.process()

        # Verify that the result is a list (even for a single track)
        assert isinstance(result, list)
        assert len(result) > 0

        # Get the first track result
        track = result[0]
        assert isinstance(track, dict)
        assert "track_output_dir" in track
        assert "artist" in track
        assert "title" in track

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