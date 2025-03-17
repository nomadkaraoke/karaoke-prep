"""
Logging utility functions.
"""

import os
import logging
from typing import Optional, Dict, Any


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    file_level: Optional[int] = None,
    console_level: Optional[int] = None,
) -> logging.Logger:
    """
    Set up a logger with console and file handlers.
    
    Args:
        name: The name of the logger
        log_file: The log file to write to (optional)
        level: The default logging level
        format_string: The format string to use for log messages
        file_level: The logging level for the file handler (defaults to level)
        console_level: The logging level for the console handler (defaults to level)
        
    Returns:
        The configured logger
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    if file_level is None:
        file_level = level
        
    if console_level is None:
        console_level = level
    
    # Create logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(format_string)
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Create file handler if log_file is provided
    if log_file:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_log_level_from_string(level_str: str) -> int:
    """
    Convert a string log level to a logging level constant.
    
    Args:
        level_str: The string log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
    Returns:
        The corresponding logging level constant
        
    Raises:
        ValueError: If the string log level is invalid
    """
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    
    level_str = level_str.upper()
    if level_str not in level_map:
        valid_levels = ", ".join(level_map.keys())
        raise ValueError(f"Invalid log level: {level_str}. Valid levels are: {valid_levels}")
    
    return level_map[level_str]


def configure_logger_from_config(
    name: str,
    config: Dict[str, Any],
    default_level: int = logging.INFO,
    default_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
) -> logging.Logger:
    """
    Configure a logger from a configuration dictionary.
    
    Args:
        name: The name of the logger
        config: The configuration dictionary
        default_level: The default logging level
        default_format: The default format string
        
    Returns:
        The configured logger
    """
    log_config = config.get("logging", {})
    
    # Get log level
    level_str = log_config.get("level", "INFO")
    try:
        level = get_log_level_from_string(level_str)
    except ValueError:
        level = default_level
    
    # Get log format
    format_string = log_config.get("format", default_format)
    
    # Get log file
    log_file = log_config.get("file")
    
    # Get file and console levels
    file_level_str = log_config.get("file_level")
    console_level_str = log_config.get("console_level")
    
    file_level = None
    if file_level_str:
        try:
            file_level = get_log_level_from_string(file_level_str)
        except ValueError:
            pass
    
    console_level = None
    if console_level_str:
        try:
            console_level = get_log_level_from_string(console_level_str)
        except ValueError:
            pass
    
    return setup_logger(
        name=name,
        log_file=log_file,
        level=level,
        format_string=format_string,
        file_level=file_level,
        console_level=console_level,
    )


def log_section(logger: logging.Logger, section_name: str, level: int = logging.INFO) -> None:
    """
    Log a section header.
    
    Args:
        logger: The logger to use
        section_name: The name of the section
        level: The logging level
    """
    separator = "=" * 80
    logger.log(level, separator)
    logger.log(level, f" {section_name} ".center(80, "="))
    logger.log(level, separator)


def log_subsection(logger: logging.Logger, subsection_name: str, level: int = logging.INFO) -> None:
    """
    Log a subsection header.
    
    Args:
        logger: The logger to use
        subsection_name: The name of the subsection
        level: The logging level
    """
    separator = "-" * 60
    logger.log(level, separator)
    logger.log(level, f" {subsection_name} ".center(60, "-"))
    logger.log(level, separator)


def log_dict(logger: logging.Logger, data: Dict[str, Any], title: Optional[str] = None, level: int = logging.INFO) -> None:
    """
    Log a dictionary.
    
    Args:
        logger: The logger to use
        data: The dictionary to log
        title: The title to use (optional)
        level: The logging level
    """
    import json
    
    if title:
        logger.log(level, f"{title}:")
    
    formatted_json = json.dumps(data, indent=2)
    for line in formatted_json.splitlines():
        logger.log(level, line)


def log_exception(logger: logging.Logger, exception: Exception, message: str = "An error occurred") -> None:
    """
    Log an exception.
    
    Args:
        logger: The logger to use
        exception: The exception to log
        message: The message to log
    """
    logger.error(f"{message}: {str(exception)}", exc_info=True) 