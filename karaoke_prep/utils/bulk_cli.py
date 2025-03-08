#!/usr/bin/env python
import argparse
import logging
import pkg_resources
import os
import csv
import asyncio
import json
import sys
from karaoke_prep import KaraokePrep
from karaoke_prep.karaoke_finalise import KaraokeFinalise

# Global logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set initial log level


async def process_track_prep(row, args, logger, log_formatter):
    """First phase: Process a track through prep stage only, without video rendering"""
    original_dir = os.getcwd()
    try:
        artist = row["Artist"].strip()
        title = row["Title"].strip()
        guide_file = row["Mixed Audio Filename"].strip()
        instrumental_file = row["Instrumental Audio Filename"].strip()

        logger.info(f"Initial prep phase for track: {artist} - {title}")

        kprep = KaraokePrep(
            artist=artist,
            title=title,
            input_media=guide_file,
            existing_instrumental=instrumental_file,
            style_params_json=args.style_params_json,
            logger=logger,
            log_level=args.log_level,
            dry_run=args.dry_run,
            render_video=False,  # First phase: no video rendering
            create_track_subfolders=True,
        )

        tracks = await kprep.process()
        return True
    except Exception as e:
        logger.error(f"Failed initial prep for {artist} - {title}: {str(e)}")
        return False
    finally:
        os.chdir(original_dir)


async def process_track_render(row, args, logger, log_formatter):
    """Second phase: Re-run prep with video rendering and run finalise"""
    # This is mostly the same as the original process_track function
    # but with render_video=True and includes finalisation
    original_dir = os.getcwd()
    try:
        artist = row["Artist"].strip()
        title = row["Title"].strip()
        guide_file = row["Mixed Audio Filename"].strip()
        instrumental_file = row["Instrumental Audio Filename"].strip()

        logger.info(f"Render phase for track: {artist} - {title}")

        kprep = KaraokePrep(
            artist=artist,
            title=title,
            input_media=guide_file,
            existing_instrumental=instrumental_file,
            style_params_json=args.style_params_json,
            logger=logger,
            log_level=args.log_level,
            dry_run=args.dry_run,
            render_video=True,
            create_track_subfolders=True,
            skip_transcription_review=True,
        )

        tracks = await kprep.process()

        # Step 2: For each track, run KaraokeFinalise
        for track in tracks:
            logger.info(f"Starting finalisation phase for {track['artist']} - {track['title']}...")

            # Look for the track directory, trying different possible formats
            possible_dirs = [
                os.path.join(args.output_dir, f"{track['artist']} - {track['title']}"),
                os.path.join(args.output_dir, f"{artist} - {title}"),
                os.path.join(args.output_dir, f"{artist.replace('  ', ' ')} - {title}"),
            ]

            track_dir = None
            for possible_dir in possible_dirs:
                if os.path.exists(possible_dir):
                    track_dir = possible_dir
                    break

            if track_dir is None:
                logger.error(f"Track directory not found. Tried: {possible_dirs}")
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
                log_level=args.log_level,
                dry_run=args.dry_run,
                enable_cdg=args.enable_cdg,
                enable_txt=args.enable_txt,
                cdg_styles=cdg_styles,
                non_interactive=True,
            )

            try:
                final_track = kfinalise.process()
                logger.info(f"Successfully completed auto processing for: {track['artist']} - {track['title']}")
            except Exception as e:
                logger.error(f"Error during finalisation: {str(e)}")
                raise e

            # Always return to the original directory after processing
            os.chdir(original_dir)

        return True

    except Exception as e:
        logger.error(f"Failed render/finalise for {artist} - {title}: {str(e)}")
        return False
    finally:
        os.chdir(original_dir)


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

        success = await process_track_prep(row, args, logger, log_formatter)
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

        success = await process_track_render(row, args, logger, log_formatter)
        if not args.dry_run:
            if success:
                update_csv_status(args.input_csv, i, "Completed")
            else:
                update_csv_status(args.input_csv, i, "Render_Failed")


def main():
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
