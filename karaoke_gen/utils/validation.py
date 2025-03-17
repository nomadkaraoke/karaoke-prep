"""
Validation utility functions.
"""

import os
import logging
from typing import Optional, Dict, Any, List, Callable


def is_url(string: str) -> bool:
    """
    Check if a string is a URL.
    
    Args:
        string: The string to check
        
    Returns:
        True if the string is a URL, False otherwise
    """
    return string.startswith("http://") or string.startswith("https://")


def is_file(string: str) -> bool:
    """
    Check if a string is a valid file.
    
    Args:
        string: The string to check
        
    Returns:
        True if the string is a valid file, False otherwise
    """
    return os.path.isfile(string)


def is_directory(string: str) -> bool:
    """
    Check if a string is a valid directory.
    
    Args:
        string: The string to check
        
    Returns:
        True if the string is a valid directory, False otherwise
    """
    return os.path.isdir(string)


def prompt_user_confirmation_or_raise_exception(
    prompt_message: str, 
    exit_message: str, 
    allow_empty: bool = False,
    non_interactive: bool = False,
    logger: Optional[logging.Logger] = None
) -> None:
    """
    Prompt the user for confirmation or raise an exception.
    
    Args:
        prompt_message: The message to display to the user
        exit_message: The message to display if the user does not confirm
        allow_empty: Whether to allow an empty response
        non_interactive: Whether to automatically confirm in non-interactive mode
        logger: The logger to use
        
    Raises:
        Exception: If the user does not confirm
    """
    if non_interactive:
        if logger:
            logger.info(f"Non-interactive mode, automatically confirming: {prompt_message}")
        return
    
    if not prompt_user_bool(prompt_message, allow_empty=allow_empty):
        if logger:
            logger.error(exit_message)
        raise Exception(exit_message)


def prompt_user_bool(prompt_message: str, allow_empty: bool = False) -> bool:
    """
    Prompt the user for a boolean value.
    
    Args:
        prompt_message: The message to display to the user
        allow_empty: Whether to allow an empty response
        
    Returns:
        True if the user confirms, False otherwise
    """
    options_string = "[y]/n" if allow_empty else "y/[n]"
    accept_responses = ["y", "yes"]
    if allow_empty:
        accept_responses.append("")
    
    print()
    response = input(f"{prompt_message} {options_string} ").strip().lower()
    return response in accept_responses


def validate_input_parameters_for_features(
    config: Dict[str, Any],
    logger: Optional[logging.Logger] = None,
    prompt_confirmation: Optional[Callable] = None
) -> Dict[str, bool]:
    """
    Validate input parameters for enabled features.
    
    Args:
        config: The configuration dictionary
        logger: The logger to use
        prompt_confirmation: A function to prompt the user for confirmation
        
    Returns:
        A dictionary of enabled features
        
    Raises:
        Exception: If validation fails
    """
    if logger:
        logger.info(f"Validating input parameters for enabled features...")
    
    current_directory = os.getcwd()
    if logger:
        logger.info(f"Current directory to process: {current_directory}")
    
    enabled_features = {
        "youtube_upload": False,
        "discord_notification": False,
        "folder_organisation": False,
        "public_share_copy": False,
        "public_share_rclone": False,
        "cdg_zip_creation": config.get("enable_cdg", False),
        "txt_zip_creation": config.get("enable_txt", False)
    }
    
    # Enable youtube upload if client secrets file is provided and is valid JSON
    youtube_client_secrets_file = config.get("youtube_client_secrets_file")
    youtube_description_file = config.get("youtube_description_file")
    
    if youtube_client_secrets_file is not None and youtube_description_file is not None:
        if not os.path.isfile(youtube_client_secrets_file):
            raise Exception(f"YouTube client secrets file does not exist: {youtube_client_secrets_file}")
        
        if not os.path.isfile(youtube_description_file):
            raise Exception(f"YouTube description file does not exist: {youtube_description_file}")
        
        # Test parsing the file as JSON to check it's valid
        try:
            import json
            with open(youtube_client_secrets_file, "r") as f:
                json.load(f)
        except json.JSONDecodeError as e:
            raise Exception(f"YouTube client secrets file is not valid JSON: {youtube_client_secrets_file}") from e
        
        if logger:
            logger.debug(f"YouTube upload checks passed, enabling YouTube upload")
        enabled_features["youtube_upload"] = True
    
    # Enable discord notifications if webhook URL is provided and is valid URL
    discord_webhook_url = config.get("discord_webhook_url")
    if discord_webhook_url is not None:
        if not discord_webhook_url.startswith("https://discord.com/api/webhooks/"):
            raise Exception(f"Discord webhook URL is not valid: {discord_webhook_url}")
        
        if logger:
            logger.debug(f"Discord webhook URL checks passed, enabling Discord notifications")
        enabled_features["discord_notification"] = True
    
    # Enable folder organisation if brand prefix and target directory are provided and target directory is valid
    brand_prefix = config.get("brand_prefix")
    organised_dir = config.get("organised_dir")
    
    if brand_prefix is not None and organised_dir is not None:
        if not os.path.isdir(organised_dir):
            raise Exception(f"Target directory does not exist: {organised_dir}")
        
        if logger:
            logger.debug(f"Brand prefix and target directory provided, enabling folder organisation")
        enabled_features["folder_organisation"] = True
    
    # Enable public share copy if public share directory is provided and is valid directory with MP4 and CDG subdirectories
    public_share_dir = config.get("public_share_dir")
    if public_share_dir is not None:
        if not os.path.isdir(public_share_dir):
            raise Exception(f"Public share directory does not exist: {public_share_dir}")
        
        mp4_dir = os.path.join(public_share_dir, "MP4")
        cdg_dir = os.path.join(public_share_dir, "CDG")
        
        if not os.path.isdir(mp4_dir):
            os.makedirs(mp4_dir, exist_ok=True)
            if logger:
                logger.info(f"Created MP4 subdirectory: {mp4_dir}")
        
        if not os.path.isdir(cdg_dir):
            os.makedirs(cdg_dir, exist_ok=True)
            if logger:
                logger.info(f"Created CDG subdirectory: {cdg_dir}")
        
        if logger:
            logger.debug(f"Public share directory checks passed, enabling public share copy")
        enabled_features["public_share_copy"] = True
    
    # Enable public share rclone if rclone destination is provided
    rclone_destination = config.get("rclone_destination")
    if rclone_destination is not None:
        if logger:
            logger.debug(f"Rclone destination provided, enabling rclone sync")
        enabled_features["public_share_rclone"] = True
    
    # Tell user which features are enabled, prompt them to confirm before proceeding
    if logger:
        logger.info(f"Enabled features:")
        logger.info(f" CDG ZIP creation: {enabled_features['cdg_zip_creation']}")
        logger.info(f" TXT ZIP creation: {enabled_features['txt_zip_creation']}")
        logger.info(f" YouTube upload: {enabled_features['youtube_upload']}")
        logger.info(f" Discord notifications: {enabled_features['discord_notification']}")
        logger.info(f" Folder organisation: {enabled_features['folder_organisation']}")
        logger.info(f" Public share copy: {enabled_features['public_share_copy']}")
        logger.info(f" Public share rclone: {enabled_features['public_share_rclone']}")
    
    if prompt_confirmation:
        prompt_confirmation(
            f"Confirm features enabled log messages above match your expectations for finalisation?",
            "Refusing to proceed without user confirmation they're happy with enabled features.",
            allow_empty=True,
        )
    
    return enabled_features 