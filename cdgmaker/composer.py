from collections import deque
from io import BytesIO
import itertools as it
import operator
from pathlib import Path
import re
import sys
import tomllib
from typing import NamedTuple, Self, TYPE_CHECKING, cast, Iterable, TypeVar
from zipfile import ZipFile
if TYPE_CHECKING:
    from _typeshed import FileDescriptorOrPath, StrOrBytesPath

from attrs import define
from cattrs import Converter
from PIL import Image, ImageFont
from pydub import AudioSegment

from .cdg import *
from .config import *
from .pack import *
from .render import *
from .utils import *


import logging
logger = logging.getLogger(__name__)

package_dir = Path(__file__).parent

T = TypeVar('T')

def batched(iterable: Iterable[T], n: int) -> Iterable[tuple[T, ...]]:
    "Batch data into tuples of length n. The last batch may be shorter."
    # batched('ABCDEFG', 3) --> ABC DEF G
    itobj = iter(iterable)
    while True:
        batch = tuple(it.islice(itobj, n))
        if not batch:
            return
        yield batch

def file_relative_to(
        filepath: "StrOrBytesPath | Path",
        *relative_to: "StrOrBytesPath | Path",
) -> Path:
    """
    Convert possibly relative filepath to absolute path, relative to any
    of the paths in `relative_to`, or to the parent directory of this
    very Python file itself.

    If the filepath is already absolute, it is returned unchanged.
    Otherwise, the first absolute filepath found to exist as a file will
    be returned.

    Parameters
    ----------
    filepath : path-like
        Filepath.
    *relative_to
        The filepath will be given as relative to these paths.

    Returns
    -------
    `pathlib.Path`
        Absolute path relative to given directories, if any exist as
        files.
    """
    filepath = Path(filepath)
    if filepath.is_absolute():
        return filepath

    # If all else fails, check filepath relative to this file
    relative_to += (Path(__file__).parent,)
    for rel in relative_to:
        outpath = Path(rel) / filepath
        if outpath.is_file():
            return outpath

    # Add more detailed error information
    searched_paths = [str(Path(rel) / filepath) for rel in relative_to]
    raise FileNotFoundError(f"File not found: {filepath}. Searched in: {', '.join(searched_paths)}")


def sync_to_cdg(cs: int) -> int:
    """
    Convert sync time to CDG frame time to the nearest frame.

    Parameters
    ----------
    cs : int
        Time in centiseconds (100ths of a second).

    Returns
    -------
    int
        Equivalent time in CDG frames.
    """
    return cs * CDG_FPS // 100


@define
class SyllableInfo:
    mask: Image.Image
    text: str
    start_offset: int
    end_offset: int
    left_edge: int
    right_edge: int
    lyric_index: int
    line_index: int
    syllable_index: int


@define
class LineInfo:
    image: Image.Image
    text: str
    syllables: list[SyllableInfo]
    x: int
    y: int
    singer: int
    lyric_index: int
    line_index: int


class LyricInfo(NamedTuple):
    lines: list[LineInfo]
    line_tile_height: int
    lines_per_page: int
    lyric_index: int


@define
class LyricTimes:
    line_draw: list[int]
    line_erase: list[int]


@define
class LyricState:
    line_draw: int
    line_erase: int
    syllable_line: int
    syllable_index: int
    draw_queue: deque[CDGPacket]
    highlight_queue: deque[list[CDGPacket]]


@define
class ComposerState:
    instrumental: int
    this_page: int
    last_page: int
    just_cleared: bool


class KaraokeComposer:
    BACKGROUND = 0
    BORDER = 1
    UNUSED_COLOR = (0, 0, 0)

    #region Constructors
    # SECTION Constructors
    def __init__(
            self,
            config: Settings,
            relative_dir: "StrOrBytesPath | Path" = "",
    ):
        self.config = config
        self.relative_dir = Path(relative_dir)
        logger.debug("loading config settings")

        font_path = self.config.font
        logger.debug(f"font_path: {font_path}")
        try:
            # First, use the font path directly from the config
            if not Path(font_path).is_file():
                # Try to find the font relative to the config file
                font_path = Path(self.relative_dir) / font_path
                if not font_path.is_file():
                    # If not found, try to find it in the package fonts directory
                    font_path = package_dir / "fonts" / Path(self.config.font).name
                if not font_path.is_file():
                    raise FileNotFoundError(f"Font file not found: {self.config.font}")
            self.font = ImageFont.truetype(str(font_path), self.config.font_size)
        except Exception as e:
            logger.error(f"Error loading font: {e}")
            raise

        # Set color table for lyrics sections
        # NOTE At the moment, this only allows for up to 3 singers, with
        # distinct color indices for active/inactive fills/strokes.
        # REVIEW Could this be smarter? Perhaps if some colors are
        # reused/omitted, color indices could be organized in a
        # different way that allows for more singers at a time.
        self.color_table = [
            self.config.background,
            self.config.border or self.UNUSED_COLOR,
            self.UNUSED_COLOR,
            self.UNUSED_COLOR,
        ]
        for singer in self.config.singers:
            self.color_table.extend([
                singer.inactive_fill,
                singer.inactive_stroke,
                singer.active_fill,
                singer.active_stroke,
            ])
        self.color_table = list(pad(
            self.color_table, 16, padvalue=self.UNUSED_COLOR,
        ))
        logger.debug(f"Color table: {self.color_table}")

        self.max_tile_height = 0
        self.lyrics: list[LyricInfo] = []
        # Process lyric sets
        for ci, lyric in enumerate(self.config.lyrics):
            logger.debug(f"processing config lyric {ci}")
            lines: list[list[str]] = []
            line_singers: list[int] = []
            for textline in re.split(r"\n+", lyric.text):
                textline: str

                # Assign singer
                if "|" in textline:
                    singer, textline = textline.split("|")
                    singer = int(singer)
                else:
                    singer = lyric.singer

                textline = textline.strip()
                # Tildes signify empty lines
                if textline == "~":
                    syllables = []
                else:
                    syllables = [
                        # Replace underscores in syllables with spaces
                        syllable.replace("_", " ")
                        for syllable in it.chain.from_iterable(
                            # Split syllables at slashes
                            cast(str, word).split("/")
                            # Split words after one space and possibly
                            # before other spaces
                            for word in re.split(r"(?<= )(?<!  ) *", textline)
                        )
                    ]

                # logger.debug(f"singer {singer}: {syllables}")
                lines.append(syllables)
                line_singers.append(singer)

            logger.debug(f"rendering line images and masks for lyric {ci}")
            line_images, line_masks = render_lines_and_masks(
                lines,
                font=self.font,
                stroke_width=self.config.stroke_width,
                stroke_type=self.config.stroke_type,
            )
            max_height = 0
            for li, image in enumerate(line_images):
                if image.width > CDG_VISIBLE_WIDTH:
                    logger.warning(
                        f"line {li} too wide\n"
                        f"max width is {CDG_VISIBLE_WIDTH} pixel(s); "
                        f"actual width is {image.width} pixel(s)\n"
                        f"\t{''.join(lines[li])}"
                    )
                max_height = max(max_height, image.height)

            tile_height = ceildiv(max_height, CDG_TILE_HEIGHT)
            self.max_tile_height = max(self.max_tile_height, tile_height)

            lyric_lines: list[LineInfo] = []
            sync_i = 0
            logger.debug(f"setting sync points for lyric {ci}")
            for li, (line, singer, line_image, line_mask) in enumerate(zip(
                lines, line_singers, line_images, line_masks,
            )):
                # Center line horizontally
                x = (CDG_SCREEN_WIDTH - line_image.width) // 2
                # Place line on correct row
                y = lyric.row * CDG_TILE_HEIGHT + (
                    (li % lyric.lines_per_page)
                    * lyric.line_tile_height * CDG_TILE_HEIGHT
                )

                # Get enough sync points for this line's syllables
                line_sync = lyric.sync[sync_i:sync_i + len(line)]
                sync_i += len(line)
                if line_sync:
                    # The last syllable ends 0.45 seconds after it
                    # starts...
                    next_sync_point = line_sync[-1] + 45
                    if sync_i < len(lyric.sync):
                        # ...or when the first syllable of the next line
                        # starts, whichever comes first
                        next_sync_point = min(
                            next_sync_point,
                            lyric.sync[sync_i],
                        )
                    line_sync.append(next_sync_point)

                # Collect this line's syllables
                syllables: list[SyllableInfo] = []
                for si, (mask, syllable, (start, end)) in enumerate(zip(
                    line_mask,
                    line,
                    it.pairwise(line_sync),
                )):
                    # NOTE Left and right edges here are relative to the
                    # mask. They will be stored relative to the screen.
                    left_edge, right_edge = 0, 0
                    bbox = mask.getbbox()
                    if bbox is not None:
                        left_edge, _, right_edge, _ = bbox

                    syllables.append(SyllableInfo(
                        mask=mask,
                        text=syllable,
                        start_offset=sync_to_cdg(start),
                        end_offset=sync_to_cdg(end),
                        left_edge=left_edge + x,
                        right_edge=right_edge + x,
                        lyric_index=ci,
                        line_index=li,
                        syllable_index=si,
                    ))

                lyric_lines.append(LineInfo(
                    image=line_image,
                    text="".join(line),
                    syllables=syllables,
                    x=x,
                    y=y,
                    singer=singer,
                    lyric_index=ci,
                    line_index=li,
                ))

            self.lyrics.append(LyricInfo(
                lines=lyric_lines,
                line_tile_height=tile_height,
                lines_per_page=lyric.lines_per_page,
                lyric_index=ci,
            ))

        # Add vertical offset to lines to vertically center them
        max_height = max(
            line.image.height
            for lyric in self.lyrics
            for line in lyric.lines
        )
        line_offset = (
            self.max_tile_height * CDG_TILE_HEIGHT - max_height
        ) // 2
        logger.debug(
            f"lines will be vertically offset by {line_offset} pixel(s)"
        )
        if line_offset:
            for lyric in self.lyrics:
                for line in lyric.lines:
                    line.y += line_offset

        self.sync_offset = sync_to_cdg(self.config.sync_offset)

        self.writer = CDGWriter()
        logger.info("config settings loaded")

        self._set_draw_times()

    @classmethod
    def from_file(
            cls,
            file: "FileDescriptorOrPath",
    ) -> Self:
        converter = Converter(prefer_attrib_converters=True)
        relative_dir = Path(file).parent
        with open(file, "rb") as stream:
            return cls(
                converter.structure(tomllib.load(stream), Settings),
                relative_dir=relative_dir,
            )

    @classmethod
    def from_string(
            cls,
            config: str,
            relative_dir: "StrOrBytesPath | Path" = "",
    ) -> Self:
        converter = Converter(prefer_attrib_converters=True)
        return cls(
            converter.structure(tomllib.loads(config), Settings),
            relative_dir=relative_dir,
        )
    # !SECTION
    #endregion

    #region Set draw times
    # SECTION Set draw times
    # Gap between line draw/erase events = 1/6 second
    LINE_DRAW_ERASE_GAP = CDG_FPS // 6
    # TODO Make more values in these set-draw-times functions into named
    # constants

    def _set_draw_times(self):
        self.lyric_times: list[LyricTimes] = []
        for lyric in self.lyrics:
            logger.debug(f"setting draw times for lyric {lyric.lyric_index}")
            line_count = len(lyric.lines)
            line_draw: list[int] = [0] * line_count
            line_erase: list[int] = [0] * line_count

            # The first page is drawn 3 seconds before the first
            # syllable
            first_syllable = next(iter(
                syllable_info
                for line_info in lyric.lines
                for syllable_info in line_info.syllables
            ))
            draw_time = first_syllable.start_offset - 900
            for i in range(lyric.lines_per_page):
                if i < line_count:
                    line_draw[i] = draw_time
                    draw_time += self.LINE_DRAW_ERASE_GAP

            # For each pair of syllables
            for last_wipe, wipe in it.pairwise(
                syllable_info
                for line_info in lyric.lines
                for syllable_info in line_info.syllables
            ):
                # Skip if not on a line boundary
                if wipe.line_index <= last_wipe.line_index:
                    continue

                # Set draw times for lines
                match self.config.clear_mode:
                    case LyricClearMode.PAGE:
                        self._set_draw_times_page(
                            last_wipe, wipe,
                            lyric=lyric,
                            line_draw=line_draw,
                            line_erase=line_erase,
                        )
                    case LyricClearMode.LINE_EAGER:
                        self._set_draw_times_line_eager(
                            last_wipe, wipe,
                            lyric=lyric,
                            line_draw=line_draw,
                            line_erase=line_erase,
                        )
                    case LyricClearMode.LINE_DELAYED | _:
                        self._set_draw_times_line_delayed(
                            last_wipe, wipe,
                            lyric=lyric,
                            line_draw=line_draw,
                            line_erase=line_erase,
                        )

            # If clearing page by page
            if self.config.clear_mode == LyricClearMode.PAGE:
                # Don't actually erase any lines
                line_erase = []
            # If we're not clearing page by page
            else:
                end_line = wipe.line_index
                # Calculate the erase time of the last highlighted line
                erase_time = wipe.end_offset + 600
                line_erase[end_line] = erase_time
                erase_time += self.LINE_DRAW_ERASE_GAP

            logger.debug(
                f"lyric {lyric.lyric_index} draw times: {line_draw!r}"
            )
            logger.debug(
                f"lyric {lyric.lyric_index} erase times: {line_erase!r}"
            )
            self.lyric_times.append(LyricTimes(
                line_draw=line_draw,
                line_erase=line_erase,
            ))
        logger.info("draw times set")

    def _set_draw_times_page(
            self,
            last_wipe: SyllableInfo,
            wipe: SyllableInfo,
            lyric: LyricInfo,
            line_draw: list[int],
            line_erase: list[int],
    ):
        line_count = len(lyric.lines)
        last_page = last_wipe.line_index // lyric.lines_per_page
        this_page = wipe.line_index // lyric.lines_per_page

        # Skip if not on a page boundary
        if this_page <= last_page:
            return

        # This page starts at the later of:
        # - a few frames after the end of the last line
        # - 3 seconds before this line
        page_draw_time = max(
            last_wipe.end_offset + 12,
            wipe.start_offset - 900,
        )

        # Calculate the available time between the start of this line
        # and the desired page draw time
        available_time = wipe.start_offset - page_draw_time
        # Calculate the absolute minimum time from the last line to this
        # line
        # NOTE This is a sensible minimum, but not guaranteed.
        minimum_time = wipe.start_offset - last_wipe.start_offset - 24

        # Warn the user if there's not likely to be enough time
        if minimum_time < 32:
            logger.warning(
                "not enough bandwidth to clear screen on lyric "
                f"{wipe.lyric_index} line {wipe.line_index}"
            )

        # If there's not enough time between the end of the last line
        # and the start of this line, but there is enough time between
        # the start of the last line and the start of this page
        if available_time < 32:
            # Shorten the last wipe's duration to make room
            new_duration = wipe.start_offset - last_wipe.start_offset - 150
            if new_duration > 0:
                last_wipe.end_offset = last_wipe.start_offset + new_duration
                page_draw_time = last_wipe.end_offset + 12
            else:
                last_wipe.end_offset = last_wipe.start_offset
                page_draw_time = last_wipe.end_offset + 32

        # Set the draw times for lines on this page
        start_line = this_page * lyric.lines_per_page
        for i in range(start_line, start_line + lyric.lines_per_page):
            if i < line_count:
                line_draw[i] = page_draw_time
                page_draw_time += self.LINE_DRAW_ERASE_GAP

    def _set_draw_times_line_eager(
            self,
            last_wipe: SyllableInfo,
            wipe: SyllableInfo,
            lyric: LyricInfo,
            line_draw: list[int],
            line_erase: list[int],
    ):
        line_count = len(lyric.lines)
        last_page = last_wipe.line_index // lyric.lines_per_page
        this_page = wipe.line_index // lyric.lines_per_page

        # The last line should be erased near the start of this line
        erase_time = wipe.start_offset

        # If we're not on the next page
        if last_page >= this_page:
            # The last line is erased 1/3 seconds after the start of
            # this line
            erase_time += 100

            # Set draw and erase times for the last line
            for i in range(last_wipe.line_index, wipe.line_index):
                if i < line_count:
                    line_erase[i] = erase_time
                    erase_time += self.LINE_DRAW_ERASE_GAP
                j = i + lyric.lines_per_page
                if j < line_count:
                    line_draw[j] = erase_time
                    erase_time += self.LINE_DRAW_ERASE_GAP
            return
        # If we're here, we're on the next page

        last_wipe_end = last_wipe.end_offset
        inter_wipe_time = wipe.start_offset - last_wipe_end

        # The last line is erased at the earlier of:
        # - halfway between the pages
        # - 1.5 seconds after the last line
        erase_time = min(
            last_wipe_end + inter_wipe_time // 2,
            last_wipe_end + 450,
        )

        # If time between pages is less than 8 seconds
        if inter_wipe_time < 2400:
            # Set draw and erase times for the last line
            for i in range(last_wipe.line_index, wipe.line_index):
                if i < line_count:
                    line_erase[i] = erase_time
                    erase_time += self.LINE_DRAW_ERASE_GAP
                j = i + lyric.lines_per_page
                if j < line_count:
                    line_draw[j] = erase_time
                    erase_time += self.LINE_DRAW_ERASE_GAP
        # If time between pages is 8 seconds or longer
        else:
            # Set erase time for the last line
            for i in range(last_wipe.line_index, wipe.line_index):
                if i < line_count:
                    line_erase[i] = erase_time
                    erase_time += self.LINE_DRAW_ERASE_GAP

            # The new page will be drawn 3 seconds before the start of
            # this line
            draw_time = wipe.start_offset - 900
            start_line = wipe.line_index
            for i in range(start_line, start_line + lyric.lines_per_page):
                if i < line_count:
                    line_draw[i] = draw_time
                    draw_time += self.LINE_DRAW_ERASE_GAP

    def _set_draw_times_line_delayed(
            self,
            last_wipe: SyllableInfo,
            wipe: SyllableInfo,
            lyric: LyricInfo,
            line_draw: list[int],
            line_erase: list[int],
    ):
        line_count = len(lyric.lines)
        last_page = last_wipe.line_index // lyric.lines_per_page
        this_page = wipe.line_index // lyric.lines_per_page

        # If we're on the same page
        if last_page == this_page:
            # The last line will be erased at the earlier of:
            # - 1/3 seconds after the start of this line
            # - 1.5 seconds after the end of the last line
            erase_time = min(
                wipe.start_offset + 100,
                last_wipe.end_offset + 450,
            )

            # Set erase time for the last line
            for i in range(last_wipe.line_index, wipe.line_index):
                if i < line_count:
                    line_erase[i] = erase_time
                    erase_time += self.LINE_DRAW_ERASE_GAP
            return
        # If we're here, we're on the next page

        last_wipe_end = max(
            last_wipe.end_offset,
            last_wipe.start_offset + 100,
        )
        inter_wipe_time = wipe.start_offset - last_wipe_end

        last_line_start_offset = lyric.lines[
            last_wipe.line_index
        ].syllables[0].start_offset

        # The last line will be erased at the earlier of:
        # - 1/3 seconds after the start of this line
        # - 1.5 seconds after the end of the last line
        # - 1/3 of the way between the pages
        erase_time = min(
            wipe.start_offset + 100,
            last_wipe_end + 450,
            last_wipe_end + inter_wipe_time // 3,
        )
        # This line will be drawn at the latest of:
        # - 1/3 seconds after the start of the last line
        # - 3 seconds before the start of this line
        # - 1/3 of the way between the pages
        draw_time = max(
            last_line_start_offset + 100,
            wipe.start_offset - 900,
            last_wipe_end + inter_wipe_time // 3,
        )

        # If time between pages is 4 seconds or more, clear current page
        # lines before drawing new page lines
        if inter_wipe_time >= 1200:
            # Set erase times for lines on previous page
            for i in range(last_wipe.line_index, wipe.line_index):
                if i < line_count:
                    line_erase[i] = erase_time
                    erase_time += self.LINE_DRAW_ERASE_GAP

            draw_time = max(draw_time, erase_time)
            start_line = last_page * lyric.lines_per_page
            # Set draw times for lines on this page
            for i in range(start_line, start_line + lyric.lines_per_page):
                j = i + lyric.lines_per_page
                if j < line_count:
                    line_draw[j] = draw_time
                    draw_time += self.LINE_DRAW_ERASE_GAP
            return
        # If time between pages is less than 4 seconds, draw new page
        # lines before clearing current page lines

        # The first lines on the next page should be drawn 1/2 seconds
        # after the start of the last line
        draw_time = last_line_start_offset + 150

        # Set draw time for all lines on the next page before this line
        start_line = last_page * lyric.lines_per_page
        for i in range(start_line, last_wipe.line_index):
            j = i + lyric.lines_per_page
            if j < line_count:
                line_draw[j] = draw_time
                draw_time += self.LINE_DRAW_ERASE_GAP

        # The last lines on the next page should be drawn at least 1/3
        # of the way between the pages
        draw_time = max(
            draw_time,
            last_wipe_end + inter_wipe_time // 3,
        )
        # Set erase times for the rest of the lines on the previous page
        for i in range(last_wipe.line_index, wipe.line_index):
            if i < line_count:
                line_erase[i] = draw_time
                draw_time += self.LINE_DRAW_ERASE_GAP
        # Set draw times for the rest of the lines on this page
        for i in range(last_wipe.line_index, wipe.line_index):
            j = i + lyric.lines_per_page
            if j < line_count:
                line_draw[j] = draw_time
                draw_time += self.LINE_DRAW_ERASE_GAP
    # !SECTION
    #endregion

    #region Compose words
    # SECTION Compose words
    def compose(self):
        try:
            # NOTE Logistically, multiple simultaneous lyric sets doesn't
            # make sense if the lyrics are being cleared by page.
            if (
                self.config.clear_mode == LyricClearMode.PAGE
                and len(self.lyrics) > 1
            ):
                raise RuntimeError(
                    "page mode doesn't support more than one lyric set"
                )

            logger.debug("loading song file")
            song: AudioSegment = AudioSegment.from_file(
                file_relative_to(self.config.file, self.relative_dir)
            )
            logger.info("song file loaded")

            self.intro_delay = 0
            # Compose the intro
            # NOTE This also sets the intro delay for later.
            self._compose_intro()

            lyric_states: list[LyricState] = []
            for lyric in self.lyrics:
                lyric_states.append(LyricState(
                    line_draw=0,
                    line_erase=0,
                    syllable_line=0,
                    syllable_index=0,
                    draw_queue=deque(),
                    highlight_queue=deque(),
                ))

            composer_state = ComposerState(
                instrumental=0,
                this_page=0,
                last_page=0,
                just_cleared=False,
            )

            # XXX If there is an instrumental section immediately after the
            # intro, the screen should not be cleared. The way I'm detecting
            # this, however, is by (mostly) copy-pasting the code that
            # checks for instrumental sections. I shouldn't do it this way.
            current_time = (
                self.writer.packets_queued - self.sync_offset
                - self.intro_delay
            )
            should_instrumental = False
            instrumental = None
            if composer_state.instrumental < len(self.config.instrumentals):
                instrumental = self.config.instrumentals[
                    composer_state.instrumental
                ]
                instrumental_time = sync_to_cdg(instrumental.sync)
                # NOTE Normally, this part has code to handle waiting for a
                # lyric to finish. If there's an instrumental this early,
                # however, there shouldn't be any lyrics to finish.
                should_instrumental = current_time >= instrumental_time
            # If there should not be an instrumental section now
            if not should_instrumental:
                logger.debug("instrumental intro is not present; clearing")
                # Clear the screen
                self.writer.queue_packets([
                    *memory_preset_repeat(self.BACKGROUND),
                    *load_color_table(self.color_table),
                ])
                logger.debug(f"loaded color table in compose: {self.color_table}")
                if self.config.border is not None:
                    self.writer.queue_packet(border_preset(self.BORDER))
            else:
                logger.debug("instrumental intro is present; not clearing")

            # While there are lines to draw/erase, or syllables to
            # highlight, or events in the highlight/draw queues, or
            # instrumental sections to process
            while any(
                state.line_draw < len(times.line_draw)
                or state.line_erase < len(times.line_erase)
                or state.syllable_line < len(lyric.lines)
                or state.draw_queue
                or state.highlight_queue
                for lyric, times, state in zip(
                    self.lyrics,
                    self.lyric_times,
                    lyric_states,
                )
            ) or (
                composer_state.instrumental < len(self.config.instrumentals)
            ):
                for lyric, times, state in zip(
                    self.lyrics,
                    self.lyric_times,
                    lyric_states,
                ):
                    self._compose_lyric(
                        lyric=lyric,
                        times=times,
                        state=state,
                        lyric_states=lyric_states,
                        composer_state=composer_state,
                    )

            # Add audio padding to intro
            logger.debug("padding intro of audio file")
            intro_silence: AudioSegment = AudioSegment.silent(
                self.intro_delay * 1000 // CDG_FPS,
                frame_rate=song.frame_rate,
            )
            padded_song = intro_silence + song

            # NOTE If video padding is not added to the end of the song, the
            # outro (or next instrumental section) begins immediately after
            # the end of the last syllable, which would be abrupt.
            if self.config.clear_mode == LyricClearMode.PAGE:
                logger.debug(
                    "clear mode is page; adding padding before outro"
                )
                self.writer.queue_packets([no_instruction()] * 3 * CDG_FPS)

            # Calculate video padding before outro
            OUTRO_DURATION = 2400
            # This karaoke file ends at the later of:
            # - The end of the audio (with the padded intro)
            # - 8 seconds after the current video time
            end = max(
                int(padded_song.duration_seconds * CDG_FPS),
                self.writer.packets_queued + OUTRO_DURATION,
            )
            logger.debug(f"song should be {end} frame(s) long")
            padding_before_outro = (
                (end - OUTRO_DURATION) - self.writer.packets_queued
            )
            logger.debug(
                f"queueing {padding_before_outro} packets before outro"
            )
            self.writer.queue_packets([no_instruction()] * padding_before_outro)

            # Compose the outro (and thus, finish the video)
            self._compose_outro(end)
            logger.info("karaoke file composed")

            # Add audio padding to outro (and thus, finish the audio)
            logger.debug("padding outro of audio file")
            outro_silence: AudioSegment = AudioSegment.silent(
                (
                    (self.writer.packets_queued * 1000 // CDG_FPS)
                    - int(padded_song.duration_seconds * 1000)
                ),
                frame_rate=song.frame_rate,
            )
            padded_song += outro_silence

            # Write CDG and MP3 data to ZIP file
            outname = self.config.outname
            zipfile_name = self.relative_dir / Path(f"{outname}.zip")
            logger.debug(f"creating {zipfile_name}")
            with ZipFile(zipfile_name, "w") as zipfile:
                cdg_bytes = BytesIO()
                logger.debug("writing cdg packets to stream")
                self.writer.write_packets(cdg_bytes)
                logger.debug(
                    f"writing stream to zipfile as {outname}.cdg"
                )
                cdg_bytes.seek(0)
                zipfile.writestr(f"{outname}.cdg", cdg_bytes.read())

                mp3_bytes = BytesIO()
                logger.debug("writing mp3 data to stream")
                padded_song.export(mp3_bytes, format="mp3")
                logger.debug(
                    f"writing stream to zipfile as {outname}.mp3"
                )
                mp3_bytes.seek(0)
                zipfile.writestr(f"{outname}.mp3", mp3_bytes.read())
            logger.info(f"karaoke files written to {zipfile_name}")
        except Exception as e:
            logger.error(f"Error in compose: {str(e)}", exc_info=True)
            raise

    def _compose_lyric(
            self,
            lyric: LyricInfo,
            times: LyricTimes,
            state: LyricState,
            lyric_states: list[LyricState],
            composer_state: ComposerState,
    ):
        current_time = (
            self.writer.packets_queued - self.sync_offset
            - self.intro_delay
        )

        should_draw_this_line = False
        line_draw_info, line_draw_time = None, None
        if state.line_draw < len(times.line_draw):
            line_draw_info = lyric.lines[state.line_draw]
            line_draw_time = times.line_draw[state.line_draw]
            should_draw_this_line = current_time >= line_draw_time

        should_erase_this_line = False
        line_erase_info, line_erase_time = None, None
        if state.line_erase < len(times.line_erase):
            line_erase_info = lyric.lines[state.line_erase]
            line_erase_time = times.line_erase[state.line_erase]
            should_erase_this_line = current_time >= line_erase_time

        # If we're clearing lyrics by page and drawing a new line
        if (
            self.config.clear_mode == LyricClearMode.PAGE
            and should_draw_this_line
        ):
            composer_state.last_page = composer_state.this_page
            composer_state.this_page = (
                line_draw_info.line_index // lyric.lines_per_page
            )
            # If this line is the start of a new page
            if composer_state.this_page > composer_state.last_page:
                logger.debug(
                    f"going from page {composer_state.last_page} to "
                    f"page {composer_state.this_page} in page mode"
                )
                # If we have not just cleared the screen
                if not composer_state.just_cleared:
                    logger.debug("clearing screen on page transition")
                    # Clear the last page
                    page_clear_packets = [
                        *memory_preset_repeat(self.BACKGROUND),
                    ]
                    if self.config.border is not None:
                        page_clear_packets.append(border_preset(self.BORDER))
                    self.writer.queue_packets(page_clear_packets)
                    composer_state.just_cleared = True
                    # Update the current frame time
                    current_time += len(page_clear_packets)
                else:
                    logger.debug("not clearing screen on page transition")

        # Queue the erasing of this line if necessary
        if should_erase_this_line:
            assert line_erase_info is not None
            logger.debug(
                f"t={self.writer.packets_queued}: erasing lyric "
                f"{line_erase_info.lyric_index} line "
                f"{line_erase_info.line_index}"
            )
            if line_erase_info.text.strip():
                state.draw_queue.extend(line_image_to_packets(
                    line_erase_info.image,
                    xy=(line_erase_info.x, line_erase_info.y),
                    background=self.BACKGROUND,
                    erase=True,
                ))
            else:
                logger.debug("line is blank; not erased")
            state.line_erase += 1
        # Queue the drawing of this line if necessary
        if should_draw_this_line:
            assert line_draw_info is not None
            logger.debug(
                f"t={self.writer.packets_queued}: drawing lyric "
                f"{line_draw_info.lyric_index} line "
                f"{line_draw_info.line_index}"
            )
            if line_draw_info.text.strip():
                state.draw_queue.extend(line_image_to_packets(
                    line_draw_info.image,
                    xy=(line_draw_info.x, line_draw_info.y),
                    fill=line_draw_info.singer << 2 | 0,
                    stroke=line_draw_info.singer << 2 | 1,
                    background=self.BACKGROUND,
                ))
            else:
                logger.debug("line is blank; not drawn")
            state.line_draw += 1

        # NOTE If this line has no syllables, we must advance the
        # syllable line index until we reach a line that has syllables.
        while state.syllable_line < len(lyric.lines):
            if lyric.lines[state.syllable_line].syllables:
                break
            state.syllable_index = 0
            state.syllable_line += 1

        should_highlight = False
        syllable_info = None
        if state.syllable_line < len(lyric.lines):
            syllable_info = (
                lyric.lines[state.syllable_line]
                .syllables[state.syllable_index]
            )
            should_highlight = current_time >= syllable_info.start_offset
        # If this syllable should be highlighted now
        if should_highlight:
            assert syllable_info is not None
            if syllable_info.text.strip():
                # Add the highlight packets to the highlight queue
                state.highlight_queue.extend(self._compose_highlight(
                    lyric=lyric,
                    syllable=syllable_info,
                    current_time=current_time,
                ))

            # Advance to the next syllable
            state.syllable_index += 1
            if state.syllable_index >= len(
                lyric.lines[state.syllable_line].syllables
            ):
                state.syllable_index = 0
                state.syllable_line += 1

        should_instrumental = False
        instrumental = None
        if composer_state.instrumental < len(self.config.instrumentals):
            instrumental = self.config.instrumentals[
                composer_state.instrumental
            ]
            instrumental_time = sync_to_cdg(instrumental.sync)
            if instrumental.wait:
                syllable_iter = iter(
                    syll
                    for line_info in lyric.lines
                    for syll in line_info.syllables
                )
                last_syllable = next(syllable_iter)
                # Find first syllable on or after the instrumental time
                while last_syllable.start_offset < instrumental_time:
                    last_syllable = next(syllable_iter)
                first_syllable = lyric.lines[
                    last_syllable.line_index
                ].syllables[0]
                # If this line is being actively sung
                if current_time >= first_syllable.start_offset:
                    # If this is the last syllable in this line
                    if last_syllable.syllable_index == len(
                        lyric.lines[last_syllable.line_index].syllables
                    ) - 1:
                        instrumental_time = 0
                        if times.line_erase:
                            # Wait for this line to be erased
                            instrumental_time = times.line_erase[
                                last_syllable.line_index
                            ]
                        if not instrumental_time:
                            # Add 1.5 seconds
                            # XXX This is hardcoded.
                            instrumental_time = last_syllable.end_offset + 450
                    else:
                        logger.debug(
                            "forcing next instrumental not to wait; it "
                            "does not occur at or before the end of this "
                            "line"
                        )
                        instrumental.wait = False
            should_instrumental = current_time >= instrumental_time

        # If there should be an instrumental section now
        if should_instrumental:
            assert instrumental is not None
            logger.info("_compose_lyric: Time for an instrumental section")
            if instrumental.wait:
                logger.info("_compose_lyric: This instrumental section waited for the previous line to finish")
            else:
                logger.info("_compose_lyric: This instrumental did not wait for the previous line to finish")

            logger.debug("_compose_lyric: Purging all highlight/draw queues")
            for st in lyric_states:
                if instrumental.wait:
                    if st.highlight_queue:
                        logger.warning("_compose_lyric: Unexpected items in highlight queue when instrumental waited")
                    if st.draw_queue:
                        if st == state:
                            logger.debug("_compose_lyric: Queueing remaining draw packets for current state")
                        else:
                            logger.warning("_compose_lyric: Unexpected items in draw queue for non-current state")
                        self.writer.queue_packets(st.draw_queue)

                st.highlight_queue.clear()
                st.draw_queue.clear()

            logger.debug("_compose_lyric: Determining instrumental end time")
            if line_draw_time is not None:
                instrumental_end = line_draw_time
            else:
                instrumental_end = None
            logger.debug(f"_compose_lyric: instrumental_end={instrumental_end}")

            composer_state.instrumental += 1
            next_instrumental = None
            if composer_state.instrumental < len(self.config.instrumentals):
                next_instrumental = self.config.instrumentals[
                    composer_state.instrumental
                ]

            should_clear = True
            if next_instrumental is not None:
                next_instrumental_time = sync_to_cdg(next_instrumental.sync)
                logger.debug(f"_compose_lyric: next_instrumental_time={next_instrumental_time}")
                if instrumental_end is None or next_instrumental_time <= instrumental_end:
                    instrumental_end = next_instrumental_time
                    should_clear = False
            else:
                if line_draw_time is None:
                    should_clear = False

            logger.info(f"_compose_lyric: Composing instrumental. End time: {instrumental_end}, Should clear: {should_clear}")
            try:
                self._compose_instrumental(instrumental, instrumental_end)
            except Exception as e:
                logger.error(f"Error in _compose_instrumental: {str(e)}", exc_info=True)
                raise

            if should_clear:
                logger.debug("_compose_lyric: Clearing screen after instrumental")
                self.writer.queue_packets([
                    *memory_preset_repeat(self.BACKGROUND),
                    *load_color_table(self.color_table),
                ])
                logger.debug(f"_compose_lyric: Loaded color table: {self.color_table}")
                if self.config.border is not None:
                    self.writer.queue_packet(border_preset(self.BORDER))
                composer_state.just_cleared = True
            else:
                logger.debug("_compose_lyric: Not clearing screen after instrumental")
            return

        composer_state.just_cleared = False
        # Create groups of packets for highlights and draws, with None
        # as a placeholder value for non-highlight packets
        highlight_groups: list[list[CDGPacket | None]] = []
        for _ in range(self.config.highlight_bandwidth):
            group = []
            if state.highlight_queue:
                group = state.highlight_queue.popleft()
            highlight_groups.append(list(pad(group, self.max_tile_height)))
        # NOTE This means the draw groups will only contain None.
        draw_groups: list[list[CDGPacket | None]] = [
            [None] * self.max_tile_height
        ] * self.config.draw_bandwidth

        # Intersperse the highlight and draw groups and queue the
        # packets
        for group in intersperse(highlight_groups, draw_groups):
            for item in group:
                if item is not None:
                    self.writer.queue_packet(item)
                    continue

                # If a group item is None, try getting packets from the
                # draw queue
                if state.draw_queue:
                    self.writer.queue_packet(state.draw_queue.popleft())
                    continue
                self.writer.queue_packet(
                    next(iter(
                        st.draw_queue.popleft()
                        for st in lyric_states
                        if st.draw_queue
                    ), no_instruction())
                )

    def _compose_highlight(
            self,
            lyric: LyricInfo,
            syllable: SyllableInfo,
            current_time: int,
    ) -> list[list[CDGPacket]]:
        assert syllable is not None
        line_info = lyric.lines[syllable.line_index]
        x = line_info.x
        y = line_info.y

        # NOTE Using the current time instead of the ideal start offset
        # accounts for any lost frames from previous events that took
        # too long.
        start_offset = current_time
        end_offset = syllable.end_offset
        left_edge = syllable.left_edge
        right_edge = syllable.right_edge

        # Calculate the length of each column group in frames
        column_group_length = (
            (self.config.draw_bandwidth + self.config.highlight_bandwidth)
            * self.max_tile_height
        ) * len(self.lyrics)
        # Calculate the number of column updates for this highlight
        columns = (
            (end_offset - start_offset) // column_group_length
        ) * self.config.highlight_bandwidth

        left_tile = left_edge // CDG_TILE_WIDTH
        right_tile = ceildiv(right_edge, CDG_TILE_WIDTH) - 1
        # The highlight must hit at least the edges of all the tiles
        # along it (not including the one before the left edge or the
        # one after the right edge)
        highlight_progress = [
            tile_index * CDG_TILE_WIDTH
            for tile_index in range(left_tile + 1, right_tile + 1)
        ]
        # If there aren't too many tile boundaries for the number of
        # column updates
        if columns - 1 >= len(highlight_progress):
            # Add enough highlight points for all the column updates...
            highlight_progress += sorted(
                # ...which are evenly distributed within the range...
                map(operator.itemgetter(0), distribute(
                    range(1, columns), left_edge, right_edge,
                )),
                # ...prioritizing highlight points nearest to the middle
                # of a tile
                key=lambda n: abs(n % CDG_TILE_WIDTH - CDG_TILE_WIDTH // 2),
            )[:columns - 1 - len(highlight_progress)]
            # NOTE We need the length of this list to be the number of
            # columns minus 1, so that when the left and right edges are
            # included, there will be as many pairs as there are
            # columns.

            # Round and sort the highlight points
            highlight_progress = sorted(map(round, highlight_progress))
        # If there are too many tile boundaries for the number of column
        # updates
        else:
            # Prepare the syllable text representation
            syllable_text = ''.join(
                f"{{{syll.text}}}" if si == syllable.syllable_index else syll.text
                for si, syll in enumerate(lyric.lines[syllable.line_index].syllables)
            )
            
            # Warn the user
            logger.warning(
                "Not enough time to highlight lyric %d line %d syllable %d. "
                "Ideal duration is %d column(s); actual duration is %d column(s). "
                "Syllable text: %s",
                syllable.lyric_index, syllable.line_index, syllable.syllable_index,
                columns, len(highlight_progress) + 1,
                syllable_text
            )

        # Create the highlight packets
        return [
            line_mask_to_packets(syllable.mask, (x, y), edges)
            for edges in it.pairwise(
                [left_edge] + highlight_progress + [right_edge]
            )
        ]
    # !SECTION
    #endregion

    #region Compose pictures
    # SECTION Compose pictures
    def _compose_instrumental(
            self,
            instrumental: SettingsInstrumental,
            end: int | None,
    ):
        logger.info(f"Composing instrumental section. End time: {end}")
        try:
            self.writer.queue_packets([
                *memory_preset_repeat(0),
                # TODO Add option for borders in instrumentals
                border_preset(0),
            ])

            logger.debug("Rendering instrumental text")
            text = instrumental.text.split("\n")
            instrumental_font = ImageFont.truetype(self.config.font, 20)
            text_images = render_lines(
                text,
                font=instrumental_font,
                # NOTE If the instrumental shouldn't have a stroke, set the
                # stroke width to 0 instead.
                stroke_width=(
                    self.config.stroke_width
                    if instrumental.stroke is not None
                    else 0
                ),
                stroke_type=self.config.stroke_type,
            )
            text_width = max(image.width for image in text_images)
            line_height = instrumental.line_tile_height * CDG_TILE_HEIGHT
            text_height = line_height * len(text)
            max_height = max(image.height for image in text_images)

            # Set X position of "text box"
            match instrumental.text_placement:
                case (
                    TextPlacement.TOP_LEFT
                    | TextPlacement.MIDDLE_LEFT
                    | TextPlacement.BOTTOM_LEFT
                ):
                    text_x = CDG_TILE_WIDTH * 2
                case (
                    TextPlacement.TOP_MIDDLE
                    | TextPlacement.MIDDLE
                    | TextPlacement.BOTTOM_MIDDLE
                ):
                    text_x = (CDG_SCREEN_WIDTH - text_width) // 2
                case (
                    TextPlacement.TOP_RIGHT
                    | TextPlacement.MIDDLE_RIGHT
                    | TextPlacement.BOTTOM_RIGHT
                ):
                    text_x = CDG_SCREEN_WIDTH - CDG_TILE_WIDTH * 2 - text_width
            # Set Y position of "text box"
            match instrumental.text_placement:
                case (
                    TextPlacement.TOP_LEFT
                    | TextPlacement.TOP_MIDDLE
                    | TextPlacement.TOP_RIGHT
                ):
                    text_y = CDG_TILE_HEIGHT * 2
                case (
                    TextPlacement.MIDDLE_LEFT
                    | TextPlacement.MIDDLE
                    | TextPlacement.MIDDLE_RIGHT
                ):
                    text_y = (
                        (CDG_SCREEN_HEIGHT - text_height) // 2
                    ) // CDG_TILE_HEIGHT * CDG_TILE_HEIGHT
                    # Add offset to place text closer to middle of line
                    text_y += (line_height - max_height) // 2
                case (
                    TextPlacement.BOTTOM_LEFT
                    | TextPlacement.BOTTOM_MIDDLE
                    | TextPlacement.BOTTOM_RIGHT
                ):
                    text_y = CDG_SCREEN_HEIGHT - CDG_TILE_HEIGHT * 2 - text_height
                    # Add offset to place text closer to bottom of line
                    text_y += line_height - max_height

            # Create "screen" image for drawing text
            screen = Image.new("P", (CDG_SCREEN_WIDTH, CDG_SCREEN_HEIGHT), 0)
            # Create list of packets to draw text
            text_image_packets: list[CDGPacket] = []
            y = text_y
            for image in text_images:
                # Set alignment of text
                match instrumental.text_align:
                    case TextAlign.LEFT:
                        x = text_x
                    case TextAlign.CENTER:
                        x = text_x + (text_width - image.width) // 2
                    case TextAlign.RIGHT:
                        x = text_x + text_width - image.width
                # Draw text onto simulated screen
                screen.paste(
                    image.point(
                        lambda v: v and (2 if v == RENDERED_FILL else 3),
                        "P",
                    ),
                    (x, y),
                )
                # Render text into packets
                text_image_packets.extend(line_image_to_packets(
                    image,
                    xy=(x, y),
                    fill=2,
                    stroke=3,
                    background=self.BACKGROUND,
                ))
                y += instrumental.line_tile_height * CDG_TILE_HEIGHT

            if instrumental.image is not None:
                logger.debug("creating instrumental background image")
                try:
                    # Load background image
                    background_image = self._load_image(
                        instrumental.image,
                        [
                            instrumental.background or self.config.background,
                            self.UNUSED_COLOR,
                            instrumental.fill,
                            instrumental.stroke or self.UNUSED_COLOR,
                        ],
                    )
                except FileNotFoundError as e:
                    logger.error(f"Failed to load instrumental image: {e}")
                    # Fallback to simple screen if image can't be loaded
                    instrumental.image = None
                    logger.warning("Falling back to simple screen for instrumental")

            if instrumental.image is None:
                logger.debug("no instrumental image; drawing simple screen")
                color_table = list(pad(
                    [
                        instrumental.background or self.config.background,
                        self.UNUSED_COLOR,
                        instrumental.fill,
                        instrumental.stroke or self.UNUSED_COLOR,
                    ],
                    8,
                    padvalue=self.UNUSED_COLOR,
                ))
                # Set palette and draw text to screen
                self.writer.queue_packets([
                    load_color_table_lo(color_table),
                    *text_image_packets,
                ])
                logger.debug(f"loaded color table in compose_instrumental: {color_table}")
            else:
                # Queue palette packets
                palette = list(batched(background_image.getpalette(), 3))
                if len(palette) < 8:
                    color_table = list(pad(palette, 8, padvalue=self.UNUSED_COLOR))
                    logger.debug(f"loaded color table in compose_instrumental: {color_table}")
                    self.writer.queue_packet(load_color_table_lo(
                        color_table,
                    ))
                else:
                    color_table = list(pad(palette, 16, padvalue=self.UNUSED_COLOR))
                    logger.debug(f"loaded color table in compose_instrumental: {color_table}")
                    self.writer.queue_packets(load_color_table(
                        color_table,
                    ))

                logger.debug("drawing instrumental text")
                # Queue text packets
                self.writer.queue_packets(text_image_packets)

                logger.debug(
                    "rendering instrumental text over background image"
                )
                # HACK To properly draw and layer everything, I need to
                # create a version of the background image that has the text
                # overlaid onto it, and is tile-aligned. This requires some
                # juggling.
                padleft = instrumental.x % CDG_TILE_WIDTH
                padright = -(
                    instrumental.x + background_image.width
                ) % CDG_TILE_WIDTH
                padtop = instrumental.y % CDG_TILE_HEIGHT
                padbottom = -(
                    instrumental.y + background_image.height
                ) % CDG_TILE_HEIGHT
                logger.debug(
                    f"padding L={padleft} R={padright} T={padtop} B={padbottom}"
                )
                # Create axis-aligned background image with proper size and
                # palette
                aligned_background_image = Image.new(
                    "P",
                    (
                        background_image.width + padleft + padright,
                        background_image.height + padtop + padbottom,
                    ),
                    0,
                )
                aligned_background_image.putpalette(background_image.getpalette())
                # Paste background image onto axis-aligned image
                aligned_background_image.paste(background_image, (padleft, padtop))
                # Paste existing screen text onto axis-aligned image
                aligned_background_image.paste(
                    screen,
                    (padleft - instrumental.x, padtop - instrumental.y),
                    # NOTE This masks out the 0 pixels.
                    mask=screen.point(lambda v: v and 255, mode="1"),
                )

                # Render background image to packets
                packets = image_to_packets(
                    aligned_background_image,
                    (instrumental.x - padleft, instrumental.y - padtop),
                    background=screen.crop((
                        instrumental.x - padleft,
                        instrumental.y - padtop,
                        instrumental.x - padleft + aligned_background_image.width,
                        instrumental.y - padtop + aligned_background_image.height,
                    )),
                )
                logger.debug(
                    "instrumental background image packed in "
                    f"{len(list(it.chain(*packets.values())))} packet(s)"
                )

                logger.debug("applying instrumental transition")
                # Queue background image packets (and apply transition)
                if instrumental.transition is None:
                    for coord_packets in packets.values():
                        self.writer.queue_packets(coord_packets)
                else:
                    transition = Image.open(
                        package_dir / "transitions" / f"{instrumental.transition}.png"
                    )
                    for coord in self._gradient_to_tile_positions(transition):
                        self.writer.queue_packets(packets.get(coord, []))

            if end is None:
                logger.debug("this instrumental will last \"forever\"")
                return

            # Wait until 3 seconds before the next line should be drawn
            current_time = (
                self.writer.packets_queued - self.sync_offset
                - self.intro_delay
            )
            preparation_time = 3 * CDG_FPS  # 3 seconds * 300 frames per second = 900 frames
            end_time = max(current_time, end - preparation_time)
            wait_time = end_time - current_time
            
            logger.debug(f"waiting for {wait_time} frame(s) before showing next lyrics")
            self.writer.queue_packets(
                [no_instruction()] * wait_time
            )

            # Clear the screen for the next lyrics
            self.writer.queue_packets([
                *memory_preset_repeat(self.BACKGROUND),
                *load_color_table(self.color_table),
            ])
            logger.debug(f"loaded color table in compose_instrumental: {self.color_table}")
            if self.config.border is not None:
                self.writer.queue_packet(border_preset(self.BORDER))

            logger.debug("instrumental section ended")
        except Exception as e:
            logger.error(f"Error in _compose_instrumental: {str(e)}", exc_info=True)
            raise

    def _compose_intro(self):
        # TODO Make it so the intro screen is not hardcoded
        logger.debug("composing intro")
        self.writer.queue_packets([
            *memory_preset_repeat(0),
        ])

        logger.debug("loading intro background image")
        # Load background image
        background_image = self._load_image(
            self.config.title_screen_background,
            [
                (17, 20, 39),  # background
                (255, 170, 204),  # border
                self.config.title_color,   # title color
                self.config.artist_color,  # artist color
            ],
        )

        smallfont = ImageFont.truetype(self.config.font, 25)
        bigfont_size = 30
        MAX_HEIGHT = 200
        # Try rendering the title and artist to an image
        while True:
            logger.debug(f"trying song title at size {bigfont_size}")
            text_image = Image.new("P", (CDG_VISIBLE_WIDTH, MAX_HEIGHT * 2), 0)
            y = 0
            bigfont = ImageFont.truetype(self.config.font, bigfont_size)

            # Draw song title
            for image in render_lines(
                get_wrapped_text(
                    self.config.title,
                    font=bigfont,
                    width=text_image.width,
                ).split("\n"),
                font=bigfont,
            ):
                text_image.paste(
                    image.point(lambda v: v and 2, "P"),  # Use index 2 for title color
                    ((text_image.width - image.width) // 2, y),
                    mask=image.point(lambda v: v and 255, "1"),
                )
                y += int(bigfont.size)

            # Draw song artist
            for image in render_lines(
                get_wrapped_text(
                    self.config.artist,
                    font=smallfont,
                    width=text_image.width,
                ).split("\n"),
                font=smallfont,
            ):
                text_image.paste(
                    image.point(lambda v: v and 3, "P"),  # Use index 3 for artist color
                    ((text_image.width - image.width) // 2, y),
                    mask=image.point(lambda v: v and 255, "1"),
                )
                y += int(smallfont.size)

            # Break out of loop only if text box ends up small enough
            text_image = text_image.crop(text_image.getbbox())
            if text_image.height <= MAX_HEIGHT:
                logger.debug("height just right")
                break
            # If text box is not small enough, reduce font size of title
            logger.debug("height too big; reducing font size")
            bigfont_size -= 2

        # Draw text onto image
        background_image.paste(
            text_image,
            (
                (CDG_SCREEN_WIDTH - text_image.width) // 2,
                (CDG_SCREEN_HEIGHT - text_image.height) // 2,
            ),
            mask=text_image.point(lambda v: v and 255, "1"),
        )

        # Queue palette packets
        palette = list(batched(background_image.getpalette(), 3))
        if len(palette) < 8:
            color_table = list(pad(palette, 8, padvalue=self.UNUSED_COLOR))
            logger.debug(f"loaded color table in compose_intro: {color_table}")
            self.writer.queue_packet(load_color_table_lo(
                color_table,
            ))
        else:
            color_table = list(pad(palette, 16, padvalue=self.UNUSED_COLOR))
            logger.debug(f"loaded color table in compose_intro: {color_table}")
            self.writer.queue_packets(load_color_table(
                color_table,
            ))

        # Render background image to packets
        packets = image_to_packets(background_image, (0, 0))
        logger.debug(
            "intro background image packed in "
            f"{len(list(it.chain(*packets.values())))} packet(s)"
        )

        # Queue background image packets (and apply transition)
        transition = Image.open(
            package_dir / "transitions" / "cdgtitlescreenwipepatternnomad.png"
        )
        for coord in self._gradient_to_tile_positions(transition):
            self.writer.queue_packets(packets.get(coord, []))

        INTRO_DURATION = 5 * CDG_FPS  # 5 seconds * 300 frames per second = 1500 frames
        FIRST_SYLLABLE_BUFFER = 3 * CDG_FPS  # 3 seconds * 300 frames per second = 900 frames

        # Queue the intro screen for 5 seconds
        end_time = INTRO_DURATION
        self.writer.queue_packets(
            [no_instruction()] * (end_time - self.writer.packets_queued)
        )

        first_syllable_start_offset = min(
            syllable.start_offset
            for lyric in self.lyrics
            for line in lyric.lines
            for syllable in line.syllables
        )
        logger.debug(f"first syllable starts at {first_syllable_start_offset}")

        MINIMUM_FIRST_SYLLABLE_TIME_FOR_NO_SILENCE = INTRO_DURATION + FIRST_SYLLABLE_BUFFER
        # If the first syllable is within 8 seconds, add 5 seconds of silence
        # Otherwise, don't add any silence
        if first_syllable_start_offset < MINIMUM_FIRST_SYLLABLE_TIME_FOR_NO_SILENCE:
            self.intro_delay = MINIMUM_FIRST_SYLLABLE_TIME_FOR_NO_SILENCE
            logger.info(f"First syllable within 8 seconds. Adding {self.intro_delay} frames of silence.")
        else:
            self.intro_delay = 0
            logger.info("First syllable after 8 seconds. No additional silence needed.")

    def _compose_outro(self, end: int):
        # TODO Make it so the outro screen is not hardcoded
        logger.debug("composing outro")
        self.writer.queue_packets([
            *memory_preset_repeat(0),
        ])

        logger.debug("loading outro background image")
        # Load background image
        background_image = self._load_image(
            self.config.title_screen_background,
            [
                (17, 20, 39),  # background
                (255, 170, 204),  # border
                self.config.artist_color,  # "Thank you for singing" color
                self.config.title_color,   # "nomadkaraoke.com" color
            ],
        )

        smallfont = ImageFont.truetype(self.config.font, 25)
        MAX_HEIGHT = 200

        # Render text to an image
        logger.debug(f"rendering outro text")
        text_image = Image.new("P", (CDG_VISIBLE_WIDTH, MAX_HEIGHT * 2), 0)
        y = 0

        # Render "Thank you for singing" text
        for image in render_lines(
            get_wrapped_text(
                "THANK YOU FOR SINGING!",
                font=smallfont,
                width=text_image.width,
            ).split("\n"),
            font=smallfont,
        ):
            text_image.paste(
                image.point(lambda v: v and 2, "P"),  # Use index 2 for artist color
                ((text_image.width - image.width) // 2, y),
                mask=image.point(lambda v: v and 255, "1"),
            )
            y += int(smallfont.size)

        # Render "nomadkaraoke.com" text
        for image in render_lines(
            get_wrapped_text(
                "nomadkaraoke.com",
                font=smallfont,
                width=text_image.width,
            ).split("\n"),
            font=smallfont,
        ):
            text_image.paste(
                image.point(lambda v: v and 3, "P"),  # Use index 3 for title color
                ((text_image.width - image.width) // 2, y),
                mask=image.point(lambda v: v and 255, "1"),
            )
            y += int(smallfont.size)

        # Break out of loop only if text box ends up small enough
        text_image = text_image.crop(text_image.getbbox())
        assert text_image.height <= MAX_HEIGHT

        # Draw text onto image
        background_image.paste(
            text_image,
            (
                (CDG_SCREEN_WIDTH - text_image.width) // 2,
                (CDG_SCREEN_HEIGHT - text_image.height) // 2,
            ),
            mask=text_image.point(lambda v: v and 255, "1"),
        )

        # Queue palette packets
        palette = list(batched(background_image.getpalette(), 3))
        if len(palette) < 8:
            self.writer.queue_packet(load_color_table_lo(
                list(pad(palette, 8, padvalue=self.UNUSED_COLOR))
            ))
        else:
            self.writer.queue_packets(load_color_table(
                list(pad(palette, 16, padvalue=self.UNUSED_COLOR))
            ))

        # Render background image to packets
        packets = image_to_packets(background_image, (0, 0))
        logger.debug(
            "intro background image packed in "
            f"{len(list(it.chain(*packets.values())))} packet(s)"
        )

        # Queue background image packets (and apply transition)
        transition = Image.open(
            package_dir / "transitions" / "cdgtitlescreenwipepatternnomad.png"
        )
        for coord in self._gradient_to_tile_positions(transition):
            self.writer.queue_packets(packets.get(coord, []))

        self.writer.queue_packets(
            [no_instruction()] * (end - self.writer.packets_queued)
        )

    def _load_image(
            self,
            image_path: "StrOrBytesPath | Path",
            partial_palette: list[RGBColor] | None = None,
    ):
        if partial_palette is None:
            partial_palette = []

        logger.debug("loading image")
        image_rgba = Image.open(
            file_relative_to(image_path, self.relative_dir)
        ).convert("RGBA")
        image = image_rgba.convert("RGB")

        # REVIEW How many colors should I allow? Should I make this
        # configurable?
        COLORS = 16 - len(partial_palette)
        logger.debug(f"quantizing to {COLORS} color(s)")
        # Reduce colors with quantization and dithering
        image = image.quantize(
            colors=COLORS,
            palette=image.quantize(
                colors=COLORS,
                method=Image.Quantize.MAXCOVERAGE,
            ),
            dither=Image.Dither.FLOYDSTEINBERG,
        )
        # Further reduce colors to conform to 12-bit RGB palette
        image.putpalette([
            # HACK The RGB values of the colors that show up in CDG
            # players are repdigits in hexadecimal - 0x00, 0x11, 0x22,
            # 0x33, etc. This means that we can simply round each value
            # to the nearest multiple of 0x11 (17 in decimal).
            0x11 * round(v / 0x11)
            for v in image.getpalette()
        ])
        image = image.quantize()
        logger.debug(f"image uses {max(image.getdata()) + 1} color(s)")

        if partial_palette:
            logger.debug(
                f"prepending {len(partial_palette)} color(s) to palette"
            )
            # Add offset to color indices
            image.putdata(image.getdata(), offset=len(partial_palette))
            # Place other colors in palette
            image.putpalette(
                list(it.chain(*partial_palette)) + image.getpalette()
            )

        logger.debug(
            f"palette: {list(batched(image.getpalette(), 3))!r}"
        )

        logger.debug("masking out non-transparent parts of image")
        # Create mask for non-transparent parts of image
        # NOTE We allow alpha values from 128 to 255 (half-transparent
        # to opaque).
        mask = Image.new("1", image_rgba.size, 0)
        mask.putdata([
            0 if pixel >= 128 else 255
            for pixel in image_rgba.getdata(band=3)
        ])
        # Set transparent parts of background to 0
        image.paste(Image.new("P", image.size, 0), mask=mask)

        return image

    def _gradient_to_tile_positions(
            self,
            image: Image.Image,
    ) -> list[tuple[int, int]]:
        """
        Convert an image of a gradient to an ordering of tile positions.

        The closer a section of the image is to white, the earlier it
        will appear. The closer a section of the image is to black, the
        later it will appear. The image is converted to `L` mode before
        processing.

        Parameters
        ----------
        image : `PIL.Image.Image`
            Image to convert.

        Returns
        -------
        list of tuple of (int, int)
            Tile positions in order.
        """
        image = image.convert("L")
        intensities: dict[tuple[int, int], int] = {}
        for tile_y, tile_x in it.product(
            range(CDG_SCREEN_HEIGHT // CDG_TILE_HEIGHT),
            range(CDG_SCREEN_WIDTH // CDG_TILE_WIDTH),
        ):
            # NOTE The intensity is negative so that, when it's sorted,
            # it will be sorted from highest intensity to lowest. This
            # is not done with reverse=True to preserve the sort's
            # stability.
            intensities[(tile_y, tile_x)] = -sum(
                image.getpixel((
                    tile_x * CDG_TILE_WIDTH + x,
                    tile_y * CDG_TILE_HEIGHT + y,
                ))
                for x in range(CDG_TILE_WIDTH)
                for y in range(CDG_TILE_HEIGHT)
            )
        return sorted(intensities, key=intensities.get)
    # !SECTION
    #endregion

def main():
    # TODO Make the logging level configurable from the command line
    logging.basicConfig(level=logging.DEBUG)

    kc = KaraokeComposer.from_file(sys.argv[1])
    kc.compose()

if __name__ == "__main__":
    main()
