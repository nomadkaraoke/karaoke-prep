from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import MediaError, DownloadError, ConversionError

import logging
import os
import asyncio
import shutil
import glob
import sys
import yt_dlp.YoutubeDL as ydl
from typing import Dict, Any, Optional, Tuple


class MediaService:
    """
    Service for media handling operations including downloading, extraction, and conversion.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the media service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        
        # Set up ffmpeg command
        ffmpeg_path = os.path.join(sys._MEIPASS, "ffmpeg.exe") if getattr(sys, "frozen", False) else "ffmpeg"
        self.ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"
        
        if self.config.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"
    
    async def download_media(self, track: Track) -> Track:
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
            output_filename_no_extension = os.path.join(track.track_output_dir, self._sanitize_filename(track.base_name))
            downloaded_file = await self._download_video(track.input_media, output_filename_no_extension)
            
            # Extract still image from video
            still_image = await self._extract_still_image_from_video(downloaded_file, output_filename_no_extension)
            
            # Convert to WAV
            audio_wav = await self._convert_to_wav(downloaded_file, output_filename_no_extension)
            
            # Update track information
            track.input_media = downloaded_file
            track.input_still_image = still_image
            track.input_audio_wav = audio_wav
            
            return track
        except Exception as e:
            raise DownloadError(f"Failed to download media: {str(e)}") from e
    
    async def prepare_media(self, track: Track) -> Track:
        """
        Prepare media from a local file.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated media information
        """
        self.logger.info(f"Preparing media from {track.input_media}")
        
        if not track.is_file:
            self.logger.warning(f"Input media is not a file: {track.input_media}")
            return track
        
        try:
            # Copy input media to output directory
            output_filename_no_extension = os.path.join(track.track_output_dir, self._sanitize_filename(track.base_name))
            copied_file = await self._copy_input_media(track.input_media, output_filename_no_extension)
            
            # Extract still image from video
            still_image = await self._extract_still_image_from_video(copied_file, output_filename_no_extension)
            
            # Convert to WAV
            audio_wav = await self._convert_to_wav(copied_file, output_filename_no_extension)
            
            # Update track information
            track.input_media = copied_file
            track.input_still_image = still_image
            track.input_audio_wav = audio_wav
            
            return track
        except Exception as e:
            raise MediaError(f"Failed to prepare media: {str(e)}") from e
    
    async def _extract_info_for_online_media(self, track: Track) -> Track:
        """
        Extract information for online media.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated information
        """
        self.logger.info(f"Extracting info for online media: {track.input_media}")
        
        try:
            if track.input_media is not None:
                # If a URL is provided, use it to extract the metadata
                with ydl({"quiet": True}) as ydl_instance:
                    track.metadata["extracted_info"] = ydl_instance.extract_info(track.input_media, download=False)
            else:
                # If no URL is provided, use the query to search for the top result
                ydl_opts = {"quiet": "True", "format": "bestaudio", "noplaylist": "True", "extract_flat": True}
                with ydl(ydl_opts) as ydl_instance:
                    query = f"{track.artist} {track.title}"
                    track.metadata["extracted_info"] = ydl_instance.extract_info(f"ytsearch1:{query}", download=False)["entries"][0]
                    if not track.metadata["extracted_info"]:
                        raise DownloadError(f"No search results found on YouTube for query: {track.artist} {track.title}")
            
            # Extract URL, extractor, and ID
            if "url" in track.metadata["extracted_info"]:
                track.input_media = track.metadata["extracted_info"]["url"]
            elif "webpage_url" in track.metadata["extracted_info"]:
                track.input_media = track.metadata["extracted_info"]["webpage_url"]
            else:
                raise DownloadError(f"Failed to extract URL from input media metadata")
            
            # Extract artist and title if not provided
            if not track.artist or not track.title:
                if "title" in track.metadata["extracted_info"] and "-" in track.metadata["extracted_info"]["title"]:
                    artist, title = track.metadata["extracted_info"]["title"].split("-", 1)
                    if not track.artist:
                        track.artist = artist.strip()
                    if not track.title:
                        track.title = title.strip()
                elif "uploader" in track.metadata["extracted_info"]:
                    if not track.artist:
                        track.artist = track.metadata["extracted_info"]["uploader"]
                    if not track.title and "title" in track.metadata["extracted_info"]:
                        track.title = track.metadata["extracted_info"]["title"].strip()
            
            return track
        except Exception as e:
            raise DownloadError(f"Failed to extract info from online media: {str(e)}") from e
    
    async def _download_video(self, url: str, output_filename_no_extension: str) -> str:
        """
        Download a video from a URL.
        
        Args:
            url: The URL to download from
            output_filename_no_extension: The output filename without extension
            
        Returns:
            The path to the downloaded file
        """
        self.logger.debug(f"Downloading media from URL {url} to filename {output_filename_no_extension} + (as yet) unknown extension")
        
        try:
            ydl_opts = {
                "quiet": True,
                "format": "bv*+ba/b",  # if a combined video + audio format is better than the best video-only format use the combined format
                "outtmpl": f"{output_filename_no_extension}.%(ext)s",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36",
            }
            
            if not self.config.dry_run:
                with ydl(ydl_opts) as ydl_instance:
                    ydl_instance.download([url])
                
                # Search for the file with any extension
                downloaded_files = glob.glob(f"{output_filename_no_extension}.*")
                if downloaded_files:
                    downloaded_file_name = downloaded_files[0]  # Assume the first match is the correct one
                    self.logger.info(f"Download finished, returning downloaded filename: {downloaded_file_name}")
                    return downloaded_file_name
                else:
                    raise DownloadError("No files found matching the download pattern")
            
            return f"{output_filename_no_extension}.mp4"  # Placeholder for dry run
        except Exception as e:
            raise DownloadError(f"Failed to download video: {str(e)}") from e
    
    async def _copy_input_media(self, input_media: str, output_filename_no_extension: str) -> str:
        """
        Copy input media to the output directory.
        
        Args:
            input_media: The input media file
            output_filename_no_extension: The output filename without extension
            
        Returns:
            The path to the copied file
        """
        self.logger.debug(f"Copying media from local path {input_media} to filename {output_filename_no_extension} + existing extension")
        
        try:
            copied_file_name = output_filename_no_extension + os.path.splitext(input_media)[1]
            self.logger.debug(f"Target filename: {copied_file_name}")
            
            # Check if source and destination are the same
            if os.path.abspath(input_media) == os.path.abspath(copied_file_name):
                self.logger.info("Source and destination are the same file, skipping copy")
                return input_media
            
            if not self.config.dry_run:
                self.logger.debug(f"Copying {input_media} to {copied_file_name}")
                shutil.copy2(input_media, copied_file_name)
            
            return copied_file_name
        except Exception as e:
            raise MediaError(f"Failed to copy input media: {str(e)}") from e
    
    async def _extract_still_image_from_video(self, input_filename: str, output_filename_no_extension: str) -> str:
        """
        Extract a still image from a video.
        
        Args:
            input_filename: The input video file
            output_filename_no_extension: The output filename without extension
            
        Returns:
            The path to the extracted image
        """
        output_filename = output_filename_no_extension + ".png"
        self.logger.info(f"Extracting still image from position 30s input media")
        
        try:
            if not self.config.dry_run:
                ffmpeg_command = f'{self.ffmpeg_base_command} -i "{input_filename}" -ss 00:00:30 -vframes 1 "{output_filename}"'
                self.logger.debug(f"Running command: {ffmpeg_command}")
                os.system(ffmpeg_command)
            
            return output_filename
        except Exception as e:
            raise ConversionError(f"Failed to extract still image: {str(e)}") from e
    
    async def _convert_to_wav(self, input_filename: str, output_filename_no_extension: str) -> str:
        """
        Convert a media file to WAV format.
        
        Args:
            input_filename: The input media file
            output_filename_no_extension: The output filename without extension
            
        Returns:
            The path to the converted WAV file
        """
        try:
            # Validate input file exists and is readable
            if not os.path.isfile(input_filename):
                raise ConversionError(f"Input audio file not found: {input_filename}")
            
            if os.path.getsize(input_filename) == 0:
                raise ConversionError(f"Input audio file is empty: {input_filename}")
            
            # Validate input file format using ffprobe
            probe_command = f'ffprobe -v error -show_entries stream=codec_type -of default=noprint_wrappers=1 "{input_filename}"'
            probe_output = os.popen(probe_command).read()
            
            if "codec_type=audio" not in probe_output:
                raise ConversionError(f"No valid audio stream found in file: {input_filename}")
            
            output_filename = output_filename_no_extension + ".wav"
            self.logger.info(f"Converting input media to audio WAV file")
            
            if not self.config.dry_run:
                ffmpeg_command = f'{self.ffmpeg_base_command} -n -i "{input_filename}" "{output_filename}"'
                self.logger.debug(f"Running command: {ffmpeg_command}")
                os.system(ffmpeg_command)
            
            return output_filename
        except Exception as e:
            raise ConversionError(f"Failed to convert to WAV: {str(e)}") from e
    
    def _sanitize_filename(self, filename: str) -> str:
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
