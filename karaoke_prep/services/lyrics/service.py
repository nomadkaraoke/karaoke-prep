import logging
import os
import glob
import shutil
from typing import Dict, Any, Optional
from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import LyricsError
from karaoke_prep.services.lyrics.fetcher import LyricsFetcher
from karaoke_prep.services.lyrics.transcriber import LyricsTranscriber
from karaoke_prep.services.lyrics.synchronizer import LyricsSynchronizer
from karaoke_prep.services.lyrics.formatter import LyricsFormatter
import datetime


class LyricsService:
    """
    Service for lyrics processing operations including fetching, transcription, synchronization, and formatting.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the lyrics service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        
        # Initialize components
        self.fetcher = LyricsFetcher(config)
        self.transcriber = LyricsTranscriber(config)
        self.synchronizer = LyricsSynchronizer(config)
        self.formatter = LyricsFormatter(config)
    
    async def process_lyrics(self, track: Track) -> Track:
        """
        Process lyrics for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated lyrics information
        """
        if self.config.skip_lyrics:
            self.logger.info(f"Skipping lyrics processing for {track.base_name}")
            return track
        
        self.logger.info(f"Processing lyrics for {track.base_name}")
        
        # Use provided lyrics file if specified
        if self.config.lyrics_file and os.path.isfile(self.config.lyrics_file):
            self.logger.info(f"Using provided lyrics file: {self.config.lyrics_file}")
            track = await self.formatter.load_lyrics_from_file(track, self.config.lyrics_file)
            return track
        
        # Check for existing lyrics files
        track = await self._check_existing_lyrics(track)
        if track.processed_lyrics:
            self.logger.info("Found existing lyrics files, skipping transcription")
            return track
        
        # Fetch lyrics if needed
        if not track.lyrics:
            track = await self.fetcher.fetch_lyrics(track)
        
        # Transcribe lyrics
        if not self.config.skip_transcription:
            track = await self.transcriber.transcribe_lyrics(track)
        
        # Synchronize lyrics
        track = await self.synchronizer.synchronize_lyrics(track)
        
        # Format lyrics
        track = await self.formatter.format_lyrics(track)
        
        return track
    
    async def _check_existing_lyrics(self, track: Track) -> Track:
        """
        Check for existing lyrics files.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated lyrics information if existing files are found
        """
        self.logger.info(f"Checking for existing lyrics files for {track.base_name}")
        
        # Check for existing files in parent directory
        parent_video_path = os.path.join(track.track_output_dir, f"{track.base_name} (With Vocals).mkv")
        parent_lrc_path = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).lrc")
        
        # Check lyrics directory for existing files
        lyrics_dir = os.path.join(track.track_output_dir, "lyrics")
        lyrics_video_path = os.path.join(lyrics_dir, f"{track.base_name} (With Vocals).mkv")
        lyrics_lrc_path = os.path.join(lyrics_dir, f"{track.base_name} (Karaoke).lrc")
        
        # If files exist in parent directory, use them
        if os.path.exists(parent_video_path) and os.path.exists(parent_lrc_path):
            self.logger.info(f"Found existing video and LRC files in parent directory")
            track.processed_lyrics = {
                "lrc_filepath": parent_lrc_path,
                "ass_filepath": parent_video_path,
            }
            return track
        
        # If files exist in lyrics directory, copy to parent and use them
        if os.path.exists(lyrics_video_path) and os.path.exists(lyrics_lrc_path):
            self.logger.info(f"Found existing video and LRC files in lyrics directory, copying to parent")
            os.makedirs(track.track_output_dir, exist_ok=True)
            
            # Copy files to parent directory
            shutil.copy2(lyrics_video_path, parent_video_path)
            shutil.copy2(lyrics_lrc_path, parent_lrc_path)
            
            track.processed_lyrics = {
                "lrc_filepath": parent_lrc_path,
                "ass_filepath": parent_video_path,
            }
            return track
        
        return track
    
    async def backup_and_prepare_for_edit(self, track: Track) -> Track:
        """
        Backup existing outputs and prepare for lyrics editing.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated backup information
        """
        self.logger.info(f"Backing up and preparing for lyrics editing for {track.base_name}")
        
        # Create backup directory
        backup_dir = os.path.join(track.track_output_dir, "backups")
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        # Create versioned backup directory
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        version_dir = os.path.join(backup_dir, f"version_{timestamp}")
        os.makedirs(version_dir)
        
        # Backup existing files
        files_to_backup = []
        
        # Backup processed lyrics
        if track.processed_lyrics and os.path.isfile(track.processed_lyrics):
            files_to_backup.append(track.processed_lyrics)
        
        # Backup videos
        for video_attr in ["video_with_lyrics", "final_video"]:
            video_path = getattr(track, video_attr, None)
            if video_path and os.path.isfile(video_path):
                files_to_backup.append(video_path)
        
        # Copy files to backup directory
        for file_path in files_to_backup:
            backup_path = os.path.join(version_dir, os.path.basename(file_path))
            shutil.copy2(file_path, backup_path)
            self.logger.info(f"Backed up {file_path} to {backup_path}")
        
        # Prepare input audio file for editing
        if track.instrumental and os.path.isfile(track.instrumental):
            edit_audio = os.path.join(track.track_output_dir, f"{track.base_name} (Edit).wav")
            shutil.copy2(track.instrumental, edit_audio)
            track.metadata["edit_audio"] = edit_audio
            self.logger.info(f"Prepared audio for editing: {edit_audio}")
        
        # Store backup information
        track.metadata["backup_dir"] = backup_dir
        track.metadata["last_backup"] = version_dir
        
        return track
    
    async def cleanup(self):
        """
        Perform cleanup operations for the lyrics service.
        """
        self.logger.info("Cleaning up lyrics service resources")
        
        # Close any open resources
        if hasattr(self, 'fetcher') and self.fetcher:
            await self.fetcher.cleanup()
        
        if hasattr(self, 'transcriber') and self.transcriber:
            await self.transcriber.cleanup()
        
        if hasattr(self, 'synchronizer') and self.synchronizer:
            await self.synchronizer.cleanup()
        
        if hasattr(self, 'formatter') and self.formatter:
            await self.formatter.cleanup()
        
        self.logger.info("Lyrics service cleanup complete")
    
    async def _find_input_audio_file(self, track: Track) -> Track:
        """
        Find the input audio file for lyrics editing.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated input audio information
        """
        self.logger.info(f"Finding input audio file for {track.base_name}")
        
        # Look for WAV file
        wav_files = glob.glob(os.path.join(track.track_output_dir, "*.wav"))
        if wav_files:
            track.input_audio_wav = wav_files[0]
            self.logger.info(f"Found input audio file: {track.input_audio_wav}")
            return track
        
        # Look for other audio files
        audio_extensions = ['.mp3', '.flac', '.ogg', '.m4a', '.aac']
        for ext in audio_extensions:
            audio_files = glob.glob(os.path.join(track.track_output_dir, f"*{ext}"))
            if audio_files:
                # Convert to WAV
                from karaoke_prep.services.audio.converter import AudioConverter
                converter = AudioConverter(self.config)
                track.input_media = audio_files[0]
                track = await converter.convert_to_wav(track)
                self.logger.info(f"Converted audio file to WAV: {track.input_audio_wav}")
                return track
        
        self.logger.warning(f"No input audio file found for {track.base_name}")
        return track
    
    def _get_timestamp(self) -> str:
        """
        Get a timestamp string for backup directory naming.
        
        Returns:
            A timestamp string
        """
        return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
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