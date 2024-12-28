#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import tempfile
import os
import json
import sys
from karaoke_prep import KaraokePrep


def is_url(string):
    """Simple check to determine if a string is a URL."""
    return string.startswith("http://") or string.startswith("https://")


def is_file(string):
    """Check if a string is a valid file."""
    return os.path.isfile(string)


def main():
    logger = logging.getLogger(__name__)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    parser = argparse.ArgumentParser(
        description="Fetch audio and lyrics for a specified song, to prepare karaoke video creation.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=54),
    )

    # Basic information
    parser.add_argument(
        "args",
        nargs="*",
        help="[Media or playlist URL] [Artist] [Title] of song to prep. If URL is provided, Artist and Title are optional but increase chance of fetching the correct lyrics. If Artist and Title are provided with no URL, the top YouTube search result will be fetched.",
    )

    package_version = pkg_resources.get_distribution("karaoke-prep").version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {package_version}")

    # Logging & Debugging
    parser.add_argument(
        "--log_level",
        default="info",
        help="Optional: logging level, e.g. info, debug, warning (default: %(default)s). Example: --log_level=debug",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Optional: perform a dry run without making any changes (default: %(default)s). Example: --dry_run=true",
    )
    parser.add_argument(
        "--render_bounding_boxes",
        action="store_true",
        help="Optional: render bounding boxes around text regions for debugging (default: %(default)s). Example: --render_bounding_boxes",
    )

    # Input/Output Configuration
    parser.add_argument(
        "--filename_pattern",
        help="Required if processing a folder: Python regex pattern to extract track names from filenames. Must contain a named group 'title'. Example: --filename_pattern='(?P<index>\\d+) - (?P<title>.+).mp3'",
    )
    parser.add_argument(
        "--output_dir",
        default=".",
        help="Optional: directory to write output files (default: <current dir>). Example: --output_dir=/app/karaoke",
    )
    parser.add_argument(
        "--no_track_subfolders",
        action="store_false",
        help="Optional: do NOT create a named subfolder for each track. Example: --no_track_subfolders",
    )
    parser.add_argument(
        "--lossless_output_format",
        default="FLAC",
        help="Optional: lossless output format for separated audio (default: FLAC). Example: --lossless_output_format=WAV",
    )
    parser.add_argument(
        "--output_png",
        type=lambda x: (str(x).lower() == "true"),
        default=True,
        help="Optional: output PNG format for title and end images (default: %(default)s). Example: --output_png=False",
    )
    parser.add_argument(
        "--output_jpg",
        type=lambda x: (str(x).lower() == "true"),
        default=True,
        help="Optional: output JPG format for title and end images (default: %(default)s). Example: --output_jpg=False",
    )

    # Audio Processing Configuration
    parser.add_argument(
        "--clean_instrumental_model",
        default="model_bs_roformer_ep_317_sdr_12.9755.ckpt",
        help="Optional: Model for clean instrumental separation (default: %(default)s).",
    )
    parser.add_argument(
        "--backing_vocals_models",
        nargs="+",
        default=["mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt"],
        help="Optional: List of models for backing vocals separation (default: %(default)s).",
    )
    parser.add_argument(
        "--other_stems_models",
        nargs="+",
        default=["htdemucs_6s.yaml"],
        help="Optional: List of models for other stems separation (default: %(default)s).",
    )

    default_model_dir_unix = "/tmp/audio-separator-models/"
    if os.name == "posix" and os.path.exists(default_model_dir_unix):
        default_model_dir = default_model_dir_unix
    else:
        # Use tempfile to get the platform-independent temp directory
        default_model_dir = os.path.join(tempfile.gettempdir(), "audio-separator-models")

    parser.add_argument(
        "--model_file_dir",
        default=default_model_dir,
        help="Optional: model files directory (default: %(default)s). Example: --model_file_dir=/app/models",
    )
    parser.add_argument(
        "--existing_instrumental",
        help="Optional: Path to an existing instrumental audio file. If provided, audio separation will be skipped.",
    )
    parser.add_argument(
        "--denoise",
        type=lambda x: (str(x).lower() == "true"),
        default=True,
        help="Optional: enable or disable denoising during separation (default: %(default)s). Example: --denoise=False",
    )
    parser.add_argument(
        "--normalize",
        type=lambda x: (str(x).lower() == "true"),
        default=True,
        help="Optional: enable or disable normalization during separation (default: %(default)s). Example: --normalize=False",
    )

    # Hardware Acceleration
    parser.add_argument(
        "--use_cuda",
        action="store_true",
        help="Optional: use Nvidia GPU with CUDA for separation (default: %(default)s). Example: --use_cuda=true",
    )
    parser.add_argument(
        "--use_coreml",
        action="store_true",
        help="Optional: use Apple Silicon GPU with CoreML for separation (default: %(default)s). Example: --use_coreml=true",
    )

    # Lyrics Configuration
    parser.add_argument(
        "--lyrics_artist",
        help="Optional: Override the artist name used for lyrics search. Example: --lyrics_artist='The Beatles'",
    )
    parser.add_argument(
        "--lyrics_title",
        help="Optional: Override the song title used for lyrics search. Example: --lyrics_title='Hey Jude'",
    )
    parser.add_argument(
        "--skip_lyrics",
        action="store_true",
        help="Optional: Skip fetching and processing lyrics. Example: --skip_lyrics",
    )
    parser.add_argument(
        "--skip_transcription",
        action="store_true",
        help="Optional: Skip audio transcription but still attempt to fetch lyrics from Spotify/Genius. Example: --skip_transcription",
    )

    # Style Configuration
    parser.add_argument(
        "--style_params_json",
        help="Optional: Path to JSON file containing style configuration for intro/end videos. Example: --style_params_json='/path/to/style_params.json'",
    )

    args = parser.parse_args()

    input_media, artist, title, filename_pattern = None, None, None, None

    if not args.args:
        parser.print_help()
        exit(1)

    # Allow 3 forms of positional arguments:
    # 1. URL or Media File only (may be single track URL, playlist URL, or local file)
    # 2. Artist and Title only
    # 3. URL, Artist, and Title
    if args.args and (is_url(args.args[0]) or is_file(args.args[0])):
        input_media = args.args[0]
        if len(args.args) > 2:
            artist = args.args[1]
            title = args.args[2]
        elif len(args.args) > 1:
            artist = args.args[1]
        else:
            logger.warn("Input media provided without Artist and Title, both will be guessed from title")

    elif os.path.isdir(args.args[0]):
        if not args.filename_pattern:
            logger.error("Filename pattern is required when processing a folder.")
            exit(1)
        if len(args.args) <= 1:
            logger.error("Second parameter provided must be Artist name; Artist is required when processing a folder.")
            exit(1)

        input_media = args.args[0]
        artist = args.args[1]
        filename_pattern = args.filename_pattern

    elif len(args.args) > 1:
        artist = args.args[0]
        title = args.args[1]
        logger.warn(f"No input media provided, the top YouTube search result for {artist} - {title} will be used.")

    else:
        parser.print_help()
        exit(1)

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    # Load style parameters if JSON file is provided
    style_params = None
    if args.style_params_json:
        try:
            with open(args.style_params_json, "r") as f:
                style_params = json.loads(f.read())
        except FileNotFoundError:
            logger.error(f"Style parameters configuration file not found: {args.style_params_json}")
            sys.exit(1)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in style parameters configuration file: {e}")
            sys.exit(1)
    else:
        # Use default values
        style_params = {
            "intro": {
                "video_duration": 5,
                "existing_image": None,
                "background_color": "#000000",
                "background_image": None,
                "font": "Montserrat-Bold.ttf",
                "artist_color": "#ffdf6b",
                "title_color": "#ffffff",
                "title_region": "370, 200, 3100, 480",
                "artist_region": "370, 700, 3100, 480",
                "extra_text": None,
                "extra_text_color": "#ffffff",
                "extra_text_region": "370, 1200, 3100, 480",
            },
            "end": {
                "video_duration": 5,
                "existing_image": None,
                "background_color": "#000000",
                "background_image": None,
                "font": "Montserrat-Bold.ttf",
                "artist_color": "#ffdf6b",
                "title_color": "#ffffff",
                "title_region": None,
                "artist_region": None,
                "extra_text": "THANK YOU FOR SINGING!",
                "extra_text_color": "#ff7acc",
                "extra_text_region": None,
            },
        }

    if args.existing_instrumental:
        args.clean_instrumental_model = None
        args.backing_vocals_models = []
        args.other_stems_models = []

    logger.info(f"KaraokePrep beginning with input_media: {input_media} artist: {artist} and title: {title}")

    kprep = KaraokePrep(
        # Basic inputs
        artist=artist,
        title=title,
        input_media=input_media,
        # Logging & Debugging
        dry_run=args.dry_run,
        log_formatter=log_formatter,
        log_level=log_level,
        render_bounding_boxes=args.render_bounding_boxes,
        # Input/Output Configuration
        filename_pattern=filename_pattern,
        output_dir=args.output_dir,
        create_track_subfolders=args.no_track_subfolders,
        lossless_output_format=args.lossless_output_format,
        output_png=args.output_png,
        output_jpg=args.output_jpg,
        # Audio Processing Configuration
        existing_instrumental=args.existing_instrumental,
        clean_instrumental_model=args.clean_instrumental_model,
        backing_vocals_models=args.backing_vocals_models,
        other_stems_models=args.other_stems_models,
        model_file_dir=args.model_file_dir,
        denoise_enabled=args.denoise,
        normalization_enabled=args.normalize,
        # Hardware Acceleration
        use_cuda=args.use_cuda,
        use_coreml=args.use_coreml,
        # Lyrics Configuration
        lyrics_artist=args.lyrics_artist,
        lyrics_title=args.lyrics_title,
        skip_lyrics=args.skip_lyrics,
        skip_transcription=args.skip_transcription,
        # Style Configuration
        style_params=style_params,
    )

    tracks = kprep.process()

    logger.info(f"Karaoke Prep complete! Output files:")

    for track in tracks:
        logger.info(f"")
        logger.info(f"Track: {track['artist']} - {track['title']}")
        logger.info(f" Input Media: {track['input_media']}")
        logger.info(f" Input WAV Audio: {track['input_audio_wav']}")
        logger.info(f" Input Still Image: {track['input_still_image']}")
        logger.info(f" Lyrics: {track['lyrics']}")
        logger.info(f" Processed Lyrics: {track['processed_lyrics']}")

        logger.info(f" Separated Audio:")

        # Clean Instrumental
        logger.info(f"  Clean Instrumental Model:")
        for stem_type, file_path in track["separated_audio"]["clean_instrumental"].items():
            logger.info(f"   {stem_type.capitalize()}: {file_path}")

        # Other Stems
        logger.info(f"  Other Stems Models:")
        for model, stems in track["separated_audio"]["other_stems"].items():
            logger.info(f"   Model: {model}")
            for stem_type, file_path in stems.items():
                logger.info(f"    {stem_type.capitalize()}: {file_path}")

        # Backing Vocals
        logger.info(f"  Backing Vocals Models:")
        for model, stems in track["separated_audio"]["backing_vocals"].items():
            logger.info(f"   Model: {model}")
            for stem_type, file_path in stems.items():
                logger.info(f"    {stem_type.capitalize()}: {file_path}")

        # Combined Instrumentals
        logger.info(f"  Combined Instrumentals:")
        for model, file_path in track["separated_audio"]["combined_instrumentals"].items():
            logger.info(f"   Model: {model}")
            logger.info(f"    Combined Instrumental: {file_path}")


if __name__ == "__main__":
    main()
