#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import os
import csv
import asyncio
from karaoke_prep import KaraokePrep
from karaoke_prep.karaoke_finalise import KaraokeFinalise


async def process_track(row, config, logger, log_formatter):
    """Process a single track through prep and finalise stages"""
    try:
        # Extract track info from CSV row
        artist = row["Artist"]
        title = row["Title"]
        guide_file = row["Mixed Audio Filename"]
        instrumental_file = row["Instrumental Audio Filename"]

        logger.info(f"Processing track: {artist} - {title}")

        # Initialize KaraokePrep
        kprep = KaraokePrep(
            artist=artist,
            title=title,
            input_media=guide_file,
            existing_instrumental=instrumental_file,
            style_params_json=config.style_params_json,
            log_formatter=log_formatter,
            log_level=config.log_level,
            dry_run=config.dry_run,
        )

        # Run prep stage
        prep_result = await kprep.process()
        if not prep_result:
            raise Exception("Prep stage failed")

        # Initialize KaraokeFinalise
        kfinalise = KaraokeFinalise(
            log_formatter=log_formatter,
            log_level=config.log_level,
            dry_run=config.dry_run,
            enable_cdg=True,
            enable_txt=True,
            brand_prefix=config.brand_prefix,
            organised_dir=config.organised_dir,
            style_params_json=config.style_params_json,
            non_interactive=True,
        )

        # Run finalise stage
        finalise_result = kfinalise.process()
        if not finalise_result:
            raise Exception("Finalise stage failed")

        return True

    except Exception as e:
        logger.error(f"Failed to process {artist} - {title}: {str(e)}")
        return False


def update_csv_status(csv_path, row_index, new_status):
    """Update the status of a processed row in the CSV file"""
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


async def async_main():
    logger = logging.getLogger(__name__)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    parser = argparse.ArgumentParser(
        description="Process multiple karaoke tracks in bulk from a CSV file.",
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=54),
    )

    # Basic information
    parser.add_argument(
        "input_csv",
        help="Path to CSV file containing tracks to process. CSV should have columns: Artist,Title,Mixed Audio Filename,Instrumental Audio Filename,Status",
    )

    package_version = pkg_resources.get_distribution("karaoke-prep").version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {package_version}")

    # Required arguments
    parser.add_argument(
        "--style_params_json",
        required=True,
        help="Path to style parameters JSON file",
    )
    parser.add_argument(
        "--brand_prefix",
        required=True,
        help="Brand prefix for output files",
    )
    parser.add_argument(
        "--organised_dir",
        required=True,
        help="Directory for organized output files",
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

    if not os.path.isfile(args.input_csv):
        logger.error(f"Input CSV file not found: {args.input_csv}")
        exit(1)

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    logger.info(f"Starting bulk processing with input CSV: {args.input_csv}")

    # Read and process CSV
    with open(args.input_csv, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)  # Convert to list to allow multiple passes

        for i, row in enumerate(rows):
            if row["Status"].lower() != "uploaded":
                logger.info(f"Skipping {row['Artist']} - {row['Title']} (Status: {row['Status']})")
                continue

            logger.info(f"Starting processing of {row['Artist']} - {row['Title']}")

            success = await process_track(row, args, logger, log_formatter)

            if not args.dry_run:
                if success:
                    update_csv_status(args.input_csv, i, "Completed")
                    logger.info(f"Successfully processed {row['Artist']} - {row['Title']}")
                else:
                    update_csv_status(args.input_csv, i, "Failed")
                    logger.error(f"Failed to process {row['Artist']} - {row['Title']}")


def main():
    # Set up logging
    logger = logging.getLogger(__name__)
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    # Run the async main function using asyncio
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
