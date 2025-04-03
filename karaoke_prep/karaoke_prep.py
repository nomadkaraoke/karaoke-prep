import os
import sys
import re
import glob
import logging
import tempfile
import shutil
import asyncio
import signal
import time
import fcntl
import errno
import psutil
from datetime import datetime
import importlib.resources as pkg_resources
import yt_dlp.YoutubeDL as ydl
from PIL import Image, ImageDraw, ImageFont
from lyrics_transcriber import LyricsTranscriber, OutputConfig, TranscriberConfig, LyricsConfig
from lyrics_transcriber.core.controller import LyricsControllerResult
from pydub import AudioSegment
import json
from dotenv import load_dotenv
from .config import (
    load_style_params,
    setup_title_format,
    setup_end_format,
    get_video_durations,
    get_existing_images,
    setup_ffmpeg_command,
)
from .metadata import extract_info_for_online_media, parse_track_metadata


class KaraokePrep:
    def __init__(
        self,
        # Basic inputs
        input_media=None,
        artist=None,
        title=None,
        filename_pattern=None,
        # Logging & Debugging
        dry_run=False,
        logger=None,
        log_level=logging.DEBUG,
        log_formatter=None,
        render_bounding_boxes=False,
        # Input/Output Configuration
        output_dir=".",
        create_track_subfolders=False,
        lossless_output_format="FLAC",
        output_png=True,
        output_jpg=True,
        # Audio Processing Configuration
        clean_instrumental_model="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        backing_vocals_models=["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"],
        other_stems_models=["htdemucs_6s.yaml"],
        model_file_dir=os.path.join(tempfile.gettempdir(), "audio-separator-models"),
        existing_instrumental=None,
        # Lyrics Configuration
        lyrics_artist=None,
        lyrics_title=None,
        lyrics_file=None,
        skip_lyrics=False,
        skip_transcription=False,
        skip_transcription_review=False,
        render_video=True,
        subtitle_offset_ms=0,
        # Style Configuration
        style_params_json=None,
        # Add the new parameter
        skip_separation=False,
    ):
        self.log_level = log_level
        self.log_formatter = log_formatter

        if logger is None:
            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(log_level)

            self.log_handler = logging.StreamHandler()

            if self.log_formatter is None:
                self.log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")

            self.log_handler.setFormatter(self.log_formatter)
            self.logger.addHandler(self.log_handler)
        else:
            self.logger = logger

        self.logger.debug(f"KaraokePrep instantiating with input_media: {input_media} artist: {artist} title: {title}")

        self.dry_run = dry_run
        self.extractor = None  # Will be set later based on source (Original or yt-dlp extractor)
        self.media_id = None  # Will be set by parse_track_metadata if applicable
        self.url = None  # Will be set by parse_track_metadata if applicable
        self.input_media = input_media
        self.artist = artist
        self.title = title
        self.filename_pattern = filename_pattern

        # Audio Processing
        self.clean_instrumental_model = clean_instrumental_model
        self.backing_vocals_models = backing_vocals_models
        self.other_stems_models = other_stems_models
        self.model_file_dir = model_file_dir
        self.existing_instrumental = existing_instrumental
        self.skip_separation = skip_separation

        # Input/Output
        self.output_dir = output_dir
        self.lossless_output_format = lossless_output_format.lower()
        self.create_track_subfolders = create_track_subfolders
        self.output_png = output_png
        self.output_jpg = output_jpg

        # Lyrics
        self.lyrics = None
        self.lyrics_artist = lyrics_artist
        self.lyrics_title = lyrics_title
        self.lyrics_file = lyrics_file
        self.skip_lyrics = skip_lyrics
        self.skip_transcription = skip_transcription
        self.skip_transcription_review = skip_transcription_review
        self.render_video = render_video
        # Style
        self.subtitle_offset_ms = subtitle_offset_ms
        self.render_bounding_boxes = render_bounding_boxes
        self.style_params_json = style_params_json

        # Load style parameters using the config module
        self.style_params = load_style_params(self.style_params_json, self.logger)

        # Set up title and end formats using the config module
        self.title_format = setup_title_format(self.style_params)
        self.end_format = setup_end_format(self.style_params)

        # Get video durations and existing images using the config module
        self.intro_video_duration, self.end_video_duration = get_video_durations(self.style_params)
        self.existing_title_image, self.existing_end_image = get_existing_images(self.style_params)

        # Set up ffmpeg command using the config module
        self.ffmpeg_base_command = setup_ffmpeg_command(self.log_level)

        self.logger.debug(f"Initialized title_format with extra_text: {self.title_format['extra_text']}")
        self.logger.debug(f"Initialized title_format with extra_text_region: {self.title_format['extra_text_region']}")

        self.logger.debug(f"Initialized end_format with extra_text: {self.end_format['extra_text']}")
        self.logger.debug(f"Initialized end_format with extra_text_region: {self.end_format['extra_text_region']}")

        self.extracted_info = None  # Will be populated by extract_info_for_online_media if needed
        self.persistent_artist = None  # Used for playlists

        self.logger.debug(f"KaraokePrep lossless_output_format: {self.lossless_output_format}")

        if not os.path.exists(self.output_dir):
            self.logger.debug(f"Overall output dir {self.output_dir} did not exist, creating")
            os.makedirs(self.output_dir)
        else:
            self.logger.debug(f"Overall output dir {self.output_dir} already exists")

    # Compatibility methods for tests - these call the new functions in metadata.py
    def extract_info_for_online_media(self, input_url=None, input_artist=None, input_title=None):
        """Compatibility method that calls the function in metadata.py"""
        self.extracted_info = extract_info_for_online_media(input_url, input_artist, input_title, self.logger)
        return self.extracted_info

    def parse_single_track_metadata(self, input_artist, input_title):
        """Compatibility method that calls the function in metadata.py"""
        metadata_result = parse_track_metadata(self.extracted_info, input_artist, input_title, self.persistent_artist, self.logger)
        self.url = metadata_result["url"]
        self.extractor = metadata_result["extractor"]
        self.media_id = metadata_result["media_id"]
        self.artist = metadata_result["artist"]
        self.title = metadata_result["title"]

    async def prep_single_track(self):
        # Add signal handler at the start
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown(s)))

        try:
            self.logger.info(f"Preparing single track: {self.artist} - {self.title}")

            if self.input_media is not None and os.path.isfile(self.input_media):
                self.extractor = "Original"
            else:
                # Use the imported parse_track_metadata function
                if self.extracted_info is not None:
                    metadata_result = parse_track_metadata(
                        self.extracted_info, self.artist, self.title, self.persistent_artist, self.logger
                    )
                    self.url = metadata_result["url"]
                    self.extractor = metadata_result["extractor"]
                    self.media_id = metadata_result["media_id"]
                    self.artist = metadata_result["artist"]
                    self.title = metadata_result["title"]

            self.logger.info(f"Preparing output path for track: {self.title} by {self.artist}")
            if self.dry_run:
                return None

            track_output_dir, artist_title = self.setup_output_paths(self.artist, self.title)

            processed_track = {
                "track_output_dir": track_output_dir,
                "artist": self.artist,
                "title": self.title,
                "extractor": self.extractor,
                "extracted_info": self.extracted_info,
                "lyrics": None,
                "processed_lyrics": None,
                "separated_audio": {},
            }

            processed_track["input_media"] = None
            processed_track["input_still_image"] = None
            processed_track["input_audio_wav"] = None

            if self.input_media is not None and os.path.isfile(self.input_media):
                input_wav_filename_pattern = os.path.join(track_output_dir, f"{artist_title} ({self.extractor} *.wav")
                input_wav_glob = glob.glob(input_wav_filename_pattern)

                if input_wav_glob:
                    processed_track["input_audio_wav"] = input_wav_glob[0]
                    self.logger.info(f"Input media WAV file already exists, skipping conversion: {processed_track['input_audio_wav']}")
                else:
                    output_filename_no_extension = os.path.join(track_output_dir, f"{artist_title} ({self.extractor})")

                    self.logger.info(f"Copying input media from {self.input_media} to new directory...")
                    processed_track["input_media"] = self.copy_input_media(self.input_media, output_filename_no_extension)

                    self.logger.info("Converting input media to WAV for audio processing...")
                    processed_track["input_audio_wav"] = self.convert_to_wav(processed_track["input_media"], output_filename_no_extension)

            else:
                # WebM may not always be the output format from ytdlp, but it's common and this is just a convenience cache
                input_webm_filename_pattern = os.path.join(track_output_dir, f"{artist_title} ({self.extractor} *.webm")
                input_webm_glob = glob.glob(input_webm_filename_pattern)

                input_png_filename_pattern = os.path.join(track_output_dir, f"{artist_title} ({self.extractor} *.png")
                input_png_glob = glob.glob(input_png_filename_pattern)

                input_wav_filename_pattern = os.path.join(track_output_dir, f"{artist_title} ({self.extractor} *.wav")
                input_wav_glob = glob.glob(input_wav_filename_pattern)

                if input_webm_glob and input_png_glob and input_wav_glob:
                    processed_track["input_media"] = input_webm_glob[0]
                    processed_track["input_still_image"] = input_png_glob[0]
                    processed_track["input_audio_wav"] = input_wav_glob[0]

                    self.logger.info(f"Input media files already exist, skipping download: {processed_track['input_media']} + .wav + .png")
                else:
                    if self.url:
                        output_filename_no_extension = os.path.join(track_output_dir, f"{artist_title} ({self.extractor} {self.media_id})")

                        self.logger.info(f"Downloading input media from {self.url}...")
                        processed_track["input_media"] = self.download_video(self.url, output_filename_no_extension)

                        self.logger.info("Extracting still image from downloaded media (if input is video)...")
                        processed_track["input_still_image"] = self.extract_still_image_from_video(
                            processed_track["input_media"], output_filename_no_extension
                        )

                        self.logger.info("Converting downloaded video to WAV for audio processing...")
                        processed_track["input_audio_wav"] = self.convert_to_wav(
                            processed_track["input_media"], output_filename_no_extension
                        )
                    else:
                        self.logger.warning(f"Skipping download due to missing URL.")

            if self.skip_lyrics:
                self.logger.info("Skipping lyrics fetch as requested.")
                processed_track["lyrics"] = None
                processed_track["processed_lyrics"] = None
            else:
                lyrics_artist = self.lyrics_artist or self.artist
                lyrics_title = self.lyrics_title or self.title

                # Create futures for both operations
                transcription_future = None
                separation_future = None

                self.logger.info("=== Starting Parallel Processing ===")

                if not self.skip_lyrics:
                    self.logger.info("Creating transcription future...")
                    # Run transcription in a separate thread
                    transcription_future = asyncio.create_task(
                        asyncio.to_thread(
                            self.transcribe_lyrics, processed_track["input_audio_wav"], lyrics_artist, lyrics_title, track_output_dir
                        )
                    )
                    self.logger.info(f"Transcription future created, type: {type(transcription_future)}")

                if not self.skip_separation:
                    self.logger.info("Creating separation future...")
                    # Run separation in a separate thread
                    separation_future = asyncio.create_task(
                        asyncio.to_thread(
                            self.process_audio_separation,
                            audio_file=processed_track["input_audio_wav"],
                            artist_title=artist_title,
                            track_output_dir=track_output_dir,
                        )
                    )
                    self.logger.info(f"Separation future created, type: {type(separation_future)}")

                self.logger.info("About to await both operations with asyncio.gather...")
                # Wait for both operations to complete
                try:
                    results = await asyncio.gather(
                        transcription_future if transcription_future else asyncio.sleep(0),
                        separation_future if separation_future else asyncio.sleep(0),
                        return_exceptions=True,
                    )
                except asyncio.CancelledError:
                    self.logger.info("Received cancellation request, cleaning up...")
                    # Cancel any running futures
                    if transcription_future and not transcription_future.done():
                        transcription_future.cancel()
                    if separation_future and not separation_future.done():
                        separation_future.cancel()
                    # Wait for futures to complete cancellation
                    await asyncio.gather(
                        transcription_future if transcription_future else asyncio.sleep(0),
                        separation_future if separation_future else asyncio.sleep(0),
                        return_exceptions=True,
                    )
                    raise

                # Handle transcription results
                if transcription_future:
                    self.logger.info("Processing transcription results...")
                    try:
                        transcriber_outputs = results[0]
                        if isinstance(transcriber_outputs, Exception):
                            self.logger.error(f"Error during lyrics transcription: {transcriber_outputs}")
                            raise transcriber_outputs  # Re-raise the exception
                        elif transcriber_outputs:
                            self.logger.info("Successfully received transcription outputs")
                            self.lyrics = transcriber_outputs.get("corrected_lyrics_text")
                            processed_track["lyrics"] = transcriber_outputs.get("corrected_lyrics_text_filepath")
                    except Exception as e:
                        self.logger.error(f"Error processing transcription results: {e}")
                        self.logger.exception("Full traceback:")
                        raise  # Re-raise the exception

                # Handle separation results
                if separation_future:
                    self.logger.info("Processing separation results...")
                    try:
                        separation_results = results[1]
                        if isinstance(separation_results, Exception):
                            self.logger.error(f"Error during audio separation: {separation_results}")
                        else:
                            self.logger.info("Successfully received separation results")
                            processed_track["separated_audio"] = separation_results
                    except Exception as e:
                        self.logger.error(f"Error processing separation results: {e}")
                        self.logger.exception("Full traceback:")

                self.logger.info("=== Parallel Processing Complete ===")

            output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (Title)")
            processed_track["title_image_png"] = f"{output_image_filepath_noext}.png"
            processed_track["title_image_jpg"] = f"{output_image_filepath_noext}.jpg"
            processed_track["title_video"] = os.path.join(track_output_dir, f"{artist_title} (Title).mov")

            if not self._file_exists(processed_track["title_video"]) and not os.environ.get("KARAOKE_PREP_SKIP_TITLE_END_SCREENS"):
                self.logger.info(f"Creating title video...")
                self.create_title_video(
                    self.artist, self.title, self.title_format, output_image_filepath_noext, processed_track["title_video"]
                )

            output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (End)")
            processed_track["end_image_png"] = f"{output_image_filepath_noext}.png"
            processed_track["end_image_jpg"] = f"{output_image_filepath_noext}.jpg"
            processed_track["end_video"] = os.path.join(track_output_dir, f"{artist_title} (End).mov")

            if not self._file_exists(processed_track["end_video"]) and not os.environ.get("KARAOKE_PREP_SKIP_TITLE_END_SCREENS"):
                self.logger.info(f"Creating end screen video...")
                self.create_end_video(self.artist, self.title, self.end_format, output_image_filepath_noext, processed_track["end_video"])

            if self.skip_separation:
                self.logger.info("Skipping audio separation as requested.")
                processed_track["separated_audio"] = {
                    "clean_instrumental": {},
                    "backing_vocals": {},
                    "other_stems": {},
                    "combined_instrumentals": {},
                }
            elif self.existing_instrumental:
                self.logger.info(f"Using existing instrumental file: {self.existing_instrumental}")
                existing_instrumental_extension = os.path.splitext(self.existing_instrumental)[1]

                instrumental_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental Custom){existing_instrumental_extension}")

                if not self._file_exists(instrumental_path):
                    shutil.copy2(self.existing_instrumental, instrumental_path)

                processed_track["separated_audio"]["Custom"] = {
                    "instrumental": instrumental_path,
                    "vocals": None,
                }
            else:
                self.logger.info(f"Separating audio for track: {self.title} by {self.artist}")
                separation_results = self.process_audio_separation(
                    audio_file=processed_track["input_audio_wav"], artist_title=artist_title, track_output_dir=track_output_dir
                )
                processed_track["separated_audio"] = separation_results

            self.logger.info("Script finished, audio downloaded, lyrics fetched and audio separated!")

            return processed_track

        except Exception as e:
            self.logger.error(f"Error in prep_single_track: {e}")
            raise
        finally:
            # Remove signal handlers
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)

    async def shutdown(self, signal):
        """Handle shutdown signals gracefully."""
        self.logger.info(f"Received exit signal {signal.name}...")

        # Get all running tasks
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

        if tasks:
            self.logger.info(f"Cancelling {len(tasks)} outstanding tasks")
            # Cancel all running tasks
            for task in tasks:
                task.cancel()

            self.logger.info("Received cancellation request, cleaning up...")

            # Wait for all tasks to complete with cancellation
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass

        # Force exit after cleanup
        self.logger.info("Cleanup complete, exiting...")
        sys.exit(0)  # Add this line to force exit

    async def process_playlist(self):
        if self.artist is None or self.title is None:
            raise Exception("Error: Artist and Title are required for processing a local file.")

        if "entries" in self.extracted_info:
            track_results = []
            self.logger.info(f"Found {len(self.extracted_info['entries'])} entries in playlist, processing each invididually...")
            for entry in self.extracted_info["entries"]:
                self.extracted_info = entry
                self.logger.info(f"Processing playlist entry with title: {self.extracted_info['title']}")
                if not self.dry_run:
                    track_results.append(await self.prep_single_track())
                self.artist = self.persistent_artist
                self.title = None
            return track_results
        else:
            raise Exception(f"Failed to find 'entries' in playlist, cannot process")

    async def process_folder(self):
        if self.filename_pattern is None or self.artist is None:
            raise Exception("Error: Filename pattern and artist are required for processing a folder.")

        folder_path = self.input_media
        output_folder_path = os.path.join(os.getcwd(), os.path.basename(folder_path))

        if not os.path.exists(output_folder_path):
            if not self.dry_run:
                self.logger.info(f"DRY RUN: Would create output folder: {output_folder_path}")
                os.makedirs(output_folder_path)
        else:
            self.logger.info(f"Output folder already exists: {output_folder_path}")

        pattern = re.compile(self.filename_pattern)
        tracks = []

        for filename in sorted(os.listdir(folder_path)):
            match = pattern.match(filename)
            if match:
                title = match.group("title")
                file_path = os.path.join(folder_path, filename)
                self.input_media = file_path
                self.title = title

                track_index = match.group("index") if "index" in match.groupdict() else None

                self.logger.info(f"Processing track: {track_index} with title: {title} from file: {filename}")

                track_output_dir = os.path.join(output_folder_path, f"{track_index} - {self.artist} - {title}")

                if not self.dry_run:
                    track = await self.prep_single_track()
                    tracks.append(track)

                    # Move the track folder to the output folder
                    track_folder = track["track_output_dir"]
                    shutil.move(track_folder, track_output_dir)
                else:
                    self.logger.info(f"DRY RUN: Would move track folder to: {os.path.basename(track_output_dir)}")

        return tracks

    async def process(self):
        if self.input_media is not None and os.path.isdir(self.input_media):
            self.logger.info(f"Input media {self.input_media} is a local folder, processing each file individually...")
            return await self.process_folder()
        elif self.input_media is not None and os.path.isfile(self.input_media):
            self.logger.info(f"Input media {self.input_media} is a local file, youtube logic will be skipped")
            return [await self.prep_single_track()]
        else:
            self.url = self.input_media
            # Use the imported extract_info_for_online_media function
            self.extracted_info = extract_info_for_online_media(
                input_url=self.url, input_artist=self.artist, input_title=self.title, logger=self.logger
            )

            if self.extracted_info and "playlist_count" in self.extracted_info:
                self.persistent_artist = self.artist
                self.logger.info(f"Input URL is a playlist, beginning batch operation with persistent artist: {self.persistent_artist}")
                return await self.process_playlist()
            else:
                self.logger.info(f"Input URL is not a playlist, processing single track")
                return [await self.prep_single_track()]
