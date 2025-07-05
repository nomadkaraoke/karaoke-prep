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
from .file_handler import FileHandler
from .audio_processor import AudioProcessor
from .lyrics_processor import LyricsProcessor
from .video_generator import VideoGenerator


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
        # YouTube/Online Configuration
        cookies_str=None,
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

        # Input/Output - Keep these as they might be needed for logic outside handlers or passed to multiple handlers
        self.output_dir = output_dir
        self.lossless_output_format = lossless_output_format.lower()
        self.create_track_subfolders = create_track_subfolders
        self.output_png = output_png
        self.output_jpg = output_jpg

        # Lyrics Config - Keep needed ones
        self.lyrics_artist = lyrics_artist
        self.lyrics_title = lyrics_title
        self.lyrics_file = lyrics_file # Passed to LyricsProcessor
        self.skip_lyrics = skip_lyrics # Used in prep_single_track logic
        self.skip_transcription = skip_transcription # Passed to LyricsProcessor
        self.skip_transcription_review = skip_transcription_review # Passed to LyricsProcessor
        self.render_video = render_video # Passed to LyricsProcessor
        self.subtitle_offset_ms = subtitle_offset_ms # Passed to LyricsProcessor

        # Audio Config - Keep needed ones
        self.existing_instrumental = existing_instrumental # Used in prep_single_track logic
        self.skip_separation = skip_separation # Used in prep_single_track logic
        self.model_file_dir = model_file_dir # Passed to AudioProcessor

        # Style Config - Keep needed ones
        self.render_bounding_boxes = render_bounding_boxes # Passed to VideoGenerator
        self.style_params_json = style_params_json # Passed to LyricsProcessor

        # YouTube/Online Config
        self.cookies_str = cookies_str # Passed to metadata extraction and file download

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

        # Instantiate Handlers
        self.file_handler = FileHandler(
            logger=self.logger,
            ffmpeg_base_command=self.ffmpeg_base_command,
            create_track_subfolders=self.create_track_subfolders,
            dry_run=self.dry_run,
        )

        self.audio_processor = AudioProcessor(
             logger=self.logger,
             log_level=self.log_level,
             log_formatter=self.log_formatter,
             model_file_dir=self.model_file_dir,
             lossless_output_format=self.lossless_output_format,
             clean_instrumental_model=clean_instrumental_model, # Passed directly from args
             backing_vocals_models=backing_vocals_models, # Passed directly from args
             other_stems_models=other_stems_models, # Passed directly from args
             ffmpeg_base_command=self.ffmpeg_base_command,
        )

        self.lyrics_processor = LyricsProcessor(
             logger=self.logger,
             style_params_json=self.style_params_json,
             lyrics_file=self.lyrics_file,
             skip_transcription=self.skip_transcription,
             skip_transcription_review=self.skip_transcription_review,
             render_video=self.render_video,
             subtitle_offset_ms=self.subtitle_offset_ms,
        )

        self.video_generator = VideoGenerator(
             logger=self.logger,
             ffmpeg_base_command=self.ffmpeg_base_command,
             render_bounding_boxes=self.render_bounding_boxes,
             output_png=self.output_png,
             output_jpg=self.output_jpg,
        )

        self.logger.debug(f"Initialized title_format with extra_text: {self.title_format['extra_text']}")
        self.logger.debug(f"Initialized title_format with extra_text_region: {self.title_format['extra_text_region']}")

        self.logger.debug(f"Initialized end_format with extra_text: {self.end_format['extra_text']}")
        self.logger.debug(f"Initialized end_format with extra_text_region: {self.end_format['extra_text_region']}")

        self.extracted_info = None  # Will be populated by extract_info_for_online_media if needed
        self.persistent_artist = None  # Used for playlists

        self.logger.debug(f"KaraokePrep lossless_output_format: {self.lossless_output_format}")

        # Use FileHandler method to check/create output dir
        if not os.path.exists(self.output_dir):
            self.logger.debug(f"Overall output dir {self.output_dir} did not exist, creating")
            os.makedirs(self.output_dir)
        else:
            self.logger.debug(f"Overall output dir {self.output_dir} already exists")

    # Compatibility methods for tests - these call the new functions in metadata.py
    def extract_info_for_online_media(self, input_url=None, input_artist=None, input_title=None):
        """Compatibility method that calls the function in metadata.py"""
        self.extracted_info = extract_info_for_online_media(input_url, input_artist, input_title, self.logger, self.cookies_str)
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

            # Determine extractor early based on input type
            # Assume self.extractor, self.url, self.media_id etc. are set by process() before calling this
            if self.input_media and os.path.isfile(self.input_media):
                if not self.extractor: # If extractor wasn't somehow set before (e.g., direct call)
                    self.extractor = "Original"
            elif self.url: # If it's a URL (set by process)
                 if not self.extractor: # Should have been set by parse_track_metadata in process()
                      self.logger.warning("Extractor not set before prep_single_track for URL, attempting fallback logic.")
                      # Fallback logic (less ideal, relies on potentially missing info)
                      if self.extracted_info and self.extracted_info.get('extractor'):
                          self.extractor = self.extracted_info['extractor']
                      elif self.media_id: # Try to guess based on ID format
                          # Basic youtube id check
                          if re.match(r'^[a-zA-Z0-9_-]{11}$', self.media_id):
                              self.extractor = "youtube"
                          else:
                              self.extractor = "UnknownSource" # Fallback if ID doesn't look like youtube
                      else:
                          self.extractor = "UnknownSource" # Final fallback
                      self.logger.info(f"Fallback extractor set to: {self.extractor}")
            elif self.input_media: # Not a file, not a URL -> maybe a direct URL string?
                self.logger.warning(f"Input media '{self.input_media}' is not a file and self.url was not set. Attempting to treat as URL.")
                # This path requires calling extract/parse again, less efficient
                try:
                    extracted = extract_info_for_online_media(self.input_media, self.artist, self.title, self.logger, self.cookies_str)
                    if extracted:
                         metadata_result = parse_track_metadata(
                             extracted, self.artist, self.title, self.persistent_artist, self.logger
                         )
                         self.url = metadata_result["url"]
                         self.extractor = metadata_result["extractor"]
                         self.media_id = metadata_result["media_id"]
                         self.artist = metadata_result["artist"]
                         self.title = metadata_result["title"]
                         self.logger.info(f"Successfully extracted metadata within prep_single_track for {self.input_media}")
                    else:
                         self.logger.error(f"Could not extract info for {self.input_media} within prep_single_track.")
                         self.extractor = "ErrorExtracting"
                         return None # Cannot proceed without metadata
                except Exception as meta_exc:
                     self.logger.error(f"Error during metadata extraction/parsing within prep_single_track: {meta_exc}")
                     self.extractor = "ErrorParsing"
                     return None # Cannot proceed
            else:
                 # If it's neither file nor URL, and input_media is None, check for existing files
                 # This path is mainly for the case where files exist from previous run
                 # We still need artist/title for filename generation
                 if not self.artist or not self.title:
                      self.logger.error("Cannot determine output path without artist/title when input_media is None and not a URL.")
                      return None
                 self.logger.info("Input media is None, assuming check for existing files based on artist/title.")
                 # We need a nominal extractor for filename matching if files exist
                 # Let's default to 'UnknownExisting' or try to infer if possible later
                 if not self.extractor:
                    self.extractor = "UnknownExisting"

            if not self.extractor:
                 self.logger.error("Could not determine extractor for the track.")
                 return None

            # Now self.extractor should be set correctly for path generation etc.

            self.logger.info(f"Preparing output path for track: {self.title} by {self.artist} (Extractor: {self.extractor})")
            if self.dry_run:
                return None

            # Delegate to FileHandler
            track_output_dir, artist_title = self.file_handler.setup_output_paths(self.output_dir, self.artist, self.title)

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

            if self.input_media and os.path.isfile(self.input_media):
                # --- Local File Input Handling ---
                input_wav_filename_pattern = os.path.join(track_output_dir, f"{artist_title} ({self.extractor}*).wav")
                input_wav_glob = glob.glob(input_wav_filename_pattern)

                if input_wav_glob:
                    processed_track["input_audio_wav"] = input_wav_glob[0]
                    self.logger.info(f"Input media WAV file already exists, skipping conversion: {processed_track['input_audio_wav']}")
                else:
                    output_filename_no_extension = os.path.join(track_output_dir, f"{artist_title} ({self.extractor})")

                    self.logger.info(f"Copying input media from {self.input_media} to new directory...")
                    # Delegate to FileHandler
                    processed_track["input_media"] = self.file_handler.copy_input_media(self.input_media, output_filename_no_extension)

                    self.logger.info("Converting input media to WAV for audio processing...")
                    # Delegate to FileHandler
                    processed_track["input_audio_wav"] = self.file_handler.convert_to_wav(processed_track["input_media"], output_filename_no_extension)

            else:
                # --- URL or Existing Files Handling ---
                # Construct patterns using the determined extractor
                base_pattern = os.path.join(track_output_dir, f"{artist_title} ({self.extractor}*)")
                input_media_glob = glob.glob(f"{base_pattern}.*webm") + glob.glob(f"{base_pattern}.*mp4") # Add other common formats if needed
                input_png_glob = glob.glob(f"{base_pattern}.png")
                input_wav_glob = glob.glob(f"{base_pattern}.wav")

                if input_media_glob and input_png_glob and input_wav_glob:
                    # Existing files found
                    processed_track["input_media"] = input_media_glob[0]
                    processed_track["input_still_image"] = input_png_glob[0]
                    processed_track["input_audio_wav"] = input_wav_glob[0]
                    self.logger.info(f"Found existing media files matching extractor '{self.extractor}', skipping download/conversion.")
                    # Ensure self.extractor reflects the found files if it was a fallback
                    # Extract the actual extractor string from the filename if needed, though it should match

                elif self.url: # URL provided and files not found, proceed with download
                    # Use media_id if available for better uniqueness
                    filename_suffix = f"{self.extractor} {self.media_id}" if self.media_id else self.extractor
                    output_filename_no_extension = os.path.join(track_output_dir, f"{artist_title} ({filename_suffix})")

                    self.logger.info(f"Downloading input media from {self.url}...")
                    # Delegate to FileHandler
                    processed_track["input_media"] = self.file_handler.download_video(self.url, output_filename_no_extension, self.cookies_str)

                    self.logger.info("Extracting still image from downloaded media (if input is video)...")
                    # Delegate to FileHandler
                    processed_track["input_still_image"] = self.file_handler.extract_still_image_from_video(
                        processed_track["input_media"], output_filename_no_extension
                    )

                    self.logger.info("Converting downloaded video to WAV for audio processing...")
                    # Delegate to FileHandler
                    processed_track["input_audio_wav"] = self.file_handler.convert_to_wav(
                        processed_track["input_media"], output_filename_no_extension
                    )
                else:
                     # This case means input_media was None, not a URL, and no existing files found
                     self.logger.error(f"Cannot proceed: No input file, no URL, and no existing files found for {artist_title}.")
                     return None

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
                            # Delegate to LyricsProcessor - pass original artist/title for filenames, lyrics_artist/lyrics_title for processing
                            self.lyrics_processor.transcribe_lyrics, 
                            processed_track["input_audio_wav"], 
                            self.artist,  # Original artist for filename generation
                            self.title,   # Original title for filename generation  
                            track_output_dir,
                            lyrics_artist,  # Lyrics artist for processing
                            lyrics_title    # Lyrics title for processing
                        )
                    )
                    self.logger.info(f"Transcription future created, type: {type(transcription_future)}")

                # Default to a placeholder task if separation won't run
                separation_future = asyncio.create_task(asyncio.sleep(0))

                # Only create real separation future if not skipping AND no existing instrumental provided
                if not self.skip_separation and not self.existing_instrumental:
                    self.logger.info("Creating separation future (not skipping and no existing instrumental)...")
                    # Run separation in a separate thread
                    separation_future = asyncio.create_task(
                        asyncio.to_thread(
                            # Delegate to AudioProcessor
                            self.audio_processor.process_audio_separation,
                            audio_file=processed_track["input_audio_wav"],
                            artist_title=artist_title,
                            track_output_dir=track_output_dir,
                        )
                    )
                    self.logger.info(f"Separation future created, type: {type(separation_future)}")
                elif self.existing_instrumental:
                     self.logger.info(f"Skipping separation future creation because existing instrumental was provided: {self.existing_instrumental}")
                elif self.skip_separation: # Check this condition explicitly for clarity
                     self.logger.info("Skipping separation future creation because skip_separation is True.")

                self.logger.info("About to await both operations with asyncio.gather...")
                # Wait for both operations to complete
                try:
                    results = await asyncio.gather(
                        transcription_future if transcription_future else asyncio.sleep(0), # Use placeholder if None
                        separation_future, # Already defaults to placeholder if not created
                        return_exceptions=True,
                    )
                except asyncio.CancelledError:
                    self.logger.info("Received cancellation request, cleaning up...")
                    # Cancel any running futures
                    if transcription_future and not transcription_future.done():
                        transcription_future.cancel()
                    if separation_future and not separation_future.done() and not isinstance(separation_future, asyncio.Task): # Check if it's a real task
                         # Don't try to cancel the asyncio.sleep(0) placeholder
                         separation_future.cancel()

                    # Wait for futures to complete cancellation
                    await asyncio.gather(
                        transcription_future if transcription_future else asyncio.sleep(0),
                        separation_future if separation_future else asyncio.sleep(0), # Use placeholder if None/Placeholder
                        return_exceptions=True,
                    )
                    raise

                # Handle transcription results
                if transcription_future:
                    self.logger.info("Processing transcription results...")
                    try:
                        # Index 0 corresponds to transcription_future in gather
                        transcriber_outputs = results[0]
                        # Check if the result is an exception or the actual output
                        if isinstance(transcriber_outputs, Exception):
                            self.logger.error(f"Error during lyrics transcription: {transcriber_outputs}")
                            # Optionally log traceback: self.logger.exception("Transcription error:")
                            raise transcriber_outputs  # Re-raise the exception
                        elif transcriber_outputs is not None and not isinstance(transcriber_outputs, asyncio.futures.Future): # Ensure it's not the placeholder future
                            self.logger.info(f"Successfully received transcription outputs: {type(transcriber_outputs)}")
                            # Ensure transcriber_outputs is a dictionary before calling .get()
                            if isinstance(transcriber_outputs, dict):
                                self.lyrics = transcriber_outputs.get("corrected_lyrics_text")
                                processed_track["lyrics"] = transcriber_outputs.get("corrected_lyrics_text_filepath")
                            else:
                                self.logger.warning(f"Unexpected type for transcriber_outputs: {type(transcriber_outputs)}, value: {transcriber_outputs}")
                        else:
                             self.logger.info("Transcription task did not return results (possibly skipped or placeholder).")
                    except Exception as e:
                        self.logger.error(f"Error processing transcription results: {e}")
                        self.logger.exception("Full traceback:")
                        raise # Re-raise the exception

                # Handle separation results only if a real future was created and ran
                # Check if separation_future was the placeholder or a real task
                # The result index in `results` depends on whether transcription_future existed
                separation_result_index = 1 if transcription_future else 0
                if separation_future is not None and not isinstance(separation_future, asyncio.Task) and len(results) > separation_result_index:
                    self.logger.info("Processing separation results...")
                    try:
                        separation_results = results[separation_result_index]
                         # Check if the result is an exception or the actual output
                        if isinstance(separation_results, Exception):
                            self.logger.error(f"Error during audio separation: {separation_results}")
                             # Optionally log traceback: self.logger.exception("Separation error:")
                            # Decide if you want to raise here or just log
                        elif separation_results is not None and not isinstance(separation_results, asyncio.futures.Future): # Ensure it's not the placeholder future
                            self.logger.info(f"Successfully received separation results: {type(separation_results)}")
                            if isinstance(separation_results, dict):
                                processed_track["separated_audio"] = separation_results
                            else:
                                 self.logger.warning(f"Unexpected type for separation_results: {type(separation_results)}, value: {separation_results}")
                        else:
                            self.logger.info("Separation task did not return results (possibly skipped or placeholder).")
                    except Exception as e:
                        self.logger.error(f"Error processing separation results: {e}")
                        self.logger.exception("Full traceback:")
                        # Decide if you want to raise here or just log
                elif not self.skip_separation and not self.existing_instrumental:
                    # This case means separation was supposed to run but didn't return results properly
                    self.logger.warning("Separation task was expected but did not yield results or resulted in an error captured earlier.")
                else:
                    # This case means separation was intentionally skipped
                    self.logger.info("Skipping processing of separation results as separation was not run.")

                self.logger.info("=== Parallel Processing Complete ===")

            output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (Title)")
            processed_track["title_image_png"] = f"{output_image_filepath_noext}.png"
            processed_track["title_image_jpg"] = f"{output_image_filepath_noext}.jpg"
            processed_track["title_video"] = os.path.join(track_output_dir, f"{artist_title} (Title).mov")

            # Use FileHandler._file_exists
            if not self.file_handler._file_exists(processed_track["title_video"]) and not os.environ.get("KARAOKE_GEN_SKIP_TITLE_END_SCREENS"):
                self.logger.info(f"Creating title video...")
                # Delegate to VideoGenerator
                self.video_generator.create_title_video(
                    artist=self.artist,
                    title=self.title,
                    format=self.title_format,
                    output_image_filepath_noext=output_image_filepath_noext,
                    output_video_filepath=processed_track["title_video"],
                    existing_title_image=self.existing_title_image,
                    intro_video_duration=self.intro_video_duration,
                )

            output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (End)")
            processed_track["end_image_png"] = f"{output_image_filepath_noext}.png"
            processed_track["end_image_jpg"] = f"{output_image_filepath_noext}.jpg"
            processed_track["end_video"] = os.path.join(track_output_dir, f"{artist_title} (End).mov")

            # Use FileHandler._file_exists
            if not self.file_handler._file_exists(processed_track["end_video"]) and not os.environ.get("KARAOKE_GEN_SKIP_TITLE_END_SCREENS"):
                self.logger.info(f"Creating end screen video...")
                 # Delegate to VideoGenerator
                self.video_generator.create_end_video(
                    artist=self.artist,
                    title=self.title,
                    format=self.end_format,
                    output_image_filepath_noext=output_image_filepath_noext,
                    output_video_filepath=processed_track["end_video"],
                    existing_end_image=self.existing_end_image,
                    end_video_duration=self.end_video_duration,
                )

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

                # Use FileHandler._file_exists
                if not self.file_handler._file_exists(instrumental_path):
                    shutil.copy2(self.existing_instrumental, instrumental_path)

                processed_track["separated_audio"]["Custom"] = {
                    "instrumental": instrumental_path,
                    "vocals": None,
                }
            else:
                # Only run separation if not skipped
                if not self.skip_separation:
                    self.logger.info(f"Separating audio for track: {self.title} by {self.artist}")
                    # Delegate to AudioProcessor (called directly, not in thread here)
                    separation_results = self.audio_processor.process_audio_separation(
                        audio_file=processed_track["input_audio_wav"], artist_title=artist_title, track_output_dir=track_output_dir
                    )
                    processed_track["separated_audio"] = separation_results
                # We don't need an else here, if skip_separation is true, separated_audio remains the default empty dict

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
                input_url=self.url, input_artist=self.artist, input_title=self.title, logger=self.logger, cookies_str=self.cookies_str
            )

            if self.extracted_info and "playlist_count" in self.extracted_info:
                self.persistent_artist = self.artist
                self.logger.info(f"Input URL is a playlist, beginning batch operation with persistent artist: {self.persistent_artist}")
                return await self.process_playlist()
            else:
                self.logger.info(f"Input URL is not a playlist, processing single track")
                # Parse metadata to extract artist and title before processing
                self.parse_single_track_metadata(self.artist, self.title)
                return [await self.prep_single_track()]
