import os
import sys
import subprocess
import tempfile
import logging
import zipfile
import shutil
import re
import pickle
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload


class KaraokeFinalise:
    def __init__(
        self,
        log_level=logging.DEBUG,
        log_formatter=None,
        dry_run=False,
        force=False,
        model_name="UVR_MDXNET_KARA_2",
        instrumental_format="flac",
        brand_prefix=None,
        target_dir=None,
        public_share_dir=None,
        youtube_client_secrets_file=None,
        youtube_description_file=None,
        rclone_destination=None,
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
            f"KaraokeFinalise instantiating, dry_run: {dry_run}, model_name: {model_name}, force: {force}, brand_prefix: {brand_prefix}, target_dir: {target_dir}, public_share_dir: {public_share_dir}, rclone_destination: {rclone_destination}"
        )

        # Path to the Windows PyInstaller frozen bundled ffmpeg.exe, or the system-installed FFmpeg binary on Mac/Linux
        ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg.exe") if getattr(sys, "frozen", False) else "ffmpeg"

        self.ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"

        if self.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"

        self.dry_run = dry_run
        self.force = force
        self.model_name = model_name
        self.instrumental_format = instrumental_format

        self.brand_prefix = brand_prefix
        self.target_dir = target_dir
        self.public_share_dir = public_share_dir
        self.youtube_client_secrets_file = youtube_client_secrets_file
        self.youtube_description_file = youtube_description_file
        self.rclone_destination = rclone_destination

    def authenticate_youtube(self):
        """Authenticate and return a YouTube service object."""
        credentials = None
        pickle_file = "/tmp/karaoke-finalise-token.pickle"

        # Token file stores the user's access and refresh tokens.
        if os.path.exists(pickle_file):
            with open(pickle_file, "rb") as token:
                credentials = pickle.load(token)

        # If there are no valid credentials, let the user log in.
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.youtube_client_secrets_file, scopes=["https://www.googleapis.com/auth/youtube.upload"]
                )
                credentials = flow.run_local_server(port=0)  # This will open a browser for authentication

            # Save the credentials for the next run
            with open(pickle_file, "wb") as token:
                pickle.dump(credentials, token)

        return build("youtube", "v3", credentials=credentials)

    def upload_to_youtube(self, video_file_path, title, description, category_id, keywords):
        """Upload video to YouTube."""
        youtube = self.authenticate_youtube()

        body = {
            "snippet": {"title": title, "description": description, "tags": keywords, "categoryId": category_id},
            "status": {"privacyStatus": "public"},  # or 'private' or 'unlisted'
        }

        # Use MediaFileUpload to handle the video file
        media_file = MediaFileUpload(video_file_path, mimetype="video/mp4", resumable=True)

        # Call the API's videos.insert method to create and upload the video.
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media_file)
        response = request.execute()

        self.logger.info(f"Uploaded video to YouTube: {response.get('id')}")

    def get_next_sequence_number(self):
        """
        Calculate the next sequence number based on existing directories in the target_dir.
        Assumes directories are named with the format: BRAND-XXXX Artist - Title
        """
        max_num = 0
        pattern = re.compile(rf"^{re.escape(self.brand_prefix)}-(\d{{4}})")

        if not os.path.isdir(self.target_dir):
            self.logger.error(f"Target directory does not exist: {self.target_dir}")
            return None

        for dir_name in os.listdir(self.target_dir):
            match = pattern.match(dir_name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

        self.logger.info(f"Next sequence number for brand {self.brand_prefix} calculated as: {max_num + 1}")
        return max_num + 1

    def process(self):
        tracks = []

        if self.dry_run:
            self.logger.info("Dry run enabled. No actions will be performed.")

        self.logger.info(f"Searching for files in current directory ending with (With Vocals).mov")
        for with_vocals_file in filter(lambda f: " (With Vocals).mov" in f, os.listdir(".")):
            base_name = with_vocals_file.replace(" (With Vocals).mov", "")
            artist = base_name.split(" - ")[0]
            title = base_name.split(" - ")[1]

            # Input files which should already exist after karaoke-prep and manual production process
            title_file = f"{base_name} (Title).mov"
            instrumental_file = f"{base_name} (Instrumental {self.model_name}).{self.instrumental_format}"
            cdg_file = f"{base_name} (Karaoke).cdg"
            mp3_file = f"{base_name} (Karaoke).mp3"

            # Output files which will be created by this script
            karaoke_mov_file = f"{base_name} (Karaoke).mov"
            final_mp4_file = f"{base_name} (Final Karaoke).mp4"
            final_zip_file = f"{base_name} (Final Karaoke).zip"

            if os.path.isfile(karaoke_mov_file) and not self.force:
                self.logger.error(
                    f"Karaoke MOV file with instrumental audio already exists: {karaoke_mov_file}. Use --force parameter to override."
                )
                return []

            if os.path.isfile(final_mp4_file) and not self.force:
                self.logger.error(f"Final MP4 file already exists: {final_mp4_file}. Use --force parameter to override.")
                return []

            if not os.path.isfile(title_file):
                self.logger.error(f"Title file not found: {title_file}")
                return []

            if not os.path.isfile(with_vocals_file):
                self.logger.error(f"With Vocals file not found: {with_vocals_file}")
                return []

            if not os.path.isfile(instrumental_file):
                self.logger.error(f"Instrumental file not found: {instrumental_file}")
                return []

            if not os.path.isfile(cdg_file):
                self.logger.error(f"CDG file not found: {cdg_file}")
                return []

            if not os.path.isfile(mp3_file):
                self.logger.error(f"MP3 file not found: {mp3_file}")
                return []

            self.logger.info(
                f"All 5 input files (Title MOV, With Vocals MOV, Instrumental {self.instrumental_format}, CDG, MP3) found for {base_name}, beginning finalisation"
            )

            # Remux the synced video with the instrumental audio to produce an instrumental karaoke MOV file
            if not os.path.isfile(karaoke_mov_file):
                self.logger.info(f"Output [With Instrumental]: remuxing synced video with instrumental audio to: {karaoke_mov_file}")

                remux_ffmpeg_command = f'{self.ffmpeg_base_command} -an -i "{with_vocals_file}" -vn -i "{instrumental_file}" -c:v copy -c:a aac "{karaoke_mov_file}"'

                if self.dry_run:
                    self.logger.info(f"DRY RUN: Would run command: {remux_ffmpeg_command}")
                else:
                    self.logger.info(f"Running command: {remux_ffmpeg_command}")
                    os.system(remux_ffmpeg_command)

            # Join the title video and the karaoke video and reencode with fixed 30 FPS to produce the final MP4
            if not os.path.isfile(final_mp4_file):
                self.logger.info(f"Output [Final Karaoke]: joining title video and instrumental video to produce: {final_mp4_file}")

                with tempfile.NamedTemporaryFile(mode="w+", delete=False, dir="/tmp", suffix=".txt") as tmp_file_list:
                    tmp_file_list.write(f"file '{os.path.abspath(title_file)}'\n")
                    tmp_file_list.write(f"file '{os.path.abspath(karaoke_mov_file)}'\n")

                join_ffmpeg_command = f'{self.ffmpeg_base_command} -f concat -safe 0 -i "{tmp_file_list.name}" -vf settb=AVTB,setpts=N/30/TB,fps=30 "{final_mp4_file}"'

                if self.dry_run:
                    self.logger.info(f"DRY RUN: Would run command: {join_ffmpeg_command}")
                else:
                    self.logger.info(f"Running command: {join_ffmpeg_command}")
                    os.system(join_ffmpeg_command)
                    os.remove(tmp_file_list.name)

            # Create the ZIP file containing the MP3 and CDG files
            if not os.path.isfile(final_zip_file):
                if self.dry_run:
                    self.logger.info(f"DRY RUN: Would create ZIP file: {final_zip_file}")
                else:
                    self.logger.info(f"Creating ZIP file containing {mp3_file} and {cdg_file}")
                    with zipfile.ZipFile(final_zip_file, "w") as zipf:
                        zipf.write(mp3_file, os.path.basename(mp3_file))
                        zipf.write(cdg_file, os.path.basename(cdg_file))
                    self.logger.info(f"ZIP file created: {final_zip_file}")

            # Create new folder in target folder and move all files to it
            new_track_prefix = None
            new_dir_path = None
            if self.brand_prefix is not None and self.target_dir is not None:
                next_num = self.get_next_sequence_number()
                new_track_prefix = f"{self.brand_prefix}-{next_num:04d}"
                new_dir_name = f"{new_track_prefix} {artist} - {title}"
                new_dir_path = os.path.join(self.target_dir, new_dir_name)

                if self.dry_run:
                    self.logger.info(f"DRY RUN: Would create new folder and move files to: {new_dir_path}")
                else:
                    if not os.path.exists(new_dir_path):
                        os.makedirs(new_dir_path)

                    for file in os.listdir("."):
                        src_file = os.path.join(".", file)
                        dest_file = os.path.join(new_dir_path, file)
                        shutil.move(src_file, dest_file)

                    self.logger.info(f"Moved all files to: {new_dir_path}")
            else:
                self.logger.info("brand_prefix or target_dir not specified, skipping move")

            # Copy files to public share directory with brand prefix
            if self.public_share_dir is not None and new_track_prefix is not None and new_dir_path is not None:
                self.logger.info(f"public_share_dir specified, will rename and copy final files to public share directory")

                src_mp4_file = os.path.join(new_dir_path, final_mp4_file)
                src_zip_file = os.path.join(new_dir_path, final_zip_file)

                dest_mp4_file = os.path.join(self.public_share_dir, f"{new_track_prefix} {base_name} (Karaoke).mp4")
                dest_zip_file = os.path.join(self.public_share_dir, f"{new_track_prefix} {base_name} (Karaoke).zip")

                if self.dry_run:
                    self.logger.info(f"DRY RUN: Would copy {src_mp4_file} to {dest_mp4_file}")
                    self.logger.info(f"DRY RUN: Would copy {src_zip_file} to {dest_zip_file}")
                else:
                    shutil.copy2(src_mp4_file, dest_mp4_file)
                    shutil.copy2(src_zip_file, dest_zip_file)
                    self.logger.info(f"Final files copied to public share directory: {dest_mp4_file}, {dest_zip_file}")
            else:
                self.logger.info(f"public_share_dir or new_track_prefix not specified, skipping copy to shared dir")

            # Upload to YouTube
            if self.youtube_client_secrets_file is not None:
                src_mp4_file = os.path.join(new_dir_path, final_mp4_file)

                if self.dry_run:
                    self.logger.info(
                        f"DRY RUN: Would upload {src_mp4_file} to YouTube using client secrets file: {self.youtube_client_secrets_file}"
                    )
                else:
                    description = f"Karaoke version of {artist} - {title} created using karaoke-prep python package."
                    if self.youtube_description_file is not None:
                        with open(self.youtube_description_file, "r") as f:
                            description = f.read()

                    self.upload_to_youtube(
                        src_mp4_file,
                        f"{artist} - {title} (Karaoke)",
                        description,
                        "10",  # Category ID for Music
                        ["karaoke", "music", "singing", "instrumental", "lyrics", artist, title],
                    )
            else:
                self.logger.info(f"youtube_client_secrets_file not specified, skipping YouTube upload")

            # Sync with various cloud destinations using rclone
            if self.rclone_destination is not None and self.public_share_dir is not None:
                rclone_cmd = ["rclone", "sync", "-v", self.public_share_dir, self.rclone_destination]
                if self.dry_run:
                    self.logger.info(f"DRY RUN: Would sync {self.public_share_dir} to {self.rclone_destination} using rclone")
                else:
                    self.logger.info(f"Running command: {rclone_cmd}")
                    subprocess.run(rclone_cmd)
            else:
                self.logger.info(f"rclone_destination or public_share_dir not specified, skipping sync")

            # Add track to list of processed tracks now we've created all of the new output files
            tracks.append(
                {
                    "artist": artist,
                    "title": title,
                    "video_with_vocals": with_vocals_file,
                    "video_with_instrumental": karaoke_mov_file,
                    "final_video": final_mp4_file,
                    "final_zip": final_zip_file,
                }
            )

        return tracks
