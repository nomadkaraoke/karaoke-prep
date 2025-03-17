import os
import asyncio
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import LyricsError


class LyricsFetcher:
    """
    Handles fetching lyrics from various sources.
    """
    
    def __init__(self, config):
        """
        Initialize the lyrics fetcher.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
    
    async def fetch_lyrics(self, track):
        """
        Fetch lyrics for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated lyrics information
        """
        self.logger.info(f"Fetching lyrics for {track.base_name}")
        
        # Skip if lyrics already exist
        if track.lyrics:
            self.logger.info(f"Lyrics already exist: {track.lyrics}")
            return track
        
        # If lyrics file is provided, use it
        if self.config.lyrics_file and os.path.exists(self.config.lyrics_file):
            self.logger.info(f"Using provided lyrics file: {self.config.lyrics_file}")
            with open(self.config.lyrics_file, "r", encoding="utf-8") as f:
                lyrics = f.read()
            
            # Save lyrics to track output directory
            lyrics_file = os.path.join(track.track_output_dir, "lyrics.txt")
            if not self.config.dry_run:
                with open(lyrics_file, "w", encoding="utf-8") as f:
                    f.write(lyrics)
            
            track.lyrics = lyrics_file
            return track
        
        # Otherwise, fetch lyrics from online sources
        artist = self.config.lyrics_artist or track.artist
        title = self.config.lyrics_title or track.title
        
        if not artist or not title:
            self.logger.warning("Artist or title not provided, cannot fetch lyrics")
            return track
        
        # Try to fetch lyrics from online sources
        try:
            lyrics = await self._fetch_lyrics_from_online_sources(artist, title)
            
            # Save lyrics to track output directory
            lyrics_file = os.path.join(track.track_output_dir, "lyrics.txt")
            if not self.config.dry_run:
                with open(lyrics_file, "w", encoding="utf-8") as f:
                    f.write(lyrics)
            
            track.lyrics = lyrics_file
            self.logger.info(f"Successfully fetched lyrics for {track.base_name}")
            
        except Exception as e:
            self.logger.warning(f"Failed to fetch lyrics: {str(e)}")
            
            # Create a placeholder lyrics file
            lyrics = f"[Placeholder lyrics for {artist} - {title}]"
            lyrics_file = os.path.join(track.track_output_dir, "lyrics.txt")
            
            if not self.config.dry_run:
                with open(lyrics_file, "w", encoding="utf-8") as f:
                    f.write(lyrics)
            
            track.lyrics = lyrics_file
        
        return track
    
    async def _fetch_lyrics_from_online_sources(self, artist, title):
        """
        Fetch lyrics from online sources.
        
        Args:
            artist: The artist name
            title: The song title
            
        Returns:
            The lyrics text
        """
        self.logger.info(f"Fetching lyrics for {artist} - {title} from online sources")
        
        # Try to fetch from Genius
        try:
            lyrics = await self._fetch_lyrics_from_genius(artist, title)
            if lyrics:
                return lyrics
        except Exception as e:
            self.logger.debug(f"Failed to fetch lyrics from Genius: {str(e)}")
        
        # Try to fetch from Musixmatch
        try:
            lyrics = await self._fetch_lyrics_from_musixmatch(artist, title)
            if lyrics:
                return lyrics
        except Exception as e:
            self.logger.debug(f"Failed to fetch lyrics from Musixmatch: {str(e)}")
        
        # Try to fetch from AZLyrics
        try:
            lyrics = await self._fetch_lyrics_from_azlyrics(artist, title)
            if lyrics:
                return lyrics
        except Exception as e:
            self.logger.debug(f"Failed to fetch lyrics from AZLyrics: {str(e)}")
        
        raise LyricsError(f"Failed to fetch lyrics for {artist} - {title} from any source")
    
    async def _fetch_lyrics_from_genius(self, artist, title):
        """
        Fetch lyrics from Genius.
        
        Args:
            artist: The artist name
            title: The song title
            
        Returns:
            The lyrics text or None if not found
        """
        self.logger.debug(f"Fetching lyrics from Genius for {artist} - {title}")
        
        # Check if Genius API token is available
        genius_token = os.environ.get("GENIUS_API_TOKEN")
        if not genius_token:
            self.logger.debug("Genius API token not available")
            return None
        
        # TODO: Implement Genius API integration
        # For now, return None to try other sources
        return None
    
    async def _fetch_lyrics_from_musixmatch(self, artist, title):
        """
        Fetch lyrics from Musixmatch.
        
        Args:
            artist: The artist name
            title: The song title
            
        Returns:
            The lyrics text or None if not found
        """
        self.logger.debug(f"Fetching lyrics from Musixmatch for {artist} - {title}")
        
        # TODO: Implement Musixmatch API integration
        # For now, return None to try other sources
        return None
    
    async def _fetch_lyrics_from_azlyrics(self, artist, title):
        """
        Fetch lyrics from AZLyrics.
        
        Args:
            artist: The artist name
            title: The song title
            
        Returns:
            The lyrics text or None if not found
        """
        self.logger.debug(f"Fetching lyrics from AZLyrics for {artist} - {title}")
        
        # TODO: Implement AZLyrics scraping
        # For now, return None to try other sources
        return None 