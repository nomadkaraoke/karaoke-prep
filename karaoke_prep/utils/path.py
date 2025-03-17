"""
Path utility functions.
"""

import os
import glob
import shutil
from typing import List, Optional, Dict, Any, Union
import logging


def normalize_path(path: str) -> str:
    """
    Normalize a path to use the correct path separator for the current OS.
    
    Args:
        path: The path to normalize
        
    Returns:
        The normalized path
    """
    return os.path.normpath(path)


def join_paths(*paths: str) -> str:
    """
    Join paths using the correct path separator for the current OS.
    
    Args:
        *paths: The paths to join
        
    Returns:
        The joined path
    """
    return os.path.join(*paths)


def get_absolute_path(path: str) -> str:
    """
    Get the absolute path of a path.
    
    Args:
        path: The path to get the absolute path of
        
    Returns:
        The absolute path
    """
    return os.path.abspath(path)


def get_relative_path(path: str, start: Optional[str] = None) -> str:
    """
    Get the relative path of a path.
    
    Args:
        path: The path to get the relative path of
        start: The start path (defaults to the current working directory)
        
    Returns:
        The relative path
    """
    if start is None:
        start = os.getcwd()
    
    return os.path.relpath(path, start)


def get_parent_directory(path: str) -> str:
    """
    Get the parent directory of a path.
    
    Args:
        path: The path to get the parent directory of
        
    Returns:
        The parent directory
    """
    return os.path.dirname(path)


def get_filename(path: str) -> str:
    """
    Get the filename from a path.
    
    Args:
        path: The path to get the filename from
        
    Returns:
        The filename
    """
    return os.path.basename(path)


def get_filename_without_extension(path: str) -> str:
    """
    Get the filename without extension from a path.
    
    Args:
        path: The path to get the filename without extension from
        
    Returns:
        The filename without extension
    """
    return os.path.splitext(os.path.basename(path))[0]


def get_file_extension(path: str) -> str:
    """
    Get the file extension from a path.
    
    Args:
        path: The path to get the file extension from
        
    Returns:
        The file extension (including the dot)
    """
    return os.path.splitext(path)[1]


def create_directory(directory: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Create a directory if it doesn't exist.
    
    Args:
        directory: The directory to create
        logger: The logger to use
        
    Returns:
        True if the directory was created or already exists, False otherwise
    """
    try:
        os.makedirs(directory, exist_ok=True)
        if logger:
            logger.info(f"Created directory: {directory}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to create directory {directory}: {str(e)}")
        return False


def delete_directory(directory: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Delete a directory if it exists.
    
    Args:
        directory: The directory to delete
        logger: The logger to use
        
    Returns:
        True if the directory was deleted or doesn't exist, False otherwise
    """
    if not os.path.exists(directory):
        return True
    
    try:
        shutil.rmtree(directory)
        if logger:
            logger.info(f"Deleted directory: {directory}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to delete directory {directory}: {str(e)}")
        return False


def list_files(directory: str, pattern: str = "*") -> List[str]:
    """
    List files in a directory matching a pattern.
    
    Args:
        directory: The directory to list files in
        pattern: The glob pattern to match files against
        
    Returns:
        A list of file paths
    """
    return glob.glob(os.path.join(directory, pattern))


def list_directories(directory: str) -> List[str]:
    """
    List subdirectories in a directory.
    
    Args:
        directory: The directory to list subdirectories in
        
    Returns:
        A list of directory paths
    """
    return [
        os.path.join(directory, d) for d in os.listdir(directory)
        if os.path.isdir(os.path.join(directory, d))
    ]


def get_file_info(file_path: str) -> Dict[str, Any]:
    """
    Get information about a file.
    
    Args:
        file_path: The path to the file
        
    Returns:
        A dictionary with file information
    """
    if not os.path.isfile(file_path):
        return {}
    
    stat = os.stat(file_path)
    
    return {
        "path": file_path,
        "size": stat.st_size,
        "created": stat.st_ctime,
        "modified": stat.st_mtime,
        "accessed": stat.st_atime,
        "filename": os.path.basename(file_path),
        "extension": os.path.splitext(file_path)[1],
        "directory": os.path.dirname(file_path),
    }


def find_files_by_extension(directory: str, extension: str, recursive: bool = True) -> List[str]:
    """
    Find files with a specific extension in a directory.
    
    Args:
        directory: The directory to search in
        extension: The file extension to search for (with or without the dot)
        recursive: Whether to search recursively
        
    Returns:
        A list of file paths
    """
    if not extension.startswith("."):
        extension = f".{extension}"
    
    if recursive:
        pattern = os.path.join(directory, f"**/*{extension}")
        return glob.glob(pattern, recursive=True)
    else:
        pattern = os.path.join(directory, f"*{extension}")
        return glob.glob(pattern)


def copy_directory(source: str, destination: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Copy a directory.
    
    Args:
        source: The source directory
        destination: The destination directory
        logger: The logger to use
        
    Returns:
        True if the directory was copied successfully, False otherwise
    """
    try:
        shutil.copytree(source, destination)
        if logger:
            logger.info(f"Copied directory from {source} to {destination}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to copy directory from {source} to {destination}: {str(e)}")
        return False


def move_directory(source: str, destination: str, logger: Optional[logging.Logger] = None) -> bool:
    """
    Move a directory.
    
    Args:
        source: The source directory
        destination: The destination directory
        logger: The logger to use
        
    Returns:
        True if the directory was moved successfully, False otherwise
    """
    try:
        shutil.move(source, destination)
        if logger:
            logger.info(f"Moved directory from {source} to {destination}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to move directory from {source} to {destination}: {str(e)}")
        return False


def get_directory_size(directory: str) -> int:
    """
    Get the total size of a directory in bytes.
    
    Args:
        directory: The directory to get the size of
        
    Returns:
        The total size in bytes
    """
    total_size = 0
    
    for dirpath, dirnames, filenames in os.walk(directory):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if os.path.isfile(file_path):
                total_size += os.path.getsize(file_path)
    
    return total_size 