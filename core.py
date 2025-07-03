"""
Core processing functions for karaoke generation.

This module contains the isolated core logic from the original karaoke-gen CLI tool,
modified to remove interactive elements and print statements for serverless execution.
"""

import os
import sys
import json
import logging
import tempfile
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Import the existing processor classes
from karaoke_gen.audio_processor import AudioProcessor
from karaoke_gen.lyrics_processor import LyricsProcessor
from karaoke_gen.video_generator import VideoGenerator
from karaoke_gen.file_handler import FileHandler
from karaoke_gen.metadata import extract_info_for_online_media, parse_track_metadata
from karaoke_gen.config import (
    load_style_params,
    setup_title_format,
    setup_end_format,
    get_video_durations,
    get_existing_images,
    setup_ffmpeg_command,
)


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


class CoreKaraokeProcessor:
    """
    Main processor class that orchestrates the karaoke generation workflow.
    """
    
    def __init__(self, model_dir: str = "/models", output_dir: str = "/output"):
        self.model_dir = model_dir
        self.output_dir = output_dir
        self.logger = setup_logger()
    
    def download_and_prep_audio(self, url: str, output_dir: str) -> str:
        """
        Download audio from URL and convert to WAV format.
        
        Args:
            url: YouTube or other media URL
            output_dir: Directory to store downloaded files
            
        Returns:
            Path to the converted WAV audio file
        """
        self.logger.info(f"Starting download and prep for URL: {url}")
        
        # Create a temporary FileHandler instance for download operations
        file_handler = FileHandler(
            logger=self.logger,
            ffmpeg_base_command=setup_ffmpeg_command(logging.INFO),
            create_track_subfolders=False,
            dry_run=False,
        )
        
        try:
            # Extract metadata from URL
            extracted_info = extract_info_for_online_media(url, None, None, self.logger)
            if not extracted_info:
                raise ValueError(f"Could not extract metadata from URL: {url}")
            
            metadata_result = parse_track_metadata(
                extracted_info, None, None, None, self.logger
            )
            
            artist = metadata_result["artist"]
            title = metadata_result["title"]
            extractor = metadata_result["extractor"]
            media_id = metadata_result["media_id"]
            
            # Create filename
            filename_suffix = f"{extractor} {media_id}" if media_id else extractor
            artist_title = f"{artist} - {title}"
            output_filename_no_extension = os.path.join(output_dir, f"{artist_title} ({filename_suffix})")
            
            # Download video with enhanced yt-dlp options for better bot avoidance
            downloaded_file = self._download_video_with_fallback(file_handler, url, output_filename_no_extension)
            
            # Convert to WAV
            wav_file = file_handler.convert_to_wav(downloaded_file, output_filename_no_extension + " (Original)")
            
            self.logger.info(f"Successfully downloaded and converted to WAV: {wav_file}")
            return wav_file
            
        except Exception as e:
            self.logger.error(f"Failed to download and prep audio: {str(e)}")
            raise
    
    def _download_video_with_fallback(self, file_handler, url: str, output_filename_no_extension: str) -> str:
        """Download video with enhanced options and fallback strategies."""
        import yt_dlp
        
        # Enhanced yt-dlp options to avoid bot detection
        enhanced_opts = {
            "quiet": True,
            "format": "bv*+ba/b",
            "outtmpl": f"{output_filename_no_extension}.%(ext)s",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "extractor_retries": 3,
            "sleep_interval": 1,
            "max_sleep_interval": 5,
            "ignoreerrors": False,
            # Add headers to look more like a real browser
            "http_headers": {
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "DNT": "1",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        }
        
        try:
            self.logger.info("Attempting download with enhanced options...")
            with yt_dlp.YoutubeDL(enhanced_opts) as ydl_instance:
                ydl_instance.download([url])
                
                # Search for the downloaded file
                import glob
                downloaded_files = glob.glob(f"{output_filename_no_extension}.*")
                if downloaded_files:
                    downloaded_file_name = downloaded_files[0]
                    self.logger.info(f"Download successful: {downloaded_file_name}")
                    return downloaded_file_name
                else:
                    raise Exception("No files found after download")
                    
        except Exception as e:
            self.logger.warning(f"Enhanced download failed: {str(e)}")
            
            # Fallback to basic download method
            try:
                self.logger.info("Falling back to basic download method...")
                return file_handler.download_video(url, output_filename_no_extension)
            except Exception as fallback_error:
                self.logger.error(f"Fallback download also failed: {str(fallback_error)}")
                raise Exception(f"All download methods failed. Last error: {str(fallback_error)}")
    
    def run_audio_separation(self, audio_file: str, model_dir: str) -> Tuple[str, str]:
        """
        Run audio separation on the input audio file.
        
        Args:
            audio_file: Path to input audio WAV file
            model_dir: Directory containing AI models
            
        Returns:
            Tuple of (instrumental_path, vocals_path)
        """
        self.logger.info(f"Starting audio separation for: {audio_file}")
        
        # Get artist and title from filename for output naming
        filename = os.path.basename(audio_file)
        artist_title = filename.replace(".wav", "").replace(" (Original)", "")
        track_output_dir = os.path.dirname(audio_file)
        
        # Initialize AudioProcessor
        audio_processor = AudioProcessor(
            logger=self.logger,
            log_level=logging.INFO,
            log_formatter=None,
            model_file_dir=model_dir,
            lossless_output_format="FLAC",
            clean_instrumental_model="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
            backing_vocals_models=["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"],
            other_stems_models=["htdemucs_6s.yaml"],
            ffmpeg_base_command=setup_ffmpeg_command(logging.INFO),
        )
        
        # Run separation
        separation_results = audio_processor.process_audio_separation(
            audio_file=audio_file,
            artist_title=artist_title,
            track_output_dir=track_output_dir,
        )
        
        # Extract paths for instrumental and vocals
        instrumental_path = separation_results["clean_instrumental"]["instrumental"]
        vocals_path = separation_results["clean_instrumental"]["vocals"]
        
        self.logger.info(f"Audio separation completed - Instrumental: {instrumental_path}, Vocals: {vocals_path}")
        return instrumental_path, vocals_path


    def transcribe_lyrics(self, vocals_path: str, artist: str, title: str, output_dir: str) -> Dict[str, Any]:
        """
        Transcribe lyrics from vocals audio file.
        
        Args:
            vocals_path: Path to vocals audio file
            artist: Artist name
            title: Song title
            output_dir: Output directory for lyrics files
            
        Returns:
            Dictionary containing transcription results and file paths
        """
        self.logger.info(f"Starting lyrics transcription for: {vocals_path}")
        
        # Initialize LyricsProcessor
        lyrics_processor = LyricsProcessor(
            logger=self.logger,
            style_params_json=None,  # Use default styles
            lyrics_file=None,
            skip_transcription=False,
            skip_transcription_review=True,  # Skip interactive review for serverless
            render_video=False,  # Don't render video in transcription step
            subtitle_offset_ms=0,
        )
        
        # Run transcription
        transcription_results = lyrics_processor.transcribe_lyrics(
            input_audio_wav=vocals_path,
            artist=artist,
            title=title,
            track_output_dir=output_dir,
        )
        
        self.logger.info("Lyrics transcription completed")
        return transcription_results

    def convert_to_wav(self, audio_file_path: str, artist: str, title: str, output_dir: str) -> str:
        """
        Convert uploaded audio file to WAV format.
        
        Args:
            audio_file_path: Path to uploaded audio file
            artist: Artist name
            title: Song title  
            output_dir: Output directory
            
        Returns:
            Path to converted WAV file
        """
        self.logger.info(f"Converting audio file to WAV: {audio_file_path}")
        
        # Create FileHandler for conversion
        file_handler = FileHandler(
            logger=self.logger,
            ffmpeg_base_command=setup_ffmpeg_command(logging.INFO),
            create_track_subfolders=False,
            dry_run=False,
        )
        
        # Check if the input file is already a WAV file in the right location
        if audio_file_path.endswith('.wav') and output_dir in audio_file_path:
            self.logger.info("File is already a WAV in the output directory")
            return audio_file_path
        
        # Create output filename
        artist_title = f"{artist} - {title}"
        output_filename_no_extension = os.path.join(output_dir, f"{artist_title} (Original)")
        
        # Convert to WAV
        wav_file = file_handler.convert_to_wav(audio_file_path, output_filename_no_extension)
        
        self.logger.info(f"Successfully converted to WAV: {wav_file}")
        return wav_file
    
    def transcribe_lyrics_with_metadata(self, vocals_path: str, artist: str, title: str) -> Dict[str, Any]:
        """
        Transcribe lyrics from vocals audio file with provided metadata.
        
        Args:
            vocals_path: Path to vocals audio file
            artist: Artist name
            title: Song title
            
        Returns:
            Dictionary containing transcription results
        """
        self.logger.info(f"Starting lyrics transcription for: {artist} - {title}")
        
        track_output_dir = os.path.dirname(vocals_path)
        
        # Initialize LyricsProcessor
        lyrics_processor = LyricsProcessor(
            logger=self.logger,
            style_params_json=None,  # Use default styles
            lyrics_file=None,
            skip_transcription=False,
            skip_transcription_review=True,  # Skip interactive review for serverless
            render_video=False,  # Don't render video in transcription step
            subtitle_offset_ms=0,
        )
        
        # Run transcription
        transcription_results = lyrics_processor.transcribe_lyrics(
            input_audio_wav=vocals_path,
            artist=artist,
            title=title,
            track_output_dir=track_output_dir,
        )
        
        self.logger.info("Lyrics transcription completed")
        return transcription_results

    def process_track(self, job_id: str, url: str, status_callback=None) -> Dict[str, Any]:
        """
        Process a single track through the complete karaoke generation pipeline.
        
        Args:
            job_id: Unique identifier for this job
            url: YouTube or media URL
            status_callback: Optional callback function to update job status
            
        Returns:
            Dictionary with processing results and output file paths
        """
        try:
            job_output_dir = Path(self.output_dir) / job_id
            job_output_dir.mkdir(parents=True, exist_ok=True)
            
            if status_callback:
                status_callback(job_id, {"status": "downloading", "progress": 10})
            
            # Step 1: Download and prep audio
            audio_path = self.download_and_prep_audio(url, str(job_output_dir))
            
            if status_callback:
                status_callback(job_id, {"status": "separating_audio", "progress": 25})
            
            # Step 2: Run audio separation
            instrumental_path, vocals_path = self.run_audio_separation(audio_path, self.model_dir)
            
            if status_callback:
                status_callback(job_id, {"status": "transcribing", "progress": 50})
            
            # Step 3: Transcribe lyrics (extract artist/title from filename)
            filename = os.path.basename(audio_path)
            # Parse artist - title from filename (assumes format "Artist - Title (...)...")
            if " - " in filename:
                artist, title_part = filename.split(" - ", 1)
                title = title_part.split(" (")[0]  # Remove extractor info
            else:
                artist, title = "Unknown Artist", "Unknown Title"
            
            transcription_results = self.transcribe_lyrics(
                vocals_path, artist, title, str(job_output_dir)
            )
            
            if status_callback:
                status_callback(job_id, {"status": "awaiting_review", "progress": 75})
            
            return {
                "job_id": job_id,
                "artist": artist,
                "title": title,
                "audio_path": audio_path,
                "instrumental_path": instrumental_path,
                "vocals_path": vocals_path,
                "transcription_results": transcription_results,
                "status": "awaiting_review"
            }
            
        except Exception as e:
            self.logger.error(f"Error processing track {job_id}: {str(e)}")
            if status_callback:
                status_callback(job_id, {"status": "error", "progress": 0, "error": str(e)})
            raise
    
    async def finalize_track(self, job_id: str, corrected_lyrics: str, status_callback=None) -> Dict[str, Any]:
        """
        Finalize track processing with corrected lyrics.
        
        Args:
            job_id: Job identifier
            corrected_lyrics: Human-corrected lyrics
            status_callback: Optional status callback
            
        Returns:
            Dictionary with final processing results
        """
        try:
            job_output_dir = Path(self.output_dir) / job_id
            
            if status_callback:
                status_callback(job_id, {"status": "generating_video", "progress": 80})
            
            # Find the instrumental file
            instrumental_files = list(job_output_dir.glob("*Instrumental*.flac"))
            if not instrumental_files:
                raise ValueError("No instrumental file found")
            
            instrumental_path = str(instrumental_files[0])
            
            # Extract artist/title from directory structure or files
            audio_files = list(job_output_dir.glob("*.wav"))
            if audio_files:
                filename = audio_files[0].stem
                if " - " in filename:
                    artist, title_part = filename.split(" - ", 1)
                    title = title_part.split(" (")[0]
                else:
                    artist, title = "Unknown Artist", "Unknown Title"
            else:
                artist, title = "Unknown Artist", "Unknown Title"
            
            # Generate final video
            final_video_path = self.generate_video_assets(
                corrected_lyrics, instrumental_path, str(job_output_dir), artist, title
            )
            
            if status_callback:
                status_callback(job_id, {
                    "status": "complete", 
                    "progress": 100, 
                    "video_path": final_video_path
                })
            
            return {
                "job_id": job_id,
                "status": "complete",
                "final_video_path": final_video_path,
                "artist": artist,
                "title": title
            }
            
        except Exception as e:
            self.logger.error(f"Error finalizing track {job_id}: {str(e)}")
            if status_callback:
                status_callback(job_id, {"status": "error", "progress": 0, "error": str(e)})
            raise
    
    def generate_video_assets(self, lyrics_data: str, instrumental_path: str) -> str:
        """
        Generate final karaoke video with synchronized lyrics.
        
        Args:
            lyrics_data: Corrected lyrics text or JSON data
            instrumental_path: Path to instrumental audio
            
        Returns:
            Path to generated video file
        """
        self.logger.info("Starting video generation...")
        
        # Parse artist and title from the instrumental filename
        filename = os.path.basename(instrumental_path)
        base_name = filename.replace(".flac", "").replace(".wav", "")
        
        if " - " in base_name:
            artist, title_part = base_name.split(" - ", 1)
            title = title_part.split(" (")[0]
        else:
            artist, title = "Unknown Artist", "Unknown Title"
        
        output_dir = os.path.dirname(instrumental_path)
        
        # Initialize VideoGenerator
        video_generator = VideoGenerator(
            logger=self.logger,
            ffmpeg_base_command=setup_ffmpeg_command(logging.INFO),
            render_bounding_boxes=False,
            output_png=True,
            output_jpg=True,
        )
        
        # Load default style parameters
        style_params = load_style_params(None, self.logger)
        title_format = setup_title_format(style_params)
        end_format = setup_end_format(style_params)
        
        # Generate title screen
        title_output_path = os.path.join(output_dir, f"{artist} - {title} (Title)")
        title_video_path = os.path.join(output_dir, f"{artist} - {title} (Title).mov")
        
        video_generator.create_title_video(
            artist=artist,
            title=title,
            format=title_format,
            output_image_filepath_noext=title_output_path,
            output_video_filepath=title_video_path,
            existing_title_image=None,
            intro_video_duration=5,  # 5 second title
        )
        
        # Generate end screen
        end_output_path = os.path.join(output_dir, f"{artist} - {title} (End)")
        end_video_path = os.path.join(output_dir, f"{artist} - {title} (End).mov")
        
        video_generator.create_end_video(
            artist=artist,
            title=title,
            format=end_format,
            output_image_filepath_noext=end_output_path,
            output_video_filepath=end_video_path,
            existing_end_image=None,
            end_video_duration=5,  # 5 second end screen
        )
        
        # For now, return the title video path as a placeholder
        # In a full implementation, this would combine title + karaoke content + end screen
        final_video_path = os.path.join(output_dir, f"{artist} - {title} (Final).mp4")
        
        # Create a simple combined video (placeholder logic)
        # This would be replaced with proper karaoke video generation
        ffmpeg_command = (
            f'ffmpeg -y -i "{title_video_path}" -i "{end_video_path}" '
            f'-filter_complex "[0:v][1:v]concat=n=2:v=1[v]" -map "[v]" '
            f'"{final_video_path}"'
        )
        
        os.system(ffmpeg_command)
        
        self.logger.info(f"Video generation completed: {final_video_path}")
        return final_video_path
    
    def transcribe_lyrics_with_metadata(self, vocals_path: str, artist: str, title: str) -> Dict[str, Any]:
        """
        Transcribe lyrics from vocals audio file with provided metadata.
        
        Args:
            vocals_path: Path to vocals audio file
            artist: Artist name
            title: Song title
            
        Returns:
            Dictionary containing transcription results
        """
        self.logger.info(f"Starting lyrics transcription for: {artist} - {title}")
        
        track_output_dir = os.path.dirname(vocals_path)
        
        # Initialize LyricsProcessor
        lyrics_processor = LyricsProcessor(
            logger=self.logger,
            style_params_json=None,  # Use default styles
            lyrics_file=None,
            skip_transcription=False,
            skip_transcription_review=True,  # Skip interactive review for serverless
            render_video=False,  # Don't render video in transcription step
            subtitle_offset_ms=0,
        )
        
        # Run transcription
        transcription_results = lyrics_processor.transcribe_lyrics(
            input_audio_wav=vocals_path,
            artist=artist,
            title=title,
            track_output_dir=track_output_dir,
        )
        
        self.logger.info("Lyrics transcription completed")
        return transcription_results