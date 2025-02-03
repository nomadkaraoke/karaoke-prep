#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import os
import sys
import asyncio
import json
from karaoke_prep import KaraokePrep
from karaoke_prep.karaoke_finalise import KaraokeFinalise


async def async_main():
    logger = logging.getLogger(__name__)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    parser = argparse.ArgumentParser(
        description="Automatically prepare and finalise karaoke videos in one step, combining karaoke-prep and karaoke-finalise functionality.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=54),
    )

    # Basic information (from prep_cli.py)
    parser.add_argument(
        "args",
        nargs="*",
        help="[Media or playlist URL] [Artist] [Title] of song to prep. If URL is provided, Artist and Title are optional but increase chance of fetching the correct lyrics. If Artist and Title are provided with no URL, the top YouTube search result will be fetched.",
    )

    package_version = pkg_resources.get_distribution("karaoke-prep").version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {package_version}")

    # Common arguments for both prep and finalise
    parser.add_argument(
        "--log_level",
        default="info",
        help="Optional: logging level, e.g. info, debug, warning (default: %(default)s). Example: --log_level=debug",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Optional: perform a dry run without making any changes. Example: --dry_run",
    )
    parser.add_argument(
        "--style_params_json",
        help="Optional: Path to JSON file containing style configuration. Example: --style_params_json='/path/to/style_params.json'",
    )

    # Prep-specific arguments (add any additional prep arguments you commonly use)
    parser.add_argument(
        "--output_dir",
        default=".",
        help="Optional: directory to write output files (default: <current dir>). Example: --output_dir=/app/karaoke",
    )
    parser.add_argument(
        "--no_track_subfolders",
        action="store_false",
        dest="create_track_subfolders",
        help="Optional: do NOT create a named subfolder for each track. Example: --no_track_subfolders",
    )
    parser.add_argument(
        "--existing_instrumental",
        help="Optional: Path to an existing instrumental audio file. If provided, audio separation will be skipped.",
    )
    parser.add_argument(
        "--lyrics_file",
        help="Optional: Path to a file containing lyrics to use instead of fetching from online. Example: --lyrics_file='/path/to/lyrics.txt'",
    )

    # Finalise-specific arguments
    parser.add_argument(
        "--enable_cdg",
        action="store_true",
        help="Optional: Enable CDG ZIP generation during finalisation. Example: --enable_cdg",
    )
    parser.add_argument(
        "--enable_txt",
        action="store_true",
        help="Optional: Enable TXT ZIP generation during finalisation. Example: --enable_txt",
    )
    parser.add_argument(
        "--brand_prefix",
        help="Optional: Your brand prefix to calculate the next sequential number. Example: --brand_prefix=BRAND",
    )
    parser.add_argument(
        "--organised_dir",
        help="Optional: Target directory where the processed folder will be moved. Example: --organised_dir='/path/to/Tracks-Organized'",
    )
    parser.add_argument(
        "--organised_dir_rclone_root",
        help="Optional: Rclone path which maps to your organised_dir. Example: --organised_dir_rclone_root='dropbox:Media/Karaoke/Tracks-Organized'",
    )
    parser.add_argument(
        "--public_share_dir",
        help="Optional: Public share directory for final files. Example: --public_share_dir='/path/to/Tracks-PublicShare'",
    )
    parser.add_argument(
        "--youtube_client_secrets_file",
        help="Optional: Path to youtube client secrets file. Example: --youtube_client_secrets_file='/path/to/client_secret.json'",
    )
    parser.add_argument(
        "--youtube_description_file",
        help="Optional: Path to youtube description template. Example: --youtube_description_file='/path/to/description.txt'",
    )
    parser.add_argument(
        "--rclone_destination",
        help="Optional: Rclone destination for public_share_dir sync. Example: --rclone_destination='googledrive:KaraokeFolder'",
    )
    parser.add_argument(
        "--discord_webhook_url",
        help="Optional: Discord webhook URL for notifications. Example: --discord_webhook_url='https://discord.com/api/webhooks/...'",
    )
    parser.add_argument(
        "--email_template_file",
        help="Optional: Path to email template file. Example: --email_template_file='/path/to/template.txt'",
    )

    args = parser.parse_args()

    # Parse input arguments similar to prep_cli.py
    input_media, artist, title = None, None, None

    if not args.args:
        parser.print_help()
        sys.exit(1)

    if args.args[0].startswith(("http://", "https://")) or os.path.isfile(args.args[0]):
        input_media = args.args[0]
        if len(args.args) > 2:
            artist = args.args[1]
            title = args.args[2]
    elif len(args.args) > 1:
        artist = args.args[0]
        title = args.args[1]
    else:
        parser.print_help()
        sys.exit(1)

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    # Step 1: Run KaraokePrep
    logger.info("Starting preparation phase...")
    kprep = KaraokePrep(
        artist=artist,
        title=title,
        input_media=input_media,
        dry_run=args.dry_run,
        log_formatter=log_formatter,
        log_level=log_level,
        output_dir=args.output_dir,
        create_track_subfolders=True if not hasattr(args, "create_track_subfolders") else args.create_track_subfolders,
        style_params_json=args.style_params_json,
        existing_instrumental=args.existing_instrumental,
        lyrics_file=args.lyrics_file,
    )

    tracks = await kprep.process()

    # Step 2: For each track, run KaraokeFinalise
    for track in tracks:
        logger.info(f"Starting finalisation phase for {track['artist']} - {track['title']}...")

        # Change to the track directory - use the output directory structure
        track_dir = os.path.join(args.output_dir, f"{track['artist']} - {track['title']}")
        if not os.path.exists(track_dir):
            logger.error(f"Track directory not found: {track_dir}")
            continue

        logger.info(f"Changing to directory: {track_dir}")
        os.chdir(track_dir)

        # Load CDG styles if CDG generation is enabled
        cdg_styles = None
        if args.enable_cdg:
            if not args.style_params_json:
                logger.error("CDG styles JSON file path (--style_params_json) is required when --enable_cdg is used")
                sys.exit(1)
            try:
                with open(args.style_params_json, "r") as f:
                    style_params = json.loads(f.read())
                    cdg_styles = style_params["cdg"]
            except FileNotFoundError:
                logger.error(f"CDG styles configuration file not found: {args.style_params_json}")
                sys.exit(1)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in CDG styles configuration file: {e}")
                sys.exit(1)

        # Initialize KaraokeFinalise
        kfinalise = KaraokeFinalise(
            log_formatter=log_formatter,
            log_level=log_level,
            dry_run=args.dry_run,
            enable_cdg=args.enable_cdg,
            enable_txt=args.enable_txt,
            brand_prefix=args.brand_prefix,
            organised_dir=args.organised_dir,
            organised_dir_rclone_root=args.organised_dir_rclone_root,
            public_share_dir=args.public_share_dir,
            youtube_client_secrets_file=args.youtube_client_secrets_file,
            youtube_description_file=args.youtube_description_file,
            rclone_destination=args.rclone_destination,
            discord_webhook_url=args.discord_webhook_url,
            email_template_file=args.email_template_file,
            cdg_styles=cdg_styles,
        )

        try:
            final_track = kfinalise.process()
            logger.info(f"Successfully completed auto processing for: {track['artist']} - {track['title']}")
        except Exception as e:
            logger.error(f"Error during finalisation: {str(e)}")
            raise e


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
