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

        self.model_name = model_name

    def process(self):
        tracks = []

        for karaoke_file in filter(lambda f: " (Karaoke).mov" in f, os.listdir(".")):
            base_name = karaoke_file.replace(" (Karaoke).mov", "")
            artist = base_name.split(" - ")[0]
            title = base_name.split(" - ")[1]

            with_vocals_file = f"{base_name} (With Vocals).mov"
            title_file = f"{base_name} (Title).mov"
            instrumental_file = f"{base_name} (Instrumental {self.model_name}).MP3"
            final_mp4_file = f"{base_name} (Final Karaoke).mp4"

            track = {
                "artist": artist,
                "title": title,
                "video_with_vocals": with_vocals_file,
                "video_with_instrumental": karaoke_file,
                "final_video": final_mp4_file,
            }

            if os.path.isfile(title_file) and os.path.isfile(karaoke_file) and os.path.isfile(instrumental_file):
                print("Renaming karaoke file to WithVocals")
                os.rename(karaoke_file, with_vocals_file)

                print(f"Remuxing karaoke video with instrumental audio to '{karaoke_file}'")
                subprocess.run(
                    ["ffmpeg", "-an", "-i", with_vocals_file, "-vn", "-i", instrumental_file, "-c:v", "copy", "-c:a", "aac", karaoke_file]
                )

                print(f"Joining '{title_file}' and '{karaoke_file}' into '{final_mp4_file}'")
                with tempfile.NamedTemporaryFile(mode="w+", delete=False, dir="/tmp", suffix=".txt") as tmp_file_list:
                    tmp_file_list.write(f"file '{os.path.abspath(title_file)}'\n")
                    tmp_file_list.write(f"file '{os.path.abspath(karaoke_file)}'\n")
                subprocess.run(
                    [
                        "ffmpeg",
                        "-f",
                        "concat",
                        "-safe",
                        "0",
                        "-i",
                        tmp_file_list.name,
                        "-vf",
                        "settb=AVTB,setpts=N/30/TB,fps=30",
                        final_mp4_file,
                    ]
                )

                os.remove(tmp_file_list.name)
            else:
                print(f"Required files for '{base_name}' not found.")

            tracks.append(track)

        return tracks
