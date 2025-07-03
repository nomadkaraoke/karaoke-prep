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

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel



# Define the environment for our functions - using Python 3.13 for latest features
karaoke_image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install([
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
        "audio-separator[cpu]>=0.34.0",
        "lyrics-converter>=0.2.1",
        "lyrics-transcriber>=0.54",
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
        "python-multipart>=0.0.6",
        "requests>=2.31.0",
    ])
    .apt_install([
        "ffmpeg",
        "libsndfile1",
        "libsox-dev",
        "sox",
    ])
    .add_local_dir("karaoke_gen", "/root/karaoke_gen")
    .add_local_file("core.py", "/root/core.py")
)

# Define the Modal app
app = modal.App("karaoke-generator-webapp")

# Define persistent storage volumes
model_volume = modal.Volume.from_name("karaoke-models", create_if_missing=True)
output_volume = modal.Volume.from_name("karaoke-output", create_if_missing=True)
cache_volume = modal.Volume.from_name("karaoke-cache", create_if_missing=True)

# Define serverless dictionaries to hold job states and logs
job_status_dict = modal.Dict.from_name("karaoke-job-statuses", create_if_missing=True)
job_logs_dict = modal.Dict.from_name("karaoke-job-logs", create_if_missing=True)

# Mount volumes to specific paths inside the container
VOLUME_CONFIG = {
    "/models": model_volume,
    "/output": output_volume,
    "/cache": cache_volume
}

# Pydantic models for API requests
class JobSubmissionRequest(BaseModel):
    url: str

class LyricsReviewRequest(BaseModel):
    lyrics: str

class JobLogHandler(logging.Handler):
    """Custom logging handler that forwards log messages to job_logs_dict"""
    
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id
        # Prevent recursion by not processing our own log messages
        self.processing = False
        
    def emit(self, record):
        if self.processing:
            return
            
        try:
            self.processing = True
            
            # Format the log message
            message = self.format(record)
            
            # Create log entry
            log_entry = {
                "timestamp": datetime.datetime.now().isoformat(),
                "level": record.levelname,
                "message": message
            }
            
            # Get existing logs or create new list
            existing_logs = job_logs_dict.get(self.job_id, [])
            existing_logs.append(log_entry)
            job_logs_dict[self.job_id] = existing_logs
            
        except Exception:
            # Silently ignore errors to prevent recursion
            pass
        finally:
            self.processing = False

def setup_job_logging(job_id: str):
    """Set up logging to capture all messages for a job"""
    
    # Create custom handler
    handler = JobLogHandler(job_id)
    
    # Set up formatter to match the CLI output format
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    
    # Only add handler to root logger - this will capture all logging via propagation
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    
    return handler

def log_message(job_id: str, level: str, message: str):
    """Log a message with timestamp and level."""
    timestamp = datetime.datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "level": level,
        "message": message
    }
    
    # Get existing logs or create new list
    existing_logs = job_logs_dict.get(job_id, [])
    existing_logs.append(log_entry)
    job_logs_dict[job_id] = existing_logs
    
    print(f"[{level}] {message}")

# Cache Utility Functions
class CacheManager:
    """Manages persistent caching across Modal functions."""
    
    def __init__(self, cache_dir: str = "/cache", logger=None):
        self.cache_dir = Path(cache_dir)
        self.logger = logger or logging.getLogger(__name__)
        
        # Create cache subdirectories
        self.audio_hashes_dir = self.cache_dir / "audio_hashes"
        self.audioshake_dir = self.cache_dir / "audioshake_responses"
        self.models_dir = self.cache_dir / "models"
        self.transcription_dir = self.cache_dir / "transcriptions"
        
        # Ensure directories exist
        for dir_path in [self.audio_hashes_dir, self.audioshake_dir, self.models_dir, self.transcription_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)
    
    def get_audio_hash(self, audio_file_path: str) -> str:
        """Generate SHA256 hash of audio file for cache key."""
        import hashlib
        
        hash_file = self.audio_hashes_dir / f"{Path(audio_file_path).name}.hash"
        
        # Check if hash already cached
        if hash_file.exists():
            with open(hash_file, 'r') as f:
                cached_hash = f.read().strip()
                self.logger.debug(f"Found cached audio hash: {cached_hash}")
                return cached_hash
        
        # Calculate hash
        sha256_hash = hashlib.sha256()
        with open(audio_file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        
        audio_hash = sha256_hash.hexdigest()
        
        # Cache the hash
        with open(hash_file, 'w') as f:
            f.write(audio_hash)
        
        self.logger.info(f"Generated and cached audio hash: {audio_hash}")
        return audio_hash
    
    def cache_audioshake_response(self, audio_hash: str, response_data: dict) -> None:
        """Cache AudioShake API response by audio hash."""
        cache_file = self.audioshake_dir / f"{audio_hash}.json"
        
        with open(cache_file, 'w') as f:
            json.dump({
                "timestamp": datetime.datetime.now().isoformat(),
                "audio_hash": audio_hash,
                "response": response_data
            }, f, indent=2)
        
        self.logger.info(f"Cached AudioShake response for hash {audio_hash}")
    
    def get_cached_audioshake_response(self, audio_hash: str) -> Optional[dict]:
        """Retrieve cached AudioShake response by audio hash."""
        cache_file = self.audioshake_dir / f"{audio_hash}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
                cached_data = json.load(f)
            
            # Check if cache is not too old (optional - remove if you want indefinite caching)
            cache_age_days = 30
            cache_time = datetime.datetime.fromisoformat(cached_data["timestamp"])
            if (datetime.datetime.now() - cache_time).days > cache_age_days:
                self.logger.info(f"AudioShake cache expired for hash {audio_hash}")
                return None
            
            self.logger.info(f"Found cached AudioShake response for hash {audio_hash}")
            return cached_data["response"]
            
        except (json.JSONDecodeError, KeyError) as e:
            self.logger.warning(f"Invalid cache file for hash {audio_hash}: {e}")
            return None
    
    def cache_model_file(self, model_name: str, model_path: str) -> str:
        """Cache a model file and return the cached path."""
        cached_model_path = self.models_dir / model_name
        
        if not cached_model_path.exists():
            shutil.copy2(model_path, cached_model_path)
            self.logger.info(f"Cached model {model_name}")
        else:
            self.logger.debug(f"Model {model_name} already cached")
        
        return str(cached_model_path)
    
    def cache_transcription_result(self, audio_hash: str, transcription_data: dict) -> None:
        """Cache transcription results by audio hash."""
        cache_file = self.transcription_dir / f"{audio_hash}.json"
        
        with open(cache_file, 'w') as f:
            json.dump({
                "timestamp": datetime.datetime.now().isoformat(),
                "audio_hash": audio_hash,
                "transcription": transcription_data
            }, f, indent=2)
        
        self.logger.info(f"Cached transcription result for hash {audio_hash}")
    
    def get_cached_transcription_result(self, audio_hash: str) -> Optional[dict]:
        """Retrieve cached transcription result by audio hash."""
        cache_file = self.transcription_dir / f"{audio_hash}.json"
        
        if not cache_file.exists():
            return None
        
        try:
            with open(cache_file, 'r') as f:
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
        
        for cache_dir in [self.audioshake_dir, self.transcription_dir]:
            for cache_file in cache_dir.glob("*.json"):
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

# Example AudioShake API caching integration
def cached_audioshake_request(cache_manager: CacheManager, audio_file_path: str, api_endpoint: str, api_data: dict, job_id: str = None) -> dict:
    """
    Example function showing how to cache AudioShake API responses.
    
    This is a template you can use to modify the lyrics-transcriber library
    or your karaoke processing code to cache AudioShake API calls.
    """
    # Get audio hash for cache key
    audio_hash = cache_manager.get_audio_hash(audio_file_path)
    
    # Check for cached response
    cached_response = cache_manager.get_cached_audioshake_response(audio_hash)
    if cached_response:
        if job_id:
            log_message(job_id, "INFO", f"Using cached AudioShake response for hash {audio_hash}")
        return cached_response
    
    # If no cache, make the actual API call
    import requests
    import os
    
    if job_id:
        log_message(job_id, "INFO", f"Making AudioShake API call for hash {audio_hash}")
    
    # Make the API request (example - adjust based on actual AudioShake API)
    headers = {"Authorization": f"Bearer {os.environ.get('AUDIOSHAKE_API_TOKEN')}"}
    response = requests.post(api_endpoint, json=api_data, headers=headers)
    
    if response.status_code == 200:
        response_data = response.json()
        
        # Cache the successful response
        cache_manager.cache_audioshake_response(audio_hash, response_data)
        
        if job_id:
            log_message(job_id, "INFO", f"Cached AudioShake response for hash {audio_hash}")
        
        return response_data
    else:
        # Don't cache error responses
        raise Exception(f"AudioShake API error: {response.status_code} - {response.text}")

# Add a cache warming function for common use cases
@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minute timeout for cache operations
)
def warm_cache():
    """Warm up the cache with commonly used models or data."""
    try:
        cache_manager = CacheManager("/cache")
        
        # Example: Pre-load commonly used model files
        model_files = [
            "/models/model_bs_roformer_ep_317_sdr_12.9755.ckpt",
            "/models/mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"
        ]
        
        for model_file in model_files:
            if Path(model_file).exists():
                model_name = Path(model_file).name
                cache_manager.cache_model_file(model_name, model_file)
                print(f"Cached model: {model_name}")
        
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
)
async def process_part_one(job_id: str, youtube_url: str):
    """First phase: Download audio, separate, and transcribe lyrics."""
    import sys
    import traceback
    
    try:
        # Set up logging to capture all messages
        log_handler = setup_job_logging(job_id)
        
        from core import ServerlessKaraokeProcessor
        
        log_message(job_id, "INFO", f"Starting job {job_id} for URL: {youtube_url}")
        
        # Update status
        update_job_status_with_timeline(
            job_id, 
            "processing", 
            progress=10,
            url=youtube_url,
            created_at=datetime.datetime.now().isoformat()
        )
        
        # Initialize processor - this now uses the same code path as the CLI
        processor = ServerlessKaraokeProcessor(model_dir="/models", output_dir="/output")
        
        # Process using the full KaraokePrep workflow (same as CLI)
        log_message(job_id, "INFO", "Starting full karaoke processing workflow...")
        result = await processor.process_url(job_id, youtube_url)
        
        # Update status to awaiting review
        update_job_status_with_timeline(
            job_id, 
            "awaiting_review", 
            progress=75,
            url=youtube_url,
            track_data=result["track_data"],
            track_output_dir=result["track_output_dir"]
        )
        
        log_message(job_id, "SUCCESS", f"Processing completed for job {job_id}. Ready for review.")
        
        # Clean up logging handler
        root_logger = logging.getLogger()
        root_logger.removeHandler(log_handler)
        
        return {"status": "success", "message": "Processing completed, ready for review"}
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        log_message(job_id, "ERROR", f"Phase 1 failed: {error_msg}")
        log_message(job_id, "ERROR", f"Traceback: {error_traceback}")
        
        update_job_status_with_timeline(
            job_id, 
            "error", 
            progress=0,
            url=youtube_url,
            error=error_msg,
            traceback=error_traceback
        )
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Phase 1 failed: {error_msg}")

@app.function(
    image=karaoke_image,
    gpu="any",
    volumes=VOLUME_CONFIG,
    timeout=1800,
)
def process_part_two(job_id: str, updated_correction_data: Optional[Dict[str, Any]] = None):
    """Second phase: Generate final video with corrected lyrics."""
    import sys
    import traceback
    from pathlib import Path
    
    try:
        # Set up logging to capture all messages
        log_handler = setup_job_logging(job_id)
        
        from lyrics_transcriber.output.generator import OutputGenerator
        from lyrics_transcriber.core.config import OutputConfig
        from lyrics_transcriber.types import CorrectionResult
        
        log_message(job_id, "INFO", f"Starting phase 2 (video generation) for job {job_id}")
        
        # Update status
        job_data = job_status_dict.get(job_id, {})
        update_job_status_with_timeline(job_id, "rendering", progress=80, **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]})
        
        # Get job info
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")
        
        # Load correction data
        if updated_correction_data:
            log_message(job_id, "INFO", "Using updated correction data from review")
            correction_result = CorrectionResult.from_dict(updated_correction_data)
        else:
            # Load from saved file
            corrections_file_path = job_data.get("corrections_file")
            if not corrections_file_path:
                corrections_file_path = str(Path(track_output_dir) / "lyrics" / f"{artist} - {title} (Lyrics Corrections).json")
            
            log_message(job_id, "INFO", f"Loading correction data from {corrections_file_path}")
            
            if not Path(corrections_file_path).exists():
                raise Exception(f"Corrections file not found: {corrections_file_path}")
            
            with open(corrections_file_path, 'r') as f:
                corrections_data = json.load(f)
            
            correction_result = CorrectionResult.from_dict(corrections_data)
        
        # Set up output config for Phase 2 (video generation)
        styles_file = job_data.get("styles_file_path") or str(Path(track_output_dir) / "styles_updated.json")
        output_config = OutputConfig(
            output_styles_json=styles_file,
            output_dir=str(Path(track_output_dir) / "lyrics"),
            cache_dir="/root/lyrics-transcriber-cache",
            render_video=True,  # Now we DO want video generation
            generate_cdg=True,  # Now we DO want CDG generation
            video_resolution="4k",
            generate_plain_text=False,  # Already done in Phase 1
            generate_lrc=False,  # Already done in Phase 1
            fetch_lyrics=False,  # Already done in Phase 1
            run_transcription=False,  # Already done in Phase 1
            run_correction=False,  # Already done in Phase 1
        )
        
        # Initialize output generator
        output_generator = OutputGenerator(config=output_config, logger=logging.getLogger(__name__))
        
        # Find the audio file
        audio_file_path = Path(track_output_dir) / f"{artist} - {title} (Original).wav"
        
        log_message(job_id, "INFO", "Starting video and CDG generation with corrected lyrics...")
        
        # Generate final outputs (video and CDG)
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
        
        log_message(job_id, "SUCCESS", f"Video and CDG generation completed")
        
        # Update status to complete with file information
        update_job_status_with_timeline(
            job_id, 
            "complete", 
            progress=100,
            video_path=str(parent_video_path),
            lrc_path=str(parent_lrc_path),
            video_url=f"/api/jobs/{job_id}/download",
            files_url=f"/api/jobs/{job_id}/files",
            download_all_url=f"/api/jobs/{job_id}/download-all",
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]}
        )
        
        log_message(job_id, "SUCCESS", f"Job {job_id} completed successfully!")
        
        # Clean up logging handler
        root_logger = logging.getLogger()
        root_logger.removeHandler(log_handler)
        
        return {"status": "success", "message": "Video generation completed", "video_path": str(parent_video_path)}
        
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
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]}
        )
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Phase 2 failed: {error_msg}")

@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=60,  # Short timeout since we're not running a persistent server
)
def prepare_review_data(job_id: str):
    """Prepare correction data for external review interface."""
    from pathlib import Path
    
    try:
        log_message(job_id, "INFO", f"Preparing review data for job {job_id}")
        
        # Check if job data exists
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise Exception(f"Job {job_id} not found")
        
        # Get the corrections file path from job data
        corrections_file_path = job_data.get("corrections_file")
        if not corrections_file_path:
            # Fallback to constructing the path
            track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
            corrections_file_path = str(Path(track_output_dir) / "lyrics" / f"{job_data.get('artist', 'Unknown')} - {job_data.get('title', 'Unknown')} (Lyrics Corrections).json")
        
        corrections_json_path = Path(corrections_file_path)
        if not corrections_json_path.exists():
            raise Exception(f"Corrections data not found at {corrections_json_path}")
        
        # Load the correction data
        with open(corrections_json_path, 'r') as f:
            corrections_data = json.load(f)
        
        log_message(job_id, "INFO", f"Review data prepared for job {job_id}")
        
        # Update job status to indicate review is active
        update_job_status_with_timeline(
            job_id, 
            "reviewing", 
            progress=77,
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]}
        )
        
        return {
            "status": "success", 
            "corrections_data": corrections_data,
            "job_id": job_id,
            "artist": job_data.get("artist"),
            "title": job_data.get("title")
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
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]}
        )
        
        raise

@app.function(
    image=karaoke_image,
    gpu="any",
    volumes=VOLUME_CONFIG,
    secrets=[modal.Secret.from_name("env-vars")],
    timeout=1800,
)
async def process_part_one_uploaded(job_id: str, audio_file_path: str, artist: str, title: str, styles_file_path: Optional[str] = None, styles_archive_path: Optional[str] = None):
    """First phase: Process uploaded audio file, separate, and transcribe lyrics."""
    import sys
    import traceback
    
    try:
        # Set up logging to capture all messages
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
        audio_hash = cache_manager.get_audio_hash(audio_file_path)
        log_message(job_id, "INFO", f"Audio hash: {audio_hash}")
        
        # Check if we have cached results for this exact audio
        cached_transcription = cache_manager.get_cached_transcription_result(audio_hash)
        if cached_transcription:
            log_message(job_id, "INFO", "Found cached transcription result, skipping processing")
            # You could return cached results here, but for now we'll continue processing
            # This is useful for development/testing scenarios
        
        # Update status
        update_job_status_with_timeline(
            job_id, 
            "processing", 
            progress=10,
            artist=artist,
            title=title,
            filename=Path(audio_file_path).name,
            audio_hash=audio_hash,  # Store audio hash for potential future use
            created_at=datetime.datetime.now().isoformat()
        )
        
        # Initialize processor - this now uses the same code path as the CLI
        processor = ServerlessKaraokeProcessor(model_dir="/models", output_dir="/output")
        
        # Process using the full KaraokePrep workflow (same as CLI)
        log_message(job_id, "INFO", "Starting full karaoke processing workflow...")
        if styles_file_path:
            log_message(job_id, "INFO", f"Using custom styles from: {styles_file_path}")
        result = await processor.process_uploaded_file(job_id, audio_file_path, artist, title, styles_file_path, styles_archive_path)
        
        # Cache the processing results for future use
        if result.get("track_data"):
            cache_manager.cache_transcription_result(audio_hash, {
                "artist": artist,
                "title": title,
                "track_data": result["track_data"],
                "track_output_dir": result["track_output_dir"],
                "status": result["status"]
            })
        
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
            audio_hash=audio_hash  # Keep the audio hash for potential future use
        )
        
        log_message(job_id, "SUCCESS", f"Processing completed for job {job_id}. Ready for review.")
        
        # Clean up logging handler
        root_logger = logging.getLogger()
        root_logger.removeHandler(log_handler)
        
        return {"status": "success", "message": "Processing completed, ready for review"}
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        log_message(job_id, "ERROR", f"Phase 1 failed: {error_msg}")
        log_message(job_id, "ERROR", f"Traceback: {error_traceback}")
        
        update_job_status_with_timeline(
            job_id, 
            "error", 
            progress=0,
            artist=artist,
            title=title,
            error=error_msg,
            traceback=error_traceback
        )
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Phase 1 failed: {error_msg}")

# Removed setup_lyrics_review function - now using full KaraokePrep workflow

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

# API Routes
@api_app.post("/api/submit")
async def submit_job(request: JobSubmissionRequest):
    """Submit a new karaoke generation job."""
    try:
        job_id = str(uuid.uuid4())[:8]
        
        # Initialize job status with timeline
        update_job_status_with_timeline(
            job_id, 
            "queued", 
            progress=0,
            url=request.url,
            created_at=datetime.datetime.now().isoformat()
        )
        
        # Initialize job logs
        job_logs_dict[job_id] = []
        
        # Spawn the background job
        process_part_one.spawn(job_id, request.url)
        
        return JSONResponse({
            "status": "success", 
            "job_id": job_id,
            "message": "Job submitted successfully"
        }, status_code=202)
        
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

@api_app.get("/api/jobs")
async def get_all_jobs():
    """Get status of all jobs."""
    try:
        jobs = dict(job_status_dict.items())
        return JSONResponse(jobs)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get status of a specific job with timeline information."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
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
                "started_at": job_data.get("created_at")
            }
        
        return JSONResponse({
            **job_data,
            "timeline_summary": timeline_summary
        })
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/jobs/{job_id}/timeline")
async def get_job_timeline(job_id: str):
    """Get detailed timeline data for a specific job."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        timeline = job_data.get("timeline", [])
        timeline_summary = get_job_timeline_summary(job_data)
        
        # Handle legacy jobs without timeline data
        if not timeline and not timeline_summary:
            # Create a synthetic timeline entry for legacy jobs
            current_time = datetime.datetime.now().isoformat()
            estimated_start = job_data.get("created_at", current_time)
            
            synthetic_timeline = [{
                "status": job_data.get("status", "unknown"),
                "started_at": estimated_start,
                "ended_at": None if job_data.get("status") not in ["complete", "error"] else current_time,
                "duration_seconds": None
            }]
            
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
                    "started_at": estimated_start
                }
            else:
                synthetic_summary = {
                    "phase_durations": {},
                    "total_duration_seconds": 0,
                    "total_duration_formatted": "Unknown",
                    "phases_completed": 0,
                    "current_phase": job_data.get("status", "unknown"),
                    "started_at": None
                }
            
            return JSONResponse({
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
                    "estimated_remaining": None
                },
                "legacy_job": True
            })
        
        # Calculate additional timeline metrics for jobs with real timeline data
        phase_transitions = []
        for i in range(len(timeline) - 1):
            current_phase = timeline[i]
            next_phase = timeline[i + 1]
            
            if current_phase.get("ended_at") and next_phase.get("started_at"):
                transition_time = (
                    datetime.datetime.fromisoformat(next_phase["started_at"]) - 
                    datetime.datetime.fromisoformat(current_phase["ended_at"])
                ).total_seconds()
                
                phase_transitions.append({
                    "from_status": current_phase["status"],
                    "to_status": next_phase["status"],
                    "transition_duration_seconds": transition_time
                })
        
        return JSONResponse({
            "job_id": job_id,
            "artist": job_data.get("artist", "Unknown"),
            "title": job_data.get("title", "Unknown"),
            "current_status": job_data.get("status"),
            "timeline": timeline,
            "timeline_summary": timeline_summary,
            "phase_transitions": phase_transitions,
            "performance_metrics": {
                "average_phase_duration": timeline_summary.get("total_duration_seconds", 0) / max(1, timeline_summary.get("phases_completed", 1)),
                "total_processing_time": timeline_summary.get("total_duration_formatted", "0s"),
                "phases_completed": timeline_summary.get("phases_completed", 0),
                "estimated_remaining": _estimate_remaining_time(timeline, job_data.get("status"))
            },
            "legacy_job": False
        })
        
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
async def delete_job(job_id: str):
    """Delete a specific job."""
    try:
        if job_id not in job_status_dict:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Remove from status and logs
        del job_status_dict[job_id]
        if job_id in job_logs_dict:
            del job_logs_dict[job_id]
        
        return JSONResponse({"status": "success", "message": f"Job {job_id} deleted"})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    """Retry a failed job."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job_data.get("status") != "error":
            raise HTTPException(status_code=400, detail="Job is not in error state")
        
        # Reset job status with new timeline
        update_job_status_with_timeline(
            job_id, 
            "queued", 
            progress=0,
            url=job_data.get("url", ""),
            created_at=datetime.datetime.now().isoformat()
        )
        
        # Clear error logs and add retry log
        job_logs_dict[job_id] = [{
            "timestamp": datetime.datetime.now().isoformat(),
            "level": "INFO",
            "message": "Job retry initiated"
        }]
        
        # Respawn the job
        process_part_one.spawn(job_id, job_data.get("url", ""))
        
        return JSONResponse({"status": "success", "message": f"Job {job_id} retry initiated"})
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/logs")
async def get_all_logs():
    """Get logs for all jobs."""
    try:
        logs = dict(job_logs_dict.items())
        return JSONResponse(logs)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/logs/{job_id}")
async def get_job_logs(job_id: str):
    """Get logs for a specific job."""
    try:
        logs = job_logs_dict.get(job_id, [])
        return JSONResponse(logs)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/stats")
async def get_stats():
    """Get statistics about all jobs."""
    try:
        jobs = dict(job_status_dict.items())
        
        stats = {
            "total": len(jobs),
            "processing": len([j for j in jobs.values() if j.get("status") in ["queued", "processing_audio", "transcribing", "rendering"]]),
            "awaiting_review": len([j for j in jobs.values() if j.get("status") == "awaiting_review"]),
            "complete": len([j for j in jobs.values() if j.get("status") == "complete"]),
            "error": len([j for j in jobs.values() if j.get("status") == "error"])
        }
        
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
            "vocals_audio": None
        }
        
        # Find LRC file
        lrc_files = list(track_output_dir.glob("**/*.lrc"))
        if lrc_files:
            review_data["lrc_file"] = str(lrc_files[0])
            
        # Find corrected lyrics text file  
        corrected_files = list(track_output_dir.glob("**/*Corrected*.txt"))
        if corrected_files:
            with open(corrected_files[0], 'r') as f:
                review_data["corrected_lyrics"] = f.read()
                
        # Find original/uncorrected lyrics
        original_files = list(track_output_dir.glob("**/*Uncorrected*.txt"))
        if original_files:
            with open(original_files[0], 'r') as f:
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
        
        return JSONResponse({
            "status": "success",
            "message": "Review data prepared",
            "review_url": review_url
        })
        
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
async def download_video(job_id: str):
    """Download the primary completed video."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job_data.get("status") != "complete":
            raise HTTPException(status_code=400, detail="Job is not complete")
        
        # First try the stored video path
        video_path = job_data.get("video_path")
        if video_path and Path(video_path).exists():
            return FileResponse(
                path=video_path,
                filename=f"karaoke-{job_id}.mkv",
                media_type="video/x-matroska"
            )
        
        # Fallback: look for any final video file
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        track_dir = Path(track_output_dir)
        
        # Look for final videos in order of preference
        video_patterns = [
            "*With Vocals*.mkv",
            "*With Vocals*.mp4", 
            "*Final Karaoke*.mp4",
            "*Final Karaoke*.mkv"
        ]
        
        for pattern in video_patterns:
            video_files = list(track_dir.rglob(pattern))
            if video_files:
                video_file = video_files[0]  # Take the first match
                return FileResponse(
                    path=str(video_file),
                    filename=f"karaoke-{job_id}-{video_file.stem}.{video_file.suffix[1:]}",
                    media_type=get_mime_type(video_file.suffix)
                )
        
        raise HTTPException(status_code=404, detail="Video file not found")
        
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
        
        # Reload volume to see files from other containers
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
        vocals_patterns = [
            f"{artist} - {title} (Original).wav"  # Fallback to original audio
        ]
        
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
        if file_extension in ['.flac']:
            media_type = "audio/flac"
        elif file_extension in ['.wav']:
            media_type = "audio/wav"
        elif file_extension in ['.mp3']:
            media_type = "audio/mpeg"
        else:
            media_type = "audio/flac"  # Default
        
        return FileResponse(
            path=str(vocals_file),
            filename=f"vocals-{job_id}{file_extension}",
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error serving audio file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving audio file: {str(e)}")

@api_app.post("/api/corrections/{job_id}/preview-video")
async def generate_preview_video(job_id: str, request: Request):
    """Generate a preview video with corrected lyrics."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job_data.get("status") not in ["reviewing", "awaiting_review"]:
            raise HTTPException(status_code=400, detail="Job is not in review state")
        
        # Get the corrected data from the request
        corrected_data = await request.json()
        
        log_message(job_id, "DEBUG", f"Generating preview video with corrected data")
        
        # Call the Modal function to generate preview video
        result = generate_preview_video_modal.remote(job_id, corrected_data)
        
        return JSONResponse({
            "status": "success",
            "message": "Preview video generated successfully",
            "preview_hash": result["preview_hash"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error generating preview video: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating preview video: {str(e)}")

@api_app.get("/api/corrections/{job_id}/audio/{audio_hash}")
async def get_audio_by_hash(job_id: str, audio_hash: str):
    """Get audio file by hash (compatible with ReviewServer API)."""
    try:
        from pathlib import Path
        import hashlib
        
        # Reload volume to see files from other containers
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
        vocals_patterns = [
            f"*Vocals*.flac",
            f"*Vocals*.FLAC", 
            f"*vocals*.flac",
            f"*vocals*.wav",
            f"{artist} - {title} (Original).wav"  # Fallback to original audio
        ]
        
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
        with open(vocals_file, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        
        if audio_hash != file_hash:
            log_message(job_id, "WARNING", f"Audio hash mismatch: expected {audio_hash}, got {file_hash}")
            # Still serve the file but log the warning
        
        log_message(job_id, "DEBUG", f"Serving vocals file: {vocals_file}")
        
        # Determine media type based on file extension
        file_extension = vocals_file.suffix.lower()
        if file_extension in ['.flac']:
            media_type = "audio/flac"
        elif file_extension in ['.wav']:
            media_type = "audio/wav"
        elif file_extension in ['.mp3']:
            media_type = "audio/mpeg"
        else:
            media_type = "audio/flac"  # Default
        
        return FileResponse(
            path=str(vocals_file),
            filename=f"vocals-{job_id}{file_extension}",
            media_type=media_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error serving audio file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error serving audio file: {str(e)}")

@api_app.get("/api/corrections/{job_id}/preview-video/{preview_hash}")
async def get_preview_video(job_id: str, preview_hash: str):
    """Get generated preview video by hash."""
    try:
        from pathlib import Path
        
        # Reload volume to see files from other containers
        output_volume.reload()
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Look for the preview video file
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        preview_dir = Path(track_output_dir) / "previews"
        
        if not preview_dir.exists():
            raise HTTPException(status_code=404, detail="Preview directory not found")
        
        # Find preview video file with matching hash
        preview_files = list(preview_dir.glob(f"preview_{preview_hash}*"))
        video_file = None
        
        for file in preview_files:
            if file.suffix in ['.mp4', '.mkv', '.avi']:
                video_file = file
                break
        
        if not video_file or not video_file.exists():
            raise HTTPException(status_code=404, detail="Preview video not found")
        
        log_message(job_id, "DEBUG", f"Serving preview video: {video_file}")
        
        return FileResponse(
            path=str(video_file),
            filename=f"preview_{preview_hash}.mp4",
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error serving preview video: {str(e)}")
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
        
        return JSONResponse({
            "status": "success",
            "message": f"Successfully updated correction handlers: {enabled_handlers}",
            "data": result["data"]
        })
        
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
        
        return JSONResponse({
            "status": "success",
            "message": f"Successfully added lyrics source '{source}' and updated corrections",
            "data": result["data"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error adding lyrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding lyrics: {str(e)}")

# Admin Routes
@api_app.post("/api/admin/clear-errors")
async def clear_error_jobs():
    """Clear all jobs with error status."""
    try:
        jobs_to_delete = []
        for job_id, job_data in job_status_dict.items():
            if job_data.get("status") == "error":
                jobs_to_delete.append(job_id)
        
        for job_id in jobs_to_delete:
            del job_status_dict[job_id]
            if job_id in job_logs_dict:
                del job_logs_dict[job_id]
        
        return JSONResponse({
            "status": "success", 
            "message": f"Cleared {len(jobs_to_delete)} error jobs"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/admin/cache/stats")
async def get_cache_stats():
    """Get cache statistics and usage information."""
    try:
        cache_manager = CacheManager("/cache")
        
        stats = {
            "cache_directories": {},
            "total_files": 0,
            "total_size_bytes": 0
        }
        
        # Check each cache directory
        for cache_type, cache_dir in {
            "audio_hashes": cache_manager.audio_hashes_dir,
            "audioshake_responses": cache_manager.audioshake_dir,
            "models": cache_manager.models_dir,
            "transcriptions": cache_manager.transcription_dir
        }.items():
            
            if cache_dir.exists():
                files = list(cache_dir.glob("*"))
                total_size = sum(f.stat().st_size for f in files if f.is_file())
                
                stats["cache_directories"][cache_type] = {
                    "file_count": len(files),
                    "size_bytes": total_size,
                    "size_mb": round(total_size / 1024 / 1024, 2)
                }
                
                stats["total_files"] += len(files)
                stats["total_size_bytes"] += total_size
        
        stats["total_size_mb"] = round(stats["total_size_bytes"] / 1024 / 1024, 2)
        stats["total_size_gb"] = round(stats["total_size_bytes"] / 1024 / 1024 / 1024, 2)
        
        return JSONResponse(stats)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.post("/api/admin/cache/clear")
async def clear_cache():
    """Clear old cache files."""
    try:
        cache_manager = CacheManager("/cache")
        
        # Clear cache files older than 90 days
        cache_manager.clear_old_cache(max_age_days=90)
        
        return JSONResponse({
            "status": "success",
            "message": "Old cache files cleared"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/admin/cache/audioshake")
async def get_audioshake_cache():
    """Get list of cached AudioShake responses."""
    try:
        cache_manager = CacheManager("/cache")
        
        cached_responses = []
        for cache_file in cache_manager.audioshake_dir.glob("*.json"):
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                cached_responses.append({
                    "audio_hash": cached_data.get("audio_hash", "unknown"),
                    "timestamp": cached_data.get("timestamp", "unknown"),
                    "file_size_bytes": cache_file.stat().st_size
                })
            except Exception:
                # Skip invalid cache files
                continue
        
        return JSONResponse({
            "status": "success",
            "cached_responses": cached_responses,
            "total_count": len(cached_responses)
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.delete("/api/admin/cache/audioshake/{audio_hash}")
async def delete_audioshake_cache(audio_hash: str):
    """Delete specific AudioShake cache entry."""
    try:
        cache_manager = CacheManager("/cache")
        cache_file = cache_manager.audioshake_dir / f"{audio_hash}.json"
        
        if cache_file.exists():
            cache_file.unlink()
            return JSONResponse({
                "status": "success",
                "message": f"Deleted AudioShake cache for hash {audio_hash}"
            })
        else:
            return JSONResponse({
                "status": "not_found",
                "message": f"No cache found for hash {audio_hash}"
            }, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/admin/export-logs")
async def export_logs():
    """Export all logs as JSON file."""
    try:
        logs_data = {
            "exported_at": datetime.datetime.now().isoformat(),
            "jobs": dict(job_status_dict.items()),
            "logs": dict(job_logs_dict.items())
        }
        
        import tempfile
        import os
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(logs_data, f, indent=2)
            temp_path = f.name
        
        return FileResponse(
            path=temp_path,
            filename=f"karaoke-logs-{datetime.datetime.now().strftime('%Y%m%d')}.json",
            media_type="application/json"
        )
        
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.post("/api/admin/cache/warm")
async def warm_cache_endpoint():
    """Trigger cache warming for commonly used models and data."""
    try:
        # Spawn the cache warming function
        result = warm_cache.remote()
        
        return JSONResponse({
            "status": "success",
            "message": "Cache warming initiated"
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

# Health check
@api_app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "1.0.0"
    })

# Debug endpoint for AudioShake API
@api_app.get("/api/debug/audioshake")
async def debug_audioshake():
    """Debug AudioShake API connectivity and credentials."""
    try:
        import os
        import requests
        
        audioshake_token = os.environ.get("AUDIOSHAKE_API_TOKEN")
        if not audioshake_token:
            return JSONResponse({
                "status": "error",
                "message": "AUDIOSHAKE_API_TOKEN environment variable not set"
            }, status_code=500)
        
        # Test API endpoints
        headers = {"Authorization": f"Bearer {audioshake_token}"}
        
        # Test 1: Upload endpoint (GET to see if it responds - normally POST)
        try:
            upload_response = requests.get(
                "https://groovy.audioshake.ai/upload/",
                headers=headers,
                timeout=10
            )
            upload_status = upload_response.status_code
            upload_text = upload_response.text[:200]  # First 200 chars
        except Exception as e:
            upload_status = "error"
            upload_text = str(e)
        
        # Test 2: Job endpoint (GET to see if it responds - normally POST)
        try:
            job_response = requests.get(
                "https://groovy.audioshake.ai/job/",
                headers=headers,
                timeout=10
            )
            job_status = job_response.status_code
            job_text = job_response.text[:200]
        except Exception as e:
            job_status = "error"
            job_text = str(e)
        
        # Test 3: Test getting a non-existent job (to see API response format)
        try:
            test_job_response = requests.get(
                "https://groovy.audioshake.ai/job/test-job-id",
                headers=headers,
                timeout=10
            )
            test_job_status = test_job_response.status_code
            test_job_text = test_job_response.text[:200]
        except Exception as e:
            test_job_status = "error"
            test_job_text = str(e)
        
        return JSONResponse({
            "status": "success",
            "audioshake_api_tests": {
                "token_present": bool(audioshake_token),
                "token_prefix": audioshake_token[:10] + "..." if audioshake_token else None,
                "upload_endpoint": {
                    "status": upload_status,
                    "response_preview": upload_text
                },
                "job_endpoint": {
                    "status": job_status,
                    "response_preview": job_text
                },
                "test_job_endpoint": {
                    "status": test_job_status,
                    "response_preview": test_job_text
                }
            },
            "timestamp": datetime.datetime.now().isoformat()
        })
        
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": str(e)
        }, status_code=500)

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
        with open(corrections_json_path, 'r') as f:
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
            f"{artist} - {title} (Original).wav"  # Fallback to original audio
        ]
        
        audio_hash = None
        for pattern in vocals_patterns:
            vocals_files = list(track_dir.glob(f"**/{pattern}"))
            if vocals_files:
                vocals_file = vocals_files[0]
                try:
                    with open(vocals_file, 'rb') as f:
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
    """Complete the review process with corrected lyrics data."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job_data.get("status") != "reviewing":
            raise HTTPException(status_code=400, detail="Job is not in reviewing state")
        
        # Get the corrected data from the request
        corrected_data = await request.json()
        
        log_message(job_id, "INFO", "Review completed, starting Phase 2 video generation")
        
        # Update job status to rendering
        update_job_status_with_timeline(
            job_id, 
            "rendering", 
            progress=80,
            **{k: v for k, v in job_data.items() if k not in ["status", "progress", "timeline", "last_updated"]}
        )
        
        # Spawn Phase 2 to generate the final video with corrected lyrics
        process_part_two.spawn(job_id, corrected_data)
        
        return JSONResponse({
            "status": "success",
            "message": "Review completed successfully, starting video generation"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        log_message(job_id, "ERROR", f"Error completing review: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

# Note: Additional review endpoints (preview video, audio, handlers) can be added here if needed
# For now, we're using a simpler approach where the review interface handles everything client-side

@api_app.post("/api/submit-file")
async def submit_file(
    audio_file: UploadFile = File(...),
    artist: str = Form(...),
    title: str = Form(...),
    styles_file: Optional[UploadFile] = File(None),
    styles_archive: Optional[UploadFile] = File(None)
):
    """Handle file upload and start processing."""
    try:
        # Generate unique job ID
        job_id = str(random.randint(10000000, 99999999))
        
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
        
        # Initialize job status with timeline
        update_job_status_with_timeline(
            job_id, 
            "queued", 
            progress=0,
            artist=artist,
            title=title,
            created_at=datetime.datetime.now().isoformat()
        )
        
        # Initialize job logs
        job_logs_dict[job_id] = []
        
        # Start processing job
        job = process_part_one_uploaded.spawn(
            job_id, 
            str(audio_file_path), 
            artist, 
            title, 
            str(styles_file_path) if styles_file_path else None,
            str(styles_archive_path) if styles_archive_path else None
        )
        
        return {"job_id": job_id, "message": "Job started successfully"}
        
    except Exception as e:
        print(f"Error in submit_file: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to submit job: {str(e)}"}
        )

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
)
def add_lyrics_source(job_id: str, source: str, lyrics_text: str):
    """Add new lyrics source and rerun correction."""
    import json
    from pathlib import Path
    from lyrics_transcriber.types import CorrectionResult
    from lyrics_transcriber.correction.operations import CorrectionOperations
    
    try:
        # Set up logging
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
        
        with open(corrections_json_path, 'r') as f:
            corrections_data = json.load(f)
        
        correction_result = CorrectionResult.from_dict(corrections_data)
        
        # Use shared operation for adding lyrics source
        updated_result = CorrectionOperations.add_lyrics_source(
            correction_result=correction_result,
            source=source,
            lyrics_text=lyrics_text,
            cache_dir="/cache",
            logger=logging.getLogger(__name__)
        )
        
        # Save updated correction data
        with open(corrections_json_path, 'w') as f:
            json.dump(updated_result.to_dict(), f, indent=2)
        
        log_message(job_id, "SUCCESS", f"Successfully added lyrics source '{source}' and updated corrections")
        
        # Clean up logging handler
        root_logger = logging.getLogger()
        root_logger.removeHandler(log_handler)
        
        return {"status": "success", "data": updated_result.to_dict()}
        
    except ValueError as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Failed to add lyrics source: {error_msg}")
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Failed to add lyrics source: {error_msg}")
    except Exception as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Failed to add lyrics source: {error_msg}")
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Failed to add lyrics source: {error_msg}")

@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minutes for correction processing
)
def update_correction_handlers(job_id: str, enabled_handlers: List[str]):
    """Update enabled correction handlers and rerun correction."""
    import json
    from pathlib import Path
    from lyrics_transcriber.types import CorrectionResult
    from lyrics_transcriber.correction.operations import CorrectionOperations
    
    try:
        # Set up logging
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
        
        with open(corrections_json_path, 'r') as f:
            corrections_data = json.load(f)
        
        correction_result = CorrectionResult.from_dict(corrections_data)
        
        # Use shared operation for updating handlers
        updated_result = CorrectionOperations.update_correction_handlers(
            correction_result=correction_result,
            enabled_handlers=enabled_handlers,
            cache_dir="/cache",
            logger=logging.getLogger(__name__)
        )
        
        # Save updated correction data
        with open(corrections_json_path, 'w') as f:
            json.dump(updated_result.to_dict(), f, indent=2)
        
        log_message(job_id, "SUCCESS", f"Successfully updated handlers: {enabled_handlers}")
        
        # Clean up logging handler
        root_logger = logging.getLogger()
        root_logger.removeHandler(log_handler)
        
        return {"status": "success", "data": updated_result.to_dict()}
        
    except Exception as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Failed to update handlers: {error_msg}")
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Failed to update handlers: {error_msg}")

@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
    timeout=300,  # 5 minutes for preview video generation
)
def generate_preview_video_modal(job_id: str, updated_data: Dict[str, Any]):
    """Generate a preview video with current corrections."""
    import json
    from pathlib import Path
    from lyrics_transcriber.types import CorrectionResult
    from lyrics_transcriber.core.config import OutputConfig
    from lyrics_transcriber.correction.operations import CorrectionOperations
    
    try:
        # Set up logging
        log_handler = setup_job_logging(job_id)
        
        # Reload volume to see files from other containers
        output_volume.reload()
        
        log_message(job_id, "INFO", "Generating preview video with corrected data")
        
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
        
        with open(corrections_json_path, 'r') as f:
            corrections_data = json.load(f)
        
        base_correction_result = CorrectionResult.from_dict(corrections_data)
        
        # Find audio file
        track_output_dir = job_data.get("track_output_dir", f"/output/{job_id}")
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")
        track_dir = Path(track_output_dir)
        audio_file = track_dir / f"{artist} - {title} (Original).wav"
        
        if not audio_file.exists():
            # Try to find any audio file
            audio_patterns = ["*.wav", "*.flac", "*.mp3"]
            for pattern in audio_patterns:
                audio_files = list(track_dir.glob(pattern))
                if audio_files:
                    audio_file = audio_files[0]
                    break
        
        if not audio_file.exists():
            raise Exception("Audio file not found for preview")
        
        # Set up preview config
        styles_file = job_data.get("styles_file_path") or str(Path(track_output_dir) / "styles_updated.json")
        log_message(job_id, "DEBUG", f"Using styles file for preview: {styles_file}")
        
        # Verify the styles file exists
        if not Path(styles_file).exists():
            log_message(job_id, "ERROR", f"Styles file does not exist: {styles_file}")
            # Try to find any styles file in the directory
            possible_styles = list(Path(track_output_dir).glob("**/styles*.json"))
            if possible_styles:
                log_message(job_id, "INFO", f"Found alternative styles files: {[str(f) for f in possible_styles]}")
                styles_file = str(possible_styles[0])
                log_message(job_id, "INFO", f"Using alternative styles file: {styles_file}")
            else:
                log_message(job_id, "WARNING", "No styles files found, using default styles")
        else:
            log_message(job_id, "DEBUG", f"Styles file exists and is accessible: {styles_file}")
        
        preview_config = OutputConfig(
            output_dir=str(Path(track_output_dir) / "previews"),
            cache_dir="/cache",
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
        
        # Use shared operation for preview generation
        result = CorrectionOperations.generate_preview_video(
            correction_result=base_correction_result,
            updated_data=updated_data,
            output_config=preview_config,
            audio_filepath=str(audio_file),
            artist=artist,
            title=title,
            logger=logging.getLogger(__name__)
        )
        
        log_message(job_id, "SUCCESS", f"Generated preview video: {result['video_path']}")
        
        # Clean up logging handler
        root_logger = logging.getLogger()
        root_logger.removeHandler(log_handler)
        
        return result
        
    except Exception as e:
        error_msg = str(e)
        log_message(job_id, "ERROR", f"Failed to generate preview video: {error_msg}")
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Failed to generate preview video: {error_msg}")

@api_app.get("/api/jobs/{job_id}/files")
async def list_job_files(job_id: str):
    """List all available files for a job."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
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
                "description": "Completed karaoke videos ready for use"
            },
            "karaoke_files": {
                "name": "Karaoke Files", 
                "patterns": ["*Final Karaoke*.zip", "*.cdg", "*.lrc"],
                "description": "CDG+MP3 and TXT+MP3 files for karaoke machines"
            },
            "working_videos": {
                "name": "Working Videos",
                "patterns": ["*With Vocals*.mp4", "*With Vocals*.mkv", "*Karaoke*.mp4"],
                "description": "Intermediate video files from processing"
            },
            "audio_files": {
                "name": "Audio Files",
                "patterns": ["*Instrumental*.flac", "*Vocals*.flac", "*.wav", "*.mp3"],
                "description": "Separated audio stems and instrumentals"
            },
            "image_files": {
                "name": "Image Files", 
                "patterns": ["*.jpg", "*.png"],
                "description": "Title screens and thumbnails"
            },
            "text_files": {
                "name": "Text & Data Files",
                "patterns": ["*.txt", "*.json", "*.ass"],
                "description": "Lyrics, corrections, and subtitle files"
            }
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
                                "mime_type": get_mime_type(file_path.suffix)
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
                    "count": len(category_files)
                }
        
        artist = job_data.get("artist", "Unknown")
        title = job_data.get("title", "Unknown")
        
        return JSONResponse({
            "job_id": job_id,
            "artist": artist,
            "title": title,
            "status": job_data.get("status"),
            "total_files": len(files),
            "total_size": total_size,
            "total_size_mb": round(total_size / 1024 / 1024, 2),
            "categories": categorized_files,
            "all_files": files  # Flat list for convenience
        })
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

def get_mime_type(file_extension: str) -> str:
    """Get MIME type for file extension."""
    mime_types = {
        '.mp4': 'video/mp4',
        '.mkv': 'video/x-matroska', 
        '.mov': 'video/quicktime',
        '.avi': 'video/x-msvideo',
        '.flac': 'audio/flac',
        '.wav': 'audio/wav',
        '.mp3': 'audio/mpeg',
        '.lrc': 'text/plain',
        '.txt': 'text/plain',
        '.json': 'application/json',
        '.ass': 'text/plain',
        '.cdg': 'application/octet-stream',
        '.zip': 'application/zip',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png'
    }
    return mime_types.get(file_extension.lower(), 'application/octet-stream')

@api_app.get("/api/jobs/{job_id}/files/{file_path:path}")
async def download_job_file(job_id: str, file_path: str):
    """Download a specific file from a job."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
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
        if mime_type.startswith('video/'):
            headers.update({
                "Accept-Ranges": "bytes",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff"
            })
        
        return FileResponse(
            path=str(requested_file),
            filename=requested_file.name,
            media_type=mime_type,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.post("/api/jobs/{job_id}/create-zip")
async def create_job_zip(job_id: str, request: Request):
    """Create a ZIP file containing selected job files."""
    try:
        # Reload volume to see files from other containers
        output_volume.reload()
        
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
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
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
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
        
        return JSONResponse({
            "zip_path": zip_path.name,  # Just filename for download endpoint
            "files_count": files_added,
            "size": zip_stat.st_size,
            "size_mb": round(zip_stat.st_size / 1024 / 1024, 2),
            "download_url": f"/api/jobs/{job_id}/files/{zip_path.name}"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/jobs/{job_id}/download-all")
async def download_all_files(job_id: str):
    """Create and download a ZIP of all job files."""
    try:
        # Create zip with all files
        create_response = await create_job_zip(job_id, type('obj', (object,), {
            'json': lambda: {"files": [], "name": f"karaoke-{job_id}-complete.zip"}
        })())
        
        if isinstance(create_response, JSONResponse):
            response_data = json.loads(create_response.body.decode())
            if "zip_path" in response_data:
                # Download the created zip
                return await download_job_file(job_id, response_data["zip_path"])
        
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
    timeline.append({
        "status": new_status,
        "started_at": current_time,
        "ended_at": None,
        "duration_seconds": None
    })
    
    # Update job data
    updated_job_data = {
        **job_data,
        **additional_data,
        "status": new_status,
        "timeline": timeline,
        "last_updated": current_time
    }
    
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
        "started_at": timeline[0]["started_at"] if timeline else None
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



 