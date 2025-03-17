#! /usr/bin/env python3

import os
import json
import logging
from karaoke_gen.karaoke_gen import KaraokePrep

# Set up logging
logger = logging.getLogger(__name__)
log_handler = logging.StreamHandler()
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)
logger.setLevel(logging.DEBUG)


# Define the artist/title combinations
def total_length(tuple):
    artist, title = tuple
    return len(artist) + len(title)


with open("data/artist-titles.json", "r", encoding="utf-8") as f:
    all_combinations = json.load(f)

# Sort by length and get shortest and longest 20
sorted_combinations = sorted(all_combinations, key=total_length)
artist_title_combinations = sorted_combinations[:20] + sorted_combinations[-20:]

# Define the format dictionary with expanded configurations
formats = [
    {
        "name": "nomadkaraoke",
        "style_params_json": "/Users/andrew/AB Dropbox/Andrew Beveridge/MediaUnsynced/Karaoke/NomadBranding/karaoke-prep-styles-nomad.json",
    },
    {
        "name": "vocalstar",
        "style_params_json": "/Users/andrew/AB Dropbox/Andrew Beveridge/MediaUnsynced/Karaoke/Tracks-NonPublished/VocalStar/Resources/karaoke-prep-styles-vocalstar.json",
    },
    {
        "name": "minimal",
        "style_params_json": None,
    },
]

# Define other parameters
base_output_dir = "outputs"
os.makedirs(base_output_dir, exist_ok=True)

# Process each format
for format in formats:
    # Create format-specific output directory
    format_output_dir = os.path.join(base_output_dir, format["name"])
    os.makedirs(format_output_dir, exist_ok=True)

    style_params = None
    if format["style_params_json"]:
        with open(format["style_params_json"], "r") as f:
            style_params = json.loads(f.read())

    # Instantiate KaraokePrep for this format
    kprep = KaraokePrep(
        log_level=logging.INFO,
        log_formatter=log_formatter,
        output_dir=format_output_dir,
        style_params=style_params,
        render_bounding_boxes=False,
        output_jpg=False,
        output_png=True,
    )

    # Run the create_title_video and create_end_video functions for each combination
    for artist, title in artist_title_combinations:
        sanitized_artist = kprep.sanitize_filename(artist)
        sanitized_title = kprep.sanitize_filename(title)

        # Generate title video
        title_image_filepath_noext = os.path.join(format_output_dir, f"{sanitized_artist}_{sanitized_title}_title")
        title_video_filepath = os.path.join(format_output_dir, f"{sanitized_artist}_{sanitized_title}_title.mov")

        kprep.intro_video_duration = 0
        kprep.create_title_video(
            artist=artist,
            title=title,
            format=kprep.title_format,
            output_image_filepath_noext=title_image_filepath_noext,
            output_video_filepath=title_video_filepath,
        )
        logger.info(f"Created title video for {artist} - {title} using {format['name']} format")

        # Generate end video
        end_image_filepath_noext = os.path.join(format_output_dir, f"{sanitized_artist}_{sanitized_title}_end")
        end_video_filepath = os.path.join(format_output_dir, f"{sanitized_artist}_{sanitized_title}_end.mov")

        kprep.end_video_duration = 0
        kprep.create_end_video(
            artist=artist,
            title=title,
            format=kprep.end_format,
            output_image_filepath_noext=end_image_filepath_noext,
            output_video_filepath=end_video_filepath,
        )
        logger.info(f"Created end video for {artist} - {title} using {format['name']} format")
