import os
import asyncio
import subprocess
from pydub import AudioSegment
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import AudioError


class AudioNormalizer:
    """
    Handles audio normalization operations.
    """
    
    def __init__(self, config):
        """
        Initialize the audio normalizer.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
        
        # Path to ffmpeg
        self.ffmpeg_path = "ffmpeg"
        
        # Set up ffmpeg base command
        self.ffmpeg_base_command = f"{self.ffmpeg_path} -hide_banner -nostats"
        
        if self.config.log_level <= 10:  # DEBUG
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"
    
    async def normalize_audio_file(self, input_path, output_path, target_level=0.0):
        """
        Normalize an audio file to a target level.
        
        Args:
            input_path: The input audio file path
            output_path: The output audio file path
            target_level: The target level in dB (default: 0.0)
            
        Returns:
            The path to the normalized audio file
        """
        self.logger.info(f"Normalizing audio file: {input_path}")
        
        # Validate input
        if not os.path.isfile(input_path):
            raise AudioError(f"Input file not found: {input_path}")
        
        if os.path.getsize(input_path) == 0:
            raise AudioError(f"Input file is empty: {input_path}")
        
        # Skip if dry run
        if self.config.dry_run:
            self.logger.info(f"[DRY RUN] Would normalize audio file: {input_path}")
            return output_path
        
        try:
            # Load audio file
            audio = AudioSegment.from_file(input_path)
            
            # Calculate the peak amplitude
            peak_amplitude = float(audio.max_dBFS)
            
            # Calculate the necessary gain
            gain_db = target_level - peak_amplitude
            
            # Apply gain
            normalized_audio = audio.apply_gain(gain_db)
            
            # Ensure the audio is not completely silent
            if normalized_audio.rms == 0:
                self.logger.warning(f"Normalized audio is silent for {input_path}. Using original audio.")
                normalized_audio = audio
            
            # Export normalized audio
            normalized_audio.export(
                output_path, 
                format=self.config.lossless_output_format.lower()
            )
            
            self.logger.info(f"Normalized audio saved to: {output_path}")
            self.logger.debug(f"Original peak: {peak_amplitude} dB, Applied gain: {gain_db} dB")
            
            return output_path
            
        except Exception as e:
            raise AudioError(f"Failed to normalize audio file: {str(e)}") from e
    
    async def normalize_audio(self, track):
        """
        Normalize audio for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with normalized audio
        """
        self.logger.info(f"Normalizing audio for {track.base_name}")
        
        files_to_normalize = []
        
        # Add clean instrumental
        if track.separated_audio["clean_instrumental"].get("instrumental"):
            files_to_normalize.append(
                ("clean_instrumental", track.separated_audio["clean_instrumental"]["instrumental"])
            )
        
        # Add combined instrumentals
        for model, path in track.separated_audio["combined_instrumentals"].items():
            files_to_normalize.append(("combined_instrumentals", path))
        
        # Add karaoke mixes
        for key, path in track.metadata.items():
            if key.startswith("karaoke_mix_") and os.path.isfile(path):
                files_to_normalize.append(("karaoke_mix", path))
        
        # Skip if no files to normalize
        if not files_to_normalize:
            self.logger.info("No files to normalize, skipping")
            return track
        
        # Normalize each file
        for key, file_path in files_to_normalize:
            if os.path.isfile(file_path):
                try:
                    # Normalize in-place
                    await self.normalize_audio_file(file_path, file_path)
                    
                    # Verify the normalized file
                    if os.path.getsize(file_path) > 0:
                        self.logger.info(f"Successfully normalized: {file_path}")
                    else:
                        raise AudioError("Normalized file is empty")
                        
                except Exception as e:
                    self.logger.error(f"Error during normalization of {file_path}: {e}")
                    self.logger.warning(f"Normalization failed for {file_path}. Original file remains unchanged.")
            else:
                self.logger.warning(f"File not found for normalization: {file_path}")
        
        self.logger.info("Audio normalization process completed")
        return track
    
    async def normalize_audio_files(self, track):
        """
        Normalize all separated audio files.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Normalizing audio files for {track.base_name}")
        
        # Skip if no separated audio
        if not track.separated_audio:
            self.logger.info("No separated audio to normalize")
            return track
        
        # Normalize clean instrumental
        if track.separated_audio.get("clean_instrumental"):
            instrumental_path = track.separated_audio["clean_instrumental"].get("instrumental")
            if instrumental_path and os.path.isfile(instrumental_path):
                normalized_path = self._get_normalized_path(instrumental_path)
                await self._normalize_audio(instrumental_path, normalized_path)
                track.separated_audio["clean_instrumental"]["instrumental"] = normalized_path
            
            vocals_path = track.separated_audio["clean_instrumental"].get("vocals")
            if vocals_path and os.path.isfile(vocals_path):
                normalized_path = self._get_normalized_path(vocals_path)
                await self._normalize_audio(vocals_path, normalized_path)
                track.separated_audio["clean_instrumental"]["vocals"] = normalized_path
        
        # Normalize backing vocals
        for model_name, stems in track.separated_audio.get("backing_vocals", {}).items():
            lead_vocals_path = stems.get("lead_vocals")
            if lead_vocals_path and os.path.isfile(lead_vocals_path):
                normalized_path = self._get_normalized_path(lead_vocals_path)
                await self._normalize_audio(lead_vocals_path, normalized_path)
                track.separated_audio["backing_vocals"][model_name]["lead_vocals"] = normalized_path
            
            backing_vocals_path = stems.get("backing_vocals")
            if backing_vocals_path and os.path.isfile(backing_vocals_path):
                normalized_path = self._get_normalized_path(backing_vocals_path)
                await self._normalize_audio(backing_vocals_path, normalized_path)
                track.separated_audio["backing_vocals"][model_name]["backing_vocals"] = normalized_path
        
        # Normalize other stems
        for model_name, stems in track.separated_audio.get("other_stems", {}).items():
            for stem_name, stem_path in stems.items():
                if stem_path and os.path.isfile(stem_path):
                    normalized_path = self._get_normalized_path(stem_path)
                    await self._normalize_audio(stem_path, normalized_path)
                    track.separated_audio["other_stems"][model_name][stem_name] = normalized_path
        
        # Normalize combined instrumentals
        for name, path in track.separated_audio.get("combined_instrumentals", {}).items():
            if path and os.path.isfile(path):
                normalized_path = self._get_normalized_path(path)
                await self._normalize_audio(path, normalized_path)
                track.separated_audio["combined_instrumentals"][name] = normalized_path
        
        return track
    
    def _get_normalized_path(self, input_path):
        """
        Get the path for the normalized audio file.
        
        Args:
            input_path: The input audio file path
            
        Returns:
            The path for the normalized audio file
        """
        # Replace extension with .normalized.ext
        base, ext = os.path.splitext(input_path)
        return f"{base}.normalized{ext}"
    
    async def _normalize_audio(self, input_path, output_path, target_level=-14.0):
        """
        Normalize an audio file to a target loudness level.
        
        Args:
            input_path: The input audio file path
            output_path: The output audio file path
            target_level: The target loudness level in LUFS
            
        Returns:
            True if successful, False otherwise
        """
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.debug(f"Normalized audio already exists: {output_path}")
            return True
        
        # Skip if input doesn't exist
        if not os.path.isfile(input_path):
            self.logger.warning(f"Input audio file not found: {input_path}")
            return False
        
        # Build ffmpeg command
        command = (
            f'{self.ffmpeg_base_command} -i "{input_path}" '
            f'-af loudnorm=I={target_level}:TP=-1.0:LRA=11.0:print_format=json '
            f'-f null -'
        )
        
        # Execute command to get loudness stats
        if not self.config.dry_run:
            try:
                self.logger.debug(f"Analyzing audio loudness: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    self.logger.error(f"Failed to analyze audio loudness: {stderr.decode()}")
                    return False
                
                # Extract loudnorm stats from stderr
                stderr_text = stderr.decode()
                stats_start = stderr_text.rfind("{")
                stats_end = stderr_text.rfind("}") + 1
                
                if stats_start >= 0 and stats_end > stats_start:
                    loudness_stats = stderr_text[stats_start:stats_end]
                    
                    # Build second pass command with measured stats
                    command = (
                        f'{self.ffmpeg_base_command} -i "{input_path}" '
                        f'-af loudnorm=I={target_level}:TP=-1.0:LRA=11.0:measured_I={target_level}:measured_TP=-1.0:measured_LRA=11.0:measured_thresh=-25.0:offset=0.0:linear=true:print_format=json '
                        f'"{output_path}"'
                    )
                    
                    # Execute second pass command
                    self.logger.debug(f"Normalizing audio: {command}")
                    process = await asyncio.create_subprocess_shell(
                        command,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        self.logger.error(f"Failed to normalize audio: {stderr.decode()}")
                        return False
                    
                    self.logger.info(f"Successfully normalized audio: {output_path}")
                    return True
                else:
                    self.logger.error("Failed to extract loudness stats from ffmpeg output")
                    return False
                
            except Exception as e:
                self.logger.error(f"Failed to normalize audio: {str(e)}")
                return False
        else:
            self.logger.info(f"[DRY RUN] Would normalize audio: {output_path}")
            return True 