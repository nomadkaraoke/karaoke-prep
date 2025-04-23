import os
import zipfile
import logging
from lyrics_converter import LyricsConverter
from lyrics_transcriber.output.cdg import CDGGenerator


class FormatGenerator:
    def __init__(self, logger=None, dry_run=False, cdg_styles=None):
        self.logger = logger or logging.getLogger(__name__)
        self.dry_run = dry_run
        self.cdg_styles = cdg_styles

    def create_cdg_zip_file(self, input_files, output_files, artist, title, user_interface=None):
        self.logger.info(f"Creating CDG and MP3 files, then zipping them...")

        # Check if CDG file already exists, if so, ask user to overwrite or skip
        if os.path.isfile(output_files["final_karaoke_cdg_zip"]):
            if user_interface and not user_interface.prompt_user_bool(
                f"Found existing CDG ZIP file: {output_files['final_karaoke_cdg_zip']}. Overwrite (y) or skip (n)?",
            ):
                self.logger.info(f"Skipping CDG ZIP file creation, existing file will be used.")
                return

        # Check if individual MP3 and CDG files already exist
        if os.path.isfile(output_files["karaoke_mp3"]) and os.path.isfile(output_files["karaoke_cdg"]):
            self.logger.info(f"Found existing MP3 and CDG files, creating ZIP file directly")
            if not self.dry_run:
                with zipfile.ZipFile(output_files["final_karaoke_cdg_zip"], "w") as zipf:
                    zipf.write(output_files["karaoke_mp3"], os.path.basename(output_files["karaoke_mp3"]))
                    zipf.write(output_files["karaoke_cdg"], os.path.basename(output_files["karaoke_cdg"]))
                self.logger.info(f"Created CDG ZIP file: {output_files['final_karaoke_cdg_zip']}")
            return

        # Generate CDG and MP3 files if they don't exist
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would generate CDG and MP3 files")
        else:
            self.logger.info(f"Generating CDG and MP3 files")

            if self.cdg_styles is None:
                raise ValueError("CDG styles configuration is required when enable_cdg is True")

            generator = CDGGenerator(output_dir=os.getcwd(), logger=self.logger)
            cdg_file, mp3_file, zip_file = generator.generate_cdg_from_lrc(
                lrc_file=input_files["karaoke_lrc"],
                audio_file=input_files["instrumental_audio"],
                title=title,
                artist=artist,
                cdg_styles=self.cdg_styles,
            )

            # Rename the generated ZIP file to match our expected naming convention
            if os.path.isfile(zip_file):
                os.rename(zip_file, output_files["final_karaoke_cdg_zip"])
                self.logger.info(f"Renamed CDG ZIP file from {zip_file} to {output_files['final_karaoke_cdg_zip']}")

        if not os.path.isfile(output_files["final_karaoke_cdg_zip"]):
            self.logger.error(f"Failed to find any CDG ZIP file. Listing directory contents:")
            for file in os.listdir():
                self.logger.error(f" - {file}")
            raise Exception(f"Failed to create CDG ZIP file: {output_files['final_karaoke_cdg_zip']}")

        self.logger.info(f"CDG ZIP file created: {output_files['final_karaoke_cdg_zip']}")

        # Extract the CDG ZIP file
        self.logger.info(f"Extracting CDG ZIP file: {output_files['final_karaoke_cdg_zip']}")
        with zipfile.ZipFile(output_files["final_karaoke_cdg_zip"], "r") as zip_ref:
            zip_ref.extractall()

        if os.path.isfile(output_files["karaoke_mp3"]):
            self.logger.info(f"Found extracted MP3 file: {output_files['karaoke_mp3']}")
        else:
            self.logger.error("Failed to find extracted MP3 file")
            raise Exception("Failed to extract MP3 file from CDG ZIP")

    def create_txt_zip_file(self, input_files, output_files, user_interface=None):
        self.logger.info(f"Creating TXT ZIP file...")

        # Check if TXT file already exists, if so, ask user to overwrite or skip
        if os.path.isfile(output_files["final_karaoke_txt_zip"]):
            if user_interface and not user_interface.prompt_user_bool(
                f"Found existing TXT ZIP file: {output_files['final_karaoke_txt_zip']}. Overwrite (y) or skip (n)?",
            ):
                self.logger.info(f"Skipping TXT ZIP file creation, existing file will be used.")
                return

        # Create the ZIP file containing the MP3 and TXT files
        if self.dry_run:
            self.logger.info(f"DRY RUN: Would create TXT ZIP file: {output_files['final_karaoke_txt_zip']}")
        else:
            self.logger.info(f"Running karaoke-converter to convert MidiCo LRC file {input_files['karaoke_lrc']} to TXT format")
            txt_converter = LyricsConverter(output_format="txt", filepath=input_files["karaoke_lrc"])
            converted_txt = txt_converter.convert_file()

            with open(output_files["karaoke_txt"], "w") as txt_file:
                txt_file.write(converted_txt)
                self.logger.info(f"TXT file written: {output_files['karaoke_txt']}")

            self.logger.info(f"Creating ZIP file containing {output_files['karaoke_mp3']} and {output_files['karaoke_txt']}")
            with zipfile.ZipFile(output_files["final_karaoke_txt_zip"], "w") as zipf:
                zipf.write(output_files["karaoke_mp3"], os.path.basename(output_files["karaoke_mp3"]))
                zipf.write(output_files["karaoke_txt"], os.path.basename(output_files["karaoke_txt"]))

            if not os.path.isfile(output_files["final_karaoke_txt_zip"]):
                raise Exception(f"Failed to create TXT ZIP file: {output_files['final_karaoke_txt_zip']}")

            self.logger.info(f"TXT ZIP file created: {output_files['final_karaoke_txt_zip']}") 