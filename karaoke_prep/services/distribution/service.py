from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import DistributionError, YouTubeError

from karaoke_prep.services.distribution.youtube import YouTubeUploader
from karaoke_prep.services.distribution.organizer import FileOrganizer
from karaoke_prep.services.distribution.cdg import CDGGenerator
from karaoke_prep.services.distribution.txt import TXTGenerator
from karaoke_prep.services.distribution.notifier import Notifier

import logging
import os
import asyncio
import shutil
import glob
import re
import subprocess
from typing import Dict, Any, Optional, List, Tuple


class DistributionService:
    """
    Service for distribution operations including file organization, YouTube uploading, and notifications.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the distribution service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        
        # Initialize components
        self.youtube_uploader = YouTubeUploader(config)
        self.file_organizer = FileOrganizer(config)
        self.cdg_generator = CDGGenerator(config)
        self.txt_generator = TXTGenerator(config)
        self.notifier = Notifier(config)
        
        # Detect best available AAC codec
        self.aac_codec = self._detect_best_aac_codec()
    
    async def distribute(self, track: Track, replace_existing: bool = False) -> Track:
        """
        Distribute the track.
        
        Args:
            track: The track to process
            replace_existing: Whether to replace existing files
            
        Returns:
            The track with updated distribution information
        """
        self.logger.info(f"Distributing {track.base_name}")
        
        # Remux and encode output video files
        track = await self._remux_and_encode_output_video_files(track)
        
        # Create CDG zip file if enabled
        if self.config.enable_cdg:
            track = self.cdg_generator.create_cdg_zip_file(track)
        
        # Create TXT zip file if enabled
        if self.config.enable_txt:
            track = self.txt_generator.create_txt_zip_file(track)
        
        # Get brand code
        if self.config.keep_brand_code:
            track.brand_code = self.file_organizer.get_existing_brand_code(track)
        else:
            track.brand_code = self.file_organizer.get_next_brand_code()
        
        # Move files to brand code folder
        if track.brand_code and self.config.organised_dir:
            track = self.file_organizer.move_files_to_brand_code_folder(track, track.brand_code)
        
        # Copy final files to public share directory
        if self.config.public_share_dir and track.brand_code:
            track = self.file_organizer.copy_final_files_to_public_share_dirs(track, track.brand_code)
        
        # Sync public share directory to rclone destination
        if self.config.rclone_destination and self.config.public_share_dir:
            self.file_organizer.sync_public_share_dir_to_rclone_destination()
        
        # Upload to YouTube
        if self.config.youtube_client_secrets_file and track.final_video_mkv:
            thumbnail_file = os.path.join(track.track_output_dir, f"{track.base_name} (Title).jpg")
            if not os.path.isfile(thumbnail_file):
                thumbnail_file = None
            
            track.youtube_url = self.youtube_uploader.upload_video(
                video_file=track.final_video_mkv,
                thumbnail_file=thumbnail_file,
                artist=track.artist,
                title=track.title,
                replace_existing=replace_existing
            )
        
        # Generate sharing link
        if self.config.organised_dir_rclone_root and track.brand_code and track.new_brand_code_dir_path:
            track.brand_code_dir_sharing_link = self.file_organizer.generate_organised_folder_sharing_link(track)
        
        # Post Discord notification
        if self.config.discord_webhook_url and track.youtube_url:
            self.notifier.post_discord_notification(track)
        
        # Draft completion email
        if self.config.email_template_file and track.youtube_url and track.brand_code_dir_sharing_link:
            self.notifier.draft_completion_email(track)
        
        return track
    
    async def _remux_and_encode_output_video_files(self, track: Track) -> Track:
        """
        Remux and encode output video files.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video file information
        """
        self.logger.info(f"Remuxing and encoding output video files for {track.base_name}")
        
        if not track.video_with_lyrics or not track.instrumental:
            self.logger.warning("No video with lyrics or instrumental audio available, cannot remux/encode")
            return track
        
        # Determine output file paths
        final_video = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke Lossless 4k).mp4")
        final_video_mkv = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke Lossless 4k).mkv")
        final_video_lossy = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke Lossy 4k).mp4")
        final_video_720p = os.path.join(track.track_output_dir, f"{track.base_name} (Final Karaoke Lossy 720p).mp4")
        
        # Check if output files already exist
        if os.path.isfile(final_video) and os.path.isfile(final_video_mkv):
            if self.config.non_interactive:
                self.logger.info(f"Non-interactive mode, automatically overwriting existing final video files")
            else:
                from karaoke_prep.utils.validation import prompt_user_bool
                if not prompt_user_bool(
                    f"Found existing Final Karaoke output files. Overwrite (y) or skip (n)?",
                ):
                    self.logger.info(f"Skipping Karaoke MP4 remux and Final video renders, existing files will be used.")
                    track.final_video = final_video
                    track.final_video_mkv = final_video_mkv
                    track.final_video_lossy = final_video_lossy
                    track.final_video_720p = final_video_720p
                    return track
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would remux and encode output video files")
            track.final_video = final_video
            track.final_video_mkv = final_video_mkv
            track.final_video_lossy = final_video_lossy
            track.final_video_720p = final_video_720p
            return track
        
        try:
            # MP4 output flags for better compatibility and streaming
            mp4_flags = "-pix_fmt yuv420p -movflags +faststart+frag_keyframe+empty_moov"
            
            # Path to ffmpeg
            ffmpeg_path = "ffmpeg"
            
            # Base ffmpeg command
            ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"
            
            if self.logger.level == logging.DEBUG:
                ffmpeg_base_command += " -loglevel verbose"
            else:
                ffmpeg_base_command += " -loglevel fatal"
            
            # Add -y if non-interactive
            if self.config.non_interactive:
                ffmpeg_base_command += " -y"
            
            # Create karaoke version with instrumental audio
            karaoke_mp4 = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).mp4")
            
            # Remux the video with instrumental audio
            remux_command = (
                f'{ffmpeg_base_command} -an -i "{track.video_with_lyrics}" '
                f'-vn -i "{track.instrumental}" -c:v copy -c:a pcm_s16le "{karaoke_mp4}"'
            )
            
            self.logger.info(f"Remuxing video with instrumental audio: {remux_command}")
            process = await asyncio.create_subprocess_shell(
                remux_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Prepare title and end videos
            title_video = os.path.join(track.track_output_dir, f"{track.base_name} (Title).mov")
            end_video = os.path.join(track.track_output_dir, f"{track.base_name} (End).mov")
            
            # Prepare concat filter for combining videos
            env_mov_input = ""
            ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0]concat=n=2:v=1:a=1[outv][outa]"'
            
            if os.path.isfile(end_video):
                self.logger.info(f"Found end video: {end_video}, including in final MP4")
                env_mov_input = f'-i "{end_video}"'
                ffmpeg_filter = '-filter_complex "[0:v:0][0:a:0][1:v:0][1:a:0][2:v:0][2:a:0]concat=n=3:v=1:a=1[outv][outa]"'
            
            # Create lossless MP4
            lossless_mp4_command = (
                f'{ffmpeg_base_command} -i "{title_video}" -i "{karaoke_mp4}" {env_mov_input} '
                f'{ffmpeg_filter} -map "[outv]" -map "[outa]" -c:v libx264 -c:a pcm_s16le '
                f'{mp4_flags} "{final_video}"'
            )
            
            self.logger.info(f"Creating MP4 version with PCM audio: {lossless_mp4_command}")
            process = await asyncio.create_subprocess_shell(
                lossless_mp4_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Create lossy MP4
            lossy_mp4_command = (
                f'{ffmpeg_base_command} -i "{final_video}" '
                f'-c:v copy -c:a {self.aac_codec} -b:a 320k {mp4_flags} "{final_video_lossy}"'
            )
            
            self.logger.info(f"Creating MP4 version with AAC audio: {lossy_mp4_command}")
            process = await asyncio.create_subprocess_shell(
                lossy_mp4_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Create MKV with FLAC audio
            mkv_command = (
                f'{ffmpeg_base_command} -i "{final_video}" '
                f'-c:v copy -c:a flac "{final_video_mkv}"'
            )
            
            self.logger.info(f"Creating MKV version with FLAC audio: {mkv_command}")
            process = await asyncio.create_subprocess_shell(
                mkv_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Create 720p MP4
            mp4_720p_command = (
                f'{ffmpeg_base_command} -i "{final_video}" '
                f'-c:v libx264 -vf "scale=1280:720" -b:v 200k -preset medium -tune animation '
                f'-c:a {self.aac_codec} -b:a 128k {mp4_flags} "{final_video_720p}"'
            )
            
            self.logger.info(f"Creating 720p version: {mp4_720p_command}")
            process = await asyncio.create_subprocess_shell(
                mp4_720p_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            # Update track with file paths
            track.final_video = final_video
            track.final_video_mkv = final_video_mkv
            track.final_video_lossy = final_video_lossy
            track.final_video_720p = final_video_720p
            
            return track
        
        except Exception as e:
            self.logger.error(f"Failed to remux and encode output video files: {str(e)}")
            raise DistributionError(f"Failed to remux and encode output video files: {str(e)}")
    
    def _detect_best_aac_codec(self) -> str:
        """
        Detect the best available AAC codec (aac_at > libfdk_aac > aac).
        
        Returns:
            The best available AAC codec
        """
        self.logger.info("Detecting best available AAC codec...")
        
        if self.config.dry_run:
            self.logger.info("DRY RUN: Would detect best available AAC codec")
            return "aac"
        
        try:
            # Run ffmpeg -codecs to get available codecs
            codec_check_command = "ffmpeg -codecs"
            result = subprocess.run(codec_check_command, shell=True, capture_output=True, text=True)
            output = result.stdout
            
            if "aac_at" in output:
                self.logger.info("Using aac_at codec (best quality)")
                return "aac_at"
            elif "libfdk_aac" in output:
                self.logger.info("Using libfdk_aac codec (good quality)")
                return "libfdk_aac"
            else:
                self.logger.info("Using built-in aac codec (basic quality)")
                return "aac"
        
        except Exception as e:
            self.logger.error(f"Failed to detect best AAC codec: {str(e)}")
            return "aac"
