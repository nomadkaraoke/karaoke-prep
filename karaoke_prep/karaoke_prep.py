import os
import sys
import re
import glob
import logging
import unicodedata
import lyricsgenius
import tempfile
import shutil
import pyperclip
from pyperclip import PyperclipException
import importlib.resources as pkg_resources
import yt_dlp.YoutubeDL as ydl
from PIL import Image, ImageDraw, ImageFont


class KaraokePrep:
    def __init__(
        self,
        input_media=None,
        artist=None,
        title=None,
        filename_pattern=None,
        dry_run=False,
        log_level=logging.DEBUG,
        log_formatter=None,
        model_names=["UVR_MDXNET_KARA_2.onnx", "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt"],
        model_file_dir=os.path.join(tempfile.gettempdir(), "audio-separator-models"),
        output_dir=".",
        lossless_output_format="FLAC",
        lossy_output_format="MP3",
        use_cuda=False,
        use_coreml=False,
        normalization_enabled=True,
        denoise_enabled=True,
        create_track_subfolders=False,
        intro_background_color="#000000",
        intro_background_image=None,
        intro_font="Montserrat-Bold.ttf",
        intro_artist_color="#ffffff",
        intro_title_color="#ff7acc",
        existing_instrumental=None,
        existing_title_image=None,
        end_background_color="#000000",
        end_background_image=None,
        end_font="Montserrat-Bold.ttf",
        end_extra_text_color="#ffffff",
        end_artist_color="#ffffff",
        end_title_color="#ff7acc",
        existing_end_image=None,
        title_video_duration=5,
        end_video_duration=5,
        title_initial_font_size=500,
        title_top_padding=950,
        title_title_padding=400,
        title_artist_padding=700,
        title_fixed_gap=150,
        end_initial_font_size=500,
        end_top_padding=950,
        end_title_padding=400,
        end_artist_padding=700,
        end_extra_text_padding=300,
        end_fixed_gap=150,
        end_extra_text="THANK YOU FOR SINGING!",
        lyrics_artist=None,
        lyrics_title=None,
        skip_lyrics=False,
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
        self.model_names = model_names
        self.model_file_dir = model_file_dir
        self.output_dir = output_dir
        self.lossless_output_format = lossless_output_format.lower()
        self.lossy_output_format = lossy_output_format.lower()
        self.use_cuda = use_cuda
        self.use_coreml = use_coreml
        self.normalization_enabled = normalization_enabled
        self.denoise_enabled = denoise_enabled
        self.create_track_subfolders = create_track_subfolders
        self.existing_instrumental = existing_instrumental
        self.existing_title_image = existing_title_image
        self.title_video_duration = title_video_duration
        self.end_video_duration = end_video_duration
        self.title_initial_font_size = title_initial_font_size
        self.title_top_padding = title_top_padding
        self.title_title_padding = title_title_padding
        self.title_artist_padding = title_artist_padding
        self.title_fixed_gap = title_fixed_gap
        self.end_initial_font_size = end_initial_font_size
        self.end_top_padding = end_top_padding
        self.end_title_padding = end_title_padding
        self.end_artist_padding = end_artist_padding
        self.end_extra_text_padding = end_extra_text_padding
        self.end_fixed_gap = end_fixed_gap
        self.end_extra_text = end_extra_text
        self.lyrics_artist = lyrics_artist
        self.lyrics_title = lyrics_title
        self.skip_lyrics = skip_lyrics

        # Path to the Windows PyInstaller frozen bundled ffmpeg.exe, or the system-installed FFmpeg binary on Mac/Linux
        ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg.exe") if getattr(sys, "frozen", False) else "ffmpeg"

        self.ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"

        if self.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"

        self.title_format = {
            "background_color": intro_background_color,
            "background_image": intro_background_image,
            "font": intro_font,
            "artist_color": intro_artist_color,
            "title_color": intro_title_color,
        }

        self.end_format = {
            "background_color": end_background_color,
            "background_image": end_background_image,
            "font": end_font,
            "extra_text_color": end_extra_text_color,
            "artist_color": end_artist_color,
            "title_color": end_title_color,
        }

        self.existing_end_image = existing_end_image

        self.extracted_info = None
        self.persistent_artist = None

        self.logger.debug(f"KaraokePrep lossless_output_format: {self.lossless_output_format}")

        if not os.path.exists(self.output_dir):
            self.logger.debug(f"Overall output dir {self.output_dir} did not exist, creating")
            os.makedirs(self.output_dir)
        else:
            self.logger.debug(f"Overall output dir {self.output_dir} already exists")

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

    def write_lyrics_from_genius(self, artist, title, filename):
        genius = lyricsgenius.Genius(access_token=os.environ["GENIUS_API_TOKEN"], verbose=False, remove_section_headers=True)
        song = genius.search_song(title, artist)
        if song:
            lyrics = self.clean_genius_lyrics(song.lyrics)

            if not self.dry_run:
                with open(filename, "w") as f:
                    f.write(lyrics)

            self.logger.info("Lyrics for %s by %s fetched successfully", title, artist)
            return lyrics.split("\n")
        else:
            self.logger.warning("Could not find lyrics for %s by %s", title, artist)
            return None

    def clean_genius_lyrics(self, lyrics):
        lyrics = lyrics.replace("\\n", "\n")
        lyrics = re.sub(r"You might also like", "", lyrics)
        lyrics = re.sub(
            r".*?Lyrics([A-Z])", r"\1", lyrics
        )  # Remove the song name and word "Lyrics" if this has a non-newline char at the start
        lyrics = re.sub(r"^[0-9]* Contributors.*Lyrics", "", lyrics)  # Remove this example: 27 ContributorsSex Bomb Lyrics
        lyrics = re.sub(
            r"See.*Live.*Get tickets as low as \$[0-9]+", "", lyrics
        )  # Remove this example: See Tom Jones LiveGet tickets as low as $71
        lyrics = re.sub(r"[0-9]+Embed$", "", lyrics)  # Remove the word "Embed" at end of line with preceding numbers if found
        lyrics = re.sub(r"(\S)Embed$", r"\1", lyrics)  # Remove the word "Embed" if it has been tacked onto a word at the end of a line
        lyrics = re.sub(r"^Embed$", r"", lyrics)  # Remove the word "Embed" if it has been tacked onto a word at the end of a line
        lyrics = re.sub(r".*?\[.*?\].*?", "", lyrics)  # Remove lines containing square brackets
        # add any additional cleaning rules here
        return lyrics

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

    def write_processed_lyrics(self, lyrics, processed_lyrics_file):
        self.logger.info(f"Writing processed lyrics to {processed_lyrics_file}")

        processed_lyrics_lines = ""
        iteration_count = 0
        max_iterations = 100  # Failsafe limit

        if not self.dry_run:
            with open(processed_lyrics_file, "w") as outfile:
                all_processed = False
                while not all_processed:
                    if iteration_count > max_iterations:
                        self.logger.error("Maximum iterations exceeded in write_processed_lyrics.")
                        break

                    all_processed = True
                    new_lyrics = []
                    for line in lyrics:
                        line = line.strip()

                        # Check for abnormal space characters and replace them
                        abnormal_spaces = [chr(i) for i in range(sys.maxunicode) if unicodedata.category(chr(i)) == "Zs" and chr(i) != " "]
                        if any(space in line for space in abnormal_spaces):
                            self.logger.warning(f"Replacing abnormal space characters found in line: {line}")
                            for space in abnormal_spaces:
                                line = line.replace(space, " ")

                        processed = self.process_line(line)
                        new_lyrics.extend(processed)
                        if any(len(l) > 36 for l in processed):
                            all_processed = False
                    lyrics = new_lyrics

                    iteration_count += 1

                # Write the processed lyrics to file
                for line in lyrics:
                    outfile.write(line + "\n")
                    processed_lyrics_lines += line + "\n"

        if not self.dry_run:
            try:
                pyperclip.copy(processed_lyrics_lines)
                self.logger.info(f"Processed lyrics copied to clipboard.")
            except PyperclipException:
                self.logger.warning("Clipboard functionality not available. Skipping clipboard operations.")

        return processed_lyrics_lines

    def sanitize_filename(self, filename):
        """Replace or remove characters that are unsafe for filenames."""
        # Replace problematic characters with underscores
        for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
            filename = filename.replace(char, "_")
        # Remove any trailing periods or spaces
        filename = filename.rstrip(" ")
        return filename

    def separate_audio(self, audio_file, model_name, instrumental_path, vocals_path):
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

        for file in output_files:
            if "(Vocals)" in file:
                os.rename(file, vocals_path)
            elif "(Instrumental)" in file:
                os.rename(file, instrumental_path)

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

    def calculate_text_size_and_position(self, draw, text, font_path, start_size, resolution, padding):
        font_size = start_size
        font = ImageFont.truetype(font_path, size=font_size) if os.path.exists(font_path) else ImageFont.load_default()

        # Initial position for calculating the text bounding box
        temp_position = (padding, padding)
        bbox = draw.textbbox(temp_position, text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        while text_width + 2 * padding > resolution[0] or text_height + 2 * padding > resolution[1]:
            font_size -= 10
            if font_size <= 0:
                raise ValueError("Cannot fit text within screen bounds.")
            font = ImageFont.truetype(font_path, size=font_size) if os.path.exists(font_path) else ImageFont.load_default()
            bbox = draw.textbbox(temp_position, text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

        text_position = ((resolution[0] - text_width) // 2, (resolution[1] - text_height) // 2)
        return font, text_position

    def calculate_text_position(self, draw, text, font, resolution, vertical_offset):
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = (resolution[0] - text_width) // 2
        text_y = vertical_offset
        return (text_x, text_y), text_height

    def create_video(
        self,
        extra_text,
        title_text,
        artist_text,
        format,
        output_image_filepath_noext,
        output_video_filepath,
        existing_image=None,
        extra_text_color=None,
        title_color=None,
        artist_color=None,
        duration=5,
        initial_font_size=500,
        top_padding=950,
        title_padding=400,
        artist_padding=700,
        extra_text_padding=600,
        fixed_gap=150,
    ):
        resolution = (3840, 2160)  # 4K resolution
        self.logger.info(f"Creating video with format: {format}")
        self.logger.info(f"extra_text: {extra_text}, artist_text: {artist_text}, title_text: {title_text}")
        self.logger.info(
            f"top_padding: {top_padding}, title_padding: {title_padding}, artist_padding: {artist_padding}, extra_text_padding: {extra_text_padding}"
        )

        if existing_image:
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
                    existing_image_obj = existing_image_obj.convert("RGB")  # Convert RGBA to RGB
                existing_image_obj.save(output_image_filepath_noext + ".jpg", quality=95)

        else:
            # Load or create background image
            if format["background_image"] and os.path.exists(format["background_image"]):
                self.logger.info(f"Using background image file: {format['background_image']}")
                background = Image.open(format["background_image"])
            else:
                self.logger.info(f"Using background color: {format['background_color']}")
                background = Image.new("RGB", resolution, color=self.hex_to_rgb(format["background_color"]))

            # Resize background to match resolution
            background = background.resize(resolution)

            draw = ImageDraw.Draw(background)

            # Accessing the font file from the package resources
            with pkg_resources.path("karaoke_prep.resources", format["font"]) as font_path:
                # Calculate positions and sizes for title, artist, and extra text
                title_font, _ = self.calculate_text_size_and_position(
                    draw, title_text, str(font_path), initial_font_size, resolution, title_padding
                )
                artist_font, _ = self.calculate_text_size_and_position(
                    draw, artist_text, str(font_path), initial_font_size, resolution, artist_padding
                )
                if extra_text:
                    self.logger.info(f"Calculating extra text font size and position for: {extra_text}")
                    extra_text_font, _ = self.calculate_text_size_and_position(
                        draw, extra_text, str(font_path), initial_font_size, resolution, extra_text_padding
                    )

            # Calculate vertical positions with consistent gap
            current_y = top_padding
            if extra_text:
                self.logger.info(f"Calculating extra text position for: {extra_text}")
                extra_text_position, extra_text_height = self.calculate_text_position(
                    draw, extra_text, extra_text_font, resolution, current_y
                )
                draw.text(extra_text_position, extra_text, fill=extra_text_color, font=extra_text_font)
                current_y += extra_text_height + fixed_gap

            title_text_position, title_height = self.calculate_text_position(draw, title_text, title_font, resolution, current_y)
            draw.text(title_text_position, title_text, fill=title_color, font=title_font)
            current_y += title_height + fixed_gap

            artist_text_position, _ = self.calculate_text_position(draw, artist_text, artist_font, resolution, current_y)
            draw.text(artist_text_position, artist_text, fill=artist_color, font=artist_font)

            # Save static background image
            background.save(f"{output_image_filepath_noext}.png")

            # Save static background image as JPG for smaller filesize to upload as YouTube thumbnail
            background_rgb = background.convert("RGB")
            background_rgb.save(f"{output_image_filepath_noext}.jpg", quality=95)

        # Use ffmpeg to create video
        ffmpeg_command = f'{self.ffmpeg_base_command} -y -loop 1 -framerate 30 -i "{output_image_filepath_noext}.png" -f lavfi -i anullsrc '
        ffmpeg_command += f'-c:v libx264 -r 30 -t {duration} -pix_fmt yuv420p -vf scale={resolution[0]}:{resolution[1]} -c:a aac -shortest "{output_video_filepath}"'

        self.logger.info("Generating video...")
        self.logger.debug(f"Running command: {ffmpeg_command}")
        os.system(ffmpeg_command)

    def create_end_video(self, artist, title, format, output_image_filepath_noext, output_video_filepath):
        extra_text = self.end_extra_text
        title_text = title.upper()
        artist_text = artist.upper()
        self.create_video(
            extra_text=extra_text,
            title_text=title_text,
            artist_text=artist_text,
            format=format,
            output_image_filepath_noext=output_image_filepath_noext,
            output_video_filepath=output_video_filepath,
            existing_image=self.existing_end_image,
            extra_text_color=format["extra_text_color"],
            title_color=format["title_color"],
            artist_color=format["artist_color"],
            duration=self.end_video_duration,
            initial_font_size=self.end_initial_font_size,
            top_padding=self.end_top_padding,
            title_padding=self.end_title_padding,
            artist_padding=self.end_artist_padding,
            extra_text_padding=self.end_extra_text_padding,
            fixed_gap=self.end_fixed_gap,
        )

    def create_title_video(self, artist, title, format, output_image_filepath_noext, output_video_filepath):
        title_text = title.upper()
        artist_text = artist.upper()
        self.create_video(
            extra_text=None,
            title_text=title_text,
            artist_text=artist_text,
            format=format,
            output_image_filepath_noext=output_image_filepath_noext,
            output_video_filepath=output_video_filepath,
            existing_image=self.existing_title_image,
            title_color=format["title_color"],
            artist_color=format["artist_color"],
            duration=self.title_video_duration,
            initial_font_size=self.title_initial_font_size,
            top_padding=self.title_top_padding,
            title_padding=self.title_title_padding,
            artist_padding=self.title_artist_padding,
            fixed_gap=self.title_fixed_gap,
        )

    def hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def prep_single_track(self):
        self.logger.info(f"Preparing single track: {self.artist} - {self.title}")

        if self.input_media is not None and os.path.isfile(self.input_media):
            self.extractor = "Local"
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
            processed_track["lyrics"] = os.path.join(track_output_dir, f"{artist_title} (Lyrics).txt")
            if os.path.exists(processed_track["lyrics"]):
                self.logger.debug(f"Lyrics file already exists, skipping fetch: {processed_track['lyrics']}")
            else:
                self.logger.info("Fetching lyrics from Genius...")
                lyrics_artist = self.lyrics_artist or self.artist
                lyrics_title = self.lyrics_title or self.title
                self.lyrics = self.write_lyrics_from_genius(lyrics_artist, lyrics_title, processed_track["lyrics"])

                processed_track["processed_lyrics"] = os.path.join(track_output_dir, f"{artist_title} (Lyrics Processed).txt")
                if self.lyrics is None:
                    processed_track["lyrics"] = None
                    processed_track["processed_lyrics"] = None
                else:
                    self.write_processed_lyrics(self.lyrics, processed_track["processed_lyrics"])

        output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (Title)")
        processed_track["title_image_png"] = f"{output_image_filepath_noext}.png"
        processed_track["title_image_jpg"] = f"{output_image_filepath_noext}.jpg"
        processed_track["title_video"] = os.path.join(track_output_dir, f"{artist_title} (Title).mov")

        if os.path.exists(processed_track["title_video"]):
            self.logger.debug(f"Title video already exists, skipping render: {processed_track['title_video']}")
        else:
            self.logger.info(f"Creating title video...")
            self.create_title_video(self.artist, self.title, self.title_format, output_image_filepath_noext, processed_track["title_video"])

        output_image_filepath_noext = os.path.join(track_output_dir, f"{artist_title} (End)")
        processed_track["end_image_png"] = f"{output_image_filepath_noext}.png"
        processed_track["end_image_jpg"] = f"{output_image_filepath_noext}.jpg"
        processed_track["end_video"] = os.path.join(track_output_dir, f"{artist_title} (End).mov")

        if os.path.exists(processed_track["end_video"]):
            self.logger.debug(f"End screen video already exists, skipping render: {processed_track['end_video']}")
        else:
            self.logger.info(f"Creating end screen video...")
            self.create_end_video(self.artist, self.title, self.end_format, output_image_filepath_noext, processed_track["end_video"])

        if self.existing_instrumental:
            self.logger.info(f"Using existing instrumental file: {self.existing_instrumental}")
            existing_instrumental_extension = os.path.splitext(self.existing_instrumental)[1]

            instrumental_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental Custom){existing_instrumental_extension}")
            instrumental_path_lossy = os.path.join(track_output_dir, f"{artist_title} (Instrumental Custom).{self.lossy_output_format}")

            shutil.copy2(self.existing_instrumental, instrumental_path)
            self.convert_to_lossy(instrumental_path, instrumental_path_lossy)

            processed_track["separated_audio"]["Custom"] = {
                "instrumental": instrumental_path,
                "instrumental_lossy": instrumental_path_lossy,
                "vocals": None,
                "vocals_lossy": None,
            }
        else:
            self.logger.info(f"Separating audio for track: {self.title} by {self.artist} using models: {', '.join(self.model_names)}")
            for model_name in self.model_names:
                processed_track[f"separated_audio"][model_name] = {}
                instrumental_path = os.path.join(
                    track_output_dir, f"{artist_title} (Instrumental {model_name}).{self.lossless_output_format}"
                )
                vocals_path = os.path.join(track_output_dir, f"{artist_title} (Vocals {model_name}).{self.lossless_output_format}")
                instrumental_path_lossy = os.path.join(
                    track_output_dir, f"{artist_title} (Instrumental {model_name}).{self.lossy_output_format}"
                )
                vocals_path_lossy = os.path.join(track_output_dir, f"{artist_title} (Vocals {model_name}).{self.lossy_output_format}")

                if not (os.path.isfile(instrumental_path) and os.path.isfile(vocals_path)):
                    self.separate_audio(processed_track["input_audio_wav"], model_name, instrumental_path, vocals_path)
                    self.convert_to_lossy(instrumental_path, instrumental_path_lossy)
                    self.convert_to_lossy(vocals_path, vocals_path_lossy)

                processed_track[f"separated_audio"][model_name]["instrumental"] = instrumental_path
                processed_track[f"separated_audio"][model_name]["vocals"] = vocals_path
                processed_track[f"separated_audio"][model_name]["instrumental_lossy"] = instrumental_path_lossy
                processed_track[f"separated_audio"][model_name]["vocals_lossy"] = vocals_path_lossy

        self.logger.info("Script finished, audio downloaded, lyrics fetched and audio separated!")

        return processed_track

    def convert_to_lossy(self, input_filename, output_filename):
        if input_filename is None or not os.path.isfile(input_filename):
            raise Exception(f"Error: Invalid input file provided for convert_to_lossy: {input_filename}")

        self.logger.info(f"Converting {self.lossless_output_format} audio to lossy {self.lossy_output_format} format")

        ffmpeg_extras = "-q:a 0" if self.lossy_output_format == "mp3" else ""

        ffmpeg_command = f'{self.ffmpeg_base_command} -i "{input_filename}" {ffmpeg_extras} "{output_filename}"'
        self.logger.debug(f"Running command: {ffmpeg_command}")
        os.system(ffmpeg_command)

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
