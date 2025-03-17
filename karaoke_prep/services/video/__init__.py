from karaoke_prep.core.project import ProjectConfig
from karaoke_prep.core.track import Track
from karaoke_prep.core.exceptions import RenderingError

import logging
import os
import json
import importlib.resources as pkg_resources
from PIL import Image, ImageDraw, ImageFont
from typing import Dict, Any, Optional, Tuple, Union


class VideoService:
    """
    Service for video processing operations including rendering, text overlay, and video creation.
    """
    
    def __init__(self, config: ProjectConfig):
        """
        Initialize the video service.
        
        Args:
            config: The project configuration
        """
        self.config = config
        self.logger = config.logger or logging.getLogger(__name__)
        self.style_params = self._load_style_params()
        
        # Store existing images from style params
        self.existing_title_image = self.style_params["intro"].get("existing_image")
        self.existing_end_image = self.style_params["end"].get("existing_image")
        
        # Set up ffmpeg command
        ffmpeg_path = "ffmpeg"  # Assuming ffmpeg is in PATH
        self.ffmpeg_base_command = f"{ffmpeg_path} -hide_banner -nostats"
        if self.config.log_level == logging.DEBUG:
            self.ffmpeg_base_command += " -loglevel verbose"
        else:
            self.ffmpeg_base_command += " -loglevel fatal"
    
    def _load_style_params(self) -> Dict[str, Any]:
        """
        Load style parameters from JSON file.
        
        Returns:
            Dictionary of style parameters
        """
        if self.config.style_params_json and os.path.exists(self.config.style_params_json):
            try:
                with open(self.config.style_params_json, "r") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                self.logger.error(f"Error parsing style parameters JSON: {e}")
        
        # Default style parameters
        return {
            "intro": {
                "video_duration": 5,
                "existing_image": None,
                "background_color": "#000000",
                "background_image": None,
                "font": "Montserrat-Bold.ttf",
                "artist_color": "#ffdf6b",
                "artist_gradient": None,
                "title_color": "#ffffff",
                "title_gradient": None,
                "title_region": "370, 200, 3100, 480",
                "artist_region": "370, 700, 3100, 480",
                "extra_text": None,
                "extra_text_color": "#ffffff",
                "extra_text_gradient": None,
                "extra_text_region": "370, 1200, 3100, 480",
                "title_text_transform": None,  # none, uppercase, lowercase, propercase
                "artist_text_transform": None,  # none, uppercase, lowercase, propercase
            },
            "end": {
                "video_duration": 5,
                "existing_image": None,
                "background_color": "#000000",
                "background_image": None,
                "font": "Montserrat-Bold.ttf",
                "artist_color": "#ffdf6b",
                "artist_gradient": None,
                "title_color": "#ffffff",
                "title_gradient": None,
                "title_region": None,
                "artist_region": None,
                "extra_text": "THANK YOU FOR SINGING!",
                "extra_text_color": "#ff7acc",
                "extra_text_gradient": None,
                "extra_text_region": None,
                "title_text_transform": None,  # none, uppercase, lowercase, propercase
                "artist_text_transform": None,  # none, uppercase, lowercase, propercase
            }
        }
    
    async def create_videos(self, track: Track) -> Track:
        """
        Create videos for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated video information
        """
        # Skip video creation if we're in lyrics-only mode
        if os.environ.get("KARAOKE_PREP_SKIP_TITLE_END_SCREENS") == "1":
            self.logger.info("Skipping title/end screen generation due to lyrics-only mode")
            return track
        
        self.logger.info(f"Creating videos for {track.base_name}")
        
        # Create title video
        title_video = await self._create_title_video(track)
        track.title_video = title_video
        
        # Create end video
        end_video = await self._create_end_video(track)
        track.end_video = end_video
        
        return track
    
    async def _create_title_video(self, track: Track) -> str:
        """
        Create a title video for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The path to the title video
        """
        self.logger.info(f"Creating title video for {track.base_name}")
        
        # Get format settings from style params
        format = self.style_params["intro"]
        
        # Prepare output paths
        output_image_filepath_noext = os.path.join(track.track_output_dir, f"{track.base_name} (Title)")
        output_video_filepath = os.path.join(track.track_output_dir, f"{track.base_name} (Title).mov")
        
        # Skip if video already exists
        if os.path.exists(output_video_filepath):
            self.logger.info("Title video already exists, skipping creation")
            return output_video_filepath
        
        # Transform text based on settings
        title_text = self._transform_text(track.title, format.get("title_text_transform"))
        artist_text = self._transform_text(track.artist, format.get("artist_text_transform"))
        
        # Create video
        await self._create_video(
            title_text=title_text,
            artist_text=artist_text,
            extra_text=format.get("extra_text"),
            format=format,
            output_image_filepath_noext=output_image_filepath_noext,
            output_video_filepath=output_video_filepath,
            existing_image=format.get("existing_image"),
            duration=format["video_duration"],
        )
        
        return output_video_filepath
    
    async def _create_end_video(self, track: Track) -> str:
        """
        Create an end video for the track.
        
        Args:
            track: The track to process
            
        Returns:
            The path to the end video
        """
        self.logger.info(f"Creating end video for {track.base_name}")
        
        # Get format settings from style params
        format = self.style_params["end"]
        
        # Prepare output paths
        output_image_filepath_noext = os.path.join(track.track_output_dir, f"{track.base_name} (End)")
        output_video_filepath = os.path.join(track.track_output_dir, f"{track.base_name} (End).mov")
        
        # Skip if video already exists
        if os.path.exists(output_video_filepath):
            self.logger.info("End video already exists, skipping creation")
            return output_video_filepath
        
        # Transform text based on settings
        title_text = self._transform_text(track.title, format.get("title_text_transform"))
        artist_text = self._transform_text(track.artist, format.get("artist_text_transform"))
        
        # Create video
        await self._create_video(
            title_text=title_text,
            artist_text=artist_text,
            extra_text=format.get("extra_text"),
            format=format,
            output_image_filepath_noext=output_image_filepath_noext,
            output_video_filepath=output_video_filepath,
            existing_image=format.get("existing_image"),
            duration=format["video_duration"],
        )
        
        return output_video_filepath
    
    async def _create_video(
        self,
        title_text: str,
        artist_text: str,
        extra_text: Optional[str],
        format: Dict[str, Any],
        output_image_filepath_noext: str,
        output_video_filepath: str,
        existing_image: Optional[str] = None,
        duration: int = 5,
    ) -> None:
        """
        Create a video with title, artist, and optional extra text.
        
        Args:
            title_text: The title text to display
            artist_text: The artist text to display
            extra_text: Optional extra text to display
            format: The format settings
            output_image_filepath_noext: The output image filepath without extension
            output_video_filepath: The output video filepath
            existing_image: Optional path to an existing image to use
            duration: The duration of the video in seconds
        """
        self.logger.debug(f"Creating video with format: {format}")
        
        resolution = (3840, 2160)  # 4K resolution
        
        if existing_image:
            await self._handle_existing_image(existing_image, output_image_filepath_noext, output_video_filepath, duration)
            return
        
        # Create or load background
        background = self._create_background(format, resolution)
        draw = ImageDraw.Draw(background)
        
        # Load font
        font_path = self._get_font_path(format["font"])
        
        if font_path:
            self.logger.info(f"Using font: {font_path}")
            # Render all text elements
            await self._render_all_text(
                draw,
                font_path,
                title_text,
                artist_text,
                extra_text,
                format,
            )
        else:
            self.logger.info("No font specified or found, skipping text rendering")
        
        # Save output files
        await self._save_output_files(
            background,
            output_image_filepath_noext,
            output_video_filepath,
            duration,
            resolution,
        )
    
    def _get_font_path(self, font_name: str) -> Optional[str]:
        """
        Get the path to a font file.
        
        Args:
            font_name: The name of the font file
            
        Returns:
            The path to the font file, or None if not found
        """
        if not font_name:
            return None
        
        # Check if absolute path
        if os.path.isabs(font_name):
            if os.path.exists(font_name):
                return font_name
            self.logger.warning(f"Font file not found at {font_name}")
            return None
        
        # Try to load from package resources
        try:
            with pkg_resources.path("karaoke_prep.resources", font_name) as font_path:
                return str(font_path)
        except Exception as e:
            self.logger.warning(f"Could not load font from resources: {e}")
            return None
    
    def _create_background(self, format: Dict[str, Any], resolution: Tuple[int, int]) -> Image.Image:
        """
        Create or load the background image.
        
        Args:
            format: The format settings
            resolution: The desired resolution
            
        Returns:
            The background image
        """
        if format["background_image"] and os.path.exists(format["background_image"]):
            self.logger.info(f"Using background image file: {format['background_image']}")
            background = Image.open(format["background_image"])
        else:
            self.logger.info(f"Using background color: {format['background_color']}")
            background = Image.new("RGB", resolution, color=self._hex_to_rgb(format["background_color"]))
        
        return background.resize(resolution)
    
    async def _render_all_text(
        self,
        draw: ImageDraw.ImageDraw,
        font_path: str,
        title_text: str,
        artist_text: str,
        extra_text: Optional[str],
        format: Dict[str, Any],
    ) -> None:
        """
        Render all text elements on the image.
        
        Args:
            draw: The ImageDraw object
            font_path: The path to the font file
            title_text: The title text
            artist_text: The artist text
            extra_text: Optional extra text
            format: The format settings
        """
        # Render title
        if format["title_region"]:
            region = self._parse_region(format["title_region"])
            await self._render_text_in_region(
                draw,
                title_text,
                font_path,
                region,
                format["title_color"],
                gradient=format.get("title_gradient"),
            )
            if self.config.render_bounding_boxes:
                self._draw_bounding_box(draw, region, format["title_color"])
        
        # Render artist
        if format["artist_region"]:
            region = self._parse_region(format["artist_region"])
            await self._render_text_in_region(
                draw,
                artist_text,
                font_path,
                region,
                format["artist_color"],
                gradient=format.get("artist_gradient"),
            )
            if self.config.render_bounding_boxes:
                self._draw_bounding_box(draw, region, format["artist_color"])
        
        # Render extra text
        if extra_text and format["extra_text_region"]:
            region = self._parse_region(format["extra_text_region"])
            await self._render_text_in_region(
                draw,
                extra_text,
                font_path,
                region,
                format["extra_text_color"],
                gradient=format.get("extra_text_gradient"),
            )
            if self.config.render_bounding_boxes:
                self._draw_bounding_box(draw, region, format["extra_text_color"])
    
    async def _render_text_in_region(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font_path: str,
        region: Tuple[int, int, int, int],
        color: str,
        gradient: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Render text within a specified region.
        
        Args:
            draw: The ImageDraw object
            text: The text to render
            font_path: The path to the font file
            region: The region to render in (x, y, width, height)
            color: The text color
            gradient: Optional gradient configuration
        """
        if not text or not region:
            return
        
        # Calculate font size and layout
        font, text_lines = self._calculate_text_size_to_fit(draw, text, font_path, region)
        
        x, y, width, height = region
        
        # Get font metrics
        ascent, descent = font.getmetrics()
        font_height = ascent + descent
        
        if isinstance(text_lines, tuple):
            # Two lines
            line1, line2 = text_lines
            bbox1 = draw.textbbox((0, 0), line1, font=font)
            bbox2 = draw.textbbox((0, 0), line2, font=font)
            
            # Calculate line heights
            line1_height = bbox1[3] - bbox1[1]
            line2_height = bbox2[3] - bbox2[1]
            
            # Add gap between lines
            line_gap = int((line1_height + line2_height) * 0.1)
            total_height = line1_height + line_gap + line2_height
            
            # Center vertically
            y_start = y + (height - total_height) // 2
            
            # Draw lines
            await self._render_text_with_gradient(
                draw,
                line1,
                (x + (width - bbox1[2]) // 2, y_start),
                bbox1,
                font,
                color,
                gradient,
            )
            await self._render_text_with_gradient(
                draw,
                line2,
                (x + (width - bbox2[2]) // 2, y_start + line1_height + line_gap),
                bbox2,
                font,
                color,
                gradient,
            )
        else:
            # Single line
            bbox = draw.textbbox((0, 0), text_lines, font=font)
            y_pos = y + (height - font_height) // 2
            
            await self._render_text_with_gradient(
                draw,
                text_lines,
                (x + (width - bbox[2]) // 2, y_pos),
                bbox,
                font,
                color,
                gradient,
            )
    
    async def _render_text_with_gradient(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        position: Tuple[int, int],
        bbox: Tuple[int, int, int, int],
        font: ImageFont.FreeTypeFont,
        color: str,
        gradient: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Render text with optional gradient.
        
        Args:
            draw: The ImageDraw object
            text: The text to render
            position: The position to render at
            bbox: The text bounding box
            font: The font to use
            color: The text color
            gradient: Optional gradient configuration
        """
        position = (int(position[0]), int(position[1]))
        
        if not gradient:
            draw.text(position, text, fill=color, font=font)
            return
        
        # Create temporary image for text
        text_layer = Image.new("RGBA", (bbox[2], bbox[3]), (0, 0, 0, 0))
        text_draw = ImageDraw.Draw(text_layer)
        
        # Draw text in first color
        text_draw.text((0, 0), text, fill=gradient["color1"], font=font)
        
        # Create and apply gradient mask
        mask = self._create_gradient_mask((bbox[2], bbox[3]), gradient)
        
        # Create second color layer
        color2_layer = Image.new("RGBA", (bbox[2], bbox[3]), (0, 0, 0, 0))
        color2_draw = ImageDraw.Draw(color2_layer)
        color2_draw.text((0, 0), text, fill=gradient["color2"], font=font)
        
        # Composite using gradient mask
        text_layer.paste(color2_layer, mask=mask)
        
        # Paste onto main image
        draw._image.paste(text_layer, position, text_layer)
    
    def _create_gradient_mask(self, size: Tuple[int, int], gradient: Dict[str, Any]) -> Image.Image:
        """
        Create a gradient mask for text coloring.
        
        Args:
            size: The size of the mask (width, height)
            gradient: The gradient configuration
            
        Returns:
            The gradient mask image
        """
        mask = Image.new("L", size)
        draw = ImageDraw.Draw(mask)
        
        width, height = size
        start = gradient["start"]
        stop = gradient["stop"]
        
        if gradient["direction"] == "horizontal":
            for x in range(width):
                pos = x / width
                intensity = self._calculate_gradient_intensity(pos, start, stop)
                draw.line([(x, 0), (x, height)], fill=intensity)
        else:  # vertical
            for y in range(height):
                pos = y / height
                intensity = self._calculate_gradient_intensity(pos, start, stop)
                draw.line([(0, y), (width, y)], fill=intensity)
        
        return mask
    
    def _calculate_gradient_intensity(self, pos: float, start: float, stop: float) -> int:
        """
        Calculate gradient intensity at a position.
        
        Args:
            pos: Position in gradient (0-1)
            start: Start point of gradient
            stop: Stop point of gradient
            
        Returns:
            Intensity value (0-255)
        """
        if pos < start:
            return 0
        elif pos > stop:
            return 255
        else:
            return int(255 * (pos - start) / (stop - start))
    
    def _calculate_text_size_to_fit(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font_path: str,
        region: Tuple[int, int, int, int],
    ) -> Tuple[ImageFont.FreeTypeFont, Union[str, Tuple[str, str]]]:
        """
        Calculate font size to fit text in region.
        
        Args:
            draw: The ImageDraw object
            text: The text to fit
            font_path: The path to the font file
            region: The region to fit in
            
        Returns:
            Tuple of (font, text_lines)
        """
        font_size = 500  # Start with large font
        font = ImageFont.truetype(font_path, size=font_size)
        
        def get_text_size(text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int]:
            bbox = draw.textbbox((0, 0), text, font=font)
            return bbox[2], bbox[3] - bbox[1]
        
        text_width, text_height = get_text_size(text, font)
        target_height = region[3]
        
        while text_width > region[2] or text_height > target_height:
            font_size -= 10
            if font_size <= 150:
                # Split into two lines
                words = text.split()
                mid = len(words) // 2
                line1 = " ".join(words[:mid])
                line2 = " ".join(words[mid:])
                
                font_size = 500
                font = ImageFont.truetype(font_path, size=font_size)
                
                while True:
                    text_width1, text_height1 = get_text_size(line1, font)
                    text_width2, text_height2 = get_text_size(line2, font)
                    total_height = text_height1 + text_height2 + text_height1 * 0.1
                    
                    if max(text_width1, text_width2) <= region[2] and total_height <= target_height:
                        return font, (line1, line2)
                    
                    font_size -= 10
                    if font_size <= 0:
                        raise RenderingError("Cannot fit text within region")
                    font = ImageFont.truetype(font_path, size=font_size)
            
            font = ImageFont.truetype(font_path, size=font_size)
            text_width, text_height = get_text_size(text, font)
        
        return font, text
    
    async def _handle_existing_image(
        self,
        existing_image: str,
        output_image_filepath_noext: str,
        output_video_filepath: str,
        duration: int,
    ) -> None:
        """
        Handle case where an existing image is provided.
        
        Args:
            existing_image: Path to existing image
            output_image_filepath_noext: Output image path without extension
            output_video_filepath: Output video path
            duration: Video duration in seconds
        """
        self.logger.info(f"Using existing image file: {existing_image}")
        
        # Copy or convert to PNG
        if existing_image.lower().endswith(".png"):
            self.logger.info(f"Copying existing PNG image file")
            import shutil
            shutil.copy2(existing_image, output_image_filepath_noext + ".png")
        else:
            self.logger.info(f"Converting existing image to PNG")
            image = Image.open(existing_image)
            image.save(output_image_filepath_noext + ".png")
        
        # Convert to JPG if needed
        if not existing_image.lower().endswith(".jpg"):
            self.logger.info(f"Converting to JPG")
            image = Image.open(existing_image)
            if image.mode == "RGBA":
                image = image.convert("RGB")
            image.save(output_image_filepath_noext + ".jpg", quality=95)
        
        # Create video
        if duration > 0:
            await self._create_video_from_image(
                output_image_filepath_noext + ".png",
                output_video_filepath,
                duration,
            )
    
    async def _save_output_files(
        self,
        background: Image.Image,
        output_image_filepath_noext: str,
        output_video_filepath: str,
        duration: int,
        resolution: Tuple[int, int],
    ) -> None:
        """
        Save output image files and create video.
        
        Args:
            background: The background image
            output_image_filepath_noext: Output image path without extension
            output_video_filepath: Output video path
            duration: Video duration in seconds
            resolution: Video resolution
        """
        # Save PNG
        if self.config.output_png:
            background.save(f"{output_image_filepath_noext}.png")
        
        # Save JPG
        if self.config.output_jpg:
            background_rgb = background.convert("RGB")
            background_rgb.save(f"{output_image_filepath_noext}.jpg", quality=95)
        
        # Create video
        if duration > 0:
            await self._create_video_from_image(
                f"{output_image_filepath_noext}.png",
                output_video_filepath,
                duration,
                resolution,
            )
    
    async def _create_video_from_image(
        self,
        image_path: str,
        video_path: str,
        duration: int,
        resolution: Tuple[int, int] = (3840, 2160),
    ) -> None:
        """
        Create a video from a static image.
        
        Args:
            image_path: Path to input image
            video_path: Path to output video
            duration: Video duration in seconds
            resolution: Video resolution
        """
        ffmpeg_command = (
            f'{self.ffmpeg_base_command} -y -loop 1 -framerate 30 -i "{image_path}" '
            f"-f lavfi -i anullsrc -c:v libx264 -r 30 -t {duration} -pix_fmt yuv420p "
            f'-vf scale={resolution[0]}:{resolution[1]} -c:a aac -shortest "{video_path}"'
        )
        
        self.logger.info("Generating video...")
        self.logger.debug(f"Running command: {ffmpeg_command}")
        
        if not self.config.dry_run:
            os.system(ffmpeg_command)
    
    def _transform_text(self, text: str, transform_type: Optional[str]) -> str:
        """
        Transform text based on specified type.
        
        Args:
            text: The text to transform
            transform_type: The type of transformation
            
        Returns:
            The transformed text
        """
        if not transform_type:
            return text
        
        if transform_type == "uppercase":
            return text.upper()
        elif transform_type == "lowercase":
            return text.lower()
        elif transform_type == "propercase":
            return text.title()
        
        return text
    
    def _parse_region(self, region_str: Optional[str]) -> Optional[Tuple[int, int, int, int]]:
        """
        Parse region string into tuple.
        
        Args:
            region_str: Region string in format "x,y,width,height"
            
        Returns:
            Tuple of (x, y, width, height) or None
        """
        if not region_str:
            return None
        
        try:
            return tuple(map(int, region_str.split(",")))
        except ValueError:
            raise RenderingError(f"Invalid region format: {region_str}")
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """
        Convert hex color to RGB tuple.
        
        Args:
            hex_color: Hex color string
            
        Returns:
            RGB tuple
        """
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    def _draw_bounding_box(self, draw: ImageDraw.ImageDraw, region: Tuple[int, int, int, int], color: str) -> None:
        """
        Draw a bounding box around a region for debugging.
        
        Args:
            draw: The ImageDraw object
            region: The region to draw around (x, y, width, height)
            color: The color to draw in
        """
        if not region:
            return
        x, y, width, height = region
        draw.rectangle([x, y, x + width, y + height], outline=color, width=2)
