#!/usr/bin/env python
import argparse
import logging
import pkg_resources
from karaoke_prep import KaraokePrep


def is_url(string):
    """Simple check to determine if a string is a URL."""
    return string.startswith("http://") or string.startswith("https://")


def main():
    logger = logging.getLogger(__name__)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    parser = argparse.ArgumentParser(
        description="Fetch audio and lyrics for a specified song, to prepare karaoke video creation.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=50),
    )

    parser.add_argument(
        "args",
        nargs="*",
        help="[YouTube video or playlist URL] [Artist] [Title] of song to prep. If URL is provided, Artist and Title are optional but increase chance of fetching the correct lyrics. If Artist and Title are provided with no URL, the top YouTube search result will be fetched.",
    )

    package_version = pkg_resources.get_distribution("karaoke-prep").version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {package_version}")

    parser.add_argument(
        "--log_level",
        default="info",
        help="Optional: logging level, e.g. info, debug, warning (default: %(default)s). Example: --log_level=debug",
    )

    parser.add_argument(
        "--model_name",
        default="UVR_MDXNET_KARA_2",
        help="Optional: model name to be used for separation (default: %(default)s). Example: --model_name=UVR-MDX-NET-Inst_HQ_3",
    )

    parser.add_argument(
        "--model_file_dir",
        default="/tmp/audio-separator-models/",
        help="Optional: model files directory (default: %(default)s). Example: --model_file_dir=/app/models",
    )

    parser.add_argument(
        "--output_dir",
        default=".",
        help="Optional: directory to write output files (default: <current dir>). Example: --output_dir=/app/karaoke",
    )

    parser.add_argument(
        "--output_format",
        default="MP3",
        help="Optional: output format for separated audio (default: MP3). Example: --output_format=FLAC",
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
        default="black",
        help="Optional: Background color for intro video (default: black). Example: --intro_background_color=#123456",
    )

    parser.add_argument(
        "--intro_background_image",
        help="Optional: Path to background image for intro video. Overrides background color if provided. Example: --intro_background_image=path/to/image.jpg",
    )

    parser.add_argument(
        "--intro_font",
        default="Avenir-Next-Bold",
        help="Optional: Font for intro video (default: Avenir-Next-Bold). Example: --intro_font=Arial",
    )

    parser.add_argument(
        "--intro_artist_color",
        default="#ff7acc",
        help="Optional: Font color for intro video artist text (default: #ff7acc). Example: --intro_artist_color=#123456",
    )

    parser.add_argument(
        "--intro_title_color",
        default="#ffdf6b",
        help="Optional: Font color for intro video title text (default: #ffdf6b). Example: --intro_title_color=#123456",
    )

    args = parser.parse_args()

    url, artist, title = None, None, None

    # Allow 3 forms of positional arguments:
    # 1. URL only (may be single track URL or playlist URL)
    # 2. Artist and Title only
    # 3. URL, Artist, and Title
    if args.args and is_url(args.args[0]):
        url = args.args[0]
        if len(args.args) > 2:
            artist = args.args[1]
            title = args.args[2]
        else:
            logger.warn("URL provided without Artist and Title, these will be guessed from YouTube Title")

    elif len(args.args) > 1:
        artist = args.args[0]
        title = args.args[1]
        logger.warn(f"No URL provided, the top YouTube search result for {artist} - {title} will be used.")
    else:
        parser.print_help()
        exit(1)

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    logger.info(f"KaraokePrep beginning with url: {url} artist: {artist} and title: {title}")

    kprep = KaraokePrep(
        artist=artist,
        title=title,
        url=url,
        log_formatter=log_formatter,
        log_level=log_level,
        model_name=args.model_name,
        model_file_dir=args.model_file_dir,
        output_dir=args.output_dir,
        output_format=args.output_format,
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
    )

    tracks = kprep.process()

    logger.info(f"Karaoke Prep complete! Output files:")

    for track in tracks:
        logger.info(f"")
        logger.info(f"Track: {track['artist']} - {track['title']}")
        logger.info(f" YouTube Video: {track['youtube_video']}")
        logger.info(f" YouTube Audio: {track['youtube_audio']}")
        logger.info(f" YouTube Still Image: {track['youtube_still_image']}")
        logger.info(f" Lyrics: {track['lyrics']}")
        logger.info(f" Instrumental: {track['instrumental_audio']}")
        logger.info(f" Vocals: {track['vocals_audio']}")


if __name__ == "__main__":
    main()
