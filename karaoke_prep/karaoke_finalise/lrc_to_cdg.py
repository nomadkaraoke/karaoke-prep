#!/usr/bin/env python3

import logging
import re
import toml
import argparse
from pathlib import Path
import sys
from PIL import ImageFont
import os
import json
from lyrics_transcriber.output.cdgmaker.composer import KaraokeComposer
from lyrics_transcriber.output.cdgmaker.render import get_wrapped_text

# Keep only the truly constant values that aren't style-related
CDG_VISIBLE_WIDTH = 280

# Create a logger specific to this module
logger = logging.getLogger(__name__)


def parse_lrc(lrc_file):
    with open(lrc_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract timestamps and lyrics
    pattern = r"\[(\d{2}):(\d{2})\.(\d{3})\](\d+:)?(/?.*)"
    matches = re.findall(pattern, content)

    if not matches:
        raise ValueError(f"No valid lyrics found in the LRC file: {lrc_file}")

    lyrics = []
    for match in matches:
        minutes, seconds, milliseconds = map(int, match[:3])
        timestamp = (minutes * 60 + seconds) * 100 + int(milliseconds / 10)  # Convert to centiseconds
        text = match[4].strip().upper()
        if text:  # Only add non-empty lyrics
            lyrics.append({"timestamp": timestamp, "text": text})
            # logger.debug(f"Parsed lyric: {timestamp} - {text}")

    logger.info(f"Found {len(lyrics)} lyric lines")
    return lyrics


def detect_instrumentals(
    lyrics_data,
    line_tile_height,
    instrumental_font_color,
    instrumental_background,
    instrumental_transition,
    instrumental_gap_threshold,
    instrumental_text,
):
    instrumentals = []
    for i in range(len(lyrics_data) - 1):
        current_end = lyrics_data[i]["timestamp"]
        next_start = lyrics_data[i + 1]["timestamp"]
        gap = next_start - current_end
        if gap >= instrumental_gap_threshold:
            instrumental_start = current_end + 200  # Add 2 seconds (200 centiseconds) delay
            instrumental_duration = (gap - 200) // 100  # Convert to seconds
            instrumentals.append(
                {
                    "sync": instrumental_start,
                    "wait": True,
                    "text": f"{instrumental_text}\n{instrumental_duration} seconds\n",
                    "text_align": "center",
                    "text_placement": "bottom middle",
                    "line_tile_height": line_tile_height,
                    "fill": instrumental_font_color,
                    "stroke": "",
                    "image": instrumental_background,
                    "transition": instrumental_transition,
                }
            )
            logger.info(
                f"Detected instrumental: Gap of {gap} cs, starting at {instrumental_start} cs, duration {instrumental_duration} seconds"
            )

    logger.info(f"Total instrumentals detected: {len(instrumentals)}")
    return instrumentals


def generate_toml(
    lrc_file,
    audio_file,
    title,
    artist,
    output_file,
    cdg_styles,
):
    """
    Generate a TOML configuration file for CDG creation.

    Args:
        cdg_styles (dict): Must contain all style-related parameters:
            - title_color
            - artist_color
            - background_color
            - border_color
            - font_path
            - font_size
            - stroke_width
            - stroke_style
            - active_fill
            - active_stroke
            - inactive_fill
            - inactive_stroke
            - title_screen_background
            - instrumental_background
            - instrumental_transition
            - instrumental_font_color
            - title_screen_transition
            - row
            - line_tile_height
            - lines_per_page
            - clear_mode
            - sync_offset
            - instrumental_gap_threshold
            - instrumental_text
            - lead_in_threshold
            - lead_in_symbols
            - lead_in_duration
            - lead_in_total
            - title_artist_gap
            - intro_duration_seconds
            - first_syllable_buffer_seconds
            - outro_background
            - outro_transition
            - outro_text_line1
            - outro_text_line2
            - outro_line1_color
            - outro_line2_color
            - outro_line1_line2_gap
    """
    # Validate required style parameters
    required_styles = {
        "title_color",
        "artist_color",
        "background_color",
        "border_color",
        "font_path",
        "font_size",
        "stroke_width",
        "stroke_style",
        "active_fill",
        "active_stroke",
        "inactive_fill",
        "inactive_stroke",
        "title_screen_background",
        "instrumental_background",
        "instrumental_transition",
        "instrumental_font_color",
        "title_screen_transition",
        "row",
        "line_tile_height",
        "lines_per_page",
        "clear_mode",
        "sync_offset",
        "instrumental_gap_threshold",
        "instrumental_text",
        "lead_in_threshold",
        "lead_in_symbols",
        "lead_in_duration",
        "lead_in_total",
        "title_artist_gap",
        "intro_duration_seconds",
        "first_syllable_buffer_seconds",
        "outro_background",
        "outro_transition",
        "outro_text_line1",
        "outro_text_line2",
        "outro_line1_color",
        "outro_line2_color",
        "outro_line1_line2_gap",
    }

    missing_styles = required_styles - set(cdg_styles.keys())
    if missing_styles:
        raise ValueError(f"Missing required style parameters: {', '.join(missing_styles)}")

    try:
        lyrics_data = parse_lrc(lrc_file)
    except ValueError as e:
        logger.error(f"Error parsing LRC file: {e}")
        return

    if not lyrics_data:
        logger.error(f"No lyrics data found in the LRC file: {lrc_file}")
        return

    sync_times = []
    formatted_lyrics = []

    for i, lyric in enumerate(lyrics_data):
        logger.debug(f"Processing lyric {i}: timestamp {lyric['timestamp']}, text '{lyric['text']}'")

        if i == 0 or lyric["timestamp"] - lyrics_data[i - 1]["timestamp"] >= cdg_styles["lead_in_threshold"]:
            lead_in_start = lyric["timestamp"] - cdg_styles["lead_in_total"]
            logger.debug(f"Adding lead-in before lyric {i} at timestamp {lead_in_start}")
            for j, symbol in enumerate(cdg_styles["lead_in_symbols"]):
                sync_time = lead_in_start + j * cdg_styles["lead_in_duration"]
                sync_times.append(sync_time)
                formatted_lyrics.append(symbol)
                logger.debug(f"  Added lead-in symbol {j+1}: '{symbol}' at {sync_time}")

        sync_times.append(lyric["timestamp"])
        formatted_lyrics.append(lyric["text"])
        logger.debug(f"Added lyric: '{lyric['text']}' at {lyric['timestamp']}")

    instrumentals = detect_instrumentals(
        lyrics_data,
        line_tile_height=cdg_styles["line_tile_height"],
        instrumental_font_color=cdg_styles["instrumental_font_color"],
        instrumental_background=cdg_styles["instrumental_background"],
        instrumental_transition=cdg_styles["instrumental_transition"],
        instrumental_gap_threshold=cdg_styles["instrumental_gap_threshold"],
        instrumental_text=cdg_styles["instrumental_text"],
    )

    formatted_lyrics = format_lyrics(
        formatted_lyrics, instrumentals, sync_times, font_path=cdg_styles["font_path"], font_size=cdg_styles["font_size"]
    )

    toml_data = {
        "title": title,
        "artist": artist,
        "file": audio_file,
        "outname": Path(lrc_file).stem,
        "clear_mode": cdg_styles["clear_mode"],
        "sync_offset": cdg_styles["sync_offset"],
        "background": cdg_styles["background_color"],
        "border": cdg_styles["border_color"],
        "font": cdg_styles["font_path"],
        "font_size": cdg_styles["font_size"],
        "stroke_width": cdg_styles["stroke_width"],
        "stroke_style": cdg_styles["stroke_style"],
        "singers": [
            {
                "active_fill": cdg_styles["active_fill"],
                "active_stroke": cdg_styles["active_stroke"],
                "inactive_fill": cdg_styles["inactive_fill"],
                "inactive_stroke": cdg_styles["inactive_stroke"],
            }
        ],
        "lyrics": [
            {
                "singer": 1,
                "sync": sync_times,
                "row": cdg_styles["row"],
                "line_tile_height": cdg_styles["line_tile_height"],
                "lines_per_page": cdg_styles["lines_per_page"],
                "text": formatted_lyrics,
            }
        ],
        "title_color": cdg_styles["title_color"],
        "artist_color": cdg_styles["artist_color"],
        "title_screen_background": cdg_styles["title_screen_background"],
        "title_screen_transition": cdg_styles["title_screen_transition"],
        "instrumentals": instrumentals,
        "intro_duration_seconds": cdg_styles["intro_duration_seconds"],
        "first_syllable_buffer_seconds": cdg_styles["first_syllable_buffer_seconds"],
        "outro_background": cdg_styles["outro_background"],
        "outro_transition": cdg_styles["outro_transition"],
        "outro_text_line1": cdg_styles["outro_text_line1"],
        "outro_text_line2": cdg_styles["outro_text_line2"],
        "outro_line1_color": cdg_styles["outro_line1_color"],
        "outro_line2_color": cdg_styles["outro_line2_color"],
        "outro_line1_line2_gap": cdg_styles["outro_line1_line2_gap"],
    }

    with open(output_file, "w", encoding="utf-8") as f:
        toml.dump(toml_data, f)
    logger.info(f"TOML file generated: {output_file}")


def get_font(font_path=None, font_size=18):
    try:
        return ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
    except IOError:
        logger.warning(f"Font file {font_path} not found. Using default font.")
        return ImageFont.load_default()


def get_text_width(text, font):
    return font.getmask(text).getbbox()[2]


def wrap_text(text, max_width, font):
    words = text.split()
    lines = []
    current_line = []
    current_width = 0

    for word in words:
        word_width = get_text_width(word, font)
        if current_width + word_width <= max_width:
            current_line.append(word)
            current_width += word_width + get_text_width(" ", font)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                logger.debug(f"Wrapped line: {' '.join(current_line)}")
            current_line = [word]
            current_width = word_width

    if current_line:
        lines.append(" ".join(current_line))
        logger.debug(f"Wrapped line: {' '.join(current_line)}")

    return lines


def format_lyrics(lyrics_data, instrumentals, sync_times, font_path=None, font_size=18):
    formatted_lyrics = []
    font = get_font(font_path, font_size)
    logger.debug(f"Using font: {font}")

    current_line = ""
    lines_on_page = 0
    page_number = 1

    for i, text in enumerate(lyrics_data):
        logger.debug(f"Processing text {i}: '{text}' (sync time: {sync_times[i]})")

        if text.startswith("/"):
            if current_line:
                wrapped_lines = get_wrapped_text(current_line.strip(), font, CDG_VISIBLE_WIDTH).split("\n")
                for wrapped_line in wrapped_lines:
                    formatted_lyrics.append(wrapped_line)
                    lines_on_page += 1
                    logger.debug(f"Added wrapped line: '{wrapped_line}'. Lines on page: {lines_on_page}")
                    if lines_on_page == 4:
                        lines_on_page = 0
                        page_number += 1
                        logger.debug(f"Page full. New page number: {page_number}")
                current_line = ""
            text = text[1:]

        current_line += text + " "
        logger.debug(f"Current line: '{current_line}'")

        is_last_before_instrumental = any(
            inst["sync"] > sync_times[i] and (i == len(sync_times) - 1 or sync_times[i + 1] > inst["sync"]) for inst in instrumentals
        )

        if is_last_before_instrumental or i == len(lyrics_data) - 1:
            if current_line:
                wrapped_lines = get_wrapped_text(current_line.strip(), font, CDG_VISIBLE_WIDTH).split("\n")
                for wrapped_line in wrapped_lines:
                    formatted_lyrics.append(wrapped_line)
                    lines_on_page += 1
                    logger.debug(f"Added wrapped line at end of section: '{wrapped_line}'. Lines on page: {lines_on_page}")
                    if lines_on_page == 4:
                        lines_on_page = 0
                        page_number += 1
                        logger.debug(f"Page full. New page number: {page_number}")
                current_line = ""

            if is_last_before_instrumental:
                blank_lines_needed = 4 - lines_on_page
                if blank_lines_needed < 4:
                    formatted_lyrics.extend(["~"] * blank_lines_needed)
                    logger.debug(f"Added {blank_lines_needed} empty lines before instrumental. Lines on page was {lines_on_page}")
                lines_on_page = 0
                page_number += 1
                logger.debug(f"Reset lines_on_page to 0. New page number: {page_number}")

    final_lyrics = []
    for line in formatted_lyrics:
        final_lyrics.append(line)
        if line.endswith(("!", "?", ".")) and not line == "~":
            final_lyrics.append("~")
            logger.debug("Added empty line after punctuation")

    result = "\n".join(final_lyrics)
    logger.debug(f"Final formatted lyrics:\n{result}")
    return result


def generate_cdg(
    lrc_file,
    audio_file,
    title,
    artist,
    cdg_styles,
):
    """
    Generate a CDG file from an LRC file and audio file.

    Args:
        lrc_file (str): Path to the LRC file
        audio_file (str): Path to the audio file
        title (str): Title of the song
        artist (str): Artist of the song
        cdg_styles (dict): Dictionary containing all style and layout parameters
    """
    # Check if font_path is just a filename and look for it in the package's fonts directory
    if cdg_styles["font_path"] and not os.path.isabs(cdg_styles["font_path"]) and not os.path.exists(cdg_styles["font_path"]):
        package_font_path = os.path.join(os.path.dirname(__file__), "fonts", cdg_styles["font_path"])
        if os.path.exists(package_font_path):
            cdg_styles["font_path"] = package_font_path
            logger.debug(f"Found font in package fonts directory: {cdg_styles['font_path']}")
        else:
            logger.warning(f"Font file {cdg_styles['font_path']} not found in package fonts directory, will use default font")
            cdg_styles["font_path"] = None

    # Set up logging for this function if it hasn't been configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    toml_file = f"{Path(lrc_file).stem}.toml"

    generate_toml(
        lrc_file,
        audio_file,
        title,
        artist,
        toml_file,
        cdg_styles,
    )

    try:
        kc = KaraokeComposer.from_file(toml_file)
        kc.compose()
        logger.info("CDG file generated successfully")
    except Exception as e:
        logger.error(f"Error composing CDG: {e}")
        raise


def cli_main():
    """
    Command-line interface entry point for the lrc2cdg tool.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Convert LRC file to CDG")
    parser.add_argument("lrc_file", help="Path to the LRC file")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--title", required=True, help="Title of the song")
    parser.add_argument("--artist", required=True, help="Artist of the song")
    parser.add_argument("--style_params_json", required=True, help="Path to JSON file containing CDG style configuration")

    args = parser.parse_args()

    try:
        with open(args.style_params_json, "r") as f:
            style_params = json.loads(f.read())
            cdg_styles = style_params["cdg"]
    except FileNotFoundError:
        logger.error(f"Style configuration file not found: {args.style_params_json}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in style configuration file: {e}")
        sys.exit(1)

    try:
        generate_cdg(
            args.lrc_file,
            args.audio_file,
            args.title,
            args.artist,
            cdg_styles,
        )
    except ValueError as e:
        logger.error(f"Invalid style configuration: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli_main()
