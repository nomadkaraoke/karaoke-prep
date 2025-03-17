import os
import logging
import asyncio
import time
import pyperclip
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.controller import KaraokeController


class Command(ABC):
    """Base class for all commands."""
    
    @abstractmethod
    async def execute(self, args: Dict[str, Any]) -> None:
        """
        Execute the command.
        
        Args:
            args: The parsed command-line arguments
        """
        pass


class ProcessCommand(Command):
    """Command for processing a track or tracks."""
    
    async def execute(self, args: Dict[str, Any]) -> None:
        """
        Execute the process command.
        
        Args:
            args: The parsed command-line arguments
        """
        # Set up logging
        logger = logging.getLogger(__name__)
        log_handler = logging.StreamHandler()
        log_formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        log_handler.setFormatter(log_formatter)
        logger.addHandler(log_handler)
        
        log_level = getattr(logging, args.get("log_level", "INFO").upper())
        logger.setLevel(log_level)
        
        # Parse input arguments
        input_media, artist, title, filename_pattern = self._parse_input_args(args, logger)
        
        # Set up environment variables for lyrics-only mode
        if args.get("lyrics_only"):
            args["skip_separation"] = True
            os.environ["KARAOKE_PREP_SKIP_AUDIO_SEPARATION"] = "1"
            os.environ["KARAOKE_PREP_SKIP_TITLE_END_SCREENS"] = "1"
            logger.info("Lyrics-only mode enabled: skipping audio separation and title/end screen generation")
        
        # Create configuration
        config = self._create_config(args, input_media, artist, title, filename_pattern, log_formatter, log_level, logger)
        
        # Create controller
        controller = KaraokeController(config)
        
        # Process tracks
        tracks = await controller.process()
        
        # Display results
        self._display_results(tracks, args, logger)
    
    def _parse_input_args(self, args: Dict[str, Any], logger: logging.Logger) -> tuple:
        """
        Parse input arguments.
        
        Args:
            args: The parsed command-line arguments
            logger: The logger
            
        Returns:
            Tuple of (input_media, artist, title, filename_pattern)
        """
        input_media, artist, title, filename_pattern = None, None, None, None
        
        if not args.get("args"):
            logger.error("No input arguments provided")
            exit(1)
        
        # Allow 3 forms of positional arguments:
        # 1. URL or Media File only (may be single track URL, playlist URL, or local file)
        # 2. Artist and Title only
        # 3. URL, Artist, and Title
        if args["args"] and (self._is_url(args["args"][0]) or self._is_file(args["args"][0])):
            input_media = args["args"][0]
            if len(args["args"]) > 2:
                artist = args["args"][1]
                title = args["args"][2]
            elif len(args["args"]) > 1:
                artist = args["args"][1]
            else:
                logger.warning("Input media provided without Artist and Title, both will be guessed from title")
        
        elif os.path.isdir(args["args"][0]):
            if not args.get("filename_pattern"):
                logger.error("Filename pattern is required when processing a folder.")
                exit(1)
            if len(args["args"]) <= 1:
                logger.error("Second parameter provided must be Artist name; Artist is required when processing a folder.")
                exit(1)
            
            input_media = args["args"][0]
            artist = args["args"][1]
            filename_pattern = args.get("filename_pattern")
        
        elif len(args["args"]) > 1:
            artist = args["args"][0]
            title = args["args"][1]
            logger.warning(f"No input media provided, the top YouTube search result for {artist} - {title} will be used.")
        
        else:
            logger.error("Invalid input arguments")
            exit(1)
        
        return input_media, artist, title, filename_pattern
    
    def _is_url(self, string: str) -> bool:
        """
        Check if a string is a URL.
        
        Args:
            string: The string to check
            
        Returns:
            True if the string is a URL, False otherwise
        """
        return string.startswith("http://") or string.startswith("https://")
    
    def _is_file(self, string: str) -> bool:
        """
        Check if a string is a file.
        
        Args:
            string: The string to check
            
        Returns:
            True if the string is a file, False otherwise
        """
        return os.path.isfile(string)
    
    def _create_config(self, args: Dict[str, Any], input_media: Optional[str], artist: Optional[str], 
                      title: Optional[str], filename_pattern: Optional[str], log_formatter: logging.Formatter, 
                      log_level: int, logger: logging.Logger) -> ProjectConfig:
        """
        Create a project configuration.
        
        Args:
            args: The parsed command-line arguments
            input_media: The input media
            artist: The artist
            title: The title
            filename_pattern: The filename pattern
            log_formatter: The log formatter
            log_level: The log level
            logger: The logger
            
        Returns:
            The project configuration
        """
        return ProjectConfig(
            # Basic inputs
            input_media=input_media,
            artist=artist,
            title=title,
            filename_pattern=filename_pattern,
            
            # Workflow control
            prep_only=args.get("prep_only", False),
            finalise_only=args.get("finalise_only", False),
            skip_transcription=args.get("skip_transcription", False),
            skip_separation=args.get("skip_separation", False),
            skip_lyrics=args.get("skip_lyrics", False),
            lyrics_only=args.get("lyrics_only", False),
            edit_lyrics=args.get("edit_lyrics", False),
            
            # Logging & Debugging
            dry_run=args.get("dry_run", False),
            logger=logger,
            log_level=log_level,
            log_formatter=log_formatter,
            render_bounding_boxes=args.get("render_bounding_boxes", False),
            
            # Input/Output Configuration
            output_dir=args.get("output_dir", "."),
            create_track_subfolders=args.get("no_track_subfolders", True),
            lossless_output_format=args.get("lossless_output_format", "FLAC"),
            output_png=args.get("output_png", True),
            output_jpg=args.get("output_jpg", True),
            
            # Audio Processing Configuration
            clean_instrumental_model=args.get("clean_instrumental_model", "model_bs_roformer_ep_317_sdr_12.9755.ckpt"),
            backing_vocals_models=args.get("backing_vocals_models", ["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"]),
            other_stems_models=args.get("other_stems_models", ["htdemucs_6s.yaml"]),
            model_file_dir=args.get("model_file_dir", os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")),
            existing_instrumental=args.get("existing_instrumental"),
            instrumental_format=args.get("instrumental_format", "flac"),
            
            # Lyrics Configuration
            lyrics_artist=args.get("lyrics_artist"),
            lyrics_title=args.get("lyrics_title"),
            lyrics_file=args.get("lyrics_file"),
            skip_transcription_review=args.get("skip_transcription_review", False),
            subtitle_offset_ms=args.get("subtitle_offset_ms", 0),
            
            # Style Configuration
            style_params_json=args.get("style_params_json"),
            
            # Finalisation Configuration
            enable_cdg=args.get("enable_cdg", False),
            enable_txt=args.get("enable_txt", False),
            brand_prefix=args.get("brand_prefix"),
            organised_dir=args.get("organised_dir"),
            organised_dir_rclone_root=args.get("organised_dir_rclone_root"),
            public_share_dir=args.get("public_share_dir"),
            youtube_client_secrets_file=args.get("youtube_client_secrets_file"),
            youtube_description_file=args.get("youtube_description_file"),
            rclone_destination=args.get("rclone_destination"),
            discord_webhook_url=args.get("discord_webhook_url"),
            email_template_file=args.get("email_template_file"),
            keep_brand_code=args.get("keep_brand_code", False),
            non_interactive=args.get("yes", False),
        )
    
    def _display_results(self, tracks: List[Track], args: Dict[str, Any], logger: logging.Logger) -> None:
        """
        Display the results of processing.
        
        Args:
            tracks: The processed tracks
            args: The parsed command-line arguments
            logger: The logger
        """
        # If prep-only mode, display detailed output
        if args.get("prep_only"):
            logger.info(f"Karaoke Prep complete! Output files:")
            
            for track in tracks:
                logger.info(f"")
                logger.info(f"Track: {track.artist} - {track.title}")
                logger.info(f" Input Media: {track.input_media}")
                logger.info(f" Input WAV Audio: {track.input_audio_wav}")
                logger.info(f" Input Still Image: {track.input_still_image}")
                logger.info(f" Lyrics: {track.lyrics}")
                logger.info(f" Processed Lyrics: {track.processed_lyrics}")
                
                logger.info(f" Separated Audio:")
                
                # Clean Instrumental
                logger.info(f"  Clean Instrumental Model:")
                for stem_type, file_path in track.separated_audio["clean_instrumental"].items():
                    logger.info(f"   {stem_type.capitalize()}: {file_path}")
                
                # Other Stems
                logger.info(f"  Other Stems Models:")
                for model, stems in track.separated_audio["other_stems"].items():
                    logger.info(f"   Model: {model}")
                    for stem_type, file_path in stems.items():
                        logger.info(f"    {stem_type.capitalize()}: {file_path}")
                
                # Backing Vocals
                logger.info(f"  Backing Vocals Models:")
                for model, stems in track.separated_audio["backing_vocals"].items():
                    logger.info(f"   Model: {model}")
                    for stem_type, file_path in stems.items():
                        logger.info(f"    {stem_type.capitalize()}: {file_path}")
                
                # Combined Instrumentals
                logger.info(f"  Combined Instrumentals:")
                for model, file_path in track.separated_audio["combined_instrumentals"].items():
                    logger.info(f"   Model: {model}")
                    logger.info(f"    Combined Instrumental: {file_path}")
            
            logger.info("Preparation phase complete. Exiting due to --prep-only flag.")
            return
        
        # Display summary of outputs for each track
        for track in tracks:
            logger.info(f"Karaoke processing complete! Output files:")
            logger.info(f"")
            logger.info(f"Track: {track.artist} - {track.title}")
            logger.info(f"")
            logger.info(f"Working Files:")
            logger.info(f" Video With Vocals: {track.video_with_vocals}")
            logger.info(f" Video With Instrumental: {track.video_with_instrumental}")
            logger.info(f"")
            logger.info(f"Final Videos:")
            logger.info(f" Lossless 4K MP4 (PCM): {track.final_video}")
            logger.info(f" Lossless 4K MKV (FLAC): {track.final_video_mkv}")
            logger.info(f" Lossy 4K MP4 (AAC): {track.final_video_lossy}")
            logger.info(f" Lossy 720p MP4 (AAC): {track.final_video_720p}")
            
            if track.final_karaoke_cdg_zip or track.final_karaoke_txt_zip:
                logger.info(f"")
                logger.info(f"Karaoke Files:")
            
            if track.final_karaoke_cdg_zip:
                logger.info(f" CDG+MP3 ZIP: {track.final_karaoke_cdg_zip}")
            
            if track.final_karaoke_txt_zip:
                logger.info(f" TXT+MP3 ZIP: {track.final_karaoke_txt_zip}")
            
            if track.brand_code:
                logger.info(f"")
                logger.info(f"Organization:")
                logger.info(f" Brand Code: {track.brand_code}")
                logger.info(f" Directory: {track.new_brand_code_dir_path}")
            
            if track.youtube_url or track.brand_code_dir_sharing_link:
                logger.info(f"")
                logger.info(f"Sharing:")
            
            if track.brand_code_dir_sharing_link:
                logger.info(f" Folder Link: {track.brand_code_dir_sharing_link}")
                try:
                    time.sleep(1)  # Brief pause between clipboard operations
                    pyperclip.copy(track.brand_code_dir_sharing_link)
                    logger.info(f" (Folder link copied to clipboard)")
                except Exception as e:
                    logger.warning(f" Failed to copy folder link to clipboard: {str(e)}")
            
            if track.youtube_url:
                logger.info(f" YouTube URL: {track.youtube_url}")
                try:
                    pyperclip.copy(track.youtube_url)
                    logger.info(f" (YouTube URL copied to clipboard)")
                except Exception as e:
                    logger.warning(f" Failed to copy YouTube URL to clipboard: {str(e)}")


class TestEmailTemplateCommand(Command):
    """Command for testing the email template."""
    
    async def execute(self, args: Dict[str, Any]) -> None:
        """
        Execute the test email template command.
        
        Args:
            args: The parsed command-line arguments
        """
        # Set up logging
        logger = logging.getLogger(__name__)
        log_handler = logging.StreamHandler()
        log_formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        log_handler.setFormatter(log_formatter)
        logger.addHandler(log_handler)
        
        log_level = getattr(logging, args.get("log_level", "INFO").upper())
        logger.setLevel(log_level)
        
        logger.info("Testing email template functionality...")
        
        # Create configuration
        config = ProjectConfig(
            log_formatter=log_formatter,
            log_level=log_level,
            email_template_file=args.get("email_template_file"),
        )
        
        # Create controller
        controller = KaraokeController(config)
        
        # Test email template
        await controller.distribution_service._test_email_template()


def get_command(args: Dict[str, Any]) -> Command:
    """
    Get the appropriate command based on the arguments.
    
    Args:
        args: The parsed command-line arguments
        
    Returns:
        The command to execute
    """
    if args.get("test_email_template"):
        return TestEmailTemplateCommand()
    else:
        return ProcessCommand()


async def execute_command(args: Dict[str, Any]) -> None:
    """
    Execute the appropriate command based on the arguments.
    
    Args:
        args: The parsed command-line arguments
    """
    command = get_command(args)
    await command.execute(args)
