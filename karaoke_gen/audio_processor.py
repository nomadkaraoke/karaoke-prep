import os
import sys
import json
import logging
import glob
import shutil
import tempfile
import time
import fcntl
import errno
import psutil
from datetime import datetime
from pydub import AudioSegment


# Placeholder class or functions for audio processing
class AudioProcessor:
    def __init__(
        self,
        logger,
        log_level,
        log_formatter,
        model_file_dir,
        lossless_output_format,
        clean_instrumental_model,
        backing_vocals_models,
        other_stems_models,
        ffmpeg_base_command,
    ):
        self.logger = logger
        self.log_level = log_level
        self.log_formatter = log_formatter
        self.model_file_dir = model_file_dir
        self.lossless_output_format = lossless_output_format
        self.clean_instrumental_model = clean_instrumental_model
        self.backing_vocals_models = backing_vocals_models
        self.other_stems_models = other_stems_models
        self.ffmpeg_base_command = ffmpeg_base_command  # Needed for combined instrumentals

    def _file_exists(self, file_path):
        """Check if a file exists and log the result."""
        exists = os.path.isfile(file_path)
        if exists:
            self.logger.info(f"File already exists, skipping creation: {file_path}")
        return exists

    def separate_audio(self, audio_file, model_name, artist_title, track_output_dir, instrumental_path, vocals_path):
        if audio_file is None or not os.path.isfile(audio_file):
            raise Exception("Error: Invalid audio source provided.")

        self.logger.debug(f"audio_file is valid file: {audio_file}")

        self.logger.info(
            f"instantiating Separator with model_file_dir: {self.model_file_dir}, model_filename: {model_name} output_format: {self.lossless_output_format}"
        )

        from audio_separator.separator import Separator

        separator = Separator(
            log_level=self.log_level,
            log_formatter=self.log_formatter,
            model_file_dir=self.model_file_dir,
            output_format=self.lossless_output_format,
        )

        separator.load_model(model_filename=model_name)
        output_files = separator.separate(audio_file)

        self.logger.debug(f"Separator output files: {output_files}")

        model_name_no_extension = os.path.splitext(model_name)[0]

        for file in output_files:
            if "(Vocals)" in file:
                self.logger.info(f"Moving Vocals file {file} to {vocals_path}")
                shutil.move(file, vocals_path)
            elif "(Instrumental)" in file:
                self.logger.info(f"Moving Instrumental file {file} to {instrumental_path}")
                shutil.move(file, instrumental_path)
            elif model_name in file:
                # Example filename 1: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Piano)_htdemucs_6s.flac"
                # Example filename 2: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Guitar)_htdemucs_6s.flac"
                # The stem name in these examples would be "Piano" or "Guitar"
                # Extract stem_name from the filename
                stem_name = file.split(f"_{model_name}")[0].split("_")[-1]
                stem_name = stem_name.strip("()")  # Remove parentheses if present

                other_stem_path = os.path.join(track_output_dir, f"{artist_title} ({stem_name} {model_name}).{self.lossless_output_format}")
                self.logger.info(f"Moving other stem file {file} to {other_stem_path}")
                shutil.move(file, other_stem_path)

            elif model_name_no_extension in file:
                # Example filename 1: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Piano)_htdemucs_6s.flac"
                # Example filename 2: "Freddie Jackson - All I'll Ever Ask (feat. Najee) (Local)_(Guitar)_htdemucs_6s.flac"
                # The stem name in these examples would be "Piano" or "Guitar"
                # Extract stem_name from the filename
                stem_name = file.split(f"_{model_name_no_extension}")[0].split("_")[-1]
                stem_name = stem_name.strip("()")  # Remove parentheses if present

                other_stem_path = os.path.join(track_output_dir, f"{artist_title} ({stem_name} {model_name}).{self.lossless_output_format}")
                self.logger.info(f"Moving other stem file {file} to {other_stem_path}")
                shutil.move(file, other_stem_path)

        self.logger.info(f"Separation complete! Output file(s): {vocals_path} {instrumental_path}")

    def process_audio_separation(self, audio_file, artist_title, track_output_dir):
        from audio_separator.separator import Separator

        self.logger.info(f"Starting audio separation process for {artist_title}")

        # Define lock file path in system temp directory
        lock_file_path = os.path.join(tempfile.gettempdir(), "audio_separator.lock")

        # Try to acquire lock
        while True:
            try:
                # First check if there's a stale lock
                if os.path.exists(lock_file_path):
                    try:
                        with open(lock_file_path, "r") as f:
                            lock_data = json.load(f)
                            pid = lock_data.get("pid")
                            start_time = datetime.fromisoformat(lock_data.get("start_time"))
                            running_track = lock_data.get("track")

                            # Check if process is still running
                            if not psutil.pid_exists(pid):
                                self.logger.warning(f"Found stale lock from dead process {pid}, removing...")
                                os.remove(lock_file_path)
                            else:
                                # Calculate runtime
                                runtime = datetime.now() - start_time
                                runtime_mins = runtime.total_seconds() / 60

                                # Get process command line
                                try:
                                    proc = psutil.Process(pid)
                                    cmdline_args = proc.cmdline()
                                    # Handle potential bytes in cmdline args (cross-platform compatibility)
                                    cmd = " ".join(arg.decode('utf-8', errors='replace') if isinstance(arg, bytes) else arg for arg in cmdline_args)
                                except (psutil.AccessDenied, psutil.NoSuchProcess):
                                    cmd = "<command unavailable>"

                                self.logger.info(
                                    f"Waiting for other audio separation process to complete before starting separation for {artist_title}...\n"
                                    f"Currently running process details:\n"
                                    f"  Track: {running_track}\n"
                                    f"  PID: {pid}\n"
                                    f"  Running time: {runtime_mins:.1f} minutes\n"
                                    f"  Command: {cmd}\n"
                                    f"To force clear the lock and kill the process, run:\n"
                                    f"  kill {pid} && rm {lock_file_path}"
                                )
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        self.logger.warning(f"Found invalid lock file, removing: {e}")
                        os.remove(lock_file_path)

                # Try to acquire lock
                lock_file = open(lock_file_path, "w")
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                # Write metadata to lock file
                lock_data = {
                    "pid": os.getpid(),
                    "start_time": datetime.now().isoformat(),
                    "track": f"{artist_title}",
                }
                json.dump(lock_data, lock_file)
                lock_file.flush()
                break

            except IOError as e:
                if e.errno != errno.EAGAIN:
                    raise
                # Lock is held by another process
                time.sleep(30)  # Wait 30 seconds before trying again
                continue

        try:
            separator = Separator(
                log_level=self.log_level,
                log_formatter=self.log_formatter,
                model_file_dir=self.model_file_dir,
                output_format=self.lossless_output_format,
            )

            stems_dir = self._create_stems_directory(track_output_dir)
            result = {"clean_instrumental": {}, "other_stems": {}, "backing_vocals": {}, "combined_instrumentals": {}}

            if os.environ.get("KARAOKE_GEN_SKIP_AUDIO_SEPARATION"):
                return result

            result["clean_instrumental"] = self._separate_clean_instrumental(
                separator, audio_file, artist_title, track_output_dir, stems_dir
            )
            result["other_stems"] = self._separate_other_stems(separator, audio_file, artist_title, stems_dir)
            result["backing_vocals"] = self._separate_backing_vocals(
                separator, result["clean_instrumental"]["vocals"], artist_title, stems_dir
            )
            result["combined_instrumentals"] = self._generate_combined_instrumentals(
                result["clean_instrumental"]["instrumental"], result["backing_vocals"], artist_title, track_output_dir
            )
            self._normalize_audio_files(result, artist_title, track_output_dir)

            # Create Audacity LOF file
            lof_path = os.path.join(stems_dir, f"{artist_title} (Audacity).lof")
            first_model = list(result["backing_vocals"].keys())[0]

            files_to_include = [
                audio_file,  # Original audio
                result["clean_instrumental"]["instrumental"],  # Clean instrumental
                result["backing_vocals"][first_model]["backing_vocals"],  # Backing vocals
                result["combined_instrumentals"][first_model],  # Combined instrumental+BV
            ]

            # Convert to absolute paths
            files_to_include = [os.path.abspath(f) for f in files_to_include]

            with open(lof_path, "w") as lof:
                for file_path in files_to_include:
                    lof.write(f'file "{file_path}"\n')

            self.logger.info(f"Created Audacity LOF file: {lof_path}")
            result["audacity_lof"] = lof_path

            # Launch Audacity with multiple tracks
            if sys.platform == "darwin":  # Check if we're on macOS
                if lof_path and os.path.exists(lof_path):
                    self.logger.info(f"Launching Audacity with LOF file: {lof_path}")
                    os.system(f'open -a Audacity "{lof_path}"')
                else:
                    self.logger.debug("Audacity LOF file not available or not found")

            self.logger.info("Audio separation, combination, and normalization process completed")
            return result
        finally:
            # Release lock
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            try:
                os.remove(lock_file_path)
            except OSError:
                pass

    def _create_stems_directory(self, track_output_dir):
        stems_dir = os.path.join(track_output_dir, "stems")
        os.makedirs(stems_dir, exist_ok=True)
        self.logger.info(f"Created stems directory: {stems_dir}")
        return stems_dir

    def _separate_clean_instrumental(self, separator, audio_file, artist_title, track_output_dir, stems_dir):
        self.logger.info(f"Separating using clean instrumental model: {self.clean_instrumental_model}")
        instrumental_path = os.path.join(
            track_output_dir, f"{artist_title} (Instrumental {self.clean_instrumental_model}).{self.lossless_output_format}"
        )
        vocals_path = os.path.join(stems_dir, f"{artist_title} (Vocals {self.clean_instrumental_model}).{self.lossless_output_format}")

        result = {}
        if not self._file_exists(instrumental_path) or not self._file_exists(vocals_path):
            separator.load_model(model_filename=self.clean_instrumental_model)
            clean_output_files = separator.separate(audio_file)

            for file in clean_output_files:
                if "(Vocals)" in file and not self._file_exists(vocals_path):
                    shutil.move(file, vocals_path)
                    result["vocals"] = vocals_path
                elif "(Instrumental)" in file and not self._file_exists(instrumental_path):
                    shutil.move(file, instrumental_path)
                    result["instrumental"] = instrumental_path
        else:
            result["vocals"] = vocals_path
            result["instrumental"] = instrumental_path

        return result

    def _separate_other_stems(self, separator, audio_file, artist_title, stems_dir):
        self.logger.info(f"Separating using other stems models: {self.other_stems_models}")
        result = {}
        for model in self.other_stems_models:
            self.logger.info(f"Processing with model: {model}")
            result[model] = {}

            # Check if any stem files for this model already exist
            existing_stems = glob.glob(os.path.join(stems_dir, f"{artist_title} (*{model}).{self.lossless_output_format}"))

            if existing_stems:
                self.logger.info(f"Found existing stem files for model {model}, skipping separation")
                for stem_file in existing_stems:
                    stem_name = os.path.basename(stem_file).split("(")[1].split(")")[0].strip()
                    result[model][stem_name] = stem_file
            else:
                separator.load_model(model_filename=model)
                other_stems_output = separator.separate(audio_file)

                for file in other_stems_output:
                    file_name = os.path.basename(file)
                    stem_name = file_name[file_name.rfind("_(") + 2 : file_name.rfind(")_")]
                    new_filename = f"{artist_title} ({stem_name} {model}).{self.lossless_output_format}"
                    other_stem_path = os.path.join(stems_dir, new_filename)
                    if not self._file_exists(other_stem_path):
                        shutil.move(file, other_stem_path)
                    result[model][stem_name] = other_stem_path

        return result

    def _separate_backing_vocals(self, separator, vocals_path, artist_title, stems_dir):
        self.logger.info(f"Separating clean vocals using backing vocals models: {self.backing_vocals_models}")
        result = {}
        for model in self.backing_vocals_models:
            self.logger.info(f"Processing with model: {model}")
            result[model] = {}
            lead_vocals_path = os.path.join(stems_dir, f"{artist_title} (Lead Vocals {model}).{self.lossless_output_format}")
            backing_vocals_path = os.path.join(stems_dir, f"{artist_title} (Backing Vocals {model}).{self.lossless_output_format}")

            if not self._file_exists(lead_vocals_path) or not self._file_exists(backing_vocals_path):
                separator.load_model(model_filename=model)
                backing_vocals_output = separator.separate(vocals_path)

                for file in backing_vocals_output:
                    if "(Vocals)" in file and not self._file_exists(lead_vocals_path):
                        shutil.move(file, lead_vocals_path)
                        result[model]["lead_vocals"] = lead_vocals_path
                    elif "(Instrumental)" in file and not self._file_exists(backing_vocals_path):
                        shutil.move(file, backing_vocals_path)
                        result[model]["backing_vocals"] = backing_vocals_path
            else:
                result[model]["lead_vocals"] = lead_vocals_path
                result[model]["backing_vocals"] = backing_vocals_path
        return result

    def _generate_combined_instrumentals(self, instrumental_path, backing_vocals_result, artist_title, track_output_dir):
        self.logger.info("Generating combined instrumental tracks with backing vocals")
        result = {}
        for model, paths in backing_vocals_result.items():
            backing_vocals_path = paths["backing_vocals"]
            combined_path = os.path.join(track_output_dir, f"{artist_title} (Instrumental +BV {model}).{self.lossless_output_format}")

            if not self._file_exists(combined_path):
                ffmpeg_command = (
                    f'{self.ffmpeg_base_command} -i "{instrumental_path}" -i "{backing_vocals_path}" '
                    f'-filter_complex "[0:a][1:a]amix=inputs=2:duration=longest:weights=1 1" '
                    f'-c:a {self.lossless_output_format.lower()} "{combined_path}"'
                )

                self.logger.debug(f"Running command: {ffmpeg_command}")
                os.system(ffmpeg_command)

            result[model] = combined_path
        return result

    def _normalize_audio_files(self, separation_result, artist_title, track_output_dir):
        self.logger.info("Normalizing clean instrumental and combined instrumentals")

        files_to_normalize = [
            ("clean_instrumental", separation_result["clean_instrumental"]["instrumental"]),
        ] + [("combined_instrumentals", path) for path in separation_result["combined_instrumentals"].values()]

        for key, file_path in files_to_normalize:
            if self._file_exists(file_path):
                try:
                    self._normalize_audio(file_path, file_path)  # Normalize in-place

                    # Verify the normalized file
                    if os.path.getsize(file_path) > 0:
                        self.logger.info(f"Successfully normalized: {file_path}")
                    else:
                        raise Exception("Normalized file is empty")

                except Exception as e:
                    self.logger.error(f"Error during normalization of {file_path}: {e}")
                    self.logger.warning(f"Normalization failed for {file_path}. Original file remains unchanged.")
            else:
                self.logger.warning(f"File not found for normalization: {file_path}")

        self.logger.info("Audio normalization process completed")

    def _normalize_audio(self, input_path, output_path, target_level=0.0):
        self.logger.info(f"Normalizing audio file: {input_path}")

        # Load audio file
        audio = AudioSegment.from_file(input_path, format=self.lossless_output_format.lower())

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

        # Export normalized audio, overwriting the original file
        normalized_audio.export(output_path, format=self.lossless_output_format.lower())

        self.logger.info(f"Normalized audio saved, replacing: {output_path}")
        self.logger.debug(f"Original peak: {peak_amplitude} dB, Applied gain: {gain_db} dB")
