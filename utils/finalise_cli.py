#!/usr/bin/env python
import argparse
import logging
import pkg_resources
from karaoke_finalise import KaraokeFinalise


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
        "--model_name",
        default="UVR_MDXNET_KARA_2",
        help="Optional: model name to be used for separation (default: %(default)s). Example: --model_name=UVR-MDX-NET-Inst_HQ_3",
    )

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level.upper())
    logger.setLevel(log_level)

    logger.info(f"KaraokeFinalise beginning with model_name: {args.model_name}")

    kfinalise = KaraokeFinalise(
        log_formatter=log_formatter,
        log_level=log_level,
        model_name=args.model_name,
    )

    tracks = kfinalise.process()

    logger.info(f"Karaoke Finalisation complete! Output files:")

    for track in tracks:
        logger.info(f"")
        logger.info(f"Track: {track['artist']} - {track['title']}")
        logger.info(f" Video With Vocals: {track['video_with_vocals']}")
        logger.info(f" Video With Instrumental: {track['video_with_instrumental']}")
        logger.info(f" Final Video with Title Screen: {track['final_video']}")


if __name__ == "__main__":
    main()
