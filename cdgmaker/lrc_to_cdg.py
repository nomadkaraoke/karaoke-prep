#!/usr/bin/env python3

import logging
import re
import toml
import argparse
from pathlib import Path
from cdgmaker.composer import KaraokeComposer
import sys
from PIL import ImageFont, Image
from cdgmaker.render import get_wrapped_text
import itertools

# Constants for TOML configuration
CLEAR_MODE = "eager"
BACKGROUND_COLOR = "#111427"
BORDER_COLOR = "#111427"
FONT_SIZE = 18
STROKE_WIDTH = 0
STROKE_STYLE = "octagon"
ACTIVE_FILL = "#7070F7"
ACTIVE_STROKE = "#000000"
INACTIVE_FILL = "#ff7acc"
INACTIVE_STROKE = "#000000"

CDG_VISIBLE_WIDTH = 280
TITLE_COLOR = "#ffffff"
ARTIST_COLOR = "#ffdf6b"

FONT = "/Users/andrew/AvenirNext-Bold.ttf"
TITLE_SCREEN_BACKGROUND = "/Users/andrew/cdg-title-screen-background-nomad-simple.png"

# Instead, create a logger specific to this module
logger = logging.getLogger(__name__)

# Add new constants for default values
DEFAULT_ROW = 4  # Increased from 1 to move text lower
DEFAULT_LINE_TILE_HEIGHT = 3
DEFAULT_LINES_PER_PAGE = 4

# Add new constants for instrumentals
INSTRUMENTAL_GAP_THRESHOLD = 1500  # 15 seconds in centiseconds
DEFAULT_INSTRUMENTAL_TEXT = "INSTRUMENTAL"

# Add these constants near the top of the file, with the other constants
INSTRUMENTAL_BACKGROUND = "/Users/andrew/cdg-instrumental-background-nomad-notes.png"
INSTRUMENTAL_TRANSITION = "cdginstrumentalwipepatternnomad"
INSTRUMENTAL_FONT_COLOR = "#ffdf6b"

# Add this constant near the top of the file with other constants
LEAD_IN_THRESHOLD = 300  # 3 seconds in centiseconds
LEAD_IN_OFFSET = 200  # 2 seconds in centiseconds

# Modify these constants near the top of the file
LEAD_IN_SYMBOLS = ["/>", ">", ">", ">"]
LEAD_IN_DURATION = 30  # 300 ms in centiseconds
LEAD_IN_TOTAL = 200  # 2 seconds in centiseconds


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


def detect_instrumentals(lyrics_data):
    instrumentals = []
    for i in range(len(lyrics_data) - 1):
        current_end = lyrics_data[i]["timestamp"]
        next_start = lyrics_data[i + 1]["timestamp"]
        gap = next_start - current_end
        if gap >= INSTRUMENTAL_GAP_THRESHOLD:
            instrumental_start = current_end + 200  # Add 2 seconds (200 centiseconds) delay
            instrumental_duration = (gap - 200) // 100  # Convert to seconds
            instrumentals.append(
                {
                    "sync": instrumental_start,
                    "wait": True,
                    "text": f"{DEFAULT_INSTRUMENTAL_TEXT}\n{instrumental_duration} seconds\n",
                    "text_align": "center",
                    "text_placement": "bottom middle",
                    "line_tile_height": DEFAULT_LINE_TILE_HEIGHT,
                    "fill": INSTRUMENTAL_FONT_COLOR,
                    "stroke": "",
                    "image": INSTRUMENTAL_BACKGROUND,
                    "transition": INSTRUMENTAL_TRANSITION,
                }
            )
            logger.info(
                f"Detected instrumental: Gap of {gap} cs, starting at {instrumental_start} cs, duration {instrumental_duration} seconds"
            )

    logger.info(f"Total instrumentals detected: {len(instrumentals)}")
    return instrumentals


def generate_toml(lrc_file, audio_file, title, artist, output_file, row, line_tile_height, lines_per_page, title_color, artist_color):
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

        if i == 0 or lyric["timestamp"] - lyrics_data[i - 1]["timestamp"] >= LEAD_IN_THRESHOLD:
            lead_in_start = lyric["timestamp"] - LEAD_IN_TOTAL
            logger.debug(f"Adding lead-in before lyric {i} at timestamp {lead_in_start}")
            for j, symbol in enumerate(LEAD_IN_SYMBOLS):
                sync_time = lead_in_start + j * LEAD_IN_DURATION
                sync_times.append(sync_time)
                formatted_lyrics.append(symbol)
                logger.debug(f"  Added lead-in symbol {j+1}: '{symbol}' at {sync_time}")

        sync_times.append(lyric["timestamp"])
        formatted_lyrics.append(lyric["text"])
        logger.debug(f"Added lyric: '{lyric['text']}' at {lyric['timestamp']}")

    instrumentals = detect_instrumentals(lyrics_data)
    formatted_lyrics = format_lyrics(formatted_lyrics, instrumentals, sync_times)

    toml_data = {
        "title": title,
        "artist": artist,
        "file": audio_file,
        "outname": Path(lrc_file).stem,
        "clear_mode": CLEAR_MODE,
        "sync_offset": 0,
        "background": BACKGROUND_COLOR,
        "border": BORDER_COLOR,
        "font": FONT,
        "font_size": FONT_SIZE,
        "stroke_width": STROKE_WIDTH,
        "stroke_style": STROKE_STYLE,
        "singers": [
            {"active_fill": ACTIVE_FILL, "active_stroke": ACTIVE_STROKE, "inactive_fill": INACTIVE_FILL, "inactive_stroke": INACTIVE_STROKE}
        ],
        "lyrics": [
            {
                "singer": 1,
                "sync": sync_times,
                "row": row,
                "line_tile_height": line_tile_height,
                "lines_per_page": lines_per_page,
                "text": formatted_lyrics,
            }
        ],
        "title_color": title_color,
        "artist_color": artist_color,
        "title_screen_background": TITLE_SCREEN_BACKGROUND,
        "instrumentals": instrumentals,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        toml.dump(toml_data, f)

    logger.info(f"TOML file generated: {output_file}")


def get_font():
    try:
        return ImageFont.truetype(FONT, FONT_SIZE)
    except IOError:
        logger.warning(f"Font file {FONT} not found. Using default font.")
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


def format_lyrics(lyrics_data, instrumentals, sync_times):
    formatted_lyrics = []
    font = get_font()
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
    row=DEFAULT_ROW,
    line_tile_height=DEFAULT_LINE_TILE_HEIGHT,
    lines_per_page=DEFAULT_LINES_PER_PAGE,
    title_color=TITLE_COLOR,
    artist_color=ARTIST_COLOR,
):
    """
    Generate a CDG file from an LRC file and audio file.

    This function can be called from other Python code to generate CDG files.
    """
    # Set up logging for this function if it hasn't been configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)  # Set to INFO by default, can be changed

    toml_file = f"{Path(lrc_file).stem}.toml"
    generate_toml(lrc_file, audio_file, title, artist, toml_file, row, line_tile_height, lines_per_page, title_color, artist_color)

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
    # Set up logging for CLI use
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    parser = argparse.ArgumentParser(description="Convert LRC file to CDG")
    parser.add_argument("lrc_file", help="Path to the LRC file")
    parser.add_argument("audio_file", help="Path to the audio file")
    parser.add_argument("--title", required=True, help="Title of the song")
    parser.add_argument("--artist", required=True, help="Artist of the song")
    parser.add_argument("--row", type=int, default=DEFAULT_ROW, help="Starting row for lyrics (0-17)")
    parser.add_argument("--line-tile-height", type=int, default=DEFAULT_LINE_TILE_HEIGHT, help="Height of each line in tile rows")
    parser.add_argument("--lines-per-page", type=int, default=DEFAULT_LINES_PER_PAGE, help="Number of lines per page")
    parser.add_argument("--title-color", default=TITLE_COLOR, help="Color of the title text on the intro screen")
    parser.add_argument("--artist-color", default=ARTIST_COLOR, help="Color of the artist text on the intro screen")

    args = parser.parse_args()

    generate_cdg(
        args.lrc_file,
        args.audio_file,
        args.title,
        args.artist,
        args.row,
        args.line_tile_height,
        args.lines_per_page,
        args.title_color,
        args.artist_color,
    )


if __name__ == "__main__":
    cli_main()
