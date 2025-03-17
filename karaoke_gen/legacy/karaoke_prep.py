"""
Legacy compatibility wrapper for the KaraokePrep class.
"""

import logging
import os
import asyncio
from typing import Dict, Any, List, Optional

from karaoke_gen.core.project import ProjectConfig
from karaoke_gen.core.track import Track
from karaoke_gen.controller import KaraokeController


class KaraokePrep:
    """
    Legacy compatibility wrapper for the KaraokePrep class.
    This class maintains backward compatibility with existing code that uses the old KaraokePrep class.
    """
    
    def __init__(
        self,
        # Basic inputs
        input_media=None,
        artist=None,
        title=None,
        filename_pattern=None,
        # Logging & Debugging
        dry_run=False,
        logger=None,
        log_level=logging.DEBUG,
        log_formatter=None,
        render_bounding_boxes=False,
        # Input/Output Configuration
        output_dir=".",
        create_track_subfolders=False,
        lossless_output_format="FLAC",
        output_png=True,
        output_jpg=True,
        # Audio Processing Configuration
        clean_instrumental_model="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        backing_vocals_models=["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"],
        other_stems_models=["htdemucs_6s.yaml"],
        model_file_dir=None,
        existing_instrumental=None,
        # Lyrics Configuration
        lyrics_artist=None,
        lyrics_title=None,
        lyrics_file=None,
        skip_lyrics=False,
        skip_transcription=False,
        skip_transcription_review=False,
        render_video=True,
        subtitle_offset_ms=0,
        # Style Configuration
        style_params_json=None,
        # Add the new parameter
        skip_separation=False,
    ):
        """
        Initialize the KaraokePrep wrapper.
        
        Args:
            input_media: The input media (URL, file, or directory)
            artist: The artist name
            title: The song title
            filename_pattern: The filename pattern for extracting track names
            dry_run: Whether to perform a dry run
            logger: The logger
            log_level: The log level
            log_formatter: The log formatter
            render_bounding_boxes: Whether to render bounding boxes
            output_dir: The output directory
            create_track_subfolders: Whether to create track subfolders
            lossless_output_format: The lossless output format
            output_png: Whether to output PNG format
            output_jpg: Whether to output JPG format
            clean_instrumental_model: The clean instrumental model
            backing_vocals_models: The backing vocals models
            other_stems_models: The other stems models
            model_file_dir: The model file directory
            existing_instrumental: The existing instrumental
            lyrics_artist: The artist name for lyrics search
            lyrics_title: The song title for lyrics search
            lyrics_file: The lyrics file
            skip_lyrics: Whether to skip lyrics processing
            skip_transcription: Whether to skip transcription
            skip_transcription_review: Whether to skip transcription review
            render_video: Whether to render video
            subtitle_offset_ms: The subtitle offset in milliseconds
            style_params_json: The style parameters JSON file
            skip_separation: Whether to skip audio separation
        """
        # Set default model_file_dir if not provided
        if model_file_dir is None:
            import tempfile
            model_file_dir = os.path.join(tempfile.gettempdir(), "audio-separator-models")
        
        # Create configuration
        self.config = ProjectConfig(
            # Basic inputs
            input_media=input_media,
            artist=artist,
            title=title,
            filename_pattern=filename_pattern,
            
            # Workflow control
            prep_only=True,  # Legacy KaraokePrep only does prep
            finalise_only=False,
            skip_transcription=skip_transcription,
            skip_separation=skip_separation,
            skip_lyrics=skip_lyrics,
            lyrics_only=False,
            edit_lyrics=False,
            
            # Logging & Debugging
            dry_run=dry_run,
            logger=logger,
            log_level=log_level,
            log_formatter=log_formatter,
            render_bounding_boxes=render_bounding_boxes,
            
            # Input/Output Configuration
            output_dir=output_dir,
            create_track_subfolders=create_track_subfolders,
            lossless_output_format=lossless_output_format,
            output_png=output_png,
            output_jpg=output_jpg,
            
            # Audio Processing Configuration
            clean_instrumental_model=clean_instrumental_model,
            backing_vocals_models=backing_vocals_models,
            other_stems_models=other_stems_models,
            model_file_dir=model_file_dir,
            existing_instrumental=existing_instrumental,
            
            # Lyrics Configuration
            lyrics_artist=lyrics_artist,
            lyrics_title=lyrics_title,
            lyrics_file=lyrics_file,
            skip_transcription_review=skip_transcription_review,
            render_video=render_video,
            subtitle_offset_ms=subtitle_offset_ms,
            
            # Style Configuration
            style_params_json=style_params_json,
        )
        
        # Create controller
        self.controller = KaraokeController(self.config)
    
    async def process(self) -> List[Dict[str, Any]]:
        """
        Process the track or tracks.
        
        Returns:
            List of processed tracks in the legacy format
        """
        # Process tracks
        tracks = await self.controller.process()
        
        # Convert to legacy format
        return [self._convert_to_legacy_format(track) for track in tracks]
    
    def _convert_to_legacy_format(self, track: Track) -> Dict[str, Any]:
        """
        Convert a Track object to the legacy format.
        
        Args:
            track: The Track object
            
        Returns:
            The track in the legacy format
        """
        return {
            "artist": track.artist,
            "title": track.title,
            "input_media": track.input_media,
            "track_output_dir": track.track_output_dir,
            "input_audio_wav": track.input_audio_wav,
            "input_still_image": track.input_still_image,
            "lyrics": track.lyrics,
            "processed_lyrics": track.processed_lyrics,
            "separated_audio": track.separated_audio,
            "title_video": track.title_video,
            "end_video": track.end_video,
            "video_with_vocals": track.video_with_vocals,
            "video_with_instrumental": track.video_with_instrumental,
        }
    
    def backup_existing_outputs(self, track_output_dir, artist, title):
        """
        Legacy method for backing up existing outputs.
        
        Args:
            track_output_dir: The track output directory
            artist: The artist name
            title: The song title
            
        Returns:
            The input audio WAV file
        """
        # Create a track
        track = Track(
            artist=artist,
            title=title,
            track_output_dir=track_output_dir
        )
        
        # Backup existing outputs
        asyncio.run(self.controller.lyrics_service.backup_and_prepare_for_edit(track))
        
        # Return the input audio WAV file
        return track.input_audio_wav 