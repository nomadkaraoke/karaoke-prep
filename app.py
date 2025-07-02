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

from fastapi import FastAPI, Request, Form, HTTPException
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
        # FastAPI dependencies
        "fastapi>=0.104.0",
        "uvicorn>=0.24.0",
        "python-multipart>=0.0.6",
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

# GPU Worker Functions
@app.function(
    image=karaoke_image,
    gpu="any",
    volumes=VOLUME_CONFIG,
    secrets=[modal.Secret.from_name("karaoke-api-keys")],
    timeout=1800,
)
def process_part_one(job_id: str, youtube_url: str):
    """First phase: Download audio, separate, and transcribe lyrics."""
    import sys
    import traceback
    from datetime import datetime
    
    def log_message(level: str, message: str):
        """Log a message with timestamp and level."""
        timestamp = datetime.now().isoformat()
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
    
    try:
        from core import CoreKaraokeProcessor
        
        log_message("INFO", f"Starting job {job_id} for URL: {youtube_url}")
        
        # Update status
        job_status_dict[job_id] = {
            "status": "processing_audio", 
            "progress": 10,
            "url": youtube_url,
            "created_at": datetime.now().isoformat()
        }
        
        # Initialize processor
        processor = CoreKaraokeProcessor()
        
        # Phase 1: Download and prep audio
        log_message("INFO", "Downloading and preparing audio...")
        output_dir = Path(f"/output/{job_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        original_audio_path = processor.download_and_prep_audio(youtube_url, str(output_dir))
        log_message("INFO", f"Audio downloaded to: {original_audio_path}")
        
        # Phase 2: Audio separation
        job_status_dict[job_id] = {"status": "processing_audio", "progress": 30, "url": youtube_url}
        log_message("INFO", "Starting audio separation...")
        
        instrumental_path, vocals_path = processor.run_audio_separation(original_audio_path, "/models")
        log_message("INFO", f"Audio separated - Instrumental: {instrumental_path}, Vocals: {vocals_path}")
        
        # Phase 3: Transcribe lyrics
        job_status_dict[job_id] = {"status": "transcribing", "progress": 60, "url": youtube_url}
        log_message("INFO", "Starting lyrics transcription...")
        
        transcription_data = processor.transcribe_lyrics(vocals_path)
        log_message("INFO", "Lyrics transcribed successfully")
        
        # Save transcription data
        transcription_path = output_dir / "transcription_raw.json"
        with open(transcription_path, 'w') as f:
            json.dump(transcription_data, f, indent=2)
        
        # Update status to awaiting review
        job_status_dict[job_id] = {
            "status": "awaiting_review", 
            "progress": 75,
            "url": youtube_url,
            "transcription_path": str(transcription_path)
        }
        
        log_message("SUCCESS", f"Phase 1 completed for job {job_id}. Awaiting lyrics review.")
        return {"status": "success", "message": "Phase 1 completed, awaiting lyrics review"}
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        log_message("ERROR", f"Phase 1 failed: {error_msg}")
        log_message("ERROR", f"Traceback: {error_traceback}")
        
        job_status_dict[job_id] = {
            "status": "error", 
            "progress": 0,
            "url": youtube_url,
            "error": error_msg,
            "traceback": error_traceback
        }
        
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
    from datetime import datetime
    
    def log_message(level: str, message: str):
        """Log a message with timestamp and level."""
        timestamp = datetime.now().isoformat()
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
    
    try:
        from core import CoreKaraokeProcessor
        
        log_message("INFO", f"Starting phase 2 for job {job_id}")
        
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
        
        log_message("INFO", "Corrected lyrics loaded")
        
        # Generate video assets
        log_message("INFO", "Starting video generation...")
        
        instrumental_path = output_dir / "instrumental.wav"
        video_path = processor.generate_video_assets(corrected_lyrics, str(instrumental_path))
        
        log_message("INFO", f"Video generated: {video_path}")
        
        # Update status to complete
        job_status_dict[job_id] = {
            "status": "complete", 
            "progress": 100,
            "video_path": video_path,
            "video_url": f"/api/jobs/{job_id}/download"
        }
        
        log_message("SUCCESS", f"Job {job_id} completed successfully!")
        return {"status": "success", "message": "Video generation completed", "video_path": video_path}
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        
        log_message("ERROR", f"Phase 2 failed: {error_msg}")
        log_message("ERROR", f"Traceback: {error_traceback}")
        
        job_status_dict[job_id] = {
            "status": "error", 
            "progress": 0,
            "error": error_msg,
            "traceback": error_traceback
        }
        
        raise Exception(f"Phase 2 failed: {error_msg}")

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
    """Get lyrics for review (returns HTML page)."""
    try:
        job_data = job_status_dict.get(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        if job_data.get("status") != "awaiting_review":
            raise HTTPException(status_code=400, detail="Job is not awaiting review")
        
        # Load raw transcription
        output_dir = Path(f"/output/{job_id}")
        transcription_path = output_dir / "transcription_raw.json"
        
        if not transcription_path.exists():
            raise HTTPException(status_code=404, detail="Transcription not found")
        
        with open(transcription_path, 'r') as f:
            raw_lyrics = json.load(f)
        
        # Return HTML page for lyrics review
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Review Lyrics - Job {job_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                textarea {{ width: 100%; height: 400px; font-family: monospace; }}
                button {{ padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; }}
                button:hover {{ background: #0056b3; }}
            </style>
        </head>
        <body>
            <h1>Review Lyrics for Job {job_id}</h1>
            <form action="/api/review/{job_id}" method="post">
                <textarea name="lyrics" placeholder="Edit the lyrics here...">{json.dumps(raw_lyrics, indent=2)}</textarea>
                <br><br>
                <button type="submit">✅ Approve and Continue to Video Generation</button>
            </form>
        </body>
        </html>
        """
        
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content=html_content)
        
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
        existing_logs = job_logs_dict.get(job_id, [])
        existing_logs.append({
            "timestamp": datetime.datetime.now().isoformat(),
            "level": "INFO",
            "message": "Lyrics approved, starting video generation"
        })
        job_logs_dict[job_id] = existing_logs
        
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

# Expose API endpoints to the internet (API-only, frontend served separately via GitHub Pages)
@app.function(
    image=karaoke_image,
    volumes=VOLUME_CONFIG,
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

 