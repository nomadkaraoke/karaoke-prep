import os
import subprocess
import tempfile


def karaoke_finalise():
    for karaoke_file in filter(lambda f: "(Karaoke).mov" in f, os.listdir(".")):
        base_name = karaoke_file.replace("(Karaoke).mov", "")
        with_vocals_file = f"{base_name}(With Vocals).mov"
        title_file = f"{base_name}(Title).mov"
        instrumental_file = f"{base_name}(Instrumental UVR_MDXNET_KARA_2).MP3"
        final_mp4_file = f"{base_name}(Final Karaoke).mp4"

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
