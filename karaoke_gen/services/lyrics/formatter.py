import os
import glob
import shutil
import datetime
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import FormattingError


class LyricsFormatter:
    """
    Handles lyrics formatting and backup operations.
    """
    
    def __init__(self, config):
        """
        Initialize the lyrics formatter.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
    
    async def format_lyrics(self, track):
        """
        Format lyrics for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated formatting information
        """
        self.logger.info(f"Formatting lyrics for {track.base_name}")
        
        # Skip if no lyrics
        if not track.lyrics:
            self.logger.warning("No lyrics found, cannot format")
            return track
        
        # Skip if already formatted
        if track.processed_lyrics and track.processed_lyrics.get("formatted_lyrics"):
            self.logger.info(f"Lyrics already formatted")
            return track
        
        try:
            # Read lyrics file
            if isinstance(track.lyrics, str) and os.path.isfile(track.lyrics):
                with open(track.lyrics, "r", encoding="utf-8") as f:
                    lyrics_text = f.read()
            else:
                lyrics_text = track.lyrics
            
            # Format lyrics
            formatted_lyrics = self._format_lyrics_text(lyrics_text)
            
            # Save formatted lyrics
            formatted_lyrics_file = os.path.join(track.track_output_dir, f"{track.base_name} (Formatted Lyrics).txt")
            if not self.config.dry_run:
                with open(formatted_lyrics_file, "w", encoding="utf-8") as f:
                    f.write(formatted_lyrics)
            
            # Update track
            if not track.processed_lyrics:
                track.processed_lyrics = {}
            
            track.processed_lyrics["formatted_lyrics"] = formatted_lyrics
            track.processed_lyrics["formatted_lyrics_file"] = formatted_lyrics_file
            
            return track
            
        except Exception as e:
            raise FormattingError(f"Failed to format lyrics: {str(e)}") from e
    
    def _format_lyrics_text(self, lyrics_text):
        """
        Format lyrics text.
        
        Args:
            lyrics_text: The lyrics text to format
            
        Returns:
            The formatted lyrics text
        """
        # Remove extra whitespace
        formatted_text = lyrics_text.strip()
        
        # Split into lines
        lines = formatted_text.split("\n")
        
        # Remove empty lines at the beginning and end
        while lines and not lines[0].strip():
            lines.pop(0)
        
        while lines and not lines[-1].strip():
            lines.pop()
        
        # Remove duplicate empty lines
        formatted_lines = []
        prev_empty = False
        for line in lines:
            is_empty = not line.strip()
            if not (is_empty and prev_empty):
                formatted_lines.append(line)
            prev_empty = is_empty
        
        # Join lines
        formatted_text = "\n".join(formatted_lines)
        
        return formatted_text
    
    async def backup_existing_outputs(self, track):
        """
        Backup existing outputs for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated backup information
        """
        self.logger.info(f"Backing up existing outputs for {track.base_name}")
        
        # Create backup directory
        backup_dir = os.path.join(track.track_output_dir, "backup_" + self._get_timestamp())
        if not self.config.dry_run:
            os.makedirs(backup_dir, exist_ok=True)
        
        # Find existing files to backup
        files_to_backup = []
        
        # Lyrics files
        lyrics_files = glob.glob(os.path.join(track.track_output_dir, "*.lrc"))
        files_to_backup.extend(lyrics_files)
        
        # Video files
        video_files = glob.glob(os.path.join(track.track_output_dir, "*.mkv"))
        video_files.extend(glob.glob(os.path.join(track.track_output_dir, "*.mp4")))
        files_to_backup.extend(video_files)
        
        # Subtitle files
        subtitle_files = glob.glob(os.path.join(track.track_output_dir, "*.srt"))
        subtitle_files.extend(glob.glob(os.path.join(track.track_output_dir, "*.ass")))
        files_to_backup.extend(subtitle_files)
        
        # Backup files
        for file_path in files_to_backup:
            if os.path.exists(file_path) and not self.config.dry_run:
                backup_path = os.path.join(backup_dir, os.path.basename(file_path))
                shutil.copy2(file_path, backup_path)
                self.logger.info(f"Backed up {file_path} to {backup_path}")
        
        return track
    
    def _get_timestamp(self):
        """
        Get a timestamp string.
        
        Returns:
            A timestamp string
        """
        return datetime.datetime.now().strftime("%Y%m%d_%H%M%S") 