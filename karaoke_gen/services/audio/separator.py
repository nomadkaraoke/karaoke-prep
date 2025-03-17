import os
import asyncio
import json
import time
import fcntl
import errno
import tempfile
import shutil
from datetime import datetime
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import AudioError
import platform
import subprocess
import logging
from typing import Dict, List, Optional, Any


class AudioSeparator:
    """
    Handles audio stem separation operations.
    """
    
    def __init__(self, config):
        """
        Initialize the audio separator.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
        
        # Initialize separator lazily to avoid circular imports
        self._separator = None
    
    @property
    def separator(self):
        """Lazy-loaded separator instance"""
        if self._separator is None:
            # Import here to avoid circular imports
            from audio_separator.separator import Separator
            
            self._separator = Separator(
                log_level=self.config.log_level,
                log_formatter=self.config.log_formatter,
                model_file_dir=self.config.model_file_dir,
                output_format=self.config.lossless_output_format,
            )
        
        return self._separator
    
    async def separate_clean_instrumental(self, track, input_audio, stems_dir):
        """
        Separate clean instrumental from a track.
        
        Args:
            track: The track to process
            input_audio: The input audio file
            stems_dir: The directory to store stems
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Separating clean instrumental for {track.base_name}")
        
        # Skip if existing instrumental is provided
        if self.config.existing_instrumental:
            self.logger.info(f"Using existing instrumental: {self.config.existing_instrumental}")
            track.separated_audio["clean_instrumental"] = {
                "instrumental": self.config.existing_instrumental,
                "vocals": None
            }
            return track
        
        # Acquire lock for audio separation
        with self._acquire_lock(track.base_name):
            artist_title = track.base_name
            
            # Define output paths
            instrumental_path = os.path.join(
                stems_dir, 
                f"{artist_title} (Clean Instrumental).{self.config.lossless_output_format.lower()}"
            )
            vocals_path = os.path.join(
                stems_dir, 
                f"{artist_title} (Clean Vocals).{self.config.lossless_output_format.lower()}"
            )
            
            # Skip if output already exists
            if os.path.isfile(instrumental_path) and os.path.isfile(vocals_path):
                self.logger.info(f"Clean instrumental and vocals already exist")
                track.separated_audio["clean_instrumental"] = {
                    "instrumental": instrumental_path,
                    "vocals": vocals_path
                }
                return track
            
            # Perform separation
            if not self.config.dry_run:
                try:
                    self.logger.info(f"Separating clean instrumental using model: {self.config.clean_instrumental_model}")
                    
                    separation_result = await self.separator.separate(
                        input_path=input_audio,
                        output_path=stems_dir,
                        model_name=self.config.clean_instrumental_model,
                        filename_prefix=f"{artist_title} (Clean",
                        output_format=self.config.lossless_output_format.lower()
                    )
                    
                    # Update track with separation results
                    track.separated_audio["clean_instrumental"] = {
                        "instrumental": separation_result["instrumental"],
                        "vocals": separation_result["vocals"]
                    }
                    
                    self.logger.info(f"Successfully separated clean instrumental")
                    
                except Exception as e:
                    raise AudioError(f"Failed to separate clean instrumental: {str(e)}") from e
            else:
                self.logger.info(f"[DRY RUN] Would separate clean instrumental")
                track.separated_audio["clean_instrumental"] = {
                    "instrumental": instrumental_path,
                    "vocals": vocals_path
                }
        
        return track
    
    async def separate_other_stems(self, track, input_audio, stems_dir):
        """
        Separate other stems from the input audio.
        
        Args:
            track: The track to process
            input_audio: The input audio file
            stems_dir: The directory to store stems
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Separating other stems for {track.base_name}")
        
        # Skip if no models are specified
        if not self.config.other_stems_models:
            self.logger.info("No other stems models specified, skipping")
            track.separated_audio["other_stems"] = {}
            return track
        
        # Acquire lock for audio separation
        with self._acquire_lock(track.base_name):
            artist_title = track.base_name
            
            # Initialize results
            track.separated_audio["other_stems"] = {}
            
            # Process each model
            for model_name in self.config.other_stems_models:
                self.logger.info(f"Separating stems using model: {model_name}")
                
                # Define output paths based on model
                if "demucs" in model_name.lower():
                    stems = ["drums", "bass", "other", "vocals"]
                    output_paths = {
                        stem: os.path.join(
                            stems_dir, 
                            f"{artist_title} (Demucs {stem.capitalize()}).{self.config.lossless_output_format.lower()}"
                        ) for stem in stems
                    }
                else:
                    # Default to 2-stem separation
                    stems = ["instrumental", "vocals"]
                    output_paths = {
                        stem: os.path.join(
                            stems_dir, 
                            f"{artist_title} ({model_name} {stem.capitalize()}).{self.config.lossless_output_format.lower()}"
                        ) for stem in stems
                    }
                
                # Check if all output files already exist
                if all(os.path.isfile(path) for path in output_paths.values()):
                    self.logger.info(f"All stems for model {model_name} already exist")
                    track.separated_audio["other_stems"][model_name] = output_paths
                    continue
                
                # Perform separation
                if not self.config.dry_run:
                    try:
                        separation_result = await self.separator.separate(
                            input_path=input_audio,
                            output_path=stems_dir,
                            model_name=model_name,
                            filename_prefix=f"{artist_title} ({model_name}",
                            output_format=self.config.lossless_output_format.lower()
                        )
                        
                        # Update track with separation results
                        track.separated_audio["other_stems"][model_name] = separation_result
                        
                        self.logger.info(f"Successfully separated stems using model: {model_name}")
                        
                    except Exception as e:
                        self.logger.error(f"Failed to separate stems using model {model_name}: {str(e)}")
                        # Continue with other models
                else:
                    self.logger.info(f"[DRY RUN] Would separate stems using model: {model_name}")
                    track.separated_audio["other_stems"][model_name] = output_paths
        
        return track
    
    async def separate_backing_vocals(self, track, stems_dir):
        """
        Separate backing vocals from the clean vocals.
        
        Args:
            track: The track to process
            stems_dir: The directory to store stems
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Separating backing vocals for {track.base_name}")
        
        # Skip if no models are specified or no clean vocals
        if not self.config.backing_vocals_models or not track.separated_audio["clean_instrumental"].get("vocals"):
            self.logger.info("No backing vocals models specified or no clean vocals available, skipping")
            track.separated_audio["backing_vocals"] = {}
            return track
        
        # Get vocals path
        vocals_path = track.separated_audio["clean_instrumental"]["vocals"]
        
        # Acquire lock for audio separation
        with self._acquire_lock(track.base_name):
            artist_title = track.base_name
            
            # Initialize results
            track.separated_audio["backing_vocals"] = {}
            
            # Process each model
            for model_name in self.config.backing_vocals_models:
                self.logger.info(f"Separating backing vocals using model: {model_name}")
                
                # Define output paths
                lead_vocals_path = os.path.join(
                    stems_dir, 
                    f"{artist_title} (Lead Vocals).{self.config.lossless_output_format.lower()}"
                )
                backing_vocals_path = os.path.join(
                    stems_dir, 
                    f"{artist_title} (Backing Vocals).{self.config.lossless_output_format.lower()}"
                )
                
                # Check if output files already exist
                if os.path.isfile(lead_vocals_path) and os.path.isfile(backing_vocals_path):
                    self.logger.info(f"Backing vocals already exist")
                    track.separated_audio["backing_vocals"][model_name] = {
                        "lead_vocals": lead_vocals_path,
                        "backing_vocals": backing_vocals_path
                    }
                    continue
                
                # Perform separation
                if not self.config.dry_run:
                    try:
                        separation_result = await self.separator.separate(
                            input_path=vocals_path,
                            output_path=stems_dir,
                            model_name=model_name,
                            filename_prefix=f"{artist_title}",
                            output_format=self.config.lossless_output_format.lower(),
                            stem_mapping={
                                "vocals": "lead_vocals",
                                "instrumental": "backing_vocals"
                            }
                        )
                        
                        # Update track with separation results
                        track.separated_audio["backing_vocals"][model_name] = {
                            "lead_vocals": separation_result["lead_vocals"],
                            "backing_vocals": separation_result["backing_vocals"]
                        }
                        
                        self.logger.info(f"Successfully separated backing vocals using model: {model_name}")
                        
                    except Exception as e:
                        self.logger.error(f"Failed to separate backing vocals using model {model_name}: {str(e)}")
                        # Continue with other models
                else:
                    self.logger.info(f"[DRY RUN] Would separate backing vocals using model: {model_name}")
                    track.separated_audio["backing_vocals"][model_name] = {
                        "lead_vocals": lead_vocals_path,
                        "backing_vocals": backing_vocals_path
                    }
        
        return track
    
    async def separate_audio(self, track):
        """
        Orchestrate the entire audio separation process.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Starting audio separation process for {track.base_name}")
        
        # Skip if requested
        if self.config.skip_separation:
            self.logger.info("Skipping audio separation as requested")
            track.separated_audio = {
                "clean_instrumental": {},
                "backing_vocals": {},
                "other_stems": {},
                "combined_instrumentals": {}
            }
            return track
            
        # Create stems directory
        stems_dir = os.path.join(track.track_output_dir, "stems")
        os.makedirs(stems_dir, exist_ok=True)
        self.logger.info(f"Created stems directory: {stems_dir}")
        
        # Check for existing instrumental
        if self.config.existing_instrumental:
            self.logger.info(f"Using existing instrumental file: {self.config.existing_instrumental}")
            existing_instrumental_extension = os.path.splitext(self.config.existing_instrumental)[1]
            
            instrumental_path = os.path.join(
                track.track_output_dir, 
                f"{track.base_name} (Instrumental Custom){existing_instrumental_extension}"
            )
            
            if not os.path.exists(instrumental_path):
                shutil.copy2(self.config.existing_instrumental, instrumental_path)
            
            track.separated_audio["clean_instrumental"] = {
                "instrumental": instrumental_path,
                "vocals": None
            }
            return track
        
        # Perform separation steps
        try:
            # Step 1: Separate clean instrumental
            track = await self.separate_clean_instrumental(track, track.input_audio_wav, stems_dir)
            
            # Step 2: Separate other stems
            track = await self.separate_other_stems(track, track.input_audio_wav, stems_dir)
            
            # Step 3: Separate backing vocals
            track = await self.separate_backing_vocals(track, stems_dir)
            
            # Step 4: Generate combined instrumentals
            track = await self.generate_combined_instrumentals(track, stems_dir)
            
            # Step 5: Normalize audio files
            track = await self.normalize_audio_files(track)
            
            # Create Audacity LOF file
            await self.create_audacity_lof_file(track, stems_dir)
            
            self.logger.info("Audio separation process completed successfully")
            return track
            
        except Exception as e:
            raise AudioError(f"Error during audio separation: {str(e)}") from e

    async def generate_combined_instrumentals(self, track, stems_dir):
        """
        Generate combined instrumental tracks with backing vocals.
        
        Args:
            track: The track to process
            stems_dir: The directory to store stems
            
        Returns:
            The track with updated audio information
        """
        self.logger.info(f"Generating combined instrumental tracks with backing vocals for {track.base_name}")
        
        # Skip if no backing vocals or clean instrumental
        if (not track.separated_audio["backing_vocals"] or 
            not track.separated_audio["clean_instrumental"].get("instrumental")):
            self.logger.info("No backing vocals or clean instrumental available, skipping")
            track.separated_audio["combined_instrumentals"] = {}
            return track
        
        instrumental_path = track.separated_audio["clean_instrumental"]["instrumental"]
        track.separated_audio["combined_instrumentals"] = {}
        
        # Process each backing vocals model
        for model, paths in track.separated_audio["backing_vocals"].items():
            if "backing_vocals" not in paths:
                continue
                
            backing_vocals_path = paths["backing_vocals"]
            combined_path = os.path.join(
                track.track_output_dir, 
                f"{track.base_name} (Instrumental +BV {model}).{self.config.lossless_output_format.lower()}"
            )
            
            # Skip if output already exists
            if os.path.isfile(combined_path):
                self.logger.info(f"Combined instrumental for model {model} already exists")
                track.separated_audio["combined_instrumentals"][model] = combined_path
                continue
            
            # Perform mixing
            if not self.config.dry_run:
                try:
                    from karaoke_gen.services.audio.mixer import AudioMixer
                    mixer = AudioMixer(self.config)
                    
                    # Mix instrumental and backing vocals
                    await mixer.mix_audio_files(
                        [instrumental_path, backing_vocals_path],
                        combined_path,
                        weights=[1, 1]
                    )
                    
                    track.separated_audio["combined_instrumentals"][model] = combined_path
                    self.logger.info(f"Successfully created combined instrumental for model {model}")
                    
                except Exception as e:
                    self.logger.error(f"Failed to create combined instrumental for model {model}: {str(e)}")
                    # Continue with other models
            else:
                self.logger.info(f"[DRY RUN] Would create combined instrumental for model {model}")
                track.separated_audio["combined_instrumentals"][model] = combined_path
        
        return track

    async def normalize_audio_files(self, track):
        """
        Normalize audio levels for instrumental and combined tracks.
        
        Args:
            track: The track to process
            
        Returns:
            The track with normalized audio files
        """
        self.logger.info(f"Normalizing audio files for {track.base_name}")
        
        files_to_normalize = []
        
        # Add clean instrumental
        if track.separated_audio["clean_instrumental"].get("instrumental"):
            files_to_normalize.append(
                ("clean_instrumental", track.separated_audio["clean_instrumental"]["instrumental"])
            )
        
        # Add combined instrumentals
        for model, path in track.separated_audio["combined_instrumentals"].items():
            files_to_normalize.append(("combined_instrumentals", path))
        
        # Skip if no files to normalize
        if not files_to_normalize:
            self.logger.info("No files to normalize, skipping")
            return track
        
        # Normalize each file
        for key, file_path in files_to_normalize:
            if os.path.isfile(file_path):
                try:
                    from karaoke_gen.services.audio.normalizer import AudioNormalizer
                    normalizer = AudioNormalizer(self.config)
                    
                    # Normalize in-place
                    await normalizer.normalize_audio_file(file_path, file_path)
                    
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

    async def create_audacity_lof_file(self, track, stems_dir):
        """
        Create an Audacity LOF file for the track.
        
        Args:
            track: The track to process
            stems_dir: The directory containing the stems
            
        Returns:
            The path to the LOF file
        """
        self.logger.info(f"Creating Audacity LOF file for {track.base_name}")
        
        # Define output path
        lof_path = os.path.join(track.track_output_dir, f"{track.base_name}.lof")
        
        # Skip if output already exists
        if os.path.isfile(lof_path) and not self.config.force_regenerate:
            self.logger.info(f"Audacity LOF file already exists: {lof_path}")
            return lof_path
        
        # Create LOF file
        if not self.config.dry_run:
            try:
                # Collect files to include in LOF
                files = []
                
                # Add original audio
                if track.input_audio_wav and os.path.isfile(track.input_audio_wav):
                    files.append(track.input_audio_wav)
                
                # Add instrumental
                if track.separated_audio["clean_instrumental"].get("instrumental"):
                    files.append(track.separated_audio["clean_instrumental"]["instrumental"])
                
                # Add other stems
                for stem_type, stem_info in track.separated_audio.items():
                    for stem_name, stem_path in stem_info.items():
                        if stem_path and os.path.isfile(stem_path) and stem_path not in files:
                            files.append(stem_path)
                
                # Write LOF file
                with open(lof_path, "w") as f:
                    f.write("window\n")
                    for file_path in files:
                        f.write(f'file "{os.path.abspath(file_path)}"\n')
                
                self.logger.info(f"Successfully created Audacity LOF file: {lof_path}")
                
                # Launch Audacity if configured
                if self.config.launch_audacity:
                    await self._launch_audacity(lof_path)
                
            except Exception as e:
                self.logger.error(f"Failed to create Audacity LOF file: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would create Audacity LOF file: {lof_path}")
        
        return lof_path
    
    async def _launch_audacity(self, lof_path):
        """
        Launch Audacity with the LOF file.
        
        Args:
            lof_path: The path to the LOF file
        """
        self.logger.info(f"Launching Audacity with LOF file: {lof_path}")
        
        try:
            # Determine Audacity executable path
            audacity_path = self.config.audacity_path
            
            if not audacity_path:
                # Try to find Audacity in common locations
                if platform.system() == "Windows":
                    audacity_path = "C:\\Program Files\\Audacity\\audacity.exe"
                elif platform.system() == "Darwin":  # macOS
                    audacity_path = "/Applications/Audacity.app/Contents/MacOS/Audacity"
                else:  # Linux
                    audacity_path = "audacity"
            
            # Launch Audacity
            subprocess.Popen([audacity_path, lof_path])
            
            self.logger.info(f"Successfully launched Audacity with LOF file: {lof_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to launch Audacity: {str(e)}")
            # Continue with other processing
    
    async def cleanup(self):
        """
        Perform cleanup operations for the audio separator.
        """
        self.logger.info("Cleaning up audio separator resources")
        
        # Release any locks
        for lock in self._locks.values():
            if lock.locked():
                lock.release()
        
        # Close any open resources
        if hasattr(self, 'demucs_model') and self.demucs_model:
            # Clean up demucs model resources if needed
            pass
        
        if hasattr(self, 'spleeter_model') and self.spleeter_model:
            # Clean up spleeter model resources if needed
            pass
        
        self.logger.info("Audio separator cleanup complete")

    def _acquire_lock(self, track_name):
        """
        Acquire a lock for audio separation.
        
        Args:
            track_name: The name of the track being processed
            
        Returns:
            A context manager for the lock
        """
        class LockContextManager:
            def __init__(self, separator, track_name):
                self.separator = separator
                self.track_name = track_name
                self.lock_file = None
                self.lock_file_path = os.path.join(tempfile.gettempdir(), "audio_separator.lock")
            
            def __enter__(self):
                # Try to acquire lock
                while True:
                    try:
                        # First check if there's a stale lock
                        if os.path.exists(self.lock_file_path):
                            try:
                                with open(self.lock_file_path, "r") as f:
                                    lock_data = json.load(f)
                                    pid = lock_data.get("pid")
                                    start_time = datetime.fromisoformat(lock_data.get("start_time"))
                                    running_track = lock_data.get("track")
                                
                                # Check if the process is still running
                                if pid and self.separator._is_process_running(pid):
                                    # Process is still running
                                    self.separator.logger.info(f"Waiting for another separation process to complete: {running_track}")
                                    time.sleep(5)
                                    continue
                                else:
                                    # Stale lock, remove it
                                    self.separator.logger.info(f"Removing stale lock file")
                                    os.remove(self.lock_file_path)
                            except (json.JSONDecodeError, KeyError, ValueError):
                                # Invalid lock file, remove it
                                self.separator.logger.info(f"Removing invalid lock file")
                                os.remove(self.lock_file_path)
                        
                        # Create lock file
                        lock_data = {
                            "pid": os.getpid(),
                            "start_time": datetime.now().isoformat(),
                            "track": self.track_name
                        }
                        
                        with open(self.lock_file_path, "w") as f:
                            json.dump(lock_data, f)
                        
                        self.lock_file = self.lock_file_path
                        self.separator.logger.info(f"Acquired lock for {self.track_name}")
                        return self
                    except Exception as e:
                        self.separator.logger.error(f"Error acquiring lock: {str(e)}")
                        time.sleep(5)
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                # Release lock
                if self.lock_file and os.path.exists(self.lock_file):
                    try:
                        os.remove(self.lock_file)
                        self.separator.logger.info(f"Released lock for {self.track_name}")
                    except Exception as e:
                        self.separator.logger.error(f"Error releasing lock: {str(e)}")
        
        return LockContextManager(self, track_name)

    def _is_process_running(self, pid):
        """
        Check if a process with the given PID is running.
        
        Args:
            pid: The process ID to check
            
        Returns:
            True if the process is running, False otherwise
        """
        try:
            # For Unix/Linux/Mac
            if os.name == 'posix':
                # Send signal 0 to the process - this doesn't actually send a signal,
                # but it does error checking to see if the process exists
                os.kill(pid, 0)
                return True
            # For Windows
            elif os.name == 'nt':
                import ctypes
                kernel32 = ctypes.windll.kernel32
                SYNCHRONIZE = 0x00100000
                process = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if process != 0:
                    kernel32.CloseHandle(process)
                    return True
                return False
            else:
                # Fallback for other OS
                return False
        except OSError:
            return False
        except Exception as e:
            self.logger.error(f"Error checking if process {pid} is running: {str(e)}")
            return False 