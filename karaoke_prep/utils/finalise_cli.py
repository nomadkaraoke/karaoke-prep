#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import os
import sys
import json
import pyperclip
import time
from karaoke_prep.karaoke_finalise import KaraokeFinalise


def main():
    logger = logging.getLogger(__name__)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    parser = argparse.ArgumentParser(
        description="Render, remux and join intermediate files to create final karaoke video, as the third stage after using karaoke-prep. Processes all (Karaoke).mov files in current directory.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=62),
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
        "--enable_cdg",
        action="store_true",
        help="Optional: Enable CDG ZIP generation during finalisation (default: disabled). Example: --enable_cdg",
    )

    parser.add_argument(
        "--enable_txt",
        action="store_true",
        help="Optional: Enable TXT ZIP generation during finalisation (default: disabled). Example: --enable_txt",
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
        "--organised_dir_rclone_root",
        default=None,
        help="Optional: Rclone path which maps to your organised_dir, to generate a sharing link after adding files to it. Example: --organised_dir_rclone_root='andrewdropbox:Media/Karaoke/Tracks-Organized'",
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

    parser.add_argument(
        "--discord_webhook_url",
        default=None,
        help="Optional: Discord webhook URL to send notifications to. Example: --discord_webhook_url='https://discord.com/api/webhooks/1234567890/TOKEN/messages",
    )

    parser.add_argument(
        "--email_template_file",
        default=None,
        help="Optional: File path to email template for drafting completion email. Example: --email_template_file='/path/to/email_template.txt'",
    )

    parser.add_argument(
        "--test_email_template",
        action="store_true",
        help="Optional: Test the email template functionality with fake data. Example: --test_email_template",
    )

    parser.add_argument(
        "--style_params_json",
        default=None,
        help="Optional: Path to JSON file containing CDG style configuration. Required if --enable_cdg is used. Example: --style_params_json='/path/to/cdg_styles.json'",
    )

    parser.add_argument(
        "--keep-brand-code",
        action="store_true",
        help="Optional: Use existing brand code from current directory instead of generating new one (default: disabled). Example: --keep-brand-code",
    )

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    logger.info(f"KaraokeFinalise CLI beginning initialisation...")

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

    kfinalise = KaraokeFinalise(
        log_formatter=log_formatter,
        log_level=log_level,
        dry_run=args.dry_run,
        model_name=args.model_name,
        instrumental_format=args.instrumental_format,
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
        keep_brand_code=args.keep_brand_code,
    )

    if args.test_email_template:
        logger.info("Testing email template functionality...")
        kfinalise.test_email_template()
    else:
        try:
            track = kfinalise.process()
        except Exception as e:
            logger.error(f"An error occurred during finalisation, see stack trace below: {str(e)}")
            raise e

    logger.info(f"Karaoke finalisation processing complete! Output files:")
    logger.info(f"")
    logger.info(f"Track: {track['artist']} - {track['title']}")
    logger.info(f"")
    logger.info(f"Working Files:")
    logger.info(f" Video With Vocals: {track['video_with_vocals']}")
    logger.info(f" Video With Instrumental: {track['video_with_instrumental']}")
    logger.info(f"")
    logger.info(f"Final Videos:")
    logger.info(f" Lossless 4K MP4 (PCM): {track['final_video']}")
    logger.info(f" Lossless 4K MKV (FLAC): {track['final_video_mkv']}")
    logger.info(f" Lossy 4K MP4 (AAC): {track['final_video_lossy']}")
    logger.info(f" Lossy 720p MP4 (AAC): {track['final_video_720p']}")

    if "final_karaoke_cdg_zip" in track or "final_karaoke_txt_zip" in track:
        logger.info(f"")
        logger.info(f"Karaoke Files:")

    if "final_karaoke_cdg_zip" in track:
        logger.info(f" CDG+MP3 ZIP: {track['final_karaoke_cdg_zip']}")

    if "final_karaoke_txt_zip" in track:
        logger.info(f" TXT+MP3 ZIP: {track['final_karaoke_txt_zip']}")

    if track["brand_code"]:
        logger.info(f"")
        logger.info(f"Organization:")
        logger.info(f" Brand Code: {track['brand_code']}")
        logger.info(f" New Directory: {track['new_brand_code_dir_path']}")

    if track["youtube_url"] or track["brand_code_dir_sharing_link"]:
        logger.info(f"")
        logger.info(f"Sharing:")

    if track["youtube_url"]:
        logger.info(f" YouTube URL: {track['youtube_url']}")
        try:
            pyperclip.copy(track["youtube_url"])
            logger.info(f" (YouTube URL copied to clipboard)")
        except Exception as e:
            logger.warning(f" Failed to copy YouTube URL to clipboard: {str(e)}")

    if track["brand_code_dir_sharing_link"]:
        logger.info(f" Folder Link: {track['brand_code_dir_sharing_link']}")
        try:
            time.sleep(1)  # Brief pause between clipboard operations
            pyperclip.copy(track["brand_code_dir_sharing_link"])
            logger.info(f" (Folder link copied to clipboard)")
        except Exception as e:
            logger.warning(f" Failed to copy folder link to clipboard: {str(e)}")


if __name__ == "__main__":
    main()
