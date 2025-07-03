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

# Define serverless dictionaries to hold job states and logs
job_status_dict = modal.Dict.from_name("karaoke-job-statuses", create_if_missing=True)
job_logs_dict = modal.Dict.from_name("karaoke-job-logs", create_if_missing=True)

# Mount volumes to specific paths inside the container
VOLUME_CONFIG = {
    "/models": model_volume,
    "/output": output_volume
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
        job_status_dict[job_id] = {
            "status": "processing", 
            "progress": 10,
            "url": youtube_url,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        # Initialize processor - this now uses the same code path as the CLI
        processor = ServerlessKaraokeProcessor(model_dir="/models", output_dir="/output")
        
        # Process using the full KaraokePrep workflow (same as CLI)
        log_message(job_id, "INFO", "Starting full karaoke processing workflow...")
        result = await processor.process_url(job_id, youtube_url)
        
        # Update status to awaiting review
        job_status_dict[job_id] = {
            "status": "awaiting_review", 
            "progress": 75,
            "url": youtube_url,
            "track_data": result["track_data"],
            "track_output_dir": result["track_output_dir"]
        }
        
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
        
        job_status_dict[job_id] = {
            "status": "error", 
            "progress": 0,
            "url": youtube_url,
            "error": error_msg,
            "traceback": error_traceback
        }
        
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
def process_part_two(job_id: str):
    """Second phase: Generate final video with corrected lyrics."""
    import sys
    import traceback
    
    try:
        # Set up logging to capture all messages
        log_handler = setup_job_logging(job_id)
        
        from core import CoreKaraokeProcessor
        
        log_message(job_id, "INFO", f"Starting phase 2 for job {job_id}")
        
        # Update status
        job_status_dict[job_id] = {"status": "rendering", "progress": 80}
        
        # Initialize processor
        processor = CoreKaraokeProcessor()
        
        # Load corrected lyrics
        output_dir = Path(f"/output/{job_id}")
        corrected_lyrics_path = output_dir / "lyrics_corrected.json"
        
        if not corrected_lyrics_path.exists():
            raise Exception("Corrected lyrics file not found")
        
        with open(corrected_lyrics_path, 'r') as f:
            corrected_lyrics = json.load(f)
        
        log_message(job_id, "INFO", "Corrected lyrics loaded")
        
        # Generate video assets
        log_message(job_id, "INFO", "Starting video generation...")
        
        instrumental_path = output_dir / "instrumental.wav"
        video_path = processor.generate_video_assets(corrected_lyrics, str(instrumental_path))
        
        log_message(job_id, "INFO", f"Video generated: {video_path}")
        
        # Update status to complete
        job_status_dict[job_id] = {
            "status": "complete", 
            "progress": 100,
            "video_path": video_path,
            "video_url": f"/api/jobs/{job_id}/download"
        }
        
        log_message(job_id, "SUCCESS", f"Job {job_id} completed successfully!")
        
        # Clean up logging handler
        root_logger = logging.getLogger()
        root_logger.removeHandler(log_handler)
        
        return {"status": "success", "message": "Video generation completed", "video_path": video_path}
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        log_message(job_id, "ERROR", f"Phase 2 failed: {error_msg}")
        log_message(job_id, "ERROR", f"Traceback: {error_traceback}")
        
        job_status_dict[job_id] = {
            "status": "error", 
            "progress": 0,
            "error": error_msg,
            "traceback": error_traceback
        }
        
        # Clean up logging handler
        try:
            root_logger = logging.getLogger()
            root_logger.removeHandler(log_handler)
        except:
            pass
        
        raise Exception(f"Phase 2 failed: {error_msg}")

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
        
        from core import ServerlessKaraokeProcessor
        
        log_message(job_id, "INFO", f"Starting job {job_id} for uploaded file: {audio_file_path}")
        log_message(job_id, "INFO", f"Artist: {artist}, Title: {title}")
        
        # CRITICAL: Reload the volume to see files written by other containers
        output_volume.reload()
        log_message(job_id, "DEBUG", "Volume reloaded to fetch latest changes")
        
        # Verify the uploaded file exists before processing
        audio_path = Path(audio_file_path)
        if not audio_path.exists():
            raise Exception(f"Uploaded file not found: {audio_file_path}")
        
        file_size = audio_path.stat().st_size
        if file_size == 0:
            raise Exception(f"Uploaded file is empty: {audio_file_path}")
        
        log_message(job_id, "INFO", f"File verified: {audio_path.name} ({file_size} bytes)")
        
        # Update status
        job_status_dict[job_id] = {
            "status": "processing", 
            "progress": 10,
            "artist": artist,
            "title": title,
            "filename": Path(audio_file_path).name,
            "created_at": datetime.datetime.now().isoformat()
        }
        
        # Initialize processor - this now uses the same code path as the CLI
        processor = ServerlessKaraokeProcessor(model_dir="/models", output_dir="/output")
        
        # Process using the full KaraokePrep workflow (same as CLI)
        log_message(job_id, "INFO", "Starting full karaoke processing workflow...")
        if styles_file_path:
            log_message(job_id, "INFO", f"Using custom styles from: {styles_file_path}")
        result = await processor.process_uploaded_file(job_id, audio_file_path, artist, title, styles_file_path, styles_archive_path)
        
        # Update status to awaiting review
        job_status_dict[job_id] = {
            "status": "awaiting_review", 
            "progress": 75,
            "artist": artist,
            "title": title,
            "track_data": result["track_data"],
            "track_output_dir": result["track_output_dir"]
        }
        
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
        
        job_status_dict[job_id] = {
            "status": "error", 
            "progress": 0,
            "artist": artist,
            "title": title,
            "error": error_msg,
            "traceback": error_traceback
        }
        
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
        
        # Initialize job status
        job_status_dict[job_id] = {
            "status": "queued", 
            "progress": 0,
            "url": request.url,
            "created_at": datetime.datetime.now().isoformat()
        }
        
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
    """Get status of a specific job."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        return JSONResponse(job_data)
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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
        
        # Reset job status
        job_status_dict[job_id] = {
            "status": "queued",
            "progress": 0,
            "url": job_data.get("url", ""),
            "created_at": datetime.datetime.now().isoformat()
        }
        
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

@api_app.post("/api/review/{job_id}")
async def submit_lyrics_review(job_id: str, lyrics: str = Form(...)):
    """Submit reviewed lyrics and continue to video generation."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Save corrected lyrics
        output_dir = Path(f"/output/{job_id}")
        corrected_lyrics_path = output_dir / "lyrics_corrected.json"
        
        # Parse the lyrics JSON
        try:
            lyrics_data = json.loads(lyrics)
        except json.JSONDecodeError:
            # If not valid JSON, treat as plain text
            lyrics_data = {"text": lyrics}
        
        with open(corrected_lyrics_path, 'w') as f:
            json.dump(lyrics_data, f, indent=2)
        
        # Update job status
        job_status_dict[job_id] = {
            **job_data,
            "status": "rendering",
            "progress": 80
        }
        
        # Add log entry
        log_message(job_id, "INFO", "Lyrics approved, starting video generation")
        
        # Spawn phase 2
        process_part_two.spawn(job_id)
        
        return JSONResponse({
            "status": "success", 
            "message": "Lyrics approved, video generation started"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@api_app.get("/api/jobs/{job_id}/download")
async def download_video(job_id: str):
    """Download the completed video."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job_data.get("status") != "complete":
            raise HTTPException(status_code=400, detail="Job is not complete")
        
        video_path = job_data.get("video_path")
        if not video_path or not Path(video_path).exists():
            raise HTTPException(status_code=404, detail="Video file not found")
        
        return FileResponse(
            path=video_path,
            filename=f"karaoke-{job_id}.mp4",
            media_type="video/mp4"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

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

# Lyrics Review Proxy Endpoints
@api_app.get("/api/corrections/{job_id}/correction-data")
async def proxy_correction_data(job_id: str):
    """Proxy correction data request to local LyricsTranscriber server."""
    try:
        import requests
        
        # Check if review server is running for this job
        review_port = get_review_server_port(job_id)
        if not review_port:
            raise HTTPException(status_code=404, detail="Review server not found for this job")
        
        # Forward request to local server
        response = requests.get(f"http://localhost:{review_port}/api/correction-data", timeout=30)
        response.raise_for_status()
        
        return JSONResponse(response.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying correction data: {str(e)}")

@api_app.post("/api/corrections/{job_id}/complete")
async def proxy_complete_review(job_id: str, request: Request):
    """Proxy review completion to local LyricsTranscriber server."""
    try:
        import requests
        
        # Check if review server is running for this job
        review_port = get_review_server_port(job_id)
        if not review_port:
            raise HTTPException(status_code=404, detail="Review server not found for this job")
        
        # Get the request body
        body = await request.body()
        
        # Forward request to local server
        response = requests.post(
            f"http://localhost:{review_port}/api/complete",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        response.raise_for_status()
        
        return JSONResponse(response.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying review completion: {str(e)}")

@api_app.post("/api/corrections/{job_id}/preview-video")
async def proxy_preview_video(job_id: str, request: Request):
    """Proxy preview video generation to local LyricsTranscriber server."""
    try:
        import requests
        
        # Check if review server is running for this job
        review_port = get_review_server_port(job_id)
        if not review_port:
            raise HTTPException(status_code=404, detail="Review server not found for this job")
        
        # Get the request body
        body = await request.body()
        
        # Forward request to local server
        response = requests.post(
            f"http://localhost:{review_port}/api/preview-video",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=120  # Longer timeout for video generation
        )
        response.raise_for_status()
        
        return JSONResponse(response.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying preview video: {str(e)}")

@api_app.get("/api/corrections/{job_id}/preview-video/{preview_hash}")
async def proxy_get_preview_video(job_id: str, preview_hash: str):
    """Proxy preview video download to local LyricsTranscriber server."""
    try:
        import requests
        from fastapi.responses import StreamingResponse
        
        # Check if review server is running for this job
        review_port = get_review_server_port(job_id)
        if not review_port:
            raise HTTPException(status_code=404, detail="Review server not found for this job")
        
        # Forward request to local server
        response = requests.get(
            f"http://localhost:{review_port}/api/preview-video/{preview_hash}",
            stream=True,
            timeout=30
        )
        response.raise_for_status()
        
        # Stream the video back
        return StreamingResponse(
            iter(lambda: response.raw.read(8192), b""),
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": "inline",
                "Cache-Control": "no-cache",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying preview video: {str(e)}")

@api_app.get("/api/corrections/{job_id}/audio/{audio_hash}")
async def proxy_get_audio(job_id: str, audio_hash: str):
    """Proxy audio file access to local LyricsTranscriber server."""
    try:
        import requests
        from fastapi.responses import StreamingResponse
        
        # Check if review server is running for this job
        review_port = get_review_server_port(job_id)
        if not review_port:
            raise HTTPException(status_code=404, detail="Review server not found for this job")
        
        # Forward request to local server
        response = requests.get(
            f"http://localhost:{review_port}/api/audio/{audio_hash}",
            stream=True,
            timeout=30
        )
        response.raise_for_status()
        
        # Stream the audio back
        return StreamingResponse(
            iter(lambda: response.raw.read(8192), b""),
            media_type="audio/mpeg"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying audio: {str(e)}")

@api_app.post("/api/corrections/{job_id}/handlers")
async def proxy_update_handlers(job_id: str, request: Request):
    """Proxy handler update to local LyricsTranscriber server."""
    try:
        import requests
        
        # Check if review server is running for this job
        review_port = get_review_server_port(job_id)
        if not review_port:
            raise HTTPException(status_code=404, detail="Review server not found for this job")
        
        # Get the request body
        body = await request.body()
        
        # Forward request to local server
        response = requests.post(
            f"http://localhost:{review_port}/api/handlers",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        response.raise_for_status()
        
        return JSONResponse(response.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying handler update: {str(e)}")

@api_app.post("/api/corrections/{job_id}/add-lyrics")
async def proxy_add_lyrics(job_id: str, request: Request):
    """Proxy add lyrics to local LyricsTranscriber server."""
    try:
        import requests
        
        # Check if review server is running for this job
        review_port = get_review_server_port(job_id)
        if not review_port:
            raise HTTPException(status_code=404, detail="Review server not found for this job")
        
        # Get the request body
        body = await request.body()
        
        # Forward request to local server
        response = requests.post(
            f"http://localhost:{review_port}/api/add-lyrics",
            data=body,
            headers={"Content-Type": "application/json"},
            timeout=60
        )
        response.raise_for_status()
        
        return JSONResponse(response.json())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error proxying add lyrics: {str(e)}")

# Helper function to track review servers
def get_review_server_port(job_id: str) -> Optional[int]:
    """Get the port number for a job's review server."""
    # This will be implemented to track running review servers
    # For now, we'll use a simple mapping stored in the job status
    job_data = job_status_dict.get(job_id)
    if job_data and "review_server_port" in job_data:
        return job_data["review_server_port"]
    return None

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

 