import os
import logging
import json
import pickle
from thefuzz import fuzz
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.http import MediaFileUpload


class YouTubeManager:
    def __init__(self, logger=None, dry_run=False, youtube_client_secrets_file=None, youtube_description_file=None, non_interactive=False):
        self.logger = logger or logging.getLogger(__name__)
        self.dry_run = dry_run
        self.youtube_client_secrets_file = youtube_client_secrets_file
        self.youtube_description_file = youtube_description_file
        self.non_interactive = non_interactive
        
        self.youtube_url_prefix = "https://www.youtube.com/watch?v="
        self.youtube_video_id = None
        self.youtube_url = None
        self.skip_notifications = False

    def authenticate_youtube(self):
        """Authenticate and return a YouTube service object."""
        credentials = None
        youtube_token_file = "/tmp/karaoke-finalise-youtube-token.pickle"

        # Token file stores the user's access and refresh tokens for YouTube.
        if os.path.exists(youtube_token_file):
            with open(youtube_token_file, "rb") as token:
                credentials = pickle.load(token)

        # If there are no valid credentials, let the user log in.
        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.youtube_client_secrets_file, scopes=["https://www.googleapis.com/auth/youtube"]
                )
                credentials = flow.run_local_server(port=0)  # This will open a browser for authentication

            # Save the credentials for the next run
            with open(youtube_token_file, "wb") as token:
                pickle.dump(credentials, token)

        return build("youtube", "v3", credentials=credentials)

    def get_channel_id(self):
        youtube = self.authenticate_youtube()

        # Get the authenticated user's channel
        request = youtube.channels().list(part="snippet", mine=True)
        response = request.execute()

        # Extract the channel ID
        if "items" in response:
            channel_id = response["items"][0]["id"]
            return channel_id
        else:
            return None

    def check_if_video_title_exists_on_youtube_channel(self, youtube_title):
        youtube = self.authenticate_youtube()
        channel_id = self.get_channel_id()

        self.logger.info(f"Searching YouTube channel {channel_id} for title: {youtube_title}")
        request = youtube.search().list(part="snippet", channelId=channel_id, q=youtube_title, type="video", maxResults=10)
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
                    if self.non_interactive:
                        self.logger.info(f"Non-interactive mode, automatically confirming match with similarity score {similarity_score}%")
                        self.youtube_video_id = found_id
                        self.youtube_url = f"{self.youtube_url_prefix}{self.youtube_video_id}"
                        self.skip_notifications = True
                        return True
                    
                    confirmation = input(f"Is '{found_title}' the video you are finalising? (y/n): ").strip().lower()
                    if confirmation == "y":
                        self.youtube_video_id = found_id
                        self.youtube_url = f"{self.youtube_url_prefix}{self.youtube_video_id}"
                        self.skip_notifications = True
                        return True

        self.logger.info(f"No matching video found with title: {youtube_title}")
        return False

    def delete_youtube_video(self, video_id):
        """
        Delete a YouTube video by its ID.
        
        Args:
            video_id: The YouTube video ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        self.logger.info(f"Deleting YouTube video with ID: {video_id}")
        
        if self.dry_run:
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

    def truncate_to_nearest_word(self, title, max_length):
        if len(title) <= max_length:
            return title
        truncated_title = title[:max_length].rsplit(" ", 1)[0]
        if len(truncated_title) < max_length:
            truncated_title += " ..."
        return truncated_title

    def upload_final_mp4_to_youtube_with_title_thumbnail(self, artist, title, input_files, output_files, replace_existing=False):
        self.logger.info(f"Uploading final MKV to YouTube with title thumbnail...")
        if self.dry_run:
            self.logger.info(
                f'DRY RUN: Would upload {output_files["final_karaoke_lossless_mkv"]} to YouTube with thumbnail {input_files["title_jpg"]} using client secrets file: {self.youtube_client_secrets_file}'
            )
        else:
            youtube_title = f"{artist} - {title} (Karaoke)"

            # Truncate title to the nearest whole word and add ellipsis if needed
            max_length = 95
            youtube_title = self.truncate_to_nearest_word(youtube_title, max_length)

            if self.check_if_video_title_exists_on_youtube_channel(youtube_title):
                if replace_existing:
                    self.logger.info(f"Video already exists on YouTube, deleting before re-upload: {self.youtube_url}")
                    if self.delete_youtube_video(self.youtube_video_id):
                        self.logger.info(f"Successfully deleted existing video, proceeding with upload")
                        # Reset the video ID and URL since we're uploading a new one
                        self.youtube_video_id = None
                        self.youtube_url = None
                    else:
                        self.logger.error(f"Failed to delete existing video, aborting upload")
                        return
                else:
                    self.logger.warning(f"Video already exists on YouTube, skipping upload: {self.youtube_url}")
                    return

            youtube_description = f"Karaoke version of {artist} - {title} created using karaoke-gen python package."
            if self.youtube_description_file is not None:
                with open(self.youtube_description_file, "r") as f:
                    youtube_description = f.read()

            youtube_category_id = "10"  # Category ID for Music
            youtube_keywords = ["karaoke", "music", "singing", "instrumental", "lyrics", artist, title]

            self.logger.info(f"Authenticating with YouTube...")
            # Upload video to YouTube and set thumbnail.
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

            # Use MediaFileUpload to handle the video file - using the MKV with FLAC audio
            media_file = MediaFileUpload(output_files["final_karaoke_lossless_mkv"], mimetype="video/x-matroska", resumable=True)

            # Call the API's videos.insert method to create and upload the video.
            self.logger.info(f"Uploading final MKV to YouTube...")
            request = youtube.videos().insert(part="snippet,status", body=body, media_body=media_file)
            response = request.execute()

            self.youtube_video_id = response.get("id")
            self.youtube_url = f"{self.youtube_url_prefix}{self.youtube_video_id}"
            self.logger.info(f"Uploaded video to YouTube: {self.youtube_url}")

            # Uploading the thumbnail
            if input_files["title_jpg"]:
                media_thumbnail = MediaFileUpload(input_files["title_jpg"], mimetype="image/jpeg")
                youtube.thumbnails().set(videoId=self.youtube_video_id, media_body=media_thumbnail).execute()
                self.logger.info(f"Uploaded thumbnail for video ID {self.youtube_video_id}") 