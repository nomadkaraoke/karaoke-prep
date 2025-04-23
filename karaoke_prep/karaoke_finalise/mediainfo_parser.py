import os
import logging
import subprocess
import json
import xml.etree.ElementTree as ET


class MediaInfoParser:
    """
    Parser for mediainfo output to extract video/audio properties.
    Supports both JSON and XML output formats from mediainfo command.
    """
    
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)
    
    def get_mediainfo_xml(self, file_path):
        """
        Get mediainfo output in XML format for a given file.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            String containing XML output from mediainfo
            
        Raises:
            RuntimeError: If mediainfo command fails
        """
        try:
            result = subprocess.run(
                ["mediainfo", "--Output=XML", file_path],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except FileNotFoundError as e:
            if "mediainfo" in str(e):
                raise RuntimeError("MediaInfo not found. Please install MediaInfo.") from e
            raise
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"MediaInfo command failed with return code {e.returncode}: {e.stderr}") from e
    
    def get_mediainfo_json(self, file_path):
        """
        Get mediainfo output in JSON format for a given file.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            Dictionary containing parsed JSON output from mediainfo
            
        Raises:
            RuntimeError: If mediainfo command fails
        """
        try:
            result = subprocess.run(
                ["mediainfo", "--Output=JSON", file_path],
                capture_output=True,
                text=True,
                check=True
            )
            return json.loads(result.stdout)
        except FileNotFoundError as e:
            if "mediainfo" in str(e):
                raise RuntimeError("MediaInfo not found. Please install MediaInfo.") from e
            raise
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"MediaInfo command failed with return code {e.returncode}: {e.stderr}") from e
        
    def get_video_duration(self, file_path):
        """
        Get the duration of a video file in seconds.
        
        Args:
            file_path: Path to the video file
            
        Returns:
            Duration in seconds (float)
            
        Raises:
            ValueError: If duration information can't be found
        """
        try:
            # Try to get duration from JSON output first
            mediainfo = self.get_mediainfo_json(file_path)
            
            # Try to find duration in video track
            for track in mediainfo["media"]["track"]:
                if track["@type"] == "Video" and "Duration" in track:
                    return float(track["Duration"])
            
            # If not found in video track, try general track
            for track in mediainfo["media"]["track"]:
                if track["@type"] == "General" and "Duration" in track:
                    return float(track["Duration"])
                    
            raise ValueError(f"Could not find Duration in mediainfo output for {file_path}")
            
        except Exception as e:
            self.logger.warning(f"Error getting duration from JSON: {str(e)}. Trying XML format.")
            
            # Fall back to XML format
            try:
                xml_output = self.get_mediainfo_xml(file_path)
                root = ET.fromstring(xml_output)
                
                # Try to find duration in video track
                for track in root.findall(".//track[@type='Video']"):
                    duration = track.find("Duration")
                    if duration is not None and duration.text:
                        return float(duration.text)
                
                # If not found in video track, try general track
                for track in root.findall(".//track[@type='General']"):
                    duration = track.find("Duration")
                    if duration is not None and duration.text:
                        return float(duration.text)
                        
                raise ValueError(f"Could not find Duration in mediainfo XML output for {file_path}")
                
            except Exception as e2:
                self.logger.error(f"Failed to get duration from XML: {str(e2)}")
                raise
    
    def get_video_resolution(self, file_path):
        """
        Get the resolution (width and height) of a video file.
        
        Args:
            file_path: Path to the video file
            
        Returns:
            Tuple containing (width, height) as integers
            
        Raises:
            ValueError: If resolution information can't be found
        """
        try:
            # Try to get resolution from JSON output
            mediainfo = self.get_mediainfo_json(file_path)
            
            # Find video track
            for track in mediainfo["media"]["track"]:
                if track["@type"] == "Video":
                    if "Width" in track and "Height" in track:
                        return (int(track["Width"]), int(track["Height"]))
            
            raise ValueError(f"Could not find Video track with Width/Height in mediainfo output for {file_path}")
            
        except Exception as e:
            self.logger.warning(f"Error getting resolution from JSON: {str(e)}. Trying XML format.")
            
            # Fall back to XML format
            try:
                xml_output = self.get_mediainfo_xml(file_path)
                root = ET.fromstring(xml_output)
                
                # Find video track
                for track in root.findall(".//track[@type='Video']"):
                    width = track.find("Width")
                    height = track.find("Height")
                    
                    if width is not None and height is not None and width.text and height.text:
                        return (int(width.text), int(height.text))
                
                raise ValueError(f"Could not find Video track with Width/Height in mediainfo XML output for {file_path}")
                
            except Exception as e2:
                self.logger.error(f"Failed to get resolution from XML: {str(e2)}")
                raise
    
    def get_video_framerate(self, file_path):
        """
        Get the framerate of a video file.
        
        Args:
            file_path: Path to the video file
            
        Returns:
            Framerate as float
            
        Raises:
            ValueError: If framerate information can't be found
        """
        try:
            # Try to get framerate from JSON output
            mediainfo = self.get_mediainfo_json(file_path)
            
            # Find video track
            for track in mediainfo["media"]["track"]:
                if track["@type"] == "Video":
                    if "FrameRate" in track:
                        return float(track["FrameRate"])
            
            raise ValueError(f"Could not find Video track with FrameRate in mediainfo output for {file_path}")
            
        except Exception as e:
            self.logger.warning(f"Error getting framerate from JSON: {str(e)}. Trying XML format.")
            
            # Fall back to XML format
            try:
                xml_output = self.get_mediainfo_xml(file_path)
                root = ET.fromstring(xml_output)
                
                # Find video track
                for track in root.findall(".//track[@type='Video']"):
                    framerate = track.find("FrameRate")
                    
                    if framerate is not None and framerate.text:
                        return float(framerate.text)
                
                raise ValueError(f"Could not find Video track with FrameRate in mediainfo XML output for {file_path}")
                
            except Exception as e2:
                self.logger.error(f"Failed to get framerate from XML: {str(e2)}")
                raise
    
    def get_audio_properties(self, file_path):
        """
        Get audio properties (sample rate and channels) of a media file.
        
        Args:
            file_path: Path to the media file
            
        Returns:
            Tuple containing (sample_rate, channels) as integers
            
        Raises:
            ValueError: If audio property information can't be found
        """
        try:
            # Try to get audio properties from JSON output
            mediainfo = self.get_mediainfo_json(file_path)
            
            # Find audio track
            for track in mediainfo["media"]["track"]:
                if track["@type"] == "Audio":
                    sample_rate = int(track.get("SamplingRate", 0))
                    channels = int(track.get("Channels", 0))
                    
                    if sample_rate > 0 and channels > 0:
                        return (sample_rate, channels)
            
            raise ValueError(f"Could not find Audio track with SamplingRate/Channels in mediainfo output for {file_path}")
            
        except Exception as e:
            self.logger.warning(f"Error getting audio properties from JSON: {str(e)}. Trying XML format.")
            
            # Fall back to XML format
            try:
                xml_output = self.get_mediainfo_xml(file_path)
                root = ET.fromstring(xml_output)
                
                # Find audio track
                for track in root.findall(".//track[@type='Audio']"):
                    sampling_rate = track.find("SamplingRate")
                    channels = track.find("Channels")
                    
                    if sampling_rate is not None and channels is not None and sampling_rate.text and channels.text:
                        return (int(sampling_rate.text), int(channels.text))
                
                raise ValueError(f"Could not find Audio track with SamplingRate/Channels in mediainfo XML output for {file_path}")
                
            except Exception as e2:
                self.logger.error(f"Failed to get audio properties from XML: {str(e2)}")
                raise 