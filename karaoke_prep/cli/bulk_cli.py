#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import os
import csv
import asyncio
import json
import sys
from typing import Dict, Any, List

from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.controller import KaraokeController
from karaoke_prep.utils.logging import setup_logger

# Global logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set initial log level


async def process_track_prep(row: Dict[str, str], args: Dict[str, Any], log_formatter: logging.Formatter) -> bool:
    """
    First phase: Process a track through prep stage only, without video rendering.
    
    Args:
        row: The CSV row containing track information
        args: The parsed command-line arguments
        log_formatter: The log formatter to use
        
    Returns:
        True if processing was successful, False otherwise
    """
    original_dir = os.getcwd()
    try:
        artist = row["Artist"].strip()
        title = row["Title"].strip()
        guide_file = row["Mixed Audio Filename"].strip()
        instrumental_file = row["Instrumental Audio Filename"].strip()

        logger.info(f"Initial prep phase for track: {artist} - {title}")

        # Create configuration
        config = ProjectConfig(
            # Basic inputs
            artist=artist,
            title=title,
            input_media=guide_file,
            existing_instrumental=instrumental_file,
            
            # Workflow control
            prep_only=True,  # Only run prep phase
            render_video=False,  # No video rendering in first phase
            
            # Logging & Debugging
            logger=logger,
            log_level=args.get("log_level", logging.INFO),
            log_formatter=log_formatter,
            dry_run=args.get("dry_run", False),
            
            # Input/Output Configuration
            output_dir=args.get("output_dir", "."),
            create_track_subfolders=True,
            
            # Style Configuration
            style_params_json=args.get("style_params_json"),
        )
        
        # Create controller and process
        controller = KaraokeController(config)
        tracks = await controller.process()
        
        return True
    except Exception as e:
        logger.error(f"Failed initial prep for {artist} - {title}: {str(e)}")
        return False
    finally:
        os.chdir(original_dir)


async def process_track_render(row: Dict[str, str], args: Dict[str, Any], log_formatter: logging.Formatter) -> bool:
    """
    Second phase: Re-run prep with video rendering and run finalise.
    
    Args:
        row: The CSV row containing track information
        args: The parsed command-line arguments
        log_formatter: The log formatter to use
        
    Returns:
        True if processing was successful, False otherwise
    """
    original_dir = os.getcwd()
    try:
        artist = row["Artist"].strip()
        title = row["Title"].strip()
        guide_file = row["Mixed Audio Filename"].strip()
        instrumental_file = row["Instrumental Audio Filename"].strip()

        logger.info(f"Render phase for track: {artist} - {title}")

        # Create configuration for the render phase
        config = ProjectConfig(
            # Basic inputs
            artist=artist,
            title=title,
            input_media=guide_file,
            existing_instrumental=instrumental_file,
            
            # Workflow control
            render_video=True,
            skip_transcription_review=True,
            
            # Logging & Debugging
            logger=logger,
            log_level=args.get("log_level", logging.INFO),
            log_formatter=log_formatter,
            dry_run=args.get("dry_run", False),
            
            # Input/Output Configuration
            output_dir=args.get("output_dir", "."),
            create_track_subfolders=True,
            
            # Style Configuration
            style_params_json=args.get("style_params_json"),
            
            # Finalisation Configuration
            enable_cdg=args.get("enable_cdg", False),
            enable_txt=args.get("enable_txt", False),
            brand_prefix=args.get("brand_prefix"),
            organised_dir=args.get("organised_dir"),
            organised_dir_rclone_root=args.get("organised_dir_rclone_root"),
            public_share_dir=args.get("public_share_dir"),
            youtube_client_secrets_file=args.get("youtube_client_secrets_file"),
            youtube_description_file=args.get("youtube_description_file"),
            rclone_destination=args.get("rclone_destination"),
            discord_webhook_url=args.get("discord_webhook_url"),
            email_template_file=args.get("email_template_file"),
            non_interactive=True,  # Always run in non-interactive mode for bulk processing
        )
        
        # Create controller and process
        controller = KaraokeController(config)
        tracks = await controller.process()
        
        logger.info(f"Successfully completed auto processing for: {artist} - {title}")
        return True
    except Exception as e:
        logger.error(f"Failed render/finalise for {artist} - {title}: {str(e)}")
        return False
    finally:
        os.chdir(original_dir)


def update_csv_status(csv_path: str, row_index: int, new_status: str) -> None:
    """
    Update the status of a processed row in the CSV file.
    
    Args:
        csv_path: The path to the CSV file
        row_index: The index of the row to update
        new_status: The new status to set
    """
    # Read all rows
    with open(csv_path, "r") as f:
        rows = list(csv.DictReader(f))

    # Update status for the processed row
    rows[row_index]["Status"] = new_status

    # Write back to CSV
    fieldnames = rows[0].keys()
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


async def async_main() -> None:
    """
    Main async function for bulk processing.
    """
    parser = argparse.ArgumentParser(
        description="Process multiple karaoke tracks in bulk from a CSV file.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=54),
    )

    # Basic information
    parser.add_argument(
        "input_csv",
        help="Path to CSV file containing tracks to process. CSV should have columns: Artist,Title,Mixed Audio Filename,Instrumental Audio Filename,Status",
    )

    package_version = pkg_resources.get_distribution("karaoke-gen").version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {package_version}")

    # Required arguments
    parser.add_argument(
        "--style_params_json",
        required=True,
        help="Path to style parameters JSON file",
    )
    parser.add_argument(
        "--output_dir",
        default=".",
        help="Optional: directory to write output files (default: <current dir>). Example: --output_dir=/app/karaoke",
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
    
    # Distribution-specific arguments
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

    # Logging & Debugging
    parser.add_argument(
        "--log_level",
        default="info",
        help="Optional: logging level, e.g. info, debug, warning (default: %(default)s). Example: --log_level=debug",
    )
    parser.add_argument(
        "--dry_run",
        action="store_true",
        help="Optional: perform a dry run without making any changes (default: %(default)s). Example: --dry_run",
    )

    args = parser.parse_args()

    # Convert input_csv to absolute path
    args.input_csv = os.path.abspath(args.input_csv)

    if not os.path.isfile(args.input_csv):
        logger.error(f"Input CSV file not found: {args.input_csv}")
        exit(1)

    # Fix: Convert log level to uppercase before getting attribute
    log_level = getattr(logging, args.log_level.upper())
    args.log_level = log_level  # Store the numeric log level in args

    # Convert args to dictionary for easier access
    args_dict = vars(args)

    logger.info(f"Starting bulk processing with input CSV: {args.input_csv}")

    # Read CSV
    with open(args.input_csv, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Phase 1: Initial prep for all tracks
    logger.info("Starting Phase 1: Initial prep for all tracks")
    for i, row in enumerate(rows):
        if row["Status"].lower() != "uploaded":
            logger.info(f"Skipping {row['Artist']} - {row['Title']} (Status: {row['Status']})")
            continue

        success = await process_track_prep(row, args_dict, log_formatter)
        if not args.dry_run:
            if success:
                update_csv_status(args.input_csv, i, "Prep_Complete")
            else:
                update_csv_status(args.input_csv, i, "Prep_Failed")

    # Phase 2: Render and finalise all tracks
    logger.info("Starting Phase 2: Render and finalise for all tracks")
    for i, row in enumerate(rows):
        if row["Status"].lower() not in ["prep_complete", "uploaded"]:
            logger.info(f"Skipping {row['Artist']} - {row['Title']} (Status: {row['Status']})")
            continue

        success = await process_track_render(row, args_dict, log_formatter)
        if not args.dry_run:
            if success:
                update_csv_status(args.input_csv, i, "Completed")
            else:
                update_csv_status(args.input_csv, i, "Render_Failed")


def main() -> None:
    """
    Main entry point for bulk processing.
    """
    # Set up logging only once
    global log_formatter  # Make log_formatter accessible to other functions
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    # Run the async main function using asyncio
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
