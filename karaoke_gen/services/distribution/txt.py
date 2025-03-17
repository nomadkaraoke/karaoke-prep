"""
TXT file generation functionality for the distribution service.
"""

import os
import zipfile
import logging
from typing import Optional, Dict, Any

from lyrics_converter import LyricsConverter

from karaoke_gen.core.project import ProjectConfig
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import DistributionError


class TXTGenerator:
    """
    Class for handling TXT file generation.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the TXT generator.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
    
    def create_txt_zip_file(self, track: Track) -> Track:
        """
        Create a TXT zip file for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated TXT zip file information
            
        Raises:
            DistributionError: If creating the TXT zip file fails
        """
        self.logger.info(f"Creating TXT ZIP file...")
        
        if not self.config.enable_txt:
            self.logger.warning("TXT generation not enabled, skipping")
            return track
        
        if not track.processed_lyrics:
            self.logger.warning("No processed lyrics available, cannot create TXT file")
            return track
        
        # Determine the output file paths
        txt_zip_file = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke TXT).zip")
        txt_file = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).txt")
        mp3_file = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).mp3")
        lrc_file = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).lrc")
        
        # Check if TXT file already exists, if so, ask user to overwrite or skip
        if os.path.isfile(txt_zip_file):
            if self.config.non_interactive:
                self.logger.info(f"Non-interactive mode, automatically overwriting existing TXT ZIP file: {txt_zip_file}")
            else:
                from karaoke_gen.utils.validation import prompt_user_bool
                if not prompt_user_bool(
                    f"Found existing TXT ZIP file: {txt_zip_file}. Overwrite (y) or skip (n)?",
                ):
                    self.logger.info(f"Skipping TXT ZIP file creation, existing file will be used.")
                    track.final_karaoke_txt_zip = txt_zip_file
                    return track
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would create TXT ZIP file: {txt_zip_file}")
            track.final_karaoke_txt_zip = txt_zip_file
            return track
        
        try:
            # Create the LRC file if it doesn't exist
            if not os.path.isfile(lrc_file) and track.processed_lyrics:
                with open(lrc_file, "w", encoding="utf-8") as f:
                    f.write(track.processed_lyrics)
            
            # Convert LRC to TXT format
            self.logger.info(f"Running karaoke-converter to convert MidiCo LRC file {lrc_file} to TXT format")
            txt_converter = LyricsConverter(output_format="txt", filepath=lrc_file)
            converted_txt = txt_converter.convert_file()
            
            # Write the TXT file
            with open(txt_file, "w", encoding="utf-8") as txt_file_handle:
                txt_file_handle.write(converted_txt)
                self.logger.info(f"TXT file written: {txt_file}")
            
            # Ensure the MP3 file exists
            if not os.path.isfile(mp3_file):
                self.logger.warning(f"MP3 file not found: {mp3_file}, cannot create TXT ZIP file")
                return track
            
            # Create the ZIP file containing the MP3 and TXT files
            self.logger.info(f"Creating ZIP file containing {mp3_file} and {txt_file}")
            with zipfile.ZipFile(txt_zip_file, "w") as zipf:
                zipf.write(mp3_file, os.path.basename(mp3_file))
                zipf.write(txt_file, os.path.basename(txt_file))
            
            # Verify the TXT ZIP file was created
            if not os.path.isfile(txt_zip_file):
                raise DistributionError(f"Failed to create TXT ZIP file: {txt_zip_file}")
            
            self.logger.info(f"TXT ZIP file created: {txt_zip_file}")
            track.final_karaoke_txt_zip = txt_zip_file
            return track
        
        except Exception as e:
            self.logger.error(f"Failed to create TXT ZIP file: {str(e)}")
            raise DistributionError(f"Failed to create TXT ZIP file: {str(e)}") 