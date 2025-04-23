import logging
import os


class UserInterface:
    def __init__(self, logger=None, non_interactive=False):
        self.logger = logger or logging.getLogger(__name__)
        self.non_interactive = non_interactive

    def prompt_user_confirmation_or_raise_exception(self, prompt_message, exit_message, allow_empty=False):
        if self.non_interactive:
            self.logger.info(f"Non-interactive mode, automatically confirming: {prompt_message}")
            return True

        if not self.prompt_user_bool(prompt_message, allow_empty=allow_empty):
            self.logger.error(exit_message)
            raise Exception(exit_message)

    def prompt_user_bool(self, prompt_message, allow_empty=False):
        if self.non_interactive:
            self.logger.info(f"Non-interactive mode, automatically answering yes to: {prompt_message}")
            return True

        options_string = "[y]/n" if allow_empty else "y/[n]"
        accept_responses = ["y", "yes"]
        if allow_empty:
            accept_responses.append("")

        print()
        response = input(f"{prompt_message} {options_string} ").strip().lower()
        return response in accept_responses

    def validate_input_parameters_for_features(self, youtube_client_secrets_file=None, youtube_description_file=None, 
                                               discord_webhook_url=None, brand_prefix=None, organised_dir=None, 
                                               public_share_dir=None, rclone_destination=None, enable_cdg=False, 
                                               enable_txt=False):
        self.logger.info(f"Validating input parameters for enabled features...")

        current_directory = os.getcwd()
        self.logger.info(f"Current directory to process: {current_directory}")

        youtube_upload_enabled = False
        discord_notication_enabled = False
        folder_organisation_enabled = False
        public_share_copy_enabled = False
        public_share_rclone_enabled = False

        # Enable youtube upload if client secrets file is provided and is valid JSON
        if youtube_client_secrets_file is not None and youtube_description_file is not None:
            if not os.path.isfile(youtube_client_secrets_file):
                raise Exception(f"YouTube client secrets file does not exist: {youtube_client_secrets_file}")

            if not os.path.isfile(youtube_description_file):
                raise Exception(f"YouTube description file does not exist: {youtube_description_file}")

            # Test parsing the file as JSON to check it's valid
            try:
                with open(youtube_client_secrets_file, "r") as f:
                    import json
                    json.load(f)
            except json.JSONDecodeError as e:
                raise Exception(f"YouTube client secrets file is not valid JSON: {youtube_client_secrets_file}") from e

            self.logger.debug(f"YouTube upload checks passed, enabling YouTube upload")
            youtube_upload_enabled = True

        # Enable discord notifications if webhook URL is provided and is valid URL
        if discord_webhook_url is not None:
            if not discord_webhook_url.startswith("https://discord.com/api/webhooks/"):
                raise Exception(f"Discord webhook URL is not valid: {discord_webhook_url}")

            self.logger.debug(f"Discord webhook URL checks passed, enabling Discord notifications")
            discord_notication_enabled = True

        # Enable folder organisation if brand prefix and target directory are provided and target directory is valid
        if brand_prefix is not None and organised_dir is not None:
            if not os.path.isdir(organised_dir):
                raise Exception(f"Target directory does not exist: {organised_dir}")

            self.logger.debug(f"Brand prefix and target directory provided, enabling folder organisation")
            folder_organisation_enabled = True

        # Enable public share copy if public share directory is provided and is valid directory with MP4 and CDG subdirectories
        if public_share_dir is not None:
            if not os.path.isdir(public_share_dir):
                raise Exception(f"Public share directory does not exist: {public_share_dir}")

            if not os.path.isdir(os.path.join(public_share_dir, "MP4")):
                raise Exception(f"Public share directory does not contain MP4 subdirectory: {public_share_dir}")

            if not os.path.isdir(os.path.join(public_share_dir, "CDG")):
                raise Exception(f"Public share directory does not contain CDG subdirectory: {public_share_dir}")

            self.logger.debug(f"Public share directory checks passed, enabling public share copy")
            public_share_copy_enabled = True

        # Enable public share rclone if rclone destination is provided
        if rclone_destination is not None:
            self.logger.debug(f"Rclone destination provided, enabling rclone sync")
            public_share_rclone_enabled = True

        # Tell user which features are enabled, prompt them to confirm before proceeding
        self.logger.info(f"Enabled features:")
        self.logger.info(f" CDG ZIP creation: {enable_cdg}")
        self.logger.info(f" TXT ZIP creation: {enable_txt}")
        self.logger.info(f" YouTube upload: {youtube_upload_enabled}")
        self.logger.info(f" Discord notifications: {discord_notication_enabled}")
        self.logger.info(f" Folder organisation: {folder_organisation_enabled}")
        self.logger.info(f" Public share copy: {public_share_copy_enabled}")
        self.logger.info(f" Public share rclone: {public_share_rclone_enabled}")

        self.prompt_user_confirmation_or_raise_exception(
            f"Confirm features enabled log messages above match your expectations for finalisation?",
            "Refusing to proceed without user confirmation they're happy with enabled features.",
            allow_empty=True,
        )
        
        return {
            "youtube_upload_enabled": youtube_upload_enabled,
            "discord_notication_enabled": discord_notication_enabled,
            "folder_organisation_enabled": folder_organisation_enabled,
            "public_share_copy_enabled": public_share_copy_enabled,
            "public_share_rclone_enabled": public_share_rclone_enabled
        } 