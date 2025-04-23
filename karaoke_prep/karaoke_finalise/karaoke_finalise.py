import os
import sys
import logging
from karaoke_prep.karaoke_finalise.file_manager import FileManager
from karaoke_prep.karaoke_finalise.media_processor import MediaProcessor
from karaoke_prep.karaoke_finalise.user_interface import UserInterface
from karaoke_prep.karaoke_finalise.youtube_manager import YouTubeManager
from karaoke_prep.karaoke_finalise.format_generator import FormatGenerator
from karaoke_prep.karaoke_finalise.notifier import Notifier
from karaoke_prep.karaoke_finalise.cloud_manager import CloudManager


class KaraokeFinalise:
    def __init__(
        self,
        logger=None,
        log_level=logging.DEBUG,
        log_formatter=None,
        dry_run=False,
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
        email_template_file=None,
        cdg_styles=None,
        keep_brand_code=False,
        non_interactive=False,
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

        self.logger.debug(
            f"KaraokeFinalise instantiating, dry_run: {dry_run}, brand_prefix: {brand_prefix}, organised_dir: {organised_dir}, public_share_dir: {public_share_dir}, rclone_destination: {rclone_destination}"
        )

        self.dry_run = dry_run
        self.instrumental_format = instrumental_format
        self.non_interactive = non_interactive

        self.brand_prefix = brand_prefix
        self.organised_dir = organised_dir
        self.organised_dir_rclone_root = organised_dir_rclone_root
        self.public_share_dir = public_share_dir
        self.youtube_client_secrets_file = youtube_client_secrets_file
        self.youtube_description_file = youtube_description_file
        self.rclone_destination = rclone_destination
        self.discord_webhook_url = discord_webhook_url
        self.email_template_file = email_template_file
        self.enable_cdg = enable_cdg
        self.enable_txt = enable_txt
        self.cdg_styles = cdg_styles
        self.keep_brand_code = keep_brand_code

        # Initialize component managers
        self.user_interface = UserInterface(logger=self.logger, non_interactive=non_interactive)
        self.file_manager = FileManager(
            logger=self.logger, 
            dry_run=dry_run, 
            brand_prefix=brand_prefix, 
            organised_dir=organised_dir, 
            public_share_dir=public_share_dir,
            keep_brand_code=keep_brand_code
        )
        self.media_processor = MediaProcessor(
            logger=self.logger, 
            dry_run=dry_run, 
            log_level=log_level,
            non_interactive=non_interactive
        )
        self.youtube_manager = YouTubeManager(
            logger=self.logger, 
            dry_run=dry_run, 
            youtube_client_secrets_file=youtube_client_secrets_file,
            youtube_description_file=youtube_description_file,
            non_interactive=non_interactive
        )
        self.format_generator = FormatGenerator(
            logger=self.logger, 
            dry_run=dry_run, 
            cdg_styles=cdg_styles
        )
        self.notifier = Notifier(
            logger=self.logger, 
            dry_run=dry_run, 
            discord_webhook_url=discord_webhook_url,
            email_template_file=email_template_file,
            youtube_client_secrets_file=youtube_client_secrets_file
        )
        self.cloud_manager = CloudManager(
            logger=self.logger, 
            dry_run=dry_run, 
            public_share_dir=public_share_dir,
            rclone_destination=rclone_destination,
            organised_dir_rclone_root=organised_dir_rclone_root
        )

        # Access suffixes from FileManager
        self.suffixes = self.file_manager.suffixes

        # Feature flags
        self.youtube_upload_enabled = False
        self.discord_notication_enabled = False
        self.folder_organisation_enabled = False
        self.public_share_copy_enabled = False
        self.public_share_rclone_enabled = False

        # State variables
        self.youtube_url = None
        self.brand_code = None
        self.new_brand_code_dir = None
        self.new_brand_code_dir_path = None
        self.brand_code_dir_sharing_link = None

    def validate_input_parameters_for_features(self):
        features = self.user_interface.validate_input_parameters_for_features(
            youtube_client_secrets_file=self.youtube_client_secrets_file,
            youtube_description_file=self.youtube_description_file,
            discord_webhook_url=self.discord_webhook_url,
            brand_prefix=self.brand_prefix,
            organised_dir=self.organised_dir,
            public_share_dir=self.public_share_dir,
            rclone_destination=self.rclone_destination,
            enable_cdg=self.enable_cdg,
            enable_txt=self.enable_txt
        )
        
        # Set feature flags
        self.youtube_upload_enabled = features["youtube_upload_enabled"]
        self.discord_notication_enabled = features["discord_notication_enabled"]
        self.folder_organisation_enabled = features["folder_organisation_enabled"]
        self.public_share_copy_enabled = features["public_share_copy_enabled"]
        self.public_share_rclone_enabled = features["public_share_rclone_enabled"]

    def execute_optional_features(self, artist, title, base_name, input_files, output_files, replace_existing=False):
        self.logger.info(f"Executing optional features...")

        if self.youtube_upload_enabled:
            try:
                self.youtube_manager.upload_final_mp4_to_youtube_with_title_thumbnail(artist, title, input_files, output_files, replace_existing)
                self.youtube_url = self.youtube_manager.youtube_url
            except Exception as e:
                self.logger.error(f"Failed to upload video to YouTube: {e}")
                print("Please manually upload the video to YouTube.")
                print()
                youtube_video_id = input("Enter the manually uploaded YouTube video ID: ").strip()
                self.youtube_url = f"{self.youtube_manager.youtube_url_prefix}{youtube_video_id}"
                self.logger.info(f"Using manually provided YouTube video ID: {youtube_video_id}")

            if self.discord_notication_enabled:
                self.notifier.post_discord_notification(
                    self.youtube_url, 
                    skip_notifications=self.youtube_manager.skip_notifications
                )

        if self.folder_organisation_enabled:
            if self.keep_brand_code:
                self.brand_code = self.file_manager.get_existing_brand_code()
                self.new_brand_code_dir = os.path.basename(os.getcwd())
                self.new_brand_code_dir_path = os.getcwd()
            else:
                self.brand_code = self.file_manager.get_next_brand_code()
                self.new_brand_code_dir, self.new_brand_code_dir_path = self.file_manager.move_files_to_brand_code_folder(
                    self.brand_code, artist, title, output_files
                )

            if self.public_share_copy_enabled:
                self.file_manager.copy_final_files_to_public_share_dirs(self.brand_code, base_name, output_files)

            if self.public_share_rclone_enabled:
                self.cloud_manager.sync_public_share_dir_to_rclone_destination()

            self.brand_code_dir_sharing_link = self.cloud_manager.generate_organised_folder_sharing_link(self.new_brand_code_dir)

    def test_email_template(self):
        """Convenience method to test the email template"""
        self.notifier.test_email_template()

    def process(self, replace_existing=False):
        if self.dry_run:
            self.logger.warning("Dry run enabled. No actions will be performed.")

        # Check required input files and parameters exist, get user to confirm features before proceeding
        self.validate_input_parameters_for_features()

        with_vocals_file = self.file_manager.find_with_vocals_file(user_interface=self.user_interface)
        base_name, artist, title = self.file_manager.get_names_from_withvocals(with_vocals_file)

        instrumental_audio_file = self.file_manager.choose_instrumental_audio_file(base_name, non_interactive=self.non_interactive)

        input_files = self.file_manager.check_input_files_exist(
            base_name, with_vocals_file, instrumental_audio_file, 
            enable_cdg=self.enable_cdg, enable_txt=self.enable_txt
        )
        output_files = self.file_manager.prepare_output_filenames(
            base_name, enable_cdg=self.enable_cdg, enable_txt=self.enable_txt
        )

        if self.enable_cdg:
            self.format_generator.create_cdg_zip_file(input_files, output_files, artist, title, user_interface=self.user_interface)

        if self.enable_txt:
            self.format_generator.create_txt_zip_file(input_files, output_files, user_interface=self.user_interface)

        self.media_processor.remux_and_encode_output_video_files(
            with_vocals_file, input_files, output_files, user_interface=self.user_interface
        )

        self.execute_optional_features(artist, title, base_name, input_files, output_files, replace_existing)

        if self.email_template_file:
            self.notifier.draft_completion_email(
                artist, title, self.youtube_url, self.brand_code_dir_sharing_link, self.brand_code
            )

        result = {
            "artist": artist,
            "title": title,
            "video_with_vocals": output_files["with_vocals_mp4"],
            "video_with_instrumental": output_files["karaoke_mp4"],
            "final_video": output_files["final_karaoke_lossless_mp4"],
            "final_video_mkv": output_files["final_karaoke_lossless_mkv"],
            "final_video_lossy": output_files["final_karaoke_lossy_mp4"],
            "final_video_720p": output_files["final_karaoke_lossy_720p_mp4"],
            "youtube_url": self.youtube_url,
            "brand_code": self.brand_code,
            "new_brand_code_dir_path": self.new_brand_code_dir_path,
            "brand_code_dir_sharing_link": self.brand_code_dir_sharing_link,
        }

        if self.enable_cdg:
            result["final_karaoke_cdg_zip"] = output_files["final_karaoke_cdg_zip"]

        if self.enable_txt:
            result["final_karaoke_txt_zip"] = output_files["final_karaoke_txt_zip"]

        return result