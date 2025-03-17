"""
YouTube uploading functionality for the distribution service.
"""

import os
import pickle
import logging
from typing import Optional, Dict, Any, List, Tuple

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from thefuzz import fuzz

from karaoke_gen.core.project import ProjectConfig
from karaoke_gen.core.exceptions import YouTubeError


class YouTubeUploader:
    """
    Class for handling YouTube uploads and related operations.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the YouTube uploader.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        self.youtube_url_prefix = "https://www.youtube.com/watch?v="
        self.youtube_token_file = "/tmp/karaoke-finalise-youtube-token.pickle"
    
    def authenticate_youtube(self) -> Any:
        """
        Authenticate and return a YouTube service object.
        
        Returns:
            The authenticated YouTube service
        
        Raises:
            YouTubeError: If authentication fails
        """
        self.logger.info("Authenticating with YouTube...")
        
        if self.config.dry_run:
            self.logger.info("DRY RUN: Would authenticate with YouTube")
            return None
        
        try:
            credentials = None
            
            # Token file stores the user's access and refresh tokens for YouTube.
            if os.path.exists(self.youtube_token_file):
                with open(self.youtube_token_file, "rb") as token:
                    credentials = pickle.load(token)
            
            # If there are no valid credentials, let the user log in.
            if not credentials or not credentials.valid:
                if credentials and credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.config.youtube_client_secrets_file, 
                        scopes=["https://www.googleapis.com/auth/youtube"]
                    )
                    credentials = flow.run_local_server(port=0)  # This will open a browser for authentication
                
                # Save the credentials for the next run
                with open(self.youtube_token_file, "wb") as token:
                    pickle.dump(credentials, token)
            
            return build("youtube", "v3", credentials=credentials)
        
        except Exception as e:
            self.logger.error(f"Failed to authenticate with YouTube: {str(e)}")
            raise YouTubeError(f"Failed to authenticate with YouTube: {str(e)}")
    
    def get_channel_id(self) -> Optional[str]:
        """
        Get the authenticated user's channel ID.
        
        Returns:
            The channel ID or None if not found
        
        Raises:
            YouTubeError: If getting the channel ID fails
        """
        self.logger.info("Getting YouTube channel ID...")
        
        if self.config.dry_run:
            self.logger.info("DRY RUN: Would get YouTube channel ID")
            return "DUMMY_CHANNEL_ID"
        
        try:
            youtube = self.authenticate_youtube()
            
            # Get the authenticated user's channel
            request = youtube.channels().list(part="snippet", mine=True)
            response = request.execute()
            
            # Extract the channel ID
            if "items" in response:
                channel_id = response["items"][0]["id"]
                self.logger.info(f"Found YouTube channel ID: {channel_id}")
                return channel_id
            else:
                self.logger.warning("No YouTube channel found for the authenticated user")
                return None
        
        except Exception as e:
            self.logger.error(f"Failed to get YouTube channel ID: {str(e)}")
            raise YouTubeError(f"Failed to get YouTube channel ID: {str(e)}")
    
    def check_if_video_title_exists(self, youtube_title: str) -> Tuple[bool, Optional[str]]:
        """
        Check if a video with the given title already exists on the authenticated user's channel.
        
        Args:
            youtube_title: The title to check
        
        Returns:
            A tuple of (exists, video_id) where exists is True if the video exists and video_id is the ID of the video
        
        Raises:
            YouTubeError: If checking for the video fails
        """
        self.logger.info(f"Checking if video with title '{youtube_title}' exists on YouTube channel...")
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would check if video with title '{youtube_title}' exists on YouTube channel")
            return False, None
        
        try:
            youtube = self.authenticate_youtube()
            channel_id = self.get_channel_id()
            
            if not channel_id:
                self.logger.warning("No YouTube channel ID found, cannot check for existing videos")
                return False, None
            
            self.logger.info(f"Searching YouTube channel {channel_id} for title: {youtube_title}")
            request = youtube.search().list(
                part="snippet", 
                channelId=channel_id, 
                q=youtube_title, 
                type="video", 
                maxResults=10
            )
            response = request.execute()
            
            # Check if any videos were found
            if "items" in response and len(response["items"]) > 0:
                for item in response["items"]:
                    found_title = item["snippet"]["title"]
                    similarity_score = fuzz.ratio(youtube_title.lower(), found_title.lower())
                    if similarity_score >= 70:  # 70% similarity
                        found_id = item["id"]["videoId"]
                        self.logger.info(
                            f"Potential match found on YouTube channel with ID: {found_id} and title: {found_title} (similarity: {similarity_score}%)"
                        )
                        
                        # In non-interactive mode, automatically confirm if similarity is high enough
                        if self.config.non_interactive:
                            self.logger.info(f"Non-interactive mode, automatically confirming match with similarity score {similarity_score}%")
                            return True, found_id
                        
                        confirmation = input(f"Is '{found_title}' the video you are finalising? (y/n): ").strip().lower()
                        if confirmation == "y":
                            return True, found_id
            
            self.logger.info(f"No matching video found with title: {youtube_title}")
            return False, None
        
        except Exception as e:
            self.logger.error(f"Failed to check if video exists on YouTube: {str(e)}")
            raise YouTubeError(f"Failed to check if video exists on YouTube: {str(e)}")
    
    def delete_youtube_video(self, video_id: str) -> bool:
        """
        Delete a YouTube video by its ID.
        
        Args:
            video_id: The YouTube video ID to delete
            
        Returns:
            True if successful, False otherwise
        
        Raises:
            YouTubeError: If deleting the video fails
        """
        self.logger.info(f"Deleting YouTube video with ID: {video_id}")
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would delete YouTube video with ID: {video_id}")
            return True
        
        try:
            youtube = self.authenticate_youtube()
            youtube.videos().delete(id=video_id).execute()
            self.logger.info(f"Successfully deleted YouTube video with ID: {video_id}")
            return True
        
        except Exception as e:
            self.logger.error(f"Failed to delete YouTube video with ID {video_id}: {e}")
            return False
    
    def truncate_to_nearest_word(self, title: str, max_length: int) -> str:
        """
        Truncate a string to the nearest word within the maximum length.
        
        Args:
            title: The string to truncate
            max_length: The maximum length
            
        Returns:
            The truncated string
        """
        if len(title) <= max_length:
            return title
        
        truncated_title = title[:max_length].rsplit(" ", 1)[0]
        if len(truncated_title) < max_length:
            truncated_title += " ..."
        
        return truncated_title
    
    def upload_video(
        self, 
        video_file: str, 
        thumbnail_file: Optional[str], 
        artist: str, 
        title: str, 
        replace_existing: bool = False
    ) -> Optional[str]:
        """
        Upload a video to YouTube with the given title and thumbnail.
        
        Args:
            video_file: The path to the video file
            thumbnail_file: The path to the thumbnail file
            artist: The artist name
            title: The track title
            replace_existing: Whether to replace an existing video
            
        Returns:
            The YouTube URL of the uploaded video or None if upload failed
        
        Raises:
            YouTubeError: If uploading the video fails
        """
        self.logger.info(f"Uploading video to YouTube: {video_file}")
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would upload {video_file} to YouTube with thumbnail {thumbnail_file}")
            return f"{self.youtube_url_prefix}DUMMY_VIDEO_ID"
        
        try:
            youtube_title = f"{artist} - {title} (Karaoke)"
            
            # Truncate title to the nearest whole word and add ellipsis if needed
            max_length = 95
            youtube_title = self.truncate_to_nearest_word(youtube_title, max_length)
            
            # Check if video already exists
            exists, video_id = self.check_if_video_title_exists(youtube_title)
            if exists:
                if replace_existing:
                    self.logger.info(f"Video already exists on YouTube, deleting before re-upload: {self.youtube_url_prefix}{video_id}")
                    if self.delete_youtube_video(video_id):
                        self.logger.info(f"Successfully deleted existing video, proceeding with upload")
                    else:
                        self.logger.error(f"Failed to delete existing video, aborting upload")
                        return None
                else:
                    self.logger.warning(f"Video already exists on YouTube, skipping upload: {self.youtube_url_prefix}{video_id}")
                    return f"{self.youtube_url_prefix}{video_id}"
            
            # Load description from file if available
            youtube_description = f"Karaoke version of {artist} - {title} created using karaoke-gen python package."
            if self.config.youtube_description_file and os.path.isfile(self.config.youtube_description_file):
                with open(self.config.youtube_description_file, "r") as f:
                    youtube_description = f.read()
            
            youtube_category_id = "10"  # Category ID for Music
            youtube_keywords = ["karaoke", "music", "singing", "instrumental", "lyrics", artist, title]
            
            self.logger.info(f"Authenticating with YouTube...")
            youtube = self.authenticate_youtube()
            
            body = {
                "snippet": {
                    "title": youtube_title,
                    "description": youtube_description,
                    "tags": youtube_keywords,
                    "categoryId": youtube_category_id,
                },
                "status": {"privacyStatus": "public"},
            }
            
            # Use MediaFileUpload to handle the video file
            media_file = MediaFileUpload(video_file, resumable=True)
            
            # Call the API's videos.insert method to create and upload the video.
            self.logger.info(f"Uploading video to YouTube...")
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media_file)
            response = request.execute()
            
            video_id = response.get("id")
            youtube_url = f"{self.youtube_url_prefix}{video_id}"
            self.logger.info(f"Uploaded video to YouTube: {youtube_url}")
            
            # Uploading the thumbnail
            if thumbnail_file and os.path.isfile(thumbnail_file):
                media_thumbnail = MediaFileUpload(thumbnail_file, mimetype="image/jpeg")
                youtube.thumbnails().set(videoId=video_id, media_body=media_thumbnail).execute()
                self.logger.info(f"Uploaded thumbnail for video ID {video_id}")
            
            return youtube_url
        
        except Exception as e:
            self.logger.error(f"Failed to upload video to YouTube: {str(e)}")
            raise YouTubeError(f"Failed to upload video to YouTube: {str(e)}") 