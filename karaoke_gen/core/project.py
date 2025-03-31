from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import logging
import os
import tempfile


@dataclass
class ProjectConfig:
    """
    Configuration for a karaoke generation project.
    This class holds all the configuration parameters for the karaoke generation process.
    """
    # Basic inputs
    input_media: Optional[str] = None
    artist: Optional[str] = None
    title: Optional[str] = None
    filename_pattern: Optional[str] = None
    
    # Workflow control
    prep_only: bool = False
    finalise_only: bool = False
    skip_transcription: bool = False
    skip_separation: bool = False
    skip_lyrics: bool = False
    skip_download: bool = False
    lyrics_only: bool = False
    edit_lyrics: bool = False
    
    # Logging & Debugging
    dry_run: bool = False
    logger: Optional[logging.Logger] = None
    log_level: int = logging.DEBUG
    log_formatter: Optional[logging.Formatter] = None
    render_bounding_boxes: bool = False
    
    # Input/Output Configuration
    output_dir: str = "."
    create_track_subfolders: bool = True
    lossless_output_format: str = "flac"
    output_png: bool = True
    output_jpg: bool = True
    
    # Audio Processing Configuration
    clean_instrumental_model: str = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"
    backing_vocals_models: List[str] = field(default_factory=lambda: ["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"])
    other_stems_models: List[str] = field(default_factory=lambda: ["htdemucs_6s.yaml"])
    model_file_dir: str = field(default_factory=lambda: os.path.join(tempfile.gettempdir(), "audio-separator-models"))
    existing_instrumental: Optional[str] = None
    instrumental_format: str = "flac"

    # Lyrics Configuration
    lyrics_artist: Optional[str] = None
    lyrics_title: Optional[str] = None
    lyrics_file: Optional[str] = None
    skip_transcription_review: bool = False
    render_video: bool = True
    subtitle_offset_ms: int = 0
    
    # Style Configuration
    style_params_json: Optional[str] = None
    
    # Video Configuration
    title_screen_duration: float = 5.0
    end_screen_duration: float = 5.0
    title_fade_in: float = 1.0
    title_fade_out: float = 1.0
    end_fade_in: float = 1.0
    end_fade_out: float = 1.0
    
    # Finalisation Configuration
    enable_cdg: bool = False
    enable_txt: bool = False
    brand_prefix: Optional[str] = None
    organised_dir: Optional[str] = None
    organised_dir_rclone_root: Optional[str] = None
    public_share_dir: Optional[str] = None
    youtube_client_secrets_file: Optional[str] = None
    youtube_description_file: Optional[str] = None
    rclone_destination: Optional[str] = None
    discord_webhook_url: Optional[str] = None
    email_template_file: Optional[str] = None
    cdg_styles: Optional[Dict[str, Any]] = None
    keep_brand_code: bool = False
    non_interactive: bool = False
    
    def __post_init__(self):
        """Perform post-initialization setup"""
        # Set up logger if not provided
        if self.logger is None:
            self.logger = logging.getLogger("karaoke_gen")
            handler = logging.StreamHandler()
            if self.log_formatter is None:
                self.log_formatter = logging.Formatter(
                    fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S"
                )
            handler.setFormatter(self.log_formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(self.log_level)
        
        # If lyrics_artist/title not specified, use the main artist/title
        if self.lyrics_artist is None and self.artist is not None:
            self.lyrics_artist = self.artist
        
        if self.lyrics_title is None and self.title is not None:
            self.lyrics_title = self.title 