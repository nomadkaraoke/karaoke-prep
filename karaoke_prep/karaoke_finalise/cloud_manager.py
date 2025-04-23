import os
import logging
import subprocess
import shlex
import time


class CloudManager:
    def __init__(self, logger=None, dry_run=False, public_share_dir=None, rclone_destination=None, organised_dir_rclone_root=None):
        self.logger = logger or logging.getLogger(__name__)
        self.dry_run = dry_run
        self.public_share_dir = public_share_dir
        self.rclone_destination = rclone_destination
        self.organised_dir_rclone_root = organised_dir_rclone_root

    def sync_public_share_dir_to_rclone_destination(self):
        self.logger.info(f"Syncing public share directory to rclone destination...")

        if not self.public_share_dir or not self.rclone_destination:
            self.logger.warning("Public share directory or rclone destination not provided, skipping sync")
            return

        # Delete .DS_Store files recursively before syncing
        for root, dirs, files in os.walk(self.public_share_dir):
            for file in files:
                if file == ".DS_Store":
                    file_path = os.path.join(root, file)
                    os.remove(file_path)
                    self.logger.info(f"Deleted .DS_Store file: {file_path}")

        rclone_cmd = f"rclone sync -v '{self.public_share_dir}' '{self.rclone_destination}'"
        
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would run command: {rclone_cmd}")
        else:
            self.logger.info(f"Running command: {rclone_cmd}")
            os.system(rclone_cmd)

    def generate_organised_folder_sharing_link(self, new_brand_code_dir):
        self.logger.info(f"Getting Organised Folder sharing link for new brand code directory...")

        if not self.organised_dir_rclone_root or not new_brand_code_dir:
            self.logger.warning("Organised dir rclone root or new brand code directory not provided, skipping link generation")
            return None

        rclone_dest = f"{self.organised_dir_rclone_root}/{new_brand_code_dir}"
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
            brand_code_dir_sharing_link = result.stdout.strip()
            self.logger.info(f"Got organised folder sharing link: {brand_code_dir_sharing_link}")
            return brand_code_dir_sharing_link
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to get organised folder sharing link. Exit code: {e.returncode}")
            self.logger.error(f"Command output (stdout): {e.stdout}")
            self.logger.error(f"Command output (stderr): {e.stderr}")
            self.logger.error(f"Full exception: {e}")
            return None