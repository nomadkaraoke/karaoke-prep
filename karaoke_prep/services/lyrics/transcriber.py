import os
import shutil
from dotenv import load_dotenv
from lyrics_transcriber import LyricsTranscriber as LyricsTranscriberLib
from lyrics_transcriber import OutputConfig, TranscriberConfig, LyricsConfig
from lyrics_transcriber.core.controller import LyricsControllerResult
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import TranscriptionError


class LyricsTranscriber:
    """
    Handles lyrics transcription and synchronization.
    """
    
    def __init__(self, config):
        """
        Initialize the lyrics transcriber.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
    
    async def transcribe_lyrics(self, track):
        """
        Transcribe lyrics for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated transcription information
        """
        self.logger.info(f"Transcribing lyrics for {track.base_name}")
        
        if not track.input_audio_wav or not os.path.exists(track.input_audio_wav):
            self.logger.warning("No input audio file found, cannot transcribe")
            return track
        
        try:
            # Check for existing files first using sanitized names
            parent_video_path = os.path.join(track.track_output_dir, f"{track.base_name} (With Vocals).mkv")
            parent_lrc_path = os.path.join(track.track_output_dir, f"{track.base_name} (Karaoke).lrc")
            
            # Check lyrics directory for existing files
            lyrics_dir = os.path.join(track.track_output_dir, "lyrics")
            lyrics_video_path = os.path.join(lyrics_dir, f"{track.base_name} (With Vocals).mkv")
            lyrics_lrc_path = os.path.join(lyrics_dir, f"{track.base_name} (Karaoke).lrc")
            
            # If files exist in parent directory, return early
            if os.path.exists(parent_video_path) and os.path.exists(parent_lrc_path):
                self.logger.info(f"Found existing video and LRC files in parent directory, skipping transcription")
                track.processed_lyrics = {
                    "lrc_filepath": parent_lrc_path,
                    "ass_filepath": parent_video_path,
                }
                return track
            
            # If files exist in lyrics directory, copy to parent and return
            if os.path.exists(lyrics_video_path) and os.path.exists(lyrics_lrc_path):
                self.logger.info(f"Found existing video and LRC files in lyrics directory, copying to parent")
                os.makedirs(track.track_output_dir, exist_ok=True)
                shutil.copy2(lyrics_video_path, parent_video_path)
                shutil.copy2(lyrics_lrc_path, parent_lrc_path)
                track.processed_lyrics = {
                    "lrc_filepath": parent_lrc_path,
                    "ass_filepath": parent_video_path,
                }
                return track
            
            # Create lyrics subdirectory for new transcription
            os.makedirs(lyrics_dir, exist_ok=True)
            self.logger.info(f"Created lyrics directory: {lyrics_dir}")
            
            # Load environment variables
            load_dotenv()
            env_config = {
                "audioshake_api_token": os.getenv("AUDIOSHAKE_API_TOKEN"),
                "genius_api_token": os.getenv("GENIUS_API_TOKEN"),
                "spotify_cookie": os.getenv("SPOTIFY_COOKIE_SP_DC"),
                "runpod_api_key": os.getenv("RUNPOD_API_KEY"),
                "whisper_runpod_id": os.getenv("WHISPER_RUNPOD_ID"),
            }
            
            # Create config objects for LyricsTranscriber
            transcriber_config = TranscriberConfig(
                audioshake_api_token=env_config.get("audioshake_api_token"),
            )
            
            lyrics_config = LyricsConfig(
                genius_api_token=env_config.get("genius_api_token"),
                spotify_cookie=env_config.get("spotify_cookie"),
                lyrics_file=track.lyrics,
            )
            
            output_config = OutputConfig(
                output_styles_json=self.config.style_params_json,
                output_dir=lyrics_dir,
                render_video=self.config.render_video,
                fetch_lyrics=True,
                run_transcription=not self.config.skip_transcription,
                run_correction=True,
                generate_plain_text=True,
                generate_lrc=True,
                generate_cdg=True,
                video_resolution="4k",
                enable_review=not self.config.skip_transcription_review,
                subtitle_offset_ms=self.config.subtitle_offset_ms,
            )
            
            # Add this log entry to debug the OutputConfig
            self.logger.info(f"Instantiating LyricsTranscriber with OutputConfig: {output_config}")
            
            # Initialize transcriber with new config objects
            transcriber = LyricsTranscriberLib(
                audio_filepath=track.input_audio_wav,
                artist=track.artist,
                title=track.title,
                transcriber_config=transcriber_config,
                lyrics_config=lyrics_config,
                output_config=output_config,
                logger=self.logger,
            )
            
            # Process and get results
            results: LyricsControllerResult = transcriber.process()
            self.logger.info(f"Transcriber Results Filepaths:")
            for key, value in results.__dict__.items():
                if key.endswith("_filepath"):
                    self.logger.info(f"  {key}: {value}")
            
            # Build output dictionary
            transcriber_outputs = {}
            if results.lrc_filepath:
                transcriber_outputs["lrc_filepath"] = results.lrc_filepath
                self.logger.info(f"Moving LRC file from {results.lrc_filepath} to {parent_lrc_path}")
                shutil.copy2(results.lrc_filepath, parent_lrc_path)
            
            if results.video_filepath:
                transcriber_outputs["video_filepath"] = results.video_filepath
                self.logger.info(f"Moving video file from {results.video_filepath} to {parent_video_path}")
                shutil.copy2(results.video_filepath, parent_video_path)
            
            if results.ass_filepath:
                transcriber_outputs["ass_filepath"] = results.ass_filepath
            
            if results.transcription_corrected:
                transcriber_outputs["corrected_lyrics_text"] = "\n".join(
                    segment.text for segment in results.transcription_corrected.corrected_segments
                )
                transcriber_outputs["corrected_lyrics_text_filepath"] = results.corrected_txt
            
            if transcriber_outputs:
                self.logger.info(f"*** Transcriber Filepath Outputs: ***")
                for key, value in transcriber_outputs.items():
                    if key.endswith("_filepath"):
                        self.logger.info(f"  {key}: {value}")
            
            track.processed_lyrics = transcriber_outputs
            return track
            
        except Exception as e:
            raise TranscriptionError(f"Failed to transcribe lyrics: {str(e)}") from e 