import os
import json
import asyncio
import tempfile
from PIL import Image, ImageDraw, ImageFont
import pkg_resources
from karaoke_gen.core.track import Track
from karaoke_gen.core.exceptions import VideoError
import shutil
from datetime import datetime


class ScreenGenerator:
    """
    Handles title and end screen generation.
    """
    
    def __init__(self, config):
        """
        Initialize the screen generator.
        
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
        
        # Initialize temporary files list
        self._temp_files = []
        
        # Load style parameters
        self.style_params = self._load_style_params()
        
        # Set up title format from style params
        self.title_format = {
            "background_color": self.style_params["intro"]["background_color"],
            "background_image": self.style_params["intro"]["background_image"],
            "font": self.style_params["intro"]["font"],
            "artist_color": self.style_params["intro"]["artist_color"],
            "artist_gradient": self.style_params["intro"].get("artist_gradient"),
            "title_color": self.style_params["intro"]["title_color"],
            "title_gradient": self.style_params["intro"].get("title_gradient"),
            "extra_text": self.style_params["intro"]["extra_text"],
            "extra_text_color": self.style_params["intro"]["extra_text_color"],
            "extra_text_gradient": self.style_params["intro"].get("extra_text_gradient"),
            "extra_text_region": self.style_params["intro"]["extra_text_region"],
            "title_region": self.style_params["intro"]["title_region"],
            "artist_region": self.style_params["intro"]["artist_region"],
            "title_text_transform": self.style_params["intro"].get("title_text_transform"),
            "artist_text_transform": self.style_params["intro"].get("artist_text_transform"),
        }
        
        # Set up end format from style params
        self.end_format = {
            "background_color": self.style_params["end"]["background_color"],
            "background_image": self.style_params["end"]["background_image"],
            "font": self.style_params["end"]["font"],
            "artist_color": self.style_params["end"]["artist_color"],
            "artist_gradient": self.style_params["end"].get("artist_gradient"),
            "title_color": self.style_params["end"]["title_color"],
            "title_gradient": self.style_params["end"].get("title_gradient"),
            "extra_text": self.style_params["end"]["extra_text"],
            "extra_text_color": self.style_params["end"]["extra_text_color"],
            "extra_text_gradient": self.style_params["end"].get("extra_text_gradient"),
            "extra_text_region": self.style_params["end"]["extra_text_region"],
            "title_region": self.style_params["end"]["title_region"],
            "artist_region": self.style_params["end"]["artist_region"],
            "title_text_transform": self.style_params["end"].get("title_text_transform"),
            "artist_text_transform": self.style_params["end"].get("artist_text_transform"),
        }
        
        # Store video durations and existing images
        self.intro_video_duration = self.style_params["intro"]["video_duration"]
        self.end_video_duration = self.style_params["end"]["video_duration"]
        self.existing_title_image = self.style_params["intro"].get("existing_image")
        self.existing_end_image = self.style_params["end"].get("existing_image")
    
    def _load_style_params(self):
        """
        Load style parameters from JSON file or use defaults.
        
        Returns:
            The style parameters
        """
        # Load style parameters from JSON or use defaults
        if self.config.style_params_json:
            try:
                with open(self.config.style_params_json, "r") as f:
                    return json.loads(f.read())
            except FileNotFoundError:
                self.logger.error(f"Style parameters configuration file not found: {self.config.style_params_json}")
                raise VideoError(f"Style parameters configuration file not found: {self.config.style_params_json}")
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON in style parameters configuration file: {e}")
                raise VideoError(f"Invalid JSON in style parameters configuration file: {e}")
        else:
            # Use default values
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
                },
            }
    
    async def create_title_video(self, track):
        """
        Create a title video for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated title video information
        """
        self.logger.info(f"Creating title video for {track.base_name}")
        
        # Define output paths
        output_image_filepath_noext = os.path.join(track.track_output_dir, f"{track.base_name} (Title)")
        output_video_filepath = f"{output_image_filepath_noext}.mov"
        
        # Skip if output already exists
        if os.path.isfile(output_video_filepath):
            self.logger.info(f"Title video already exists: {output_video_filepath}")
            track.title_video = output_video_filepath
            return track
        
        # Apply text transformations
        artist_text = self._transform_text(track.artist, self.title_format["artist_text_transform"])
        title_text = self._transform_text(track.title, self.title_format["title_text_transform"])
        
        # Create video
        if not self.config.dry_run:
            try:
                await self._create_video(
                    extra_text=self.title_format["extra_text"],
                    title_text=title_text,
                    artist_text=artist_text,
                    format=self.title_format,
                    output_image_filepath_noext=output_image_filepath_noext,
                    output_video_filepath=output_video_filepath,
                    existing_image=self.existing_title_image,
                    duration=self.intro_video_duration,
                    render_bounding_boxes=self.config.render_bounding_boxes,
                    output_png=self.config.output_png,
                    output_jpg=self.config.output_jpg,
                )
                
                track.title_video = output_video_filepath
                self.logger.info(f"Successfully created title video: {output_video_filepath}")
                
            except Exception as e:
                raise VideoError(f"Failed to create title video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would create title video: {output_video_filepath}")
            track.title_video = output_video_filepath
        
        return track
    
    async def create_end_video(self, track):
        """
        Create an end video for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated end video information
        """
        self.logger.info(f"Creating end video for {track.base_name}")
        
        # Define output paths
        output_image_filepath_noext = os.path.join(track.track_output_dir, f"{track.base_name} (End)")
        output_video_filepath = f"{output_image_filepath_noext}.mov"
        
        # Skip if output already exists
        if os.path.isfile(output_video_filepath):
            self.logger.info(f"End video already exists: {output_video_filepath}")
            track.end_video = output_video_filepath
            return track
        
        # Apply text transformations
        artist_text = self._transform_text(track.artist, self.end_format["artist_text_transform"])
        title_text = self._transform_text(track.title, self.end_format["title_text_transform"])
        
        # Create video
        if not self.config.dry_run:
            try:
                await self._create_video(
                    extra_text=self.end_format["extra_text"],
                    title_text=title_text,
                    artist_text=artist_text,
                    format=self.end_format,
                    output_image_filepath_noext=output_image_filepath_noext,
                    output_video_filepath=output_video_filepath,
                    existing_image=self.existing_end_image,
                    duration=self.end_video_duration,
                    render_bounding_boxes=self.config.render_bounding_boxes,
                    output_png=self.config.output_png,
                    output_jpg=self.config.output_jpg,
                )
                
                track.end_video = output_video_filepath
                self.logger.info(f"Successfully created end video: {output_video_filepath}")
                
            except Exception as e:
                raise VideoError(f"Failed to create end video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would create end video: {output_video_filepath}")
            track.end_video = output_video_filepath
        
        return track
    
    async def _create_video(
        self,
        extra_text,
        title_text,
        artist_text,
        format,
        output_image_filepath_noext,
        output_video_filepath,
        existing_image=None,
        duration=5,
        render_bounding_boxes=False,
        output_png=True,
        output_jpg=True,
    ):
        """
        Create a video with text overlay.
        
        Args:
            extra_text: The extra text to display
            title_text: The title text to display
            artist_text: The artist text to display
            format: The format parameters
            output_image_filepath_noext: The output image filepath without extension
            output_video_filepath: The output video filepath
            existing_image: The existing image to use
            duration: The video duration in seconds
            render_bounding_boxes: Whether to render bounding boxes
            output_png: Whether to output PNG format
            output_jpg: Whether to output JPG format
            
        Returns:
            The output video filepath
        """
        # Handle existing image
        if existing_image and os.path.isfile(existing_image):
            return await self._handle_existing_image(
                existing_image, output_image_filepath_noext, output_video_filepath, duration
            )
        
        # Create background
        resolution = (3840, 2160)  # 4K resolution
        background = self._create_background(format, resolution)
        
        # Create draw object
        draw = ImageDraw.Draw(background)
        
        # Get font path
        font_path = self._get_font_path(format.get("font", "Montserrat-Bold.ttf"))
        
        # Render text
        self._render_all_text(draw, font_path, title_text, artist_text, format, render_bounding_boxes)
        
        # Save output files
        await self._save_output_files(
            background, output_image_filepath_noext, output_video_filepath, output_png, output_jpg, duration, resolution
        )
        
        return output_video_filepath
    
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
    
    def _create_background(self, format, resolution):
        """
        Create a background image.
        
        Args:
            format: The format parameters
            resolution: The resolution
            
        Returns:
            The background image
        """
        # Create background
        background = Image.new("RGB", resolution, self.hex_to_rgb(format["background_color"]))
        
        # Add background image if specified
        if format.get("background_image") and os.path.isfile(format["background_image"]):
            try:
                bg_image = Image.open(format["background_image"]).convert("RGBA")
                bg_image = bg_image.resize(resolution, Image.LANCZOS)
                background.paste(bg_image, (0, 0), bg_image)
            except Exception as e:
                self.logger.error(f"Failed to load background image: {str(e)}")
        
        return background
    
    def _render_all_text(self, draw, font_path, title_text, artist_text, format, render_bounding_boxes):
        """
        Render all text on the image.
        
        Args:
            draw: The ImageDraw object
            font_path: The font path
            title_text: The title text
            artist_text: The artist text
            format: The format parameters
            render_bounding_boxes: Whether to render bounding boxes
        """
        # Render title if region is specified
        if format.get("title_region") and title_text:
            title_region = self.parse_region(format["title_region"])
            self._render_text_in_region(
                draw,
                title_text,
                font_path,
                title_region,
                format["title_color"],
                format.get("title_gradient"),
            )
            if render_bounding_boxes:
                self._draw_bounding_box(draw, title_region, "#FF0000")
        
        # Render artist if region is specified
        if format.get("artist_region") and artist_text:
            artist_region = self.parse_region(format["artist_region"])
            self._render_text_in_region(
                draw,
                artist_text,
                font_path,
                artist_region,
                format["artist_color"],
                format.get("artist_gradient"),
            )
            if render_bounding_boxes:
                self._draw_bounding_box(draw, artist_region, "#00FF00")
        
        # Render extra text if specified
        if format.get("extra_text") and format.get("extra_text_region"):
            extra_text_region = self.parse_region(format["extra_text_region"])
            self._render_text_in_region(
                draw,
                format["extra_text"],
                font_path,
                extra_text_region,
                format["extra_text_color"],
                format.get("extra_text_gradient"),
            )
            if render_bounding_boxes:
                self._draw_bounding_box(draw, extra_text_region, "#0000FF")
    
    async def _save_output_files(
        self, background, output_image_filepath_noext, output_video_filepath, output_png, output_jpg, duration, resolution
    ):
        """
        Save output files.
        
        Args:
            background: The background image
            output_image_filepath_noext: The output image filepath without extension
            output_video_filepath: The output video filepath
            output_png: Whether to output PNG format
            output_jpg: Whether to output JPG format
            duration: The video duration in seconds
            resolution: The resolution
        """
        # Save PNG if requested
        if output_png:
            png_path = f"{output_image_filepath_noext}.png"
            background.save(png_path, "PNG")
            self.logger.debug(f"Saved PNG image: {png_path}")
        
        # Save JPG if requested
        if output_jpg:
            jpg_path = f"{output_image_filepath_noext}.jpg"
            background.save(jpg_path, "JPEG", quality=95)
            self.logger.debug(f"Saved JPG image: {jpg_path}")
        
        # Create video from image
        image_path = f"{output_image_filepath_noext}.jpg" if output_jpg else f"{output_image_filepath_noext}.png"
        await self._create_video_from_image(image_path, output_video_filepath, duration, resolution)
    
    async def _create_video_from_image(self, image_path, video_path, duration, resolution=(3840, 2160)):
        """
        Create a video from an image.
        
        Args:
            image_path: The image path
            video_path: The video path
            duration: The video duration in seconds
            resolution: The resolution
        """
        # Use the same ffmpeg command as the old implementation
        command = (
            f'{self.ffmpeg_base_command} -y -loop 1 -framerate 30 -i "{image_path}" '
            f'-f lavfi -i anullsrc -c:v libx264 -r 30 -t {duration} -pix_fmt yuv420p '
            f'-vf "scale={resolution[0]}:{resolution[1]}" -c:a aac -shortest "{video_path}"'
        )
        
        self.logger.debug(f"Creating video from image: {command}")
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            error_message = stderr.decode() if stderr else "Unknown error"
            raise VideoError(f"Failed to create video from image: {error_message}")
        
        self.logger.debug(f"Created video from image: {video_path}")
        
        # Verify the file was created successfully
        if not os.path.isfile(video_path):
            raise VideoError(f"Failed to create video file: {video_path}")
            
        return video_path
    
    async def _handle_existing_image(self, existing_image, output_image_filepath_noext, output_video_filepath, duration):
        """
        Handle an existing image.
        
        Args:
            existing_image: The existing image path
            output_image_filepath_noext: The output image filepath without extension
            output_video_filepath: The output video filepath
            duration: The video duration in seconds
            
        Returns:
            The output video filepath
        """
        self.logger.info(f"Using existing image: {existing_image}")
        
        # Copy existing image
        image = Image.open(existing_image)
        resolution = image.size
        
        # Save as JPG
        jpg_path = f"{output_image_filepath_noext}.jpg"
        image.save(jpg_path, "JPEG", quality=95)
        
        # Create video from image
        await self._create_video_from_image(jpg_path, output_video_filepath, duration, resolution)
        
        return output_video_filepath
    
    def _render_text_in_region(self, draw, text, font_path, region, color, gradient=None, font=None):
        """
        Render text in a region.
        
        Args:
            draw: The ImageDraw object
            text: The text to render
            font_path: The font path
            region: The region to render in
            color: The text color
            gradient: The gradient configuration
            font: The font object
        """
        if not text:
            return
        
        # Calculate font size to fit region
        if font is None:
            font_size = self.calculate_text_size_to_fit(draw, text, font_path, region)
            font = ImageFont.truetype(font_path, font_size)
        
        # Get text size using newer Pillow method
        left, top, right, bottom = font.getbbox(text)
        text_width = right - left
        text_height = bottom - top
        
        # Calculate position to center text in region
        x = region[0] + (region[2] - text_width) // 2
        y = region[1] + (region[3] - text_height) // 2
        
        # Render text with gradient if specified
        if gradient:
            self._render_text_with_gradient(draw, text, (x, y), font, gradient)
        else:
            # Render text with solid color
            draw.text((x, y), text, fill=self.hex_to_rgb(color), font=font)
    
    def _render_text_with_gradient(self, draw, text, position, font, gradient):
        """
        Render text with a gradient.
        
        Args:
            draw: The ImageDraw object
            text: The text to render
            position: The position to render at
            font: The font object
            gradient: The gradient configuration
        """
        # TODO: Implement gradient rendering
        # For now, just render with the first color
        draw.text(position, text, fill=self.hex_to_rgb(gradient["colors"][0]), font=font)
    
    def _draw_bounding_box(self, draw, region, color):
        """
        Draw a bounding box.
        
        Args:
            draw: The ImageDraw object
            region: The region to draw around
            color: The box color
        """
        draw.rectangle([region[0], region[1], region[0] + region[2], region[1] + region[3]], outline=self.hex_to_rgb(color), width=5)
    
    def calculate_text_size_to_fit(self, draw, text, font_path, region):
        """
        Calculate the font size to fit text in a region.
        
        Args:
            draw: The ImageDraw object
            text: The text to render
            font_path: The font path
            region: The region to fit in
            
        Returns:
            The font size
        """
        # Define a function to get text size using newer Pillow method
        def get_text_size(text, font):
            left, top, right, bottom = font.getbbox(text)
            return right - left, bottom - top
        
        # Binary search for the largest font size that fits
        min_size = 10
        max_size = 500
        target_width = region[2] * 0.9  # 90% of region width
        target_height = region[3] * 0.9  # 90% of region height
        
        while min_size <= max_size:
            mid_size = (min_size + max_size) // 2
            font = ImageFont.truetype(font_path, mid_size)
            text_width, text_height = get_text_size(text, font)
            
            if text_width <= target_width and text_height <= target_height:
                min_size = mid_size + 1
            else:
                max_size = mid_size - 1
        
        # Return the largest size that fits
        return max_size
    
    def _transform_text(self, text, transform_type):
        """
        Transform text based on the specified type.
        
        Args:
            text: The text to transform
            transform_type: The transformation type
            
        Returns:
            The transformed text
        """
        if not text:
            return text
        
        if transform_type == "uppercase":
            return text.upper()
        elif transform_type == "lowercase":
            return text.lower()
        elif transform_type == "propercase":
            return text.title()
        else:
            return text
    
    def parse_region(self, region_str):
        """
        Parse a region string.
        
        Args:
            region_str: The region string
            
        Returns:
            The parsed region as (x, y, width, height)
        """
        if region_str:
            try:
                parts = [int(p.strip()) for p in region_str.split(",")]
                if len(parts) == 4:
                    return tuple(parts)
            except ValueError:
                pass
        
        self.logger.warning(f"Invalid region format: {region_str}, using default")
        return (0, 0, 3840, 2160)
    
    def hex_to_rgb(self, hex_color):
        """
        Convert a hex color to RGB.
        
        Args:
            hex_color: The hex color
            
        Returns:
            The RGB color
        """
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    async def generate_title_screen(self, track):
        """
        Generate a title screen for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated title screen information
        """
        self.logger.info(f"Generating title screen for {track.base_name}")
        
        # Define output paths
        output_image_filepath_noext = os.path.join(track.track_output_dir, f"{track.base_name} (Title)")
        output_image_path = f"{output_image_filepath_noext}.png"
        output_jpg_path = f"{output_image_filepath_noext}.jpg"
        output_video_path = os.path.join(track.track_output_dir, f"{track.base_name} (Title).mov")
        
        # Skip if output already exists
        if os.path.isfile(output_video_path):
            self.logger.info(f"Title screen already exists: {output_video_path}")
            track.title_video = output_video_path
            return track
        
        # Generate title screen
        if not self.config.dry_run:
            try:
                # Check for existing image first
                if self.existing_title_image and os.path.isfile(self.existing_title_image):
                    # Handle existing image case
                    await self._handle_existing_image(
                        self.existing_title_image, 
                        output_image_filepath_noext, 
                        output_video_path, 
                        self.intro_video_duration
                    )
                else:
                    # Create background
                    resolution = (3840, 2160)  # 4K resolution
                    background = self._create_background(self.title_format, resolution)
                    
                    # Create draw object
                    draw = ImageDraw.Draw(background)
                    
                    # Get font path
                    font_path = self._get_font_path(self.title_format.get("font", "Montserrat-Bold.ttf"))
                    
                    # Apply text transformations
                    artist_text = self._transform_text(track.artist, self.title_format["artist_text_transform"])
                    title_text = self._transform_text(track.title, self.title_format["title_text_transform"])
                    
                    # Render all text
                    self._render_all_text(
                        draw, 
                        font_path, 
                        title_text, 
                        artist_text, 
                        self.title_format, 
                        self.config.render_bounding_boxes
                    )
                    
                    # Save images
                    if self.config.output_png:
                        background.save(output_image_path, "PNG")
                        self.logger.debug(f"Saved PNG image: {output_image_path}")
                    
                    if self.config.output_jpg:
                        background_rgb = background.convert("RGB")
                        background_rgb.save(output_jpg_path, "JPEG", quality=95)
                        self.logger.debug(f"Saved JPG image: {output_jpg_path}")
                    
                    # Create video from image
                    image_path = output_jpg_path if self.config.output_jpg else output_image_path
                    await self._create_video_from_image(
                        image_path, 
                        output_video_path, 
                        self.intro_video_duration,
                        resolution
                    )
                
                track.title_video = output_video_path
                self.logger.info(f"Successfully generated title screen: {output_video_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to generate title screen: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would generate title screen: {output_video_path}")
            track.title_video = output_video_path
        
        return track
    
    async def generate_end_screen(self, track):
        """
        Generate an end screen for a track.
        
        Args:
            track: The track to process
            
        Returns:
            The track with updated end screen information
        """
        self.logger.info(f"Generating end screen for {track.base_name}")
        
        # Define output paths
        output_image_filepath_noext = os.path.join(track.track_output_dir, f"{track.base_name} (End)")
        output_image_path = f"{output_image_filepath_noext}.png"
        output_jpg_path = f"{output_image_filepath_noext}.jpg"
        output_video_path = os.path.join(track.track_output_dir, f"{track.base_name} (End).mov")
        
        # Skip if output already exists
        if os.path.isfile(output_video_path):
            self.logger.info(f"End screen already exists: {output_video_path}")
            track.end_video = output_video_path
            return track
        
        # Generate end screen
        if not self.config.dry_run:
            try:
                # Check for existing image first
                if self.existing_end_image and os.path.isfile(self.existing_end_image):
                    # Handle existing image case
                    await self._handle_existing_image(
                        self.existing_end_image, 
                        output_image_filepath_noext, 
                        output_video_path, 
                        self.end_video_duration
                    )
                else:
                    # Create background
                    resolution = (3840, 2160)  # 4K resolution
                    background = self._create_background(self.end_format, resolution)
                    
                    # Create draw object
                    draw = ImageDraw.Draw(background)
                    
                    # Get font path
                    font_path = self._get_font_path(self.end_format.get("font", "Montserrat-Bold.ttf"))
                    
                    # Apply text transformations
                    artist_text = self._transform_text(track.artist, self.end_format["artist_text_transform"])
                    title_text = self._transform_text(track.title, self.end_format["title_text_transform"])
                    
                    # Render all text
                    self._render_all_text(
                        draw, 
                        font_path, 
                        title_text, 
                        artist_text, 
                        self.end_format, 
                        self.config.render_bounding_boxes
                    )
                    
                    # Save images
                    if self.config.output_png:
                        background.save(output_image_path, "PNG")
                        self.logger.debug(f"Saved PNG image: {output_image_path}")
                    
                    if self.config.output_jpg:
                        background_rgb = background.convert("RGB")
                        background_rgb.save(output_jpg_path, "JPEG", quality=95)
                        self.logger.debug(f"Saved JPG image: {output_jpg_path}")
                    
                    # Create video from image
                    image_path = output_jpg_path if self.config.output_jpg else output_image_path
                    await self._create_video_from_image(
                        image_path, 
                        output_video_path, 
                        self.end_video_duration,
                        resolution
                    )
                
                track.end_video = output_video_path
                self.logger.info(f"Successfully generated end screen: {output_video_path}")
                
            except Exception as e:
                self.logger.error(f"Failed to generate end screen: {str(e)}")
                # Continue with other processing
        else:
            self.logger.info(f"[DRY RUN] Would generate end screen: {output_video_path}")
            track.end_video = output_video_path
        
        return track
    
    async def _create_title_image(self, track, output_path):
        """
        Create a title image.
        
        Args:
            track: The track to process
            output_path: The output path for the image
            
        Returns:
            The output path
        """
        self.logger.info(f"Creating title image for {track.base_name}")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"Title image already exists: {output_path}")
            return output_path
        
        # Create image
        if not self.config.dry_run:
            try:
                # Get style parameters
                style = self.style_params.get("intro", {})
                
                # Create background
                resolution = (3840, 2160)  # 4K resolution
                background = self._create_background(self.title_format, resolution)
                
                # Create draw object
                draw = ImageDraw.Draw(background)
                
                # Get font path
                font_path = self._get_font_path(self.title_format.get("font", "Montserrat-Bold.ttf"))
                
                # Apply text transformations
                artist_text = self._transform_text(track.artist, self.title_format["artist_text_transform"])
                title_text = self._transform_text(track.title, self.title_format["title_text_transform"])
                
                # Render all text
                self._render_all_text(
                    draw, 
                    font_path, 
                    title_text, 
                    artist_text, 
                    self.title_format, 
                    self.config.render_bounding_boxes
                )
                
                # Save image directly to output path
                background.save(output_path)
                
                self.logger.info(f"Successfully created title image: {output_path}")
                
            except Exception as e:
                raise VideoError(f"Failed to create title image: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would create title image: {output_path}")
        
        return output_path

    async def _create_end_image(self, track, output_path):
        """
        Create an end image.
        
        Args:
            track: The track to process
            output_path: The output path for the image
            
        Returns:
            The output path
        """
        self.logger.info(f"Creating end image for {track.base_name}")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"End image already exists: {output_path}")
            return output_path
        
        # Create image
        if not self.config.dry_run:
            try:
                # Get style parameters
                style = self.style_params.get("end", {})
                
                # Create background
                resolution = (3840, 2160)  # 4K resolution
                background = self._create_background(self.end_format, resolution)
                
                # Create draw object
                draw = ImageDraw.Draw(background)
                
                # Get font path
                font_path = self._get_font_path(self.end_format.get("font", "Montserrat-Bold.ttf"))
                
                # Apply text transformations
                artist_text = self._transform_text(track.artist, self.end_format["artist_text_transform"])
                title_text = self._transform_text(track.title, self.end_format["title_text_transform"])
                
                # Render all text
                self._render_all_text(
                    draw, 
                    font_path, 
                    title_text, 
                    artist_text, 
                    self.end_format, 
                    self.config.render_bounding_boxes
                )
                
                # Save image directly to output path
                background.save(output_path)
                
                self.logger.info(f"Successfully created end image: {output_path}")
                
            except Exception as e:
                raise VideoError(f"Failed to create end image: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would create end image: {output_path}")
        
        return output_path
    
    async def _convert_image_to_video(self, image_path, output_path, duration=5.0, fade_in=1.0, fade_out=1.0):
        """
        Convert an image to a video with fade effects.
        
        Args:
            image_path: The input image path
            output_path: The output video path
            duration: The duration of the video in seconds
            fade_in: The fade-in duration in seconds
            fade_out: The fade-out duration in seconds
        """
        self.logger.info(f"Converting image to video: {image_path}")
        
        # Skip if output already exists
        if os.path.isfile(output_path):
            self.logger.info(f"Video already exists: {output_path}")
            return output_path
            
        # Verify image exists
        if not os.path.isfile(image_path):
            raise VideoError(f"Input image file does not exist: {image_path}")
        
        # Create video
        if not self.config.dry_run:
            try:
                # Build ffmpeg command, using more basic options for better compatibility
                command = (
                    f'{self.ffmpeg_base_command} -loop 1 -i "{image_path}" '
                    f'-c:v libx264 -preset fast -crf 23 -t {duration} -pix_fmt yuv420p '
                    f'-y "{output_path}"'
                )
                
                # Execute command
                self.logger.debug(f"Converting image to video: {command}")
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    error_message = stderr.decode() if stderr else "Unknown error"
                    raise VideoError(f"Failed to convert image to video: {error_message}")
                
                # Verify output file was created
                if not os.path.isfile(output_path):
                    raise VideoError(f"Output video file was not created: {output_path}")
                    
                self.logger.info(f"Successfully converted image to video: {output_path}")
                
            except Exception as e:
                raise VideoError(f"Failed to convert image to video: {str(e)}") from e
        else:
            self.logger.info(f"[DRY RUN] Would convert image to video: {output_path}")
        
        return output_path
    
    async def cleanup(self):
        """
        Perform cleanup operations for the screen generator.
        """
        self.logger.info("Cleaning up screen generator resources")
        
        # Clean up temporary files
        if hasattr(self, '_temp_files') and self._temp_files:
            for temp_file in self._temp_files:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                        self.logger.debug(f"Removed temporary file: {temp_file}")
                    except Exception as e:
                        self.logger.warning(f"Failed to remove temporary file {temp_file}: {str(e)}")
        
        # Reset temporary files list
        self._temp_files = []
        
        self.logger.info("Screen generator cleanup complete") 