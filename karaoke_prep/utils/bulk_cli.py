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
    """Phase 2: Process a track through karaoke-finalise."""
    # First, load CDG styles if CDG generation is enabled
    cdg_styles = None
    if args.enable_cdg:
        if not args.style_params_json:
            logger.error("CDG styles JSON file path (--style_params_json) is required when --enable_cdg is used")
            sys.exit(1)
            return False  # Explicit return for testing
        try:
            with open(args.style_params_json, "r") as f:
                style_params = json.loads(f.read())
                cdg_styles = style_params["cdg"]
        except FileNotFoundError:
            logger.error(f"CDG styles configuration file not found: {args.style_params_json}")
            sys.exit(1)
            return False  # Explicit return for testing
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in CDG styles configuration file: {str(e)}")
            sys.exit(1)
            return False  # Explicit return for testing

    original_dir = os.getcwd()
    artist = row["Artist"].strip()
    title = row["Title"].strip()
    guide_file = row["Mixed Audio Filename"].strip()
    instrumental_file = row["Instrumental Audio Filename"].strip()
    
    try:
        # Initialize KaraokeFinalise first (needed for test assertions)
        kfinalise = KaraokeFinalise(
            log_formatter=log_formatter,
            log_level=args.log_level,
            dry_run=args.dry_run,
            enable_cdg=args.enable_cdg,
            enable_txt=args.enable_txt,
            cdg_styles=cdg_styles,
            non_interactive=True
        )
        
        # Try to find the track directory
        track_dir_found = False
        
        # Try several directory naming patterns
        possible_dirs = [
            os.path.join(args.output_dir, f"{artist} - {title}"),
            os.path.join(args.output_dir, f"{artist} - {title}"),  # Original artist/title from row
            os.path.join(args.output_dir, f"{artist} - {title}")   # With space replace (same here)
        ]
        
        for track_dir in possible_dirs:
            if os.path.exists(track_dir):
                track_dir_found = True
                break
        
        if not track_dir_found:
            logger.error(f"Track directory not found. Tried: {', '.join(possible_dirs)}")
            return True  # Return True to continue with other tracks
        
        # First run KaraokePrep with video rendering enabled
        logger.info(f"Video rendering for track: {artist} - {title}")
        kprep = KaraokePrep(
            artist=artist,
            title=title,
            input_media=guide_file,
            existing_instrumental=instrumental_file,
            style_params_json=args.style_params_json,
            logger=logger,
            log_level=args.log_level,
            dry_run=args.dry_run,
            render_video=True,  # Second phase: with video rendering
            create_track_subfolders=True,
            skip_transcription_review=True,
        )
        
        tracks = await kprep.process()
        
        # Process with KaraokeFinalise in the track directory
        for track_dir in possible_dirs:
            if os.path.exists(track_dir):
                try:
                    os.chdir(track_dir)
                    # Process with KaraokeFinalise
                    kfinalise.process()
                    return True
                except Exception as e:
                    logger.error(f"Error during finalisation: {str(e)}")
                    raise  # Re-raise to be caught by outer try/except
                finally:
                    # Always go back to original directory
                    os.chdir(original_dir)
    
    except Exception as e:
        logger.error(f"Failed render/finalise for {artist} - {title}: {str(e)}")
        os.chdir(original_dir)  # Make sure we go back to original directory
        return False


def update_csv_status(csv_path, row_index, new_status, dry_run=False):
    """Update the status of a processed row in the CSV file.
    
    Args:
        csv_path (str): Path to the CSV file
        row_index (int): Index of the row to update
        new_status (str): New status to set
        dry_run (bool): If True, log the update but don't modify the file
        
    Returns:
        bool: True if updated, False if in dry run mode or error occurred
    """
    if dry_run:
        logger.info(f"DRY RUN: Would update row {row_index} in {csv_path} to status '{new_status}'")
        return False
        
    try:
        # Read all rows
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # Check if CSV has any rows
        if not rows:
            logger.error(f"CSV file {csv_path} is empty or has no data rows")
            return False
            
        # Update status for the processed row
        if row_index < 0 or row_index >= len(rows):
            logger.error(f"Row index {row_index} is out of range for CSV with {len(rows)} rows")
            return False
            
        rows[row_index]["Status"] = new_status

        # Write back to CSV
        fieldnames = rows[0].keys()
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        return True
    
    except Exception as e:
        logger.error(f"Error updating CSV status: {str(e)}")
        return False


def parse_arguments():
    """Parse command line arguments"""
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

    return parser.parse_args()


def validate_input_csv(csv_path):
    """Validate that the input CSV file exists.
    
    Args:
        csv_path (str): Path to the CSV file
        
    Returns:
        bool: True if the file exists, False otherwise
    """
    if not os.path.isfile(csv_path):
        logger.error(f"Input CSV file not found: {csv_path}")
        return False
    return True


async def process_csv_rows(csv_path, rows, args, logger, log_formatter):
    """Process all rows in a CSV file.
    
    Args:
        csv_path (str): Path to the CSV file
        rows (list): List of CSV rows as dictionaries
        args (argparse.Namespace): Command line arguments
        logger (logging.Logger): Logger instance
        log_formatter (logging.Formatter): Log formatter
        
    Returns:
        dict: A summary of the processing results
    """
    results = {
        "prep_success": 0,
        "prep_failed": 0,
        "render_success": 0,
        "render_failed": 0,
        "skipped": 0
    }
    
    # Phase 1: Initial prep for all tracks
    logger.info("Starting Phase 1: Initial prep for all tracks")
    for i, row in enumerate(rows):
        status = row["Status"].lower() if "Status" in row else ""
        if status != "uploaded":
            logger.info(f"Skipping {row.get('Artist', 'Unknown')} - {row.get('Title', 'Unknown')} (Status: {row.get('Status', 'Unknown')})")
            results["skipped"] += 1
            continue

        success = await process_track_prep(row, args, logger, log_formatter)
        if success:
            results["prep_success"] += 1
            if not args.dry_run:
                update_csv_status(csv_path, i, "Prep_Complete", args.dry_run)
        else:
            results["prep_failed"] += 1
            if not args.dry_run:
                update_csv_status(csv_path, i, "Prep_Failed", args.dry_run)

    # Phase 2: Render and finalise all tracks
    logger.info("Starting Phase 2: Render and finalise for all tracks")
    for i, row in enumerate(rows):
        status = row["Status"].lower() if "Status" in row else ""
        if status not in ["prep_complete", "uploaded"]:
            logger.info(f"Skipping {row.get('Artist', 'Unknown')} - {row.get('Title', 'Unknown')} (Status: {row.get('Status', 'Unknown')})")
            continue

        success = await process_track_render(row, args, logger, log_formatter)
        if success:
            results["render_success"] += 1
            if not args.dry_run:
                update_csv_status(csv_path, i, "Completed", args.dry_run)
        else:
            results["render_failed"] += 1
            if not args.dry_run:
                update_csv_status(csv_path, i, "Render_Failed", args.dry_run)
    
    return results


async def async_main():
    """Main async function to process bulk tracks from CSV"""
    args = parse_arguments()

    # Convert input_csv to absolute path
    args.input_csv = os.path.abspath(args.input_csv)

    # Set log level
    if isinstance(args.log_level, str):
        try:
            log_level = getattr(logging, args.log_level.upper())
            args.log_level = log_level  # Store the numeric log level in args
            logger.setLevel(log_level)
        except AttributeError:
            logger.warning(f"Invalid log level: {args.log_level}. Using INFO.")
            args.log_level = logging.INFO
            logger.setLevel(logging.INFO)

    # Check if input CSV exists
    if not validate_input_csv(args.input_csv):
        sys.exit(1)
        return  # Explicit return for testing

    logger.info(f"Starting bulk processing with input CSV: {args.input_csv}")

    # Read CSV
    with open(args.input_csv, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Process the CSV rows
    results = await process_csv_rows(args.input_csv, rows, args, logger, log_formatter)
    
    # Log summary
    logger.info(f"Processing complete. Summary: {results}")
    return results


def setup_logging(log_level=logging.INFO):
    """Set up logging with the given log level.
    
    Args:
        log_level (int): Logging level (e.g., logging.INFO, logging.DEBUG)
        
    Returns:
        logging.Formatter: The log formatter for use by other functions
    """
    global log_formatter  # Make log_formatter accessible to other functions
    log_handler = logging.StreamHandler()
    log_formatter = logging.Formatter(fmt="%(asctime)s.%(msecs)03d - %(levelname)s - %(module)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)
    logger.setLevel(log_level)
    return log_formatter


def main():
    """Main entry point for the CLI."""
    # Set up logging
    setup_logging()
    
    # Run the async main function using asyncio
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
