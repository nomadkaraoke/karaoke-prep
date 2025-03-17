import os
import asyncio
import logging
from typing import List, Optional
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import VideoError
from karaoke_prep.services.video.screens import ScreenGenerator
from karaoke_prep.services.video.renderer import VideoRenderer
from karaoke_prep.services.video.compositor import VideoCompositor


class VideoService:
    """
    Service for orchestrating the video generation process.
    """
    
    def __init__(self, config):
        """
        Initialize the video service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        
        # Initialize components
        self.screen_generator = ScreenGenerator(config)
        self.renderer = VideoRenderer(config)
        self.compositor = VideoCompositor(config)
    
    async def process_video(self, track: Track) -> Track:
        """
        Process video for a track, including screen generation, rendering, and composition.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Processing video for {track.base_name}")
        
        try:
            # Skip if final video already exists and we're not forcing regeneration
            if track.final_video and os.path.isfile(track.final_video) and not self.config.force_regenerate:
                self.logger.info(f"Final video already exists for {track.base_name}, skipping video processing")
                return track
            
            # Generate screens
            track = await self.generate_screens(track)
            
            # Render videos
            track = await self.render_videos(track)
            
            # Compose final video
            track = await self.compose_final_video(track)
            
            # Create additional versions
            track = await self.create_additional_versions(track)
            
            return track
            
        except Exception as e:
            self.logger.error(f"Failed to process video for {track.base_name}: {str(e)}")
            # Continue with other processing
            return track
    
    async def generate_screens(self, track: Track) -> Track:
        """
        Generate title and end screens for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated screen information
        """
        self.logger.info(f"Generating screens for {track.base_name}")
        
        try:
            # Generate title screen
            if not track.title_video or not os.path.isfile(track.title_video) or self.config.force_regenerate:
                track = await self.screen_generator.generate_title_screen(track)
            else:
                self.logger.info(f"Title screen already exists: {track.title_video}")
            
            # Generate end screen
            if not track.end_video or not os.path.isfile(track.end_video) or self.config.force_regenerate:
                track = await self.screen_generator.generate_end_screen(track)
            else:
                self.logger.info(f"End screen already exists: {track.end_video}")
            
            return track
            
        except Exception as e:
            self.logger.error(f"Failed to generate screens for {track.base_name}: {str(e)}")
            # Continue with other processing
            return track
    
    async def render_videos(self, track: Track) -> Track:
        """
        Render videos for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        self.logger.info(f"Rendering videos for {track.base_name}")
        
        try:
            # Render lyrics video
            if (not track.video_with_lyrics or not os.path.isfile(track.video_with_lyrics) or 
                self.config.force_regenerate):
                track = await self.renderer.render_lyrics_video(track)
            else:
                self.logger.info(f"Lyrics video already exists: {track.video_with_lyrics}")
            
            # Render instrumental video
            if (not track.video_with_instrumental or not os.path.isfile(track.video_with_instrumental) or 
                self.config.force_regenerate):
                track = await self.renderer.render_instrumental_video(track)
            else:
                self.logger.info(f"Instrumental video already exists: {track.video_with_instrumental}")
            
            return track
            
        except Exception as e:
            self.logger.error(f"Failed to render videos for {track.base_name}: {str(e)}")
            # Continue with other processing
            return track
    
    async def compose_final_video(self, track: Track) -> Track:
        """
        Compose the final video for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated final video information
        """
        self.logger.info(f"Composing final video for {track.base_name}")
        
        try:
            # Skip if final video already exists
            if track.final_video and os.path.isfile(track.final_video) and not self.config.force_regenerate:
                self.logger.info(f"Final video already exists: {track.final_video}")
                return track
            
            # Check for required videos
            if not track.title_video or not os.path.isfile(track.title_video):
                self.logger.warning(f"Title video not found for {track.base_name}")
                return track
            
            if not track.video_with_lyrics and not track.video_with_instrumental:
                self.logger.warning(f"No content videos found for {track.base_name}")
                return track
            
            # Compose final video
            track = await self.compositor.compose_final_video(track)
            
            return track
            
        except Exception as e:
            self.logger.error(f"Failed to compose final video for {track.base_name}: {str(e)}")
            # Continue with other processing
            return track
    
    async def create_additional_versions(self, track: Track) -> Track:
        """
        Create additional versions of the final video.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video version information
        """
        self.logger.info(f"Creating additional video versions for {track.base_name}")
        
        try:
            # Skip if no final video
            if not track.final_video or not os.path.isfile(track.final_video):
                self.logger.warning(f"No final video found for {track.base_name}")
                return track
            
            # Create lossless version
            if not track.final_video_mkv or not os.path.isfile(track.final_video_mkv) or self.config.force_regenerate:
                track = await self.compositor.create_lossless_version(track)
            else:
                self.logger.info(f"Lossless version already exists: {track.final_video_mkv}")
            
            # Create 720p version
            if not track.final_video_720p or not os.path.isfile(track.final_video_720p) or self.config.force_regenerate:
                track = await self.compositor.create_720p_version(track)
            else:
                self.logger.info(f"720p version already exists: {track.final_video_720p}")
            
            # Create lossy version
            if not track.final_video_lossy or not os.path.isfile(track.final_video_lossy) or self.config.force_regenerate:
                track = await self.compositor.create_lossy_version(track)
            else:
                self.logger.info(f"Lossy version already exists: {track.final_video_lossy}")
            
            return track
            
        except Exception as e:
            self.logger.error(f"Failed to create additional versions for {track.base_name}: {str(e)}")
            # Continue with other processing
            return track
    
    async def cleanup(self):
        """
        Perform cleanup operations for the video service.
        """
        self.logger.info("Cleaning up video service resources")
        
        # Clean up temporary files
        if self.config.cleanup_temp_files:
            self.logger.info("Cleaning up temporary video files")
            # Implementation would depend on what temporary files are created
        
        # Close any open resources
        if hasattr(self, 'screen_generator'):
            await self.screen_generator.cleanup()
        
        if hasattr(self, 'renderer'):
            await self.renderer.cleanup()
        
        if hasattr(self, 'compositor'):
            await self.compositor.cleanup()
        
        self.logger.info("Video service cleanup complete") 