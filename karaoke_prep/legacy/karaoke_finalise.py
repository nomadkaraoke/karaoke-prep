"""
Legacy compatibility wrapper for the KaraokeFinalise class.
"""

import logging
import os
import asyncio
from typing import Dict, Any, Optional

from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.controller import KaraokeController


class KaraokeFinalise:
    """
    Legacy compatibility wrapper for the KaraokeFinalise class.
    This class maintains backward compatibility with existing code that uses the old KaraokeFinalise class.
    """
    
    def __init__(
        self,
        logger=None,
        log_level=logging.DEBUG,
        log_formatter=None,
        dry_run=False,
        instrumental_format="flac",
        enable_cdg=False,
        enable_txt=False,
        brand_prefix=None,
        organised_dir=None,
        organised_dir_rclone_root=None,
        public_share_dir=None,
        youtube_client_secrets_file=None,
        youtube_description_file=None,
        rclone_destination=None,
        discord_webhook_url=None,
        email_template_file=None,
        cdg_styles=None,
        keep_brand_code=False,
        non_interactive=False,
    ):
        """
        Initialize the KaraokeFinalise wrapper.
        
        Args:
            logger: The logger
            log_level: The log level
            log_formatter: The log formatter
            dry_run: Whether to perform a dry run
            instrumental_format: The instrumental format
            enable_cdg: Whether to enable CDG generation
            enable_txt: Whether to enable TXT generation
            brand_prefix: The brand prefix
            organised_dir: The organised directory
            organised_dir_rclone_root: The organised directory rclone root
            public_share_dir: The public share directory
            youtube_client_secrets_file: The YouTube client secrets file
            youtube_description_file: The YouTube description file
            rclone_destination: The rclone destination
            discord_webhook_url: The Discord webhook URL
            email_template_file: The email template file
            cdg_styles: The CDG styles
            keep_brand_code: Whether to keep the brand code
            non_interactive: Whether to run in non-interactive mode
        """
        # Create configuration
        self.config = ProjectConfig(
            # Workflow control
            prep_only=False,
            finalise_only=True,  # Legacy KaraokeFinalise only does finalisation
            
            # Logging & Debugging
            dry_run=dry_run,
            logger=logger,
            log_level=log_level,
            log_formatter=log_formatter,
            
            # Audio Processing Configuration
            instrumental_format=instrumental_format,
            
            # Finalisation Configuration
            enable_cdg=enable_cdg,
            enable_txt=enable_txt,
            brand_prefix=brand_prefix,
            organised_dir=organised_dir,
            organised_dir_rclone_root=organised_dir_rclone_root,
            public_share_dir=public_share_dir,
            youtube_client_secrets_file=youtube_client_secrets_file,
            youtube_description_file=youtube_description_file,
            rclone_destination=rclone_destination,
            discord_webhook_url=discord_webhook_url,
            email_template_file=email_template_file,
            cdg_styles=cdg_styles,
            keep_brand_code=keep_brand_code,
            non_interactive=non_interactive,
        )
        
        # Create controller
        self.controller = KaraokeController(self.config)
    
    def process(self, replace_existing=False) -> Dict[str, Any]:
        """
        Process the track.
        
        Args:
            replace_existing: Whether to replace existing files
            
        Returns:
            The processed track in the legacy format
        """
        # Process track
        tracks = asyncio.run(self.controller.process())
        
        # Convert to legacy format
        if tracks:
            return self._convert_to_legacy_format(tracks[0])
        else:
            return {}
    
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
            "video_with_vocals": track.video_with_vocals,
            "video_with_instrumental": track.video_with_instrumental,
            "final_video": track.final_video,
            "final_video_mkv": track.final_video_mkv,
            "final_video_lossy": track.final_video_lossy,
            "final_video_720p": track.final_video_720p,
            "final_karaoke_cdg_zip": track.final_karaoke_cdg_zip,
            "final_karaoke_txt_zip": track.final_karaoke_txt_zip,
            "brand_code": track.brand_code,
            "new_brand_code_dir_path": track.new_brand_code_dir_path,
            "youtube_url": track.youtube_url,
            "brand_code_dir_sharing_link": track.brand_code_dir_sharing_link,
        }
    
    def test_email_template(self) -> None:
        """
        Test the email template.
        """
        asyncio.run(self.controller.distribution_service._test_email_template()) 