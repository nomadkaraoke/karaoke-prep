import os
import asyncio
import subprocess
from typing import List, Optional
from pydub import AudioSegment
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import AudioError


class AudioMixer:
    """
    Handles audio mixing operations.
    """
    
    def __init__(self, config):
        """
        Initialize the audio mixer.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
        
        # Set up ffmpeg base command
        self.ffmpeg_base_command = "ffmpeg -hide_banner"
        if self.config.log_level <= 10:  # DEBUG
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"
    
    async def mix_audio_files(self, input_files: List[str], output_file: str, weights: Optional[List[float]] = None):
        """
        Mix multiple audio files into a single output file.
        
        Args:
            input_files: List of input audio file paths
            output_file: Output file path
            weights: Optional list of weights for each input file (default: equal weights)
            
        Returns:
            The path to the mixed audio file
        """
        self.logger.info(f"Mixing {len(input_files)} audio files into {output_file}")
        
        # Validate inputs
        if not input_files:
            raise AudioError("No input files provided for mixing")
        
        for input_file in input_files:
            if not os.path.isfile(input_file):
                raise AudioError(f"Input file not found: {input_file}")
        
        # Set default weights if not provided
        if weights is None:
            weights = [1.0] * len(input_files)
        
        # Ensure weights match input files
        if len(weights) != len(input_files):
            raise AudioError(f"Number of weights ({len(weights)}) does not match number of input files ({len(input_files)})")
        
        # Build ffmpeg command
        input_args = " ".join([f'-i "{input_file}"' for input_file in input_files])
        weight_str = " ".join([str(w) for w in weights])
        
        filter_complex = f'"'
        for i in range(len(input_files)):
            filter_complex += f"[{i}:a]"
        filter_complex += f"amix=inputs={len(input_files)}:duration=longest:weights={weight_str}[outa]"
        filter_complex += f'"'
        
        output_format = os.path.splitext(output_file)[1][1:].lower()
        if not output_format:
            output_format = self.config.lossless_output_format.lower()
        
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} {input_args} '
            f'-filter_complex {filter_complex} '
            f'-map "[outa]" -c:a {output_format} "{output_file}"'
        )
        
        # Execute command
        if not self.config.dry_run:
            self.logger.debug(f"Running command: {ffmpeg_command}")
            
            try:
                process = await asyncio.create_subprocess_shell(
                    ffmpeg_command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise AudioError(f"Failed to mix audio files: {error_message}")
                
                self.logger.info(f"Successfully mixed audio files to {output_file}")
                return output_file
                
            except Exception as e:
                raise AudioError(f"Error mixing audio files: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would mix audio files to {output_file}")
            return output_file
    
    async def mix_audio(self, track):
        """
        Mix audio for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated mixed audio information
        """
        self.logger.info(f"Mixing audio for {track.base_name}")
        
        # Skip if no separated audio
        if not track.separated_audio["clean_instrumental"].get("instrumental"):
            self.logger.info("No instrumental available for mixing, skipping")
            return track
        
        # Mix instrumental with backing vocals if available
        if track.separated_audio["backing_vocals"]:
            for model, paths in track.separated_audio["backing_vocals"].items():
                if "backing_vocals" not in paths:
                    continue
                
                instrumental_path = track.separated_audio["clean_instrumental"]["instrumental"]
                backing_vocals_path = paths["backing_vocals"]
                
                output_path = os.path.join(
                    track.track_output_dir,
                    f"{track.base_name} (Karaoke Mix {model}).{self.config.lossless_output_format.lower()}"
                )
                
                # Skip if output already exists
                if os.path.isfile(output_path):
                    self.logger.info(f"Mixed audio for model {model} already exists")
                    track.metadata[f"karaoke_mix_{model}"] = output_path
                    continue
                
                # Mix files
                try:
                    mixed_path = await self.mix_audio_files(
                        [instrumental_path, backing_vocals_path],
                        output_path,
                        weights=[1.0, 0.8]  # Slightly reduce backing vocals volume
                    )
                    
                    track.metadata[f"karaoke_mix_{model}"] = mixed_path
                    self.logger.info(f"Created karaoke mix for model {model}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to create karaoke mix for model {model}: {str(e)}")
        
        return track
    
    async def generate_combined_instrumentals(self, track, stems_dir):
        """
        Generate combined instrumental tracks by mixing different stems.
        
        Args:
            track: The track to process
            stems_dir: The directory containing stems
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Generating combined instrumentals for {track.base_name}")
        
        # Skip if no clean instrumental
        if not track.separated_audio.get("clean_instrumental", {}).get("instrumental"):
            self.logger.info("No clean instrumental available, skipping combined instrumentals")
            track.separated_audio["combined_instrumentals"] = {}
            return track
        
        # Initialize combined instrumentals
        track.separated_audio["combined_instrumentals"] = {}
        
        # Get clean instrumental path
        instrumental_path = track.separated_audio["clean_instrumental"]["instrumental"]
        
        # Get backing vocals path if available
        backing_vocals_path = None
        for model_name, stems in track.separated_audio.get("backing_vocals", {}).items():
            if stems.get("backing_vocals"):
                backing_vocals_path = stems["backing_vocals"]
                break
        
        # Generate instrumental with backing vocals if available
        if backing_vocals_path:
            output_path = os.path.join(
                stems_dir, 
                f"{track.base_name} (Instrumental with Backing Vocals).{self.config.lossless_output_format.lower()}"
            )
            
            # Skip if output already exists
            if os.path.isfile(output_path):
                self.logger.info(f"Instrumental with backing vocals already exists: {output_path}")
                track.separated_audio["combined_instrumentals"]["instrumental_with_backing_vocals"] = output_path
            else:
                # Mix instrumental and backing vocals
                if not self.config.dry_run:
                    try:
                        await self._mix_audio_files(
                            [instrumental_path, backing_vocals_path],
                            output_path
                        )
                        track.separated_audio["combined_instrumentals"]["instrumental_with_backing_vocals"] = output_path
                    except Exception as e:
                        self.logger.error(f"Failed to mix instrumental with backing vocals: {str(e)}")
                else:
                    self.logger.info(f"[DRY RUN] Would mix instrumental with backing vocals: {output_path}")
                    track.separated_audio["combined_instrumentals"]["instrumental_with_backing_vocals"] = output_path
        
        # Generate other combined instrumentals from demucs stems if available
        demucs_stems = {}
        for model_name, stems in track.separated_audio.get("other_stems", {}).items():
            if "demucs" in model_name.lower():
                demucs_stems = stems
                break
        
        if demucs_stems:
            # Mix drums + bass + other (no vocals)
            if all(stem in demucs_stems for stem in ["drums", "bass", "other"]):
                output_path = os.path.join(
                    stems_dir, 
                    f"{track.base_name} (Demucs Instrumental).{self.config.lossless_output_format.lower()}"
                )
                
                # Skip if output already exists
                if os.path.isfile(output_path):
                    self.logger.info(f"Demucs instrumental already exists: {output_path}")
                    track.separated_audio["combined_instrumentals"]["demucs_instrumental"] = output_path
                else:
                    # Mix drums, bass, and other
                    if not self.config.dry_run:
                        try:
                            await self._mix_audio_files(
                                [demucs_stems["drums"], demucs_stems["bass"], demucs_stems["other"]],
                                output_path
                            )
                            track.separated_audio["combined_instrumentals"]["demucs_instrumental"] = output_path
                        except Exception as e:
                            self.logger.error(f"Failed to mix demucs instrumental: {str(e)}")
                    else:
                        self.logger.info(f"[DRY RUN] Would mix demucs instrumental: {output_path}")
                        track.separated_audio["combined_instrumentals"]["demucs_instrumental"] = output_path
        
        return track
    
    async def _mix_audio_files(self, input_paths, output_path):
        """
        Mix multiple audio files together.
        
        Args:
            input_paths: List of input audio file paths
            output_path: Output audio file path
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Load first audio file
            mixed = AudioSegment.from_file(input_paths[0])
            
            # Mix in additional audio files
            for path in input_paths[1:]:
                audio = AudioSegment.from_file(path)
                mixed = mixed.overlay(audio)
            
            # Export mixed audio
            mixed.export(output_path, format=os.path.splitext(output_path)[1][1:])
            
            self.logger.info(f"Successfully mixed audio files: {output_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to mix audio files: {str(e)}")
            raise AudioError(f"Failed to mix audio files: {str(e)}") from e 