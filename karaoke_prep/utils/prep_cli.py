#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import tempfile
import os
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

    parser.add_argument(
        "args",
        nargs="*",
        help="[Media or playlist URL] [Artist] [Title] of song to prep. If URL is provided, Artist and Title are optional but increase chance of fetching the correct lyrics. If Artist and Title are provided with no URL, the top YouTube search result will be fetched.",
    )

    package_version = pkg_resources.get_distribution("karaoke-prep").version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {package_version}")

    parser.add_argument(
        "--log_level",
        default="info",
        help="Optional: logging level, e.g. info, debug, warning (default: %(default)s). Example: --log_level=debug",
    )

    parser.add_argument(
        "--filename_pattern",
        help="Required if processing a folder: Python regex pattern to extract track names from filenames. Must contain a named group 'title'. Example: --filename_pattern='(?P<index>\\d+) - (?P<title>.+).mp3'",
    )

    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Optional: perform a dry run without making any changes (default: %(default)s). Example: --dry_run=true",
    )

    parser.add_argument(
        "--model_names",
        nargs="+",
        default=[
            "model_mel_band_roformer_ep_3005_sdr_11.4360.ckpt",
            "UVR_MDXNET_KARA_2.onnx",
            "2_HP-UVR.pth",
            "MDX23C-8KFFT-InstVoc_HQ_2.ckpt",
        ],
        help="Optional: list of model names to be used for separation (default: %(default)s). Example: --model_names UVR_MDXNET_KARA_2.onnx UVR-MDX-NET-Inst_HQ_4.onnx",
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
        "--output_dir",
        default=".",
        help="Optional: directory to write output files (default: <current dir>). Example: --output_dir=/app/karaoke",
    )

    parser.add_argument(
        "--lossless_output_format",
        default="FLAC",
        help="Optional: lossless output format for separated audio (default: FLAC). Example: --lossless_output_format=WAV",
    )

    parser.add_argument(
        "--lossy_output_format",
        default="MP3",
        help="Optional: lossy output format for separated audio (default: MP3). Example: --lossy_output_format=OGG",
    )

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

    parser.add_argument(
        "--no_track_subfolders",
        action="store_false",
        help="Optional: do NOT create a named subfolder for each track. Example: --no_track_subfolders",
    )

    parser.add_argument(
        "--intro_background_color",
        default="#000000",
        help="Optional: Background color for intro video (default: black). Example: --intro_background_color=#123456",
    )

    parser.add_argument(
        "--intro_background_image",
        help="Optional: Path to background image for intro video. Overrides background color if provided. Example: --intro_background_image=path/to/image.jpg",
    )

    parser.add_argument(
        "--intro_font",
        default="Montserrat-Bold.ttf",
        help="Optional: Font file for intro video (default: Montserrat-Bold.ttf). Example: --intro_font=AvenirNext-Bold.ttf",
    )

    parser.add_argument(
        "--intro_artist_color",
        default="#ffdf6b",
        help="Optional: Font color for intro video artist text (default: #ffdf6b). Example: --intro_artist_color=#123456",
    )

    parser.add_argument(
        "--intro_title_color",
        default="#ffffff",
        help="Optional: Font color for intro video title text (default: #ffffff). Example: --intro_title_color=#123456",
    )

    parser.add_argument(
        "--existing_instrumental",
        help="Optional: Path to an existing instrumental audio file. If provided, audio separation will be skipped.",
    )

    parser.add_argument(
        "--existing_title_image",
        help="Optional: Path to an existing title image file. If provided, title image generation will be skipped.",
    )

    parser.add_argument(
        "--end_background_color",
        default="#000000",
        help="Optional: Background color for end screen video (default: black). Example: --end_background_color=#123456",
    )

    parser.add_argument(
        "--end_background_image",
        help="Optional: Path to background image for end screen video. Overrides background color if provided. Example: --end_background_image=path/to/image.jpg",
    )

    parser.add_argument(
        "--end_font",
        default="Montserrat-Bold.ttf",
        help="Optional: Font file for end screen video (default: Montserrat-Bold.ttf). Example: --end_font=AvenirNext-Bold.ttf",
    )

    parser.add_argument(
        "--end_text_color",
        default="#ffffff",
        help="Optional: Font color for end screen video text (default: #ffffff). Example: --end_text_color=#123456",
    )

    parser.add_argument(
        "--existing_end_image",
        help="Optional: Path to an existing end screen image file. If provided, end screen image generation will be skipped.",
    )

    parser.add_argument(
        "--title_video_duration",
        type=int,
        default=5,
        help="Optional: duration of the title video in seconds (default: 5). Example: --title_video_duration=10",
    )

    parser.add_argument(
        "--end_video_duration",
        type=int,
        default=5,
        help="Optional: duration of the end video in seconds (default: 5). Example: --end_video_duration=10",
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

    if args.existing_instrumental:
        args.model_names = ["Custom"]

    logger.info(f"KaraokePrep beginning with input_media: {input_media} artist: {artist} and title: {title}")

    kprep = KaraokePrep(
        artist=artist,
        title=title,
        input_media=input_media,
        filename_pattern=filename_pattern,
        dry_run=args.dry_run,
        log_formatter=log_formatter,
        log_level=log_level,
        model_names=args.model_names,
        model_file_dir=args.model_file_dir,
        output_dir=args.output_dir,
        lossless_output_format=args.lossless_output_format,
        lossy_output_format=args.lossy_output_format,
        use_cuda=args.use_cuda,
        use_coreml=args.use_coreml,
        normalization_enabled=args.normalize,
        denoise_enabled=args.denoise,
        create_track_subfolders=args.no_track_subfolders,
        intro_background_color=args.intro_background_color,
        intro_background_image=args.intro_background_image,
        intro_font=args.intro_font,
        intro_artist_color=args.intro_artist_color,
        intro_title_color=args.intro_title_color,
        existing_instrumental=args.existing_instrumental,
        existing_title_image=args.existing_title_image,
        end_background_color=args.end_background_color,
        end_background_image=args.end_background_image,
        end_font=args.end_font,
        end_text_color=args.end_text_color,
        existing_end_image=args.existing_end_image,
        title_video_duration=args.title_video_duration,
        end_video_duration=args.end_video_duration,
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

        for model_name in args.model_names:
            logger.info(f" Instrumental: {track['separated_audio'][model_name]['instrumental']}")
            logger.info(f" Instrumental (Lossy): {track['separated_audio'][model_name]['instrumental_lossy']}")
            logger.info(f" Vocals: {track['separated_audio'][model_name]['vocals']}")
            logger.info(f" Vocals (Lossy): {track['separated_audio'][model_name]['vocals_lossy']}")


if __name__ == "__main__":
    main()
