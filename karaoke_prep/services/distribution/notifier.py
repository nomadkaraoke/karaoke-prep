"""
Notification functionality for the distribution service.
"""

import os
import pickle
import logging
import base64
import requests
from typing import Optional, Dict, Any
from email.mime.text import MIMEText

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import DistributionError


class Notifier:
    """
    Class for handling notifications.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the notifier.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        self.gmail_token_file = "/tmp/karaoke-finalise-gmail-token.pickle"
        self.gmail_service = None
    
    def post_discord_message(self, message: str, webhook_url: str) -> None:
        """
        Post a message to a Discord channel via webhook.
        
        Args:
            message: The message to post
            webhook_url: The Discord webhook URL
            
        Raises:
            DistributionError: If posting the message fails
        """
        self.logger.info(f"Posting message to Discord...")
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would post message to Discord: {message}")
            return
        
        try:
            data = {"content": message}
            response = requests.post(webhook_url, json=data)
            response.raise_for_status()  # This will raise an exception if the request failed
            self.logger.info("Message posted to Discord")
        
        except Exception as e:
            self.logger.error(f"Failed to post message to Discord: {str(e)}")
            raise DistributionError(f"Failed to post message to Discord: {str(e)}")
    
    def post_discord_notification(self, track: Track, skip_notifications: bool = False) -> None:
        """
        Post a notification to Discord.
        
        Args:
            track: The track to notify about
            skip_notifications: Whether to skip notifications
            
        Raises:
            DistributionError: If posting the notification fails
        """
        self.logger.info(f"Posting Discord notification...")
        
        if not self.config.discord_webhook_url:
            self.logger.warning("Discord webhook URL not set, cannot post notification")
            return
        
        if skip_notifications:
            self.logger.info(f"Skipping Discord notification as requested")
            return
        
        if self.config.dry_run:
            self.logger.info(
                f"DRY RUN: Would post Discord notification for YouTube URL {track.youtube_url} using webhook URL: {self.config.discord_webhook_url}"
            )
            return
        
        try:
            # Create a rich embed for Discord
            embed = {
                "title": f"{track.artist} - {track.title}",
                "description": "New karaoke track available!",
                "color": 0x00ff00,  # Green color
                "fields": []
            }
            
            # Add brand code if available
            if track.brand_code:
                embed["fields"].append({
                    "name": "Brand Code",
                    "value": track.brand_code,
                    "inline": True
                })
            
            # Add YouTube URL if available
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
            
            # Create the payload
            payload = {
                "embeds": [embed]
            }
            
            # Post to Discord
            response = requests.post(self.config.discord_webhook_url, json=payload)
            response.raise_for_status()
            
            self.logger.info("Discord notification posted successfully")
        
        except Exception as e:
            self.logger.error(f"Failed to post Discord notification: {str(e)}")
            raise DistributionError(f"Failed to post Discord notification: {str(e)}")
    
    def authenticate_gmail(self) -> Any:
        """
        Authenticate and return a Gmail service object.
        
        Returns:
            The authenticated Gmail service
            
        Raises:
            DistributionError: If authentication fails
        """
        self.logger.info("Authenticating with Gmail...")
        
        if self.config.dry_run:
            self.logger.info("DRY RUN: Would authenticate with Gmail")
            return None
        
        try:
            creds = None
            
            # Token file stores the user's access and refresh tokens for Gmail.
            if os.path.exists(self.gmail_token_file):
                with open(self.gmail_token_file, "rb") as token:
                    creds = pickle.load(token)
            
            # If there are no valid credentials, let the user log in.
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.config.youtube_client_secrets_file,  # Reuse the YouTube client secrets file
                        ["https://www.googleapis.com/auth/gmail.compose"]
                    )
                    creds = flow.run_local_server(port=0)
                
                # Save the credentials for the next run
                with open(self.gmail_token_file, "wb") as token:
                    pickle.dump(creds, token)
            
            return build("gmail", "v1", credentials=creds)
        
        except Exception as e:
            self.logger.error(f"Failed to authenticate with Gmail: {str(e)}")
            raise DistributionError(f"Failed to authenticate with Gmail: {str(e)}")
    
    def draft_completion_email(self, track: Track) -> None:
        """
        Draft a completion email.
        
        Args:
            track: The track to draft an email for
            
        Raises:
            DistributionError: If drafting the email fails
        """
        self.logger.info(f"Drafting completion email...")
        
        if not self.config.email_template_file:
            self.logger.info("Email template file not provided, skipping email draft creation.")
            return
        
        if not track.youtube_url or not track.brand_code_dir_sharing_link:
            self.logger.warning("YouTube URL or sharing link not available, cannot draft completion email")
            return
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would draft completion email for {track.artist} - {track.title}")
            return
        
        try:
            # Read the email template
            with open(self.config.email_template_file, "r", encoding="utf-8") as f:
                template = f.read()
            
            # Format the email body
            email_body = template.format(
                youtube_url=track.youtube_url,
                dropbox_url=track.brand_code_dir_sharing_link,
                artist=track.artist,
                title=track.title,
                brand_code=track.brand_code
            )
            
            # Create the email subject
            subject = f"{track.brand_code}: {track.artist} - {track.title}"
            
            # Create the email message
            message = MIMEText(email_body)
            message["subject"] = subject
            
            # Encode the message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            
            # Get the Gmail service
            if not self.gmail_service:
                self.gmail_service = self.authenticate_gmail()
            
            # Create the draft
            draft = self.gmail_service.users().drafts().create(
                userId="me",
                body={"message": {"raw": raw_message}}
            ).execute()
            
            self.logger.info(f"Email draft created with ID: {draft['id']}")
        
        except Exception as e:
            self.logger.error(f"Failed to draft completion email: {str(e)}")
            raise DistributionError(f"Failed to draft completion email: {str(e)}")
    
    def test_email_template(self) -> None:
        """
        Test the email template by creating a draft with fake data.
        
        Raises:
            DistributionError: If testing the email template fails
        """
        self.logger.info(f"Testing email template...")
        
        if not self.config.email_template_file:
            self.logger.error("Email template file not provided. Use --email_template_file to specify the file path.")
            return
        
        if self.config.dry_run:
            self.logger.info(f"DRY RUN: Would test email template")
            return
        
        try:
            # Create a fake track
            fake_track = Track(
                artist="Test Artist",
                title="Test Song",
                brand_code="TEST-0001",
                youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                brand_code_dir_sharing_link="https://www.dropbox.com/sh/fake/folder/link"
            )
            
            # Draft the email
            self.draft_completion_email(fake_track)
            
            self.logger.info("Email template test complete. Check your Gmail drafts for the test email.")
        
        except Exception as e:
            self.logger.error(f"Failed to test email template: {str(e)}")
            raise DistributionError(f"Failed to test email template: {str(e)}") 