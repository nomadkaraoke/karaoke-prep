import os
import asyncio
import re
import yt_dlp
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import DownloadError


class MediaDownloader:
    """
    Handles downloading media from URLs.
    """
    
    def __init__(self, config):
        """
        Initialize the media downloader.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
    
    async def download_media(self, track):
        """
        Download media from a URL.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Downloading media from {track.input_media}")
        
        if not track.is_url:
            self.logger.warning(f"Input media is not a URL: {track.input_media}")
            return track
        
        try:
            # Extract info for online media
            track = await self._extract_info_for_online_media(track)
            
            # Download the video
            output_filename_no_extension = os.path.join(
                track.track_output_dir, 
                self._sanitize_filename(track.base_name)
            )
            
            downloaded_file = await self._download_video(track.input_media, output_filename_no_extension)
            
            # Update track information
            track.input_media = downloaded_file
            
            return track
            
        except Exception as e:
            raise DownloadError(f"Failed to download media: {str(e)}") from e
    
    async def _extract_info_for_online_media(self, track):
        """
        Extract information for online media.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated information
        """
        self.logger.info(f"Extracting info for online media: {track.input_media}")
        
        # Skip if artist and title are already provided
        if track.artist and track.title:
            self.logger.info(f"Using provided artist: {track.artist} and title: {track.title}")
            return track
        
        # Extract info from URL
        try:
            ydl_opts = {
                "quiet": True,
                "no_warnings": True,
                "extract_flat": "in_playlist",
                "skip_download": True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl_instance:
                info = ydl_instance.extract_info(track.input_media, download=False)
                
                # Handle playlists
                if "entries" in info:
                    # Get the first video in the playlist
                    if not info["entries"]:
                        raise DownloadError("Playlist is empty")
                    
                    info = info["entries"][0]
                
                # Extract artist and title
                if not track.artist or not track.title:
                    artist, title = self._parse_video_title(info.get("title", ""))
                    
                    if not track.artist:
                        track.artist = artist
                    
                    if not track.title:
                        track.title = title
                
                self.logger.info(f"Extracted artist: {track.artist} and title: {track.title}")
                
                return track
                
        except Exception as e:
            raise DownloadError(f"Failed to extract info for online media: {str(e)}") from e
    
    async def _download_video(self, url, output_filename_no_extension):
        """
        Download a video from a URL.
        
        Args:
            url: The URL to download from
            output_filename_no_extension: The output filename without extension
            
        Returns:
            The path to the downloaded file
        """
        self.logger.info(f"Downloading video from {url}")
        
        # Define output template
        output_template = f"{output_filename_no_extension}.%(ext)s"
        
        # Set up yt-dlp options
        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": output_template,
            "quiet": self.config.log_level > 10,  # Only show output if log level is DEBUG
            "no_warnings": self.config.log_level > 10,
            "ignoreerrors": False,
            "noplaylist": True,
        }
        
        if self.config.dry_run:
            self.logger.info(f"[DRY RUN] Would download video from {url} to {output_template}")
            return f"{output_filename_no_extension}.mp4"
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl_instance:
                info = ydl_instance.extract_info(url, download=True)
                
                # Get the downloaded file path
                if info and "requested_downloads" in info:
                    for download in info["requested_downloads"]:
                        if "filepath" in download:
                            downloaded_file = download["filepath"]
                            self.logger.info(f"Successfully downloaded video: {downloaded_file}")
                            return downloaded_file
                
                # Fallback: try to guess the file path
                extensions = ["mp4", "webm", "mkv", "m4a", "mp3"]
                for ext in extensions:
                    possible_path = f"{output_filename_no_extension}.{ext}"
                    if os.path.isfile(possible_path):
                        self.logger.info(f"Found downloaded file: {possible_path}")
                        return possible_path
                
                raise DownloadError("Failed to determine downloaded file path")
                
        except Exception as e:
            raise DownloadError(f"Failed to download video: {str(e)}") from e
    
    def _parse_video_title(self, video_title):
        """
        Parse artist and title from a video title.
        
        Args:
            video_title: The video title
            
        Returns:
            Tuple of (artist, title)
        """
        self.logger.debug(f"Parsing video title: {video_title}")
        
        # Try to match "Artist - Title" pattern
        match = re.search(r"(.+?)\s*[-–—]\s*(.+)", video_title)
        if match:
            artist = match.group(1).strip()
            title = match.group(2).strip()
            
            # Clean up title (remove things like "Official Video", etc.)
            title = re.sub(r"\(Official\s+Video\)", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"\(Official\s+Music\s+Video\)", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"\(Official\s+Lyric\s+Video\)", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"\(Lyric\s+Video\)", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"\(Audio\)", "", title, flags=re.IGNORECASE).strip()
            title = re.sub(r"\(Official\s+Audio\)", "", title, flags=re.IGNORECASE).strip()
            
            return artist, title
        
        # If no match, use the whole title as both artist and title
        return video_title, video_title
    
    def _sanitize_filename(self, filename):
        """
        Sanitize a filename by removing invalid characters.
        
        Args:
            filename: The filename to sanitize
            
        Returns:
            The sanitized filename
        """
        # Replace characters that are invalid in filenames
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename 