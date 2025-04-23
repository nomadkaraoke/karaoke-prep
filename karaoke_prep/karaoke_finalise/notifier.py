import os
import logging
import pickle
import base64
import requests
from email.mime.text import MIMEText
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


class Notifier:
    def __init__(self, logger=None, dry_run=False, discord_webhook_url=None, email_template_file=None, youtube_client_secrets_file=None):
        self.logger = logger or logging.getLogger(__name__)
        self.dry_run = dry_run
        self.discord_webhook_url = discord_webhook_url
        self.email_template_file = email_template_file
        self.youtube_client_secrets_file = youtube_client_secrets_file
        self.gmail_service = None
    
    def post_discord_message(self, message):
        """Post a message to a Discord channel via webhook."""
        if not self.discord_webhook_url:
            self.logger.warning("Discord webhook URL not provided, skipping notification")
            return
            
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would post Discord message: {message}")
            return
            
        data = {"content": message}
        response = requests.post(self.discord_webhook_url, json=data)
        response.raise_for_status()  # This will raise an exception if the request failed
        self.logger.info("Message posted to Discord")

    def post_discord_notification(self, youtube_url, skip_notifications=False):
        self.logger.info(f"Posting Discord notification...")

        if skip_notifications:
            self.logger.info(f"Skipping Discord notification as video was previously uploaded to YouTube")
            return

        if self.dry_run:
            self.logger.info(
                f"DRY RUN: Would post Discord notification for youtube URL {youtube_url} using webhook URL: {self.discord_webhook_url}"
            )
        else:
            discord_message = f"New upload: {youtube_url}"
            self.post_discord_message(discord_message)

    def authenticate_gmail(self):
        """Authenticate and return a Gmail service object."""
        if not self.youtube_client_secrets_file:
            raise ValueError("YouTube client secrets file is required for Gmail authentication")
            
        creds = None
        gmail_token_file = "/tmp/karaoke-finalise-gmail-token.pickle"

        if os.path.exists(gmail_token_file):
            with open(gmail_token_file, "rb") as token:
                creds = pickle.load(token)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.youtube_client_secrets_file, ["https://www.googleapis.com/auth/gmail.compose"]
                )
                creds = flow.run_local_server(port=0)
            with open(gmail_token_file, "wb") as token:
                pickle.dump(creds, token)

        return build("gmail", "v1", credentials=creds)

    def draft_completion_email(self, artist, title, youtube_url, dropbox_url, brand_code):
        if not self.email_template_file:
            self.logger.info("Email template file not provided, skipping email draft creation.")
            return

        with open(self.email_template_file, "r") as f:
            template = f.read()

        email_body = template.format(youtube_url=youtube_url, dropbox_url=dropbox_url)

        subject = f"{brand_code}: {artist} - {title}"

        if self.dry_run:
            self.logger.info(f"DRY RUN: Would create email draft with subject: {subject}")
            self.logger.info(f"DRY RUN: Email body:\n{email_body}")
        else:
            if not self.gmail_service:
                self.gmail_service = self.authenticate_gmail()

            message = MIMEText(email_body)
            message["subject"] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            draft = self.gmail_service.users().drafts().create(userId="me", body={"message": {"raw": raw_message}}).execute()
            self.logger.info(f"Email draft created with ID: {draft['id']}")

    def test_email_template(self):
        if not self.email_template_file:
            self.logger.error("Email template file not provided. Use --email_template_file to specify the file path.")
            return

        fake_artist = "Test Artist"
        fake_title = "Test Song"
        fake_youtube_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        fake_dropbox_url = "https://www.dropbox.com/sh/fake/folder/link"
        fake_brand_code = "TEST-0001"

        self.draft_completion_email(fake_artist, fake_title, fake_youtube_url, fake_dropbox_url, fake_brand_code)

        self.logger.info("Email template test complete. Check your Gmail drafts for the test email.") 