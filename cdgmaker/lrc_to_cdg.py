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

# Keep only the truly constant values that aren't style-related
CDG_VISIBLE_WIDTH = 280

# Constants for lead-in behavior
LEAD_IN_THRESHOLD = 300  # 3 seconds in centiseconds
LEAD_IN_SYMBOLS = ["/>", ">", ">", ">"]
LEAD_IN_DURATION = 30  # 300 ms in centiseconds
LEAD_IN_TOTAL = 200  # 2 seconds in centiseconds

# Constants for instrumental detection
INSTRUMENTAL_GAP_THRESHOLD = 1500  # 15 seconds in centiseconds
DEFAULT_INSTRUMENTAL_TEXT = "INSTRUMENTAL"

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
    line_tile_height=3,
    instrumental_font_color="#ffdf6b",
    instrumental_background=None,
    instrumental_transition="cdginstrumentalwipepatternnomad",
):
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
    row=4,
    line_tile_height=3,
    lines_per_page=4,
    title_color="#ffffff",
    artist_color="#ffdf6b",
    background_color="#111427",
    border_color="#111427",
    font_path=None,
    font_size=18,
    stroke_width=0,
    stroke_style="octagon",
    active_fill="#7070F7",
    active_stroke="#000000",
    inactive_fill="#ff7acc",
    inactive_stroke="#000000",
    title_screen_background=None,
    instrumental_background=None,
    instrumental_transition="cdginstrumentalwipepatternnomad",
    instrumental_font_color="#ffdf6b",
):
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

    instrumentals = detect_instrumentals(
        lyrics_data,
        line_tile_height=line_tile_height,
        instrumental_font_color=instrumental_font_color,
        instrumental_background=instrumental_background,
        instrumental_transition=instrumental_transition,
    )

    formatted_lyrics = format_lyrics(formatted_lyrics, instrumentals, sync_times, font_path=font_path, font_size=font_size)

    toml_data = {
        "title": title,
        "artist": artist,
        "file": audio_file,
        "outname": Path(lrc_file).stem,
        "clear_mode": "eager",
        "sync_offset": 0,
        "background": background_color,
        "border": border_color,
        "font": font_path,
        "font_size": font_size,
        "stroke_width": stroke_width,
        "stroke_style": stroke_style,
        "singers": [
            {"active_fill": active_fill, "active_stroke": active_stroke, "inactive_fill": inactive_fill, "inactive_stroke": inactive_stroke}
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
        "title_screen_background": title_screen_background,
        "instrumentals": instrumentals,
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
    row=4,
    line_tile_height=3,
    lines_per_page=4,
    title_color="#ffffff",
    artist_color="#ffdf6b",
    background_color="#111427",
    border_color="#111427",
    font_path="/Users/andrew/AvenirNext-Bold.ttf",
    font_size=18,
    stroke_width=0,
    stroke_style="octagon",
    active_fill="#7070F7",
    active_stroke="#000000",
    inactive_fill="#ff7acc",
    inactive_stroke="#000000",
    title_screen_background="/Users/andrew/cdg-title-screen-background-nomad-simple.png",
    instrumental_background="/Users/andrew/cdg-instrumental-background-nomad-notes.png",
    instrumental_transition="cdginstrumentalwipepatternnomad",
    instrumental_font_color="#ffdf6b",
):
    """
    Generate a CDG file from an LRC file and audio file.
    All style parameters have default values but can be overridden.
    """
    # Set up logging for this function if it hasn't been configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    toml_file = f"{Path(lrc_file).stem}.toml"

    # Pass all style parameters to generate_toml
    generate_toml(
        lrc_file,
        audio_file,
        title,
        artist,
        toml_file,
        row=row,
        line_tile_height=line_tile_height,
        lines_per_page=lines_per_page,
        title_color=title_color,
        artist_color=artist_color,
        background_color=background_color,
        border_color=border_color,
        font_path=font_path,
        font_size=font_size,
        stroke_width=stroke_width,
        stroke_style=stroke_style,
        active_fill=active_fill,
        active_stroke=active_stroke,
        inactive_fill=inactive_fill,
        inactive_stroke=inactive_stroke,
        title_screen_background=title_screen_background,
        instrumental_background=instrumental_background,
        instrumental_transition=instrumental_transition,
        instrumental_font_color=instrumental_font_color,
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
    parser.add_argument("--row", type=int, default=4, help="Starting row for lyrics (0-17)")
    parser.add_argument("--line-tile-height", type=int, default=3, help="Height of each line in tile rows")
    parser.add_argument("--lines-per-page", type=int, default=4, help="Number of lines per page")
    parser.add_argument("--title-color", default="#ffffff", help="Color of the title text")
    parser.add_argument("--artist-color", default="#ffdf6b", help="Color of the artist text")
    # Add all the new style parameters as CLI arguments
    parser.add_argument("--background-color", default="#111427", help="Background color")
    parser.add_argument("--border-color", default="#111427", help="Border color")
    parser.add_argument("--font-path", help="Path to font file")
    parser.add_argument("--font-size", type=int, default=18, help="Font size")
    parser.add_argument("--active-fill", default="#7070F7", help="Active text fill color")
    parser.add_argument("--active-stroke", default="#000000", help="Active text stroke color")
    parser.add_argument("--inactive-fill", default="#ff7acc", help="Inactive text fill color")
    parser.add_argument("--inactive-stroke", default="#000000", help="Inactive text stroke color")
    parser.add_argument("--title-screen-background", help="Path to title screen background image")
    parser.add_argument("--instrumental-background", help="Path to instrumental background image")
    parser.add_argument("--instrumental-transition", default="cdginstrumentalwipepatternnomad", help="Instrumental transition effect")
    parser.add_argument("--instrumental-font-color", default="#ffdf6b", help="Instrumental text color")

    args = parser.parse_args()

    generate_cdg(
        args.lrc_file,
        args.audio_file,
        args.title,
        args.artist,
        row=args.row,
        line_tile_height=args.line_tile_height,
        lines_per_page=args.lines_per_page,
        title_color=args.title_color,
        artist_color=args.artist_color,
        background_color=args.background_color,
        border_color=args.border_color,
        font_path=args.font_path,
        font_size=args.font_size,
        active_fill=args.active_fill,
        active_stroke=args.active_stroke,
        inactive_fill=args.inactive_fill,
        inactive_stroke=args.inactive_stroke,
        title_screen_background=args.title_screen_background,
        instrumental_background=args.instrumental_background,
        instrumental_transition=args.instrumental_transition,
        instrumental_font_color=args.instrumental_font_color,
    )


if __name__ == "__main__":
    cli_main()
