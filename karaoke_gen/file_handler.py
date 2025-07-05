import os
import glob
import logging
import shutil
import tempfile
import yt_dlp.YoutubeDL as ydl
from .utils import sanitize_filename


# Placeholder class or functions for file handling
class FileHandler:
    def __init__(self, logger, ffmpeg_base_command, create_track_subfolders, dry_run):
        self.logger = logger
        self.ffmpeg_base_command = ffmpeg_base_command
        self.create_track_subfolders = create_track_subfolders
        self.dry_run = dry_run

    def _file_exists(self, file_path):
        """Check if a file exists and log the result."""
        exists = os.path.isfile(file_path)
        if exists:
            self.logger.info(f"File already exists, skipping creation: {file_path}")
        return exists

    # Placeholder methods - to be filled by user moving code
    def copy_input_media(self, input_media, output_filename_no_extension):
        self.logger.debug(f"Copying media from local path {input_media} to filename {output_filename_no_extension} + existing extension")

        copied_file_name = output_filename_no_extension + os.path.splitext(input_media)[1]
        self.logger.debug(f"Target filename: {copied_file_name}")

        # Check if source and destination are the same
        if os.path.abspath(input_media) == os.path.abspath(copied_file_name):
            self.logger.info("Source and destination are the same file, skipping copy")
            return input_media

        self.logger.debug(f"Copying {input_media} to {copied_file_name}")
        shutil.copy2(input_media, copied_file_name)

        return copied_file_name

    def download_video(self, url, output_filename_no_extension, cookies_str=None):
        self.logger.debug(f"Downloading media from URL {url} to filename {output_filename_no_extension} + (as yet) unknown extension")

        ydl_opts = {
            "quiet": True,
            "format": "bv*+ba/b",  # if a combined video + audio format is better than the best video-only format use the combined format
            "outtmpl": f"{output_filename_no_extension}.%(ext)s",
            # Enhanced anti-detection options
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "referer": "https://www.youtube.com/",
            "sleep_interval": 1,
            "max_sleep_interval": 3,
            "fragment_retries": 3,
            "extractor_retries": 3,
            "retries": 3,
            # Headers to appear more human
            "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-us,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            },
        }

        # Add cookies if provided
        if cookies_str:
            self.logger.info("Using provided cookies for enhanced YouTube download access")
            # Save cookies to a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(cookies_str)
                ydl_opts['cookiefile'] = f.name
        else:
            self.logger.info("No cookies provided for download - attempting standard download")

        try:
            with ydl(ydl_opts) as ydl_instance:
                ydl_instance.download([url])

                # Search for the file with any extension
                downloaded_files = glob.glob(f"{output_filename_no_extension}.*")
                if downloaded_files:
                    downloaded_file_name = downloaded_files[0]  # Assume the first match is the correct one
                    self.logger.info(f"Download finished, returning downloaded filename: {downloaded_file_name}")
                    return downloaded_file_name
                else:
                    self.logger.error("No files found matching the download pattern.")
                    return None
        finally:
            # Clean up temporary cookie file if it was created
            if cookies_str and 'cookiefile' in ydl_opts:
                try:
                    import os
                    os.unlink(ydl_opts['cookiefile'])
                except:
                    pass

    def extract_still_image_from_video(self, input_filename, output_filename_no_extension):
        output_filename = output_filename_no_extension + ".png"
        self.logger.info(f"Extracting still image from position 30s input media")
        ffmpeg_command = f'{self.ffmpeg_base_command} -i "{input_filename}" -ss 00:00:30 -vframes 1 "{output_filename}"'
        self.logger.debug(f"Running command: {ffmpeg_command}")
        os.system(ffmpeg_command)
        return output_filename

    def convert_to_wav(self, input_filename, output_filename_no_extension):
        """Convert input audio to WAV format, with input validation."""
        # Validate input file exists and is readable
        if not os.path.isfile(input_filename):
            raise Exception(f"Input audio file not found: {input_filename}")

        if os.path.getsize(input_filename) == 0:
            raise Exception(f"Input audio file is empty: {input_filename}")

        # Validate input file format using ffprobe
        probe_command = f'ffprobe -v error -show_entries stream=codec_type -of default=noprint_wrappers=1 "{input_filename}"'
        probe_output = os.popen(probe_command).read()

        if "codec_type=audio" not in probe_output:
            raise Exception(f"No valid audio stream found in file: {input_filename}")

        output_filename = output_filename_no_extension + ".wav"
        self.logger.info(f"Converting input media to audio WAV file")
        ffmpeg_command = f'{self.ffmpeg_base_command} -n -i "{input_filename}" "{output_filename}"'
        self.logger.debug(f"Running command: {ffmpeg_command}")
        if not self.dry_run:
            os.system(ffmpeg_command)
        return output_filename

    def setup_output_paths(self, output_dir, artist, title):
        if title is None and artist is None:
            raise ValueError("Error: At least title or artist must be provided")

        # If only title is provided, use it for both artist and title portions of paths
        if artist is None:
            sanitized_title = sanitize_filename(title)
            artist_title = sanitized_title
        else:
            sanitized_artist = sanitize_filename(artist)
            sanitized_title = sanitize_filename(title)
            artist_title = f"{sanitized_artist} - {sanitized_title}"

        track_output_dir = output_dir
        if self.create_track_subfolders:
            track_output_dir = os.path.join(output_dir, f"{artist_title}")

        if not os.path.exists(track_output_dir):
            self.logger.debug(f"Output dir {track_output_dir} did not exist, creating")
            os.makedirs(track_output_dir)

        return track_output_dir, artist_title

    def backup_existing_outputs(self, track_output_dir, artist, title):
        """
        Backup existing outputs to a versioned folder.

        Args:
            track_output_dir: The directory containing the track outputs
            artist: The artist name
            title: The track title

        Returns:
            The path to the original input audio file
        """
        self.logger.info(f"Backing up existing outputs for {artist} - {title}")

        # Sanitize artist and title for filenames
        sanitized_artist = sanitize_filename(artist)
        sanitized_title = sanitize_filename(title)
        base_name = f"{sanitized_artist} - {sanitized_title}"

        # Find the next available version number
        version_num = 1
        while os.path.exists(os.path.join(track_output_dir, f"version-{version_num}")):
            version_num += 1

        version_dir = os.path.join(track_output_dir, f"version-{version_num}")
        self.logger.info(f"Creating backup directory: {version_dir}")
        os.makedirs(version_dir, exist_ok=True)

        # Find the input audio file (we'll need this for re-running the transcription)
        input_audio_wav = os.path.join(track_output_dir, f"{base_name}.wav")
        if not os.path.exists(input_audio_wav):
            self.logger.warning(f"Input audio file not found: {input_audio_wav}")
            # Try to find any WAV file
            wav_files = glob.glob(os.path.join(track_output_dir, "*.wav"))
            if wav_files:
                input_audio_wav = wav_files[0]
                self.logger.info(f"Using alternative input audio file: {input_audio_wav}")
            else:
                raise Exception(f"No input audio file found in {track_output_dir}")

        # List of file patterns to move
        file_patterns = [
            f"{base_name} (With Vocals).*",
            f"{base_name} (Karaoke).*",
            f"{base_name} (Final Karaoke*).*",
        ]

        # Move files matching patterns to version directory
        for pattern in file_patterns:
            for file_path in glob.glob(os.path.join(track_output_dir, pattern)):
                if os.path.isfile(file_path):
                    dest_path = os.path.join(version_dir, os.path.basename(file_path))
                    self.logger.info(f"Moving {file_path} to {dest_path}")
                    if not self.dry_run:
                        shutil.move(file_path, dest_path)

        # Also backup the lyrics directory
        lyrics_dir = os.path.join(track_output_dir, "lyrics")
        if os.path.exists(lyrics_dir):
            lyrics_backup_dir = os.path.join(version_dir, "lyrics")
            self.logger.info(f"Backing up lyrics directory to {lyrics_backup_dir}")
            if not self.dry_run:
                shutil.copytree(lyrics_dir, lyrics_backup_dir)
                # Remove the original lyrics directory
                shutil.rmtree(lyrics_dir)

        return input_audio_wav
