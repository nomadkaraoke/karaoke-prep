import requests
import os
import re
import glob
from bs4 import BeautifulSoup
import yt_dlp
import logging
import lyricsgenius
from slugify import slugify
from audio_separator import Separator


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
        use_cuda=False,
        use_coreml=False,
        normalization_enabled=True,
        denoise_enabled=True,
        create_track_subfolders=False,
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
        self.use_cuda = use_cuda
        self.use_coreml = use_coreml
        self.normalization_enabled = normalization_enabled
        self.denoise_enabled = denoise_enabled
        self.create_track_subfolders = create_track_subfolders

        if not os.path.exists(self.output_dir):
            self.logger.debug(f"Overall output dir {self.output_dir} did not exist, creating")
            os.makedirs(self.output_dir)
        else:
            self.logger.debug(f"Overall output dir {self.output_dir} already exists")

        if artist is None or title is None:
            raise Exception("Error: You must provide an artist and title.")

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

    def download_audio(self, youtube_id, filename):
        ydl_opts = {
            "format": "ba",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "wav",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": f"{filename}",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
        }

        with yt_dlp.YoutubeDL(ydl_opts) as youtube_dl_instance:
            youtube_dl_instance.download([f"https://www.youtube.com/watch?v={youtube_id}"])

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

        self.logger.debug(f"instantiating Separator with model_name: {model_name} and instrumental_path: {instrumental_path}")
        separator = Separator(
            audio_file,
            log_level=self.log_level,
            log_formatter=self.log_formatter,
            model_name=model_name,
            model_file_dir=self.model_file_dir,
            output_format="FLAC",
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

    def prep(self):
        artist = self.artist
        title = self.title

        self.logger.info(f"Downloading inputs for track: {title} by {artist}")
        track_output_dir, artist_title = self.setup_output_paths(artist, title)
        processed_track = {
            "track_output_dir": track_output_dir,
            "artist": artist,
            "title": title,
        }

        yt_filename_pattern = os.path.join(track_output_dir, f"{artist_title} (YouTube *.wav")
        youtube_audio_files = glob.glob(yt_filename_pattern)
        youtube_audio_file = None

        if youtube_audio_files:
            youtube_audio_file = youtube_audio_files[0]
            self.logger.debug(f"Youtube audio already exists, skipping download: {youtube_audio_file}")
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
                youtube_audio_file = os.path.join(track_output_dir, f"{artist_title} (YouTube {youtube_id})")

                self.logger.info("Downloading original audio from YouTube to filename {original_audio_filename}")
                self.download_audio(youtube_id, youtube_audio_file)
                youtube_audio_file = youtube_audio_file + ".wav"
            else:
                self.logger.warning(f"Skipping {title} by {artist} due to missing YouTube ID.")

        processed_track["youtube_audio"] = youtube_audio_file

        lyrics_file = os.path.join(track_output_dir, f"{artist_title} (Lyrics).txt")
        if os.path.exists(lyrics_file):
            self.logger.debug(f"Lyrics file already exists, skipping fetch: {lyrics_file}")
        else:
            self.logger.info("Fetching lyrics from Genius...")
            self.write_lyrics_from_genius(artist, title, lyrics_file)

        processed_track["lyrics"] = lyrics_file

        self.logger.info(f"Separating audio twice for track: {title} by {artist}")

        instrumental_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental {self.model_name}).flac")
        vocals_path = os.path.join(track_output_dir, f"{artist_title} (Vocals {self.model_name}).flac")

        if os.path.isfile(instrumental_path) and os.path.isfile(vocals_path):
            self.logger.debug(f"Separated audio files already exist in output paths, skipping separation: {instrumental_path}")
        else:
            self.separate_audio(processed_track["youtube_audio"], self.model_name, instrumental_path, vocals_path)

        processed_track["instrumental_audio"] = instrumental_path
        processed_track["vocals_audio"] = vocals_path

        instrumental_path_2 = os.path.join(track_output_dir, f"{artist_title} (Instrumental {self.model_name_2}).flac")
        vocals_path_2 = os.path.join(track_output_dir, f"{artist_title} (Vocals {self.model_name_2}).flac")

        if os.path.isfile(instrumental_path_2) and os.path.isfile(vocals_path_2):
            self.logger.debug(f"Separated audio files already exist in output paths, skipping separation: {instrumental_path_2}")
        else:
            self.separate_audio(processed_track["youtube_audio"], self.model_name_2, instrumental_path_2, vocals_path_2)

        processed_track["instrumental_audio_2"] = instrumental_path_2
        processed_track["vocals_audio_2"] = vocals_path_2

        self.logger.info("Script finished, audio downloaded, lyrics fetched and audio separated!")

        return processed_track
