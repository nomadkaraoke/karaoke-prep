import os
import re
import shutil
import logging


class FileManager:
    def __init__(self, logger=None, dry_run=False, brand_prefix=None, organised_dir=None, public_share_dir=None, keep_brand_code=False):
        self.logger = logger or logging.getLogger(__name__)
        self.dry_run = dry_run
        self.brand_prefix = brand_prefix
        self.organised_dir = organised_dir
        self.public_share_dir = public_share_dir
        self.keep_brand_code = keep_brand_code
        self.suffixes = {
            "title_mov": " (Title).mov",
            "title_jpg": " (Title).jpg",
            "end_mov": " (End).mov",
            "end_jpg": " (End).jpg",
            "with_vocals_mov": " (With Vocals).mov",
            "with_vocals_mp4": " (With Vocals).mp4",
            "with_vocals_mkv": " (With Vocals).mkv",
            "karaoke_lrc": " (Karaoke).lrc",
            "karaoke_txt": " (Karaoke).txt",
            "karaoke_mp4": " (Karaoke).mp4",
            "karaoke_cdg": " (Karaoke).cdg",
            "karaoke_mp3": " (Karaoke).mp3",
            "final_karaoke_lossless_mp4": " (Final Karaoke Lossless 4k).mp4",
            "final_karaoke_lossless_mkv": " (Final Karaoke Lossless 4k).mkv",
            "final_karaoke_lossy_mp4": " (Final Karaoke Lossy 4k).mp4",
            "final_karaoke_lossy_720p_mp4": " (Final Karaoke Lossy 720p).mp4",
            "final_karaoke_cdg_zip": " (Final Karaoke CDG).zip",
            "final_karaoke_txt_zip": " (Final Karaoke TXT).zip",
        }

    def check_input_files_exist(self, base_name, with_vocals_file, instrumental_audio_file, enable_cdg=False, enable_txt=False):
        self.logger.info(f"Checking required input files exist...")

        input_files = {
            "title_mov": f"{base_name}{self.suffixes['title_mov']}",
            "title_jpg": f"{base_name}{self.suffixes['title_jpg']}",
            "instrumental_audio": instrumental_audio_file,
            "with_vocals_mov": with_vocals_file,
        }

        optional_input_files = {
            "end_mov": f"{base_name}{self.suffixes['end_mov']}",
            "end_jpg": f"{base_name}{self.suffixes['end_jpg']}",
        }

        if enable_cdg or enable_txt:
            input_files["karaoke_lrc"] = f"{base_name}{self.suffixes['karaoke_lrc']}"

        for key, file_path in input_files.items():
            if not os.path.isfile(file_path):
                raise Exception(f"Input file {key} not found: {file_path}")

            self.logger.info(f" Input file {key} found: {file_path}")

        for key, file_path in optional_input_files.items():
            if not os.path.isfile(file_path):
                self.logger.info(f" Optional input file {key} not found: {file_path}")
            else:
                self.logger.info(f" Input file {key} found, adding to input_files: {file_path}")
                input_files[key] = file_path

        return input_files

    def prepare_output_filenames(self, base_name, enable_cdg=False, enable_txt=False):
        output_files = {
            "karaoke_mp4": f"{base_name}{self.suffixes['karaoke_mp4']}",
            "karaoke_mp3": f"{base_name}{self.suffixes['karaoke_mp3']}",
            "karaoke_cdg": f"{base_name}{self.suffixes['karaoke_cdg']}",
            "with_vocals_mp4": f"{base_name}{self.suffixes['with_vocals_mp4']}",
            "final_karaoke_lossless_mp4": f"{base_name}{self.suffixes['final_karaoke_lossless_mp4']}",
            "final_karaoke_lossless_mkv": f"{base_name}{self.suffixes['final_karaoke_lossless_mkv']}",
            "final_karaoke_lossy_mp4": f"{base_name}{self.suffixes['final_karaoke_lossy_mp4']}",
            "final_karaoke_lossy_720p_mp4": f"{base_name}{self.suffixes['final_karaoke_lossy_720p_mp4']}",
        }

        if enable_cdg:
            output_files["final_karaoke_cdg_zip"] = f"{base_name}{self.suffixes['final_karaoke_cdg_zip']}"

        if enable_txt:
            output_files["karaoke_txt"] = f"{base_name}{self.suffixes['karaoke_txt']}"
            output_files["final_karaoke_txt_zip"] = f"{base_name}{self.suffixes['final_karaoke_txt_zip']}"

        return output_files

    def find_with_vocals_file(self, user_interface=None):
        self.logger.info("Finding input file ending in (With Vocals).mov/.mp4/.mkv or (Karaoke).mov/.mp4/.mkv")

        # Define all possible suffixes for with vocals files
        with_vocals_suffixes = [
            self.suffixes["with_vocals_mov"],
            self.suffixes["with_vocals_mp4"],
            self.suffixes["with_vocals_mkv"],
        ]

        # First try to find a properly named with vocals file in any supported format
        with_vocals_files = [f for f in os.listdir(".") if any(f.endswith(suffix) for suffix in with_vocals_suffixes)]

        if with_vocals_files:
            self.logger.info(f"Found with vocals file: {with_vocals_files[0]}")
            return with_vocals_files[0]

        # If no with vocals file found, look for potentially misnamed karaoke files
        karaoke_suffixes = [" (Karaoke).mov", " (Karaoke).mp4", " (Karaoke).mkv"]
        karaoke_files = [f for f in os.listdir(".") if any(f.endswith(suffix) for suffix in karaoke_suffixes)]

        if karaoke_files and user_interface:
            for file in karaoke_files:
                # Get the current extension
                current_ext = os.path.splitext(file)[1].lower()  # Convert to lowercase
                base_without_suffix = file.replace(f" (Karaoke){current_ext}", "")

                # Map file extension to suffix dictionary key
                ext_to_suffix = {".mov": "with_vocals_mov", ".mp4": "with_vocals_mp4", ".mkv": "with_vocals_mkv"}

                if current_ext in ext_to_suffix:
                    new_file = f"{base_without_suffix}{self.suffixes[ext_to_suffix[current_ext]]}"

                    user_interface.prompt_user_confirmation_or_raise_exception(
                        f"Found '{file}' but no '(With Vocals)', rename to {new_file} for vocal input?",
                        "Unable to proceed without With Vocals file or user confirmation of rename.",
                        allow_empty=True,
                    )

                    os.rename(file, new_file)
                    self.logger.info(f"Renamed '{file}' to '{new_file}'")
                    return new_file
                else:
                    self.logger.warning(f"Unsupported file extension: {current_ext}")

        raise Exception("No suitable files found for processing.")

    def choose_instrumental_audio_file(self, base_name, non_interactive=False):
        self.logger.info(f"Choosing instrumental audio file to use as karaoke audio...")

        search_string = " (Instrumental"
        self.logger.info(f"Searching for files in current directory containing {search_string}")

        all_instrumental_files = [f for f in os.listdir(".") if search_string in f]
        flac_files = set(f.rsplit(".", 1)[0] for f in all_instrumental_files if f.endswith(".flac"))
        mp3_files = set(f.rsplit(".", 1)[0] for f in all_instrumental_files if f.endswith(".mp3"))
        wav_files = set(f.rsplit(".", 1)[0] for f in all_instrumental_files if f.endswith(".wav"))

        self.logger.debug(f"FLAC files found: {flac_files}")
        self.logger.debug(f"MP3 files found: {mp3_files}")
        self.logger.debug(f"WAV files found: {wav_files}")

        # Filter out MP3 files if their FLAC or WAV counterpart exists
        # Filter out WAV files if their FLAC counterpart exists
        filtered_files = [
            f
            for f in all_instrumental_files
            if f.endswith(".flac")
            or (f.endswith(".wav") and f.rsplit(".", 1)[0] not in flac_files)
            or (f.endswith(".mp3") and f.rsplit(".", 1)[0] not in flac_files and f.rsplit(".", 1)[0] not in wav_files)
        ]

        self.logger.debug(f"Filtered instrumental files: {filtered_files}")

        if not filtered_files:
            raise Exception(f"No instrumental audio files found containing {search_string}")

        if len(filtered_files) == 1:
            return filtered_files[0]

        # In non-interactive mode, always choose the first option
        if non_interactive:
            self.logger.info(f"Non-interactive mode, automatically choosing first instrumental file: {filtered_files[0]}")
            return filtered_files[0]

        # Sort the remaining instrumental options alphabetically
        filtered_files.sort(reverse=True)

        self.logger.info(f"Found multiple files containing {search_string}:")
        for i, file in enumerate(filtered_files):
            self.logger.info(f" {i+1}: {file}")

        print()
        response = input(f"Choose instrumental audio file to use as karaoke audio: [1]/{len(filtered_files)}: ").strip().lower()
        if response == "":
            response = "1"

        try:
            response = int(response)
        except ValueError:
            raise Exception(f"Invalid response to instrumental audio file choice prompt: {response}")

        if response < 1 or response > len(filtered_files):
            raise Exception(f"Invalid response to instrumental audio file choice prompt: {response}")

        return filtered_files[response - 1]

    def get_names_from_withvocals(self, with_vocals_file):
        self.logger.info(f"Getting artist and title from {with_vocals_file}")

        # Remove both possible suffixes and their extensions
        base_name = with_vocals_file
        for suffix_key in ["with_vocals_mov", "with_vocals_mp4", "with_vocals_mkv"]:
            suffix = self.suffixes[suffix_key]
            if suffix in base_name:
                base_name = base_name.replace(suffix, "")
                break

        # If we didn't find a match above, try removing just the extension
        if base_name == with_vocals_file:
            base_name = os.path.splitext(base_name)[0]

        artist, title = base_name.split(" - ", 1)
        return base_name, artist, title

    def get_next_brand_code(self):
        """
        Calculate the next sequence number based on existing directories in the organised_dir.
        Assumes directories are named with the format: BRAND-XXXX Artist - Title
        """
        max_num = 0
        pattern = re.compile(rf"^{re.escape(self.brand_prefix)}-(\d{{4}})")

        if not os.path.isdir(self.organised_dir):
            raise Exception(f"Target directory does not exist: {self.organised_dir}")

        for dir_name in os.listdir(self.organised_dir):
            match = pattern.match(dir_name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

        self.logger.info(f"Next sequence number for brand {self.brand_prefix} calculated as: {max_num + 1}")
        next_seq_number = max_num + 1

        return f"{self.brand_prefix}-{next_seq_number:04d}"

    def move_files_to_brand_code_folder(self, brand_code, artist, title, output_files):
        self.logger.info(f"Moving files to new brand-prefixed directory...")

        new_brand_code_dir = f"{brand_code} - {artist} - {title}"
        new_brand_code_dir_path = os.path.join(self.organised_dir, new_brand_code_dir)

        orig_dir = os.getcwd()
        os.chdir(os.path.dirname(orig_dir))
        self.logger.info(f"Changed dir to parent directory: {os.getcwd()}")

        if self.dry_run:
            self.logger.info(f"DRY RUN: Would move original directory {orig_dir} to: {new_brand_code_dir_path}")
        else:
            os.rename(orig_dir, new_brand_code_dir_path)

        # Update output_files dictionary with the new paths after moving
        self.logger.info(f"Updating output file paths to reflect move to {new_brand_code_dir_path}")
        for key in output_files:
            if output_files[key]:  # Check if the path exists (e.g., optional files)
                old_basename = os.path.basename(output_files[key])
                new_path = os.path.join(new_brand_code_dir_path, old_basename)
                output_files[key] = new_path
                self.logger.debug(f"  Updated {key}: {new_path}")
                
        return new_brand_code_dir, new_brand_code_dir_path

    def copy_final_files_to_public_share_dirs(self, brand_code, base_name, output_files):
        self.logger.info(f"Copying final MP4, 720p MP4, and ZIP to public share directory...")

        # Validate public_share_dir is a valid folder with MP4, MP4-720p, and CDG subdirectories
        if not os.path.isdir(self.public_share_dir):
            raise Exception(f"Public share directory does not exist: {self.public_share_dir}")

        if not os.path.isdir(os.path.join(self.public_share_dir, "MP4")):
            raise Exception(f"Public share directory does not contain MP4 subdirectory: {self.public_share_dir}")

        if not os.path.isdir(os.path.join(self.public_share_dir, "MP4-720p")):
            raise Exception(f"Public share directory does not contain MP4-720p subdirectory: {self.public_share_dir}")

        if not os.path.isdir(os.path.join(self.public_share_dir, "CDG")):
            raise Exception(f"Public share directory does not contain CDG subdirectory: {self.public_share_dir}")

        if brand_code is None:
            raise Exception(f"New track prefix was not set, refusing to copy to public share directory")

        dest_mp4_dir = os.path.join(self.public_share_dir, "MP4")
        dest_720p_dir = os.path.join(self.public_share_dir, "MP4-720p")
        dest_cdg_dir = os.path.join(self.public_share_dir, "CDG")
        os.makedirs(dest_mp4_dir, exist_ok=True)
        os.makedirs(dest_720p_dir, exist_ok=True)
        os.makedirs(dest_cdg_dir, exist_ok=True)

        dest_mp4_file = os.path.join(dest_mp4_dir, f"{brand_code} - {base_name}.mp4")
        dest_720p_mp4_file = os.path.join(dest_720p_dir, f"{brand_code} - {base_name}.mp4")
        dest_zip_file = os.path.join(dest_cdg_dir, f"{brand_code} - {base_name}.zip")

        if self.dry_run:
            self.logger.info(
                f"DRY RUN: Would copy final MP4, 720p MP4, and ZIP to {dest_mp4_file}, {dest_720p_mp4_file}, and {dest_zip_file}"
            )
        else:
            shutil.copy2(output_files["final_karaoke_lossy_mp4"], dest_mp4_file)  # Changed to use lossy MP4
            shutil.copy2(output_files["final_karaoke_lossy_720p_mp4"], dest_720p_mp4_file)
            shutil.copy2(output_files["final_karaoke_cdg_zip"], dest_zip_file)
            self.logger.info(f"Copied final files to public share directory")

    def get_existing_brand_code(self):
        """Extract brand code from current directory name"""
        current_dir = os.path.basename(os.getcwd())
        if " - " not in current_dir:
            raise Exception(f"Current directory '{current_dir}' does not match expected format 'BRAND-XXXX - Artist - Title'")

        brand_code = current_dir.split(" - ")[0]
        if not brand_code or "-" not in brand_code:
            raise Exception(f"Could not extract valid brand code from directory name '{current_dir}'")

        self.logger.info(f"Using existing brand code: {brand_code}")
        return brand_code 