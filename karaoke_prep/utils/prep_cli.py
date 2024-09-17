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
            "UVR_MDXNET_KARA_2.onnx",
            "mel_band_roformer_karaoke_aufr33_viperx_sdr_10.1956.ckpt",
            "2_HP-UVR.pth",
            "model_bs_roformer_ep_317_sdr_12.9755.yaml",
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
        "--end_extra_text",
        default="THANK YOU FOR SINGING!",
        help="Optional: Extra text to display on the end screen video. Example: --end_extra_text='THANK YOU FOR WATCHING!'",
    )

    parser.add_argument(
        "--end_font",
        default="Montserrat-Bold.ttf",
        help="Optional: Font file for end screen video (default: Montserrat-Bold.ttf). Example: --end_font=AvenirNext-Bold.ttf",
    )

    parser.add_argument(
        "--end_extra_text_color",
        default="#ff7acc",
        help="Optional: Font color for end screen video text (default: #ffffff). Example: --end_extra_text_color=#123456",
    )

    parser.add_argument(
        "--end_artist_color",
        default="#ffdf6b",
        help="Optional: Font color for end screen video artist text (default: #ffdf6b). Example: --end_artist_color=#123456",
    )

    parser.add_argument(
        "--end_title_color",
        default="#ffffff",
        help="Optional: Font color for end screen video title text (default: #ffffff). Example: --end_title_color=#123456",
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

    parser.add_argument(
        "--title_initial_font_size",
        type=int,
        default=500,
        help="Optional: Initial font size for title video (default: 500). Example: --title_initial_font_size=600",
    )
    parser.add_argument(
        "--title_top_padding",
        type=int,
        default=950,
        help="Optional: Top padding for title video (default: 950). Example: --title_top_padding=1000",
    )
    parser.add_argument(
        "--title_title_padding",
        type=int,
        default=400,
        help="Optional: Title padding for title video (default: 400). Example: --title_title_padding=450",
    )
    parser.add_argument(
        "--title_artist_padding",
        type=int,
        default=700,
        help="Optional: Artist padding for title video (default: 700). Example: --title_artist_padding=750",
    )
    parser.add_argument(
        "--title_fixed_gap",
        type=int,
        default=150,
        help="Optional: Fixed gap for title video (default: 150). Example: --title_fixed_gap=200",
    )
    parser.add_argument(
        "--end_initial_font_size",
        type=int,
        default=500,
        help="Optional: Initial font size for end video (default: 500). Example: --end_initial_font_size=600",
    )
    parser.add_argument(
        "--end_top_padding",
        type=int,
        default=950,
        help="Optional: Top padding for end video (default: 950). Example: --end_top_padding=1000",
    )
    parser.add_argument(
        "--end_title_padding",
        type=int,
        default=400,
        help="Optional: Title padding for end video (default: 400). Example: --end_title_padding=450",
    )
    parser.add_argument(
        "--end_artist_padding",
        type=int,
        default=700,
        help="Optional: Artist padding for end video (default: 700). Example: --end_artist_padding=750",
    )
    parser.add_argument(
        "--end_extra_text_padding",
        type=int,
        default=300,
        help="Optional: Extra text padding for end video (default: 600). Example: --end_extra_text_padding=650",
    )
    parser.add_argument(
        "--end_fixed_gap",
        type=int,
        default=150,
        help="Optional: Fixed gap for end video (default: 150). Example: --end_fixed_gap=200",
    )

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
        existing_instrumental=args.existing_instrumental,
        existing_title_image=args.existing_title_image,
        existing_end_image=args.existing_end_image,
        title_video_duration=args.title_video_duration,
        intro_background_color=args.intro_background_color,
        intro_background_image=args.intro_background_image,
        intro_font=args.intro_font,
        intro_artist_color=args.intro_artist_color,
        intro_title_color=args.intro_title_color,
        title_initial_font_size=args.title_initial_font_size,
        title_top_padding=args.title_top_padding,
        title_title_padding=args.title_title_padding,
        title_artist_padding=args.title_artist_padding,
        title_fixed_gap=args.title_fixed_gap,
        end_video_duration=args.end_video_duration,
        end_extra_text=args.end_extra_text,
        end_background_color=args.end_background_color,
        end_background_image=args.end_background_image,
        end_font=args.end_font,
        end_extra_text_color=args.end_extra_text_color,
        end_artist_color=args.end_artist_color,
        end_title_color=args.end_title_color,
        end_initial_font_size=args.end_initial_font_size,
        end_top_padding=args.end_top_padding,
        end_title_padding=args.end_title_padding,
        end_artist_padding=args.end_artist_padding,
        end_extra_text_padding=args.end_extra_text_padding,
        end_fixed_gap=args.end_fixed_gap,
        lyrics_artist=args.lyrics_artist,
        lyrics_title=args.lyrics_title,
        skip_lyrics=args.skip_lyrics,
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
