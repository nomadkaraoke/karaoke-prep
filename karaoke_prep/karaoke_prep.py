import os
import sys
import re
import glob
import logging
import tempfile
import shutil
import importlib.resources as pkg_resources
import yt_dlp.YoutubeDL as ydl
from PIL import Image, ImageDraw, ImageFont
from lyrics_transcriber import LyricsTranscriber
from pydub import AudioSegment


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
        denoise_enabled=True,
        normalization_enabled=True,
        # Hardware Acceleration
        use_cuda=False,
        use_coreml=False,
        # Lyrics Configuration
        lyrics_artist=None,
        lyrics_title=None,
        skip_lyrics=False,
        skip_transcription=False,
        # Style Configuration
        style_params=None,
    ):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        self.log_level = log_level
        self.log_formatter = log_formatter

        self.log_handler = logging.StreamHandler()

        if self.log_formatter is None:
            self.log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")

        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)

        self.logger.debug(f"KaraokePrep instantiating with input_media: {input_media} artist: {artist} title: {title}")

        self.dry_run = dry_run
        self.extractor = None
        self.media_id = None
        self.url = None
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
        self.denoise_enabled = denoise_enabled
        self.normalization_enabled = normalization_enabled

        # Input/Output
        self.output_dir = output_dir
        self.lossless_output_format = lossless_output_format.lower()
        self.create_track_subfolders = create_track_subfolders
        self.output_png = output_png
        self.output_jpg = output_jpg

        # Hardware
        self.use_cuda = use_cuda
        self.use_coreml = use_coreml

        # Lyrics
        self.lyrics = None
        self.lyrics_artist = lyrics_artist
        self.lyrics_title = lyrics_title
        self.skip_lyrics = skip_lyrics
        self.skip_transcription = skip_transcription

        # Style
        self.render_bounding_boxes = render_bounding_boxes

        # Set default style parameters if none provided
        if style_params is None:
            style_params = {
                "intro": {
                    "video_duration": 5,
                    "existing_image": None,
                    "background_color": "#000000",
                    "background_image": None,
                    "font": "Montserrat-Bold.ttf",
                    "artist_color": "#ffdf6b",
                    "title_color": "#ffffff",
                    "title_region": "370, 200, 3100, 480",
                    "artist_region": "370, 700, 3100, 480",
                    "extra_text": None,
                    "extra_text_color": "#ffffff",
                    "extra_text_region": "370, 1200, 3100, 480",
                },
                "end": {
                    "video_duration": 5,
                    "existing_image": None,
                    "background_color": "#000000",
                    "background_image": None,
                    "font": "Montserrat-Bold.ttf",
                    "artist_color": "#ffdf6b",
                    "title_color": "#ffffff",
                    "title_region": None,
                    "artist_region": None,
                    "extra_text": "THANK YOU FOR SINGING!",
                    "extra_text_color": "#ff7acc",
                    "extra_text_region": None,
                },
            }

        # Set up title format from style params
        self.title_format = {
            "background_color": style_params["intro"]["background_color"],
            "background_image": style_params["intro"]["background_image"],
            "font": style_params["intro"]["font"],
            "artist_color": style_params["intro"]["artist_color"],
            "title_color": style_params["intro"]["title_color"],
            "extra_text": style_params["intro"]["extra_text"],
            "extra_text_color": style_params["intro"]["extra_text_color"],
            "extra_text_region": style_params["intro"]["extra_text_region"],
            "title_region": style_params["intro"]["title_region"],
            "artist_region": style_params["intro"]["artist_region"],
        }

        # Set up end format from style params
        self.end_format = {
            "background_color": style_params["end"]["background_color"],
            "background_image": style_params["end"]["background_image"],
            "font": style_params["end"]["font"],
            "artist_color": style_params["end"]["artist_color"],
            "title_color": style_params["end"]["title_color"],
            "extra_text": style_params["end"]["extra_text"],
            "extra_text_color": style_params["end"]["extra_text_color"],
            "extra_text_region": style_params["end"]["extra_text_region"],
            "title_region": style_params["end"]["title_region"],
            "artist_region": style_params["end"]["artist_region"],
        }

        # Store video durations and existing images
        self.intro_video_duration = style_params["intro"]["video_duration"]
        self.end_video_duration = style_params["end"]["video_duration"]
        self.existing_title_image = style_params["intro"]["existing_image"]
        self.existing_end_image = style_params["end"]["existing_image"]

        # Path to the Windows PyInstaller frozen bundled ffmpeg.exe, or the system-installed FFmpeg binary on Mac/Linux
        ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg.exe") if getattr(sys, "frozen", False) else "ffmpeg"

        self.ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"

        if self.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"

        self.logger.debug(f"Initialized title_format with extra_text: {self.title_format['extra_text']}")
        self.logger.debug(f"Initialized title_format with extra_text_region: {self.title_format['extra_text_region']}")

        self.logger.debug(f"Initialized end_format with extra_text: {self.end_format['extra_text']}")
        self.logger.debug(f"Initialized end_format with extra_text_region: {self.end_format['extra_text_region']}")

        self.extracted_info = None
        self.persistent_artist = None

        self.logger.debug(f"KaraokePrep lossless_output_format: {self.lossless_output_format}")

        if not os.path.exists(self.output_dir):
            self.logger.debug(f"Overall output dir {self.output_dir} did not exist, creating")
            os.makedirs(self.output_dir)
        else:
            self.logger.debug(f"Overall output dir {self.output_dir} already exists")

    @staticmethod
    def parse_region(region_str):
        if region_str:
            try:
                return tuple(map(int, region_str.split(",")))
            except ValueError:
                raise ValueError(f"Invalid region format: {region_str}. Expected format: 'x,y,width,height'")
        return None

    def extract_info_for_online_media(self, input_url=None, input_artist=None, input_title=None):
        self.logger.info(f"Extracting info for input_url: {input_url} input_artist: {input_artist} input_title: {input_title}")
        if input_url is not None:
            # If a URL is provided, use it to extract the metadata
            with ydl({"quiet": True}) as ydl_instance:
                self.extracted_info = ydl_instance.extract_info(input_url, download=False)
        else:
            # If no URL is provided, use the query to search for the top result
            ydl_opts = {"quiet": "True", "format": "bestaudio", "noplaylist": "True", "extract_flat": True}
            with ydl(ydl_opts) as ydl_instance:
                query = f"{input_artist} {input_title}"
                self.extracted_info = ydl_instance.extract_info(f"ytsearch1:{query}", download=False)["entries"][0]
                if not self.extracted_info:
                    raise Exception(f"No search results found on YouTube for query: {input_artist} {input_title}")

    def parse_single_track_metadata(self, input_artist, input_title):
        """
        Parses self.extracted_info to extract URL, extractor, ID, artist and title.
        """
        # Default values if parsing fails
        self.url = None
        self.extractor = None
        self.media_id = None

        metadata_artist = ""
        metadata_title = ""

        if "url" in self.extracted_info:
            self.url = self.extracted_info["url"]
        elif "webpage_url" in self.extracted_info:
            self.url = self.extracted_info["webpage_url"]
        else:
            raise Exception(f"Failed to extract URL from input media metadata: {self.extracted_info}")

        if "extractor_key" in self.extracted_info:
            self.extractor = self.extracted_info["extractor_key"]
        elif "ie_key" in self.extracted_info:
            self.extractor = self.extracted_info["ie_key"]
        else:
            raise Exception(f"Failed to find extractor name from input media metadata: {self.extracted_info}")

        if "id" in self.extracted_info:
            self.media_id = self.extracted_info["id"]

        # Example: "Artist - Title"
        if "title" in self.extracted_info and "-" in self.extracted_info["title"]:
            metadata_artist, metadata_title = self.extracted_info["title"].split("-", 1)
            metadata_artist = metadata_artist.strip()
            metadata_title = metadata_title.strip()
        elif "uploader" in self.extracted_info:
            # Fallback to uploader as artist if title parsing fails
            metadata_artist = self.extracted_info["uploader"]
            if "title" in self.extracted_info:
                metadata_title = self.extracted_info["title"].strip()

        # If unable to parse, log an appropriate message
        if not metadata_artist or not metadata_title:
            self.logger.warning("Could not parse artist and title from the input media metadata.")

        if input_artist is None:
            self.logger.warn(f"Artist not provided as input, setting to {metadata_artist} from input media metadata...")
            self.artist = metadata_artist

        if input_title is None:
            self.logger.warn(f"Title not provided as input, setting to {metadata_title} from input media metadata...")
            self.title = metadata_title

        if self.persistent_artist:
            self.logger.debug(
                f"Resetting self.artist from {self.artist} to persistent artist: {self.persistent_artist} for consistency while processing playlist..."
            )
            self.artist = self.persistent_artist

        if self.artist and self.title:
            self.logger.info(f"Extracted url: {self.url}, artist: {self.artist}, title: {self.title}")
        else:
            self.logger.debug(self.extracted_info)
            raise Exception("Failed to extract artist and title from the input media metadata.")

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

    def download_video(self, url, output_filename_no_extension):
        self.logger.debug(f"Downloading media from URL {url} to filename {output_filename_no_extension} + (as yet) unknown extension")

        ydl_opts = {
            "quiet": True,
            "format": "bv*+ba/b",  # if a combined video + audio format is better than the best video-only format use the combined format
            "outtmpl": f"{output_filename_no_extension}.%(ext)s",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
        }

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

    def extract_still_image_from_video(self, input_filename, output_filename_no_extension):
        output_filename = output_filename_no_extension + ".png"
        self.logger.info(f"Extracting still image from position 30s input media")
        ffmpeg_command = f'{self.ffmpeg_base_command} -i "{input_filename}" -ss 00:00:30 -vframes 1 "{output_filename}"'
        self.logger.debug(f"Running command: {ffmpeg_command}")
        os.system(ffmpeg_command)
        return output_filename

    def convert_to_wav(self, input_filename, output_filename_no_extension):
        output_filename = output_filename_no_extension + ".wav"
        self.logger.info(f"Converting input media to audio WAV file")
        ffmpeg_command = f'{self.ffmpeg_base_command} -n -i "{input_filename}" "{output_filename}"'
        self.logger.debug(f"Running command: {ffmpeg_command}")
        if not self.dry_run:
            os.system(ffmpeg_command)
        return output_filename

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

        # Create lyrics subdirectory
        lyrics_dir = os.path.join(track_output_dir, "lyrics")
        os.makedirs(lyrics_dir, exist_ok=True)
        self.logger.info(f"Created lyrics directory: {lyrics_dir}")

        transcriber = LyricsTranscriber(
            input_audio_wav,
            log_level=self.log_level,
            log_formatter=self.log_formatter,
            artist=artist,
            title=title,
            output_dir=lyrics_dir,
            skip_transcription=self.skip_transcription,
        )

        transcriber_outputs = transcriber.generate()

        if transcriber_outputs:
            self.logger.info(f"*** Transcriber Filepath Outputs: ***")
            for key, value in transcriber_outputs.items():
                if key.endswith("_filepath"):
                    self.logger.info(f"  {key}: {value}")

        return transcriber_outputs

    def sanitize_filename(self, filename):
        """Replace or remove characters that are unsafe for filenames."""
        # Replace problematic characters with underscores
        for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
            filename = filename.replace(char, "_")
        # Remove any trailing periods or spaces
        filename = filename.rstrip(" ")
        return filename

    def separate_audio(self, audio_file, model_name, artist_title, track_output_dir, instrumental_path, vocals_path):
        if audio_file is None or not os.path.isfile(audio_file):
            raise Exception("Error: Invalid audio source provided.")

        self.logger.debug(f"audio_file is valid file: {audio_file}")

        self.logger.info(
            f"instantiating Separator with model_file_dir: {self.model_file_dir}, model_filename: {model_name} output_format: {self.lossless_output_format}"
        )

        from audio_separator.separator import Separator

        separator = Separator(
            log_level=self.log_level,
            log_formatter=self.log_formatter,
            model_file_dir=self.model_file_dir,
            output_format=self.lossless_output_format,
        )

        separator.load_model(model_filename=model_name)
        output_files = separator.separate(audio_file)

        self.logger.debug(f"Separator output files: {output_files}")

        model_name_no_extension = os.path.splitext(model_name)[0]

        for file in output_files:
            if "(Vocals)" in file:
                self.logger.info(f"Renaming Vocals file {file} to {vocals_path}")
                os.rename(file, vocals_path)
            elif "(Instrumental)" in file:
                self.logger.info(f"Renaming Instrumental file {file} to {instrumental_path}")
                os.rename(file, instrumental_path)
            elif model_name in file:
                # Example filename 1: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Piano)_htdemucs_6s.flac"
                # Example filename 2: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Guitar)_htdemucs_6s.flac"
                # The stem name in these examples would be "Piano" or "Guitar"
                # Extract stem_name from the filename
                stem_name = file.split(f"_{model_name}")[0].split("_")[-1]
                stem_name = stem_name.strip("()")  # Remove parentheses if present

                other_stem_path = os.path.join(track_output_dir, f"{artist_title} ({stem_name} {model_name}).{self.lossless_output_format}")
                self.logger.info(f"Renaming other stem file {file} to {other_stem_path}")
                os.rename(file, other_stem_path)

            elif model_name_no_extension in file:
                # Example filename 1: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Piano)_htdemucs_6s.flac"
                # Example filename 2: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Guitar)_htdemucs_6s.flac"
                # The stem name in these examples would be "Piano" or "Guitar"
                # Extract stem_name from the filename
                stem_name = file.split(f"_{model_name_no_extension}")[0].split("_")[-1]
                stem_name = stem_name.strip("()")  # Remove parentheses if present

                other_stem_path = os.path.join(track_output_dir, f"{artist_title} ({stem_name} {model_name}).{self.lossless_output_format}")
                self.logger.info(f"Renaming other stem file {file} to {other_stem_path}")
                os.rename(file, other_stem_path)

        self.logger.info(f"Separation complete! Output file(s): {vocals_path} {instrumental_path}")

    def setup_output_paths(self, artist, title):
        sanitized_artist = self.sanitize_filename(artist)
        sanitized_title = self.sanitize_filename(title)
        artist_title = f"{sanitized_artist} - {sanitized_title}"

        track_output_dir = self.output_dir
        if self.create_track_subfolders:
            track_output_dir = os.path.join(self.output_dir, f"{artist_title}")

        if not os.path.exists(track_output_dir):
            self.logger.debug(f"Output dir {track_output_dir} did not exist, creating")
            os.makedirs(track_output_dir)

        return track_output_dir, artist_title

    def calculate_text_size_to_fit(self, draw, text, font_path, region):
        font_size = 500  # Start with a large font size
        font = ImageFont.truetype(font_path, size=font_size) if os.path.exists(font_path) else ImageFont.load_default()

        def get_text_size(text, font):
            return draw.textbbox((0, 0), text, font=font)[2:]

        text_width, text_height = get_text_size(text, font)

        while text_width > region[2] or text_height > region[3]:
            font_size -= 10
            if font_size <= 150:
                # Split the text into two lines
                words = text.split()
                mid = len(words) // 2
                line1 = " ".join(words[:mid])
                line2 = " ".join(words[mid:])

                # Reset font size for two-line layout
                font_size = 500
                font = ImageFont.truetype(font_path, size=font_size) if os.path.exists(font_path) else ImageFont.load_default()

                while True:
                    text_width1, text_height1 = get_text_size(line1, font)
                    text_width2, text_height2 = get_text_size(line2, font)
                    total_height = text_height1 + text_height2

                    if max(text_width1, text_width2) <= region[2] and total_height <= region[3]:
                        return font, (line1, line2)

                    font_size -= 10
                    if font_size <= 0:
                        raise ValueError("Cannot fit text within the defined region.")
                    font = ImageFont.truetype(font_path, size=font_size) if os.path.exists(font_path) else ImageFont.load_default()

            font = ImageFont.truetype(font_path, size=font_size) if os.path.exists(font_path) else ImageFont.load_default()
            text_width, text_height = get_text_size(text, font)

        return font, text

    def _render_text_in_region(self, draw, text, font_path, region, color, font=None):
        """Helper method to render text within a specified region."""
        self.logger.debug(f"Rendering text: '{text}' in region: {region} with color: {color}")

        if text is None:
            self.logger.debug("Text is None, skipping rendering")
            return region

        if font is None:
            font, text_lines = self.calculate_text_size_to_fit(draw, text, font_path, region)
        else:
            text_lines = text

        self.logger.debug(f"Using text_lines: {text_lines}")

        x, y, width, height = region

        if isinstance(text_lines, tuple):  # Two lines
            line1, line2 = text_lines
            bbox1 = draw.textbbox((0, 0), line1, font=font)
            bbox2 = draw.textbbox((0, 0), line2, font=font)

            total_height = bbox1[3] + bbox2[3]
            y_offset = (height - total_height) // 2

            # Draw first line
            draw.text((x + (width - bbox1[2]) // 2, y + y_offset), line1, fill=color, font=font)

            # Draw second line
            draw.text((x + (width - bbox2[2]) // 2, y + y_offset + bbox1[3]), line2, fill=color, font=font)
        else:
            # Single line
            bbox = draw.textbbox((0, 0), text_lines, font=font)
            position = (
                x + (width - bbox[2]) // 2,
                y + (height - bbox[3]) // 2,
            )
            draw.text(position, text_lines, fill=color, font=font)

        return region

    def _draw_bounding_box(self, draw, region, color):
        """Helper method to draw a bounding box around a region."""
        x, y, width, height = region
        draw.rectangle([x, y, x + width, y + height], outline=color, width=2)

    def create_video(
        self,
        extra_text,
        title_text,
        artist_text,
        format,
        output_image_filepath_noext,
        output_video_filepath,
        existing_image=None,
        duration=5,
        render_bounding_boxes=False,
        output_png=True,
        output_jpg=True,
    ):
        """Create a video with title, artist, and optional extra text."""
        self.logger.debug(f"Creating video with extra_text: '{extra_text}'")
        self.logger.debug(f"Format settings: {format}")

        resolution = (3840, 2160)  # 4K resolution
        self.logger.info(f"Creating video with format: {format}")
        self.logger.info(f"extra_text: {extra_text}, artist_text: {artist_text}, title_text: {title_text}")

        if existing_image:
            return self._handle_existing_image(existing_image, output_image_filepath_noext, output_video_filepath, duration)

        # Create or load background
        background = self._create_background(format, resolution)
        draw = ImageDraw.Draw(background)

        if format["font"] is not None:
            self.logger.info(f"Using font: {format['font']}")
            with pkg_resources.path("karaoke_prep.resources", format["font"]) as font_path:
                # Render all text elements
                self._render_all_text(
                    draw,
                    str(font_path),
                    title_text,
                    artist_text,
                    format,
                    render_bounding_boxes,
                )
        else:
            self.logger.info("No font specified, skipping text rendering")

        # Save images and create video
        self._save_output_files(
            background, output_image_filepath_noext, output_video_filepath, output_png, output_jpg, duration, resolution
        )

    def _handle_existing_image(self, existing_image, output_image_filepath_noext, output_video_filepath, duration):
        """Handle case where an existing image is provided."""
        self.logger.info(f"Using existing image file: {existing_image}")
        existing_extension = os.path.splitext(existing_image)[1]

        if existing_extension == ".png":
            self.logger.info(f"Copying existing PNG image file: {existing_image}")
            shutil.copy2(existing_image, output_image_filepath_noext + existing_extension)
        else:
            self.logger.info(f"Converting existing image to PNG")
            existing_image_obj = Image.open(existing_image)
            existing_image_obj.save(output_image_filepath_noext + ".png")

        if existing_extension != ".jpg":
            self.logger.info(f"Converting existing image to JPG")
            existing_image_obj = Image.open(existing_image)
            if existing_image_obj.mode == "RGBA":
                existing_image_obj = existing_image_obj.convert("RGB")
            existing_image_obj.save(output_image_filepath_noext + ".jpg", quality=95)

        if duration > 0:
            self._create_video_from_image(output_image_filepath_noext + ".png", output_video_filepath, duration)

    def _create_background(self, format, resolution):
        """Create or load the background image."""
        if format["background_image"] and os.path.exists(format["background_image"]):
            self.logger.info(f"Using background image file: {format['background_image']}")
            background = Image.open(format["background_image"])
        else:
            self.logger.info(f"Using background color: {format['background_color']}")
            background = Image.new("RGB", resolution, color=self.hex_to_rgb(format["background_color"]))

        return background.resize(resolution)

    def _render_all_text(self, draw, font_path, title_text, artist_text, format, render_bounding_boxes):
        """Render all text elements on the image."""
        # Render title
        if format["title_region"]:
            region_parsed = self.parse_region(format["title_region"])
            region = self._render_text_in_region(draw, title_text.upper(), font_path, region_parsed, format["title_color"])
            if render_bounding_boxes:
                self._draw_bounding_box(draw, region, format["title_color"])

        # Render artist
        if format["artist_region"]:
            region_parsed = self.parse_region(format["artist_region"])
            region = self._render_text_in_region(draw, artist_text.upper(), font_path, region_parsed, format["artist_color"])
            if render_bounding_boxes:
                self._draw_bounding_box(draw, region, format["artist_color"])

        # Render extra text if provided
        if format["extra_text"]:
            region_parsed = self.parse_region(format["extra_text_region"])
            region = self._render_text_in_region(draw, format["extra_text"], font_path, region_parsed, format["extra_text_color"])
            if render_bounding_boxes:
                self._draw_bounding_box(draw, region, format["extra_text_color"])

    def _save_output_files(
        self, background, output_image_filepath_noext, output_video_filepath, output_png, output_jpg, duration, resolution
    ):
        """Save the output image files and create video if needed."""
        # Save static background image
        if output_png:
            background.save(f"{output_image_filepath_noext}.png")

        if output_jpg:
            # Save static background image as JPG for smaller filesize
            background_rgb = background.convert("RGB")
            background_rgb.save(f"{output_image_filepath_noext}.jpg", quality=95)

        if duration > 0:
            self._create_video_from_image(f"{output_image_filepath_noext}.png", output_video_filepath, duration, resolution)

    def _create_video_from_image(self, image_path, video_path, duration, resolution=(3840, 2160)):
        """Create a video from a static image."""
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -y -loop 1 -framerate 30 -i "{image_path}" '
            f"-f lavfi -i anullsrc -c:v libx264 -r 30 -t {duration} -pix_fmt yuv420p "
            f'-vf scale={resolution[0]}:{resolution[1]} -c:a aac -shortest "{video_path}"'
        )

        self.logger.info("Generating video...")
        self.logger.debug(f"Running command: {ffmpeg_command}")
        os.system(ffmpeg_command)

    def create_title_video(self, artist, title, format, output_image_filepath_noext, output_video_filepath):
        title_text = title.upper()
        artist_text = artist.upper()
        self.create_video(
            title_text=title_text,
            artist_text=artist_text,
            extra_text=format["extra_text"],
            format=format,
            output_image_filepath_noext=output_image_filepath_noext,
            output_video_filepath=output_video_filepath,
            existing_image=self.existing_title_image,
            duration=self.intro_video_duration,
            render_bounding_boxes=self.render_bounding_boxes,
            output_png=self.output_png,
            output_jpg=self.output_jpg,
        )

    def create_end_video(self, artist, title, format, output_image_filepath_noext, output_video_filepath):
        title_text = title.upper()
        artist_text = artist.upper()
        self.create_video(
            title_text=title_text,
            artist_text=artist_text,
            extra_text=format["extra_text"],
            format=format,
            output_image_filepath_noext=output_image_filepath_noext,
            output_video_filepath=output_video_filepath,
            existing_image=self.existing_end_image,
            duration=self.end_video_duration,
            render_bounding_boxes=self.render_bounding_boxes,
            output_png=self.output_png,
            output_jpg=self.output_jpg,
        )

    def hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def process_audio_separation(self, audio_file, artist_title, track_output_dir):
        from audio_separator.separator import Separator

        self.logger.info(f"Starting audio separation process for {artist_title}")

        separator = Separator(
            log_level=self.log_level,
            log_formatter=self.log_formatter,
            model_file_dir=self.model_file_dir,
            output_format=self.lossless_output_format,
        )

        stems_dir = self._create_stems_directory(track_output_dir)
        result = {"clean_instrumental": {}, "other_stems": {}, "backing_vocals": {}, "combined_instrumentals": {}}

        if os.environ.get("KARAOKE_PREP_SKIP_AUDIO_SEPARATION"):
            return result

        result["clean_instrumental"] = self._separate_clean_instrumental(separator, audio_file, artist_title, track_output_dir, stems_dir)
        result["other_stems"] = self._separate_other_stems(separator, audio_file, artist_title, stems_dir)
        result["backing_vocals"] = self._separate_backing_vocals(separator, result["clean_instrumental"]["vocals"], artist_title, stems_dir)
        result["combined_instrumentals"] = self._generate_combined_instrumentals(
            result["clean_instrumental"]["instrumental"], result["backing_vocals"], artist_title, track_output_dir
        )
        self._normalize_audio_files(result, artist_title, track_output_dir)

        self.logger.info("Audio separation, combination, and normalization process completed")
        return result

    def _create_stems_directory(self, track_output_dir):
        stems_dir = os.path.join(track_output_dir, "stems")
        os.makedirs(stems_dir, exist_ok=True)
        self.logger.info(f"Created stems directory: {stems_dir}")
        return stems_dir

    def _separate_clean_instrumental(self, separator, audio_file, artist_title, track_output_dir, stems_dir):
        self.logger.info(f"Separating using clean instrumental model: {self.clean_instrumental_model}")
        instrumental_path = os.path.join(
            track_output_dir, f"{artist_title} (Instrumental {self.clean_instrumental_model}).{self.lossless_output_format}"
        )
        vocals_path = os.path.join(stems_dir, f"{artist_title} (Vocals {self.clean_instrumental_model}).{self.lossless_output_format}")

        result = {}
        if not self._file_exists(instrumental_path) or not self._file_exists(vocals_path):
            separator.load_model(model_filename=self.clean_instrumental_model)
            clean_output_files = separator.separate(audio_file)

            for file in clean_output_files:
                if "(Vocals)" in file and not self._file_exists(vocals_path):
                    os.rename(file, vocals_path)
                    result["vocals"] = vocals_path
                elif "(Instrumental)" in file and not self._file_exists(instrumental_path):
                    os.rename(file, instrumental_path)
                    result["instrumental"] = instrumental_path
        else:
            result["vocals"] = vocals_path
            result["instrumental"] = instrumental_path

        return result

    def _separate_other_stems(self, separator, audio_file, artist_title, stems_dir):
        self.logger.info(f"Separating using other stems models: {self.other_stems_models}")
        result = {}
        for model in self.other_stems_models:
            self.logger.info(f"Processing with model: {model}")
            result[model] = {}

            # Check if any stem files for this model already exist
            existing_stems = glob.glob(os.path.join(stems_dir, f"{artist_title} (*{model}).{self.lossless_output_format}"))

            if existing_stems:
                self.logger.info(f"Found existing stem files for model {model}, skipping separation")
                for stem_file in existing_stems:
                    stem_name = os.path.basename(stem_file).split("(")[1].split(")")[0].strip()
                    result[model][stem_name] = stem_file
            else:
                separator.load_model(model_filename=model)
                other_stems_output = separator.separate(audio_file)

                for file in other_stems_output:
                    file_name = os.path.basename(file)
                    stem_name = file_name[file_name.rfind("_(") + 2 : file_name.rfind(")_")]
                    new_filename = f"{artist_title} ({stem_name} {model}).{self.lossless_output_format}"
                    other_stem_path = os.path.join(stems_dir, new_filename)
                    if not self._file_exists(other_stem_path):
                        os.rename(file, other_stem_path)
                    result[model][stem_name] = other_stem_path

        return result

    def _separate_backing_vocals(self, separator, vocals_path, artist_title, stems_dir):
        self.logger.info(f"Separating clean vocals using backing vocals models: {self.backing_vocals_models}")
        result = {}
        for model in self.backing_vocals_models:
            self.logger.info(f"Processing with model: {model}")
            result[model] = {}
            lead_vocals_path = os.path.join(stems_dir, f"{artist_title} (Lead Vocals {model}).{self.lossless_output_format}")
            backing_vocals_path = os.path.join(stems_dir, f"{artist_title} (Backing Vocals {model}).{self.lossless_output_format}")

            if not self._file_exists(lead_vocals_path) or not self._file_exists(backing_vocals_path):
                separator.load_model(model_filename=model)
                backing_vocals_output = separator.separate(vocals_path)

                for file in backing_vocals_output:
                    if "(Vocals)" in file and not self._file_exists(lead_vocals_path):
                        os.rename(file, lead_vocals_path)
                        result[model]["lead_vocals"] = lead_vocals_path
                    elif "(Instrumental)" in file and not self._file_exists(backing_vocals_path):
                        os.rename(file, backing_vocals_path)
                        result[model]["backing_vocals"] = backing_vocals_path
            else:
                result[model]["lead_vocals"] = lead_vocals_path
                result[model]["backing_vocals"] = backing_vocals_path
        return result

    def _generate_combined_instrumentals(self, instrumental_path, backing_vocals_result, artist_title, track_output_dir):
        self.logger.info("Generating combined instrumental tracks with backing vocals")
        result = {}
        for model, paths in backing_vocals_result.items():
            backing_vocals_path = paths["backing_vocals"]
            combined_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental +BV {model}).{self.lossless_output_format}")

            if not self._file_exists(combined_path):
                ffmpeg_command = (
                    f'{self.ffmpeg_base_command} -i "{instrumental_path}" -i "{backing_vocals_path}" '
                    f'-filter_complex "[0:a][1:a]amix=inputs=2:duration=longest:weights=1 1" '
                    f'-c:a {self.lossless_output_format.lower()} "{combined_path}"'
                )

                self.logger.debug(f"Running command: {ffmpeg_command}")
                os.system(ffmpeg_command)

            result[model] = combined_path
        return result

    def _normalize_audio_files(self, separation_result, artist_title, track_output_dir):
        self.logger.info("Normalizing clean instrumental and combined instrumentals")

        files_to_normalize = [
            ("clean_instrumental", separation_result["clean_instrumental"]["instrumental"]),
        ] + [("combined_instrumentals", path) for path in separation_result["combined_instrumentals"].values()]

        for key, file_path in files_to_normalize:
            if self._file_exists(file_path):
                try:
                    self._normalize_audio(file_path, file_path)  # Normalize in-place

                    # Verify the normalized file
                    if os.path.getsize(file_path) > 0:
                        self.logger.info(f"Successfully normalized: {file_path}")
                    else:
                        raise Exception("Normalized file is empty")

                except Exception as e:
                    self.logger.error(f"Error during normalization of {file_path}: {e}")
                    self.logger.warning(f"Normalization failed for {file_path}. Original file remains unchanged.")
            else:
                self.logger.warning(f"File not found for normalization: {file_path}")

        self.logger.info("Audio normalization process completed")

    def _normalize_audio(self, input_path, output_path, target_level=0.0):
        self.logger.info(f"Normalizing audio file: {input_path}")

        # Load audio file
        audio = AudioSegment.from_file(input_path, format=self.lossless_output_format.lower())

        # Calculate the peak amplitude
        peak_amplitude = float(audio.max_dBFS)

        # Calculate the necessary gain
        gain_db = target_level - peak_amplitude

        # Apply gain
        normalized_audio = audio.apply_gain(gain_db)

        # Ensure the audio is not completely silent
        if normalized_audio.rms == 0:
            self.logger.warning(f"Normalized audio is silent for {input_path}. Using original audio.")
            normalized_audio = audio

        # Export normalized audio, overwriting the original file
        normalized_audio.export(output_path, format=self.lossless_output_format.lower())

        self.logger.info(f"Normalized audio saved, replacing: {output_path}")
        self.logger.debug(f"Original peak: {peak_amplitude} dB, Applied gain: {gain_db} dB")

    def _file_exists(self, file_path):
        """Check if a file exists and log the result."""
        exists = os.path.isfile(file_path)
        if exists:
            self.logger.info(f"File already exists, skipping creation: {file_path}")
        return exists

    def prep_single_track(self):
        self.logger.info(f"Preparing single track: {self.artist} - {self.title}")

        if self.input_media is not None and os.path.isfile(self.input_media):
            self.extractor = "Original"
        else:
            # Parses metadata in self.extracted_info to set vars: self.url, self.extractor, self.media_id, self.artist, self.title
            self.parse_single_track_metadata(input_artist=self.artist, input_title=self.title)

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
                    processed_track["input_audio_wav"] = self.convert_to_wav(processed_track["input_media"], output_filename_no_extension)
                else:
                    self.logger.warning(f"Skipping download due to missing URL.")

        if self.skip_lyrics:
            self.logger.info("Skipping lyrics fetch as requested.")
            processed_track["lyrics"] = None
            processed_track["processed_lyrics"] = None
        else:
            lyrics_artist = self.lyrics_artist or self.artist
            lyrics_title = self.lyrics_title or self.title

            transcriber_outputs = self.transcribe_lyrics(processed_track["input_audio_wav"], lyrics_artist, lyrics_title, track_output_dir)

            if transcriber_outputs:
                self.lyrics = transcriber_outputs.get("corrected_lyrics_text")
                processed_track["lyrics"] = transcriber_outputs.get("corrected_lyrics_text_filepath")

        output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (Title)")
        processed_track["title_image_png"] = f"{output_image_filepath_noext}.png"
        processed_track["title_image_jpg"] = f"{output_image_filepath_noext}.jpg"
        processed_track["title_video"] = os.path.join(track_output_dir, f"{artist_title} (Title).mov")

        if not self._file_exists(processed_track["title_video"]) and not os.environ.get("KARAOKE_PREP_SKIP_TITLE_END_SCREENS"):
            self.logger.info(f"Creating title video...")
            self.create_title_video(self.artist, self.title, self.title_format, output_image_filepath_noext, processed_track["title_video"])

        output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (End)")
        processed_track["end_image_png"] = f"{output_image_filepath_noext}.png"
        processed_track["end_image_jpg"] = f"{output_image_filepath_noext}.jpg"
        processed_track["end_video"] = os.path.join(track_output_dir, f"{artist_title} (End).mov")

        if not self._file_exists(processed_track["end_video"]) and not os.environ.get("KARAOKE_PREP_SKIP_TITLE_END_SCREENS"):
            self.logger.info(f"Creating end screen video...")
            self.create_end_video(self.artist, self.title, self.end_format, output_image_filepath_noext, processed_track["end_video"])

        if self.existing_instrumental:
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

    def process_playlist(self):
        if self.artist is None or self.title is None:
            raise Exception("Error: Artist and Title are required for processing a local file.")

        if "entries" in self.extracted_info:
            track_results = []
            self.logger.info(f"Found {len(self.extracted_info['entries'])} entries in playlist, processing each invididually...")
            for entry in self.extracted_info["entries"]:
                self.extracted_info = entry
                self.logger.info(f"Processing playlist entry with title: {self.extracted_info['title']}")
                if not self.dry_run:
                    track_results.append(self.prep_single_track())
                self.artist = self.persistent_artist
                self.title = None
            return track_results
        else:
            raise Exception(f"Failed to find 'entries' in playlist, cannot process")

    def process_folder(self):
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
                    track = self.prep_single_track()
                    tracks.append(track)

                    # Move the track folder to the output folder
                    track_folder = track["track_output_dir"]
                    shutil.move(track_folder, track_output_dir)
                else:
                    self.logger.info(f"DRY RUN: Would move track folder to: {os.path.basename(track_output_dir)}")

        return tracks

    def process(self):
        if self.input_media is not None and os.path.isdir(self.input_media):
            self.logger.info(f"Input media {self.input_media} is a local folder, processing each file individually...")

            return self.process_folder()
        elif self.input_media is not None and os.path.isfile(self.input_media):
            self.logger.info(f"Input media {self.input_media} is a local file, youtube logic will be skipped")

            return [self.prep_single_track()]
        else:
            self.url = self.input_media
            # Runs yt-dlp extract_info for input URL or artist/title search query to set var: self.extracted_info
            # We do this first as the input URL may be a playlist
            self.extract_info_for_online_media(input_url=self.url, input_artist=self.artist, input_title=self.title)

            if self.extracted_info and "playlist_count" in self.extracted_info:
                self.persistent_artist = self.artist
                self.logger.info(f"Input URL is a playlist, beginning batch operation with persistent artist: {self.persistent_artist}")
                return self.process_playlist()
            else:
                self.logger.info(f"Input URL is not a playlist, processing single track")
                return [self.prep_single_track()]
