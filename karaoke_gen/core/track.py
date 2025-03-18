from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import os


@dataclass
class Track:
    """
    Represents a track being processed through the karaoke generation pipeline.
    This class holds all the data related to a single track throughout its lifecycle.
    """
    # Basic track information
    artist: Optional[str] = None
    title: Optional[str] = None
    input_media: Optional[str] = None
    
    # Paths to generated files
    track_output_dir: Optional[str] = None
    input_audio_wav: Optional[str] = None
    input_still_image: Optional[str] = None
    
    # Lyrics information
    lyrics: Optional[str] = None
    processed_lyrics: Optional[str] = None
    
    # Separated audio files
    separated_audio: Dict[str, Any] = field(default_factory=lambda: {
        "clean_instrumental": {},
        "other_stems": {},
        "backing_vocals": {},
        "combined_instrumentals": {}
    })
    
    # Video files
    title_video: Optional[str] = None
    end_video: Optional[str] = None
    video_with_lyrics: Optional[str] = None
    video_with_instrumental: Optional[str] = None
    
    # Final output files
    final_video: Optional[str] = None
    final_video_mkv: Optional[str] = None
    final_video_lossy: Optional[str] = None
    final_video_720p: Optional[str] = None
    final_karaoke_cdg_zip: Optional[str] = None
    final_karaoke_txt_zip: Optional[str] = None
    
    # Distribution information
    brand_code: Optional[str] = None
    new_brand_code_dir_path: Optional[str] = None
    youtube_url: Optional[str] = None
    brand_code_dir_sharing_link: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def base_name(self) -> str:
        """Returns the base name for the track (artist - title)"""
        if self.artist and self.title:
            return f"{self.artist} - {self.title}"
        return os.path.basename(self.input_media) if self.input_media else "unknown"
    
    @property
    def is_url(self) -> bool:
        """Returns True if the input_media is a URL"""
        if not self.input_media:
            return False
        return self.input_media.startswith("http://") or self.input_media.startswith("https://")
    
    @property
    def is_file(self) -> bool:
        """Returns True if the input_media is a file"""
        if not self.input_media:
            return False
        return os.path.isfile(self.input_media)
    
    @property
    def is_directory(self) -> bool:
        """Returns True if the input_media is a directory"""
        if not self.input_media:
            return False
        return os.path.isdir(self.input_media)
    
    @property
    def instrumental(self) -> Optional[str]:
        """Returns the path to the instrumental audio file"""
        if self.separated_audio and "clean_instrumental" in self.separated_audio:
            return self.separated_audio["clean_instrumental"].get("instrumental")
        return None
    
    @property
    def duration(self) -> float:
        """Returns the duration of the track in seconds"""
        if self.metadata and "duration" in self.metadata:
            return self.metadata["duration"]
        return 0.0
    
    @property
    def audio_file(self) -> Optional[str]:
        """Returns the path to the input audio file (WAV)"""
        return self.input_audio_wav
    
    @property
    def wav_file(self) -> Optional[str]:
        """Alias for input_audio_wav"""
        return self.input_audio_wav
    
    @property
    def video_with_vocals(self) -> Optional[str]:
        """Alias for video_with_lyrics for backward compatibility"""
        return self.video_with_lyrics 