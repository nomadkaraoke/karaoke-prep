"""
CDG file generation functionality for the distribution service.
"""

import os
import zipfile
import logging
from typing import Optional, Dict, Any, Tuple

from lyrics_transcriber.output.cdg import CDGGenerator as LyricsTranscriberCDGGenerator

from karaoke_gen.core.project import ProjectConfig
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import DistributionError


class CDGGenerator:
    """
    Class for handling CDG file generation.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the CDG generator.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
    
    def create_cdg_zip_file(self, track: Track) -> Track:
        """
        Create a CDG zip file for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated CDG zip file information
            
        Raises:
            DistributionError: If creating the CDG zip file fails
        """
        self.logger.info(f"Creating CDG and MP3 files, then zipping them...")
        
        if not self.config.enable_cdg:
            self.logger.warning("CDG generation not enabled, skipping")
            return track
        
        if not track.processed_lyrics:
            self.logger.warning("No processed lyrics available, cannot create CDG file")
            return track
        
        if not track.instrumental:
            self.logger.warning("No instrumental audio available, cannot create CDG file")
            return track
        
        # Determine the output file paths
        cdg_zip_file = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke CDG).zip")
        cdg_file = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).cdg")
        mp3_file = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).mp3")
        lrc_file = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).lrc")
        
        # Check if CDG file already exists, if so, ask user to overwrite or skip
        if os.path.isfile(cdg_zip_file):
            if self.config.non_interactive:
                self.logger.info(f"Non-interactive mode, automatically overwriting existing CDG ZIP file: {cdg_zip_file}")
            else:
                from karaoke_gen.utils.validation import prompt_user_bool
                if not prompt_user_bool(
                    f"Found existing CDG ZIP file: {cdg_zip_file}. Overwrite (y) or skip (n)?",
                ):
                    self.logger.info(f"Skipping CDG ZIP file creation, existing file will be used.")
                    track.final_karaoke_cdg_zip = cdg_zip_file
                    return track
        
        # Check if individual MP3 and CDG files already exist
        if os.path.isfile(mp3_file) and os.path.isfile(cdg_file):
            self.logger.info(f"Found existing MP3 and CDG files, creating ZIP file directly")
            
            if self.config.dry_run:
                self.logger.info(f"DRY RUN: Would create ZIP file from existing MP3 and CDG files")
                track.final_karaoke_cdg_zip = cdg_zip_file
                return track
            
            try:
                with zipfile.ZipFile(cdg_zip_file, "w") as zipf:
                    zipf.write(mp3_file, os.path.basename(mp3_file))
                    zipf.write(cdg_file, os.path.basename(cdg_file))
                
                self.logger.info(f"Created CDG ZIP file: {cdg_zip_file}")
                track.final_karaoke_cdg_zip = cdg_zip_file
                return track
            
            except Exception as e:
                self.logger.error(f"Failed to create CDG ZIP file: {str(e)}")
                raise DistributionError(f"Failed to create CDG ZIP file: {str(e)}")
        
        # Generate CDG and MP3 files if they don't exist
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would generate CDG and MP3 files")
            track.final_karaoke_cdg_zip = cdg_zip_file
            return track
        
        try:
            self.logger.info(f"Generating CDG and MP3 files")
            
            if not self.config.cdg_styles:
                raise DistributionError("CDG styles configuration is required when enable_cdg is True")
            
            # Create the LRC file if it doesn't exist
            if not os.path.isfile(lrc_file) and track.processed_lyrics:
                with open(lrc_file, "w", encoding="utf-8") as f:
                    f.write(track.processed_lyrics)
            
            # Use the CDGGenerator from lyrics_transcriber to generate the CDG file
            generator = LyricsTranscriberCDGGenerator(output_dir=track.track_output_dir, logger=self.logger)
            
            cdg_file_generated, mp3_file_generated, zip_file_generated = generator.generate_cdg_from_lrc(
                lrc_file=lrc_file,
                audio_file=track.instrumental,
                title=track.title,
                artist=track.artist,
                cdg_styles=self.config.cdg_styles,
            )
            
            # Rename the generated ZIP file to match our expected naming convention
            if os.path.isfile(zip_file_generated) and zip_file_generated != cdg_zip_file:
                os.rename(zip_file_generated, cdg_zip_file)
                self.logger.info(f"Renamed CDG ZIP file from {zip_file_generated} to {cdg_zip_file}")
            
            # Verify the CDG ZIP file was created
            if not os.path.isfile(cdg_zip_file):
                self.logger.error(f"Failed to find any CDG ZIP file. Listing directory contents:")
                for file in os.listdir(track.track_output_dir):
                    self.logger.error(f" - {file}")
                raise DistributionError(f"Failed to create CDG ZIP file: {cdg_zip_file}")
            
            self.logger.info(f"CDG ZIP file created: {cdg_zip_file}")
            
            # Extract the CDG ZIP file to get the individual files
            self.logger.info(f"Extracting CDG ZIP file: {cdg_zip_file}")
            with zipfile.ZipFile(cdg_zip_file, "r") as zip_ref:
                zip_ref.extractall(track.track_output_dir)
            
            # Verify the MP3 file was extracted
            if os.path.isfile(mp3_file):
                self.logger.info(f"Found extracted MP3 file: {mp3_file}")
            else:
                self.logger.error("Failed to find extracted MP3 file")
                raise DistributionError("Failed to extract MP3 file from CDG ZIP")
            
            track.final_karaoke_cdg_zip = cdg_zip_file
            return track
        
        except Exception as e:
            self.logger.error(f"Failed to create CDG ZIP file: {str(e)}")
            raise DistributionError(f"Failed to create CDG ZIP file: {str(e)}") 