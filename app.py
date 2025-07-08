"""
Modal Karaoke Generator API Backend

This module contains the Modal application structure for running karaoke generation
as serverless functions with GPU acceleration and API endpoints for the frontend.
"""

import modal
import uuid
import json
import traceback
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import random
import shutil
import zipfile
import os
import logging
import hashlib
import time
import subprocess
from enum import Enum

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File, Depends
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel


# Define the environment for our functions - using Python 3.13 for latest features with NVENC hardware acceleration
karaoke_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.1-devel-ubuntu22.04", add_python="3.13")
    .apt_install(
        [
            # Core system packages
            "curl",
            "wget", 
            "xz-utils",
            # Audio libraries
            "libsndfile1",
            "libsox-dev",
            "sox",
            "fontconfig",  # For font management
            # Build tools for compiling Python packages with C extensions
            "build-essential",
            "clang",
            "gcc",
            "g++",
            "make",
            # rclone for cloud storage sync
            "unzip",
        ]
    )
    .run_commands([
        # Set up CUDA library paths for NVENC support
        "echo '/usr/local/cuda/lib64' >> /etc/ld.so.conf.d/cuda.conf",
        "ldconfig",
        # Install latest FFmpeg with full NVENC support
        "wget https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
        "tar -xf ffmpeg-master-latest-linux64-gpl.tar.xz",
        "cp ffmpeg-master-latest-linux64-gpl/bin/* /usr/local/bin/",
        "chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe",
        # Install rclone
        "curl https://rclone.org/install.sh | bash",
        # Verify installations and NVENC support
        "ffmpeg -version",
        "ffmpeg -hide_banner -encoders | grep nvenc || echo 'NVENC encoders check'",
        "rclone version",
    ])
    .pip_install(
        [
            # Core dependencies
            "torch>=2.7",
            "requests>=2",
            "beautifulsoup4>=4",
            "yt-dlp",
            "lyricsgenius>=3",
            "fetch-lyrics-from-genius>=0.1",
            "pillow>=10.1",
            "google-api-python-client",
            "google-auth",
            "google-auth-oauthlib",
            "google-auth-httplib2",
            "thefuzz>=0.22",
            "numpy>=2",
            "audio-separator[gpu]>=0.34.0",
            "lyrics-converter>=0.2.1",
            "kbputils>=0.0.12",
            "fuzzywuzzy>=0.18",
            "ffmpeg-python>=0.2.0",
            "pydub>=0.25",
            "opencv-python>=4.8",
            "openai-whisper>=20240930",
            "soundfile>=0.12",
            "librosa>=0.10",
            "demucs>=4.0.1",
            "psutil>=5.9.0",
            # FastAPI dependencies
            "fastapi>=0.104.0",
            "uvicorn>=0.24.0",
            "python-multipart>=0.0.7",
            "requests>=2.31.0",
            # Uncomment this line to use the lyrics-transcriber package from PyPI
            "lyrics-transcriber>=0.61",
            # To use the local version of lyrics-transcriber, comment out the line above and
            # uncomment the lyrics_transcriber_local "add_local_dir" and "run_commands" lines below
        ]
    )
    .env({
        "LYRICS_TRANSCRIBER_CACHE_DIR": "/cache", 
        "AUDIO_SEPARATOR_MODEL_DIR": "/models",
        # CUDA environment for NVENC support
        "LD_LIBRARY_PATH": "/usr/local/cuda/lib64:$LD_LIBRARY_PATH",
        "PATH": "/usr/local/cuda/bin:$PATH"
    })
    # ----- lyrics_transcriber_local -----
    # Uncomment this section to use the local version of lyrics-transcriber
    # If using the PyPI version, comment out this section and
    # uncomment the normal lyrics-transcriber line above
    # .add_local_dir("lyrics_transcriber_local", "/root/lyrics_transcriber_local", copy=True)
    # .run_commands([
    #     "cd /root/lyrics_transcriber_local && pip install -e .",  # Install lyrics-transcriber from local first
    #     "python -c 'import lyrics_transcriber; print(f\"✓ lyrics-transcriber installed from: {lyrics_transcriber.__file__}\")'",  # Verify installation
    # ])
    # ----- lyrics_transcriber_local -----
    .add_local_dir("karaoke_gen", "/root/karaoke_gen")
    .add_local_file("core.py", "/root/core.py")
)

# Define the Modal app
app = modal.App("karaoke-generator-webapp")

# Define persistent storage volumes
model_volume = modal.Volume.from_name("karaoke-models", create_if_missing=True)
output_volume = modal.Volume.from_name("karaoke-output", create_if_missing=True)
cache_volume = modal.Volume.from_name("karaoke-cache", create_if_missing=True)
preview_volume = modal.Volume.from_name("karaoke-previews", create_if_missing=True)

# Define serverless dictionaries to hold job states
job_status_dict = modal.Dict.from_name("karaoke-job-statuses", create_if_missing=True)
# Note: job_logs_dict removed - now using Modal's native logging via CLI queries

# Add new Modal Dicts for authentication and YouTube cookies
auth_tokens_dict = modal.Dict.from_name("karaoke-auth-tokens", create_if_missing=True)
token_usage_dict = modal.Dict.from_name("karaoke-token-usage", create_if_missing=True)
user_sessions_dict = modal.Dict.from_name("karaoke-user-sessions", create_if_missing=True)
user_youtube_cookies_dict = modal.Dict.from_name("karaoke-youtube-cookies", create_if_missing=True)

# Add configuration storage for finalization features
finalization_config_dict = modal.Dict.from_name("karaoke-finalization-config", create_if_missing=True)

# Add system configuration storage for log levels, etc.
system_config_dict = modal.Dict.from_name("karaoke-system-config", create_if_missing=True)

# Add a volume for storing configuration files
config_volume = modal.Volume.from_name("karaoke-config", create_if_missing=True)

# Add new Modal Dict for storing user YouTube credentials
user_youtube_credentials_dict = modal.Dict.from_name("karaoke-user-youtube-credentials", create_if_missing=True)

# Mount volumes to specific paths inside the container
VOLUME_CONFIG = {"/models": model_volume, "/output": output_volume, "/cache": cache_volume, "/config": config_volume, "/previews": preview_volume}


# User type enumeration (must be defined before Pydantic models that use it)
class UserType(str, Enum):
    ADMIN = "admin"
    UNLIMITED = "unlimited"
    LIMITED = "limited"
    STRIPE = "stripe"


# Pydantic models for API requests
class JobSubmissionRequest(BaseModel):
    url: str


class YouTubeSubmissionRequest(BaseModel):
    url: str
    artist: Optional[str] = None
    title: Optional[str] = None


class LyricsReviewRequest(BaseModel):
    lyrics: str


class AuthRequest(BaseModel):
    token: str


class AuthResponse(BaseModel):
    success: bool
    user_type: str
    remaining_uses: Optional[int] = None
    message: str
    admin_access: bool = False


class CreateTokenRequest(BaseModel):
    token_type: UserType
    token_value: str
    max_uses: Optional[int] = None
    description: Optional[str] = None


class JobLogHandler(logging.Handler):
    """Custom logging handler that outputs to both Modal's native logging and local log files"""

    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        # Prevent recursion by not processing our own log messages
        self.processing = False
        # Set up local log file path
        self.log_file_path = Path(f"/output/{job_id}/job_logs.jsonl")

    def emit(self, record):
        if self.processing:
            return

        try:
            self.processing = True

            # Filter out noisy logs from Modal's internal operations
            if self._should_filter_log(record):
                return

            # Format the log message
            message = self.format(record)

            # Create log entry
            log_entry = {"timestamp": datetime.datetime.now().isoformat(), "level": record.levelname, "message": message}

            # Print to stdout for Modal's native logging
            print(f"[{log_entry['level']}] {log_entry['message']}")
            
            # Also write to local log file (JSONL format - one JSON object per line)
            try:
                # Ensure the directory exists - use more robust directory creation
                import os
                directory = self.log_file_path.parent
                if not directory.exists():
                    directory.mkdir(parents=True, exist_ok=True)
                
                # Append to the log file (JSONL format) with explicit error handling
                with open(self.log_file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry) + "\n")
                    f.flush()  # Ensure data is written immediately
                    

                    
            except PermissionError as e:
                print(f"[WARNING] Permission denied writing to log file {self.log_file_path}: {e}")
            except OSError as e:
                print(f"[WARNING] OS error writing to log file {self.log_file_path}: {e}")
            except Exception as e:
                print(f"[WARNING] Unexpected error writing to local log file {self.log_file_path}: {e}")

        except Exception as e:
            # Print error for debugging but don't crash
            print(f"[ERROR] JobLogHandler.emit failed: {e}")
        finally:
            self.processing = False

    def _should_filter_log(self, record):
        """Filter out noisy logs from Modal's internal libraries and operations."""
        
        # Filter by logger name (module)
        noisy_modules = [
            'hpack',
            'ssa',
            'byteflow',
            'PngImagePlugin'
        ]
        if any(record.name.startswith(module) for module in noisy_modules):
            return True

        # Keep all other logs
        return False

    def flush(self):
        """Flush any pending log writes to disk."""
        try:
            # Force flush stdout
            import sys
            sys.stdout.flush()
            
            # Force filesystem sync if the log file exists
            if self.log_file_path.exists():
                try:
                    import os
                    # Open and close to ensure all writes are flushed
                    with open(self.log_file_path, "a") as f:
                        f.flush()
                        os.fsync(f.fileno())
                except (PermissionError, OSError, Exception):
                    pass  # Fail silently on flush errors
        except Exception as e:
            # Don't crash on flush errors
            print(f"[WARNING] Could not flush log file: {e}")


def setup_job_logging(job_id: str):
    """Set up logging to capture all messages for a job"""

    # Create custom handler
    handler = JobLogHandler(job_id)

    # Set up formatter to match the CLI output format
    formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)

    # Add handler to root logger - this will capture all logging via propagation
    root_logger = logging.getLogger()
    
    # Remove any existing handlers to avoid duplicates
    for existing_handler in root_logger.handlers[:]:
        if isinstance(existing_handler, JobLogHandler):
            root_logger.removeHandler(existing_handler)
    
    root_logger.addHandler(handler)
    
    # Get configured log level from system config, default to INFO for production
    system_config = system_config_dict.get("config", {})
    log_level_name = system_config.get("log_level", "DEBUG")
    log_level = getattr(logging, log_level_name.upper(), logging.DEBUG)
    root_logger.setLevel(log_level)
    
    # Force specific loggers that are important for our application to the correct level
    important_loggers = [
        'karaoke_gen',
        'lyrics_transcriber', 
        'karaoke_finalise',
        '__main__',  # Main script logs
    ]
    
    for logger_name in important_loggers:
        important_logger = logging.getLogger(logger_name)
        important_logger.setLevel(log_level)
        # Ensure propagation is enabled so logs reach the root handler
        important_logger.propagate = True
    
    # Specifically configure video generation loggers to ensure NVENC/FFmpeg logs are captured
    video_loggers = [
        'lyrics_transcriber.output.video',
        'lyrics_transcriber.output.generator',
        f'lyrics_transcriber.preview.{job_id}',  # Preview-specific logger
    ]
    
    for logger_name in video_loggers:
        video_logger = logging.getLogger(logger_name)
        video_logger.setLevel(log_level)
        video_logger.propagate = True

    # Suppress noisy debug logs from Modal's internal libraries
    noisy_loggers = [
        'hpack',
        'ssa',
        'byteflow',
        'PngImagePlugin',
        'modal',  # Suppress most Modal internal logs
        'urllib3',  # HTTP request logs
        'requests',  # HTTP request logs  
    ]
    
    for logger_name in noisy_loggers:
        noisy_logger = logging.getLogger(logger_name)
        # Set these loggers to WARNING level to suppress DEBUG/INFO spam
        noisy_logger.setLevel(logging.WARNING)
    

        
    return handler


def log_message(job_id: str, level: str, message: str):
    """Log a message with timestamp and level."""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {"timestamp": timestamp, "level": level, "message": message}

    # Print to stdout for Modal's native logging
    print(f"[{level}] {message}")
    
    # Also write to local log file
    try:
        log_file_path = Path(f"/output/{job_id}/job_logs.jsonl")
        
        # Ensure the directory exists
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Append to the log file (JSONL format)
        with open(log_file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception as e:
        # If local file write fails, just print the error but don't crash
        print(f"[WARNING] Could not write to local log file: {e}")


# Cache Utility Functions
class CacheManager:
    """Manages persistent caching across Modal functions."""

    def __init__(self, cache_dir: str = "/cache", logger=None):
        self.cache_dir = Path(cache_dir)
        self.logger = logger or logging.getLogger(__name__)

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_audio_hash(self, audio_file_path: str) -> str:
        """Generate MD5 hash of audio file for cache key."""
        import hashlib

        # Verify audio hash matches (basic security check)
        with open(audio_file_path, "rb") as f:
            audio_hash = hashlib.md5(f.read()).hexdigest()

        self.logger.debug(f"Generated audio hash: {audio_hash}")
        return audio_hash

    def cache_transcription_result(self, audio_hash: str, transcription_data: dict) -> None:
        """Cache transcription results by audio hash."""
        cache_file = self.cache_dir / f"transcription_{audio_hash}.json"

        with open(cache_file, "w") as f:
            json.dump(
                {"timestamp": datetime.datetime.now().isoformat(), "audio_hash": audio_hash, "transcription": transcription_data},
                f,
                indent=2,
            )

        self.logger.info(f"Cached transcription result for hash {audio_hash}")

    def get_cached_transcription_result(self, audio_hash: str) -> Optional[dict]:
        """Retrieve cached transcription result by audio hash."""
        cache_file = self.cache_dir / f"transcription_{audio_hash}.json"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r") as f:
                cached_data = json.load(f)

            self.logger.info(f"Found cached transcription result for hash {audio_hash}")
            return cached_data["transcription"]

        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Invalid transcription cache file for hash {audio_hash}: {e}")
            return None

    def clear_old_cache(self, max_age_days: int = 90) -> None:
        """Clear cache files older than specified days."""
        import time

        cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
        cleared_count = 0

        # Clear all JSON cache files older than the cutoff
        for cache_file in self.cache_dir.glob("*.json"):
            if cache_file.stat().st_mtime < cutoff_time:
                cache_file.unlink()
                cleared_count += 1

        # Also clear old preview videos
        for cache_file in self.cache_dir.glob("preview_*.mp4"):
            if cache_file.stat().st_mtime < cutoff_time:
                cache_file.unlink()
                cleared_count += 1

        if cleared_count > 0:
            self.logger.info(f"Cleared {cleared_count} old cache files")


def setup_cache_manager(job_id: str) -> CacheManager:
    """Set up cache manager for a job."""
    logger = logging.getLogger(__name__)
    cache_manager = CacheManager("/cache", logger)

    # Log cache directory status
    log_message(job_id, "INFO", f"Cache manager initialized: {cache_manager.cache_dir}")

    return cache_manager


def setup_rclone_config(job_id: str) -> bool:
    """Set up rclone configuration for cloud storage access."""
    try:
        log_message(job_id, "INFO", "Setting up rclone configuration")
        
        # Check if rclone.conf exists in the config volume
        rclone_source_file = Path("/config/rclone.conf")
        if not rclone_source_file.exists():
            log_message(job_id, "WARNING", "No rclone.conf file found in /config/")
            return False
            
        # Create rclone config directory
        rclone_config_dir = Path.home() / ".config" / "rclone"
        rclone_config_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy rclone configuration from config volume
        rclone_config_file = rclone_config_dir / "rclone.conf"
        import shutil
        shutil.copy2(rclone_source_file, rclone_config_file)
            
        log_message(job_id, "INFO", f"rclone configuration copied to {rclone_config_file}")
        
        # Test rclone configuration
        import subprocess
        result = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True)
        if result.returncode == 0:
            remotes = result.stdout.strip().split('\n') if result.stdout.strip() else []
            log_message(job_id, "INFO", f"rclone configured successfully. Available remotes: {remotes}")
            return True
        else:
            log_message(job_id, "ERROR", f"rclone configuration test failed: {result.stderr}")
            return False
            
    except Exception as e:
        log_message(job_id, "ERROR", f"Failed to setup rclone configuration: {str(e)}")
        return False


def get_finalization_config(job_id: str) -> Dict[str, Any]:
    """Get finalization configuration for KaraokeFinalise."""
    config = finalization_config_dict.get("config", {})
    
    # Set up default configuration
    default_config = {
        "enable_youtube_upload": False,
        "enable_discord_notifications": False,
        "enable_folder_organisation": False,
        "enable_public_share_copy": False,
        "enable_rclone_sync": False,
        "enable_email_drafts": False,
        "brand_prefix": "NOMAD",
        "organised_dir": "/output/organized",
        "organised_dir_rclone_root": "andrewdropboxfull:Tracks-Organized",
        "public_share_dir": "/output/public-share",
        "rclone_destination": "googledrive:Nomad Karaoke",
        "youtube_client_secrets_file": "/config/karaoke-finalise-client-secret.json",
        "youtube_description_file": "/config/youtube-video-description.txt",
        "discord_webhook_url": os.environ.get("DISCORD_WEBHOOK_URL", ""),
        "email_template_file": "/config/email-template.txt",
    }
    
    # Merge with stored configuration, but don't overwrite environment variables with empty strings
    merged_config = {**default_config, **config}
    
    # Special handling for discord_webhook_url: prefer environment variable if stored config is empty
    if not merged_config.get("discord_webhook_url") and os.environ.get("DISCORD_WEBHOOK_URL"):
        merged_config["discord_webhook_url"] = os.environ.get("DISCORD_WEBHOOK_URL")
    
    log_message(job_id, "DEBUG", f"Finalization config loaded: {list(merged_config.keys())}")
    
    return merged_config


# Add a cache warming function for common use cases
@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minute timeout for cache operations
    retries=0,
)
def warm_cache():
    """Warm up the cache with commonly used data."""
    try:
        cache_manager = CacheManager("/cache")

        # Check cache statistics for debugging
        cache_dir = cache_manager.cache_dir
        if cache_dir.exists():
            all_files = list(cache_dir.glob("*"))
            total_files = len([f for f in all_files if f.is_file()])
            total_size = sum(f.stat().st_size for f in all_files if f.is_file())

            print(f"Cache directory: {cache_dir}")
            print(f"Total cache files: {total_files}")
            print(f"Total cache size: {total_size / 1024 / 1024:.2f} MB")

            # Show breakdown by file type
            audioshake_files = len(list(cache_dir.glob("audioshake_*.json")))
            genius_files = len(list(cache_dir.glob("genius_*.json")))
            preview_files = len(list(cache_dir.glob("preview_*.mp4")))

            print(f"AudioShake cache files: {audioshake_files}")
            print(f"Genius cache files: {genius_files}")
            print(f"Preview video files: {preview_files}")

        print("Cache warming completed")
        return {"status": "success", "message": "Cache warmed successfully"}

    except Exception as e:
        print(f"Cache warming failed: {str(e)}")
        return {"status": "error", "message": str(e)}


# GPU Worker Functions
@app.function(
    image=karaoke_image,
    gpu="any",
    volumes=VOLUME_CONFIG,
    secrets=[modal.Secret.from_name("env-vars")],
    timeout=1800,
    retries=0,
)
async def process_part_one(job_id: str, youtube_url: str, cookies_str: Optional[str] = None, override_artist: Optional[str] = None, override_title: Optional[str] = None, styles_file_path: Optional[str] = None, styles_archive_path: Optional[str] = None):
    """First phase: Download audio, separate, and transcribe lyrics."""
    import sys
    import traceback

    try:
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(job_id)
        
        from core import ServerlessKaraokeProcessor

        log_message(job_id, "INFO", f"Starting job {job_id} for URL: {youtube_url}")

        # CRITICAL: Reload volume to see files written by other containers
        output_volume.reload()
        log_message(job_id, "DEBUG", "Output volume reloaded to fetch latest files")

        # Update status
        update_job_status_with_timeline(job_id, "processing", progress=10, url=youtube_url, created_at=datetime.datetime.now().isoformat())

        # Initialize processor - this now uses the same code path as the CLI
        processor = ServerlessKaraokeProcessor(model_dir="/models", output_dir="/output")

        # Verify styles files exist before processing
        verified_styles_file = None
        verified_styles_archive = None
        
        if styles_file_path:
            if Path(styles_file_path).exists():
                verified_styles_file = styles_file_path
                file_size = Path(styles_file_path).stat().st_size
                log_message(job_id, "INFO", f"Using styles file: {styles_file_path} ({file_size} bytes)")
            else:
                log_message(job_id, "WARNING", f"Styles file not found: {styles_file_path}")
                
        if styles_archive_path:
            if Path(styles_archive_path).exists():
                verified_styles_archive = styles_archive_path
                archive_size = Path(styles_archive_path).stat().st_size
                log_message(job_id, "INFO", f"Using styles archive: {styles_archive_path} ({archive_size} bytes)")
            else:
                log_message(job_id, "WARNING", f"Styles archive not found: {styles_archive_path}")
        
        # Process using the full KaraokePrep workflow (same as CLI)
        log_message(job_id, "INFO", "Starting full karaoke processing workflow...")
        result = await processor.process_url(job_id, youtube_url, cookies_str, override_artist, override_title, verified_styles_file, verified_styles_archive)

        # Update status to awaiting review
        update_job_status_with_timeline(
            job_id,
            "awaiting_review",
            progress=75,
            url=youtube_url,
            track_data=result["track_data"],
            track_output_dir=result["track_output_dir"],
            corrections_file=result.get("corrections_file"),
            styles_file_path=result.get("styles_file_path"),
        )

        log_message(job_id, "SUCCESS", f"Processing completed for job {job_id}. Ready for review.")

        return {"status": "success", "message": "Processing completed, ready for review"}

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        log_message(job_id, "ERROR", f"Phase 1 failed: {error_msg}")
        log_message(job_id, "ERROR", f"Traceback: {error_traceback}")

        update_job_status_with_timeline(job_id, "error", progress=0, url=youtube_url, error=error_msg, traceback=error_traceback)

        raise Exception(f"Phase 1 failed: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


@app.function(
    image=karaoke_image,
    gpu="any",
    volumes=VOLUME_CONFIG,
    secrets=[modal.Secret.from_name("env-vars")],
    timeout=1800,
    retries=0,
)
def process_part_two(job_id: str, updated_correction_data: Optional[Dict[str, Any]] = None):
    """Second phase: Generate 'With Vocals' video with corrected lyrics (no finalization yet)."""
    import sys
    import traceback
    from pathlib import Path

    try:
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(job_id)
        
        from lyrics_transcriber.output.generator import OutputGenerator
        from lyrics_transcriber.core.config import OutputConfig
        from lyrics_transcriber.types import CorrectionResult
        from lyrics_transcriber.correction.operations import CorrectionOperations

        log_message(job_id, "INFO", f"Starting phase 2 (video generation only) for job {job_id}")

        # Update status
        job_data = job_status_dict.get(job_id, {})
        update_job_status_with_timeline(
            job_id,
            "rendering",
            progress=80,
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]},
        )

        # Get job info
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")

        # Always load the original correction data from file first
        corrections_file_path = job_data.get("corrections_file")
        if not corrections_file_path:
            corrections_file_path = str(Path(track_output_dir) / "lyrics" / f"{artist} - {title} (Lyrics Corrections).json")

        log_message(job_id, "INFO", f"Loading original correction data from {corrections_file_path}")

        if not Path(corrections_file_path).exists():
            raise Exception(f"Corrections file not found: {corrections_file_path}")

        with open(corrections_file_path, "r") as f:
            original_corrections_data = json.load(f)

        base_correction_result = CorrectionResult.from_dict(original_corrections_data)

        # Apply updated data if provided
        if updated_correction_data:
            log_message(job_id, "INFO", "Applying updated correction data from review")
            correction_result = CorrectionOperations.update_correction_result_with_data(base_correction_result, updated_correction_data)
        else:
            log_message(job_id, "INFO", "Using original correction data (no updates from review)")
            correction_result = base_correction_result

        # Set up output config for Phase 2 (video generation only, no CDG yet)
        styles_file = job_data.get("styles_file_path") or str(Path(track_output_dir) / "styles_updated.json")
        output_config = OutputConfig(
            output_styles_json=styles_file,
            output_dir=str(Path(track_output_dir) / "lyrics"),
            render_video=True,  # Generate the "With Vocals" video
            generate_cdg=False,  # Skip CDG for now - will do in phase 3
            video_resolution="4k",
            generate_plain_text=False,  # Already done in Phase 1
            generate_lrc=False,  # Already done in Phase 1
            fetch_lyrics=False,  # Already done in Phase 1
            run_transcription=False,  # Already done in Phase 1
            run_correction=False,  # Already done in Phase 1
        )

        # Initialize output generator (logs will go to Modal's stdout, not captured in job log file)
        output_generator = OutputGenerator(config=output_config, logger=None)

        # Find the audio file - look for the actual downloaded file
        track_dir = Path(track_output_dir)
        audio_files = list(track_dir.glob(f"{artist} - {title}*.wav"))
        if not audio_files:
            raise Exception(f"No audio file found matching pattern: {artist} - {title}*.wav in {track_output_dir}")
        
        audio_file_path = audio_files[0]  # Use the first match
        log_message(job_id, "INFO", f"Found audio file: {audio_file_path}")

        log_message(job_id, "INFO", "Starting video generation with corrected lyrics...")

        # Generate "With Vocals" video only
        output_files = output_generator.generate_outputs(
            transcription_corrected=correction_result,
            lyrics_results={},  # Not needed for Phase 2
            output_prefix=f"{artist} - {title}",
            audio_filepath=str(audio_file_path),
            artist=artist,
            title=title,
        )

        # Move generated files to parent directory for easier access
        parent_video_path = Path(track_output_dir) / f"{artist} - {title} (With Vocals).mkv"
        parent_lrc_path = Path(track_output_dir) / f"{artist} - {title} (Karaoke).lrc"

        if output_files.video and Path(output_files.video).exists():
            log_message(job_id, "INFO", f"Moving video from {output_files.video} to {parent_video_path}")
            shutil.copy2(output_files.video, parent_video_path)

        if output_files.lrc and Path(output_files.lrc).exists():
            log_message(job_id, "INFO", f"Moving LRC from {output_files.lrc} to {parent_lrc_path}")
            shutil.copy2(output_files.lrc, parent_lrc_path)

        log_message(job_id, "SUCCESS", f"Video generation completed - ready for instrumental selection")

        # Commit volume changes to persist the "With Vocals" video for Phase 3
        log_message(job_id, "INFO", "Committing volume changes to persist Phase 2 video files...")
        output_volume.commit()
        log_message(job_id, "INFO", "Volume commit completed for Phase 2")

        # Update status to ready for instrumental selection and finalization
        update_job_status_with_timeline(
            job_id,
            "ready_for_finalization",
            progress=85,
            video_path=str(parent_video_path),
            lrc_path=str(parent_lrc_path),
            output_files_partial={"video": str(parent_video_path), "lrc": str(parent_lrc_path)},
            **{
                k: v
                for k, v in job_data.items()
                if k not in ["status", "progress", "timeline", "last_updated", "video_path", "lrc_path", "output_files_partial"]
            },
        )

        log_message(job_id, "SUCCESS", f"Phase 2 completed for job {job_id}! Ready for instrumental selection.")

        return {
            "status": "success",
            "message": "Video generation completed, ready for instrumental selection",
            "video_path": str(parent_video_path),
        }

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        log_message(job_id, "ERROR", f"Phase 2 failed: {error_msg}")
        log_message(job_id, "ERROR", f"Traceback: {error_traceback}")

        job_data = job_status_dict.get(job_id, {})
        update_job_status_with_timeline(
            job_id,
            "error",
            progress=0,
            error=error_msg,
            traceback=error_traceback,
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]},
        )

        raise Exception(f"Phase 2 failed: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


@app.function(
    image=karaoke_image,
    gpu="any",
    volumes=VOLUME_CONFIG,
    secrets=[modal.Secret.from_name("env-vars")],
    timeout=1800,
    retries=0,
    cpu=16.0,
    memory=16384,
)
def process_part_three(job_id: str, selected_instrumental: Optional[str] = None):
    """Third phase: Generate final video formats and packages with selected instrumental."""
    import sys
    import traceback
    from pathlib import Path

    try:
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(job_id)
        
        log_message(job_id, "INFO", f"Starting phase 3 (finalization) for job {job_id}")
        if selected_instrumental:
            log_message(job_id, "INFO", f"Using selected instrumental: {selected_instrumental}")

        # Update status
        job_data = job_status_dict.get(job_id, {})
        update_job_status_with_timeline(
            job_id,
            "finalizing",
            progress=90,
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]},
        )

        # Get job info
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")

        # Get user's finalization preferences
        finalization_options = job_data.get("finalization_options", {})
        user_upload_to_youtube = finalization_options.get("upload_to_youtube", False)
        
        log_message(job_id, "INFO", f"User's YouTube upload preference: {user_upload_to_youtube}")
        if user_upload_to_youtube:
            log_message(job_id, "INFO", "User requested YouTube upload - will attempt upload if credentials available")
        else:
            log_message(job_id, "INFO", "User opted out of YouTube upload - will skip upload even if configured")

        # Load CDG styles from the styles JSON file for KaraokeFinalise
        log_message(job_id, "INFO", "Loading CDG styles from styles configuration")

        styles_file = job_data.get("styles_file_path") or str(Path(track_output_dir) / "styles_updated.json")
        cdg_styles = None

        if Path(styles_file).exists():
            try:
                with open(styles_file, "r") as f:
                    style_params = json.load(f)
                    cdg_styles = style_params.get("cdg")
                    if cdg_styles:
                        log_message(job_id, "INFO", f"Loaded CDG styles from {styles_file}")
                    else:
                        log_message(job_id, "WARNING", f"No CDG styles found in {styles_file}")
            except Exception as e:
                log_message(job_id, "ERROR", f"Error loading CDG styles from {styles_file}: {str(e)}")
                raise Exception(f"Failed to load CDG styles: {str(e)}")
        else:
            log_message(job_id, "ERROR", f"Styles file not found: {styles_file}")
            raise Exception(f"Styles file not found: {styles_file}")

        # Now do finalization using the existing KaraokeFinalise class
        log_message(job_id, "INFO", "Starting finalization phase using KaraokeFinalise")

        # Import the existing finalization class
        from karaoke_gen.karaoke_finalise.karaoke_finalise import KaraokeFinalise

        # Change to the track directory for processing
        original_cwd = os.getcwd()
        os.chdir(track_output_dir)
        log_message(job_id, "INFO", f"Changed working directory to: {track_output_dir}")

        try:
            # Get finalization configuration
            config = get_finalization_config(job_id)
            
            # Set up rclone if needed
            rclone_available = False
            if config.get("enable_rclone_sync") or config.get("enable_folder_organisation"):
                rclone_available = setup_rclone_config(job_id)
                if not rclone_available:
                    log_message(job_id, "WARNING", "rclone setup failed, disabling cloud sync features")
            
            # Set up organized and public share directories
            organized_dir = None
            public_share_dir = None
            
            if config.get("enable_folder_organisation"):
                organized_dir = config.get("organised_dir")
                if organized_dir:
                    Path(organized_dir).mkdir(parents=True, exist_ok=True)
                    log_message(job_id, "INFO", f"Created organized directory: {organized_dir}")
                    
            if config.get("enable_public_share_copy"):
                public_share_dir = config.get("public_share_dir")
                if public_share_dir:
                    Path(public_share_dir).mkdir(parents=True, exist_ok=True)
                    # Create subdirectories expected by KaraokeFinalise
                    (Path(public_share_dir) / "MP4").mkdir(exist_ok=True)
                    (Path(public_share_dir) / "MP4-720p").mkdir(exist_ok=True)
                    (Path(public_share_dir) / "CDG").mkdir(exist_ok=True)
                    log_message(job_id, "INFO", f"Created public share directory structure: {public_share_dir}")
            
            log_message(job_id, "INFO", "Initializing KaraokeFinalise with configuration...")
            
            # Get user credentials for YouTube upload if enabled and user wants it
            youtube_credentials = None
            if config.get("enable_youtube_upload") and user_upload_to_youtube:
                log_message(job_id, "DEBUG", f"YouTube upload enabled in config and requested by user, checking for user credentials")
                
                # Get user from job data if available
                user_token = job_data.get("user_token")
                log_message(job_id, "DEBUG", f"User token from job data: {user_token[:8] + '...' if user_token else 'None'}")
                
                if user_token:
                    user_credentials = user_youtube_credentials_dict.get("user_credentials", {})
                    log_message(job_id, "DEBUG", f"Found {len(user_credentials)} user credential entries in storage")
                    
                    if user_token in user_credentials:
                        cred_data = user_credentials[user_token]
                        expires_at = cred_data.get("expires_at")
                        log_message(job_id, "DEBUG", f"Found credentials for user, expires_at: {expires_at}")
                        
                        # Check if credentials are not expired
                        if not expires_at or time.time() < expires_at:
                            youtube_credentials = cred_data["credentials"]
                            log_message(job_id, "INFO", "Using stored YouTube credentials for upload")
                        else:
                            log_message(job_id, "WARNING", f"YouTube credentials expired (expires_at: {expires_at}, current: {time.time()}), disabling upload")
                    else:
                        log_message(job_id, "WARNING", f"No YouTube credentials found for user token {user_token[:8]}..., disabling upload")
                        # Debug: show available user tokens
                        available_tokens = list(user_credentials.keys())
                        log_message(job_id, "DEBUG", f"Available user tokens: {[t[:8] + '...' for t in available_tokens]}")
                else:
                    log_message(job_id, "WARNING", "No user token in job data, disabling YouTube upload")
                    # Debug: show what keys are available in job_data
                    log_message(job_id, "DEBUG", f"Available job_data keys: {list(job_data.keys())}")
            elif config.get("enable_youtube_upload") and not user_upload_to_youtube:
                log_message(job_id, "INFO", "YouTube upload enabled in config but user opted out, skipping upload")
            else:
                log_message(job_id, "DEBUG", "YouTube upload not enabled in config or not requested by user")

            # Set up KaraokeFinalise with full configuration (logs go to Modal stdout)
            finalizer = KaraokeFinalise(
                logger=None,
                log_level=logging.DEBUG,
                dry_run=False,
                instrumental_format="flac",
                enable_cdg=True,  # Enable CDG creation
                enable_txt=True,  # Enable TXT creation
                brand_prefix=config.get("brand_prefix") if config.get("enable_folder_organisation") else None,
                organised_dir=organized_dir if config.get("enable_folder_organisation") else None,
                organised_dir_rclone_root=config.get("organised_dir_rclone_root") if config.get("enable_folder_organisation") and rclone_available else None,
                public_share_dir=public_share_dir if config.get("enable_public_share_copy") else None,
                youtube_client_secrets_file=config.get("youtube_client_secrets_file") if config.get("enable_youtube_upload") and Path(config.get("youtube_client_secrets_file", "")).exists() else None,
                youtube_description_file=config.get("youtube_description_file") if config.get("enable_youtube_upload") and Path(config.get("youtube_description_file", "")).exists() else None,
                rclone_destination=config.get("rclone_destination") if config.get("enable_rclone_sync") and rclone_available else None,
                discord_webhook_url=config.get("discord_webhook_url") if config.get("enable_discord_notifications") and config.get("discord_webhook_url") else None,
                email_template_file=config.get("email_template_file") if config.get("enable_email_drafts") and Path(config.get("email_template_file", "")).exists() else None,
                cdg_styles=cdg_styles,  # Pass CDG styles configuration
                non_interactive=True,  # CRITICAL: disable user prompts
                keep_brand_code=False,  # Don't keep existing brand code, generate new one
                user_youtube_credentials=youtube_credentials,  # Pass user's YouTube credentials
                server_side_mode=True,  # CRITICAL: enable server-side mode for Modal deployment
            )
                
            # Log which features are enabled
            features_enabled = []
            if finalizer.youtube_upload_enabled:
                features_enabled.append("YouTube upload")
            if finalizer.discord_notication_enabled:
                features_enabled.append("Discord notifications")
            if finalizer.folder_organisation_enabled:
                features_enabled.append("folder organization")
            if finalizer.public_share_copy_enabled:
                features_enabled.append("public share copy")
            if finalizer.public_share_rclone_enabled:
                features_enabled.append("rclone sync")
                
            log_message(job_id, "INFO", f"KaraokeFinalise configured with features: {', '.join(features_enabled) if features_enabled else 'basic video generation only'}")

            # Get the "With Vocals" video from phase 2 - search flexibly for the file
            base_name = f"{artist} - {title}"
            
            # Try different possible "With Vocals" video patterns and locations
            with_vocals_patterns = [
                f"{base_name} (With Vocals).mkv",
                f"{base_name} (With Vocals).mp4", 
                f"*{base_name}*With Vocals*.mkv",
                f"*{base_name}*With Vocals*.mp4"
            ]
            
            with_vocals_file = None
            current_dir = Path(".")
            
            # Search in current directory and subdirectories
            for pattern in with_vocals_patterns:
                # First try current directory
                matching_files = list(current_dir.glob(pattern))
                if matching_files:
                    with_vocals_file = matching_files[0]
                    break
                    
                # Then try recursive search
                matching_files = list(current_dir.rglob(pattern))
                if matching_files:
                    with_vocals_file = matching_files[0] 
                    break
            
            if not with_vocals_file or not with_vocals_file.exists():
                # List all files for debugging
                log_message(job_id, "ERROR", "With Vocals video not found. Directory contents:")
                for file_path in current_dir.rglob("*"):
                    if file_path.is_file():
                        log_message(job_id, "ERROR", f"  {file_path}")
                
                raise Exception(f"With Vocals video not found. Searched for patterns: {with_vocals_patterns}")

            log_message(job_id, "INFO", f"Found With Vocals video: {with_vocals_file}")
            
            # Convert to string for KaraokeFinalise compatibility
            with_vocals_file = str(with_vocals_file)

            # Find instrumental files
            base_name = f"{artist} - {title}"

            # If user selected a specific instrumental, create a symlink with expected name
            if selected_instrumental:
                log_message(job_id, "INFO", f"Using user-selected instrumental: {selected_instrumental}")
                # Create a symlink so KaraokeFinalise can find it with the expected naming
                expected_instrumental = f"{base_name} (Instrumental).flac"
                if not Path(expected_instrumental).exists():
                    Path(expected_instrumental).symlink_to(selected_instrumental)
                    log_message(job_id, "INFO", f"Created symlink: {expected_instrumental} -> {selected_instrumental}")

            log_message(job_id, "INFO", "About to start KaraokeFinalise.process() - this may take several minutes...")
            
            # Add timeout monitoring
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError("KaraokeFinalise.process() timed out")
            
            # Set a 45-minute timeout for the process call
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(45 * 60)  # 45 minutes
            
            try:
                # Let KaraokeFinalise handle all the video format creation and packaging
                log_message(job_id, "INFO", "Running KaraokeFinalise.process() for video formats and packages")
                result = finalizer.process(replace_existing=False)
                
                # Cancel the timeout
                signal.alarm(0)
                
                log_message(job_id, "SUCCESS", "KaraokeFinalise.process() completed successfully")
                
            except TimeoutError as e:
                signal.alarm(0)
                log_message(job_id, "ERROR", "KaraokeFinalise.process() timed out after 45 minutes")
                raise Exception("Finalization process timed out")
            except Exception as e:
                signal.alarm(0)
                log_message(job_id, "ERROR", f"KaraokeFinalise.process() failed: {str(e)}")
                raise

            # Extract the created files from the result
            final_files = {
                "lossless_4k": result.get("final_video"),
                "lossy_4k": result.get("final_video_lossy"),
                "mkv_flac": result.get("final_video_mkv"),
                "compressed_720p": result.get("final_video_720p"),
            }

            package_files = {}
            if result.get("final_karaoke_cdg_zip"):
                package_files["cdg_zip"] = result["final_karaoke_cdg_zip"]
            if result.get("final_karaoke_txt_zip"):
                package_files["txt_zip"] = result["final_karaoke_txt_zip"]

            # CRITICAL: Verify that final video files were actually created
            missing_files = []
            for file_type, file_path in final_files.items():
                if file_path and not Path(file_path).exists():
                    missing_files.append(f"{file_type}: {file_path}")
                elif file_path and Path(file_path).stat().st_size == 0:
                    missing_files.append(f"{file_type}: {file_path} (0 bytes)")

            if missing_files:
                error_msg = f"KaraokeFinalise completed but final video files are missing or empty: {missing_files}"
                log_message(job_id, "ERROR", error_msg)

                # List all files in directory for debugging
                log_message(job_id, "ERROR", "Current directory contents:")
                for file in Path(".").glob("*"):
                    size = file.stat().st_size if file.is_file() else "dir"
                    log_message(job_id, "ERROR", f"  {file.name}: {size} bytes" if size != "dir" else f"  {file.name}/")

                raise Exception(error_msg)

            log_message(
                job_id,
                "SUCCESS",
                f"KaraokeFinalise completed - created {len([f for f in final_files.values() if f])} video formats and {len(package_files)} packages",
            )

            # Log the actual files that were created for verification
            for file_type, file_path in final_files.items():
                if file_path and Path(file_path).exists():
                    file_size = Path(file_path).stat().st_size
                    log_message(job_id, "INFO", f"Created {file_type}: {file_path} ({file_size} bytes)")

        finally:
            # Always return to original directory
            os.chdir(original_cwd)
            log_message(job_id, "DEBUG", f"Restored working directory to: {original_cwd}")

        log_message(
            job_id,
            "SUCCESS",
            f"Finalization completed - created {len([f for f in final_files.values() if f])} video formats and {len(package_files)} packages",
        )

        # CRITICAL: Commit volume changes to persist final video files
        log_message(job_id, "INFO", "Committing volume changes to persist final video files...")
        output_volume.commit()
        log_message(job_id, "INFO", "Volume commit completed - final files should now be persistent")

        # Update status to complete with all file information
        best_video_path = final_files.get("lossless_4k") or final_files.get("lossy_4k") or ""
        update_job_status_with_timeline(
            job_id,
            "complete",
            progress=100,
            video_path=str(best_video_path),
            lrc_path=str(Path(track_output_dir) / f"{artist} - {title} (Karaoke).lrc"),
            video_url=f"/api/jobs/{job_id}/download",
            files_url=f"/api/jobs/{job_id}/files",
            download_all_url=f"/api/jobs/{job_id}/download-all",
            final_files=final_files,
            package_files=package_files,
            selected_instrumental=selected_instrumental,
            # Add YouTube URL and Dropbox sharing link from KaraokeFinalise result
            youtube_url=result.get("youtube_url"),
            brand_code=result.get("brand_code"),
            brand_code_dir_sharing_link=result.get("brand_code_dir_sharing_link"),
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated", "video_path", "lrc_path"]},
        )

        log_message(job_id, "SUCCESS", f"Job {job_id} completed successfully!")

        return {"status": "success", "message": "Finalization completed", "final_files": final_files}

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        log_message(job_id, "ERROR", f"Phase 3 failed: {error_msg}")
        log_message(job_id, "ERROR", f"Traceback: {error_traceback}")

        job_data = job_status_dict.get(job_id, {})
        update_job_status_with_timeline(
            job_id,
            "error",
            progress=0,
            error=error_msg,
            traceback=error_traceback,
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]},
        )

        raise Exception(f"Phase 3 failed: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=60,  # Short timeout since we're not running a persistent server
    retries=0,
)
def prepare_review_data(job_id: str):
    """Prepare correction data for external review interface."""
    from pathlib import Path
    import json

    try:
        log_message(job_id, "INFO", f"Preparing review data for job {job_id}")

        # CRITICAL: Reload the volume to see files written by other containers
        output_volume.reload()

        # Check if job data exists
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise Exception(f"Job {job_id} not found")

        # Debug logging to see what job_data contains
        log_message(job_id, "DEBUG", f"Job data keys: {list(job_data.keys())}")
        log_message(job_id, "DEBUG", f"Artist from job_data: {job_data.get('artist')}")
        log_message(job_id, "DEBUG", f"Title from job_data: {job_data.get('title')}")

        # Try to extract artist/title from track_data if main job_data doesn't have them
        artist = job_data.get("artist")
        title = job_data.get("title")
        
        if not artist or not title:
            track_data = job_data.get("track_data", {})
            if track_data:
                artist = artist or track_data.get("artist")
                title = title or track_data.get("title")
                log_message(job_id, "DEBUG", f"Extracted from track_data - Artist: {artist}, Title: {title}")

        # Get the corrections file path from job data
        corrections_file_path = job_data.get("corrections_file")
        
        if not corrections_file_path:
            # Fallback to constructing the path
            track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
            
            if artist and title:
                corrections_file_path = str(
                    Path(track_output_dir) / "lyrics" / f"{artist} - {title} (Lyrics Corrections).json"
                )
                log_message(job_id, "DEBUG", f"Constructed path with artist/title: {corrections_file_path}")
            else:
                # Last resort: scan the lyrics directory for any corrections file
                lyrics_dir = Path(track_output_dir) / "lyrics"
                if lyrics_dir.exists():
                    corrections_files = list(lyrics_dir.glob("*Lyrics Corrections*.json"))
                    if corrections_files:
                        corrections_file_path = str(corrections_files[0])
                        log_message(job_id, "INFO", f"Found corrections file by scanning: {corrections_file_path}")
                        
                        # Try to extract artist/title from the filename
                        filename = corrections_files[0].stem
                        if " (Lyrics Corrections)" in filename:
                            artist_title = filename.replace(" (Lyrics Corrections)", "")
                            if " - " in artist_title:
                                artist, title = artist_title.split(" - ", 1)
                                log_message(job_id, "INFO", f"Extracted from filename - Artist: {artist}, Title: {title}")
                    else:
                        log_message(job_id, "ERROR", f"No corrections files found in {lyrics_dir}")
                        corrections_file_path = str(lyrics_dir / "Unknown - Unknown (Lyrics Corrections).json")
                else:
                    log_message(job_id, "ERROR", f"Lyrics directory not found: {lyrics_dir}")
                    corrections_file_path = str(Path(track_output_dir) / "lyrics" / "Unknown - Unknown (Lyrics Corrections).json")

        corrections_json_path = Path(corrections_file_path)
        log_message(job_id, "DEBUG", f"Final corrections file path: {corrections_json_path}")
        log_message(job_id, "DEBUG", f"File exists: {corrections_json_path.exists()}")

        if not corrections_json_path.exists():
            # List files in the lyrics directory for debugging
            lyrics_dir = corrections_json_path.parent
            if lyrics_dir.exists():
                all_files = list(lyrics_dir.glob("*"))
                log_message(job_id, "ERROR", f"Files in lyrics directory: {[f.name for f in all_files]}")
            
            raise Exception(f"Corrections data not found at {corrections_json_path}")

        # Load the correction data
        with open(corrections_json_path, "r") as f:
            corrections_data = json.load(f)

        log_message(job_id, "INFO", f"Review data prepared for job {job_id}")

        # Update job status to indicate review is active, preserving artist/title
        update_job_status_with_timeline(
            job_id,
            "reviewing",
            progress=77,
            artist=artist,
            title=title,
            corrections_file=str(corrections_json_path),
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated", "artist", "title", "corrections_file"]},
        )

        return {
            "status": "success",
            "corrections_data": corrections_data,
            "job_id": job_id,
            "artist": artist,
            "title": title,
        }

    except Exception as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Review data preparation failed: {error_msg}")

        # Update job status to error
        job_data = job_status_dict.get(job_id, {})
        update_job_status_with_timeline(
            job_id,
            "error",
            error=error_msg,
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]},
        )

        raise


@app.function(
    image=karaoke_image,
    gpu="any",
    volumes=VOLUME_CONFIG,
    secrets=[modal.Secret.from_name("env-vars")],
    timeout=1800,
    retries=0,
)
async def process_part_one_uploaded(
    job_id: str,
    audio_file_path: str,
    artist: str,
    title: str,
    styles_file_path: Optional[str] = None,
    styles_archive_path: Optional[str] = None,
):
    """First phase: Process uploaded audio file, separate, and transcribe lyrics."""
    import sys
    import traceback

    try:
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(job_id)
        
        # Set up cache manager
        cache_manager = setup_cache_manager(job_id)

        from core import ServerlessKaraokeProcessor

        log_message(job_id, "INFO", f"Starting job {job_id} for uploaded file: {audio_file_path}")
        log_message(job_id, "INFO", f"Artist: {artist}, Title: {title}")

        # CRITICAL: Reload the volume to see files written by other containers
        output_volume.reload()
        cache_volume.reload()  # Also reload cache volume
        log_message(job_id, "DEBUG", "Volumes reloaded to fetch latest changes")

        # Verify the uploaded file exists before processing
        audio_path = Path(audio_file_path)
        if not audio_path.exists():
            raise Exception(f"Uploaded file not found: {audio_file_path}")

        file_size = audio_path.stat().st_size
        if file_size == 0:
            raise Exception(f"Uploaded file is empty: {audio_file_path}")

        log_message(job_id, "INFO", f"File verified: {audio_path.name} ({file_size} bytes)")

        # Generate audio hash for caching
        log_message(job_id, "DEBUG", "About to generate audio hash for caching...")
        audio_hash = cache_manager.get_audio_hash(audio_file_path)
        log_message(job_id, "INFO", f"Audio hash generated: {audio_hash}")

        # Check if we have cached results for this exact audio
        log_message(job_id, "DEBUG", "Checking for cached transcription results...")
        cached_transcription = cache_manager.get_cached_transcription_result(audio_hash)
        if cached_transcription:
            log_message(job_id, "INFO", "Found cached transcription result, skipping processing")
            # You could return cached results here, but for now we'll continue processing
            # This is useful for development/testing scenarios
        else:
            log_message(job_id, "DEBUG", "No cached results found, proceeding with processing")

        # Update status
        log_message(job_id, "DEBUG", "Updating job status to processing...")
        update_job_status_with_timeline(
            job_id,
            "processing",
            progress=10,
            artist=artist,
            title=title,
            filename=Path(audio_file_path).name,
            audio_hash=audio_hash,  # Store audio hash for potential future use
            created_at=datetime.datetime.now().isoformat(),
        )
        log_message(job_id, "DEBUG", "Job status updated successfully")

        # Initialize processor - this now uses the same code path as the CLI
        log_message(job_id, "DEBUG", "Initializing ServerlessKaraokeProcessor...")
        processor = ServerlessKaraokeProcessor(model_dir="/models", output_dir="/output")
        log_message(job_id, "DEBUG", "ServerlessKaraokeProcessor initialized successfully")

        # Process using the full KaraokePrep workflow (same as CLI)
        log_message(job_id, "INFO", "Starting full karaoke processing workflow...")
        if styles_file_path:
            log_message(job_id, "INFO", f"Using custom styles from: {styles_file_path}")
        result = await processor.process_uploaded_file(job_id, audio_file_path, artist, title, styles_file_path, styles_archive_path)

        # Cache the processing results for future use
        if result.get("track_data"):
            cache_manager.cache_transcription_result(
                audio_hash,
                {
                    "artist": artist,
                    "title": title,
                    "track_data": result["track_data"],
                    "track_output_dir": result["track_output_dir"],
                    "status": result["status"],
                },
            )

        # Update status to awaiting review
        update_job_status_with_timeline(
            job_id,
            result["status"],  # Use the status from result (either "awaiting_review" or "complete")
            progress=75,
            artist=artist,
            title=title,
            track_data=result["track_data"],
            track_output_dir=result["track_output_dir"],
            corrections_file=result.get("corrections_file"),  # Store corrections file path if available
            styles_file_path=result.get("styles_file_path"),  # Use updated styles file path from result
            audio_hash=audio_hash,  # Keep the audio hash for potential future use
        )

        log_message(job_id, "SUCCESS", f"Processing completed for job {job_id}. Ready for review.")

        return {"status": "success", "message": "Processing completed, ready for review"}

    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()

        log_message(job_id, "ERROR", f"Phase 1 failed: {error_msg}")
        log_message(job_id, "ERROR", f"Traceback: {error_traceback}")

        update_job_status_with_timeline(job_id, "error", progress=0, artist=artist, title=title, error=error_msg, traceback=error_traceback)

        raise Exception(f"Phase 1 failed: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


# Removed setup_lyrics_review function - now using full KaraokePrep workflow


# Authentication functions (must be defined before FastAPI routes)
def generate_session_token(original_token: str) -> str:
    """Generate a secure session token from the original access token."""
    timestamp = str(int(time.time()))
    combined = f"{original_token}:{timestamp}:{os.environ.get('AUTH_SECRET', 'default-secret')}"
    return hashlib.sha256(combined.encode()).hexdigest()


def validate_token(token: str) -> tuple[bool, UserType, int, str]:
    """
    Validate an access token and return (is_valid, user_type, remaining_uses, message).
    """
    if not token:
        return False, UserType.LIMITED, 0, "No token provided"

    # Check for admin tokens (from environment variables)
    admin_tokens = os.environ.get("ADMIN_TOKENS", "").split(",")
    admin_tokens = [t.strip() for t in admin_tokens if t.strip()]

    if token in admin_tokens:
        return True, UserType.ADMIN, -1, "Admin access granted"

    # Check stored tokens
    stored_tokens = auth_tokens_dict.get("tokens", {})

    if token not in stored_tokens:
        return False, UserType.LIMITED, 0, "Invalid token"

    token_data = stored_tokens[token]
    token_type = UserType(token_data["type"])
    max_uses = token_data.get("max_uses", -1)

    # Check if token is still active
    if not token_data.get("active", True):
        return False, token_type, 0, "Token has been revoked"

    # For unlimited tokens, no usage check needed
    if token_type == UserType.UNLIMITED:
        return True, token_type, -1, "Unlimited access granted"

    # For limited tokens, check usage
    if token_type == UserType.LIMITED:
        if max_uses <= 0:  # Unlimited uses
            return True, token_type, -1, "Limited token with unlimited uses"

        usage_data = token_usage_dict.get(token, {"uses": 0})
        remaining_uses = max_uses - usage_data["uses"]

        if remaining_uses <= 0:
            return False, token_type, 0, "Token usage limit exceeded"

        return True, token_type, remaining_uses, f"Limited token: {remaining_uses} uses remaining"

    # For Stripe tokens, check expiration and usage
    if token_type == UserType.STRIPE:
        # Add Stripe-specific validation logic here
        created_at = token_data.get("created_at", 0)
        expires_at = token_data.get("expires_at", 0)
        current_time = time.time()

        if expires_at > 0 and current_time > expires_at:
            return False, token_type, 0, "Token has expired"

        if max_uses > 0:
            usage_data = token_usage_dict.get(token, {"uses": 0})
            remaining_uses = max_uses - usage_data["uses"]

            if remaining_uses <= 0:
                return False, token_type, 0, "Token usage limit exceeded"

            return True, token_type, remaining_uses, f"Stripe token: {remaining_uses} uses remaining"

        return True, token_type, -1, "Stripe access granted"

    return False, UserType.LIMITED, 0, "Unknown token type"


def increment_token_usage(token: str) -> bool:
    """
    Increment the usage count for a token. Returns True if successful.
    """
    # Don't track usage for admin or unlimited tokens
    is_valid, user_type, remaining_uses, _ = validate_token(token)

    if not is_valid:
        return False

    if user_type in [UserType.ADMIN, UserType.UNLIMITED]:
        return True  # No usage tracking needed

    # Increment usage for limited and stripe tokens
    usage_data = token_usage_dict.get(token, {"uses": 0, "last_used": 0})
    usage_data["uses"] += 1
    usage_data["last_used"] = time.time()
    token_usage_dict[token] = usage_data

    return True


def track_job_usage(token: str, job_id: str) -> bool:
    """Track that a token was used to create a job."""
    if not increment_token_usage(token):
        return False

    # Store job creation record
    usage_data = token_usage_dict.get(token, {})
    if "jobs" not in usage_data:
        usage_data["jobs"] = []

    usage_data["jobs"].append({"job_id": job_id, "created_at": time.time()})

    token_usage_dict[token] = usage_data
    return True


# Authentication dependency for FastAPI
security = HTTPBearer(auto_error=False)


async def authenticate_user_or_token(request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    FastAPI dependency to authenticate users via Authorization header OR token query parameter.
    This enables direct download links with token in URL.
    """
    token = None

    # First try to get token from Authorization header
    if credentials:
        token = credentials.credentials

    # If no header token, try query parameter
    if not token:
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check if this is a session token
    session_data = user_sessions_dict.get(token)
    if session_data:
        # This is a session token - validate the original token
        original_token = session_data["original_token"]
        is_valid, user_type, remaining_uses, message = validate_token(original_token)

        if not is_valid:
            # Original token is no longer valid - remove session
            del user_sessions_dict[token]
            raise HTTPException(status_code=401, detail=f"Authentication failed: {message}")

        # Update session last used time
        session_data["last_used"] = time.time()
        user_sessions_dict[token] = session_data

        return {
            "token": original_token,  # Return original token for usage tracking
            "session_token": token,  # Include session token for cookie association
            "user_type": user_type,
            "remaining_uses": remaining_uses,
            "admin_access": user_type == UserType.ADMIN,
            "message": message,
        }

    # If not a session token, validate as direct access token
    is_valid, user_type, remaining_uses, message = validate_token(token)

    if not is_valid:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {message}")

    return {
        "token": token,
        "user_type": user_type,
        "remaining_uses": remaining_uses,
        "admin_access": user_type == UserType.ADMIN,
        "message": message,
    }


async def authenticate_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """
    FastAPI dependency to authenticate users on protected endpoints.
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    # First check if this is a session token
    session_data = user_sessions_dict.get(token)
    if session_data:
        # This is a session token - validate the original token
        original_token = session_data["original_token"]
        is_valid, user_type, remaining_uses, message = validate_token(original_token)

        if not is_valid:
            # Original token is no longer valid - remove session
            del user_sessions_dict[token]
            raise HTTPException(status_code=401, detail=f"Authentication failed: {message}")

        # Update session last used time
        session_data["last_used"] = time.time()
        user_sessions_dict[token] = session_data

        return {
            "token": original_token,  # Return original token for usage tracking
            "session_token": token,  # Include session token for cookie association
            "user_type": user_type,
            "remaining_uses": remaining_uses,
            "admin_access": user_type == UserType.ADMIN,
            "message": message,
        }

    # If not a session token, validate as direct access token
    is_valid, user_type, remaining_uses, message = validate_token(token)

    if not is_valid:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {message}")

    return {
        "token": token,
        "user_type": user_type,
        "remaining_uses": remaining_uses,
        "admin_access": user_type == UserType.ADMIN,
        "message": message,
    }


async def authenticate_admin(user: dict = Depends(authenticate_user)) -> dict:
    """
    FastAPI dependency to authenticate admin users only.
    """
    if user["user_type"] != UserType.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")

    return user


# FastAPI Application for API endpoints
api_app = FastAPI(title="Karaoke Generator API", version="1.0.0")

# Add CORS middleware
api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Authentication API Routes
@api_app.post("/api/auth/login")
async def login(auth_request: AuthRequest):
    """Authenticate a user with their access token."""
    try:
        token = auth_request.token.strip()
        is_valid, user_type, remaining_uses, message = validate_token(token)

        if not is_valid:
            return JSONResponse({"success": False, "message": message}, status_code=401)

        # Generate a session token for the frontend
        session_token = generate_session_token(token)

        # Store session data
        session_data = {
            "original_token": token,
            "user_type": user_type.value,
            "remaining_uses": remaining_uses,
            "created_at": time.time(),
            "last_used": time.time(),
        }
        user_sessions_dict[session_token] = session_data

        return JSONResponse(
            {
                "success": True,
                "user_type": user_type.value,
                "remaining_uses": remaining_uses,
                "admin_access": user_type == UserType.ADMIN,
                "message": message,
                "access_token": session_token,
            }
        )

    except Exception as e:
        return JSONResponse({"success": False, "message": f"Authentication error: {str(e)}"}, status_code=500)


@api_app.post("/api/auth/validate")
async def validate_auth(user: dict = Depends(authenticate_user)):
    """Validate the current user's authentication status."""
    return JSONResponse(
        {
            "success": True,
            "user_type": user["user_type"].value,
            "remaining_uses": user["remaining_uses"],
            "admin_access": user["admin_access"],
            "message": user["message"],
        }
    )


@api_app.post("/api/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Logout the current user by invalidating their session."""
    if credentials:
        session_token = credentials.credentials
        if session_token in user_sessions_dict:
            del user_sessions_dict[session_token]

    return JSONResponse({"success": True, "message": "Logged out successfully"})


# Admin-only authentication management routes
@api_app.post("/api/admin/tokens/create")
async def create_token(request: CreateTokenRequest, admin: dict = Depends(authenticate_admin)):
    """Create a new access token (admin only)."""
    try:
        stored_tokens = auth_tokens_dict.get("tokens", {})

        token_data = {
            "type": request.token_type.value,
            "max_uses": request.max_uses,
            "description": request.description,
            "created_at": time.time(),
            "created_by": admin["token"][:8] + "...",
            "active": True,
        }

        # For Stripe tokens, add expiration if needed
        if request.token_type == UserType.STRIPE:
            # Default 30 days expiration for Stripe tokens
            token_data["expires_at"] = time.time() + (30 * 24 * 60 * 60)

        stored_tokens[request.token_value] = token_data
        auth_tokens_dict["tokens"] = stored_tokens

        return JSONResponse({"success": True, "message": f"Token '{request.token_value}' created successfully", "token_data": token_data})

    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error creating token: {str(e)}"}, status_code=500)


@api_app.get("/api/admin/tokens/list")
async def list_tokens(admin: dict = Depends(authenticate_admin)):
    """List all access tokens (admin only)."""
    try:
        stored_tokens = auth_tokens_dict.get("tokens", {})

        # Add usage information to each token
        token_list = []
        for token_value, token_data in stored_tokens.items():
            usage_data = token_usage_dict.get(token_value, {"uses": 0})

            token_info = {
                "token": token_value,
                "type": token_data["type"],
                "max_uses": token_data.get("max_uses", -1),
                "current_uses": usage_data.get("uses", 0),
                "description": token_data.get("description"),
                "created_at": token_data.get("created_at"),
                "active": token_data.get("active", True),
                "last_used": usage_data.get("last_used"),
                "jobs_created": len(usage_data.get("jobs", [])),
            }

            # Add expiration info for Stripe tokens
            if token_data["type"] == "stripe":
                token_info["expires_at"] = token_data.get("expires_at")
                token_info["expired"] = token_data.get("expires_at", 0) < time.time()

            token_list.append(token_info)

        return JSONResponse({"success": True, "tokens": token_list})

    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error listing tokens: {str(e)}"}, status_code=500)


@api_app.post("/api/admin/tokens/{token_value}/revoke")
async def revoke_token(token_value: str, admin: dict = Depends(authenticate_admin)):
    """Revoke an access token (admin only)."""
    try:
        stored_tokens = auth_tokens_dict.get("tokens", {})

        if token_value not in stored_tokens:
            return JSONResponse({"success": False, "message": "Token not found"}, status_code=404)

        stored_tokens[token_value]["active"] = False
        stored_tokens[token_value]["revoked_at"] = time.time()
        stored_tokens[token_value]["revoked_by"] = admin["token"][:8] + "..."

        auth_tokens_dict["tokens"] = stored_tokens

        return JSONResponse({"success": True, "message": f"Token '{token_value}' revoked successfully"})

    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error revoking token: {str(e)}"}, status_code=500)


# YouTube OAuth Management  
class YouTubeAuthRequest(BaseModel):
    authorization_code: str
    redirect_uri: str


@api_app.get("/api/youtube/auth-url")
async def get_youtube_auth_url(user: dict = Depends(authenticate_user)):
    """Get YouTube OAuth authorization URL for user authentication."""
    try:
        from google_auth_oauthlib.flow import Flow
        import secrets
        
        # Get YouTube client secrets file path
        config = get_finalization_config("youtube_auth")
        youtube_secrets_file = config.get("youtube_client_secrets_file")
        
        if not youtube_secrets_file or not Path(youtube_secrets_file).exists():
            return JSONResponse({
                "success": False,
                "message": "YouTube OAuth not configured. Please contact admin to set up YouTube client secrets."
            }, status_code=400)
        
        # Generate state parameter for security
        state = secrets.token_urlsafe(32)
        
        # Store state associated with user for verification
        user_token = user["token"]
        auth_states = user_youtube_credentials_dict.get("auth_states", {})
        auth_states[state] = {
            "user_token": user_token,
            "created_at": time.time(),
            "expires_at": time.time() + 600  # 10 minute expiry
        }
        user_youtube_credentials_dict["auth_states"] = auth_states
        
        # Create OAuth flow
        flow = Flow.from_client_secrets_file(
            youtube_secrets_file,
            scopes=['https://www.googleapis.com/auth/youtube'],
            redirect_uri=f"{get_base_api_url()}/api/youtube/oauth-callback"
        )
        
        # Generate authorization URL
        authorization_url, _ = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            state=state
        )
        
        return JSONResponse({
            "success": True,
            "authorization_url": authorization_url,
            "state": state,
            "message": "Open this URL in a new tab to authenticate with YouTube"
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"Error generating YouTube auth URL: {str(e)}"
        }, status_code=500)


@api_app.get("/api/youtube/oauth-callback")
async def youtube_oauth_callback(request: Request):
    """Handle YouTube OAuth callback and store credentials."""
    try:
        from google_auth_oauthlib.flow import Flow
        import pickle
        import base64
        
        # Get query parameters
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        error = request.query_params.get('error')
        
        if error:
            return JSONResponse({
                "success": False,
                "message": f"YouTube authorization denied: {error}"
            }, status_code=400)
        
        if not code or not state:
            return JSONResponse({
                "success": False,
                "message": "Missing authorization code or state parameter"
            }, status_code=400)
        
        # Verify state parameter
        auth_states = user_youtube_credentials_dict.get("auth_states", {})
        if state not in auth_states:
            return JSONResponse({
                "success": False,
                "message": "Invalid or expired state parameter"
            }, status_code=400)
        
        state_data = auth_states[state]
        if time.time() > state_data["expires_at"]:
            return JSONResponse({
                "success": False,
                "message": "Authorization state expired. Please try again."
            }, status_code=400)
        
        user_token = state_data["user_token"]
        
        # Clean up used state
        del auth_states[state]
        user_youtube_credentials_dict["auth_states"] = auth_states
        
        # Get YouTube client secrets
        config = get_finalization_config("youtube_auth")
        youtube_secrets_file = config.get("youtube_client_secrets_file")
        
        # Complete OAuth flow
        flow = Flow.from_client_secrets_file(
            youtube_secrets_file,
            scopes=['https://www.googleapis.com/auth/youtube'],
            redirect_uri=f"{get_base_api_url()}/api/youtube/oauth-callback"
        )
        
        # Exchange authorization code for tokens
        flow.fetch_token(code=code)
        
        # Serialize credentials for storage
        credentials = flow.credentials
        credentials_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Store credentials associated with user
        user_credentials = user_youtube_credentials_dict.get("user_credentials", {})
        user_credentials[user_token] = {
            "credentials": credentials_data,
            "created_at": time.time(),
            "expires_at": credentials.expiry.timestamp() if credentials.expiry else None
        }
        user_youtube_credentials_dict["user_credentials"] = user_credentials
        
        # Return success page
        success_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>YouTube Authentication Success</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
                .success { color: #28a745; font-size: 24px; margin-bottom: 20px; }
                .instructions { color: #666; margin-bottom: 30px; }
                .close-btn { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; }
            </style>
            <script>
                // Close window automatically after showing success
                setTimeout(() => {
                    if (window.opener) {
                        window.opener.postMessage({ type: 'youtube_auth_success' }, '*');
                        window.close();
                    }
                }, 2000);
            </script>
        </head>
        <body>
            <div class="success">✅ YouTube Authentication Successful!</div>
            <div class="instructions">
                You can now upload videos to YouTube. This window will close automatically.
            </div>
            <button class="close-btn" onclick="window.close()">Close Window</button>
        </body>
        </html>
        """
        return HTMLResponse(content=success_html)
        
    except Exception as e:
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>YouTube Authentication Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; padding: 50px; }}
                .error {{ color: #dc3545; font-size: 24px; margin-bottom: 20px; }}
                .details {{ color: #666; margin-bottom: 30px; }}
            </style>
        </head>
        <body>
            <div class="error">❌ YouTube Authentication Failed</div>
            <div class="details">Error: {str(e)}</div>
            <button onclick="window.close()">Close Window</button>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html)


@api_app.get("/api/youtube/auth-status")
async def get_youtube_auth_status(user: dict = Depends(authenticate_user)):
    """Get current YouTube authentication status for user."""
    try:
        user_token = user["token"]
        user_credentials = user_youtube_credentials_dict.get("user_credentials", {})
        
        if user_token not in user_credentials:
            return JSONResponse({
                "success": True,
                "authenticated": False,
                "message": "Not authenticated with YouTube"
            })
        
        cred_data = user_credentials[user_token]
        expires_at = cred_data.get("expires_at")
        
        # Check if credentials are expired
        is_expired = expires_at and time.time() > expires_at
        
        return JSONResponse({
            "success": True,
            "authenticated": not is_expired,
            "expires_at": expires_at,
            "created_at": cred_data.get("created_at"),
            "message": "Authenticated with YouTube" if not is_expired else "YouTube credentials expired"
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"Error checking YouTube auth status: {str(e)}"
        }, status_code=500)


@api_app.delete("/api/youtube/auth")
async def revoke_youtube_auth(user: dict = Depends(authenticate_user)):
    """Revoke user's YouTube authentication."""
    try:
        user_token = user["token"]
        user_credentials = user_youtube_credentials_dict.get("user_credentials", {})
        
        # First, revoke the token with Google's servers if we have credentials
        if user_token in user_credentials:
            try:
                from google.oauth2.credentials import Credentials
                import requests
                
                cred_data = user_credentials[user_token]
                credentials_data = cred_data["credentials"]
                
                # Create credentials object
                credentials = Credentials(
                    token=credentials_data['token'],
                    refresh_token=credentials_data.get('refresh_token'),
                    token_uri=credentials_data.get('token_uri'),
                    client_id=credentials_data.get('client_id'),
                    client_secret=credentials_data.get('client_secret'),
                    scopes=credentials_data.get('scopes')
                )
                
                # Revoke with Google's servers
                revoke_url = f"https://oauth2.googleapis.com/revoke?token={credentials.token}"
                response = requests.post(revoke_url)
                
                if response.status_code == 200:
                    print(f"Successfully revoked token with Google for user {user_token[:8]}...")
                else:
                    print(f"Warning: Failed to revoke token with Google (status {response.status_code}), but proceeding with local deletion")
                    
            except Exception as revoke_error:
                print(f"Warning: Error revoking token with Google: {str(revoke_error)}, but proceeding with local deletion")
            
            # Always delete from local storage regardless of Google revocation result
            del user_credentials[user_token]
            user_youtube_credentials_dict["user_credentials"] = user_credentials
        
        return JSONResponse({
            "success": True,
            "message": "YouTube authentication revoked successfully"
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"Error revoking YouTube auth: {str(e)}"
        }, status_code=500)


# YouTube Cookie Management (Admin Only)
class UpdateCookiesRequest(BaseModel):
    cookies: str


@api_app.get("/api/admin/cookies/status")
async def get_cookie_status(admin: dict = Depends(authenticate_admin)):
    """Get current YouTube cookie status (admin only)."""
    try:
        cookie_data = user_youtube_cookies_dict.get("admin_cookies", {})
        
        has_cookies = bool(cookie_data.get("cookies"))
        last_updated = cookie_data.get("updated_at")
        
        # Consider cookies expired if they're older than 30 days
        is_expired = False
        if has_cookies and last_updated:
            cookie_age_days = (time.time() - last_updated) / (24 * 60 * 60)
            is_expired = cookie_age_days > 30
        
        return JSONResponse({
            "success": True,
            "has_cookies": has_cookies,
            "last_updated": last_updated,
            "is_expired": is_expired,
            "cookie_age_days": int((time.time() - last_updated) / (24 * 60 * 60)) if last_updated else None
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error getting cookie status: {str(e)}"}, status_code=500)


@api_app.post("/api/admin/cookies/update")
async def update_cookies(request: UpdateCookiesRequest, admin: dict = Depends(authenticate_admin)):
    """Update stored YouTube cookies (admin only)."""
    try:
        cookies_str = request.cookies.strip()
        
        if not cookies_str:
            return JSONResponse({"success": False, "message": "Cookie data cannot be empty"}, status_code=400)
        
        # Basic validation - cookies should contain expected YouTube cookie names
        expected_cookies = ["VISITOR_INFO1_LIVE", "YSC"]  # Common YouTube cookies
        has_expected = any(cookie_name in cookies_str for cookie_name in expected_cookies)
        
        if not has_expected:
            return JSONResponse({
                "success": False, 
                "message": f"Cookie data does not appear to contain YouTube cookies. Expected to find one of: {expected_cookies}"
            }, status_code=400)
        
        # Store cookies with metadata
        cookie_data = {
            "cookies": cookies_str,
            "updated_at": time.time(),
            "updated_by": admin["token"][:8] + "...",
            "character_count": len(cookies_str)
        }
        
        user_youtube_cookies_dict["admin_cookies"] = cookie_data
        
        return JSONResponse({
            "success": True, 
            "message": f"YouTube cookies updated successfully ({len(cookies_str)} characters)",
            "updated_at": cookie_data["updated_at"]
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error updating cookies: {str(e)}"}, status_code=500)


@api_app.post("/api/admin/cookies/test")
async def test_cookies(admin: dict = Depends(authenticate_admin)):
    """Test stored YouTube cookies with a simple request (admin only)."""
    try:
        cookie_data = user_youtube_cookies_dict.get("admin_cookies", {})
        
        if not cookie_data.get("cookies"):
            return JSONResponse({"success": False, "message": "No cookies stored to test"}, status_code=400)
        
        # Test cookies with a simple YouTube request
        import requests
        import tempfile
        import os
        
        cookies_str = cookie_data["cookies"]
        
        # Save cookies to temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(cookies_str)
            cookies_file = f.name
        
        try:
            # Test with yt-dlp to extract info from a simple video
            import subprocess
            
            test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Roll - always available
            
            result = subprocess.run([
                'yt-dlp', 
                '--cookies', cookies_file,
                '--no-download',
                '--get-title',
                '--get-duration', 
                test_url
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Extract title and duration from output
                output_lines = result.stdout.strip().split('\n')
                title = output_lines[0] if len(output_lines) > 0 else "Unknown"
                duration = output_lines[1] if len(output_lines) > 1 else "Unknown"
                
                return JSONResponse({
                    "success": True, 
                    "message": f"Cookies working! Successfully accessed: {title} ({duration})",
                    "test_url": test_url,
                    "extracted_title": title,
                    "extracted_duration": duration
                })
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                return JSONResponse({
                    "success": False, 
                    "message": f"Cookie test failed: {error_msg}",
                    "test_url": test_url
                })
                
        finally:
            # Clean up temporary cookies file
            try:
                os.unlink(cookies_file)
            except:
                pass
        
    except subprocess.TimeoutExpired:
        return JSONResponse({"success": False, "message": "Cookie test timed out (30 seconds)"})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error testing cookies: {str(e)}"}, status_code=500)


@api_app.delete("/api/admin/cookies/delete")
async def delete_cookies(admin: dict = Depends(authenticate_admin)):
    """Delete stored YouTube cookies (admin only)."""
    try:
        if "admin_cookies" not in user_youtube_cookies_dict:
            return JSONResponse({"success": False, "message": "No cookies stored to delete"}, status_code=404)
        
        # Store deletion info for audit trail
        old_data = user_youtube_cookies_dict.get("admin_cookies", {})
        deletion_info = {
            "deleted_at": time.time(),
            "deleted_by": admin["token"][:8] + "...",
            "previous_update": old_data.get("updated_at"),
            "character_count": len(old_data.get("cookies", ""))
        }
        
        # Delete the cookies but keep deletion audit trail
        del user_youtube_cookies_dict["admin_cookies"]
        user_youtube_cookies_dict["last_deletion"] = deletion_info
        
        return JSONResponse({
            "success": True, 
            "message": f"YouTube cookies deleted successfully (was {deletion_info['character_count']} characters)",
            "deleted_at": deletion_info["deleted_at"]
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error deleting cookies: {str(e)}"}, status_code=500)


# Finalization Configuration Management (Admin Only)
@api_app.get("/api/admin/finalization/config")
async def get_finalization_config_endpoint(admin: dict = Depends(authenticate_admin)):
    """Get current finalization configuration (admin only)."""
    try:
        config = finalization_config_dict.get("config", {})
        
        # Check which config files exist
        config_files_status = {}
        config_files = {
            "youtube_client_secrets_file": "/config/karaoke-finalise-client-secret.json",
            "youtube_description_file": "/config/youtube-video-description.txt", 
            "email_template_file": "/config/email-template.txt",
            "rclone_config_file": "/config/rclone.conf"
        }
        
        for file_key, file_path in config_files.items():
            config_files_status[file_key] = {
                "path": file_path,
                "exists": Path(file_path).exists(),
                "size": Path(file_path).stat().st_size if Path(file_path).exists() else 0
            }
        
        return JSONResponse({
            "success": True,
            "config": config,
            "config_files": config_files_status,
            "discord_webhook_configured": bool(os.environ.get("DISCORD_WEBHOOK_URL"))
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error getting configuration: {str(e)}"}, status_code=500)


class FinalizationConfigRequest(BaseModel):
    enable_youtube_upload: bool = False
    enable_discord_notifications: bool = False
    enable_folder_organisation: bool = False
    enable_public_share_copy: bool = False
    enable_rclone_sync: bool = False
    enable_email_drafts: bool = False
    brand_prefix: str = "NOMAD"
    organised_dir: str = "/output/organized"
    organised_dir_rclone_root: str = "andrewdropboxfull:MediaUnsynced/Karaoke/Tracks-Organized"
    public_share_dir: str = "/output/public-share" 
    rclone_destination: str = "googledrive:Nomad Karaoke"
    discord_webhook_url: str = ""


@api_app.post("/api/admin/finalization/config")
async def update_finalization_config(request: FinalizationConfigRequest, admin: dict = Depends(authenticate_admin)):
    """Update finalization configuration (admin only)."""
    try:
        new_config = request.dict()
        new_config["updated_at"] = time.time()
        new_config["updated_by"] = admin["token"][:8] + "..."
        
        finalization_config_dict["config"] = new_config
        
        return JSONResponse({
            "success": True,
            "message": "Finalization configuration updated successfully",
            "config": new_config
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error updating configuration: {str(e)}"}, status_code=500)


@api_app.post("/api/admin/finalization/test-config")
async def test_finalization_config(admin: dict = Depends(authenticate_admin)):
    """Test finalization configuration (admin only)."""
    try:
        test_job_id = f"test-{int(time.time())}"
        
        # Test basic configuration loading
        config = get_finalization_config(test_job_id)
        
        test_results = {
            "config_loaded": True,
            "rclone_test": False,
            "youtube_secrets_test": False,
            "discord_webhook_test": False,
            "file_checks": {}
        }
        
        # Test rclone setup
        if config.get("enable_rclone_sync") or config.get("enable_folder_organisation"):
            test_results["rclone_test"] = setup_rclone_config(test_job_id)
        
        # Test YouTube secrets file
        youtube_secrets_file = config.get("youtube_client_secrets_file", "")
        if youtube_secrets_file and Path(youtube_secrets_file).exists():
            try:
                import json
                with open(youtube_secrets_file, 'r') as f:
                    json.load(f)
                test_results["youtube_secrets_test"] = True
            except:
                test_results["youtube_secrets_test"] = False
        
        # Test Discord webhook
        discord_webhook = config.get("discord_webhook_url", "")
        if discord_webhook and config.get("enable_discord_notifications"):
            test_results["discord_webhook_test"] = discord_webhook.startswith("https://discord.com/api/webhooks/")
        
        # Check config files
        config_files = ["youtube_client_secrets_file", "youtube_description_file", "email_template_file"]
        for file_key in config_files:
            file_path = config.get(file_key, "")
            test_results["file_checks"][file_key] = {
                "configured": bool(file_path),
                "exists": Path(file_path).exists() if file_path else False
            }
        
        return JSONResponse({
            "success": True,
            "message": "Configuration test completed",
            "test_results": test_results,
            "config_summary": {
                "enabled_features": [k for k, v in config.items() if k.startswith("enable_") and v],
                "brand_prefix": config.get("brand_prefix"),
                "organized_dir": config.get("organised_dir"),
                "rclone_destination": config.get("rclone_destination")
            }
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error testing configuration: {str(e)}"}, status_code=500)


# System Configuration Management (Admin Only)
@api_app.get("/api/admin/system/log-level")
async def get_log_level(admin: dict = Depends(authenticate_admin)):
    """Get current system log level (admin only)."""
    try:
        system_config = system_config_dict.get("config", {})
        current_log_level = system_config.get("log_level", "INFO")
        
        return JSONResponse({
            "success": True,
            "log_level": current_log_level,
            "available_levels": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "description": f"Current log level: {current_log_level}"
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error getting log level: {str(e)}"}, status_code=500)


class LogLevelRequest(BaseModel):
    log_level: str


@api_app.post("/api/admin/system/log-level")
async def set_log_level(request: LogLevelRequest, admin: dict = Depends(authenticate_admin)):
    """Set system log level (admin only)."""
    try:
        log_level = request.log_level.upper()
        
        # Validate log level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if log_level not in valid_levels:
            return JSONResponse({
                "success": False, 
                "message": f"Invalid log level '{log_level}'. Must be one of: {', '.join(valid_levels)}"
            }, status_code=400)
        
        # Get existing config and update log level
        system_config = system_config_dict.get("config", {})
        system_config["log_level"] = log_level
        system_config["updated_at"] = time.time()
        system_config["updated_by"] = admin["token"][:8] + "..."
        
        # Save updated config
        system_config_dict["config"] = system_config
        
        return JSONResponse({
            "success": True,
            "message": f"Log level set to {log_level}",
            "log_level": log_level,
            "note": f"New log level will apply to new jobs. Existing jobs will continue with their current log level."
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error setting log level: {str(e)}"}, status_code=500)


class YouTubeMetadataRequest(BaseModel):
    url: str


@api_app.post("/api/youtube/metadata")
async def get_youtube_metadata(request: YouTubeMetadataRequest, user: dict = Depends(authenticate_user)):
    """Extract metadata from YouTube URL without processing the full job."""
    import re
    
    try:
        youtube_url = request.url.strip()
        
        # Validate YouTube URL format
        youtube_pattern = r'^https://(www\.)?(youtube\.com/(watch\?v=|embed/)|youtu\.be/).+'
        if not re.match(youtube_pattern, youtube_url):
            return JSONResponse({
                "success": False,
                "message": "Invalid YouTube URL format"
            }, status_code=400)
        
        # Get stored admin cookies for metadata extraction
        stored_cookies = None
        cookie_data = user_youtube_cookies_dict.get("admin_cookies", {})
        if cookie_data and cookie_data.get("cookies"):
            stored_cookies = cookie_data["cookies"]
        
        # Extract metadata using the same function as full processing
        from karaoke_gen.metadata import extract_info_for_online_media, parse_track_metadata
        import logging
        
        # Create a logger for this operation
        logger = logging.getLogger("metadata_extraction")
        logger.setLevel(logging.DEBUG)
        
        try:
            # Extract info from YouTube
            extracted_info = extract_info_for_online_media(
                input_url=youtube_url, 
                input_artist=None, 
                input_title=None, 
                logger=logger, 
                cookies_str=stored_cookies
            )
            
            if not extracted_info:
                return JSONResponse({
                    "success": False,
                    "message": "Could not extract metadata from YouTube URL"
                }, status_code=400)
            
            # Parse metadata to get artist and title
            metadata_result = parse_track_metadata(
                extracted_info, None, None, None, logger
            )
            
            artist = metadata_result.get("artist", "").strip()
            title = metadata_result.get("title", "").strip()
            
            # Return extracted metadata
            return JSONResponse({
                "success": True,
                "artist": artist,
                "title": title,
                "message": "Metadata extracted successfully"
            })
            
        except Exception as e:
            error_msg = str(e)
            
            # Check for bot detection errors
            if any(keyword in error_msg.lower() for keyword in ['sign in', 'bot', 'automated', '403', 'forbidden', 'captcha']):
                return JSONResponse({
                    "success": False,
                    "message": "YouTube access blocked. Please contact admin to update cookies.",
                    "error_type": "bot_detection"
                }, status_code=400)
            else:
                return JSONResponse({
                    "success": False,
                    "message": f"Error extracting metadata: {error_msg}",
                    "error_type": "extraction_error"
                }, status_code=400)
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "message": f"Server error: {str(e)}"
        }, status_code=500)


# Protected API Routes (now require authentication)
@api_app.post("/api/submit")
async def submit_job(request: JobSubmissionRequest, user: dict = Depends(authenticate_user)):
    """Submit a new karaoke generation job."""
    try:
        job_id = str(uuid.uuid4())[:8]

        # Track token usage for this job
        if not track_job_usage(user["token"], job_id):
            return JSONResponse({"status": "error", "message": "Failed to track token usage"}, status_code=500)

        # Initialize job status with timeline and user info
        update_job_status_with_timeline(
            job_id,
            "queued",
            progress=0,
            url=request.url,
            created_at=datetime.datetime.now().isoformat(),
            user_type=user["user_type"].value,
            remaining_uses=user["remaining_uses"],
            user_token=user["token"],  # Store user token for YouTube auth
        )

        # Job logs are now handled by Modal's native logging
        # No need to initialize job_logs_dict

        # Spawn the background job
        process_part_one.spawn(job_id, request.url)

        return JSONResponse(
            {
                "status": "success",
                "job_id": job_id,
                "message": "Job submitted successfully",
                "remaining_uses": user["remaining_uses"] - 1 if user["remaining_uses"] > 0 else user["remaining_uses"],
            },
            status_code=202,
        )

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@api_app.post("/api/submit-youtube")
async def submit_youtube_job(
    url: str = Form(...),
    artist: str = Form(...),
    title: str = Form(...),
    styles_file: Optional[UploadFile] = File(None),
    styles_archive: Optional[UploadFile] = File(None),
    user: dict = Depends(authenticate_user),
):
    """Submit a new YouTube karaoke generation job with styles support."""
    try:
        job_id = str(uuid.uuid4())[:8]

        # Track token usage for this job
        if not track_job_usage(user["token"], job_id):
            return JSONResponse({"status": "error", "message": "Failed to track token usage"}, status_code=500)

        # Create output directory
        output_dir = Path("/output") / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Get stored admin cookies from the cookies dict
        stored_cookies = None
        cookie_data = user_youtube_cookies_dict.get("admin_cookies", {})
        if cookie_data and cookie_data.get("cookies"):
            stored_cookies = cookie_data["cookies"]
            print(f"Using stored admin YouTube cookies for job {job_id}")

        # Handle styles files if provided
        styles_file_path = None
        if styles_file:
            print(f"Processing styles file: {styles_file.filename}, content_type: {styles_file.content_type}")
            styles_file_path = output_dir / "styles.json"
            
            # Reset file pointer to beginning
            await styles_file.seek(0)
            file_content = await styles_file.read()
            print(f"Read {len(file_content)} bytes from styles file")
            
            # Write the content to disk
            with open(styles_file_path, "wb") as f:
                f.write(file_content)
            
            # Verify the file was saved and has content
            if not styles_file_path.exists():
                raise Exception(f"Styles file was not created at {styles_file_path}")
            
            file_size = styles_file_path.stat().st_size
            if file_size == 0:
                raise Exception(f"Styles file is empty at {styles_file_path}")
            
            print(f"Successfully saved styles file: {file_size} bytes at {styles_file_path}")

        # Handle styles archive if provided
        styles_archive_path = None
        if styles_archive:
            print(f"Processing styles archive: {styles_archive.filename}, content_type: {styles_archive.content_type}")
            styles_archive_path = output_dir / "styles_archive.zip"
            
            # Reset file pointer to beginning
            await styles_archive.seek(0)
            archive_content = await styles_archive.read()
            print(f"Read {len(archive_content)} bytes from styles archive")
            
            # Write the content to disk
            with open(styles_archive_path, "wb") as f:
                f.write(archive_content)
            
            # Verify the archive was saved and has content
            if not styles_archive_path.exists():
                raise Exception(f"Styles archive was not created at {styles_archive_path}")
            
            archive_size = styles_archive_path.stat().st_size
            if archive_size == 0:
                raise Exception(f"Styles archive is empty at {styles_archive_path}")
                
            print(f"Successfully saved styles archive: {archive_size} bytes at {styles_archive_path}")

        # Log the submission with styles info
        styles_info = []
        if styles_file and styles_file_path and styles_file_path.exists():
            styles_size = styles_file_path.stat().st_size
            styles_info.append(f"Styles file: {styles_file.filename} ({styles_size} bytes)")
        if styles_archive and styles_archive_path and styles_archive_path.exists():
            archive_size = styles_archive_path.stat().st_size
            styles_info.append(f"Styles archive: {styles_archive.filename} ({archive_size} bytes)")
        
        styles_message = f" with {', '.join(styles_info)}" if styles_info else " with default styles"
        print(f"YouTube job submitted: {url}{styles_message}")

        # Get optional override artist and title
        override_artist = artist.strip() if artist else None
        override_title = title.strip() if title else None
        
        # Initialize job status with timeline and user info
        update_job_status_with_timeline(
            job_id,
            "queued",
            progress=0,
            url=url,
            artist=override_artist,  # Store the artist from form submission
            title=override_title,    # Store the title from form submission
            created_at=datetime.datetime.now().isoformat(),
            user_type=user["user_type"].value,
            remaining_uses=user["remaining_uses"],
            has_stored_cookies=bool(stored_cookies),
            override_artist=override_artist,
            override_title=override_title,
            user_token=user["token"],  # Store user token for YouTube auth
        )

        # Job logs are now handled by Modal's native logging
        # No need to initialize job_logs_dict
        
        # Ensure files are committed to volume before spawning GPU function
        if styles_file_path or styles_archive_path:
            output_volume.commit()
            print(f"Volume committed for job {job_id} after file upload")
            
            # Give a small delay for Modal volume sync
            import time
            time.sleep(1)
        
        # Only pass file paths for files that actually exist
        styles_file_passed = str(styles_file_path) if styles_file_path and styles_file_path.exists() else None
        styles_archive_passed = str(styles_archive_path) if styles_archive_path and styles_archive_path.exists() else None
        process_part_one.spawn(job_id, url, stored_cookies, override_artist, override_title, styles_file_passed, styles_archive_passed)

        return JSONResponse(
            {
                "status": "success",
                "job_id": job_id,
                "message": "YouTube job submitted successfully" + (" with stored cookies" if stored_cookies else " (no cookies available)") + styles_message,
                "remaining_uses": user["remaining_uses"] - 1 if user["remaining_uses"] > 0 else user["remaining_uses"],
            },
            status_code=200,
        )

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@api_app.get("/api/jobs")
async def get_all_jobs(user: dict = Depends(authenticate_user)):
    """Get status of all jobs for authenticated user."""
    try:
        all_jobs = dict(job_status_dict.items())

        # For admin users, return all jobs
        if user["user_type"] == UserType.ADMIN:
            return JSONResponse(all_jobs)

        # For regular users, only return their jobs
        user_jobs = {}
        usage_data = token_usage_dict.get(user["token"], {"jobs": []})
        user_job_ids = [job["job_id"] for job in usage_data.get("jobs", [])]

        for job_id, job_data in all_jobs.items():
            if job_id in user_job_ids or job_data.get("user_type") == user["user_type"].value:
                user_jobs[job_id] = job_data

        return JSONResponse(user_jobs)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def check_job_access(job_id: str, user: dict) -> bool:
    """Check if user has access to a specific job."""
    if user["user_type"] == UserType.ADMIN:
        return True

    # Check if user created this job
    usage_data = token_usage_dict.get(user["token"], {"jobs": []})
    user_job_ids = [job["job_id"] for job in usage_data.get("jobs", [])]

    return job_id in user_job_ids


@api_app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str, user: dict = Depends(authenticate_user)):
    """Get status of a specific job with timeline information."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        # Add timeline summary to response
        timeline_summary = get_job_timeline_summary(job_data)

        # If no timeline summary exists, create a basic one for legacy jobs
        if not timeline_summary and job_data.get("created_at"):
            start_time = datetime.datetime.fromisoformat(job_data["created_at"])
            duration_seconds = int((datetime.datetime.now() - start_time).total_seconds())
            timeline_summary = {
                "total_duration_seconds": duration_seconds,
                "total_duration_formatted": format_duration(duration_seconds),
                "current_phase": job_data.get("status", "unknown"),
                "started_at": job_data.get("created_at"),
            }

        return JSONResponse({**job_data, "timeline_summary": timeline_summary})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/jobs/{job_id}/timeline")
async def get_job_timeline(job_id: str, user: dict = Depends(authenticate_user)):
    """Get detailed timeline data for a specific job."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        timeline = job_data.get("timeline", [])
        timeline_summary = get_job_timeline_summary(job_data)

        # Handle legacy jobs without timeline data
        if not timeline and not timeline_summary:
            # Create a synthetic timeline entry for legacy jobs
            current_time = datetime.datetime.now().isoformat()
            estimated_start = job_data.get("created_at", current_time)

            synthetic_timeline = [
                {
                    "status": job_data.get("status", "unknown"),
                    "started_at": estimated_start,
                    "ended_at": None if job_data.get("status") not in ["complete", "error"] else current_time,
                    "duration_seconds": None,
                }
            ]

            # Calculate duration if we have created_at
            if job_data.get("created_at"):
                start_time = datetime.datetime.fromisoformat(job_data["created_at"])
                duration_seconds = int((datetime.datetime.now() - start_time).total_seconds())
                if job_data.get("status") in ["complete", "error"]:
                    synthetic_timeline[0]["duration_seconds"] = duration_seconds

                synthetic_summary = {
                    "phase_durations": {job_data.get("status", "unknown"): duration_seconds},
                    "total_duration_seconds": duration_seconds,
                    "total_duration_formatted": format_duration(duration_seconds),
                    "phases_completed": 1 if job_data.get("status") in ["complete", "error"] else 0,
                    "current_phase": job_data.get("status", "unknown"),
                    "started_at": estimated_start,
                }
            else:
                synthetic_summary = {
                    "phase_durations": {},
                    "total_duration_seconds": 0,
                    "total_duration_formatted": "Unknown",
                    "phases_completed": 0,
                    "current_phase": job_data.get("status", "unknown"),
                    "started_at": None,
                }

            return JSONResponse(
                {
                    "job_id": job_id,
                    "artist": job_data.get("artist", "Unknown"),
                    "title": job_data.get("title", "Unknown"),
                    "current_status": job_data.get("status"),
                    "timeline": synthetic_timeline,
                    "timeline_summary": synthetic_summary,
                    "phase_transitions": [],
                    "performance_metrics": {
                        "average_phase_duration": synthetic_summary.get("total_duration_seconds", 0),
                        "total_processing_time": synthetic_summary.get("total_duration_formatted", "Unknown"),
                        "phases_completed": synthetic_summary.get("phases_completed", 0),
                        "estimated_remaining": None,
                    },
                    "legacy_job": True,
                }
            )

        # Calculate additional timeline metrics for jobs with real timeline data
        phase_transitions = []
        for i in range(len(timeline) - 1):
            current_phase = timeline[i]
            next_phase = timeline[i + 1]

            if current_phase.get("ended_at") and next_phase.get("started_at"):
                transition_time = (
                    datetime.datetime.fromisoformat(next_phase["started_at"]) - datetime.datetime.fromisoformat(current_phase["ended_at"])
                ).total_seconds()

                phase_transitions.append(
                    {
                        "from_status": current_phase["status"],
                        "to_status": next_phase["status"],
                        "transition_duration_seconds": transition_time,
                    }
                )

        return JSONResponse(
            {
                "job_id": job_id,
                "artist": job_data.get("artist", "Unknown"),
                "title": job_data.get("title", "Unknown"),
                "current_status": job_data.get("status"),
                "timeline": timeline,
                "timeline_summary": timeline_summary,
                "phase_transitions": phase_transitions,
                "performance_metrics": {
                    "average_phase_duration": timeline_summary.get("total_duration_seconds", 0)
                    / max(1, timeline_summary.get("phases_completed", 1)),
                    "total_processing_time": timeline_summary.get("total_duration_formatted", "0s"),
                    "phases_completed": timeline_summary.get("phases_completed", 0),
                    "estimated_remaining": _estimate_remaining_time(timeline, job_data.get("status")),
                },
                "legacy_job": False,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def _estimate_remaining_time(timeline: List[Dict], current_status: str) -> Optional[str]:
    """Estimate remaining processing time based on historical data and current status."""
    if current_status in ["complete", "error"]:
        return None

    # This is a simple estimation - in a real system you might use historical job data
    # to make more accurate predictions
    typical_durations = {
        "queued": 30,
        "processing": 900,  # 15 minutes
        "awaiting_review": 0,  # User dependent
        "reviewing": 0,  # User dependent
        "rendering": 600,  # 10 minutes
    }

    remaining_phases = []
    found_current = False

    for phase in ["queued", "processing", "awaiting_review", "rendering", "complete"]:
        if phase == current_status:
            found_current = True
            continue
        if found_current and phase != "complete":
            remaining_phases.append(phase)

    if not remaining_phases:
        return None

    total_estimated = sum(typical_durations.get(phase, 0) for phase in remaining_phases)

    if total_estimated > 0:
        return format_duration(total_estimated)

    return None


@api_app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, user: dict = Depends(authenticate_user)):
    """Delete a specific job."""
    try:
        if job_id not in job_status_dict:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        # Remove from status
        del job_status_dict[job_id]
        # Note: Logs are now stored in Modal's native logging, no cleanup needed

        return JSONResponse({"status": "success", "message": f"Job {job_id} deleted"})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, user: dict = Depends(authenticate_user)):
    """Retry a failed job."""
    from pathlib import Path

    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        if job_data.get("status") != "error":
            raise HTTPException(status_code=400, detail="Job is not in error state")

        # Track token usage for the retry
        if not track_job_usage(user["token"], job_id):
            return JSONResponse({"status": "error", "message": "Failed to track token usage for retry"}, status_code=500)

        # Reset job status with new timeline
        update_job_status_with_timeline(
            job_id,
            "queued",
            progress=0,
            url=job_data.get("url", ""),
            created_at=datetime.datetime.now().isoformat(),
            user_type=user["user_type"].value,
            remaining_uses=user["remaining_uses"],
        )

        # Note: Job retry will be logged via Modal's native logging
        # No need to manually initialize logs

        # Determine job type and spawn the appropriate processing function
        if job_data.get("filename"):
            # This was a file upload job - use process_part_one_uploaded
            artist = job_data.get("artist", "Unknown")
            title = job_data.get("title", "Unknown")
            audio_file_path = f"/output/{job_id}/uploaded.flac"  # Standard upload path
            styles_file_path = job_data.get("styles_file_path")
            styles_archive_path = f"/output/{job_id}/styles_archive.zip" if Path(f"/output/{job_id}/styles_archive.zip").exists() else None

            process_part_one_uploaded.spawn(job_id, audio_file_path, artist, title, styles_file_path, styles_archive_path)
        else:
            # This was a URL job - use process_part_one
            youtube_url = job_data.get("url", "")
            if not youtube_url:
                raise HTTPException(status_code=400, detail="No URL found for retry")
            
            # Get stored admin cookies for retry
            stored_cookies = None
            cookie_data = user_youtube_cookies_dict.get("admin_cookies", {})
            if cookie_data and cookie_data.get("cookies"):
                stored_cookies = cookie_data["cookies"]
            
            # Extract override artist/title from original job if they exist
            override_artist = job_data.get("override_artist")
            override_title = job_data.get("override_title")
            
            # Extract styles file paths from original job if they exist
            styles_file_path = job_data.get("styles_file_path")
            styles_archive_path = f"/output/{job_id}/styles_archive.zip" if Path(f"/output/{job_id}/styles_archive.zip").exists() else None
            
            process_part_one.spawn(job_id, youtube_url, stored_cookies, override_artist, override_title, styles_file_path, styles_archive_path)

        return JSONResponse({"status": "success", "message": f"Job {job_id} retry initiated"})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/logs")
async def get_all_logs(
    user: dict = Depends(authenticate_admin),
    include: str = "",
    exclude: str = "",
    level: str = "",
    limit: int = 1000,
    regex: bool = False
):
    """Get logs for all jobs by querying Modal directly (admin only)."""
    try:
        # Get all jobs and their associated container info
        all_jobs = dict(job_status_dict.items())
        
        logs_by_job = {}
        
        # For each job, try to get its logs from Modal
        for job_id, job_data in all_jobs.items():
            try:
                job_logs = await get_modal_logs_for_job(
                    job_id, job_data, 
                    include_filter=include,
                    exclude_filter=exclude,
                    level_filter=level,
                    limit=limit,
                    use_regex=regex
                )
                if job_logs:
                    logs_by_job[job_id] = job_logs
            except Exception as e:
                # If we can't get logs for a specific job, skip it but don't fail the whole request
                logs_by_job[job_id] = [{"timestamp": "unknown", "level": "ERROR", "message": f"Could not fetch logs: {str(e)}"}]
        
        return JSONResponse(logs_by_job)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/logs/{job_id}")
async def get_job_logs(
    job_id: str, 
    user: dict = Depends(authenticate_user),
    include: str = "",
    exclude: str = "",
    level: str = "",
    limit: int = 1000,
    regex: bool = False
):
    """Get logs for a specific job by querying Modal directly."""
    try:
        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        # Get job data to find associated containers
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Get logs from Modal with filtering
        logs = await get_modal_logs_for_job(
            job_id, job_data,
            include_filter=include,
            exclude_filter=exclude, 
            level_filter=level,
            limit=limit,
            use_regex=regex
        )
        
        # Return logs with metadata about filtering
        return JSONResponse({
            "logs": logs,
            "total_count": len(logs),
            "filters_applied": {
                "include": include,
                "exclude": exclude,
                "level": level,
                "limit": limit,
                "regex": regex
            }
        })
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/logs/{job_id}/raw")
async def get_raw_job_logs(job_id: str, user: dict = Depends(authenticate_user)):
    """Get raw log file content for debugging (admin only)."""
    try:
        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        # Reload volume and wait for sync
        output_volume.reload()
        import asyncio
        await asyncio.sleep(0.5)
        
        log_file_path = Path(f"/output/{job_id}/job_logs.jsonl")
        
        if not log_file_path.exists():
            return JSONResponse({
                "exists": False,
                "path": str(log_file_path),
                "content": None,
                "size": 0
            })
        
        file_size = log_file_path.stat().st_size
        
        with open(log_file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        return JSONResponse({
            "exists": True,
            "path": str(log_file_path),
            "content": content,
            "size": file_size,
            "lines": len(content.splitlines()) if content else 0
        })
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/stats")
async def get_stats(user: dict = Depends(authenticate_user)):
    """Get statistics about jobs accessible to the user."""
    try:
        all_jobs = dict(job_status_dict.items())

        # For admin users, show stats for all jobs
        if user["user_type"] == UserType.ADMIN:
            jobs = all_jobs
        else:
            # For regular users, only show stats for their jobs
            usage_data = token_usage_dict.get(user["token"], {"jobs": []})
            user_job_ids = [job["job_id"] for job in usage_data.get("jobs", [])]
            jobs = {job_id: job_data for job_id, job_data in all_jobs.items() if job_id in user_job_ids}

        stats = {
            "total": len(jobs),
            "processing": len([j for j in jobs.values() if j.get("status") in ["queued", "processing_audio", "transcribing", "rendering"]]),
            "awaiting_review": len([j for j in jobs.values() if j.get("status") == "awaiting_review"]),
            "complete": len([j for j in jobs.values() if j.get("status") == "complete"]),
            "error": len([j for j in jobs.values() if j.get("status") == "error"]),
        }

        # Add user-specific stats
        stats["user_type"] = user["user_type"].value
        stats["remaining_uses"] = user["remaining_uses"]

        return JSONResponse(stats)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/review/{job_id}")
async def get_lyrics_for_review(job_id: str):
    """Get lyrics data for review interface."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") != "awaiting_review":
            raise HTTPException(status_code=400, detail="Job is not awaiting review")

        # Get review data from the processed track
        track_data = job_data.get("track_data", {})
        track_output_dir = Path(job_data.get("track_output_dir", f"/output/{job_id}"))

        # Look for generated files by KaraokePrep
        review_data = {
            "job_id": job_id,
            "artist": track_data.get("artist", "Unknown"),
            "title": track_data.get("title", "Unknown"),
            "lrc_file": None,
            "corrected_lyrics": None,
            "original_lyrics": None,
            "vocals_audio": None,
        }

        # Find LRC file
        lrc_files = list(track_output_dir.glob("**/*.lrc"))
        if lrc_files:
            review_data["lrc_file"] = str(lrc_files[0])

        # Find corrected lyrics text file
        corrected_files = list(track_output_dir.glob("**/*Corrected*.txt"))
        if corrected_files:
            with open(corrected_files[0], "r") as f:
                review_data["corrected_lyrics"] = f.read()

        # Find original/uncorrected lyrics
        original_files = list(track_output_dir.glob("**/*Uncorrected*.txt"))
        if original_files:
            with open(original_files[0], "r") as f:
                review_data["original_lyrics"] = f.read()

        # Find vocals audio file
        vocals_files = list(track_output_dir.glob("**/*Vocals*.flac")) + list(track_output_dir.glob("**/*Vocals*.FLAC"))
        if vocals_files:
            review_data["vocals_audio"] = str(vocals_files[0])

        return JSONResponse(review_data)

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.post("/api/review/{job_id}/start")
async def start_review(job_id: str):
    """Start the review process for a specific job."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") != "awaiting_review":
            raise HTTPException(status_code=400, detail="Job is not awaiting review")

        # Prepare review data
        result = prepare_review_data.remote(job_id)

        log_message(job_id, "INFO", "Review data prepared, redirecting to review interface")

        # Create the review URL with the base API URL (not including job_id)
        # The frontend will append specific endpoints like /correction-data, /audio/, etc.
        review_url = f"https://lyrics.nomadkaraoke.com/?baseApiUrl={get_base_api_url()}/api/corrections/{job_id}"

        return JSONResponse({"status": "success", "message": "Review data prepared", "review_url": review_url})

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def get_base_api_url() -> str:
    """Get the base API URL for this Modal deployment."""
    # This will be the external URL of the Modal API endpoint
    # In production, this should be set via environment variable
    return "https://nomadkaraoke--karaoke-generator-webapp-api-endpoint.modal.run"


@api_app.get("/api/jobs/{job_id}/download")
async def download_video(job_id: str, request: Request, user: dict = Depends(authenticate_user_or_token)):
    """Download the Final Karaoke Lossy 4k MP4 video."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        if job_data.get("status") != "complete":
            raise HTTPException(status_code=400, detail="Job is not complete")

        # Look specifically for the Final Karaoke Lossy 4k MP4 file
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        track_dir = Path(track_output_dir)

        # Find the Final Karaoke Lossy 4k MP4 file
        video_files = list(track_dir.rglob("*Final Karaoke Lossy 4k*.mp4"))
        
        if not video_files:
            raise HTTPException(status_code=404, detail="Final Karaoke Lossy 4k MP4 file not found")

        video_file = video_files[0]  # Take the first match
        return FileResponse(
            path=str(video_file),
            filename=video_file.name,
            media_type="video/mp4",
        )

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/corrections/{job_id}/audio/")
async def get_audio_file(job_id: str):
    """Get the vocals audio file for review playback."""
    try:
        from pathlib import Path
        import hashlib
        import shutil
        import tempfile

        # Reload output volume to see latest audio files (no conflicts since previews are in separate volume)
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") not in ["reviewing", "awaiting_review"]:
            raise HTTPException(status_code=400, detail="Job is not in review state")

        # Get job details
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")

        # Look for vocals audio file
        track_dir = Path(track_output_dir)

        # Try different possible vocals file patterns
        vocals_patterns = [f"{artist} - {title}*.wav"]

        vocals_file = None
        for pattern in vocals_patterns:
            vocals_files = list(track_dir.glob(f"**/{pattern}"))
            if vocals_files:
                vocals_file = vocals_files[0]
                break

        if not vocals_file or not vocals_file.exists():
            log_message(job_id, "ERROR", f"No vocals audio file found in {track_dir}")
            raise HTTPException(status_code=404, detail="Vocals audio file not found")

        log_message(job_id, "DEBUG", f"Serving vocals file: {vocals_file}")

        # Determine media type based on file extension
        file_extension = vocals_file.suffix.lower()
        if file_extension in [".flac"]:
            media_type = "audio/flac"
        elif file_extension in [".wav"]:
            media_type = "audio/wav"
        elif file_extension in [".mp3"]:
            media_type = "audio/mpeg"
        else:
            media_type = "audio/flac"  # Default

        # Serve the original file directly to minimize volume conflicts
        # The preview video generation will gracefully handle volume reload failures
        return FileResponse(
            path=str(vocals_file), 
            filename=f"vocals-{job_id}{file_extension}", 
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error serving audio file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving audio file: {str(e)}")


@api_app.post("/api/corrections/{job_id}/preview-video")
async def generate_preview_video(job_id: str, request: Request):
    """Generate a preview video with corrected lyrics."""
    import time
    start_time = time.time()
    
    try:
        log_message(job_id, "INFO", f"🎬 [STAGE 1] Preview video request received at {datetime.datetime.now().isoformat()}")
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") not in ["reviewing", "awaiting_review"]:
            raise HTTPException(status_code=400, detail="Job is not in review state")

        # Get the corrected data from the request
        request_parse_start = time.time()
        corrected_data = await request.json()
        request_parse_duration = time.time() - request_parse_start
        log_message(job_id, "DEBUG", f"📋 Request data parsed in {request_parse_duration:.3f}s")

        log_message(job_id, "INFO", f"🚀 [STAGE 1] Starting Modal function for preview video generation")

        # Call the Modal function to generate preview video
        modal_call_start = time.time()
        result = generate_preview_video_modal.remote(job_id, corrected_data)
        modal_call_duration = time.time() - modal_call_start
        
        total_duration = time.time() - start_time
        log_message(job_id, "INFO", f"✅ [STAGE 1] Preview video API call completed in {total_duration:.3f}s (Modal function: {modal_call_duration:.3f}s)")

        return JSONResponse(
            {"status": "success", "message": "Preview video generated successfully", "preview_hash": result["preview_hash"]}
        )

    except HTTPException:
        total_duration = time.time() - start_time
        log_message(job_id, "ERROR", f"❌ [STAGE 1] Preview video request failed after {total_duration:.3f}s (HTTPException)")
        raise
    except Exception as e:
        total_duration = time.time() - start_time
        log_message(job_id, "ERROR", f"❌ [STAGE 1] Preview video request failed after {total_duration:.3f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating preview video: {str(e)}")


@api_app.get("/api/corrections/{job_id}/audio/{audio_hash}")
async def get_audio_by_hash(job_id: str, audio_hash: str):
    """Get audio file by hash (compatible with ReviewServer API)."""
    try:
        from pathlib import Path
        import hashlib
        import shutil

        # Reload output volume to see latest audio files (no conflicts since previews are in separate volume)
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") not in ["reviewing", "awaiting_review"]:
            raise HTTPException(status_code=400, detail="Job is not in review state")

        # Get job details
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")

        # Look for vocals audio file
        track_dir = Path(track_output_dir)

        # Try different possible vocals file patterns
        vocals_patterns = [f"{artist} - {title}*.wav"]

        vocals_file = None
        for pattern in vocals_patterns:
            vocals_files = list(track_dir.glob(f"**/{pattern}"))
            if vocals_files:
                vocals_file = vocals_files[0]
                break

        if not vocals_file or not vocals_file.exists():
            log_message(job_id, "ERROR", f"No vocals audio file found in {track_dir}")
            raise HTTPException(status_code=404, detail="Vocals audio file not found")

        # Verify audio hash matches (basic security check)
        with open(vocals_file, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()

        if audio_hash != file_hash:
            log_message(job_id, "WARNING", f"Audio hash mismatch: expected {audio_hash}, got {file_hash}")
            # Still serve the file but log the warning

        log_message(job_id, "DEBUG", f"Serving vocals file: {vocals_file}")

        # Determine media type based on file extension
        file_extension = vocals_file.suffix.lower()
        if file_extension in [".flac"]:
            media_type = "audio/flac"
        elif file_extension in [".wav"]:
            media_type = "audio/wav"
        elif file_extension in [".mp3"]:
            media_type = "audio/mpeg"
        else:
            media_type = "audio/flac"  # Default

        # Serve the original file directly to minimize volume conflicts
        # The preview video generation will gracefully handle volume reload failures
        return FileResponse(
            path=str(vocals_file), 
            filename=f"vocals-{job_id}{file_extension}", 
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error serving audio file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving audio file: {str(e)}")


@api_app.get("/api/corrections/{job_id}/preview-video/{preview_hash}")
async def get_preview_video(job_id: str, preview_hash: str):
    """Get generated preview video by hash."""
    import time
    request_start_time = time.time()
    
    try:
        from pathlib import Path

        log_message(job_id, "INFO", f"📺 [STAGE 4] Preview video fetch request received at {datetime.datetime.now().isoformat()} for hash: {preview_hash}")

        # Reload preview volume to see latest preview videos (no conflicts since previews are in separate volume)
        volume_reload_start = time.time()
        try:
            preview_volume.reload()
            volume_reload_duration = time.time() - volume_reload_start
            log_message(job_id, "DEBUG", f"📁 [STAGE 4] Preview volume reload completed in {volume_reload_duration:.3f}s")
        except Exception as e:
            log_message(job_id, "WARNING", f"📁 [STAGE 4] Preview volume reload failed: {str(e)} - proceeding anyway")

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Look for the preview video file in dedicated preview volume
        file_search_start = time.time()
        preview_dir = Path(f"/previews/{job_id}")

        if not preview_dir.exists():
            raise HTTPException(status_code=404, detail="Preview directory not found")

        # Find preview video file with matching hash
        log_message(job_id, "DEBUG", f"🔍 [STAGE 4] Looking for preview video in {preview_dir}")
        log_message(job_id, "DEBUG", f"🎯 [STAGE 4] Preview hash: {preview_hash}")

        # List all files in preview directory for debugging
        if preview_dir.exists():
            all_files = list(preview_dir.glob("*"))
            log_message(job_id, "DEBUG", f"📂 [STAGE 4] Files in preview directory: {[f.name for f in all_files]}")

        preview_files = list(preview_dir.glob(f"preview_{preview_hash}*"))
        log_message(job_id, "DEBUG", f"📋 [STAGE 4] Found preview files matching pattern: {[f.name for f in preview_files]}")

        video_file = None
        for file in preview_files:
            log_message(job_id, "DEBUG", f"🔍 [STAGE 4] Checking file: {file.name}, suffix: {file.suffix}")
            if file.suffix in [".mp4", ".mkv", ".avi"]:
                video_file = file
                log_message(job_id, "DEBUG", f"✅ [STAGE 4] Selected video file: {video_file}")
                break

        if not video_file or not video_file.exists():
            log_message(job_id, "ERROR", f"❌ [STAGE 4] Preview video not found. Pattern: preview_{preview_hash}*, Directory: {preview_dir}")
            if preview_dir.exists():
                all_files = list(preview_dir.glob("*"))
                log_message(job_id, "ERROR", f"📂 [STAGE 4] Available files: {[f.name for f in all_files]}")
            raise HTTPException(status_code=404, detail="Preview video not found")

        file_search_duration = time.time() - file_search_start
        log_message(job_id, "DEBUG", f"🔎 [STAGE 4] File search completed in {file_search_duration:.3f}s")
        log_message(job_id, "INFO", f"📤 [STAGE 4] Serving preview video: {video_file.name}")

        # Detect proper MIME type based on actual file extension
        file_extension = video_file.suffix.lower()
        if file_extension == ".mp4":
            media_type = "video/mp4"
        elif file_extension == ".mkv":
            media_type = "video/x-matroska"
        elif file_extension == ".avi":
            media_type = "video/x-msvideo"
        else:
            media_type = "video/mp4"  # Default fallback

        log_message(job_id, "DEBUG", f"Using media type: {media_type} for file: {video_file.name}")

        # Get file size for Content-Length header
        file_stat_start = time.time()
        file_size = video_file.stat().st_size
        file_stat_duration = time.time() - file_stat_start
        log_message(job_id, "DEBUG", f"📊 [STAGE 4] Video file size: {file_size} bytes (stat took {file_stat_duration:.3f}s)")

        total_request_duration = time.time() - request_start_time
        log_message(job_id, "INFO", f"✅ [STAGE 4] Preview video fetch completed in {total_request_duration:.3f}s - starting file transfer")

        return FileResponse(
            path=str(video_file),
            filename=f"preview_{preview_hash}{file_extension}",
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff",
                "Content-Length": str(file_size),
            },
        )

    except HTTPException:
        error_duration = time.time() - request_start_time
        log_message(job_id, "ERROR", f"❌ [STAGE 4] Preview video fetch failed after {error_duration:.3f}s (HTTPException)")
        raise
    except Exception as e:
        error_duration = time.time() - request_start_time
        log_message(job_id, "ERROR", f"❌ [STAGE 4] Preview video fetch failed after {error_duration:.3f}s: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving preview video: {str(e)}")


@api_app.post("/api/corrections/{job_id}/handlers")
async def update_handlers(job_id: str, request: Request):
    """Update enabled correction handlers."""
    try:
        # Get the enabled handlers list from request
        enabled_handlers = await request.json()

        log_message(job_id, "INFO", f"Handlers update requested: {enabled_handlers}")

        # Call the Modal function to update handlers
        result = update_correction_handlers.remote(job_id, enabled_handlers)

        return JSONResponse(
            {"status": "success", "message": f"Successfully updated correction handlers: {enabled_handlers}", "data": result["data"]}
        )

    except Exception as e:
        log_message(job_id, "ERROR", f"Error updating handlers: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating handlers: {str(e)}")


@api_app.post("/api/corrections/{job_id}/add-lyrics")
async def add_lyrics(job_id: str, request: Request):
    """Add new lyrics source."""
    try:
        # Get the lyrics data from request
        lyrics_data = await request.json()
        source = lyrics_data.get("source", "").strip()
        lyrics_text = lyrics_data.get("lyrics", "").strip()

        log_message(job_id, "INFO", f"Add lyrics requested: source='{source}', length={len(lyrics_text)}")

        if not source or not lyrics_text:
            raise HTTPException(status_code=400, detail="Source name and lyrics text are required")

        # Call the Modal function to add lyrics source
        result = add_lyrics_source.remote(job_id, source, lyrics_text)

        return JSONResponse(
            {"status": "success", "message": f"Successfully added lyrics source '{source}' and updated corrections", "data": result["data"]}
        )

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error adding lyrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding lyrics: {str(e)}")


# Admin Routes
@api_app.post("/api/admin/clear-errors")
async def clear_error_jobs(admin: dict = Depends(authenticate_admin)):
    """Clear all jobs with error status."""
    try:
        jobs_to_delete = []
        for job_id, job_data in job_status_dict.items():
            if job_data.get("status") == "error":
                jobs_to_delete.append(job_id)

        for job_id in jobs_to_delete:
            del job_status_dict[job_id]
            # Note: Logs are now stored in Modal's native logging, no cleanup needed

        return JSONResponse({"status": "success", "message": f"Cleared {len(jobs_to_delete)} error jobs"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/admin/cache/stats")
async def get_cache_stats(admin: dict = Depends(authenticate_admin)):
    """Get cache statistics and usage information."""
    try:
        cache_manager = CacheManager("/cache")

        stats = {"cache_categories": {}, "total_files": 0, "total_size_bytes": 0}

        # Define cache file patterns based on real cache structure
        cache_patterns = {
            "audioshake_responses": ["audioshake_*_raw.json", "audioshake_*_converted.json"],
            "genius_lyrics": ["genius_*_raw.json", "genius_*_converted.json"],
            "spotify_lyrics": ["spotify_*_raw.json", "spotify_*_converted.json"],
            "whisper_transcriptions": ["whisper_*_raw.json", "whisper_*_converted.json"],
            "file_sources": ["file_*_raw.json", "file_*_converted.json"],
            "anchor_sequences": ["anchors_*.json"],
            "preview_videos": ["preview_*.mp4"],
            "processed_lyrics": ["* (Lyrics *).txt"],
            "temporary_files": ["temp_*.ass", "resized_*.png"],
            "other_files": ["*.json", "*.txt", "*.mp4", "*.png"],  # Catch-all for remaining files
        }

        # Check each cache category
        for category, patterns in cache_patterns.items():
            files = []
            for pattern in patterns:
                files.extend(cache_manager.cache_dir.glob(pattern))

            # Remove duplicates (files might match multiple patterns)
            files = list(set(files))

            if files:
                category_size = sum(f.stat().st_size for f in files if f.is_file())

                stats["cache_categories"][category] = {
                    "file_count": len(files),
                    "size_bytes": category_size,
                    "size_mb": round(category_size / 1024 / 1024, 2),
                }

                stats["total_files"] += len(files)
                stats["total_size_bytes"] += category_size

        # Get actual total from all files (to handle any overlaps)
        all_files = list(cache_manager.cache_dir.glob("*"))
        actual_files = [f for f in all_files if f.is_file()]
        actual_total_size = sum(f.stat().st_size for f in actual_files)

        stats["total_files"] = len(actual_files)
        stats["total_size_bytes"] = actual_total_size
        stats["total_size_mb"] = round(actual_total_size / 1024 / 1024, 2)
        stats["total_size_gb"] = round(actual_total_size / 1024 / 1024 / 1024, 2)

        return JSONResponse(stats)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.post("/api/admin/cache/clear")
async def clear_cache(admin: dict = Depends(authenticate_admin)):
    """Clear old cache files."""
    try:
        cache_manager = CacheManager("/cache")

        # Clear cache files older than 90 days
        cache_manager.clear_old_cache(max_age_days=90)

        return JSONResponse({"status": "success", "message": "Old cache files cleared"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/admin/cache/audioshake")
async def get_audioshake_cache(admin: dict = Depends(authenticate_admin)):
    """Get list of cached AudioShake responses."""
    try:
        cache_manager = CacheManager("/cache")

        cached_responses = []

        # Look for both raw and converted AudioShake files
        audioshake_files = []
        audioshake_files.extend(cache_manager.cache_dir.glob("audioshake_*_raw.json"))
        audioshake_files.extend(cache_manager.cache_dir.glob("audioshake_*_converted.json"))

        for cache_file in audioshake_files:
            try:
                with open(cache_file, "r") as f:
                    cached_data = json.load(f)

                # Extract hash from filename
                filename = cache_file.name
                if filename.startswith("audioshake_"):
                    parts = filename.replace("audioshake_", "").replace(".json", "")
                    if parts.endswith("_raw"):
                        audio_hash = parts[:-4]
                        file_type = "raw"
                    elif parts.endswith("_converted"):
                        audio_hash = parts[:-10]
                        file_type = "converted"
                    else:
                        audio_hash = parts
                        file_type = "unknown"
                else:
                    audio_hash = "unknown"
                    file_type = "unknown"

                cached_responses.append(
                    {
                        "audio_hash": audio_hash,
                        "file_type": file_type,
                        "timestamp": cached_data.get("timestamp", "unknown"),
                        "file_size_bytes": cache_file.stat().st_size,
                        "filename": cache_file.name,
                    }
                )
            except Exception as e:
                # Skip invalid cache files but log for debugging
                cached_responses.append(
                    {
                        "audio_hash": "invalid",
                        "file_type": "error",
                        "timestamp": "unknown",
                        "file_size_bytes": cache_file.stat().st_size,
                        "filename": cache_file.name,
                        "error": str(e),
                    }
                )
                continue

        return JSONResponse({"status": "success", "cached_responses": cached_responses, "total_count": len(cached_responses)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.delete("/api/admin/cache/audioshake/{audio_hash}")
async def delete_audioshake_cache(audio_hash: str, admin: dict = Depends(authenticate_admin)):
    """Delete specific AudioShake cache entry."""
    try:
        cache_manager = CacheManager("/cache")

        # Look for both raw and converted files
        cache_files = [
            cache_manager.cache_dir / f"audioshake_{audio_hash}_raw.json",
            cache_manager.cache_dir / f"audioshake_{audio_hash}_converted.json",
        ]

        deleted_files = []
        for cache_file in cache_files:
            if cache_file.exists():
                cache_file.unlink()
                deleted_files.append(cache_file.name)

        if deleted_files:
            return JSONResponse(
                {"status": "success", "message": f"Deleted AudioShake cache for hash {audio_hash}", "deleted_files": deleted_files}
            )
        else:
            return JSONResponse({"status": "not_found", "message": f"No cache found for hash {audio_hash}"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/admin/export-logs")
async def export_logs(admin: dict = Depends(authenticate_admin)):
    """Export all job data and detailed logs as JSON file."""
    try:
        # Get all jobs
        all_jobs = dict(job_status_dict.items())
        
        # Get logs for all jobs from local log files
        logs_by_job = {}
        for job_id, job_data in all_jobs.items():
            try:
                job_logs = await get_modal_logs_for_job(job_id, job_data)
                logs_by_job[job_id] = job_logs
            except Exception as e:
                logs_by_job[job_id] = [{"timestamp": "unknown", "level": "ERROR", "message": f"Could not fetch logs: {str(e)}"}]
        
        logs_data = {
            "exported_at": datetime.datetime.now().isoformat(),
            "export_method": "local_log_files",
            "jobs": all_jobs,
            "logs": logs_by_job,
            "note": "Detailed logs from local job log files, supplemented with timeline data"
        }

        import tempfile
        import os

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(logs_data, f, indent=2)
            temp_path = f.name

        return FileResponse(
            path=temp_path, filename=f"karaoke-logs-{datetime.datetime.now().strftime('%Y%m%d')}.json", media_type="application/json"
        )

    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.post("/api/admin/cache/warm")
async def warm_cache_endpoint(admin: dict = Depends(authenticate_admin)):
    """Trigger cache warming for commonly used models and data."""
    try:
        # Spawn the cache warming function
        result = warm_cache.remote()

        return JSONResponse({"status": "success", "message": "Cache warming initiated"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Health check
@api_app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "timestamp": datetime.datetime.now().isoformat(), "version": "1.0.0"})


# Debug endpoint for AudioShake API
@api_app.get("/api/debug/audioshake")
async def debug_audioshake():
    """Debug AudioShake API connectivity and credentials."""
    try:
        import os
        import requests

        audioshake_token = os.environ.get("AUDIOSHAKE_API_TOKEN")
        if not audioshake_token:
            return JSONResponse({"status": "error", "message": "AUDIOSHAKE_API_TOKEN environment variable not set"}, status_code=500)

        # Test API endpoints
        headers = {"Authorization": f"Bearer {audioshake_token}"}

        # Test 1: Upload endpoint (GET to see if it responds - normally POST)
        try:
            upload_response = requests.get("https://groovy.audioshake.ai/upload/", headers=headers, timeout=10)
            upload_status = upload_response.status_code
            upload_text = upload_response.text[:200]  # First 200 chars
        except Exception as e:
            upload_status = "error"
            upload_text = str(e)

        # Test 2: Job endpoint (GET to see if it responds - normally POST)
        try:
            job_response = requests.get("https://groovy.audioshake.ai/job/", headers=headers, timeout=10)
            job_status = job_response.status_code
            job_text = job_response.text[:200]
        except Exception as e:
            job_status = "error"
            job_text = str(e)

        # Test 3: Test getting a non-existent job (to see API response format)
        try:
            test_job_response = requests.get("https://groovy.audioshake.ai/job/test-job-id", headers=headers, timeout=10)
            test_job_status = test_job_response.status_code
            test_job_text = test_job_response.text[:200]
        except Exception as e:
            test_job_status = "error"
            test_job_text = str(e)

        return JSONResponse(
            {
                "status": "success",
                "audioshake_api_tests": {
                    "token_present": bool(audioshake_token),
                    "token_prefix": audioshake_token[:10] + "..." if audioshake_token else None,
                    "upload_endpoint": {"status": upload_status, "response_preview": upload_text},
                    "job_endpoint": {"status": job_status, "response_preview": job_text},
                    "test_job_endpoint": {"status": test_job_status, "response_preview": test_job_text},
                },
                "timestamp": datetime.datetime.now().isoformat(),
            }
        )

    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# Lyrics Review Endpoints
@api_app.get("/api/corrections/{job_id}/correction-data")
async def get_correction_data(job_id: str):
    """Get correction data for review interface."""
    try:
        from pathlib import Path
        import hashlib

        # CRITICAL: Reload the volume to see files written by other containers
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") not in ["reviewing", "awaiting_review"]:
            raise HTTPException(status_code=400, detail="Job is not in review state")

        # DEBUG: Log job data to understand what we have
        log_message(job_id, "DEBUG", f"get_correction_data called for job {job_id}")
        log_message(job_id, "DEBUG", f"Job status: {job_data.get('status')}")
        log_message(job_id, "DEBUG", f"Job data keys: {list(job_data.keys())}")

        # Get the corrections file path from job data
        corrections_file_path = job_data.get("corrections_file")
        log_message(job_id, "DEBUG", f"corrections_file from job data: {corrections_file_path}")

        if not corrections_file_path:
            # Fallback to constructing the path
            track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
            artist = job_data.get("artist", "Unknown")
            title = job_data.get("title", "Unknown")
            corrections_file_path = str(Path(track_output_dir) / "lyrics" / f"{artist} - {title} (Lyrics Corrections).json")
            log_message(job_id, "DEBUG", f"Fallback path constructed: {corrections_file_path}")
            log_message(job_id, "DEBUG", f"Using track_output_dir: {track_output_dir}, artist: {artist}, title: {title}")

        corrections_json_path = Path(corrections_file_path)
        log_message(job_id, "DEBUG", f"Checking if file exists: {corrections_json_path}")
        log_message(job_id, "DEBUG", f"File exists: {corrections_json_path.exists()}")

        # If file doesn't exist, try to list what files ARE in the lyrics directory
        if not corrections_json_path.exists():
            lyrics_dir = corrections_json_path.parent
            log_message(job_id, "DEBUG", f"Lyrics directory: {lyrics_dir}")
            log_message(job_id, "DEBUG", f"Lyrics directory exists: {lyrics_dir.exists()}")

            if lyrics_dir.exists():
                files_in_lyrics_dir = list(lyrics_dir.glob("*"))
                log_message(job_id, "DEBUG", f"Files in lyrics directory: {[str(f) for f in files_in_lyrics_dir]}")

            raise HTTPException(status_code=404, detail="Corrections data not found")

        # Load and return the correction data
        with open(corrections_json_path, "r") as f:
            corrections_data = json.load(f)

        # Find audio file and generate hash for frontend
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")
        track_dir = Path(track_output_dir)

        # Try to find vocals audio file for hash generation
        vocals_patterns = [
            f"*Vocals*.flac",
            f"*Vocals*.FLAC",
            f"*vocals*.flac",
            f"*vocals*.wav",
            f"{artist} - {title}*.wav",  # Any audio file for this track (including YouTube ID)
        ]

        audio_hash = None
        for pattern in vocals_patterns:
            vocals_files = list(track_dir.glob(f"**/{pattern}"))
            if vocals_files:
                vocals_file = vocals_files[0]
                try:
                    with open(vocals_file, "rb") as f:
                        audio_hash = hashlib.md5(f.read()).hexdigest()
                    log_message(job_id, "DEBUG", f"Generated audio hash {audio_hash} for {vocals_file}")
                    break
                except Exception as e:
                    log_message(job_id, "WARNING", f"Could not generate hash for {vocals_file}: {e}")

        # Add audio hash to metadata if we have it
        if audio_hash and "metadata" in corrections_data:
            corrections_data["metadata"]["audio_hash"] = audio_hash
        elif audio_hash:
            corrections_data["metadata"] = {"audio_hash": audio_hash}

        log_message(job_id, "DEBUG", f"Successfully loaded corrections data with {len(corrections_data)} keys")
        return JSONResponse(corrections_data)

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error getting correction data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting correction data: {str(e)}")


@api_app.post("/api/corrections/{job_id}/complete")
async def complete_review(job_id: str, request: Request):
    """Complete the review process with corrected lyrics data (Phase 2 - video generation only)."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") != "reviewing":
            raise HTTPException(status_code=400, detail="Job is not in reviewing state")

        # Get the corrected lyrics data from request
        request_data = await request.json()
        
        # Handle both formats:
        # 1. Direct format (React frontend): { corrections: ..., corrected_segments: ... }
        # 2. Wrapped format (Web frontend): { corrected_data: { corrections: ..., corrected_segments: ... } }
        if "corrected_data" in request_data:
            # Wrapped format from web frontend
            corrected_data = request_data.get("corrected_data", {})
            log_message(job_id, "DEBUG", "Received corrected data in wrapped format (web frontend)")
        elif "corrections" in request_data or "corrected_segments" in request_data:
            # Direct format from React frontend  
            corrected_data = request_data
            log_message(job_id, "DEBUG", "Received corrected data in direct format (React frontend)")
        else:
            # No corrected data provided
            corrected_data = {}
            log_message(job_id, "DEBUG", "No corrected data provided in request")

        # Get additional options for the new two-step flow
        selected_instrumental = request_data.get("selected_instrumental")
        upload_to_youtube = request_data.get("upload_to_youtube", False)

        # Log the corrected data details for debugging
        if corrected_data:
            corrections_count = len(corrected_data.get("corrections", {}))
            segments_count = len(corrected_data.get("corrected_segments", []))
            log_message(job_id, "INFO", f"Received corrected data: {corrections_count} corrections, {segments_count} segments")
        else:
            log_message(job_id, "INFO", "No corrected data received - will use original transcription")

        # Log additional parameters if provided (for backward compatibility)
        if selected_instrumental:
            log_message(job_id, "INFO", f"Selected instrumental for completion: {selected_instrumental}")
        
        if upload_to_youtube:
            log_message(job_id, "INFO", "YouTube upload requested for completion")

        log_message(job_id, "INFO", "Review completed, starting Phase 2 (video generation only)")

        # For the new two-step flow, we store the finalization options in job data
        # and only proceed to Phase 2 (video generation), then let the frontend
        # handle the instrumental selection and YouTube upload decision separately
        if selected_instrumental or upload_to_youtube:
            # Store finalization options for later use in Phase 3
            job_data["finalization_options"] = {
                "selected_instrumental": selected_instrumental,
                "upload_to_youtube": upload_to_youtube
            }
            job_status_dict[job_id] = job_data
            log_message(job_id, "INFO", "Stored finalization options for Phase 3")

        # Spawn Phase 2 to generate the "With Vocals" video only
        process_part_two.spawn(job_id, corrected_data)

        return JSONResponse({"status": "success", "message": "Review completed successfully, starting video generation"})

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error completing review: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.post("/api/corrections/{job_id}/finalize")
async def finalize_with_instrumental(job_id: str, request: Request):
    """Complete Phase 3 (finalization) with selected instrumental and YouTube upload decision."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") != "ready_for_finalization":
            raise HTTPException(status_code=400, detail="Job is not ready for finalization")

        # Get the finalization options from request
        request_data = await request.json()
        selected_instrumental = request_data.get("selected_instrumental")
        upload_to_youtube = request_data.get("upload_to_youtube", False)

        log_message(job_id, "INFO", "Starting Phase 3 (finalization) with user preferences")
        if selected_instrumental:
            log_message(job_id, "INFO", f"Using selected instrumental: {selected_instrumental}")
        
        if upload_to_youtube:
            log_message(job_id, "INFO", "YouTube upload enabled for finalization")
        else:
            log_message(job_id, "INFO", "YouTube upload disabled for finalization")

        # Store the finalization preferences in job data for process_part_three to access
        job_data["finalization_options"] = {
            "selected_instrumental": selected_instrumental,
            "upload_to_youtube": upload_to_youtube
        }
        job_status_dict[job_id] = job_data

        # Spawn Phase 3 to generate final formats with selected instrumental
        # Pass the selected instrumental as a parameter for backward compatibility
        process_part_three.spawn(job_id, selected_instrumental)

        return JSONResponse({"status": "success", "message": "Finalization started with selected preferences"})

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error starting finalization: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


# Note: Additional review endpoints (preview video, audio, handlers) can be added here if needed
# For now, we're using a simpler approach where the review interface handles everything client-side


@api_app.post("/api/submit-file")
async def submit_file(
    audio_file: UploadFile = File(...),
    artist: str = Form(...),
    title: str = Form(...),
    styles_file: Optional[UploadFile] = File(None),
    styles_archive: Optional[UploadFile] = File(None),
    user: dict = Depends(authenticate_user),
):
    """Handle file upload and start processing."""
    try:
        # Generate unique job ID
        job_id = str(random.randint(10000000, 99999999))

        # Track token usage for this job
        if not track_job_usage(user["token"], job_id):
            return JSONResponse(status_code=500, content={"error": "Failed to track token usage"})

        # Create output directory
        output_dir = Path("/output") / job_id
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save audio file
        audio_file_path = output_dir / "uploaded.flac"
        with open(audio_file_path, "wb") as buffer:
            shutil.copyfileobj(audio_file.file, buffer)

        # Handle styles file if provided
        styles_file_path = None
        if styles_file:
            styles_file_path = output_dir / "styles.json"
            with open(styles_file_path, "wb") as buffer:
                shutil.copyfileobj(styles_file.file, buffer)

        # Handle styles archive if provided
        styles_archive_path = None
        if styles_archive:
            styles_archive_path = output_dir / "styles_archive.zip"
            with open(styles_archive_path, "wb") as buffer:
                shutil.copyfileobj(styles_archive.file, buffer)

        # Log the upload
        audio_size = audio_file_path.stat().st_size
        styles_size = styles_file_path.stat().st_size if styles_file_path else 0
        archive_size = styles_archive_path.stat().st_size if styles_archive_path else 0

        upload_msg = f"Audio file uploaded: {audio_file.filename} ({audio_size} bytes)"
        if styles_file_path:
            upload_msg += f", Styles file uploaded: {styles_file.filename} ({styles_size} bytes)"
        if styles_archive_path:
            upload_msg += f", Styles archive uploaded: {styles_archive.filename} ({archive_size} bytes)"
        print(upload_msg)

        # Initialize job status with timeline and user info
        update_job_status_with_timeline(
            job_id,
            "queued",
            progress=0,
            artist=artist,
            title=title,
            created_at=datetime.datetime.now().isoformat(),
            user_type=user["user_type"].value,
            remaining_uses=user["remaining_uses"],
            user_token=user["token"],  # Store user token for YouTube auth
        )

        # Job logs are now handled by Modal's native logging
        # No need to initialize job_logs_dict

        # Ensure files are committed to volume before spawning GPU function
        output_volume.commit()
        print(f"Volume committed for job {job_id} after file upload")
        
        # Give a small delay for Modal volume sync
        import time
        time.sleep(1)

        # Start processing job
        job = process_part_one_uploaded.spawn(
            job_id,
            str(audio_file_path),
            artist,
            title,
            str(styles_file_path) if styles_file_path else None,
            str(styles_archive_path) if styles_archive_path else None,
        )

        return {"job_id": job_id, "message": "Job started successfully"}

    except Exception as e:
        print(f"Error in submit_file: {str(e)}")
        return JSONResponse(status_code=500, content={"error": f"Failed to submit job: {str(e)}"})


# Expose API endpoints to the internet (API-only, frontend served separately via GitHub Pages)
@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,  # Mount volumes so API can write files to shared storage
    secrets=[modal.Secret.from_name("env-vars")],  # Add secrets for debug endpoints
    min_containers=1,  # Keep at least 1 container warm for API responsiveness
    max_containers=10,  # Allow scaling up to 10 containers
    scaledown_window=5 * 60,  # Wait 5 minutes before scaling down
)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def api_endpoint():
    """
    Expose the FastAPI application as a web endpoint for API access.
    Frontend is served separately via GitHub Pages.
    """
    return api_app


@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minutes for correction processing
    retries=0,
)
def add_lyrics_source(job_id: str, source: str, lyrics_text: str):
    """Add new lyrics source and rerun correction."""
    import json
    from pathlib import Path
    from lyrics_transcriber.types import CorrectionResult
    from lyrics_transcriber.correction.operations import CorrectionOperations

    try:
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(job_id)
        
        # Reload volume to see files from other containers
        output_volume.reload()

        log_message(job_id, "INFO", f"Adding lyrics source '{source}' with {len(lyrics_text)} characters")

        # Get job data
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise Exception(f"Job {job_id} not found")

        # Get correction data file path
        corrections_file_path = job_data.get("corrections_file")
        if not corrections_file_path:
            track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
            artist = job_data.get("artist", "Unknown")
            title = job_data.get("title", "Unknown")
            corrections_file_path = str(Path(track_output_dir) / "lyrics" / f"{artist} - {title} (Lyrics Corrections).json")

        # Load current correction data
        corrections_json_path = Path(corrections_file_path)
        if not corrections_json_path.exists():
            raise Exception(f"Corrections data not found at {corrections_json_path}")

        with open(corrections_json_path, "r") as f:
            corrections_data = json.load(f)

        correction_result = CorrectionResult.from_dict(corrections_data)

        # Use shared operation for adding lyrics source
        updated_result = CorrectionOperations.add_lyrics_source(
            correction_result=correction_result,
            source=source,
            lyrics_text=lyrics_text,
            cache_dir="/cache",
            logger=None,
        )

        # Save updated correction data
        with open(corrections_json_path, "w") as f:
            json.dump(updated_result.to_dict(), f, indent=2)

        # Commit volume changes to persist updated corrections file
        output_volume.commit()
        log_message(job_id, "INFO", "Volume committed after updating corrections")

        log_message(job_id, "SUCCESS", f"Successfully added lyrics source '{source}' and updated corrections")

        return {"status": "success", "data": updated_result.to_dict()}

    except ValueError as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Failed to add lyrics source: {error_msg}")

        raise Exception(f"Failed to add lyrics source: {error_msg}")
    except Exception as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Failed to add lyrics source: {error_msg}")

        raise Exception(f"Failed to add lyrics source: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minutes for correction processing
    retries=0,
)
def update_correction_handlers(job_id: str, enabled_handlers: List[str]):
    """Update enabled correction handlers and rerun correction."""
    import json
    from pathlib import Path
    from lyrics_transcriber.types import CorrectionResult
    from lyrics_transcriber.correction.operations import CorrectionOperations

    try:
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(job_id)
        
        # Reload volume to see files from other containers
        output_volume.reload()

        log_message(job_id, "INFO", f"Updating correction handlers: {enabled_handlers}")

        # Get job data
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise Exception(f"Job {job_id} not found")

        # Get correction data file path
        corrections_file_path = job_data.get("corrections_file")
        if not corrections_file_path:
            track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
            artist = job_data.get("artist", "Unknown")
            title = job_data.get("title", "Unknown")
            corrections_file_path = str(Path(track_output_dir) / "lyrics" / f"{artist} - {title} (Lyrics Corrections).json")

        # Load current correction data
        corrections_json_path = Path(corrections_file_path)
        if not corrections_json_path.exists():
            raise Exception(f"Corrections data not found at {corrections_json_path}")

        with open(corrections_json_path, "r") as f:
            corrections_data = json.load(f)

        correction_result = CorrectionResult.from_dict(corrections_data)

        # Use shared operation for updating handlers
        updated_result = CorrectionOperations.update_correction_handlers(
            correction_result=correction_result, enabled_handlers=enabled_handlers, cache_dir="/cache", logger=None
        )

        # Save updated correction data
        with open(corrections_json_path, "w") as f:
            json.dump(updated_result.to_dict(), f, indent=2)

        # Commit volume changes to persist updated corrections file
        output_volume.commit()
        log_message(job_id, "INFO", "Volume committed after updating handlers")

        log_message(job_id, "SUCCESS", f"Successfully updated handlers: {enabled_handlers}")

        return {"status": "success", "data": updated_result.to_dict()}

    except Exception as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Failed to update handlers: {error_msg}")

        raise Exception(f"Failed to update handlers: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minutes for preview video generation
    retries=0,
    gpu="any",
    cpu=8.0,
    memory=16384,
)
def generate_preview_video_modal(job_id: str, updated_data: Dict[str, Any]):
    """Generate a preview video with current corrections."""
    import json
    import time
    from pathlib import Path
    from lyrics_transcriber.types import CorrectionResult
    from lyrics_transcriber.core.config import OutputConfig
    from lyrics_transcriber.correction.operations import CorrectionOperations

    function_start_time = time.time()
    
    try:
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(job_id)
        
        log_message(job_id, "INFO", f"🎥 [STAGE 2] Modal function for preview video generation started at {datetime.datetime.now().isoformat()}")

        # Get job data and prepare configuration
        config_prep_start = time.time()
        log_message(job_id, "INFO", f"⚙️ [STAGE 2] Starting config preparation at {datetime.datetime.now().isoformat()}")
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise Exception(f"Job {job_id} not found")

        # Get correction data file path
        corrections_file_path = job_data.get("corrections_file")
        if not corrections_file_path:
            track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
            artist = job_data.get("artist", "Unknown")
            title = job_data.get("title", "Unknown")
            corrections_file_path = str(Path(track_output_dir) / "lyrics" / f"{artist} - {title} (Lyrics Corrections).json")

        # Load current correction data
        corrections_json_path = Path(corrections_file_path)
        if not corrections_json_path.exists():
            raise Exception(f"Corrections data not found at {corrections_json_path}")

        with open(corrections_json_path, "r") as f:
            corrections_data = json.load(f)

        base_correction_result = CorrectionResult.from_dict(corrections_data)

        # Find audio file
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")
        track_dir = Path(track_output_dir)

        # Ensure the base directory exists
        track_dir.mkdir(parents=True, exist_ok=True)

        # Find audio file using flexible pattern matching
        audio_file = None
        audio_patterns = [f"{artist} - {title}*.wav", "*.wav", "*.flac", "*.mp3"]
        for pattern in audio_patterns:
            audio_files = list(track_dir.glob(pattern))
            if audio_files:
                audio_file = audio_files[0]
                break

        if not audio_file or not audio_file.exists():
            raise Exception("Audio file not found for preview")

        # Set up preview config
        styles_file = job_data.get("styles_file_path") or str(Path(track_output_dir) / "styles_updated.json")

        # Verify the styles file exists
        if not Path(styles_file).exists():
            log_message(job_id, "WARNING", f"Styles file not found: {styles_file}")
            # Try to find any styles file in the directory
            possible_styles = list(Path(track_output_dir).glob("**/styles*.json"))
            if possible_styles:
                styles_file = str(possible_styles[0])
                log_message(job_id, "INFO", f"Using alternative styles file: {styles_file}")
            else:
                log_message(job_id, "WARNING", "No styles files found, using default styles")

        # Use dedicated preview volume instead of job output directory
        # This completely separates preview videos from audio files, eliminating volume conflicts
        preview_dir = Path(f"/previews/{job_id}")
        preview_dir.mkdir(parents=True, exist_ok=True)

        # Set up preview config with cache_dir pointing to dedicated preview volume
        # This ensures preview videos are isolated from audio file operations
        preview_config = OutputConfig(
            output_dir=str(track_output_dir),
            cache_dir=str(preview_dir),  # Point cache_dir to dedicated preview volume
            output_styles_json=styles_file,
            video_resolution="360p",  # Force 360p for preview
            render_video=True,
            generate_cdg=False,
            generate_plain_text=False,
            generate_lrc=False,
            fetch_lyrics=False,
            run_transcription=False,
            run_correction=False,
        )
        
        config_prep_duration = time.time() - config_prep_start
        log_message(job_id, "INFO", f"✅ [STAGE 2] Config preparation completed in {config_prep_duration:.3f}s")

        # Use shared operation for preview generation
        video_generation_start = time.time()
        log_message(job_id, "INFO", f"⚙️ [STAGE 2] Starting video generation (FFmpeg) at {datetime.datetime.now().isoformat()}")
        
        # Create a logger that's connected to the job logging system
        preview_logger = logging.getLogger(f"lyrics_transcriber.preview.{job_id}")
        preview_logger.setLevel(logging.DEBUG)  # Ensure we capture all video generation logs
        preview_logger.propagate = True  # Ensure it propagates to the root handler
        
        # Also ensure the VideoGenerator logger is properly configured 
        video_logger = logging.getLogger("lyrics_transcriber.output.video")
        video_logger.setLevel(logging.DEBUG)
        video_logger.propagate = True
        
        # Debug: Log the logger configuration
        log_message(job_id, "DEBUG", f"🔧 Preview logger: {preview_logger.name}, level: {preview_logger.level}, propagate: {preview_logger.propagate}")
        log_message(job_id, "DEBUG", f"🔧 Video logger: {video_logger.name}, level: {video_logger.level}, propagate: {video_logger.propagate}")
        log_message(job_id, "DEBUG", f"🔧 Root logger handlers: {len(logging.getLogger().handlers)}")
        
        # Test the logger to make sure it works
        preview_logger.info("🧪 Preview logger test - this should appear in logs")
        video_logger.info("🧪 Video logger test - this should appear in logs")
        
        result = CorrectionOperations.generate_preview_video(
            correction_result=base_correction_result,
            updated_data=updated_data,
            output_config=preview_config,
            audio_filepath=str(audio_file),
            artist=artist,
            title=title,
            logger=preview_logger,  # Use properly connected logger for video generation logs
        )
        
        video_generation_duration = time.time() - video_generation_start
        log_message(job_id, "SUCCESS", f"✅ [STAGE 2] Video generation completed in {video_generation_duration:.3f}s: {result['video_path']}")

        # Flush stdout before volume commit to ensure all logs are visible
        log_message(job_id, "INFO", f"📝 [STAGE 3] Flushing stdout before volume commit")
        import sys
        sys.stdout.flush()

        # Commit preview volume changes before returning (preview videos are now in separate volume)
        volume_commit_start = time.time()
        log_message(job_id, "INFO", f"💾 [STAGE 3] Starting preview volume commit at {datetime.datetime.now().isoformat()}")
        preview_volume.commit()
        volume_commit_duration = time.time() - volume_commit_start
        log_message(job_id, "INFO", f"✅ [STAGE 3] Preview volume commit completed in {volume_commit_duration:.3f}s")

        # Final flush after volume commit
        sys.stdout.flush()

        function_total_duration = time.time() - function_start_time
        log_message(job_id, "INFO", f"🎉 [STAGE 2] Modal function completed successfully in {function_total_duration:.3f}s")

        return result

    except Exception as e:
        error_msg = str(e)
        function_error_duration = time.time() - function_start_time
        log_message(job_id, "ERROR", f"❌ [STAGE 2] Modal function failed after {function_error_duration:.3f}s: {error_msg}")

        raise Exception(f"Failed to generate preview video: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


@api_app.get("/api/jobs/{job_id}/files")
async def list_job_files(job_id: str, user: dict = Depends(authenticate_user)):
    """List all available files for a job."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        track_dir = Path(track_output_dir)

        if not track_dir.exists():
            raise HTTPException(status_code=404, detail="Job output directory not found")

        files = []
        total_size = 0

        # Define file categories and their display order
        file_categories = {
            "final_videos": {
                "name": "Final Videos",
                "patterns": ["*Final Karaoke*.mp4", "*Final Karaoke*.mkv"],
                "description": "Completed karaoke videos ready for use",
            },
            "karaoke_files": {
                "name": "Karaoke Files",
                "patterns": ["*Final Karaoke*.zip", "*.cdg", "*.lrc"],
                "description": "CDG+MP3 and TXT+MP3 files for karaoke machines",
            },
            "working_videos": {
                "name": "Working Videos",
                "patterns": ["*With Vocals*.mp4", "*With Vocals*.mkv", "*Karaoke*.mp4"],
                "description": "Intermediate video files from processing",
            },
            "audio_files": {
                "name": "Audio Files",
                "patterns": ["*Instrumental*.flac", "*Vocals*.flac", "*.wav", "*.mp3"],
                "description": "Separated audio stems and instrumentals",
            },
            "image_files": {"name": "Image Files", "patterns": ["*.jpg", "*.png"], "description": "Title screens and thumbnails"},
            "text_files": {
                "name": "Text & Data Files",
                "patterns": ["*.txt", "*.json", "*.ass"],
                "description": "Lyrics, corrections, and subtitle files",
            },
        }

        # Collect all files and categorize them
        for category_id, category_info in file_categories.items():
            category_files = []

            for pattern in category_info["patterns"]:
                for file_path in track_dir.rglob(pattern):
                    if file_path.is_file():
                        try:
                            file_stat = file_path.stat()
                            relative_path = file_path.relative_to(track_dir)

                            file_info = {
                                "name": file_path.name,
                                "path": str(relative_path),
                                "full_path": str(file_path),
                                "size": file_stat.st_size,
                                "size_mb": round(file_stat.st_size / 1024 / 1024, 2),
                                "modified": datetime.datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                                "category": category_id,
                                "mime_type": get_mime_type(file_path.suffix),
                            }
                            category_files.append(file_info)
                            total_size += file_stat.st_size
                        except (OSError, PermissionError) as e:
                            # Skip files we can't access
                            continue

            if category_files:
                # Sort files within category by name
                category_files.sort(key=lambda x: x["name"])
                files.extend(category_files)

        # Group files by category for response
        categorized_files = {}
        for category_id, category_info in file_categories.items():
            category_files = [f for f in files if f["category"] == category_id]
            if category_files:
                categorized_files[category_id] = {
                    "name": category_info["name"],
                    "description": category_info["description"],
                    "files": category_files,
                    "count": len(category_files),
                }

        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")

        return JSONResponse(
            {
                "job_id": job_id,
                "artist": artist,
                "title": title,
                "status": job_data.get("status"),
                "total_files": len(files),
                "total_size": total_size,
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "categories": categorized_files,
                "all_files": files,  # Flat list for convenience
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


def get_mime_type(file_extension: str) -> str:
    """Get MIME type for file extension."""
    mime_types = {
        ".mp4": "video/mp4",
        ".mkv": "video/x-matroska",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".flac": "audio/flac",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".lrc": "text/plain",
        ".txt": "text/plain",
        ".json": "application/json",
        ".ass": "text/plain",
        ".cdg": "application/octet-stream",
        ".zip": "application/zip",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    }
    return mime_types.get(file_extension.lower(), "application/octet-stream")


@api_app.get("/api/jobs/{job_id}/files/{file_path:path}")
async def download_job_file(job_id: str, file_path: str, request: Request, user: dict = Depends(authenticate_user_or_token)):
    """Download a specific file from a job."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        track_dir = Path(track_output_dir)

        # Resolve the requested file path safely
        requested_file = track_dir / file_path

        # Security check: ensure the resolved path is still within the job directory
        try:
            requested_file = requested_file.resolve()
            track_dir = track_dir.resolve()
            if not str(requested_file).startswith(str(track_dir)):
                raise HTTPException(status_code=403, detail="Access denied")
        except (OSError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid file path")

        if not requested_file.exists() or not requested_file.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        # Determine MIME type
        mime_type = get_mime_type(requested_file.suffix)

        # For video files, add range support headers
        headers = {}
        if mime_type.startswith("video/"):
            headers.update(
                {"Accept-Ranges": "bytes", "Cache-Control": "no-cache, no-store, must-revalidate", "X-Content-Type-Options": "nosniff"}
            )

        return FileResponse(path=str(requested_file), filename=requested_file.name, media_type=mime_type, headers=headers)

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.post("/api/jobs/{job_id}/create-zip")
async def create_job_zip(job_id: str, request: Request, user: dict = Depends(authenticate_user)):
    """Create a ZIP file containing selected job files."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        # Get selected file paths from request body
        try:
            request_data = await request.json()
            selected_files = request_data.get("files", [])
            zip_name = request_data.get("name", f"karaoke-{job_id}-files.zip")
        except:
            # If no specific files requested, include all files
            selected_files = []
            zip_name = f"karaoke-{job_id}-all-files.zip"

        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        track_dir = Path(track_output_dir)

        if not track_dir.exists():
            raise HTTPException(status_code=404, detail="Job output directory not found")

        # Create ZIP file in a temp location within the job directory
        zip_path = track_dir / f"temp_{zip_name}"

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            files_added = 0

            if selected_files:
                # Add only selected files
                for file_path in selected_files:
                    source_file = track_dir / file_path

                    # Security check
                    try:
                        source_file = source_file.resolve()
                        if not str(source_file).startswith(str(track_dir.resolve())):
                            continue  # Skip files outside job directory
                    except (OSError, ValueError):
                        continue

                    if source_file.exists() and source_file.is_file():
                        # Use just the filename in the ZIP to avoid deep directory structure
                        arc_name = source_file.name
                        zip_file.write(source_file, arc_name)
                        files_added += 1
            else:
                # Add all files if none specified
                for file_path in track_dir.rglob("*"):
                    if file_path.is_file() and not file_path.name.startswith("temp_"):
                        # Create a reasonable archive structure
                        relative_path = file_path.relative_to(track_dir)
                        zip_file.write(file_path, str(relative_path))
                        files_added += 1

        if files_added == 0:
            zip_path.unlink(missing_ok=True)
            raise HTTPException(status_code=404, detail="No files found to zip")

        # Return info about the created zip file
        zip_stat = zip_path.stat()

        return JSONResponse(
            {
                "zip_path": zip_path.name,  # Just filename for download endpoint
                "files_count": files_added,
                "size": zip_stat.st_size,
                "size_mb": round(zip_stat.st_size / 1024 / 1024, 2),
                "download_url": f"/api/jobs/{job_id}/files/{zip_path.name}",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@api_app.get("/api/jobs/{job_id}/download-all")
async def download_all_files(job_id: str, request: Request, user: dict = Depends(authenticate_user_or_token)):
    """Create and download a ZIP of all job files."""
    try:
        # Check if user has access to this job
        if not check_job_access(job_id, user):
            raise HTTPException(status_code=403, detail="Access denied to this job")

        # Create zip with all files
        create_response = await create_job_zip(
            job_id, type("obj", (object,), {"json": lambda: {"files": [], "name": f"karaoke-{job_id}-complete.zip"}})(), user
        )

        if isinstance(create_response, JSONResponse):
            response_data = json.loads(create_response.body.decode())
            if "zip_path" in response_data:
                # Download the created zip
                return await download_job_file(job_id, response_data["zip_path"], request, user)

        raise HTTPException(status_code=500, detail="Failed to create zip file")

    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Job Timeline Management Functions
def update_job_status_with_timeline(job_id: str, new_status: str, progress: int = None, **additional_data):
    """Update job status and maintain timeline history."""
    current_time = datetime.datetime.now().isoformat()

    # Get existing job data
    job_data = job_status_dict.get(job_id, {})

    # Initialize timeline if it doesn't exist
    if "timeline" not in job_data:
        job_data["timeline"] = []

    # End the previous status if one exists
    timeline = job_data["timeline"]
    if timeline and timeline[-1].get("ended_at") is None:
        timeline[-1]["ended_at"] = current_time
        started_at = datetime.datetime.fromisoformat(timeline[-1]["started_at"])
        ended_at = datetime.datetime.fromisoformat(current_time)
        timeline[-1]["duration_seconds"] = int((ended_at - started_at).total_seconds())

    # Add new status to timeline
    timeline.append({"status": new_status, "started_at": current_time, "ended_at": None, "duration_seconds": None})

    # Update job data
    updated_job_data = {**job_data, **additional_data, "status": new_status, "timeline": timeline, "last_updated": current_time}

    if progress is not None:
        updated_job_data["progress"] = progress

    # Calculate total job duration
    if timeline:
        job_started = datetime.datetime.fromisoformat(timeline[0]["started_at"])
        total_duration = int((datetime.datetime.now() - job_started).total_seconds())
        updated_job_data["total_duration_seconds"] = total_duration

    job_status_dict[job_id] = updated_job_data
    return updated_job_data


def get_job_timeline_summary(job_data: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a summary of job timeline data."""
    timeline = job_data.get("timeline", [])
    if not timeline:
        return {}

    # Calculate phase durations
    phase_durations = {}
    total_duration = 0

    for phase in timeline:
        status = phase["status"]
        duration = phase.get("duration_seconds")

        if duration is not None:
            phase_durations[status] = duration
            total_duration += duration
        elif phase.get("ended_at") is None:
            # Current phase - calculate ongoing duration
            started_at = datetime.datetime.fromisoformat(phase["started_at"])
            ongoing_duration = int((datetime.datetime.now() - started_at).total_seconds())
            phase_durations[status] = ongoing_duration
            total_duration += ongoing_duration

    # Find longest and shortest phases
    completed_phases = {k: v for k, v in phase_durations.items() if v > 0}
    longest_phase = max(completed_phases.items(), key=lambda x: x[1]) if completed_phases else None
    shortest_phase = min(completed_phases.items(), key=lambda x: x[1]) if completed_phases else None

    return {
        "phase_durations": phase_durations,
        "total_duration_seconds": total_duration,
        "total_duration_formatted": format_duration(total_duration),
        "longest_phase": {"status": longest_phase[0], "duration": longest_phase[1]} if longest_phase else None,
        "shortest_phase": {"status": shortest_phase[0], "duration": shortest_phase[1]} if shortest_phase else None,
        "phases_completed": len([p for p in timeline if p.get("ended_at") is not None]),
        "current_phase": timeline[-1]["status"] if timeline else None,
        "started_at": timeline[0]["started_at"] if timeline else None,
    }


def format_duration(seconds: int) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        return f"{minutes}m {remaining_seconds}s"
    else:
        hours = seconds // 3600
        remaining_minutes = (seconds % 3600) // 60
        return f"{hours}h {remaining_minutes}m"


async def get_modal_logs_for_job(
    job_id: str, 
    job_data: Dict[str, Any], 
    include_filter: str = "",
    exclude_filter: str = "",
    level_filter: str = "",
    limit: int = 1000,
    use_regex: bool = False
) -> List[Dict[str, Any]]:
    """Get detailed job logs from local log file plus timeline information with server-side filtering."""
    from datetime import datetime
    import re
    import asyncio
    
    log_entries = []
    
    # First, try to read detailed logs from the local log file
    try:
        # CRITICAL: Reload volume and wait a moment for sync to complete
        output_volume.reload()
        await asyncio.sleep(0.5)  # Give volume sync time to complete
        
        log_file_path = Path(f"/output/{job_id}/job_logs.jsonl")
        
        if log_file_path.exists():
            with open(log_file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            log_entry = json.loads(line)
                            log_entries.append(log_entry)
                        except json.JSONDecodeError:
                            # Skip malformed lines
                            continue
        
    except Exception as e:
        # If we can't read the log file, add an error entry
        log_entries.append({
            "timestamp": datetime.now().isoformat(),
            "level": "WARNING",
            "message": f"Could not read detailed logs: {str(e)}"
        })
    
    # If we don't have any detailed logs, fall back to timeline-based logs
    if not log_entries or len(log_entries) <= 1:  # Only header or empty
        log_entries = []
        
        # Add job creation info  
        if job_data.get("created_at"):
            artist = job_data.get("artist", "Unknown")
            title = job_data.get("title", "Unknown")
            log_entries.append({
                "timestamp": job_data["created_at"],
                "level": "INFO",
                "message": f"🎵 Job created: {artist} - {title}"
            })
            
            # Add URL or filename info
            if job_data.get("url"):
                log_entries.append({
                    "timestamp": job_data["created_at"],
                    "level": "INFO", 
                    "message": f"🔗 Source: {job_data['url']}"
                })
            elif job_data.get("filename"):
                log_entries.append({
                    "timestamp": job_data["created_at"],
                    "level": "INFO",
                    "message": f"📁 Uploaded file: {job_data['filename']}"
                })
        
        # Add timeline entries
        timeline = job_data.get("timeline", [])
        for phase in timeline:
            status = phase["status"]
            started_at = phase["started_at"]
            ended_at = phase.get("ended_at")
            duration = phase.get("duration_seconds")
            
            # Status start message
            status_emoji = {
                "queued": "⏳", "processing": "⚙️", "awaiting_review": "👀",
                "reviewing": "✏️", "ready_for_finalization": "🎬", "rendering": "🎨",
                "finalizing": "🎯", "complete": "✅", "error": "❌"
            }.get(status, "📝")
            
            log_entries.append({
                "timestamp": started_at,
                "level": "INFO",
                "message": f"{status_emoji} Phase started: {status.replace('_', ' ').title()}"
            })
            
            # Status end message with duration
            if ended_at and duration is not None:
                duration_str = format_duration(duration)
                log_entries.append({
                    "timestamp": ended_at,
                    "level": "INFO", 
                    "message": f"✓ Phase completed: {status.replace('_', ' ').title()} ({duration_str})"
                })
    
    # Always add current status at the end
    current_status = job_data.get("status", "unknown")
    progress = job_data.get("progress", 0)
    last_updated = job_data.get("last_updated", datetime.now().isoformat())
    
    status_emoji = {
        "queued": "⏳", "processing": "⚙️", "awaiting_review": "👀",
        "reviewing": "✏️", "ready_for_finalization": "🎬", "rendering": "🎨", 
        "finalizing": "🎯", "complete": "✅", "error": "❌"
    }.get(current_status, "📝")
    
    log_entries.append({
        "timestamp": last_updated,
        "level": "INFO",
        "message": f"{status_emoji} Current Status: {current_status.replace('_', ' ').title()} ({progress}%)"
    })
    
    # Add error info if present
    if job_data.get("error"):
        log_entries.append({
            "timestamp": last_updated,
            "level": "ERROR",
            "message": f"❌ Error: {job_data['error']}"
        })
    
    # Sort by timestamp (oldest first for chronological order)
    log_entries.sort(key=lambda x: x["timestamp"])
    
    # Apply server-side filtering
    filtered_entries = apply_server_side_log_filters(
        log_entries, include_filter, exclude_filter, level_filter, use_regex
    )
    
    # Apply limit (get most recent entries if limit is specified)
    if limit > 0 and len(filtered_entries) > limit:
        filtered_entries = filtered_entries[-limit:]
    
    return filtered_entries


def apply_server_side_log_filters(
    log_entries: List[Dict[str, Any]], 
    include_filter: str, 
    exclude_filter: str, 
    level_filter: str, 
    use_regex: bool
) -> List[Dict[str, Any]]:
    """Apply server-side filtering to log entries."""
    import re
    
    filtered_entries = []
    
    # Define log levels in order from lowest to highest severity
    log_levels = {
        'DEBUG': 0,
        'INFO': 1,
        'WARNING': 2,
        'ERROR': 3,
        'CRITICAL': 4
    }
    
    for log_entry in log_entries:
        # Level filtering (show selected level and above)
        if level_filter:
            entry_level = log_entry.get("level", "INFO")
            entry_level_value = log_levels.get(entry_level, 1)
            selected_level_value = log_levels.get(level_filter, 1)
            
            if entry_level_value < selected_level_value:
                continue
        
        # Combine searchable text
        search_text = f"{log_entry.get('level', '')} {log_entry.get('message', '')}".lower()
        
        # Apply exclude filter first
        if exclude_filter:
            try:
                if use_regex:
                    if re.search(exclude_filter, search_text, re.IGNORECASE):
                        continue
                else:
                    if exclude_filter.lower() in search_text:
                        continue
            except re.error:
                # If regex is invalid, fall back to string matching
                if exclude_filter.lower() in search_text:
                    continue
        
        # Apply include filter
        if include_filter:
            try:
                if use_regex:
                    if not re.search(include_filter, search_text, re.IGNORECASE):
                        continue
                else:
                    if include_filter.lower() not in search_text:
                        continue
            except re.error:
                # If regex is invalid, fall back to string matching
                if include_filter.lower() not in search_text:
                    continue
        
        # If we reach here, the entry passed all filters
        filtered_entries.append(log_entry)
    
    return filtered_entries


@api_app.get("/api/corrections/{job_id}/instrumentals")
async def get_available_instrumentals(job_id: str):
    """Get list of available instrumental files for a job."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") not in ["reviewing", "awaiting_review", "ready_for_finalization"]:
            raise HTTPException(status_code=400, detail="Job is not ready for instrumental selection")

        # Get job details
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        track_dir = Path(track_output_dir)

        # Find all instrumental files
        instrumental_files = list(track_dir.glob(f"*Instrumental*.flac"))

        if not instrumental_files:
            raise HTTPException(status_code=404, detail="No instrumental files found")

        # Create list of instrumental options with metadata
        instrumentals = []
        for inst_file in instrumental_files:
            try:
                file_stat = inst_file.stat()
                file_size_mb = round(file_stat.st_size / 1024 / 1024, 1)

                # Determine instrumental type based on filename
                filename = inst_file.name
                instrumental_type = "Unknown"
                recommended = False
                description = ""

                if "+BV" in filename:
                    instrumental_type = "Instrumental With Backing Vocals"
                    description = "Typically includes background vocals and harmonies - listen all the way through first to see if this sounds good!"
                elif "model_bs_roformer" in filename:
                    instrumental_type = "Clean Instrumental"
                    description = "Pure instrumental without any vocals - safe option if you're not sure"
                    recommended = True  # Clean instrumental is safest option
                elif "htdemucs" in filename:
                    instrumental_type = "Other Stems"
                    description = "Alternative separation model"
                instrumentals.append(
                    {
                        "filename": inst_file.name,
                        "path": str(inst_file.relative_to(track_dir)),
                        "size_mb": file_size_mb,
                        "type": instrumental_type,
                        "description": description,
                        "recommended": recommended,
                        "audio_url": f"/corrections/{job_id}/instrumental-preview/{inst_file.name}",
                    }
                )

            except Exception as e:
                log_message(job_id, "WARNING", f"Error processing instrumental file {inst_file}: {e}")
                continue

        # Sort instrumentals with recommended first
        instrumentals.sort(key=lambda x: (not x["recommended"], x["filename"]))

        log_message(job_id, "INFO", f"Found {len(instrumentals)} instrumental options")

        return JSONResponse({"job_id": job_id, "instrumentals": instrumentals, "total_count": len(instrumentals)})

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error getting instrumentals: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting instrumentals: {str(e)}")


@api_app.get("/api/corrections/{job_id}/instrumental-preview/{filename}")
async def get_instrumental_preview(job_id: str, filename: str):
    """Get instrumental audio file for preview."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()

        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")

        if job_data.get("status") not in ["reviewing", "awaiting_review", "ready_for_finalization"]:
            raise HTTPException(status_code=400, detail="Job is not ready for instrumental selection")

        # Get job details and find the specific instrumental file
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        track_dir = Path(track_output_dir)

        # Security: only allow files that match the expected instrumental pattern
        if not filename.endswith(".flac") or "Instrumental" not in filename:
            raise HTTPException(status_code=403, detail="Invalid file requested")

        instrumental_file = track_dir / filename

        if not instrumental_file.exists() or not instrumental_file.is_file():
            raise HTTPException(status_code=404, detail="Instrumental file not found")

        # Verify it's actually in the track directory (security check)
        try:
            instrumental_file.resolve().relative_to(track_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=403, detail="Access denied")

        log_message(job_id, "DEBUG", f"Serving instrumental preview: {filename}")

        return FileResponse(
            path=str(instrumental_file),
            filename=f"instrumental-{job_id}-{filename}",
            media_type="audio/flac",
            headers={
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error serving instrumental preview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving instrumental preview: {str(e)}")


# Add job cloning functions after the other admin endpoints

class CloneJobRequest(BaseModel):
    source_job_id: str
    target_phase: str


@api_app.post("/api/admin/jobs/{job_id}/clone")
async def clone_job(job_id: str, request: CloneJobRequest, admin: dict = Depends(authenticate_admin)):
    """Clone a job at a specific phase (admin only)."""
    try:
        result = clone_job_at_phase.remote(job_id, request.target_phase)
        
        return JSONResponse({
            "success": True,
            "message": f"Job cloned successfully",
            "new_job_id": result["new_job_id"],
            "target_phase": request.target_phase
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error cloning job: {str(e)}"}, status_code=500)


@api_app.get("/api/admin/jobs/{job_id}/clone-info")
async def get_clone_info(job_id: str, admin: dict = Depends(authenticate_admin)):
    """Get information about available clone points for a job (admin only)."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        current_status = job_data.get("status", "unknown")
        timeline = job_data.get("timeline", [])
        
        # Define available clone points based on current job status
        available_phases = []
        
        # Add clone points based on what phases the job has completed
        completed_phases = [phase["status"] for phase in timeline if phase.get("ended_at")]
        
        if "processing" in completed_phases or current_status in ["awaiting_review", "reviewing", "ready_for_finalization", "rendering", "finalizing", "complete"]:
            available_phases.append({
                "phase": "awaiting_review",
                "name": "After Phase 1 (Processing Complete)",
                "description": "Clone to test lyrics review and Phase 2 (video generation)"
            })
        
        if "reviewing" in completed_phases or current_status in ["ready_for_finalization", "rendering", "finalizing", "complete"]:
            available_phases.append({
                "phase": "ready_for_finalization", 
                "name": "After Phase 2 (Video Generated)",
                "description": "Clone to test instrumental selection and Phase 3 (finalization)"
            })
        

        
        return JSONResponse({
            "success": True,
            "job_id": job_id,
            "current_status": current_status,
            "available_phases": available_phases,
            "artist": job_data.get("artist", "Unknown"),
            "title": job_data.get("title", "Unknown")
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error getting clone info: {str(e)}"}, status_code=500)


@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minute timeout for file copying
    retries=0,
)
def clone_job_at_phase(source_job_id: str, target_phase: str):
    """Clone a job at a specific phase for testing purposes."""
    import shutil
    import uuid
    from pathlib import Path
    
    try:
        # Generate new job ID
        new_job_id = str(uuid.uuid4())[:8]
        
        # Set up logging to capture ALL log messages from all modules
        log_handler = setup_job_logging(new_job_id)
        
        log_message(new_job_id, "INFO", f"Cloning job {source_job_id} at phase {target_phase}")
        
        # Get source job data
        source_job_data = job_status_dict.get(source_job_id)
        if not source_job_data:
            raise Exception(f"Source job {source_job_id} not found")
        
        # Reload volumes to see latest files
        output_volume.reload()
        cache_volume.reload()
        
        # Define source and target directories
        source_dir = Path(f"/output/{source_job_id}")
        target_dir = Path(f"/output/{new_job_id}")
        
        if not source_dir.exists():
            raise Exception(f"Source job directory not found: {source_dir}")
        
        # Create target directory
        target_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all files from source to target
        log_message(new_job_id, "INFO", f"Copying files from {source_dir} to {target_dir}")
        files_copied = 0
        total_size = 0
        
        for item in source_dir.rglob("*"):
            if item.is_file():
                # Calculate relative path and create target path
                relative_path = item.relative_to(source_dir)
                target_path = target_dir / relative_path
                
                # Create parent directories if needed
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Copy file and log the operation
                file_size = item.stat().st_size
                shutil.copy2(item, target_path)
                files_copied += 1
                total_size += file_size
                
                # Log every file copied for debugging
                log_message(new_job_id, "DEBUG", f"Copied: {relative_path} ({file_size} bytes)")
                
                # Special logging for important files
                if "With Vocals" in item.name:
                    log_message(new_job_id, "INFO", f"✅ Copied With Vocals file: {relative_path}")
                elif "Instrumental" in item.name and item.suffix == ".flac":
                    log_message(new_job_id, "INFO", f"✅ Copied instrumental file: {relative_path}")
        
        log_message(new_job_id, "INFO", f"File copy completed: {files_copied} files, {total_size / 1024 / 1024:.1f} MB total")
        
        # Create cloned job data
        clone_data = source_job_data.copy()
        
        # Update job metadata
        clone_data["status"] = target_phase
        clone_data["progress"] = get_progress_for_phase(target_phase)
        clone_data["track_output_dir"] = str(target_dir)
        clone_data["created_at"] = datetime.datetime.now().isoformat()
        clone_data["last_updated"] = datetime.datetime.now().isoformat()
        clone_data["cloned_from"] = source_job_id
        clone_data["clone_target_phase"] = target_phase
        
        # IMPORTANT: Preserve user_token for YouTube authentication
        # This ensures cloned jobs can still access the original user's YouTube credentials
        if "user_token" in source_job_data:
            clone_data["user_token"] = source_job_data["user_token"]
            log_message(new_job_id, "INFO", f"Preserved user_token from source job for YouTube authentication")
        else:
            log_message(new_job_id, "WARNING", f"Source job has no user_token - YouTube upload may not work in cloned job")
        
        # Don't modify artist/title as it breaks file finding logic
        # The cloned_from and clone_target_phase fields provide sufficient tracking
        
        # Update file paths in job data to point to new directory
        if "corrections_file" in clone_data:
            old_path = clone_data["corrections_file"]
            if old_path and old_path.startswith(f"/output/{source_job_id}"):
                clone_data["corrections_file"] = old_path.replace(f"/output/{source_job_id}", f"/output/{new_job_id}")
        
        if "styles_file_path" in clone_data:
            old_path = clone_data["styles_file_path"]
            if old_path and old_path.startswith(f"/output/{source_job_id}"):
                clone_data["styles_file_path"] = old_path.replace(f"/output/{source_job_id}", f"/output/{new_job_id}")
        
        # Create a new timeline for the cloned job
        current_time = datetime.datetime.now().isoformat()
        clone_data["timeline"] = [{
            "status": target_phase,
            "started_at": current_time,
            "ended_at": None,
            "duration_seconds": None
        }]
        
        # Store cloned job data
        job_status_dict[new_job_id] = clone_data
        
        # Clone job logging will be handled by Modal's native logging
        # Initial clone message will appear in Modal logs
        
        # Commit volume changes to persist the cloned files
        output_volume.commit()
        log_message(new_job_id, "INFO", "Volume committed after cloning")
        
        log_message(new_job_id, "SUCCESS", f"Job successfully cloned from {source_job_id} at phase {target_phase}")
        
        return {
            "status": "success",
            "new_job_id": new_job_id,
            "target_phase": target_phase,
            "message": f"Job cloned successfully from {source_job_id}"
        }
        
    except Exception as e:
        error_msg = str(e)
        log_message(new_job_id if 'new_job_id' in locals() else "unknown", "ERROR", f"Job cloning failed: {error_msg}")
        raise Exception(f"Job cloning failed: {error_msg}")
    finally:
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            if 'log_handler' in locals():
                root_logger.removeHandler(log_handler)
        except:
            pass


def get_progress_for_phase(phase: str) -> int:
    """Get appropriate progress percentage for a given phase."""
    phase_progress = {
        "queued": 0,
        "processing": 25,
        "awaiting_review": 75,
        "reviewing": 77,
        "ready_for_finalization": 85,
        "rendering": 90,
        "finalizing": 95,
        "complete": 100,
        "error": 0
    }
    return phase_progress.get(phase, 0)


@api_app.post("/api/admin/jobs/{job_id}/resume-at-phase")
async def resume_job_at_phase(job_id: str, request: dict, admin: dict = Depends(authenticate_admin)):
    """Resume a cloned job at a specific phase (admin only)."""
    try:
        target_phase = request.get("target_phase")
        selected_instrumental = request.get("selected_instrumental")
        corrected_data = request.get("corrected_data", {})
        
        if not target_phase:
            raise HTTPException(status_code=400, detail="target_phase is required")
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Spawn the appropriate processing function based on target phase
        if target_phase == "ready_for_finalization" and selected_instrumental:
            # Resume at phase 3 with instrumental selection
            process_part_three.spawn(job_id, selected_instrumental)
            message = f"Resumed job {job_id} at phase 3 (finalization) with instrumental: {selected_instrumental}"
            
        elif target_phase == "reviewing" and corrected_data:
            # Resume at phase 2 with corrected data
            process_part_two.spawn(job_id, corrected_data)
            message = f"Resumed job {job_id} at phase 2 (video generation) with corrections"
            
        elif target_phase == "awaiting_review":
            # Job is ready for manual review - no automatic resumption needed
            message = f"Job {job_id} is ready for review at phase 1 completion"
            
        else:
            raise HTTPException(status_code=400, detail=f"Cannot resume at phase {target_phase} with provided parameters")
        
        return JSONResponse({
            "success": True,
            "message": message,
            "job_id": job_id,
            "target_phase": target_phase
        })
        
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Error resuming job: {str(e)}"}, status_code=500)
