"""
Core processing functions for karaoke generation.

This module contains a wrapper around the existing KaraokePrep functionality
for serverless execution on Modal.
"""

import os
import sys
import json
import logging
import tempfile
import shutil
import asyncio
import zipfile
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# Import the existing KaraokePrep class that the CLI uses
from karaoke_gen import KaraokePrep


def setup_logger(log_level=logging.INFO) -> logging.Logger:
    """Set up a basic logger for core processing functions."""
    logger = logging.getLogger(__name__)
    logger.setLevel(log_level)
    
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    
    return logger


class ServerlessKaraokeProcessor:
    """
    Serverless wrapper around the existing KaraokePrep functionality.
    Uses the same code path as the CLI for consistency.
    """
    
    def __init__(self, model_dir: str = "/models", output_dir: str = "/output"):
        self.model_dir = model_dir
        self.output_dir = output_dir
        # Use the logger from this module - job-specific logging will be set up externally
        self.logger = logging.getLogger(__name__)
    
    async def process_uploaded_file(self, job_id: str, audio_file_path: str, artist: str, title: str, styles_file_path: Optional[str] = None, styles_archive_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Process uploaded audio file through the complete karaoke generation pipeline.
        Uses the same KaraokePrep workflow as the CLI.
        
        Args:
            job_id: Unique identifier for this job
            audio_file_path: Path to uploaded audio file
            artist: Artist name
            title: Song title
            styles_file_path: Optional path to uploaded styles JSON file
            styles_archive_path: Optional path to uploaded styles archive file
            
        Returns:
            Dictionary with processing results and output file paths
        """
        try:
            job_output_dir = Path(self.output_dir) / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"Processing uploaded file: {audio_file_path}")
            self.logger.info(f"Artist: {artist}, Title: {title}")
            if styles_file_path:
                self.logger.info(f"Using custom styles: {styles_file_path}")
            
            # Handle styles archive extraction
            if styles_archive_path:
                self.logger.info(f"Using styles archive: {styles_archive_path}")
                
                # Extract archive to the job output directory instead of /tmp
                styles_assets_dir = job_output_dir / "styles_assets"
                styles_assets_dir.mkdir(exist_ok=True)
                
                with zipfile.ZipFile(styles_archive_path, 'r') as zip_ref:
                    zip_ref.extractall(styles_assets_dir)
                
                self.logger.info(f"Extracted styles archive to {styles_assets_dir}")
                
                # List extracted files for debugging
                extracted_files = []
                for root, dirs, files in os.walk(styles_assets_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        extracted_files.append(file_path)
                        
                        # Check if file is readable
                        try:
                            file_stat = os.stat(file_path)
                            self.logger.info(f"Extracted file: {file_path} (size: {file_stat.st_size} bytes)")
                        except Exception as e:
                            self.logger.warning(f"Could not stat file {file_path}: {e}")
                
                # Update styles JSON to use the extracted files
                if styles_file_path:
                    updated_styles_path = job_output_dir / "styles_updated.json"
                    self._update_styles_paths(styles_file_path, str(updated_styles_path), str(styles_assets_dir))
                    styles_file_path = str(updated_styles_path)
                    self.logger.info(f"Updated styles file paths: {styles_file_path}")
            
            # Validate that style-referenced files exist (do this after archive extraction)
            if styles_file_path:
                self.logger.info("Starting styles file validation...")
                missing_files = self._validate_styles_files(styles_file_path)
                if missing_files:
                    self.logger.error(f"Validation failed. Missing files: {missing_files}")
                    raise Exception(f"Missing style files - please ensure these files are included in the styles archive: {', '.join(missing_files)}")
                else:
                    self.logger.info("Styles file validation passed - all files found")
            
            # Set up KaraokePrep with the same formatter used by the CLI
            log_formatter = logging.Formatter(
                fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", 
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            
            # Create KaraokePrep instance using the same configuration as CLI
            kprep = KaraokePrep(
                input_media=audio_file_path,
                artist=artist,
                title=title,
                filename_pattern=None,
                dry_run=False,
                log_formatter=log_formatter,
                log_level=logging.INFO,
                render_bounding_boxes=False,
                output_dir=str(job_output_dir),
                create_track_subfolders=False,  # Don't create subfolders in serverless
                lossless_output_format="FLAC",
                output_png=True,
                output_jpg=True,
                clean_instrumental_model="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
                backing_vocals_models=["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"],
                other_stems_models=["htdemucs_6s.yaml"],
                model_file_dir=self.model_dir,
                existing_instrumental=None,
                skip_separation=False,
                lyrics_artist=artist,
                lyrics_title=title,
                lyrics_file=None,
                skip_lyrics=False,
                skip_transcription=False,
                skip_transcription_review=False,
                subtitle_offset_ms=0,
                style_params_json=styles_file_path,  # Use uploaded styles file if provided
            )
            
            # Process the track using the full KaraokePrep workflow
            self.logger.info("Starting KaraokePrep processing...")
            tracks = await kprep.process()
            
            if not tracks:
                raise Exception("No tracks were processed")
            
            track = tracks[0]  # We're processing a single track
            
            self.logger.info(f"Successfully processed track: {track['artist']} - {track['title']}")
            
            return {
                "job_id": job_id,
                "status": "awaiting_review",
                "track_data": track,
                "track_output_dir": track.get("track_output_dir", str(job_output_dir)),
            }
            
        except Exception as e:
            self.logger.error(f"Error processing uploaded file {job_id}: {str(e)}")
            raise

    async def process_url(self, job_id: str, url: str) -> Dict[str, Any]:
        """
        Process a URL through the complete karaoke generation pipeline.
        Uses the same KaraokePrep workflow as the CLI.
        
        Args:
            job_id: Unique identifier for this job
            url: YouTube or other media URL
            
        Returns:
            Dictionary with processing results and output file paths
        """
        try:
            job_output_dir = Path(self.output_dir) / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"Processing URL: {url}")
            
            # Set up KaraokePrep with the same formatter used by the CLI
            log_formatter = logging.Formatter(
                fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", 
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            
            # Create KaraokePrep instance using the same configuration as CLI
            kprep = KaraokePrep(
                input_media=url,
                artist=None,  # Will be extracted from URL
                title=None,   # Will be extracted from URL
                filename_pattern=None,
                dry_run=False,
                log_formatter=log_formatter,
                log_level=logging.INFO,
                render_bounding_boxes=False,
                output_dir=str(job_output_dir),
                create_track_subfolders=False,  # Don't create subfolders in serverless
                lossless_output_format="FLAC",
                output_png=True,
                output_jpg=True,
                clean_instrumental_model="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
                backing_vocals_models=["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"],
                other_stems_models=["htdemucs_6s.yaml"],
                model_file_dir=self.model_dir,
                existing_instrumental=None,
                skip_separation=False,
                lyrics_artist=None,
                lyrics_title=None,
                lyrics_file=None,
                skip_lyrics=False,
                skip_transcription=False,
                skip_transcription_review=True,  # Skip interactive review for serverless
                subtitle_offset_ms=0,
                style_params_json=None,  # No styles support for URL processing yet
            )
            
            # Process the track using the full KaraokePrep workflow
            self.logger.info("Starting KaraokePrep processing...")
            tracks = await kprep.process()
            
            if not tracks:
                raise Exception("No tracks were processed")
            
            track = tracks[0]  # We're processing a single track
            
            self.logger.info(f"Successfully processed track: {track['artist']} - {track['title']}")
            
            return {
                "job_id": job_id,
                "status": "awaiting_review", 
                "track_data": track,
                "track_output_dir": track.get("track_output_dir", str(job_output_dir)),
            }
            
        except Exception as e:
            self.logger.error(f"Error processing URL {job_id}: {str(e)}")
            raise
    
    def get_review_data(self, job_id: str, track_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract review data from processed track for frontend review interface.
        """
        try:
            track_dir = Path(track_data.get("track_output_dir", f"{self.output_dir}/{job_id}"))
            
            # Look for transcription results
            transcription_files = {
                "lrc_file": None,
                "corrected_lyrics": None,
                "original_lyrics": None,
                "vocals_audio": None
            }
            
            # Find LRC file
            lrc_files = list(track_dir.glob("**/*.lrc"))
            if lrc_files:
                transcription_files["lrc_file"] = str(lrc_files[0])
            
            # Find corrected lyrics text file
            corrected_files = list(track_dir.glob("**/*Corrected*.txt"))
            if corrected_files:
                with open(corrected_files[0], 'r') as f:
                    transcription_files["corrected_lyrics"] = f.read()
            
            # Find original/uncorrected lyrics
            original_files = list(track_dir.glob("**/*Uncorrected*.txt"))
            if original_files:
                with open(original_files[0], 'r') as f:
                    transcription_files["original_lyrics"] = f.read()
            
            # Find vocals audio file
            vocals_files = list(track_dir.glob("**/*Vocals*.flac")) + list(track_dir.glob("**/*Vocals*.FLAC"))
            if vocals_files:
                transcription_files["vocals_audio"] = str(vocals_files[0])
            
            return {
                "job_id": job_id,
                "artist": track_data.get("artist", "Unknown"),
                "title": track_data.get("title", "Unknown"),
                "transcription_files": transcription_files,
                "track_data": track_data
            }
            
        except Exception as e:
            self.logger.error(f"Error getting review data for {job_id}: {str(e)}")
            return {
                "job_id": job_id,
                "error": str(e)
            }

    def _validate_styles_files(self, styles_file_path: str) -> List[str]:
        """
        Validate that all files referenced in the styles JSON exist.
        Returns a list of missing file paths.
        """
        missing_files = []
        
        try:
            with open(styles_file_path, 'r') as f:
                styles_data = json.load(f)
            
            # Common keys that reference files
            file_keys = [
                'background_image', 'existing_image', 'font', 'font_path',
                'instrumental_background', 'title_screen_background', 'outro_background'
            ]
            
            def check_section(section_data, section_name):
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        if key in file_keys and value:
                            # Convert to string and check if it's a file path
                            file_path = str(value)
                            if file_path.startswith('/') and not Path(file_path).exists():
                                missing_files.append(file_path)
                        elif isinstance(value, dict):
                            check_section(value, f"{section_name}.{key}")
            
            # Check all sections
            check_section(styles_data, "styles")
            
            return missing_files
            
        except Exception as e:
            self.logger.warning(f"Could not validate styles file: {str(e)}")
            return []  # Don't block processing for validation errors

    def _update_styles_paths(self, input_styles_path: str, output_styles_path: str, assets_dir: str) -> None:
        """
        Update file paths in styles JSON to point to the extracted assets directory.
        """
        try:
            with open(input_styles_path, 'r') as f:
                styles_data = json.load(f)
            
            # Common keys that reference files
            file_keys = [
                'background_image', 'existing_image', 'font', 'font_path',
                'instrumental_background', 'title_screen_background', 'outro_background'
            ]
            
            def update_section(section_data):
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        if key in file_keys and value:
                            file_path = str(value)
                            if file_path.startswith('/tmp/'):
                                # Extract filename and update to use assets directory
                                filename = Path(file_path).name
                                new_path = os.path.join(assets_dir, filename)
                                section_data[key] = new_path
                                self.logger.info(f"Updated path: {file_path} -> {new_path}")
                        elif isinstance(value, dict):
                            update_section(value)
            
            update_section(styles_data)
            
            # Write updated styles file
            with open(output_styles_path, 'w') as f:
                json.dump(styles_data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Could not update styles paths: {str(e)}")
            raise