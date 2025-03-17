import os
import asyncio
import logging
from typing import List, Optional
from karaoke_prep.core.track import Track
from karaoke_prep.services.audio.service import AudioService
from karaoke_prep.services.lyrics.service import LyricsService
from karaoke_prep.services.video.service import VideoService


class KaraokeService:
    """
    Main service for orchestrating the entire karaoke preparation process.
    """
    
    def __init__(self, config):
        """
        Initialize the karaoke service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
        
        # Initialize component services
        self.audio_service = AudioService(config)
        self.lyrics_service = LyricsService(config)
        self.video_service = VideoService(config)
    
    async def process_track(self, track: Track) -> Track:
        """
        Process a single track through the entire karaoke preparation pipeline.
        
        Args:
            track: The track to process
            
        Returns:
            The processed track
        """
        self.logger.info(f"Processing track: {track.base_name}")
        
        try:
            # Create output directory if it doesn't exist
            if not os.path.exists(track.track_output_dir):
                os.makedirs(track.track_output_dir)
            
            # Process audio
            track = await self.audio_service.process_audio(track)
            
            # Process lyrics
            track = await self.lyrics_service.process_lyrics(track)
            
            # Process video
            track = await self.video_service.process_video(track)
            
            self.logger.info(f"Successfully processed track: {track.base_name}")
            return track
            
        except Exception as e:
            self.logger.error(f"Failed to process track {track.base_name}: {str(e)}")
            return track
    
    async def process_tracks(self, tracks: List[Track]) -> List[Track]:
        """
        Process multiple tracks through the entire karaoke preparation pipeline.
        
        Args:
            tracks: The list of tracks to process
            
        Returns:
            The list of processed tracks
        """
        self.logger.info(f"Processing {len(tracks)} tracks")
        
        processed_tracks = []
        
        # Process tracks sequentially or in parallel based on configuration
        if self.config.parallel_processing:
            # Process tracks in parallel with a limit on concurrency
            semaphore = asyncio.Semaphore(self.config.max_concurrent_tracks)
            
            async def process_with_semaphore(track):
                async with semaphore:
                    return await self.process_track(track)
            
            tasks = [process_with_semaphore(track) for track in tracks]
            processed_tracks = await asyncio.gather(*tasks)
        else:
            # Process tracks sequentially
            for track in tracks:
                processed_track = await self.process_track(track)
                processed_tracks.append(processed_track)
        
        self.logger.info(f"Finished processing {len(processed_tracks)} tracks")
        return processed_tracks
    
    async def cleanup(self):
        """
        Perform cleanup operations after processing is complete.
        """
        self.logger.info("Performing cleanup operations")
        
        # Cleanup temporary files if configured
        if self.config.cleanup_temp_files:
            self.logger.info("Cleaning up temporary files")
            # Implement cleanup logic here
        
        # Close any open resources
        await self.audio_service.cleanup()
        await self.lyrics_service.cleanup()
        await self.video_service.cleanup()
        
        self.logger.info("Cleanup complete")
    
    def get_summary(self, tracks: List[Track]) -> str:
        """
        Generate a summary of the processed tracks.
        
        Args:
            tracks: The list of processed tracks
            
        Returns:
            A summary string
        """
        summary = []
        summary.append(f"Processed {len(tracks)} tracks:")
        
        for track in tracks:
            track_summary = f"- {track.base_name}:"
            
            # Add audio processing summary
            if track.instrumental:
                track_summary += " [Audio: ✓]"
            else:
                track_summary += " [Audio: ✗]"
            
            # Add lyrics processing summary
            if track.processed_lyrics:
                track_summary += " [Lyrics: ✓]"
            else:
                track_summary += " [Lyrics: ✗]"
            
            # Add video processing summary
            if track.final_video:
                track_summary += " [Video: ✓]"
            else:
                track_summary += " [Video: ✗]"
            
            summary.append(track_summary)
        
        return "\n".join(summary) 