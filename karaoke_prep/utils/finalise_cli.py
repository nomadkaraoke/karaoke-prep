#!/usr/bin/env python
import argparse
import logging
import pkg_resources
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
        action="store_true",
        help="Optional: Enable dry run mode to print actions without executing them (default: disabled). Example: --dry_run",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Optional: Force processing even if final output file exists (default: disabled). Example: --force",
    )

    parser.add_argument(
        "--model_name",
        default="UVR_MDXNET_KARA_2",
        help="Optional: model name to be used for separation (default: %(default)s). Example: --model_name=UVR-MDX-NET-Inst_HQ_3",
    )

    parser.add_argument(
        "--brand_prefix",
        default=None,
        help="Optional: Your brand prefix to calculate the next sequential number and move the resulting folder. Example: --brand_prefix=BRAND",
    )

    parser.add_argument(
        "--target_dir",
        default=None,
        help="Optional: Target directory where the processed folder will be moved after finalisation. Example: --target_dir='/path/to/Tracks-Organized'",
    )

    parser.add_argument(
        "--public_share_dir",
        default=None,
        help="Optional: Public share directory where final MP4 and ZIP files will be copied. Example: --public_share_dir='/path/to/Tracks-PublicShare'",
    )

    parser.add_argument(
        "--rclone_destination",
        default=None,
        help="Optional: Rclone destination to sync your public_share_dir to after adding files to it. Example: --rclone_destination='googledrive:YourBrandNameFolder'",
    )

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    logger.info(f"KaraokeFinalise beginning with model_name: {args.model_name}")

    kfinalise = KaraokeFinalise(
        log_formatter=log_formatter,
        log_level=log_level,
        dry_run=args.dry_run,
        force=args.force,
        model_name=args.model_name,
        brand_prefix=args.brand_prefix,
        target_dir=args.target_dir,
        public_share_dir=args.public_share_dir,
        rclone_destination=args.rclone_destination,
    )

    tracks = kfinalise.process()

    if len(tracks) == 0:
        logger.error(f"No tracks found to process.")
        return

    logger.info(f"Karaoke finalisation processing complete! Output files:")
    for track in tracks:
        logger.info(f"")
        logger.info(f"Track: {track['artist']} - {track['title']}")
        logger.info(f" Video With Vocals: {track['video_with_vocals']}")
        logger.info(f" Video With Instrumental: {track['video_with_instrumental']}")
        logger.info(f" Final CDG+MP3 ZIP: {track['final_video']}")
        logger.info(f" Final Video with Title: {track['final_zip']}")


if __name__ == "__main__":
    main()
