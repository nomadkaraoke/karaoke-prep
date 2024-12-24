import os
import json
import logging
from karaoke_prep.karaoke_prep import KaraokePrep

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
artist_title_combinations = sorted_combinations[:10] + sorted_combinations[-10:]

# Define the format dictionary with expanded configurations
formats = [
    {
        "name": "vocalstar",
        "intro_background_image": "/Users/andrew/AB Dropbox/Andrew Beveridge/MediaUnsynced/Karaoke/Tracks-NonPublished/VocalStar/Resources/vocal-star-title-background-black.4k.png",
        "end_background_image": "/Users/andrew/AB Dropbox/Andrew Beveridge/MediaUnsynced/Karaoke/Tracks-NonPublished/VocalStar/Resources/vocal-star-end-card-black.4k.png",
        "font": "Zurich_Cn_BT_Bold.ttf",
        "artist_color": "#FCDF01",
        "title_color": "#FCDF01",
        "intro_title_region": "370,470,3100,480",
        "intro_artist_region": "370,1210,3100,480",
        "intro_extra_text": "GET READY TO SING!",
        "intro_extra_text_color": "#FFFFFF",
        "intro_extra_text_region": "370,1800,3100,280",
        "end_title_region": "370,670,3100,480",
        "end_artist_region": "370,1410,3100,480",
        "end_extra_text": "THANK YOU FOR SINGING!",
        "end_extra_text_color": "#FFFFFF",
        "end_extra_text_region": "370,1800,3100,280",
    },
    {
        "name": "nomadkaraoke",
        "intro_background_image": "/Users/andrew/AB Dropbox/Andrew Beveridge/MediaUnsynced/Karaoke/NomadBranding/karaoke-title-screen-background-nomad-4k.png",
        "end_background_color": "#000000",  # Using solid color for end screen
        "font": "AvenirNext-Bold.ttf",
        "artist_color": "#FFFFFF",
        "title_color": "#ffdf6b",
        "intro_title_region": "370,950,3100,350",
        "intro_artist_region": "370,1350,3100,450",
        "intro_extra_text": None,  # No extra text on intro
        "end_title_region": "370,800,3100,350",
        "end_artist_region": "370,1200,3100,450",
        "end_extra_text": "Follow us @NomadKaraoke",
        "end_extra_text_color": "#ffdf6b",
        "end_extra_text_region": "370,1700,3100,280",
    },
    {
        "name": "minimal",
        "intro_background_color": "#000033",
        "end_background_color": "#000033",
        "font": "Montserrat-Bold.ttf",
        "artist_color": "#FFFFFF",
        "title_color": "#ffdf6b",
        "intro_title_region": "370,800,3100,400",
        "intro_artist_region": "370,1300,3100,400",
        "intro_extra_text": None,  # No extra text on either screen
        "end_title_region": "370,800,3100,400",
        "end_artist_region": "370,1300,3100,400",
        "end_extra_text": None,
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

    # Instantiate KaraokePrep for this format
    kprep = KaraokePrep(
        log_level=logging.INFO,
        log_formatter=log_formatter,
        output_dir=format_output_dir,
        intro_background_image=format.get("intro_background_image"),
        intro_background_color=format.get("intro_background_color", "#000000"),
        end_background_image=format.get("end_background_image"),
        end_background_color=format.get("end_background_color", "#000000"),
        intro_font=format["font"],
        end_font=format["font"],
        intro_artist_color=format["artist_color"],
        intro_title_color=format["title_color"],
        end_artist_color=format["artist_color"],
        end_title_color=format["title_color"],
        intro_title_region=format.get("intro_title_region"),
        intro_artist_region=format.get("intro_artist_region"),
        intro_extra_text=format.get("intro_extra_text"),
        intro_extra_text_color=format.get("intro_extra_text_color"),
        intro_extra_text_region=format.get("intro_extra_text_region"),
        end_title_region=format.get("end_title_region"),
        end_artist_region=format.get("end_artist_region"),
        end_extra_text=format.get("end_extra_text"),
        end_extra_text_color=format.get("end_extra_text_color"),
        end_extra_text_region=format.get("end_extra_text_region"),
        intro_video_duration=0,
        end_video_duration=0,
        render_bounding_boxes=True,
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

        kprep.create_end_video(
            artist=artist,
            title=title,
            format=kprep.end_format,
            output_image_filepath_noext=end_image_filepath_noext,
            output_video_filepath=end_video_filepath,
        )
        logger.info(f"Created end video for {artist} - {title} using {format['name']} format")
