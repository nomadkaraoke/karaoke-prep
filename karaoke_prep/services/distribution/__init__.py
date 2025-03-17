from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import DistributionError, YouTubeError

import logging
import os
import asyncio
import shutil
import glob
import re
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
            track = await self._create_cdg_zip_file(track)
        
        # Create TXT zip file if enabled
        if self.config.enable_txt:
            track = await self._create_txt_zip_file(track)
        
        # Get brand code
        if self.config.keep_brand_code:
            brand_code = await self._get_existing_brand_code(track)
        else:
            brand_code = await self._get_next_brand_code()
        
        track.brand_code = brand_code
        
        # Move files to brand code folder
        if brand_code:
            track = await self._move_files_to_brand_code_folder(track)
        
        # Copy final files to public share directory
        if self.config.public_share_dir:
            track = await self._copy_final_files_to_public_share_dirs(track)
        
        # Sync public share directory to rclone destination
        if self.config.rclone_destination:
            await self._sync_public_share_dir_to_rclone_destination()
        
        # Upload to YouTube
        if self.config.youtube_client_secrets_file:
            track = await self._upload_to_youtube(track, replace_existing)
        
        # Post Discord notification
        if self.config.discord_webhook_url:
            await self._post_discord_notification(track)
        
        # Generate sharing link
        if self.config.organised_dir_rclone_root:
            track.brand_code_dir_sharing_link = await self._generate_organised_folder_sharing_link(track)
        
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
        
        if not track.final_video:
            self.logger.warning("No final video to remux/encode")
            return track
        
        # Create MKV version
        if not self.config.dry_run:
            mkv_output = track.final_video.replace(".mp4", ".mkv")
            await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", track.final_video,
                "-c", "copy", mkv_output,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            track.final_video_mkv = mkv_output
        
        # Create lossy version
        if not self.config.dry_run:
            lossy_output = track.final_video.replace(".mp4", "_lossy.mp4")
            await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", track.final_video,
                "-c:v", "libx264", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                lossy_output,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            track.final_video_lossy = lossy_output
        
        # Create 720p version
        if not self.config.dry_run:
            output_720p = track.final_video.replace(".mp4", "_720p.mp4")
            await asyncio.create_subprocess_exec(
                "ffmpeg", "-i", track.final_video,
                "-vf", "scale=-1:720",
                "-c:v", "libx264", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                output_720p,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            track.final_video_720p = output_720p
        
        return track
    
    async def _create_cdg_zip_file(self, track: Track) -> Track:
        """
        Create a CDG zip file for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated CDG zip file information
        """
        self.logger.info(f"Creating CDG zip file for {track.base_name}")
        
        if not self.config.enable_cdg:
            return track
        
        if not self.config.dry_run:
            # Create CDG files using the configured styles
            cdg_dir = os.path.join(track.track_output_dir, "cdg")
            os.makedirs(cdg_dir, exist_ok=True)
            
            # Apply each CDG style
            for style_name, style_params in (self.config.cdg_styles or {}).items():
                cdg_file = os.path.join(cdg_dir, f"{track.base_name}_{style_name}.cdg")
                mp3_file = os.path.join(cdg_dir, f"{track.base_name}_{style_name}.mp3")
                
                # Convert instrumental to MP3 for CDG
                await asyncio.create_subprocess_exec(
                    "ffmpeg", "-i", track.instrumental_file,
                    "-c:a", "libmp3lame", "-b:a", "320k",
                    mp3_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                # Generate CDG file using style parameters
                # TODO: Implement actual CDG generation with style parameters
                # For now, create a placeholder CDG file
                with open(cdg_file, "wb") as f:
                    f.write(b"CDG")
            
            # Create zip file containing all CDG files
            zip_file = os.path.join(track.track_output_dir, f"{track.base_name}_cdg.zip")
            shutil.make_archive(
                os.path.splitext(zip_file)[0],
                "zip",
                cdg_dir
            )
            track.final_karaoke_cdg_zip = zip_file
            
            # Clean up temporary CDG directory
            shutil.rmtree(cdg_dir)
        
        return track
    
    async def _create_txt_zip_file(self, track: Track) -> Track:
        """
        Create a TXT zip file for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated TXT zip file information
        """
        self.logger.info(f"Creating TXT zip file for {track.base_name}")
        
        if not self.config.enable_txt:
            return track
        
        if not self.config.dry_run:
            # Create TXT files directory
            txt_dir = os.path.join(track.track_output_dir, "txt")
            os.makedirs(txt_dir, exist_ok=True)
            
            # Create TXT file with lyrics
            txt_file = os.path.join(txt_dir, f"{track.base_name}.txt")
            with open(txt_file, "w", encoding="utf-8") as f:
                f.write(f"{track.artist} - {track.title}\n\n")
                if hasattr(track, "lyrics") and track.lyrics:
                    f.write(track.lyrics)
                else:
                    f.write("No lyrics available")
            
            # Create zip file containing all TXT files
            zip_file = os.path.join(track.track_output_dir, f"{track.base_name}_txt.zip")
            shutil.make_archive(
                os.path.splitext(zip_file)[0],
                "zip",
                txt_dir
            )
            track.final_karaoke_txt_zip = zip_file
            
            # Clean up temporary TXT directory
            shutil.rmtree(txt_dir)
        
        return track
    
    async def _get_next_brand_code(self) -> str:
        """
        Get the next brand code.
        
        Returns:
            The next brand code
        """
        if not self.config.brand_prefix:
            return None
        
        self.logger.info(f"Getting next brand code for prefix {self.config.brand_prefix}")
        
        # Get all existing brand codes
        organised_dir = self.config.organised_dir or "."
        pattern = os.path.join(organised_dir, f"{self.config.brand_prefix}-*")
        existing_codes = []
        
        for path in glob.glob(pattern):
            if os.path.isdir(path):
                code_match = re.match(rf"{self.config.brand_prefix}-(\d+)", os.path.basename(path))
                if code_match:
                    existing_codes.append(int(code_match.group(1)))
        
        # Get the next number
        next_number = 1
        if existing_codes:
            next_number = max(existing_codes) + 1
        
        # Format with leading zeros
        return f"{self.config.brand_prefix}-{next_number:04d}"
    
    async def _get_existing_brand_code(self, track: Track) -> str:
        """
        Get the existing brand code from the current directory.
        
        Args:
            track: The track to process
            
        Returns:
            The existing brand code
        """
        if not self.config.brand_prefix:
            return None
        
        self.logger.info("Getting existing brand code from current directory")
        
        # Get the current directory name
        current_dir = os.path.basename(track.track_output_dir)
        
        # Extract brand code from directory name
        # Format: "BRAND-XXXX - Artist - Title"
        match = re.match(rf"({self.config.brand_prefix}-\d+) - ", current_dir)
        if match:
            return match.group(1)
        
        return None
    
    async def _move_files_to_brand_code_folder(self, track: Track) -> Track:
        """
        Move files to the brand code folder.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated file paths
        """
        if not track.brand_code:
            return track
        
        self.logger.info(f"Moving files to brand code folder {track.brand_code}")
        
        # Create the brand code folder name
        brand_code_dir_name = f"{track.brand_code} - {track.artist} - {track.title}"
        brand_code_dir_path = os.path.join(self.config.organised_dir or os.path.dirname(track.track_output_dir), brand_code_dir_name)
        
        # Create the directory if it doesn't exist
        if not os.path.exists(brand_code_dir_path) and not self.config.dry_run:
            os.makedirs(brand_code_dir_path, exist_ok=True)
        
        if not self.config.dry_run:
            # Move all final files to the brand code folder
            files_to_move = [
                track.final_video,
                track.final_video_mkv,
                track.final_video_lossy,
                track.final_video_720p,
                track.final_karaoke_cdg_zip,
                track.final_karaoke_txt_zip
            ]
            
            for file_path in files_to_move:
                if file_path and os.path.exists(file_path):
                    new_path = os.path.join(brand_code_dir_path, os.path.basename(file_path))
                    shutil.move(file_path, new_path)
                    
                    # Update the track's file paths
                    if file_path == track.final_video:
                        track.final_video = new_path
                    elif file_path == track.final_video_mkv:
                        track.final_video_mkv = new_path
                    elif file_path == track.final_video_lossy:
                        track.final_video_lossy = new_path
                    elif file_path == track.final_video_720p:
                        track.final_video_720p = new_path
                    elif file_path == track.final_karaoke_cdg_zip:
                        track.final_karaoke_cdg_zip = new_path
                    elif file_path == track.final_karaoke_txt_zip:
                        track.final_karaoke_txt_zip = new_path
        
        track.new_brand_code_dir_path = brand_code_dir_path
        return track
    
    async def _copy_final_files_to_public_share_dirs(self, track: Track) -> Track:
        """
        Copy final files to public share directories.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated file paths
        """
        if not self.config.public_share_dir or not track.brand_code:
            return track
        
        self.logger.info(f"Copying final files to public share directory {self.config.public_share_dir}")
        
        if not self.config.dry_run:
            # Create brand code directory in public share
            public_brand_code_dir = os.path.join(self.config.public_share_dir, track.brand_code)
            os.makedirs(public_brand_code_dir, exist_ok=True)
            
            # Copy all final files
            files_to_copy = [
                track.final_video_lossy,
                track.final_video_720p,
                track.final_karaoke_cdg_zip,
                track.final_karaoke_txt_zip
            ]
            
            for file_path in files_to_copy:
                if file_path and os.path.exists(file_path):
                    shutil.copy2(file_path, public_brand_code_dir)
        
        return track
    
    async def _sync_public_share_dir_to_rclone_destination(self) -> None:
        """
        Sync public share directory to rclone destination.
        """
        if not self.config.rclone_destination or not self.config.public_share_dir:
            return
        
        self.logger.info(f"Syncing public share directory to rclone destination {self.config.rclone_destination}")
        
        if not self.config.dry_run:
            try:
                # Run rclone sync command
                process = await asyncio.create_subprocess_exec(
                    "rclone", "sync",
                    self.config.public_share_dir,
                    self.config.rclone_destination,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    raise DistributionError(f"rclone sync failed: {error_msg}")
                
            except Exception as e:
                self.logger.error(f"Failed to sync to rclone destination: {str(e)}")
                raise DistributionError(f"Failed to sync to rclone destination: {str(e)}")
    
    async def _upload_to_youtube(self, track: Track, replace_existing: bool = False) -> Track:
        """
        Upload the track to YouTube.
        
        Args:
            track: The track to process
            replace_existing: Whether to replace an existing video
            
        Returns:
            The track with updated YouTube information
        """
        if not self.config.youtube_client_secrets_file:
            return track
        
        self.logger.info(f"Uploading {track.base_name} to YouTube")
        
        if not self.config.dry_run:
            try:
                from google_auth_oauthlib.flow import InstalledAppFlow
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                from googleapiclient.http import MediaFileUpload
                
                # OAuth 2.0 scopes needed for the YouTube Data API
                SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
                
                # Load client secrets
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.config.youtube_client_secrets_file, SCOPES)
                credentials = flow.run_local_server(port=0)
                
                # Build the YouTube API service
                youtube = build('youtube', 'v3', credentials=credentials)
                
                # Prepare video metadata
                video_metadata = {
                    'snippet': {
                        'title': f"{track.artist} - {track.title} (Karaoke Version)",
                        'description': "Karaoke version",  # Can be customized from template file
                        'tags': ['karaoke', track.artist, track.title],
                        'categoryId': '10'  # Music category
                    },
                    'status': {
                        'privacyStatus': 'private',  # Start as private
                        'selfDeclaredMadeForKids': False
                    }
                }
                
                # Load custom description if available
                if self.config.youtube_description_file and os.path.exists(self.config.youtube_description_file):
                    with open(self.config.youtube_description_file, 'r', encoding='utf-8') as f:
                        video_metadata['snippet']['description'] = f.read().format(
                            artist=track.artist,
                            title=track.title
                        )
                
                # Upload the video
                media = MediaFileUpload(
                    track.final_video_720p or track.final_video,
                    mimetype='video/mp4',
                    resumable=True
                )
                
                request = youtube.videos().insert(
                    part=','.join(video_metadata.keys()),
                    body=video_metadata,
                    media_body=media
                )
                
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        self.logger.info(f"Uploaded {int(status.progress() * 100)}%")
                
                track.youtube_url = f"https://www.youtube.com/watch?v={response['id']}"
                self.logger.info(f"Video uploaded successfully: {track.youtube_url}")
                
            except Exception as e:
                self.logger.error(f"Failed to upload to YouTube: {str(e)}")
                raise YouTubeError(f"Failed to upload to YouTube: {str(e)}")
        
        return track
    
    async def _post_discord_notification(self, track: Track) -> None:
        """
        Post a notification to Discord.
        
        Args:
            track: The track to process
        """
        if not self.config.discord_webhook_url:
            return
        
        self.logger.info("Posting notification to Discord")
        
        if not self.config.dry_run:
            try:
                import aiohttp
                
                # Prepare the embed
                embed = {
                    "title": f"{track.artist} - {track.title}",
                    "description": "New karaoke track available!",
                    "color": 0x00ff00,  # Green color
                    "fields": [
                        {
                            "name": "Brand Code",
                            "value": track.brand_code or "N/A",
                            "inline": True
                        }
                    ]
                }
                
                # Add YouTube link if available
                if track.youtube_url:
                    embed["fields"].append({
                        "name": "YouTube",
                        "value": track.youtube_url,
                        "inline": True
                    })
                
                # Add sharing link if available
                if track.brand_code_dir_sharing_link:
                    embed["fields"].append({
                        "name": "Download",
                        "value": track.brand_code_dir_sharing_link,
                        "inline": True
                    })
                
                # Prepare the webhook payload
                payload = {
                    "embeds": [embed]
                }
                
                # Send the webhook
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.config.discord_webhook_url, json=payload) as response:
                        if response.status != 204:
                            error_text = await response.text()
                            raise DistributionError(f"Discord webhook failed with status {response.status}: {error_text}")
                
                self.logger.info("Discord notification sent successfully")
                
            except Exception as e:
                self.logger.error(f"Failed to post Discord notification: {str(e)}")
                raise DistributionError(f"Failed to post Discord notification: {str(e)}")
    
    async def _generate_organised_folder_sharing_link(self, track: Track) -> str:
        """
        Generate a sharing link for the organised folder.
        
        Args:
            track: The track to process
            
        Returns:
            The sharing link
        """
        if not self.config.organised_dir_rclone_root or not track.brand_code:
            return None
        
        self.logger.info("Generating sharing link for organised folder")
        
        if not self.config.dry_run:
            try:
                # Get the relative path from the organised directory to the brand code directory
                rel_path = os.path.relpath(track.new_brand_code_dir_path, self.config.organised_dir)
                
                # Combine with the rclone root to form the sharing URL
                sharing_link = f"{self.config.organised_dir_rclone_root.rstrip('/')}/{rel_path}"
                
                return sharing_link
                
            except Exception as e:
                self.logger.error(f"Failed to generate sharing link: {str(e)}")
                raise DistributionError(f"Failed to generate sharing link: {str(e)}")
        
        return None
