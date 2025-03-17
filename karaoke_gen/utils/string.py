"""
String utility functions.
"""

import re
import unicodedata
from typing import Optional, List, Dict, Any


def slugify(value: str, allow_unicode: bool = False) -> str:
    """
    Convert a string to a URL-friendly slug.
    
    Args:
        value: The string to convert
        allow_unicode: Whether to allow Unicode characters
        
    Returns:
        The slugified string
    """
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    value = re.sub(r"[-\s]+", "-", value).strip("-_")
    return value


def truncate_string(value: str, max_length: int, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length.
    
    Args:
        value: The string to truncate
        max_length: The maximum length
        suffix: The suffix to append if truncated
        
    Returns:
        The truncated string
    """
    if len(value) <= max_length:
        return value
    
    return value[:max_length - len(suffix)] + suffix


def extract_artist_and_title(filename: str) -> Dict[str, str]:
    """
    Extract artist and title from a filename.
    
    Args:
        filename: The filename to extract from
        
    Returns:
        A dictionary with "artist" and "title" keys
    """
    # Remove file extension
    name_without_ext = re.sub(r"\.[^.]+$", "", filename)
    
    # Try to split by " - " first
    parts = name_without_ext.split(" - ", 1)
    if len(parts) == 2:
        return {"artist": parts[0].strip(), "title": parts[1].strip()}
    
    # Try to split by "-" if " - " didn't work
    parts = name_without_ext.split("-", 1)
    if len(parts) == 2:
        return {"artist": parts[0].strip(), "title": parts[1].strip()}
    
    # If no separator found, use the whole name as the title
    return {"artist": "", "title": name_without_ext.strip()}


def format_duration(seconds: int) -> str:
    """
    Format a duration in seconds to a human-readable string.
    
    Args:
        seconds: The duration in seconds
        
    Returns:
        The formatted duration string (MM:SS)
    """
    minutes, seconds = divmod(seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def format_filesize(size_bytes: int) -> str:
    """
    Format a file size in bytes to a human-readable string.
    
    Args:
        size_bytes: The file size in bytes
        
    Returns:
        The formatted file size string
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    
    size_kb = size_bytes / 1024
    if size_kb < 1024:
        return f"{size_kb:.1f} KB"
    
    size_mb = size_kb / 1024
    if size_mb < 1024:
        return f"{size_mb:.1f} MB"
    
    size_gb = size_mb / 1024
    return f"{size_gb:.1f} GB"


def strip_html_tags(html: str) -> str:
    """
    Strip HTML tags from a string.
    
    Args:
        html: The HTML string
        
    Returns:
        The string with HTML tags removed
    """
    return re.sub(r"<[^>]+>", "", html)


def normalize_whitespace(text: str) -> str:
    """
    Normalize whitespace in a string.
    
    Args:
        text: The string to normalize
        
    Returns:
        The string with normalized whitespace
    """
    # Replace multiple whitespace characters with a single space
    return re.sub(r"\s+", " ", text).strip()


def extract_urls(text: str) -> List[str]:
    """
    Extract URLs from a string.
    
    Args:
        text: The string to extract URLs from
        
    Returns:
        A list of URLs
    """
    url_pattern = r"https?://[^\s]+"
    return re.findall(url_pattern, text)


def replace_placeholders(template: str, data: Dict[str, Any]) -> str:
    """
    Replace placeholders in a template string with values from a dictionary.
    
    Args:
        template: The template string with {placeholder} syntax
        data: The dictionary with placeholder values
        
    Returns:
        The template with placeholders replaced
    """
    return template.format(**data)


def generate_random_string(length: int = 8) -> str:
    """
    Generate a random string of a specified length.
    
    Args:
        length: The length of the random string
        
    Returns:
        The random string
    """
    import random
    import string
    
    characters = string.ascii_letters + string.digits
    return "".join(random.choice(characters) for _ in range(length)) 