import os
import asyncio
import tempfile
from PIL import Image, ImageDraw, ImageFont
import pkg_resources
from karaoke_gen.core.exceptions import VideoError


class TextRenderer:
    """
    Handles text rendering for videos.
    """
    
    def __init__(self, config):
        """
        Initialize the text renderer.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger
        
        # Path to ffmpeg
        self.ffmpeg_path = "ffmpeg"
        
        # Set up ffmpeg base command
        self.ffmpeg_base_command = f"{self.ffmpeg_path} -hide_banner -nostats"
        
        if self.config.log_level <= 10:  # DEBUG
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"
    
    async def render_lyrics(self, track, lyrics_file, output_file, font_name=None, font_size=None, 
                           font_color=None, outline_color=None, outline_width=None, 
                           position=None, alignment=None, background_color=None):
        """
        Render lyrics to a video file.
        
        Args:
            track: The track to process
            lyrics_file: The lyrics file to render
            output_file: The output file path
            font_name: The font name
            font_size: The font size
            font_color: The font color
            outline_color: The outline color
            outline_width: The outline width
            position: The position
            alignment: The alignment
            background_color: The background color
            
        Returns:
            The output file path
        """
        self.logger.info(f"Rendering lyrics for {track.base_name}")
        
        # Skip if output already exists
        if os.path.isfile(output_file):
            self.logger.info(f"Lyrics video already exists: {output_file}")
            return output_file
        
        # Check if lyrics file exists
        if not os.path.isfile(lyrics_file):
            self.logger.error(f"Lyrics file not found: {lyrics_file}")
            raise VideoError(f"Lyrics file not found: {lyrics_file}")
        
        # Set default values
        font_name = font_name or self.config.lyrics_font or "Arial"
        font_size = font_size or self.config.lyrics_font_size or 48
        font_color = font_color or self.config.lyrics_font_color or "white"
        outline_color = outline_color or self.config.lyrics_outline_color or "black"
        outline_width = outline_width or self.config.lyrics_outline_width or 2
        position = position or self.config.lyrics_position or "bottom"
        alignment = alignment or self.config.lyrics_alignment or "center"
        background_color = background_color or self.config.lyrics_background_color or "transparent"
        
        # Get font path
        font_path = self._get_font_path(font_name)
        
        # Create subtitles file
        subtitles_file = await self._create_subtitles_file(
            lyrics_file, 
            font_path, 
            font_size, 
            font_color, 
            outline_color, 
            outline_width, 
            position, 
            alignment, 
            background_color
        )
        
        # Create video with subtitles
        if not self.config.dry_run:
            try:
                # Create a black video if no input video is provided
                temp_video = await self._create_temp_black_video(track.duration)
                
                # Add subtitles to video
                await self._add_subtitles_to_video(temp_video, subtitles_file, output_file)
                
                # Clean up temporary files
                os.remove(temp_video)
                os.remove(subtitles_file)
                
                self.logger.info(f"Successfully rendered lyrics: {output_file}")
                
            except Exception as e:
                raise VideoError(f"Failed to render lyrics: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would render lyrics: {output_file}")
        
        return output_file
    
    async def render_text_overlay(self, input_video, output_video, text, font_name=None, font_size=None,
                                 font_color=None, outline_color=None, outline_width=None,
                                 position=None, alignment=None, background_color=None,
                                 start_time=None, end_time=None):
        """
        Render text overlay on a video.
        
        Args:
            input_video: The input video file
            output_video: The output video file
            text: The text to render
            font_name: The font name
            font_size: The font size
            font_color: The font color
            outline_color: The outline color
            outline_width: The outline width
            position: The position
            alignment: The alignment
            background_color: The background color
            start_time: The start time
            end_time: The end time
            
        Returns:
            The output video file
        """
        self.logger.info(f"Rendering text overlay on {input_video}")
        
        # Skip if output already exists
        if os.path.isfile(output_video):
            self.logger.info(f"Text overlay video already exists: {output_video}")
            return output_video
        
        # Check if input video exists
        if not os.path.isfile(input_video):
            self.logger.error(f"Input video not found: {input_video}")
            raise VideoError(f"Input video not found: {input_video}")
        
        # Set default values
        font_name = font_name or self.config.overlay_font or "Arial"
        font_size = font_size or self.config.overlay_font_size or 48
        font_color = font_color or self.config.overlay_font_color or "white"
        outline_color = outline_color or self.config.overlay_outline_color or "black"
        outline_width = outline_width or self.config.overlay_outline_width or 2
        position = position or self.config.overlay_position or "bottom"
        alignment = alignment or self.config.overlay_alignment or "center"
        background_color = background_color or self.config.overlay_background_color or "transparent"
        
        # Get font path
        font_path = self._get_font_path(font_name)
        
        # Create subtitles file with single entry
        subtitles_file = await self._create_simple_subtitles_file(
            text,
            start_time or 0,
            end_time or 999999,
            font_path,
            font_size,
            font_color,
            outline_color,
            outline_width,
            position,
            alignment,
            background_color
        )
        
        # Add subtitles to video
        if not self.config.dry_run:
            try:
                await self._add_subtitles_to_video(input_video, subtitles_file, output_video)
                
                # Clean up temporary files
                os.remove(subtitles_file)
                
                self.logger.info(f"Successfully rendered text overlay: {output_video}")
                
            except Exception as e:
                raise VideoError(f"Failed to render text overlay: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would render text overlay: {output_video}")
        
        return output_video
    
    def _get_font_path(self, font_name):
        """
        Get the path to a font file.
        
        Args:
            font_name: The font name
            
        Returns:
            The font path
        """
        # Check if font is a path
        if os.path.isfile(font_name):
            return font_name
        
        # Check in resources directory
        resources_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resources")
        font_path = os.path.join(resources_dir, font_name)
        if os.path.isfile(font_path):
            return font_path
        
        # Try to find font in package resources
        try:
            font_path = pkg_resources.resource_filename("karaoke_gen", f"resources/{font_name}")
            if os.path.isfile(font_path):
                return font_path
        except Exception:
            pass
        
        # Default to a system font
        self.logger.warning(f"Font not found: {font_name}, using default font")
        return font_name
    
    async def _create_subtitles_file(self, lyrics_file, font_path, font_size, font_color, 
                                    outline_color, outline_width, position, alignment, background_color):
        """
        Create a subtitles file from a lyrics file.
        
        Args:
            lyrics_file: The lyrics file
            font_path: The font path
            font_size: The font size
            font_color: The font color
            outline_color: The outline color
            outline_width: The outline width
            position: The position
            alignment: The alignment
            background_color: The background color
            
        Returns:
            The subtitles file path
        """
        # Create a temporary file for subtitles
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as temp_file:
            subtitles_file = temp_file.name
        
        # Parse LRC file and convert to ASS format
        with open(lyrics_file, "r", encoding="utf-8") as f:
            lrc_lines = f.readlines()
        
        # Write ASS header
        with open(subtitles_file, "w", encoding="utf-8") as f:
            f.write("[Script Info]\n")
            f.write("Title: Lyrics\n")
            f.write("ScriptType: v4.00+\n")
            f.write("WrapStyle: 0\n")
            f.write("ScaledBorderAndShadow: yes\n")
            f.write("YCbCr Matrix: None\n\n")
            
            f.write("[V4+ Styles]\n")
            f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            
            # Convert colors to ASS format
            primary_color = self._color_to_ass(font_color)
            outline_color_ass = self._color_to_ass(outline_color)
            background_color_ass = self._color_to_ass(background_color)
            
            # Set alignment based on position and alignment
            ass_alignment = self._get_ass_alignment(position, alignment)
            
            # Set margin based on position
            margin_v = 20 if position == "bottom" else (20 if position == "top" else 10)
            
            f.write(f"Style: Default,{os.path.basename(font_path)},{font_size},{primary_color},{primary_color},{outline_color_ass},{background_color_ass},0,0,0,0,100,100,0,0,1,{outline_width},0,{ass_alignment},10,10,{margin_v},1\n\n")
            
            f.write("[Events]\n")
            f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            
            # Parse LRC lines
            events = []
            for line in lrc_lines:
                line = line.strip()
                if line and "[" in line and "]" in line:
                    try:
                        time_tag = line[line.find("[") + 1:line.find("]")]
                        if ":" in time_tag and "." in time_tag:
                            minutes, rest = time_tag.split(":")
                            seconds, milliseconds = rest.split(".")
                            
                            start_time_seconds = int(minutes) * 60 + int(seconds) + int(milliseconds) / 100
                            text = line[line.find("]") + 1:].strip()
                            
                            if text:  # Only add non-empty lines
                                events.append((start_time_seconds, text))
                    except Exception as e:
                        self.logger.warning(f"Failed to parse LRC line: {line}, error: {str(e)}")
            
            # Sort events by start time
            events.sort(key=lambda x: x[0])
            
            # Write events with end times
            for i, (start_time, text) in enumerate(events):
                # Set end time to the start time of the next event, or 5 seconds after if it's the last event
                end_time = events[i + 1][0] if i < len(events) - 1 else start_time + 5
                
                # Format times as h:mm:ss.cc
                start_time_formatted = self._format_ass_time(start_time)
                end_time_formatted = self._format_ass_time(end_time)
                
                # Escape special characters
                text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
                
                f.write(f"Dialogue: 0,{start_time_formatted},{end_time_formatted},Default,,0,0,0,,{text}\n")
        
        return subtitles_file
    
    async def _create_simple_subtitles_file(self, text, start_time, end_time, font_path, font_size, 
                                          font_color, outline_color, outline_width, position, 
                                          alignment, background_color):
        """
        Create a simple subtitles file with a single entry.
        
        Args:
            text: The text
            start_time: The start time in seconds
            end_time: The end time in seconds
            font_path: The font path
            font_size: The font size
            font_color: The font color
            outline_color: The outline color
            outline_width: The outline width
            position: The position
            alignment: The alignment
            background_color: The background color
            
        Returns:
            The subtitles file path
        """
        # Create a temporary file for subtitles
        with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as temp_file:
            subtitles_file = temp_file.name
        
        # Write ASS header
        with open(subtitles_file, "w", encoding="utf-8") as f:
            f.write("[Script Info]\n")
            f.write("Title: Text Overlay\n")
            f.write("ScriptType: v4.00+\n")
            f.write("WrapStyle: 0\n")
            f.write("ScaledBorderAndShadow: yes\n")
            f.write("YCbCr Matrix: None\n\n")
            
            f.write("[V4+ Styles]\n")
            f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n")
            
            # Convert colors to ASS format
            primary_color = self._color_to_ass(font_color)
            outline_color_ass = self._color_to_ass(outline_color)
            background_color_ass = self._color_to_ass(background_color)
            
            # Set alignment based on position and alignment
            ass_alignment = self._get_ass_alignment(position, alignment)
            
            # Set margin based on position
            margin_v = 20 if position == "bottom" else (20 if position == "top" else 10)
            
            f.write(f"Style: Default,{os.path.basename(font_path)},{font_size},{primary_color},{primary_color},{outline_color_ass},{background_color_ass},0,0,0,0,100,100,0,0,1,{outline_width},0,{ass_alignment},10,10,{margin_v},1\n\n")
            
            f.write("[Events]\n")
            f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
            
            # Format times as h:mm:ss.cc
            start_time_formatted = self._format_ass_time(start_time)
            end_time_formatted = self._format_ass_time(end_time)
            
            # Escape special characters
            text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            
            f.write(f"Dialogue: 0,{start_time_formatted},{end_time_formatted},Default,,0,0,0,,{text}\n")
        
        return subtitles_file
    
    def _color_to_ass(self, color):
        """
        Convert a color to ASS format.
        
        Args:
            color: The color
            
        Returns:
            The ASS color
        """
        if color == "transparent":
            return "&H00FFFFFF"  # Transparent
        
        # Handle hex colors
        if color.startswith("#"):
            r = int(color[1:3], 16)
            g = int(color[3:5], 16)
            b = int(color[5:7], 16)
            return f"&H00{b:02X}{g:02X}{r:02X}"
        
        # Handle named colors
        color_map = {
            "white": "&H00FFFFFF",
            "black": "&H00000000",
            "red": "&H000000FF",
            "green": "&H0000FF00",
            "blue": "&H00FF0000",
            "yellow": "&H0000FFFF",
            "cyan": "&H00FFFF00",
            "magenta": "&H00FF00FF",
        }
        
        return color_map.get(color.lower(), "&H00FFFFFF")  # Default to white
    
    def _get_ass_alignment(self, position, alignment):
        """
        Get the ASS alignment value.
        
        Args:
            position: The position
            alignment: The alignment
            
        Returns:
            The ASS alignment value
        """
        # ASS alignment values:
        # 1: bottom left, 2: bottom center, 3: bottom right
        # 4: middle left, 5: middle center, 6: middle right
        # 7: top left, 8: top center, 9: top right
        
        if position == "bottom":
            if alignment == "left":
                return 1
            elif alignment == "right":
                return 3
            else:  # center
                return 2
        elif position == "middle":
            if alignment == "left":
                return 4
            elif alignment == "right":
                return 6
            else:  # center
                return 5
        elif position == "top":
            if alignment == "left":
                return 7
            elif alignment == "right":
                return 9
            else:  # center
                return 8
        else:
            return 2  # Default to bottom center
    
    def _format_ass_time(self, seconds):
        """
        Format seconds as h:mm:ss.cc for ASS format.
        
        Args:
            seconds: The time in seconds
            
        Returns:
            The formatted time
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds_remainder = seconds % 60
        centiseconds = int((seconds_remainder - int(seconds_remainder)) * 100)
        
        return f"{hours}:{minutes:02d}:{int(seconds_remainder):02d}.{centiseconds:02d}"
    
    async def _create_temp_black_video(self, duration):
        """
        Create a temporary black video.
        
        Args:
            duration: The duration in seconds
            
        Returns:
            The temporary video file path
        """
        # Create a temporary file for the video
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
            temp_video = temp_file.name
        
        # Create a black video
        command = (
            f'{self.ffmpeg_base_command} -f lavfi -i color=c=black:s=1920x1080:r=30 '
            f'-t {duration} -c:v libx264 -pix_fmt yuv420p "{temp_video}"'
        )
        
        self.logger.debug(f"Creating temporary black video: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to create temporary black video: {error_message}")
        
        return temp_video
    
    async def _add_subtitles_to_video(self, input_video, subtitles_file, output_video):
        """
        Add subtitles to a video.
        
        Args:
            input_video: The input video file
            subtitles_file: The subtitles file
            output_video: The output video file
            
        Returns:
            The output video file
        """
        # Add subtitles to video
        command = (
            f'{self.ffmpeg_base_command} -i "{input_video}" -vf '
            f'ass="{subtitles_file}" -c:v prores_ks -profile:v 3 -vendor ap10 '
            f'-bits_per_mb 8000 -pix_fmt yuv422p10le "{output_video}"'
        )
        
        self.logger.debug(f"Adding subtitles to video: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to add subtitles to video: {error_message}")
        
        return output_video 