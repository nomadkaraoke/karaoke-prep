import os
import subprocess
import tempfile
import logging


class KaraokeFinalise:
    def __init__(
        self,
        log_level=logging.DEBUG,
        log_formatter=None,
        model_name="UVR_MDXNET_KARA_2",
    ):
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)
        self.log_level = log_level
        self.log_formatter = log_formatter

        self.log_handler = logging.StreamHandler()

        if self.log_formatter is None:
            self.log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")

        self.log_handler.setFormatter(self.log_formatter)
        self.logger.addHandler(self.log_handler)

        self.logger.debug(f"KaraokeFinalise instantiating")

        self.ffmpeg_base_command = "ffmpeg -hide_banner -nostats"

        if self.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"

        self.model_name = model_name

    def process(self):
        tracks = []

        self.logger.info(f"Searching for files in current directory ending with (Karaoke).mov")
        for karaoke_file in filter(lambda f: " (Karaoke).mov" in f, os.listdir(".")):
            base_name = karaoke_file.replace(" (Karaoke).mov", "")
            artist = base_name.split(" - ")[0]
            title = base_name.split(" - ")[1]

            with_vocals_file = f"{base_name} (With Vocals).mov"
            title_file = f"{base_name} (Title).mov"
            instrumental_file = f"{base_name} (Instrumental {self.model_name}).mp3"

            final_mp4_file = f"{base_name} (Final Karaoke).mp4"

            track = {
                "artist": artist,
                "title": title,
                "video_with_vocals": with_vocals_file,
                "video_with_instrumental": karaoke_file,
                "final_video": final_mp4_file,
            }

            if os.path.isfile(title_file) and os.path.isfile(karaoke_file) and os.path.isfile(instrumental_file):
                self.logger.info(f"All 3 input files found for {base_name}, beginning finalisation")

                self.logger.info(f"Output [With Vocals]: renaming synced video to: {with_vocals_file}")
                os.rename(karaoke_file, with_vocals_file)

                self.logger.info(f"Output [With Instrumental]: remuxing synced video with instrumental audio to: {karaoke_file}")

                ffmpeg_command = f'{self.ffmpeg_base_command} -an -i "{with_vocals_file}" -vn -i "{instrumental_file}" -c:v copy -c:a aac "{karaoke_file}"'
                self.logger.debug(f"Running command: {ffmpeg_command}")
                os.system(ffmpeg_command)

                self.logger.info(f"Output [Final Karaoke]: joining title video and instrumental video to produce: {final_mp4_file}")

                with tempfile.NamedTemporaryFile(mode="w+", delete=False, dir="/tmp", suffix=".txt") as tmp_file_list:
                    tmp_file_list.write(f"file '{os.path.abspath(title_file)}'\n")
                    tmp_file_list.write(f"file '{os.path.abspath(karaoke_file)}'\n")

                ffmpeg_command = f'{self.ffmpeg_base_command} -f concat -safe 0 -i "{tmp_file_list.name}" -vf settb=AVTB,setpts=N/30/TB,fps=30 "{final_mp4_file}"'
                self.logger.debug(f"Running command: {ffmpeg_command}")
                os.system(ffmpeg_command)

                os.remove(tmp_file_list.name)
            else:
                self.logger.error(f"Unable to find all 3 required input files:\n {title_file}\n {karaoke_file}\n {instrumental_file}")

            tracks.append(track)

        return tracks
