"""
File utility functions.
"""

import os
import re
import shutil
import subprocess
import logging
import zipfile
from typing import Optional, List, Dict, Any


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to be safe for all operating systems.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        The sanitized filename
    """
    # Replace invalid characters with underscores
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(". ")
    # Ensure the filename is not empty
    if not sanitized:
        sanitized = "unnamed"
    return sanitized


def ensure_directory_exists(directory: str) -> None:
    """
    Ensure a directory exists, creating it if necessary.
    
    Args:
        directory: The directory to ensure exists
    """
    os.makedirs(directory, exist_ok=True)


def backup_existing_files(file_path: str, max_backups: int = 5) -> None:
    """
    Backup existing files to prevent overwriting.
    
    Args:
        file_path: The file to backup
        max_backups: The maximum number of backups to keep
    """
    if not os.path.exists(file_path):
        return
    
    # Create backup directory
    backup_dir = os.path.join(os.path.dirname(file_path), "backups")
    ensure_directory_exists(backup_dir)
    
    # Get base filename
    base_name = os.path.basename(file_path)
    
    # Create backup filename with timestamp
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(backup_dir, f"{base_name}.{timestamp}")
    
    # Copy the file to the backup location
    shutil.copy2(file_path, backup_file)
    
    # Remove old backups if there are too many
    backup_files = [
        os.path.join(backup_dir, f) for f in os.listdir(backup_dir)
        if f.startswith(base_name + ".")
    ]
    backup_files.sort(key=os.path.getmtime)
    
    if len(backup_files) > max_backups:
        for old_backup in backup_files[:-max_backups]:
            os.remove(old_backup)


def file_exists(file_path: str) -> bool:
    """
    Check if a file exists with proper error handling.
    
    Args:
        file_path: The file to check
        
    Returns:
        True if the file exists, False otherwise
    """
    try:
        return os.path.isfile(file_path)
    except Exception:
        return False


def copy_file(source: str, destination: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Copy a file with proper error handling.
    
    Args:
        source: The source file
        destination: The destination file
        logger: The logger to use
        
    Returns:
        True if the copy was successful, False otherwise
    """
    try:
        shutil.copy2(source, destination)
        if logger:
            logger.info(f"Copied {source} to {destination}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to copy {source} to {destination}: {str(e)}")
        return False


def move_file(source: str, destination: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Move a file with proper error handling.
    
    Args:
        source: The source file
        destination: The destination file
        logger: The logger to use
        
    Returns:
        True if the move was successful, False otherwise
    """
    try:
        shutil.move(source, destination)
        if logger:
            logger.info(f"Moved {source} to {destination}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to move {source} to {destination}: {str(e)}")
        return False


def delete_file(file_path: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Delete a file with proper error handling.
    
    Args:
        file_path: The file to delete
        logger: The logger to use
        
    Returns:
        True if the deletion was successful, False otherwise
    """
    try:
        os.remove(file_path)
        if logger:
            logger.info(f"Deleted {file_path}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to delete {file_path}: {str(e)}")
        return False


def create_zip_file(zip_file: str, files: List[str], logger: Optional[logging.Logger] = None) -> bool:
    """
    Create a zip file from a list of files.
    
    Args:
        zip_file: The zip file to create
        files: The files to include in the zip file
        logger: The logger to use
        
    Returns:
        True if the zip file was created successfully, False otherwise
    """
    try:
        with zipfile.ZipFile(zip_file, "w") as zipf:
            for file in files:
                if os.path.isfile(file):
                    zipf.write(file, os.path.basename(file))
                    if logger:
                        logger.info(f"Added {file} to {zip_file}")
        
        if logger:
            logger.info(f"Created zip file: {zip_file}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to create zip file {zip_file}: {str(e)}")
        return False


def execute_command(command: str, description: str, logger: Optional[logging.Logger] = None, dry_run: bool = False) -> bool:
    """
    Execute a shell command with proper error handling.
    
    Args:
        command: The command to execute
        description: A description of the command
        logger: The logger to use
        dry_run: Whether to perform a dry run
        
    Returns:
        True if the command was executed successfully, False otherwise
    """
    if logger:
        logger.info(description)
    
    if dry_run:
        if logger:
            logger.info(f"DRY RUN: Would run command: {command}")
        return True
    
    if logger:
        logger.info(f"Running command: {command}")
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        if logger and result.stdout:
            logger.debug(f"Command output: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        if logger:
            logger.error(f"Command failed with exit code {e.returncode}")
            logger.error(f"Command output (stdout): {e.stdout}")
            logger.error(f"Command output (stderr): {e.stderr}")
        return False
    except Exception as e:
        if logger:
            logger.error(f"Failed to execute command: {str(e)}")
        return False 