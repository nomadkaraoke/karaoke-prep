"""
File organization functionality for the distribution service.
"""

import os
import re
import shutil
import subprocess
import time
import logging
import shlex
from typing import Optional, Dict, Any, List

from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import DistributionError


class FileOrganizer:
    """
    Class for handling file organization operations.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the file organizer.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
    
    def get_next_brand_code(self) -> str:
        """
        Calculate the next sequence number based on existing directories in the organised_dir.
        Assumes directories are named with the format: BRAND-XXXX Artist - Title
        
        Returns:
            The next brand code
            
        Raises:
            DistributionError: If the target directory does not exist
        """
        self.logger.info(f"Getting next brand code for prefix {self.config.brand_prefix}")
        
        if not self.config.brand_prefix or not self.config.organised_dir:
            self.logger.warning("Brand prefix or organised directory not set, cannot get next brand code")
            return None
        
        if not os.path.isdir(self.config.organised_dir):
            raise DistributionError(f"Target directory does not exist: {self.config.organised_dir}")
        
        max_num = 0
        pattern = re.compile(rf"^{re.escape(self.config.brand_prefix)}-(\d{{4}})")
        
        for dir_name in os.listdir(self.config.organised_dir):
            match = pattern.match(dir_name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)
        
        self.logger.info(f"Next sequence number for brand {self.config.brand_prefix} calculated as: {max_num + 1}")
        next_seq_number = max_num + 1
        
        return f"{self.config.brand_prefix}-{next_seq_number:04d}"
    
    def get_existing_brand_code(self, track: Track) -> str:
        """
        Extract brand code from current directory name.
        
        Args:
            track: The track to process
            
        Returns:
            The existing brand code
            
        Raises:
            DistributionError: If the current directory name does not match the expected format
        """
        self.logger.info("Getting existing brand code from current directory")
        
        if not self.config.brand_prefix:
            self.logger.warning("Brand prefix not set, cannot get existing brand code")
            return None
        
        current_dir = os.path.basename(track.track_output_dir)
        
        if " - " not in current_dir:
            raise DistributionError(f"Current directory '{current_dir}' does not match expected format 'BRAND-XXXX - Artist - Title'")
        
        brand_code = current_dir.split(" - ")[0]
        if not brand_code or "-" not in brand_code:
            raise DistributionError(f"Could not extract valid brand code from directory name '{current_dir}'")
        
        self.logger.info(f"Using existing brand code: {brand_code}")
        return brand_code
    
    def move_files_to_brand_code_folder(self, track: Track, brand_code: str) -> Track:
        """
        Move files to a brand code folder.
        
        Args:
            track: The track to process
            brand_code: The brand code to use
            
        Returns:
            The track with updated file paths
            
        Raises:
            DistributionError: If moving the files fails
        """
        self.logger.info(f"Moving files to new brand-prefixed directory...")
        
        if not brand_code:
            self.logger.warning("Brand code not set, cannot move files")
            return track
        
        new_brand_code_dir = f"{brand_code} - {track.artist} - {track.title}"
        new_brand_code_dir_path = os.path.join(self.config.organised_dir, new_brand_code_dir)
        
        # Store the new directory path in the track
        track.new_brand_code_dir_path = new_brand_code_dir_path
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would move original directory {track.track_output_dir} to: {new_brand_code_dir_path}")
            return track
        
        try:
            # Create the parent directory if it doesn't exist
            os.makedirs(os.path.dirname(new_brand_code_dir_path), exist_ok=True)
            
            # Move the directory
            shutil.move(track.track_output_dir, new_brand_code_dir_path)
            
            # Update the track's output directory
            track.track_output_dir = new_brand_code_dir_path
            
            # Update file paths
            if track.final_video:
                track.final_video = os.path.join(new_brand_code_dir_path, os.path.basename(track.final_video))
            
            if track.final_video_mkv:
                track.final_video_mkv = os.path.join(new_brand_code_dir_path, os.path.basename(track.final_video_mkv))
            
            if track.final_video_lossy:
                track.final_video_lossy = os.path.join(new_brand_code_dir_path, os.path.basename(track.final_video_lossy))
            
            if track.final_video_720p:
                track.final_video_720p = os.path.join(new_brand_code_dir_path, os.path.basename(track.final_video_720p))
            
            if track.final_karaoke_cdg_zip:
                track.final_karaoke_cdg_zip = os.path.join(new_brand_code_dir_path, os.path.basename(track.final_karaoke_cdg_zip))
            
            if track.final_karaoke_txt_zip:
                track.final_karaoke_txt_zip = os.path.join(new_brand_code_dir_path, os.path.basename(track.final_karaoke_txt_zip))
            
            return track
        
        except Exception as e:
            self.logger.error(f"Failed to move files to brand code folder: {str(e)}")
            raise DistributionError(f"Failed to move files to brand code folder: {str(e)}")
    
    def copy_final_files_to_public_share_dirs(self, track: Track, brand_code: str) -> Track:
        """
        Copy final files to public share directories.
        
        Args:
            track: The track to process
            brand_code: The brand code to use
            
        Returns:
            The track with updated file paths
            
        Raises:
            DistributionError: If copying the files fails
        """
        self.logger.info(f"Copying final MP4, 720p MP4, and ZIP to public share directory...")
        
        if not self.config.public_share_dir:
            self.logger.warning("Public share directory not set, cannot copy files")
            return track
        
        if not brand_code:
            raise DistributionError(f"Brand code not set, refusing to copy to public share directory")
        
        # Validate public_share_dir is a valid folder with MP4, MP4-720p, and CDG subdirectories
        if not os.path.isdir(self.config.public_share_dir):
            raise DistributionError(f"Public share directory does not exist: {self.config.public_share_dir}")
        
        dest_mp4_dir = os.path.join(self.config.public_share_dir, "MP4")
        dest_720p_dir = os.path.join(self.config.public_share_dir, "MP4-720p")
        dest_cdg_dir = os.path.join(self.config.public_share_dir, "CDG")
        
        # Create directories if they don't exist
        for dir_path in [dest_mp4_dir, dest_720p_dir, dest_cdg_dir]:
            if not os.path.isdir(dir_path):
                if self.config.dry_run:
                    self.logger.info(f"DRY RUN: Would create directory: {dir_path}")
                else:
                    os.makedirs(dir_path, exist_ok=True)
        
        # Prepare destination file paths
        dest_mp4_file = os.path.join(dest_mp4_dir, f"{brand_code} - {track.base_name}.mp4")
        dest_720p_mp4_file = os.path.join(dest_720p_dir, f"{brand_code} - {track.base_name}.mp4")
        dest_zip_file = os.path.join(dest_cdg_dir, f"{brand_code} - {track.base_name}.zip")
        
        if self.config.dry_run:
            self.logger.info(
                f"DRY RUN: Would copy final MP4, 720p MP4, and ZIP to {dest_mp4_file}, {dest_720p_mp4_file}, and {dest_zip_file}"
            )
            return track
        
        try:
            # Copy files
            if track.final_video_lossy and os.path.isfile(track.final_video_lossy):
                shutil.copy2(track.final_video_lossy, dest_mp4_file)
            
            if track.final_video_720p and os.path.isfile(track.final_video_720p):
                shutil.copy2(track.final_video_720p, dest_720p_mp4_file)
            
            if track.final_karaoke_cdg_zip and os.path.isfile(track.final_karaoke_cdg_zip):
                shutil.copy2(track.final_karaoke_cdg_zip, dest_zip_file)
            
            self.logger.info(f"Copied final files to public share directory")
            return track
        
        except Exception as e:
            self.logger.error(f"Failed to copy files to public share directory: {str(e)}")
            raise DistributionError(f"Failed to copy files to public share directory: {str(e)}")
    
    def sync_public_share_dir_to_rclone_destination(self) -> None:
        """
        Sync public share directory to rclone destination.
        
        Raises:
            DistributionError: If syncing fails
        """
        self.logger.info(f"Syncing public share directory to rclone destination...")
        
        if not self.config.rclone_destination or not self.config.public_share_dir:
            self.logger.warning("Rclone destination or public share directory not set, cannot sync")
            return
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would sync {self.config.public_share_dir} to {self.config.rclone_destination}")
            return
        
        try:
            # Delete .DS_Store files recursively before syncing
            for root, dirs, files in os.walk(self.config.public_share_dir):
                for file in files:
                    if file == ".DS_Store":
                        file_path = os.path.join(root, file)
                        os.remove(file_path)
                        self.logger.info(f"Deleted .DS_Store file: {file_path}")
            
            # Build the rclone command
            rclone_cmd = f"rclone sync -v '{self.config.public_share_dir}' '{self.config.rclone_destination}'"
            
            # Execute the command
            self.logger.info(f"Running command: {rclone_cmd}")
            process = subprocess.run(rclone_cmd, shell=True, check=True, capture_output=True, text=True)
            
            if process.returncode != 0:
                raise DistributionError(f"rclone sync failed: {process.stderr}")
            
            self.logger.info(f"Successfully synced public share directory to rclone destination")
        
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to sync to rclone destination. Exit code: {e.returncode}")
            self.logger.error(f"Command output (stdout): {e.stdout}")
            self.logger.error(f"Command output (stderr): {e.stderr}")
            raise DistributionError(f"Failed to sync to rclone destination: {e.stderr}")
        
        except Exception as e:
            self.logger.error(f"Failed to sync to rclone destination: {str(e)}")
            raise DistributionError(f"Failed to sync to rclone destination: {str(e)}")
    
    def generate_organised_folder_sharing_link(self, track: Track) -> Optional[str]:
        """
        Generate a sharing link for the organised folder.
        
        Args:
            track: The track to process
            
        Returns:
            The sharing link
            
        Raises:
            DistributionError: If generating the link fails
        """
        self.logger.info(f"Getting Organised Folder sharing link for new brand code directory...")
        
        if not self.config.organised_dir_rclone_root or not track.brand_code or not track.new_brand_code_dir_path:
            self.logger.warning("Organised directory rclone root, brand code, or new brand code directory path not set, cannot generate sharing link")
            return None
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would get sharing link for {track.new_brand_code_dir_path}")
            return "https://file-sharing-service.com/example"
        
        try:
            # Build the rclone destination path
            rclone_dest = f"{self.config.organised_dir_rclone_root}/{os.path.basename(track.new_brand_code_dir_path)}"
            rclone_link_cmd = f"rclone link {shlex.quote(rclone_dest)}"
            
            # Add a 5-second delay to allow the service to index the folder before generating a link
            self.logger.info("Waiting 5 seconds before generating link...")
            time.sleep(5)
            
            # Execute the command
            self.logger.info(f"Running command: {rclone_link_cmd}")
            result = subprocess.run(rclone_link_cmd, shell=True, check=True, capture_output=True, text=True)
            
            sharing_link = result.stdout.strip()
            self.logger.info(f"Got organised folder sharing link: {sharing_link}")
            
            return sharing_link
        
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to get organised folder sharing link. Exit code: {e.returncode}")
            self.logger.error(f"Command output (stdout): {e.stdout}")
            self.logger.error(f"Command output (stderr): {e.stderr}")
            raise DistributionError(f"Failed to get organised folder sharing link: {e.stderr}")
        
        except Exception as e:
            self.logger.error(f"Failed to get organised folder sharing link: {str(e)}")
            raise DistributionError(f"Failed to get organised folder sharing link: {str(e)}") 