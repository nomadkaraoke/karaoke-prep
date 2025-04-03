import os
import re
import logging
import shutil
from lyrics_transcriber import LyricsTranscriber, OutputConfig, TranscriberConfig, LyricsConfig
from lyrics_transcriber.core.controller import LyricsControllerResult
from dotenv import load_dotenv


# Placeholder class or functions for lyrics processing
class LyricsProcessor:
    def __init__(
        self, logger, style_params_json, lyrics_file, skip_transcription, skip_transcription_review, render_video, subtitle_offset_ms
    ):
        self.logger = logger
        self.style_params_json = style_params_json
        self.lyrics_file = lyrics_file
        self.skip_transcription = skip_transcription
        self.skip_transcription_review = skip_transcription_review
        self.render_video = render_video
        self.subtitle_offset_ms = subtitle_offset_ms

    def sanitize_filename(self, filename):
        """Replace or remove characters that are unsafe for filenames."""
        # Replace problematic characters with underscores
        for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
            filename = filename.replace(char, "_")
        # Remove any trailing periods or spaces
        filename = filename.rstrip(" ")
        return filename

    def find_best_split_point(self, line):
        """
        Find the best split point in a line based on the specified criteria.
        """

        self.logger.debug(f"Finding best_split_point for line: {line}")
        words = line.split()
        mid_word_index = len(words) // 2
        self.logger.debug(f"words: {words} mid_word_index: {mid_word_index}")

        # Check for a comma within one or two words of the middle word
        if "," in line:
            mid_point = len(" ".join(words[:mid_word_index]))
            comma_indices = [i for i, char in enumerate(line) if char == ","]

            for index in comma_indices:
                if abs(mid_point - index) < 20 and len(line[: index + 1].strip()) <= 36:
                    self.logger.debug(
                        f"Found comma at index {index} which is within 20 characters of mid_point {mid_point} and results in a suitable line length, accepting as split point"
                    )
                    return index + 1  # Include the comma in the first line

        # Check for 'and'
        if " and " in line:
            mid_point = len(line) // 2
            and_indices = [m.start() for m in re.finditer(" and ", line)]
            for index in sorted(and_indices, key=lambda x: abs(x - mid_point)):
                if len(line[: index + len(" and ")].strip()) <= 36:
                    self.logger.debug(f"Found 'and' at index {index} which results in a suitable line length, accepting as split point")
                    return index + len(" and ")

        # If no better split point is found, try splitting at the middle word
        if len(words) > 2 and mid_word_index > 0:
            split_at_middle = len(" ".join(words[:mid_word_index]))
            if split_at_middle <= 36:
                self.logger.debug(f"Splitting at middle word index: {mid_word_index}")
                return split_at_middle

        # If the line is still too long, forcibly split at the maximum length
        forced_split_point = 36
        if len(line) > forced_split_point:
            self.logger.debug(f"Line is still too long, forcibly splitting at position {forced_split_point}")
            return forced_split_point

    def process_line(self, line):
        """
        Process a single line to ensure it's within the maximum length,
        and handle parentheses.
        """
        processed_lines = []
        iteration_count = 0
        max_iterations = 100  # Failsafe limit

        while len(line) > 36:
            if iteration_count > max_iterations:
                self.logger.error(f"Maximum iterations exceeded in process_line for line: {line}")
                break

            # Check if the line contains parentheses
            if "(" in line and ")" in line:
                start_paren = line.find("(")
                end_paren = line.find(")") + 1
                if end_paren < len(line) and line[end_paren] == ",":
                    end_paren += 1

                if start_paren > 0:
                    processed_lines.append(line[:start_paren].strip())
                processed_lines.append(line[start_paren:end_paren].strip())
                line = line[end_paren:].strip()
            else:
                split_point = self.find_best_split_point(line)
                processed_lines.append(line[:split_point].strip())
                line = line[split_point:].strip()

            iteration_count += 1

        if line:  # Add the remaining part if not empty
            processed_lines.append(line)

        return processed_lines

    def transcribe_lyrics(self, input_audio_wav, artist, title, track_output_dir):
        self.logger.info(
            f"Transcribing lyrics for track {artist} - {title} from audio file: {input_audio_wav} with output directory: {track_output_dir}"
        )

        # Check for existing files first using sanitized names
        sanitized_artist = self.sanitize_filename(artist)
        sanitized_title = self.sanitize_filename(title)
        parent_video_path = os.path.join(track_output_dir, f"{sanitized_artist} - {sanitized_title} (With Vocals).mkv")
        parent_lrc_path = os.path.join(track_output_dir, f"{sanitized_artist} - {sanitized_title} (Karaoke).lrc")

        # Check lyrics directory for existing files
        lyrics_dir = os.path.join(track_output_dir, "lyrics")
        lyrics_video_path = os.path.join(lyrics_dir, f"{sanitized_artist} - {sanitized_title} (With Vocals).mkv")
        lyrics_lrc_path = os.path.join(lyrics_dir, f"{sanitized_artist} - {sanitized_title} (Karaoke).lrc")

        # If files exist in parent directory, return early
        if os.path.exists(parent_video_path) and os.path.exists(parent_lrc_path):
            self.logger.info(f"Found existing video and LRC files in parent directory, skipping transcription")
            return {
                "lrc_filepath": parent_lrc_path,
                "ass_filepath": parent_video_path,
            }

        # If files exist in lyrics directory, copy to parent and return
        if os.path.exists(lyrics_video_path) and os.path.exists(lyrics_lrc_path):
            self.logger.info(f"Found existing video and LRC files in lyrics directory, copying to parent")
            os.makedirs(track_output_dir, exist_ok=True)
            shutil.copy2(lyrics_video_path, parent_video_path)
            shutil.copy2(lyrics_lrc_path, parent_lrc_path)
            return {
                "lrc_filepath": parent_lrc_path,
                "ass_filepath": parent_video_path,
            }

        # Create lyrics subdirectory for new transcription
        os.makedirs(lyrics_dir, exist_ok=True)
        self.logger.info(f"Created lyrics directory: {lyrics_dir}")

        # Load environment variables
        load_dotenv()
        env_config = {
            "audioshake_api_token": os.getenv("AUDIOSHAKE_API_TOKEN"),
            "genius_api_token": os.getenv("GENIUS_API_TOKEN"),
            "spotify_cookie": os.getenv("SPOTIFY_COOKIE_SP_DC"),
            "runpod_api_key": os.getenv("RUNPOD_API_KEY"),
            "whisper_runpod_id": os.getenv("WHISPER_RUNPOD_ID"),
        }

        # Create config objects for LyricsTranscriber
        transcriber_config = TranscriberConfig(
            audioshake_api_token=env_config.get("audioshake_api_token"),
        )

        lyrics_config = LyricsConfig(
            genius_api_token=env_config.get("genius_api_token"),
            spotify_cookie=env_config.get("spotify_cookie"),
            lyrics_file=self.lyrics_file,
        )

        output_config = OutputConfig(
            output_styles_json=self.style_params_json,
            output_dir=lyrics_dir,
            render_video=self.render_video,
            fetch_lyrics=True,
            run_transcription=not self.skip_transcription,
            run_correction=True,
            generate_plain_text=True,
            generate_lrc=True,
            generate_cdg=True,
            video_resolution="4k",
            enable_review=not self.skip_transcription_review,
            subtitle_offset_ms=self.subtitle_offset_ms,
        )

        # Add this log entry to debug the OutputConfig
        self.logger.info(f"Instantiating LyricsTranscriber with OutputConfig: {output_config}")

        # Initialize transcriber with new config objects
        transcriber = LyricsTranscriber(
            audio_filepath=input_audio_wav,
            artist=artist,
            title=title,
            transcriber_config=transcriber_config,
            lyrics_config=lyrics_config,
            output_config=output_config,
            logger=self.logger,
        )

        # Process and get results
        results: LyricsControllerResult = transcriber.process()
        self.logger.info(f"Transcriber Results Filepaths:")
        for key, value in results.__dict__.items():
            if key.endswith("_filepath"):
                self.logger.info(f"  {key}: {value}")

        # Build output dictionary
        transcriber_outputs = {}
        if results.lrc_filepath:
            transcriber_outputs["lrc_filepath"] = results.lrc_filepath
            self.logger.info(f"Moving LRC file from {results.lrc_filepath} to {parent_lrc_path}")
            shutil.copy2(results.lrc_filepath, parent_lrc_path)

        if results.ass_filepath:
            transcriber_outputs["ass_filepath"] = results.ass_filepath
            self.logger.info(f"Moving video file from {results.video_filepath} to {parent_video_path}")
            shutil.copy2(results.video_filepath, parent_video_path)

        if results.transcription_corrected:
            transcriber_outputs["corrected_lyrics_text"] = "\n".join(
                segment.text for segment in results.transcription_corrected.corrected_segments
            )
            transcriber_outputs["corrected_lyrics_text_filepath"] = results.corrected_txt

        if transcriber_outputs:
            self.logger.info(f"*** Transcriber Filepath Outputs: ***")
            for key, value in transcriber_outputs.items():
                if key.endswith("_filepath"):
                    self.logger.info(f"  {key}: {value}")

        return transcriber_outputs
