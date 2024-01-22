#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import os
import sys
from karaoke_prep.karaoke_finalise import KaraokeFinalise


def main():
    logger = logging.getLogger(__name__)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    parser = argparse.ArgumentParser(
        description="Render, remux and join intermediate files to create final karaoke video, as the third stage after using karaoke-prep. Processes all (Karaoke).mov files in current directory.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=54),
    )

    package_version = pkg_resources.get_distribution("karaoke-prep").version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {package_version}")

    parser.add_argument(
        "--log_level",
        default="info",
        help="Optional: logging level, e.g. info, debug, warning (default: %(default)s). Example: --log_level=debug",
    )

    parser.add_argument(
        "--dry_run",
        "-n",
        action="store_true",
        help="Optional: Enable dry run mode to print actions without executing them (default: disabled). Example: -n or --dry_run",
    )

    parser.add_argument(
        "--model_name",
        default=None,
        help="Optional: specific model name to be used for separation (default: interactive prompt). Example: --model_name=UVR-MDX-NET-Inst_HQ_3",
    )

    parser.add_argument(
        "--instrumental_format",
        default="flac",
        help="Optional: format / file extension for instrumental track to use for remux (default: %(default)s). Example: --instrumental_format=mp3",
    )

    parser.add_argument(
        "--brand_prefix",
        default=None,
        help="Optional: Your brand prefix to calculate the next sequential number and move the resulting folder. Example: --brand_prefix=BRAND",
    )

    parser.add_argument(
        "--organised_dir",
        default=None,
        help="Optional: Target directory where the processed folder will be moved after finalisation. Example: --organised_dir='/path/to/Tracks-Organized'",
    )

    parser.add_argument(
        "--public_share_dir",
        default=None,
        help="Optional: Public share directory where final MP4 and ZIP files will be copied. Example: --public_share_dir='/path/to/Tracks-PublicShare'",
    )

    parser.add_argument(
        "--youtube_client_secrets_file",
        default=None,
        help="Optional: File path to youtube client secrets file. Example: --youtube_client_secrets_file='/path/to/client_secret_1234567890_apps.googleusercontent.com.json'",
    )

    parser.add_argument(
        "--youtube_description_file",
        default=None,
        help="Optional: File path to youtube video description text for uploaded videos. Example: --youtube_description_file='/path/to/youtube_description.txt'",
    )

    parser.add_argument(
        "--rclone_destination",
        default=None,
        help="Optional: Rclone destination to sync your public_share_dir to after adding files to it. Example: --rclone_destination='googledrive:YourBrandNameFolder'",
    )

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    logger.info(f"KaraokeFinalise CLI beginning initialisation...")

    kfinalise = KaraokeFinalise(
        log_formatter=log_formatter,
        log_level=log_level,
        dry_run=args.dry_run,
        model_name=args.model_name,
        instrumental_format=args.instrumental_format,
        brand_prefix=args.brand_prefix,
        organised_dir=args.organised_dir,
        public_share_dir=args.public_share_dir,
        youtube_client_secrets_file=args.youtube_client_secrets_file,
        youtube_description_file=args.youtube_description_file,
        rclone_destination=args.rclone_destination,
        discord_webhook_url=os.environ.get("DISCORD_WEBHOOK_URL"),
    )

    try:
        track = kfinalise.process()
    except Exception as e:
        logger.error(f"An error occurred during finalisation, see stack trace below: {str(e)}")
        raise e

    logger.info(f"Karaoke finalisation processing complete! Output files:")
    logger.info(f"")
    logger.info(f"Track: {track['artist']} - {track['title']}")
    logger.info(f" Video With Vocals: {track['video_with_vocals']}")
    logger.info(f" Video With Instrumental: {track['video_with_instrumental']}")
    logger.info(f" Final CDG+MP3 ZIP: {track['final_video']}")
    logger.info(f" Final Video with Title: {track['final_zip']}")
    logger.info(f" YouTube URL: {track['youtube_url']}")
    logger.info(f" Brand Code: {track['brand_code']}")
    logger.info(f" New Brand Code Directory: {track['new_brand_code_dir_path']}")


if __name__ == "__main__":
    main()
