import os
import sys
import json
import shlex
import logging
import zipfile
import shutil
import re
import requests
import pickle
from lyrics_converter import LyricsConverter
from thefuzz import fuzz
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload
import subprocess
import time
from cdgmaker.lrc_to_cdg import generate_cdg
from google.oauth2.credentials import Credentials
import base64
from email.mime.text import MIMEText


class KaraokeFinalise:
    def __init__(
        self,
        log_level=logging.DEBUG,
        log_formatter=None,
        dry_run=False,
        model_name=None,
        instrumental_format="flac",
        enable_cdg=False,
        enable_txt=False,
        brand_prefix=None,
        organised_dir=None,
        organised_dir_rclone_root=None,
        public_share_dir=None,
        youtube_client_secrets_file=None,
        youtube_description_file=None,
        rclone_destination=None,
        discord_webhook_url=None,
        non_interactive=False,
        email_template_file=None,
        cdg_styles=None,
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

        self.logger.debug(
            f"KaraokeFinalise instantiating, dry_run: {dry_run}, model_name: {model_name}, brand_prefix: {brand_prefix}, organised_dir: {organised_dir}, public_share_dir: {public_share_dir}, rclone_destination: {rclone_destination}"
        )

        # Path to the Windows PyInstaller frozen bundled ffmpeg.exe, or the system-installed FFmpeg binary on Mac/Linux
        ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg.exe") if getattr(sys, "frozen", False) else "ffmpeg"

        self.ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"

        if self.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"

        self.dry_run = dry_run
        self.model_name = model_name
        self.instrumental_format = instrumental_format

        self.brand_prefix = brand_prefix
        self.organised_dir = organised_dir
        self.organised_dir_rclone_root = organised_dir_rclone_root

        self.public_share_dir = public_share_dir
        self.youtube_client_secrets_file = youtube_client_secrets_file
        self.youtube_description_file = youtube_description_file
        self.rclone_destination = rclone_destination
        self.discord_webhook_url = discord_webhook_url
        self.enable_cdg = enable_cdg
        self.enable_txt = enable_txt

        self.youtube_upload_enabled = False
        self.discord_notication_enabled = False
        self.folder_organisation_enabled = False
        self.public_share_copy_enabled = False
        self.public_share_rclone_enabled = False

        self.skip_notifications = False
        self.non_interactive = non_interactive

        self.suffixes = {
            "title_mov": " (Title).mov",
            "title_jpg": " (Title).jpg",
            "end_mov": " (End).mov",
            "end_jpg": " (End).jpg",
            "with_vocals_mov": " (With Vocals).mov",
            "with_vocals_mp4": " (With Vocals).mp4",
            "karaoke_lrc": " (Karaoke).lrc",
            "karaoke_cdg": " (Karaoke).cdg",
            "karaoke_txt": " (Karaoke).txt",
            "karaoke_mp3": " (Karaoke).mp3",
            "karaoke_mov": " (Karaoke).mov",
            "final_karaoke_mp4": " (Final Karaoke).mp4",
            "final_karaoke_lossless_mkv": " (Final Karaoke Lossless).mkv",
            "final_karaoke_cdg_zip": " (Final Karaoke CDG).zip",
            "final_karaoke_txt_zip": " (Final Karaoke TXT).zip",
            "final_karaoke_720p_mp4": " (Final Karaoke 720p).mp4",
        }

        self.youtube_url_prefix = "https://www.youtube.com/watch?v="

        self.youtube_url = None
        self.brand_code = None
        self.new_brand_code_dir = None
        self.new_brand_code_dir_path = None
        self.brand_code_dir_sharing_link = None

        self.email_template_file = email_template_file
        self.gmail_service = None

        self.cdg_styles = cdg_styles

    def check_input_files_exist(self, base_name, with_vocals_file, instrumental_audio_file):
        self.logger.info(f"Checking required input files exist...")

        input_files = {
            "title_mov": f"{base_name}{self.suffixes['title_mov']}",
            "title_jpg": f"{base_name}{self.suffixes['title_jpg']}",
            "instrumental_audio": instrumental_audio_file,
            "with_vocals_mov": with_vocals_file,
        }

        optional_input_files = {
            "end_mov": f"{base_name}{self.suffixes['end_mov']}",
            "end_jpg": f"{base_name}{self.suffixes['end_jpg']}",
        }

        if self.enable_cdg or self.enable_txt:
            input_files["karaoke_lrc"] = f"{base_name}{self.suffixes['karaoke_lrc']}"

        for key, file_path in input_files.items():
            if not os.path.isfile(file_path):
                raise Exception(f"Input file {key} not found: {file_path}")

            self.logger.info(f" Input file {key} found: {file_path}")

        for key, file_path in optional_input_files.items():
            if not os.path.isfile(file_path):
                self.logger.info(f" Optional input file {key} not found: {file_path}")

            self.logger.info(f" Input file {key} found, adding to input_files: {file_path}")
            input_files[key] = file_path

        return input_files

    def prepare_output_filenames(self, base_name):
        output_files = {
            "karaoke_mov": f"{base_name}{self.suffixes['karaoke_mov']}",
            "karaoke_mp3": f"{base_name}{self.suffixes['karaoke_mp3']}",
            "with_vocals_mp4": f"{base_name}{self.suffixes['with_vocals_mp4']}",
            "final_karaoke_mp4": f"{base_name}{self.suffixes['final_karaoke_mp4']}",
            "final_karaoke_lossless_mkv": f"{base_name}{self.suffixes['final_karaoke_lossless_mkv']}",
            "final_karaoke_720p_mp4": f"{base_name}{self.suffixes['final_karaoke_720p_mp4']}",
        }

        if self.enable_cdg:
            output_files["final_karaoke_cdg_zip"] = f"{base_name}{self.suffixes['final_karaoke_cdg_zip']}"

        if self.enable_txt:
            output_files["karaoke_txt"] = f"{base_name}{self.suffixes['karaoke_txt']}"
            output_files["final_karaoke_txt_zip"] = f"{base_name}{self.suffixes['final_karaoke_txt_zip']}"

        return output_files

    def prompt_user_confirmation_or_raise_exception(self, prompt_message, exit_message, allow_empty=False):
        if not self.prompt_user_bool(prompt_message, allow_empty=allow_empty):
            self.logger.error(exit_message)
            raise Exception(exit_message)

    def prompt_user_bool(self, prompt_message, allow_empty=False):
        if self.non_interactive:
            self.logger.warning(f"Non-interactive mode, responding True for prompt: {prompt_message}")
            return True

        options_string = "[y]/n" if allow_empty else "y/[n]"
        accept_responses = ["y", "yes"]
        if allow_empty:
            accept_responses.append("")

        print()
        response = input(f"{prompt_message} {options_string} ").strip().lower()
        return response in accept_responses

    def validate_input_parameters_for_features(self):
        self.logger.info(f"Validating input parameters for enabled features...")

        current_directory = os.getcwd()
        self.logger.info(f"Current directory to process: {current_directory}")

        # Enable youtube upload if client secrets file is provided and is valid JSON
        if self.youtube_client_secrets_file is not None and self.youtube_description_file is not None:
            if not os.path.isfile(self.youtube_client_secrets_file):
                raise Exception(f"YouTube client secrets file does not exist: {self.youtube_client_secrets_file}")

            if not os.path.isfile(self.youtube_description_file):
                raise Exception(f"YouTube description file does not exist: {self.youtube_description_file}")

            # Test parsing the file as JSON to check it's valid
            try:
                with open(self.youtube_client_secrets_file, "r") as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                raise Exception(f"YouTube client secrets file is not valid JSON: {self.youtube_client_secrets_file}") from e

            self.logger.debug(f"YouTube upload checks passed, enabling YouTube upload")
            self.youtube_upload_enabled = True

        # Enable discord notifications if webhook URL is provided and is valid URL
        if self.discord_webhook_url is not None:
            if not self.discord_webhook_url.startswith("https://discord.com/api/webhooks/"):
                raise Exception(f"Discord webhook URL is not valid: {self.discord_webhook_url}")

            self.logger.debug(f"Discord webhook URL checks passed, enabling Discord notifications")
            self.discord_notication_enabled = True

        # Enable folder organisation if brand prefix and target directory are provided and target directory is valid
        if self.brand_prefix is not None and self.organised_dir is not None:
            if not os.path.isdir(self.organised_dir):
                raise Exception(f"Target directory does not exist: {self.organised_dir}")

            self.logger.debug(f"Brand prefix and target directory provided, enabling folder organisation")
            self.folder_organisation_enabled = True

        # Enable public share copy if public share directory is provided and is valid directory with MP4 and CDG subdirectories
        if self.public_share_dir is not None:
            if not os.path.isdir(self.public_share_dir):
                raise Exception(f"Public share directory does not exist: {self.public_share_dir}")

            if not os.path.isdir(os.path.join(self.public_share_dir, "MP4")):
                raise Exception(f"Public share directory does not contain MP4 subdirectory: {self.public_share_dir}")

            if not os.path.isdir(os.path.join(self.public_share_dir, "CDG")):
                raise Exception(f"Public share directory does not contain CDG subdirectory: {self.public_share_dir}")

            self.logger.debug(f"Public share directory checks passed, enabling public share copy")
            self.public_share_copy_enabled = True

        # Enable public share rclone if rclone destination is provided
        if self.rclone_destination is not None:
            self.logger.debug(f"Rclone destination provided, enabling rclone sync")
            self.public_share_rclone_enabled = True

        # Tell user which features are enabled, prompt them to confirm before proceeding
        self.logger.info(f"Enabled features:")
        self.logger.info(f" CDG ZIP creation: {self.enable_cdg}")
        self.logger.info(f" TXT ZIP creation: {self.enable_txt}")
        self.logger.info(f" YouTube upload: {self.youtube_upload_enabled}")
        self.logger.info(f" Discord notifications: {self.discord_notication_enabled}")
        self.logger.info(f" Folder organisation: {self.folder_organisation_enabled}")
        self.logger.info(f" Public share copy: {self.public_share_copy_enabled}")
        self.logger.info(f" Public share rclone: {self.public_share_rclone_enabled}")

        self.prompt_user_confirmation_or_raise_exception(
            f"Confirm features enabled log messages above match your expectations for finalisation?",
            "Refusing to proceed without user confirmation they're happy with enabled features.",
            allow_empty=True,
        )

    def authenticate_youtube(self):
        """Authenticate and return a YouTube service object."""
        credentials = None
        youtube_token_file = "/tmp/karaoke-finalise-youtube-token.pickle"

        # Token file stores the user's access and refresh tokens for YouTube.
        if os.path.exists(youtube_token_file):
            with open(youtube_token_file, "rb") as token:
                credentials = pickle.load(token)

        # If there are no valid credentials, let the user log in.
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.youtube_client_secrets_file, scopes=["https://www.googleapis.com/auth/youtube"]
                )
                credentials = flow.run_local_server(port=0)  # This will open a browser for authentication

            # Save the credentials for the next run
            with open(youtube_token_file, "wb") as token:
                pickle.dump(credentials, token)

        return build("youtube", "v3", credentials=credentials)

    def get_channel_id(self):
        youtube = self.authenticate_youtube()

        # Get the authenticated user's channel
        request = youtube.channels().list(part="snippet", mine=True)
        response = request.execute()

        # Extract the channel ID
        if "items" in response:
            channel_id = response["items"][0]["id"]
            return channel_id
        else:
            return None

    def check_if_video_title_exists_on_youtube_channel(self, youtube_title):
        youtube = self.authenticate_youtube()
        channel_id = self.get_channel_id()

        self.logger.info(f"Searching YouTube channel {channel_id} for title: {youtube_title}")
        request = youtube.search().list(part="snippet", channelId=channel_id, q=youtube_title, type="video", maxResults=10)
        response = request.execute()

        # Check if any videos were found
        if "items" in response and len(response["items"]) > 0:
            for item in response["items"]:
                found_title = item["snippet"]["title"]
                similarity_score = fuzz.ratio(youtube_title.lower(), found_title.lower())
                if similarity_score >= 70:  # 70% similarity
                    found_id = item["id"]["videoId"]
                    self.logger.info(
                        f"Potential match found on YouTube channel with ID: {found_id} and title: {found_title} (similarity: {similarity_score}%)"
                    )
                    confirmation = input(f"Is '{found_title}' the video you are finalising? (y/n): ").strip().lower()
                    if confirmation == "y":
                        self.youtube_video_id = found_id
                        self.youtube_url = f"{self.youtube_url_prefix}{self.youtube_video_id}"
                        self.skip_notifications = True
                        return True

        self.logger.info(f"No matching video found with title: {youtube_title}")
        return False

    def truncate_to_nearest_word(self, title, max_length):
        if len(title) <= max_length:
            return title
        truncated_title = title[:max_length].rsplit(" ", 1)[0]
        if len(truncated_title) < max_length:
            truncated_title += " ..."
        return truncated_title

    def upload_final_mp4_to_youtube_with_title_thumbnail(self, artist, title, input_files, output_files):
        self.logger.info(f"Uploading final lossless MKV to YouTube with title thumbnail...")
        if self.dry_run:
            self.logger.info(
                f'DRY RUN: Would upload {output_files["final_karaoke_lossless_mkv"]} to YouTube with thumbnail {input_files["title_jpg"]} using client secrets file: {self.youtube_client_secrets_file}'
            )
        else:
            youtube_title = f"{artist} - {title} (Karaoke)"

            # Truncate title to the nearest whole word and add ellipsis if needed
            max_length = 95
            youtube_title = self.truncate_to_nearest_word(youtube_title, max_length)

            if self.check_if_video_title_exists_on_youtube_channel(youtube_title):
                self.logger.warning(f"Video already exists on YouTube, skipping upload: {self.youtube_url}")
                return

            youtube_description = f"Karaoke version of {artist} - {title} created using karaoke-prep python package."
            if self.youtube_description_file is not None:
                with open(self.youtube_description_file, "r") as f:
                    youtube_description = f.read()

            youtube_category_id = "10"  # Category ID for Music
            youtube_keywords = ["karaoke", "music", "singing", "instrumental", "lyrics", artist, title]

            self.logger.info(f"Authenticating with YouTube...")
            # Upload video to YouTube and set thumbnail.
            youtube = self.authenticate_youtube()

            body = {
                "snippet": {
                    "title": youtube_title,
                    "description": youtube_description,
                    "tags": youtube_keywords,
                    "categoryId": youtube_category_id,
                },
                "status": {"privacyStatus": "public"},
            }

            # Use MediaFileUpload to handle the video file - now using the lossless MKV
            media_file = MediaFileUpload(output_files["final_karaoke_lossless_mkv"], mimetype="video/x-matroska", resumable=True)

            # Call the API's videos.insert method to create and upload the video.
            self.logger.info(f"Uploading final lossless MKV to YouTube...")
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media_file)
            response = request.execute()

            self.youtube_video_id = response.get("id")
            self.youtube_url = f"{self.youtube_url_prefix}{self.youtube_video_id}"
            self.logger.info(f"Uploaded video to YouTube: {self.youtube_url}")

            # Uploading the thumbnail
            if input_files["title_jpg"]:
                media_thumbnail = MediaFileUpload(input_files["title_jpg"], mimetype="image/jpeg")
                youtube.thumbnails().set(videoId=self.youtube_video_id, media_body=media_thumbnail).execute()
                self.logger.info(f"Uploaded thumbnail for video ID {self.youtube_video_id}")

    def get_next_brand_code(self):
        """
        Calculate the next sequence number based on existing directories in the organised_dir.
        Assumes directories are named with the format: BRAND-XXXX Artist - Title
        """
        max_num = 0
        pattern = re.compile(rf"^{re.escape(self.brand_prefix)}-(\d{{4}})")

        if not os.path.isdir(self.organised_dir):
            raise Exception(f"Target directory does not exist: {self.organised_dir}")

        for dir_name in os.listdir(self.organised_dir):
            match = pattern.match(dir_name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

        self.logger.info(f"Next sequence number for brand {self.brand_prefix} calculated as: {max_num + 1}")
        next_seq_number = max_num + 1

        return f"{self.brand_prefix}-{next_seq_number:04d}"

    def post_discord_message(self, message, webhook_url):
        """Post a message to a Discord channel via webhook."""
        data = {"content": message}
        response = requests.post(webhook_url, json=data)
        response.raise_for_status()  # This will raise an exception if the request failed
        self.logger.info("Message posted to Discord")

    def find_with_vocals_file(self):
        self.logger.info("Finding input file in current directory ending (With Vocals).mov or (With Vocals).mp4")

        with_vocals_files = [f for f in os.listdir(".") if self.suffixes["with_vocals_mov"] in f]

        if not with_vocals_files:
            self.logger.info(f"No with vocals MOV file found, looking for with vocals MP4 file instead")

            with_vocals_files = [f for f in os.listdir(".") if self.suffixes["with_vocals_mp4"] in f]
            if with_vocals_files:
                self.logger.info(f"Found with vocals MP4 file: {with_vocals_files[0]}")
                return with_vocals_files[0]

        if not with_vocals_files:
            karaoke_files = [f for f in os.listdir(".") if self.suffixes["karaoke_mov"] in f]
            if karaoke_files:
                for file in karaoke_files:
                    new_file = file.replace(self.suffixes["karaoke_mov"], self.suffixes["with_vocals_mov"])

                    self.prompt_user_confirmation_or_raise_exception(
                        f"Found '{file}' but no '(With Vocals)', rename to {new_file} for vocal input?",
                        "Unable to proceed without With Vocals file or user confirmation of rename.",
                        allow_empty=True,
                    )

                    os.rename(file, new_file)
                    self.logger.info(f"Renamed '{file}' to '{new_file}'")
                    return new_file
            else:
                raise Exception("No suitable files found for processing.")
        else:
            return with_vocals_files[0]  # Assuming only one such file is expected

    def choose_instrumental_audio_file(self, base_name):
        self.logger.info(f"Choosing instrumental audio file to use as karaoke audio...")

        search_string = " (Instrumental"
        self.logger.info(f"Searching for files in current directory containing {search_string}")

        all_instrumental_files = [f for f in os.listdir(".") if search_string in f]
        flac_files = set(f.rsplit(".", 1)[0] for f in all_instrumental_files if f.endswith(".flac"))
        mp3_files = set(f.rsplit(".", 1)[0] for f in all_instrumental_files if f.endswith(".mp3"))
        wav_files = set(f.rsplit(".", 1)[0] for f in all_instrumental_files if f.endswith(".wav"))

        self.logger.debug(f"FLAC files found: {flac_files}")
        self.logger.debug(f"MP3 files found: {mp3_files}")
        self.logger.debug(f"WAV files found: {wav_files}")

        # Filter out MP3 files if their FLAC or WAV counterpart exists
        # Filter out WAV files if their FLAC counterpart exists
        filtered_files = [
            f
            for f in all_instrumental_files
            if f.endswith(".flac")
            or (f.endswith(".wav") and f.rsplit(".", 1)[0] not in flac_files)
            or (f.endswith(".mp3") and f.rsplit(".", 1)[0] not in flac_files and f.rsplit(".", 1)[0] not in wav_files)
        ]

        self.logger.debug(f"Filtered instrumental files: {filtered_files}")

        if not filtered_files:
            raise Exception(f"No instrumental audio files found containing {search_string}")

        if len(filtered_files) == 1:
            return filtered_files[0]

        # Sort the remaining instrumental options alphabetically
        filtered_files.sort(reverse=True)

        self.logger.info(f"Found multiple files containing {search_string}:")
        for i, file in enumerate(filtered_files):
            self.logger.info(f" {i+1}: {file}")

        print()
        response = input(f"Choose instrumental audio file to use as karaoke audio: [1]/{len(filtered_files)}: ").strip().lower()
        if response == "":
            response = "1"

        try:
            response = int(response)
        except ValueError:
            raise Exception(f"Invalid response to instrumental audio file choice prompt: {response}")

        if response < 1 or response > len(filtered_files):
            raise Exception(f"Invalid response to instrumental audio file choice prompt: {response}")

        return filtered_files[response - 1]

    def get_names_from_withvocals(self, with_vocals_file):
        self.logger.info(f"Getting artist and title from {with_vocals_file}")

        base_name = with_vocals_file.replace(self.suffixes["with_vocals_mov"], "").replace(self.suffixes["with_vocals_mp4"], "")
        artist, title = base_name.split(" - ", 1)
        return base_name, artist, title

    def execute_command(self, command, description):
        self.logger.info(description)
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would run command: {command}")
        else:
            self.logger.info(f"Running command: {command}")
            os.system(command)

    def remux_and_encode_output_video_files(self, with_vocals_file, input_files, output_files):
        self.logger.info(f"Remuxing and encoding output video files...")

        # Check if output files already exist, if so, ask user to overwrite or skip
        if (
            os.path.isfile(output_files["karaoke_mov"])
            and os.path.isfile(output_files["final_karaoke_mp4"])
            and os.path.isfile(output_files["final_karaoke_lossless_mkv"])
        ):
            if not self.prompt_user_bool(
                f"Found existing Final Karaoke output files. Overwrite (y) or skip (n)?",
            ):
                self.logger.info(f"Skipping Karaoke MOV remux and Final video renders, existing files will be used.")
                return

        # Remux the synced video with the instrumental audio to produce an instrumental karaoke MOV file
        remux_ffmpeg_command = f'{self.ffmpeg_base_command} -an -i "{with_vocals_file}" -vn -i "{input_files["instrumental_audio"]}" -c:v copy -c:a aac "{output_files["karaoke_mov"]}"'
        self.execute_command(remux_ffmpeg_command, "Remuxing video with instrumental audio")

        # Convert the with vocals video to MP4 if it isn't already
        if not with_vocals_file.endswith(".mp4"):
            with_vocals_mp4_command = (
                f'{self.ffmpeg_base_command} -i "{with_vocals_file}" -c:v libx264 -c:a aac "{output_files["with_vocals_mp4"]}"'
            )
            self.execute_command(with_vocals_mp4_command, "Converting with vocals video to MP4")

            # Delete the with vocals mov after successfully converting it to mp4
            if not self.dry_run and os.path.isfile(with_vocals_file):
                self.logger.info(f"Deleting with vocals MOV file: {with_vocals_file}")
                os.remove(with_vocals_file)

        # Quote file paths to handle special characters
        title_mov_file = shlex.quote(os.path.abspath(input_files["title_mov"]))
        karaoke_mov_file = shlex.quote(os.path.abspath(output_files["karaoke_mov"]))
        output_final_mp4_file = shlex.quote(output_files["final_karaoke_mp4"])

        env_mov_input = ""
        ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]"'

        # Check if end_mov file exists and include it in the concat command
        if "end_mov" in input_files and os.path.isfile(input_files["end_mov"]):
            self.logger.info(f"Found end_mov file: {input_files['end_mov']}, including in final MKV")
            end_mov_file = shlex.quote(os.path.abspath(input_files["end_mov"]))
            env_mov_input = f"-i {end_mov_file}"
            ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0][2:v:0][2:a:0]concat=n=3:v=1:a=1[outv][outa]"'

        aac_codec = "libfdk_aac"

        # Check if aac_at codec is available
        codec_check_command = f"{self.ffmpeg_base_command} -codecs"
        result = os.popen(codec_check_command).read()
        if "aac_at" in result:
            aac_codec = "aac_at"

        # Create the lossless MKV version first (for YouTube upload)
        env_mov_input = ""
        ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]"'

        # Check if end_mov file exists and include it in the concat command
        if "end_mov" in input_files and os.path.isfile(input_files["end_mov"]):
            self.logger.info(f"Found end_mov file: {input_files['end_mov']}, including in final MKV")
            end_mov_file = shlex.quote(os.path.abspath(input_files["end_mov"]))
            env_mov_input = f"-i {end_mov_file}"
            ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0][2:v:0][2:a:0]concat=n=3:v=1:a=1[outv][outa]"'

        # Create lossless MKV with FLAC audio
        join_ffmpeg_command_mkv = f'{self.ffmpeg_base_command} -i {title_mov_file} -i {karaoke_mov_file} {env_mov_input} {ffmpeg_filter} -map "[outv]" -map "[outa]" -c:v libx264 -c:a flac "{output_files["final_karaoke_lossless_mkv"]}"'

        self.execute_command(join_ffmpeg_command_mkv, "Creating lossless MKV version with FLAC audio")

        # Create the regular MP4 version (for sharing)
        join_ffmpeg_command = f'{self.ffmpeg_base_command} -i {title_mov_file} -i {karaoke_mov_file} {env_mov_input} {ffmpeg_filter} -map "[outv]" -map "[outa]" -c:v libx264 -c:a {aac_codec} -q:a 14 "{output_files["final_karaoke_mp4"]}"'

        self.execute_command(join_ffmpeg_command, "Creating MP4 version with AAC audio")

        # Prompt user to check final video files before proceeding
        self.prompt_user_confirmation_or_raise_exception(
            f"Final video files created: {output_files['final_karaoke_mp4']} and {output_files['final_karaoke_lossless_mkv']}, please check them! Proceed?",
            "Refusing to proceed without user confirmation they're happy with the Final videos.",
            allow_empty=True,
        )

    def create_cdg_zip_file(self, input_files, output_files, artist, title):
        self.logger.info(f"Creating CDG and MP3 files, then zipping them...")

        # Check if CDG file already exists, if so, ask user to overwrite or skip
        if os.path.isfile(output_files["final_karaoke_cdg_zip"]):
            if not self.prompt_user_bool(
                f"Found existing CDG ZIP file: {output_files['final_karaoke_cdg_zip']}. Overwrite (y) or skip (n)?",
            ):
                self.logger.info(f"Skipping CDG ZIP file creation, existing file will be used.")
                return

        # Generate CDG and MP3 files
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would generate CDG and MP3 files")
        else:
            self.logger.info(f"Generating CDG and MP3 files")

            if self.cdg_styles is None:
                raise ValueError("CDG styles configuration is required when enable_cdg is True")

            generate_cdg(
                input_files["karaoke_lrc"],
                input_files["instrumental_audio"],
                title,
                artist,
                self.cdg_styles,
            )

        # Look for the generated ZIP file
        expected_zip = f"{artist} - {title} (Karaoke).zip"

        self.logger.info(f"Searching for CDG ZIP file. Expected: {expected_zip}")

        if os.path.isfile(expected_zip):
            self.logger.info(f"Found expected CDG ZIP file: {expected_zip}")
            os.rename(expected_zip, output_files["final_karaoke_cdg_zip"])
            self.logger.info(f"Renamed CDG ZIP file from {expected_zip} to {output_files['final_karaoke_cdg_zip']}")

        if not os.path.isfile(output_files["final_karaoke_cdg_zip"]):
            self.logger.error(f"Failed to find any CDG ZIP file. Listing directory contents:")
            for file in os.listdir():
                self.logger.error(f" - {file}")
            raise Exception(f"Failed to create CDG ZIP file: {output_files['final_karaoke_cdg_zip']}")

        self.logger.info(f"CDG ZIP file created: {output_files['final_karaoke_cdg_zip']}")

        # Extract the CDG ZIP file
        self.logger.info(f"Extracting CDG ZIP file: {output_files['final_karaoke_cdg_zip']}")
        with zipfile.ZipFile(output_files["final_karaoke_cdg_zip"], "r") as zip_ref:
            zip_ref.extractall()

        if os.path.isfile(output_files["karaoke_mp3"]):
            self.logger.info(f"Found extracted MP3 file: {output_files['karaoke_mp3']}")
        else:
            self.logger.error("Failed to find extracted MP3 file")
            raise Exception("Failed to extract MP3 file from CDG ZIP")

    def create_txt_zip_file(self, input_files, output_files):
        self.logger.info(f"Creating TXT ZIP file...")

        # Check if TXT file already exists, if so, ask user to overwrite or skip
        if os.path.isfile(output_files["final_karaoke_txt_zip"]):
            if not self.prompt_user_bool(
                f"Found existing TXT ZIP file: {output_files['final_karaoke_txt_zip']}. Overwrite (y) or skip (n)?",
            ):
                self.logger.info(f"Skipping TXT ZIP file creation, existing file will be used.")
                return

        # Create the ZIP file containing the MP3 and TXT files
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would create TXT ZIP file: {output_files['final_karaoke_txt_zip']}")
        else:
            self.logger.info(f"Running karaoke-converter to convert MidiCo LRC file {input_files['karaoke_lrc']} to TXT format")
            txt_converter = LyricsConverter(output_format="txt", filepath=input_files["karaoke_lrc"])
            converted_txt = txt_converter.convert_file()

            with open(output_files["karaoke_txt"], "w") as txt_file:
                txt_file.write(converted_txt)
                self.logger.info(f"TXT file written: {output_files['karaoke_txt']}")

            self.logger.info(f"Creating ZIP file containing {output_files['karaoke_mp3']} and {output_files['karaoke_txt']}")
            with zipfile.ZipFile(output_files["final_karaoke_txt_zip"], "w") as zipf:
                zipf.write(output_files["karaoke_mp3"], os.path.basename(output_files["karaoke_mp3"]))
                zipf.write(output_files["karaoke_txt"], os.path.basename(output_files["karaoke_txt"]))

            if not os.path.isfile(output_files["final_karaoke_txt_zip"]):
                raise Exception(f"Failed to create TXT ZIP file: {output_files['final_karaoke_txt_zip']}")

            self.logger.info(f"TXT ZIP file created: {output_files['final_karaoke_txt_zip']}")

    def encode_720p_version(self, input_file, output_file):
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -i "{input_file}" '
            f'-c:v libx264 -vf "scale=1280:720" -b:v 200k -preset medium -tune animation '
            f'-c:a copy "{output_file}"'
        )

        self.execute_command(ffmpeg_command, "Encoding 720p version of the final video")

    def move_files_to_brand_code_folder(self, brand_code, artist, title, output_files):
        self.logger.info(f"Moving files to new brand-prefixed directory...")

        self.new_brand_code_dir = f"{brand_code} - {artist} - {title}"
        self.new_brand_code_dir_path = os.path.join(self.organised_dir, self.new_brand_code_dir)

        self.prompt_user_confirmation_or_raise_exception(
            f"Move files to new brand-prefixed directory {self.new_brand_code_dir_path} and delete current dir?",
            "Refusing to move files without user confirmation of move.",
            allow_empty=True,
        )

        orig_dir = os.getcwd()
        os.chdir(os.path.dirname(orig_dir))
        self.logger.info(f"Changed dir to parent directory: {os.getcwd()}")

        if self.dry_run:
            self.logger.info(f"DRY RUN: Would move original directory {orig_dir} to: {self.new_brand_code_dir_path}")
        else:
            os.rename(orig_dir, self.new_brand_code_dir_path)

    def copy_final_files_to_public_share_dirs(self, brand_code, base_name, output_files):
        self.logger.info(f"Copying final MP4, 720p MP4, and ZIP to public share directory...")

        # Validate public_share_dir is a valid folder with MP4, MP4-720p, and CDG subdirectories
        if not os.path.isdir(self.public_share_dir):
            raise Exception(f"Public share directory does not exist: {self.public_share_dir}")

        if not os.path.isdir(os.path.join(self.public_share_dir, "MP4")):
            raise Exception(f"Public share directory does not contain MP4 subdirectory: {self.public_share_dir}")

        if not os.path.isdir(os.path.join(self.public_share_dir, "MP4-720p")):
            raise Exception(f"Public share directory does not contain MP4-720p subdirectory: {self.public_share_dir}")

        if not os.path.isdir(os.path.join(self.public_share_dir, "CDG")):
            raise Exception(f"Public share directory does not contain CDG subdirectory: {self.public_share_dir}")

        if brand_code is None:
            raise Exception(f"New track prefix was not set, refusing to copy to public share directory")

        dest_mp4_dir = os.path.join(self.public_share_dir, "MP4")
        dest_720p_dir = os.path.join(self.public_share_dir, "MP4-720p")
        dest_cdg_dir = os.path.join(self.public_share_dir, "CDG")
        os.makedirs(dest_mp4_dir, exist_ok=True)
        os.makedirs(dest_720p_dir, exist_ok=True)
        os.makedirs(dest_cdg_dir, exist_ok=True)

        dest_mp4_file = os.path.join(dest_mp4_dir, f"{brand_code} - {base_name}.mp4")
        dest_720p_mp4_file = os.path.join(dest_720p_dir, f"{brand_code} - {base_name}.mp4")
        dest_zip_file = os.path.join(dest_cdg_dir, f"{brand_code} - {base_name}.zip")

        if self.dry_run:
            self.logger.info(
                f"DRY RUN: Would copy final MP4, 720p MP4, and ZIP to {dest_mp4_file}, {dest_720p_mp4_file}, and {dest_zip_file}"
            )
        else:
            shutil.copy2(output_files["final_karaoke_mp4"], dest_mp4_file)
            shutil.copy2(output_files["final_karaoke_720p_mp4"], dest_720p_mp4_file)
            shutil.copy2(output_files["final_karaoke_cdg_zip"], dest_zip_file)
            self.logger.info(f"Copied final files to public share directory")

    def sync_public_share_dir_to_rclone_destination(self):
        self.logger.info(f"Syncing public share directory to rclone destination...")

        # Delete .DS_Store files recursively before syncing
        for root, dirs, files in os.walk(self.public_share_dir):
            for file in files:
                if file == ".DS_Store":
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    self.logger.info(f"Deleted .DS_Store file: {file_path}")

        rclone_cmd = f"rclone sync -v '{self.public_share_dir}' '{self.rclone_destination}'"
        self.execute_command(rclone_cmd, "Syncing with cloud destination")

    def post_discord_notification(self):
        self.logger.info(f"Posting Discord notification...")

        if self.skip_notifications:
            self.logger.info(f"Skipping Discord notification as video was previously uploaded to YouTube")
            return

        if self.dry_run:
            self.logger.info(
                f"DRY RUN: Would post Discord notification for youtube URL {self.youtube_url} using webhook URL: {self.discord_webhook_url}"
            )
        else:
            discord_message = f"New upload: {self.youtube_url}"
            self.post_discord_message(discord_message, self.discord_webhook_url)

    def generate_organised_folder_sharing_link(self):
        self.logger.info(f"Getting Organised Folder sharing link for new brand code directory...")

        rclone_dest = f"{self.organised_dir_rclone_root}/{self.new_brand_code_dir}"
        rclone_link_cmd = f"rclone link {shlex.quote(rclone_dest)}"

        if self.dry_run:
            self.logger.info(f"DRY RUN: Would get sharing link with: {rclone_link_cmd}")
            return "https://file-sharing-service.com/example"

        # Add a 5-second delay to allow dropbox to index the folder before generating a link
        self.logger.info("Waiting 5 seconds before generating link...")
        time.sleep(5)

        try:
            self.logger.info(f"Running command: {rclone_link_cmd}")
            result = subprocess.run(rclone_link_cmd, shell=True, check=True, capture_output=True, text=True)
            self.brand_code_dir_sharing_link = result.stdout.strip()
            self.logger.info(f"Got organised folder sharing link: {self.brand_code_dir_sharing_link}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to get organised folder sharing link. Exit code: {e.returncode}")
            self.logger.error(f"Command output (stdout): {e.stdout}")
            self.logger.error(f"Command output (stderr): {e.stderr}")
            self.logger.error(f"Full exception: {e}")

    def execute_optional_features(self, artist, title, base_name, input_files, output_files):
        self.logger.info(f"Executing optional features...")

        if self.youtube_upload_enabled:
            try:
                self.upload_final_mp4_to_youtube_with_title_thumbnail(artist, title, input_files, output_files)
            except Exception as e:
                self.logger.error(f"Failed to upload video to YouTube: {e}")
                print("Please manually upload the video to YouTube.")
                print()
                self.youtube_video_id = input("Enter the manually uploaded YouTube video ID: ").strip()
                self.youtube_url = f"{self.youtube_url_prefix}{self.youtube_video_id}"
                self.logger.info(f"Using manually provided YouTube video ID: {self.youtube_video_id}")

            if self.discord_notication_enabled:
                self.post_discord_notification()

        if self.folder_organisation_enabled:
            self.brand_code = self.get_next_brand_code()

            if self.public_share_copy_enabled:
                self.copy_final_files_to_public_share_dirs(self.brand_code, base_name, output_files)

            if self.public_share_rclone_enabled:
                self.sync_public_share_dir_to_rclone_destination()

            self.move_files_to_brand_code_folder(self.brand_code, artist, title, output_files)

            self.generate_organised_folder_sharing_link()

    def authenticate_gmail(self):
        """Authenticate and return a Gmail service object."""
        creds = None
        gmail_token_file = "/tmp/karaoke-finalise-gmail-token.pickle"

        if os.path.exists(gmail_token_file):
            with open(gmail_token_file, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.youtube_client_secrets_file, ["https://www.googleapis.com/auth/gmail.compose"]
                )
                creds = flow.run_local_server(port=0)
            with open(gmail_token_file, "wb") as token:
                pickle.dump(creds, token)

        return build("gmail", "v1", credentials=creds)

    def draft_completion_email(self, artist, title, youtube_url, dropbox_url):
        if not self.email_template_file:
            self.logger.info("Email template file not provided, skipping email draft creation.")
            return

        with open(self.email_template_file, "r") as f:
            template = f.read()

        email_body = template.format(youtube_url=youtube_url, dropbox_url=dropbox_url)

        subject = f"{self.brand_code}: {artist} - {title}"

        if self.dry_run:
            self.logger.info(f"DRY RUN: Would create email draft with subject: {subject}")
            self.logger.info(f"DRY RUN: Email body:\n{email_body}")
        else:
            if not self.gmail_service:
                self.gmail_service = self.authenticate_gmail()

            message = MIMEText(email_body)
            message["subject"] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            draft = self.gmail_service.users().drafts().create(userId="me", body={"message": {"raw": raw_message}}).execute()
            self.logger.info(f"Email draft created with ID: {draft['id']}")

    def test_email_template(self):
        if not self.email_template_file:
            self.logger.error("Email template file not provided. Use --email_template_file to specify the file path.")
            return

        fake_artist = "Test Artist"
        fake_title = "Test Song"
        fake_youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        fake_dropbox_url = "https://www.dropbox.com/sh/fake/folder/link"
        fake_brand_code = "TEST-0001"

        self.brand_code = fake_brand_code
        self.draft_completion_email(fake_artist, fake_title, fake_youtube_url, fake_dropbox_url)

        self.logger.info("Email template test complete. Check your Gmail drafts for the test email.")

    def process(self):
        if self.dry_run:
            self.logger.warning("Dry run enabled. No actions will be performed.")

        # Check required input files and parameters exist, get user to confirm features before proceeding
        self.validate_input_parameters_for_features()

        with_vocals_file = self.find_with_vocals_file()
        base_name, artist, title = self.get_names_from_withvocals(with_vocals_file)

        instrumental_audio_file = self.choose_instrumental_audio_file(base_name)

        input_files = self.check_input_files_exist(base_name, with_vocals_file, instrumental_audio_file)
        output_files = self.prepare_output_filenames(base_name)

        if self.enable_cdg:
            self.create_cdg_zip_file(input_files, output_files, artist, title)

        if self.enable_txt:
            self.create_txt_zip_file(input_files, output_files)

        self.remux_and_encode_output_video_files(with_vocals_file, input_files, output_files)
        self.encode_720p_version(output_files["final_karaoke_mp4"], output_files["final_karaoke_720p_mp4"])

        self.execute_optional_features(artist, title, base_name, input_files, output_files)

        result = {
            "artist": artist,
            "title": title,
            "video_with_vocals": output_files["with_vocals_mp4"],
            "video_with_instrumental": output_files["karaoke_mov"],
            "final_video": output_files["final_karaoke_mp4"],
            "final_video_720p": output_files["final_karaoke_720p_mp4"],
            "youtube_url": self.youtube_url,
            "brand_code": self.brand_code,
            "new_brand_code_dir_path": self.new_brand_code_dir_path,
            "brand_code_dir_sharing_link": self.brand_code_dir_sharing_link,
        }

        if self.enable_cdg:
            result["final_karaoke_cdg_zip"] = output_files["final_karaoke_cdg_zip"]

        if self.enable_txt:
            result["final_karaoke_txt_zip"] = output_files["final_karaoke_txt_zip"]

        if self.email_template_file:
            self.draft_completion_email(artist, title, result["youtube_url"], result["brand_code_dir_sharing_link"])

        return result
