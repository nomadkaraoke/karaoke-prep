import os
import re
import glob
import yt_dlp
import logging
import lyricsgenius
import subprocess
from PIL import Image, ImageDraw, ImageFont


class KaraokePrep:
    def __init__(
        self,
        url=None,
        artist=None,
        title=None,
        log_level=logging.DEBUG,
        log_formatter=None,
        model_name="UVR_MDXNET_KARA_2",
        model_name_2="UVR-MDX-NET-Inst_HQ_3",
        model_file_dir="/tmp/audio-separator-models/",
        output_dir=".",
        output_format="WAV",
        use_cuda=False,
        use_coreml=False,
        normalization_enabled=True,
        denoise_enabled=True,
        create_track_subfolders=False,
        intro_background_color="#000000",
        intro_background_image=None,
        intro_font="AvenirNext-Bold.ttf",
        intro_artist_color="#ff7acc",
        intro_title_color="#ffdf6b",
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

        self.logger.debug(f"KaraokePrep instantiating with url: {url} artist: {artist} title: {title}")

        self.url = url
        self.artist = artist
        self.title = title
        self.model_name = model_name
        self.model_name_2 = model_name_2
        self.model_file_dir = model_file_dir
        self.output_dir = output_dir
        self.output_format = output_format
        self.use_cuda = use_cuda
        self.use_coreml = use_coreml
        self.normalization_enabled = normalization_enabled
        self.denoise_enabled = denoise_enabled
        self.create_track_subfolders = create_track_subfolders
        self.intro_background_color = intro_background_color
        self.intro_background_image = intro_background_image
        self.intro_font = intro_font
        self.intro_artist_color = intro_artist_color
        self.intro_title_color = intro_title_color

        self.logger.debug(f"KaraokePrep output_format: {self.output_format}")

        if not os.path.exists(self.output_dir):
            self.logger.debug(f"Overall output dir {self.output_dir} did not exist, creating")
            os.makedirs(self.output_dir)
        else:
            self.logger.debug(f"Overall output dir {self.output_dir} already exists")

    def extract_metadata_from_url(self):
        """
        Extracts metadata from the YouTube URL.
        """
        if self.url:
            with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
                info = ydl.extract_info(self.url, download=False)
                self.artist, self.title = self.parse_metadata(info)
                if self.artist and self.title:
                    self.logger.info(f"Extracted artist: {self.artist}, title: {self.title}")
                else:
                    self.logger.error("Failed to extract artist and title from the YouTube URL.")

    def parse_metadata(self, info):
        """
        Parses the metadata to extract artist and title.

        :param info: The metadata information extracted from yt_dlp.
        :return: A tuple containing the artist and title.
        """
        # Default values if parsing fails
        artist = ""
        title = ""

        # Example: "Artist - Title"
        if "title" in info and "-" in info["title"]:
            artist, title = info["title"].split("-", 1)
            artist = artist.strip()
            title = title.strip()
        elif "uploader" in info:
            # Fallback to uploader as artist if title parsing fails
            artist = info["uploader"]
            if "title" in info:
                title = info["title"].strip()

        # If unable to parse, log an appropriate message
        if not artist or not title:
            self.logger.warning("Could not parse artist and title from the video metadata.")

        return artist, title

    def get_youtube_id_for_top_search_result(self, query):
        ydl_opts = {"quiet": "True", "format": "bestaudio", "noplaylist": "True", "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            video = ydl.extract_info(f"ytsearch1:{query}", download=False)["entries"][0]

            if video:
                youtube_id = video.get("id")
                return youtube_id
            else:
                self.logger.warning(f"No YouTube results found for query: {query}")
                return None

    def download_video(self, youtube_id, output_filename_no_extension):
        self.logger.debug(f"Downloading YouTube video {youtube_id} to filename {output_filename_no_extension} + (as yet) unknown extension")
        ydl_opts = {
            "format": "bv*+ba/b",  # if a combined video + audio format is better than the best video-only format use the combined format
            "outtmpl": f"{output_filename_no_extension}",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as youtube_dl_instance:
            youtube_dl_instance.download([f"https://www.youtube.com/watch?v={youtube_id}"])
            self.logger.warn(f"Download finished, assuming hard-coded webm extension (!) and returning this filename")
            # TODO: Replace hard-coded webm extension with the actual extension of the downloaded file using yt-dlp hooks / event callback
            return output_filename_no_extension + ".webm"

    def extract_still_image_from_video(self, input_filename, output_filename_no_extension):
        output_filename = output_filename_no_extension + ".png"
        self.logger.debug(f"Extracting still image from position 30s YouTube video to {output_filename}")
        os.system(f'ffmpeg -i "{input_filename}" -ss 00:00:30 -vframes 1 "{output_filename}"')
        return output_filename

    def convert_to_wav(self, input_filename, output_filename_no_extension):
        output_filename = output_filename_no_extension + ".wav"
        self.logger.debug(f"Converting {input_filename} to WAV file {output_filename}")
        os.system(f'ffmpeg -i "{input_filename}" "{output_filename}"')
        return output_filename

    def write_lyrics_from_genius(self, artist, title, filename):
        genius = lyricsgenius.Genius(os.environ["GENIUS_API_TOKEN"])
        song = genius.search_song(title, artist)
        if song:
            lyrics = self.clean_genius_lyrics(song.lyrics)

            with open(filename, "w") as f:
                f.write(lyrics)

            self.logger.info("Lyrics for %s by %s fetched successfully", title, artist)
        else:
            self.logger.warning("Could not find lyrics for %s by %s", title, artist)

    def clean_genius_lyrics(self, lyrics):
        lyrics = lyrics.replace("\\n", "\n")
        lyrics = re.sub(r"You might also like", "", lyrics)
        lyrics = re.sub(
            r".*?Lyrics([A-Z])", r"\1", lyrics
        )  # Remove the song name and word "Lyrics" if this has a non-newline char at the start
        lyrics = re.sub(r"[0-9]+Embed$", "", lyrics)  # Remove the word "Embed" at end of line with preceding numbers if found
        lyrics = re.sub(r"(\S)Embed$", r"\1", lyrics)  # Remove the word "Embed" if it has been tacked onto a word at the end of a line
        lyrics = re.sub(r"^Embed$", r"", lyrics)  # Remove the word "Embed" if it has been tacked onto a word at the end of a line
        lyrics = re.sub(r".*?\[.*?\].*?", "", lyrics)  # Remove lines containing square brackets
        # add any additional cleaning rules here
        return lyrics

    def sanitize_filename(self, filename):
        """Replace or remove characters that are unsafe for filenames."""
        # Replace problematic characters with underscores
        for char in ["\\", "/", ":", "*", "?", '"', "<", ">", "|"]:
            filename = filename.replace(char, "_")
        # Remove any trailing periods or spaces
        filename = filename.rstrip(". ")
        return filename

    def separate_audio(self, audio_file, model_name, instrumental_path, vocals_path):
        if audio_file is None or not os.path.isfile(audio_file):
            raise Exception("Error: Invalid audio source provided.")

        self.logger.debug(f"audio_file is valid file: {audio_file}")

        self.logger.debug(
            f"instantiating Separator with model_name: {model_name} instrumental_path: {instrumental_path} and output_format: {self.output_format}"
        )

        from audio_separator import Separator

        separator = Separator(
            audio_file,
            log_level=self.log_level,
            log_formatter=self.log_formatter,
            model_name=model_name,
            model_file_dir=self.model_file_dir,
            output_format=self.output_format,
            primary_stem_path=instrumental_path,
            secondary_stem_path=vocals_path,
        )
        _, _ = separator.separate()
        self.logger.debug(f"Separation complete!")

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

    def create_intro_video(self, artist, title, output_filename):
        duration = 5  # Duration in seconds
        resolution = (3840, 2160)  # 4K resolution
        font_size = 400  # Adjust as needed
        line_spacing = 50  # Adjust as needed

        # Load or create background image
        if self.intro_background_image:
            background = Image.open(self.intro_background_image)
        else:
            background = Image.new("RGB", resolution, color=self.hex_to_rgb(self.intro_background_color))

        # Resize background to match resolution
        background = background.resize(resolution)

        # Create an ImageDraw instance
        draw = ImageDraw.Draw(background)

        # Check if the font file exists, if not use a default font
        if os.path.exists(self.intro_font):
            font = ImageFont.truetype(self.intro_font, size=font_size)
        else:
            self.logger.warning(f"Font file not found: {self.intro_font}. Using default font.")
            font = ImageFont.load_default(size=font_size)

        # Calculate text width using the ImageDraw instance
        artist_text_width = draw.textlength(artist, font=font)
        title_text_width = draw.textlength(title, font=font)

        # Calculate text positions
        artist_text_position = ((resolution[0] - artist_text_width) // 2, resolution[1] // 2 - font_size - line_spacing)
        title_text_position = ((resolution[0] - title_text_width) // 2, resolution[1] // 2 + line_spacing)

        # Draw text
        draw.text(artist_text_position, artist, fill=self.intro_artist_color, font=font)
        draw.text(title_text_position, title, fill=self.intro_title_color, font=font)

        # Save to a temporary image file
        temp_image_path = "/tmp/temp_background.png"
        background.save(temp_image_path)
        self.logger.warning(f"Temporarily saving background image to {temp_image_path}")

        # Use ffmpeg to create video
        ffmpeg_command = [
            "ffmpeg",
            "-y",  # Overwrite output files without asking
            "-loop",  # Loop the input image
            "1",  # Loop the input image
            "-i",  # Input file
            temp_image_path,  # Input file
            "-c:v",  # Video codec
            "libx264",  # Video codec
            "-t",  # Duration
            str(duration),  # Duration
            "-pix_fmt",  # Pixel format
            "yuv420p",  # Pixel format
            "-vf",  # Video filter
            f"scale={resolution[0]}:{resolution[1]}",  # Video filter
            output_filename,  # Output filename
        ]

        subprocess.run(ffmpeg_command)
        # os.remove(temp_image_path)

    def hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple."""
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))

    def prep_single_track(self):
        if self.artist is None or self.title is None:
            self.logger.warn(f"Artist or Title nor specified manually, guessing from YouTube metadata...")
            self.extract_metadata_from_url()

        artist = self.artist
        title = self.title

        self.logger.info(f"Downloading inputs for track: {title} by {artist}")
        track_output_dir, artist_title = self.setup_output_paths(artist, title)
        processed_track = {
            "track_output_dir": track_output_dir,
            "artist": artist,
            "title": title,
        }

        yt_webm_filename_pattern = os.path.join(track_output_dir, f"{artist_title} (YouTube *.webm")
        yt_webm_glob = glob.glob(yt_webm_filename_pattern)

        yt_png_filename_pattern = os.path.join(track_output_dir, f"{artist_title} (YouTube *.png")
        yt_png_glob = glob.glob(yt_png_filename_pattern)

        yt_wav_filename_pattern = os.path.join(track_output_dir, f"{artist_title} (YouTube *.wav")
        yt_wav_glob = glob.glob(yt_wav_filename_pattern)

        processed_track["youtube_video"] = None
        processed_track["youtube_still_image"] = None
        processed_track["youtube_audio"] = None

        if yt_webm_glob and yt_png_glob and yt_wav_glob:
            processed_track["youtube_video"] = yt_webm_glob[0]
            processed_track["youtube_still_image"] = yt_png_glob[0]
            processed_track["youtube_audio"] = yt_wav_glob[0]

            self.logger.debug(f"YouTube output files already exist, skipping download: {processed_track['youtube_video']} + .wav + .png")
        else:
            if self.url is None:
                self.logger.warn(f"No URL specified - the top result from YouTube will be used.")
                self.logger.info("Searching YouTube for video ID...")
                query = f"{artist} {title}"
                youtube_id = self.get_youtube_id_for_top_search_result(query)
            else:
                self.logger.info("Parsing YouTube video ID from URL...")
                youtube_id = self.url.split("watch?v=")[1]
            if youtube_id:
                output_filename_no_extension = os.path.join(track_output_dir, f"{artist_title} (YouTube {youtube_id})")

                self.logger.info("Downloading original video from YouTube...")
                processed_track["youtube_video"] = self.download_video(youtube_id, output_filename_no_extension)

                self.logger.info("Extracting still image from downloaded video...")
                processed_track["youtube_still_image"] = self.extract_still_image_from_video(
                    processed_track["youtube_video"], output_filename_no_extension
                )

                self.logger.info("Converting downloaded video to WAV for audio processing...")
                processed_track["youtube_audio"] = self.convert_to_wav(processed_track["youtube_video"], output_filename_no_extension)
            else:
                self.logger.warning(f"Skipping {title} by {artist} due to missing YouTube ID.")

        lyrics_file = os.path.join(track_output_dir, f"{artist_title} (Lyrics).txt")
        if os.path.exists(lyrics_file):
            self.logger.debug(f"Lyrics file already exists, skipping fetch: {lyrics_file}")
        else:
            self.logger.info("Fetching lyrics from Genius...")
            self.write_lyrics_from_genius(artist, title, lyrics_file)

        processed_track["lyrics"] = lyrics_file

        intro_filename = os.path.join(track_output_dir, f"{artist_title} (Intro).mp4")
        self.create_intro_video(artist, title, intro_filename)

        self.logger.info(f"Separating audio twice for track: {title} by {artist}")

        instrumental_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental {self.model_name}).{self.output_format}")
        vocals_path = os.path.join(track_output_dir, f"{artist_title} (Vocals {self.model_name}).{self.output_format}")

        if os.path.isfile(instrumental_path) and os.path.isfile(vocals_path):
            self.logger.debug(f"Separated audio files already exist in output paths, skipping separation: {instrumental_path}")
        else:
            self.separate_audio(processed_track["youtube_audio"], self.model_name, instrumental_path, vocals_path)

        processed_track["instrumental_audio"] = instrumental_path
        processed_track["vocals_audio"] = vocals_path

        instrumental_path_2 = os.path.join(track_output_dir, f"{artist_title} (Instrumental {self.model_name_2}).{self.output_format}")
        vocals_path_2 = os.path.join(track_output_dir, f"{artist_title} (Vocals {self.model_name_2}).{self.output_format}")

        if os.path.isfile(instrumental_path_2) and os.path.isfile(vocals_path_2):
            self.logger.debug(f"Separated audio files already exist in output paths, skipping separation: {instrumental_path_2}")
        else:
            self.separate_audio(processed_track["youtube_audio"], self.model_name_2, instrumental_path_2, vocals_path_2)

        processed_track["instrumental_audio_2"] = instrumental_path_2
        processed_track["vocals_audio_2"] = vocals_path_2

        self.logger.info("Script finished, audio downloaded, lyrics fetched and audio separated!")

        return processed_track

    def is_playlist_url(self):
        """
        Checks if the provided URL is a YouTube playlist URL.
        """
        if self.url and "playlist?list=" in self.url:
            return True
        return False

    def process_playlist(self):
        """
        Processes all videos in a YouTube playlist.
        """
        self.logger.debug("Querying playlist metadata from YouTube...")
        with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
            result = ydl.extract_info(self.url, download=False)
            if "entries" in result:
                track_results = []
                self.logger.info(f"Found {len(result['entries'])} videos in playlist, processing each invididually...")
                for video in result["entries"]:
                    video_url = f"https://www.youtube.com/watch?v={video['id']}"
                    self.logger.info(f"Processing video: {video_url}")
                    self.url = video_url
                    track_results.append(self.prep_single_track())
                    self.artist = None
                    self.title = None
                return track_results

    def process(self):
        if self.is_playlist_url():
            self.logger.info(f"Provided YouTube URL is a playlist, beginning batch operation")
            return self.process_playlist()
        else:
            self.logger.info(f"Provided YouTube URL is NOT a playlist, processing single track")
            return [self.prep_single_track()]
