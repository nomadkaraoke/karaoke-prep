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
                skip_transcription_review=False,  # Enable review step - will be intercepted for web interface
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
            
            # Check if correction data was generated (indicating lyrics transcription occurred)
            track_output_dir = track.get("track_output_dir", str(job_output_dir))
            lyrics_dir = Path(track_output_dir) / "lyrics"
            corrections_file = lyrics_dir / f"{artist} - {title} (Lyrics Corrections).json"
            
            if corrections_file.exists():
                self.logger.info(f"Found lyrics correction data at {corrections_file}, setting status to awaiting_review")
                return {
                    "job_id": job_id,
                    "status": "awaiting_review",
                    "track_data": track,
                    "track_output_dir": track_output_dir,
                    "corrections_file": str(corrections_file),
                    "styles_file_path": styles_file_path,  # Return the updated styles file path
                }
            else:
                self.logger.info("No lyrics correction data found, job completed successfully")
                return {
                    "job_id": job_id,
                    "status": "complete",
                    "track_data": track,
                    "track_output_dir": track_output_dir,
                    "styles_file_path": styles_file_path,  # Return the updated styles file path
                }
            
        except Exception as e:
            self.logger.error(f"Error processing uploaded file {job_id}: {str(e)}")
            raise

    async def process_url(self, job_id: str, url: str, stored_cookies: Optional[str] = None, override_artist: Optional[str] = None, override_title: Optional[str] = None, styles_file_path: Optional[str] = None, styles_archive_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Process a URL through the complete karaoke generation pipeline.
        Uses the same KaraokePrep workflow as the CLI.
        
        Args:
            job_id: Unique identifier for this job
            url: YouTube or other media URL
            stored_cookies: Optional stored browser cookies to help bypass bot detection
            
        Returns:
            Dictionary with processing results and output file paths
        """
        try:
            job_output_dir = Path(self.output_dir) / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            self.logger.info(f"Processing URL: {url}")
            if override_artist:
                self.logger.info(f"Artist override: {override_artist}")
            if override_title:
                self.logger.info(f"Title override: {override_title}")
            
            # Handle styles files the same way as uploaded files
            if styles_file_path:
                self.logger.info(f"Using custom styles: {styles_file_path}")
            
            # Handle styles archive extraction
            if styles_archive_path:
                self.logger.info(f"Using styles archive: {styles_archive_path}")
                
                # Extract archive to the job output directory
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
            
            # Ensure styles file was provided - frontend should always upload one
            if not styles_file_path:
                raise Exception("No styles file provided. The frontend should upload default styles for all jobs.")
            
            # Validate that style-referenced files exist (do this after archive extraction)
            if styles_file_path:
                self.logger.info("Starting styles file validation...")
                missing_files = self._validate_styles_files(styles_file_path)
                if missing_files:
                    self.logger.error(f"Validation failed. Missing files: {missing_files}")
                    raise Exception(f"Missing style files - please ensure these files are included in the styles archive: {', '.join(missing_files)}")
                else:
                    self.logger.info("Styles file validation passed - all files found")
            
            if stored_cookies:
                self.logger.info("Using stored admin cookies for enhanced access")
            else:
                self.logger.info("No stored cookies available - attempting server-side extraction with anti-detection measures")
            
            # Set up enhanced yt-dlp options
            ytdlp_options = self.get_ytdlp_options(stored_cookies)
            
            # Override the extraction options in the environment
            # This is a bit hacky but necessary since KaraokePrep doesn't expose yt-dlp options directly
            cookies_file_path = None
            try:
                if stored_cookies:
                    # Save stored cookies to a file and set environment variable
                    import tempfile
                    cookies_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
                    cookies_file.write(stored_cookies)
                    cookies_file.close()
                    cookies_file_path = cookies_file.name
                    os.environ['YT_DLP_COOKIEFILE'] = cookies_file_path
                    self.logger.debug(f"Stored cookies saved to: {cookies_file_path}")
                
                # Set additional yt-dlp options via environment
                os.environ['YT_DLP_USER_AGENT'] = ytdlp_options['user_agent']
                os.environ['YT_DLP_REFERER'] = ytdlp_options['referer']
                
                # Set up KaraokePrep with the same formatter used by the CLI
                log_formatter = logging.Formatter(
                    fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", 
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
                
                # Create KaraokePrep instance using the same configuration as CLI
                kprep = KaraokePrep(
                    input_media=url,
                    artist=override_artist,  # User-provided override or None
                    title=override_title,    # User-provided override or None
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
                    skip_transcription_review=False,  # Enable review step - will be intercepted for web interface
                    subtitle_offset_ms=0,
                    style_params_json=styles_file_path,  # Use processed styles file (default or custom)
                    cookies_str=stored_cookies,  # Pass stored admin cookies
                )
                
                # Process the track using the full KaraokePrep workflow
                self.logger.info("Starting KaraokePrep processing...")
                tracks = await kprep.process()
                
                if not tracks:
                    raise Exception("No tracks were processed")
                
                track = tracks[0]  # We're processing a single track
                
                self.logger.info(f"Successfully processed track: {track['artist']} - {track['title']}")
                
                # Check if correction data was generated (indicating lyrics transcription occurred)
                track_output_dir = track.get("track_output_dir", str(job_output_dir))
                lyrics_dir = Path(track_output_dir) / "lyrics"
                artist = track.get("artist", "Unknown")
                title = track.get("title", "Unknown")
                corrections_file = lyrics_dir / f"{artist} - {title} (Lyrics Corrections).json"
                
                if corrections_file.exists():
                    self.logger.info(f"Found lyrics correction data at {corrections_file}, setting status to awaiting_review")
                    return {
                        "job_id": job_id,
                        "status": "awaiting_review",
                        "track_data": track,
                        "track_output_dir": track_output_dir,
                        "corrections_file": str(corrections_file),
                        "styles_file_path": styles_file_path,  # Return the processed styles file path
                    }
                else:
                    self.logger.info("No lyrics correction data found, job completed successfully")
                    return {
                        "job_id": job_id,
                        "status": "complete",
                        "track_data": track,
                        "track_output_dir": track_output_dir,
                        "styles_file_path": styles_file_path,  # Return the processed styles file path
                    }
                    
            finally:
                # Clean up cookies file and environment variables
                if cookies_file_path:
                    try:
                        os.unlink(cookies_file_path)
                    except:
                        pass
                
                for env_var in ['YT_DLP_COOKIEFILE', 'YT_DLP_USER_AGENT', 'YT_DLP_REFERER']:
                    if env_var in os.environ:
                        del os.environ[env_var]
                        
        except Exception as e:
            error_msg = str(e)
            self.logger.error(f"Error processing URL {job_id}: {error_msg}")
            
            # Check if this looks like a bot detection error
            if any(keyword in error_msg.lower() for keyword in ['sign in', 'bot', 'automated', '403', 'forbidden', 'captcha']):
                # This suggests YouTube bot detection - provide helpful error message
                raise Exception(
                    f"YouTube access blocked (bot detection): {error_msg}. "
                    f"This usually means YouTube is blocking server requests. "
                    f"Try providing browser cookies to help bypass this restriction."
                )
            else:
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

    def get_ytdlp_options(self, stored_cookies: Optional[str] = None):
        """Get yt-dlp options with enhanced anti-detection."""
        options = {
            # Basic extraction options
            'format': 'bestaudio[ext=webm]/bestaudio[ext=m4a]/bestaudio',
            'extractaudio': True,
            'audioformat': 'flac',
            'outtmpl': '%(title)s.%(ext)s',
            
            # Anti-detection options
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'referer': 'https://www.youtube.com/',
            'sleep_interval': 1,
            'max_sleep_interval': 3,
            'fragment_retries': 3,
            'extractor_retries': 3,
            'retries': 3,
            
            # Headers to appear more human
            'http_headers': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # Avoid bot-like behavior
            'no_check_certificate': False,
            'prefer_insecure': False,
            'call_home': False,
        }
        
        # Add stored cookies if available
        if stored_cookies:
            # Save stored cookies to a temporary file
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                f.write(stored_cookies)
                options['cookiefile'] = f.name
        
        return options



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
        Also install any font files system-wide so they can be referenced by name.
        """
        try:
            with open(input_styles_path, 'r') as f:
                styles_data = json.load(f)
            
            # Build a map of all files in the assets directory for quick lookup
            assets_path = Path(assets_dir)
            file_map = {}
            font_files = []  # Track font files for installation
            
            self.logger.info(f"Building file map from assets directory: {assets_dir}")
            for root, dirs, files in os.walk(assets_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    filename = file.lower()  # Use lowercase for case-insensitive matching
                    file_map[filename] = file_path
                    
                    # Check if this is a font file
                    if filename.endswith(('.ttf', '.otf', '.woff', '.woff2')):
                        font_files.append(file_path)
                        self.logger.info(f"Found font file for installation: {file_path}")
                    
                    self.logger.debug(f"Found asset file: {filename} -> {file_path}")
            
            self.logger.info(f"Found {len(file_map)} files in assets directory, {len(font_files)} fonts")
            
            # Install font files system-wide
            if font_files:
                self._install_fonts(font_files)
            
            # Common keys that reference files
            file_keys = [
                'background_image', 'existing_image', 'font', 'font_path',
                'instrumental_background', 'title_screen_background', 'outro_background'
            ]
            
            paths_updated = 0
            paths_failed = 0
            
            def update_section(section_data, section_path=""):
                nonlocal paths_updated, paths_failed
                
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        current_path = f"{section_path}.{key}" if section_path else key
                        
                        if key in file_keys and value:
                            file_path = str(value).strip()
                            
                            # Check if this is an absolute path that needs updating
                            if file_path.startswith('/'):
                                self.logger.info(f"Processing file path at {current_path}: {file_path}")
                                
                                # Extract just the filename
                                original_filename = Path(file_path).name
                                filename_lower = original_filename.lower()
                                
                                # Look for the file in our assets map
                                if filename_lower in file_map:
                                    new_path = file_map[filename_lower]
                                    section_data[key] = new_path
                                    paths_updated += 1
                                    self.logger.info(f"✓ Updated path at {current_path}: {file_path} -> {new_path}")
                                    
                                    # Verify the new path exists
                                    if not Path(new_path).exists():
                                        self.logger.warning(f"WARNING: Updated path does not exist: {new_path}")
                                        paths_failed += 1
                                else:
                                    self.logger.error(f"✗ Could not find file '{original_filename}' in assets directory for path at {current_path}")
                                    self.logger.error(f"Available files: {list(file_map.keys())}")
                                    paths_failed += 1
                            else:
                                self.logger.debug(f"Skipping relative path at {current_path}: {file_path}")
                                
                        elif isinstance(value, dict):
                            update_section(value, current_path)
                        elif isinstance(value, list):
                            # Handle arrays that might contain file paths
                            for i, item in enumerate(value):
                                if isinstance(item, dict):
                                    update_section(item, f"{current_path}[{i}]")
            
            self.logger.info("Starting styles path updates...")
            update_section(styles_data)
            
            self.logger.info(f"Path update summary: {paths_updated} updated, {paths_failed} failed")
            
            # Write updated styles file
            with open(output_styles_path, 'w') as f:
                json.dump(styles_data, f, indent=2)
            
            self.logger.info(f"Updated styles file written to: {output_styles_path}")
            
            # Now update font names with correct names that FFmpeg recognizes
            if font_files:
                self._fix_font_names_in_styles(output_styles_path, font_files)
                
                # Run test render to verify font rendering works
                test_output_dir = str(Path(output_styles_path).parent)
                self.test_font_render(font_files, test_output_dir)
            
            # Log the content of the updated file for debugging
            self.logger.debug("Updated styles file content:")
            with open(output_styles_path, 'r') as f:
                content = f.read()
                # Only log first 1000 chars to avoid spam
                self.logger.debug(content[:1000] + ("..." if len(content) > 1000 else ""))
                
        except Exception as e:
            self.logger.error(f"Could not update styles paths: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def _install_fonts(self, font_files: List[str]) -> None:
        """
        Install font files system-wide so they can be referenced by name in FFmpeg.
        """
        import subprocess
        
        try:
            # Try to install fonts in multiple directories for maximum compatibility
            font_dirs = [
                Path.home() / '.fonts',
                Path('/usr/share/fonts/truetype/custom'),
                Path('/usr/local/share/fonts'),
                Path('/tmp/fonts')
            ]
            
            installed_fonts = []
            
            # Install fonts in all accessible directories
            for fonts_dir in font_dirs:
                try:
                    fonts_dir.mkdir(parents=True, exist_ok=True)
                    self.logger.info(f"Installing fonts in: {fonts_dir}")
                    
                    for font_file in font_files:
                        try:
                            source_path = Path(font_file)
                            dest_path = fonts_dir / source_path.name
                            
                            # Copy the font file
                            shutil.copy2(source_path, dest_path)
                            if str(dest_path) not in installed_fonts:
                                installed_fonts.append(str(dest_path))
                            self.logger.info(f"✓ Installed font: {source_path.name} -> {dest_path}")
                            
                        except Exception as e:
                            self.logger.warning(f"Failed to install font {font_file} to {fonts_dir}: {str(e)}")
                            
                except PermissionError:
                    self.logger.info(f"Cannot write to fonts directory: {fonts_dir}")
                except Exception as e:
                    self.logger.warning(f"Error setting up fonts directory {fonts_dir}: {str(e)}")
            
            if installed_fonts:
                # Set up environment variables for font discovery
                import os
                font_paths = [str(Path(f).parent) for f in installed_fonts]
                font_paths = list(set(font_paths))  # Remove duplicates
                
                if font_paths:
                    # Set FONTCONFIG_PATH to help with font discovery
                    current_fontconfig = os.environ.get('FONTCONFIG_PATH', '')
                    new_fontconfig = ':'.join(font_paths)
                    if current_fontconfig:
                        new_fontconfig = f"{current_fontconfig}:{new_fontconfig}"
                    os.environ['FONTCONFIG_PATH'] = new_fontconfig
                    self.logger.info(f"Set FONTCONFIG_PATH to: {new_fontconfig}")
                
                # Refresh the font cache
                try:
                    # Try to run fc-cache to refresh font cache
                    result = subprocess.run(['fc-cache', '-f'], 
                                          capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        self.logger.info("✓ Font cache refreshed successfully")
                    else:
                        self.logger.warning(f"Font cache refresh had warnings: {result.stderr}")
                    
                    # List installed fonts for verification
                    try:
                        result = subprocess.run(['fc-list'], 
                                              capture_output=True, text=True, timeout=10)
                        if result.returncode == 0:
                            font_list = result.stdout
                            for font_file in installed_fonts:
                                font_name = Path(font_file).stem
                                if font_name.lower() in font_list.lower():
                                    self.logger.info(f"✓ Verified font is available: {font_name}")
                                else:
                                    self.logger.warning(f"⚠ Font may not be properly installed: {font_name}")
                    except Exception as e:
                        self.logger.debug(f"Could not verify font installation: {str(e)}")
                        
                    # Additional debugging: Check what FFmpeg sees
                    try:
                        self.logger.info("=== FFmpeg Font Debugging ===")
                        
                        # Test if FFmpeg can find the font by name
                        ffmpeg_result = subprocess.run([
                            'ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'color=black:size=100x100:duration=1',
                            '-vf', 'drawtext=text=TEST:fontfile=/root/.fonts/AvenirNext-Bold.ttf:fontsize=24:fontcolor=white',
                            '-frames:v', '1', '-f', 'null', '-'
                        ], capture_output=True, text=True, timeout=10)
                        
                        if ffmpeg_result.returncode == 0:
                            self.logger.info("✓ FFmpeg can access font by file path")
                        else:
                            self.logger.warning(f"✗ FFmpeg cannot access font by file path: {ffmpeg_result.stderr}")
                        
                        # Test if FFmpeg can find the font by name
                        ffmpeg_result = subprocess.run([
                            'ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'color=black:size=100x100:duration=1',
                            '-vf', 'drawtext=text=TEST:font=AvenirNext-Bold:fontsize=24:fontcolor=white',
                            '-frames:v', '1', '-f', 'null', '-'
                        ], capture_output=True, text=True, timeout=10)
                        
                        if ffmpeg_result.returncode == 0:
                            self.logger.info("✓ FFmpeg can access font by name")
                        else:
                            self.logger.warning(f"✗ FFmpeg cannot access font by name: {ffmpeg_result.stderr}")
                            
                        # Get actual font name from fc-query
                        fc_query_result = subprocess.run([
                            'fc-query', '--format=%{family}\\n', '/root/.fonts/AvenirNext-Bold.ttf'
                        ], capture_output=True, text=True, timeout=10)
                        
                        if fc_query_result.returncode == 0:
                            actual_font_name = fc_query_result.stdout.strip()
                            self.logger.info(f"✓ Actual font family name: '{actual_font_name}'")
                            
                            # Test with the actual font name
                            if actual_font_name and actual_font_name != "AvenirNext-Bold":
                                ffmpeg_result = subprocess.run([
                                    'ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'color=black:size=100x100:duration=1',
                                    '-vf', f'drawtext=text=TEST:font={actual_font_name}:fontsize=24:fontcolor=white',
                                    '-frames:v', '1', '-f', 'null', '-'
                                ], capture_output=True, text=True, timeout=10)
                                
                                if ffmpeg_result.returncode == 0:
                                    self.logger.info(f"✓ FFmpeg can access font by actual name: '{actual_font_name}'")
                                else:
                                    self.logger.warning(f"✗ FFmpeg cannot access font by actual name '{actual_font_name}': {ffmpeg_result.stderr}")
                        else:
                            self.logger.warning(f"Could not query font name: {fc_query_result.stderr}")
                        
                        # List all fonts that FFmpeg can see
                        try:
                            # This uses a trick to get FFmpeg to list all available fonts
                            ffmpeg_list_result = subprocess.run([
                                'ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'color=black:size=100x100:duration=0.1',
                                '-vf', 'drawtext=text=:font=ThisFontDoesNotExist:fontsize=1', 
                                '-f', 'null', '-'
                            ], capture_output=True, text=True, timeout=10)
                            
                            # FFmpeg will error but should list available fonts in stderr
                            if "unable to find a suitable font" in ffmpeg_list_result.stderr.lower():
                                self.logger.info("FFmpeg font listing (available fonts mentioned in error):")
                                # Extract font info from error message
                                lines = ffmpeg_list_result.stderr.split('\n')
                                for line in lines:
                                    if 'font' in line.lower() and ('available' in line.lower() or 'found' in line.lower()):
                                        self.logger.info(f"  {line.strip()}")
                            
                        except Exception as e:
                            self.logger.debug(f"Could not list FFmpeg fonts: {str(e)}")
                            
                        self.logger.info("=== End FFmpeg Font Debugging ===")
                        
                    except Exception as e:
                        self.logger.warning(f"Font debugging failed: {str(e)}")
                        
                except subprocess.TimeoutExpired:
                    self.logger.warning("Font cache refresh timed out")
                except FileNotFoundError:
                    self.logger.warning("fc-cache not found, fonts may not be properly cached")
                except Exception as e:
                    self.logger.warning(f"Error refreshing font cache: {str(e)}")
                
                self.logger.info(f"Successfully installed {len(installed_fonts)} fonts")
            else:
                self.logger.warning("No fonts were successfully installed")
                
        except Exception as e:
            self.logger.error(f"Error installing fonts: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            # Don't raise - font installation failure shouldn't stop the job

    def _fix_font_names_in_styles(self, styles_file_path: str, installed_font_files: List[str]) -> None:
        """
        Update font names in styles JSON to use the actual font names that FFmpeg recognizes.
        This is necessary because FFmpeg's font rendering can be sensitive to font names.
        """
        import subprocess
        
        try:
            with open(styles_file_path, 'r') as f:
                styles_data = json.load(f)
            
            # Build a map of font file paths to their actual family names
            font_name_map = {}
            for font_file in installed_font_files:
                try:
                    result = subprocess.run([
                        'fc-query', '--format=%{family}\\n', font_file
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        actual_font_name = result.stdout.strip()
                        font_name_map[font_file] = actual_font_name
                        self.logger.info(f"Font file {font_file} -> Font name '{actual_font_name}'")
                    else:
                        self.logger.warning(f"fc-query failed for {font_file}: {result.stderr}")
                except Exception as e:
                    self.logger.warning(f"Could not resolve font name for {font_file}: {str(e)}")
            
            fonts_updated = 0
            
            def update_section(section_data, section_path=""):
                nonlocal fonts_updated
                
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        current_path = f"{section_path}.{key}" if section_path else key
                        
                        # Look for font name fields (not file paths)
                        if key == 'font' and isinstance(value, str) and value:
                            # This is a font name field - check if we have a corresponding font_path
                            font_path_key = 'font_path'
                            if font_path_key in section_data and section_data[font_path_key]:
                                font_path = str(section_data[font_path_key]).strip()
                                
                                # Find matching font in our installed fonts
                                for font_file, actual_name in font_name_map.items():
                                    if font_path.endswith(Path(font_file).name) or font_file == font_path:
                                        old_name = value
                                        section_data[key] = actual_name
                                        fonts_updated += 1
                                        self.logger.info(f"✓ Updated font name at {current_path}: '{old_name}' -> '{actual_name}'")
                                        break
                                else:
                                    self.logger.warning(f"Could not find matching font file for {current_path} with path {font_path}")
                            else:
                                self.logger.debug(f"No font_path found for font name at {current_path}")
                                
                        elif isinstance(value, dict):
                            update_section(value, current_path)
                        elif isinstance(value, list):
                            for i, item in enumerate(value):
                                if isinstance(item, dict):
                                    update_section(item, f"{current_path}[{i}]")
            
            self.logger.info("Starting font name correction in styles...")
            update_section(styles_data)
            
            self.logger.info(f"Font name update summary: {fonts_updated} font names updated")
            
            # Write updated styles file
            with open(styles_file_path, 'w') as f:
                json.dump(styles_data, f, indent=2)
            
            self.logger.info(f"Updated styles file written to: {styles_file_path}")
                
        except Exception as e:
            self.logger.error(f"Could not update font names in styles: {str(e)}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            # Don't raise - this shouldn't stop the job

    def test_font_render(self, font_files: List[str], output_dir: str) -> None:
        """
        Create a test video with ASS subtitles to verify font rendering works correctly.
        """
        import subprocess
        import tempfile
        
        try:
            test_dir = Path(output_dir) / "font_tests"
            test_dir.mkdir(exist_ok=True)
            
            self.logger.info("=== Starting Font Render Test ===")
            
            for font_file in font_files:
                try:
                    # Get actual font name
                    result = subprocess.run([
                        'fc-query', '--format=%{family}\\n', font_file
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode == 0:
                        font_name = result.stdout.strip()
                        
                        # Create test ASS file
                        ass_content = f"""[Script Info]
Title: Font Test
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontpath, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TestStyle,{font_name},{font_file},48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:03.00,TestStyle,,0,0,0,,Font Test: {font_name}
Dialogue: 0,0:00:03.00,0:00:06.00,TestStyle,,0,0,0,,The quick brown fox jumps
Dialogue: 0,0:00:06.00,0:00:09.00,TestStyle,,0,0,0,,ABCDEFGHIJKLMNOP
"""
                        
                        ass_file = test_dir / f"test_{Path(font_file).stem}.ass"
                        with open(ass_file, 'w') as f:
                            f.write(ass_content)
                        
                        # Create test video
                        output_video = test_dir / f"test_{Path(font_file).stem}.mp4"
                        
                        cmd = [
                            'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                            '-f', 'lavfi', '-i', 'color=black:size=640x360:duration=10:rate=25',
                            '-vf', f"ass={ass_file}",
                            '-c:v', 'libx264', '-preset', 'ultrafast',
                            str(output_video)
                        ]
                        
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                        
                        if result.returncode == 0:
                            self.logger.info(f"✓ Test video created successfully: {output_video}")
                            self.logger.info(f"  Font: {font_name} ({Path(font_file).name})")
                        else:
                            self.logger.error(f"✗ Test video failed for {font_name}: {result.stderr}")
                            
                except Exception as e:
                    self.logger.error(f"Test render failed for {font_file}: {str(e)}")
            
            self.logger.info("=== Font Render Test Complete ===")
            
        except Exception as e:
            self.logger.error(f"Font test render failed: {str(e)}")
            # Don't raise - this is just a test

    def debug_ass_file(self, ass_file_path: str) -> None:
        """
        Debug ASS file content to see what font is actually being used.
        """
        try:
            if not Path(ass_file_path).exists():
                self.logger.warning(f"ASS file not found: {ass_file_path}")
                return
                
            self.logger.info(f"=== Debugging ASS File: {ass_file_path} ===")
            
            with open(ass_file_path, 'r') as f:
                lines = f.readlines()
            
            # Look for Style lines
            for i, line in enumerate(lines):
                if line.startswith('Style:'):
                    self.logger.info(f"Line {i+1}: {line.strip()}")
                    
                    # Parse the style line
                    parts = line.strip().split(',')
                    if len(parts) >= 4:
                        style_name = parts[0].split(':')[1] if ':' in parts[0] else parts[0]
                        fontname = parts[1] if len(parts) > 1 else "N/A"
                        fontpath = parts[2] if len(parts) > 2 else "N/A"
                        fontsize = parts[3] if len(parts) > 3 else "N/A"
                        
                        self.logger.info(f"  Style Name: {style_name}")
                        self.logger.info(f"  Font Name: {fontname}")
                        self.logger.info(f"  Font Path: {fontpath}")
                        self.logger.info(f"  Font Size: {fontsize}")
                        
                        # Check if font path exists
                        if fontpath.startswith('/') and fontpath != "N/A":
                            exists = Path(fontpath).exists()
                            self.logger.info(f"  Font File Exists: {exists}")
                            if not exists:
                                self.logger.warning(f"  ⚠ Font file missing: {fontpath}")
            
            self.logger.info("=== End ASS File Debug ===")
            
        except Exception as e:
            self.logger.error(f"Error debugging ASS file: {str(e)}")

    def ensure_fonts_available(self, styles_file_path: str) -> None:
        """
        Ensure fonts are available in the current environment by re-installing them if needed.
        This is useful when ASS generation happens in a different process/context.
        """
        try:
            if not Path(styles_file_path).exists():
                self.logger.warning(f"Styles file not found: {styles_file_path}")
                return
                
            self.logger.info("=== Ensuring Fonts Available ===")
            
            # Load styles to find font files
            with open(styles_file_path, 'r') as f:
                styles_data = json.load(f)
            
            # Find font files referenced in styles
            font_files = []
            def find_fonts(section_data):
                if isinstance(section_data, dict):
                    for key, value in section_data.items():
                        if key == 'font_path' and value and str(value).endswith('.ttf'):
                            font_files.append(str(value))
                        elif isinstance(value, dict):
                            find_fonts(value)
            
            find_fonts(styles_data)
            
            if font_files:
                self.logger.info(f"Found {len(font_files)} font files to ensure: {font_files}")
                
                # Check if fonts are already available
                import subprocess
                fonts_need_install = []
                
                for font_file in font_files:
                    if Path(font_file).exists():
                        try:
                            # Check if font is in fc-list
                            result = subprocess.run(['fc-query', '--format=%{family}\\n', font_file],
                                                  capture_output=True, text=True, timeout=5)
                            if result.returncode == 0:
                                font_name = result.stdout.strip()
                                
                                # Check if FFmpeg can access it
                                ffmpeg_result = subprocess.run([
                                    'ffmpeg', '-hide_banner', '-f', 'lavfi', '-i', 'color=black:size=100x100:duration=0.1',
                                    '-vf', f'drawtext=text=TEST:font={font_name}:fontsize=12',
                                    '-frames:v', '1', '-f', 'null', '-'
                                ], capture_output=True, text=True, timeout=5)
                                
                                if ffmpeg_result.returncode == 0:
                                    self.logger.info(f"✓ Font available: {font_name} ({Path(font_file).name})")
                                else:
                                    self.logger.warning(f"⚠ Font not accessible to FFmpeg: {font_name}")
                                    fonts_need_install.append(font_file)
                            else:
                                self.logger.warning(f"⚠ Font not in fc-list: {font_file}")
                                fonts_need_install.append(font_file)
                        except Exception as e:
                            self.logger.warning(f"Error checking font {font_file}: {str(e)}")
                            fonts_need_install.append(font_file)
                    else:
                        self.logger.error(f"✗ Font file missing: {font_file}")
                
                # Re-install fonts if needed
                if fonts_need_install:
                    self.logger.info(f"Re-installing {len(fonts_need_install)} fonts")
                    self._install_fonts(fonts_need_install)
                else:
                    self.logger.info("All fonts are already available")
            else:
                self.logger.info("No font files found in styles")
                
            self.logger.info("=== Font Availability Check Complete ===")
            
        except Exception as e:
            self.logger.error(f"Error ensuring fonts available: {str(e)}")