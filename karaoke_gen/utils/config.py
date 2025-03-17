"""
Configuration utility functions.
"""

import os
import json
import logging
from typing import Dict, Any, Optional, List, Union


def load_config_file(config_file: str, logger: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """
    Load a configuration file.
    
    Args:
        config_file: The configuration file to load
        logger: The logger to use
        
    Returns:
        The loaded configuration
        
    Raises:
        FileNotFoundError: If the configuration file does not exist
        json.JSONDecodeError: If the configuration file is not valid JSON
    """
    if logger:
        logger.info(f"Loading configuration from {config_file}")
    
    if not os.path.isfile(config_file):
        error_msg = f"Configuration file not found: {config_file}"
        if logger:
            logger.error(error_msg)
        raise FileNotFoundError(error_msg)
    
    try:
        with open(config_file, "r") as f:
            config = json.load(f)
            
        if logger:
            logger.info(f"Successfully loaded configuration from {config_file}")
        return config
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in configuration file {config_file}: {str(e)}"
        if logger:
            logger.error(error_msg)
        raise


def save_config_file(config_file: str, config: Dict[str, Any], logger: Optional[logging.Logger] = None) -> bool:
    """
    Save a configuration file.
    
    Args:
        config_file: The configuration file to save
        config: The configuration to save
        logger: The logger to use
        
    Returns:
        True if the configuration was saved successfully, False otherwise
    """
    if logger:
        logger.info(f"Saving configuration to {config_file}")
    
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)
            
        if logger:
            logger.info(f"Successfully saved configuration to {config_file}")
        return True
    except Exception as e:
        if logger:
            logger.error(f"Failed to save configuration to {config_file}: {str(e)}")
        return False


def get_config_value(config: Dict[str, Any], key: str, default: Any = None) -> Any:
    """
    Get a value from a configuration dictionary.
    
    Args:
        config: The configuration dictionary
        key: The key to get
        default: The default value to return if the key is not found
        
    Returns:
        The value for the key, or the default value if the key is not found
    """
    return config.get(key, default)


def set_config_value(config: Dict[str, Any], key: str, value: Any) -> Dict[str, Any]:
    """
    Set a value in a configuration dictionary.
    
    Args:
        config: The configuration dictionary
        key: The key to set
        value: The value to set
        
    Returns:
        The updated configuration dictionary
    """
    config[key] = value
    return config


def merge_configs(base_config: Dict[str, Any], override_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge two configuration dictionaries.
    
    Args:
        base_config: The base configuration dictionary
        override_config: The override configuration dictionary
        
    Returns:
        The merged configuration dictionary
    """
    result = base_config.copy()
    
    for key, value in override_config.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
            
    return result


def validate_required_config_keys(config: Dict[str, Any], required_keys: List[str], logger: Optional[logging.Logger] = None) -> bool:
    """
    Validate that a configuration dictionary contains all required keys.
    
    Args:
        config: The configuration dictionary
        required_keys: The required keys
        logger: The logger to use
        
    Returns:
        True if all required keys are present, False otherwise
    """
    missing_keys = [key for key in required_keys if key not in config]
    
    if missing_keys:
        if logger:
            logger.error(f"Missing required configuration keys: {', '.join(missing_keys)}")
        return False
    
    return True


def get_nested_config_value(config: Dict[str, Any], key_path: str, default: Any = None) -> Any:
    """
    Get a nested value from a configuration dictionary using a dot-separated path.
    
    Args:
        config: The configuration dictionary
        key_path: The dot-separated path to the key
        default: The default value to return if the key is not found
        
    Returns:
        The value for the key, or the default value if the key is not found
    """
    keys = key_path.split(".")
    current = config
    
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
        
    return current


def set_nested_config_value(config: Dict[str, Any], key_path: str, value: Any) -> Dict[str, Any]:
    """
    Set a nested value in a configuration dictionary using a dot-separated path.
    
    Args:
        config: The configuration dictionary
        key_path: The dot-separated path to the key
        value: The value to set
        
    Returns:
        The updated configuration dictionary
    """
    keys = key_path.split(".")
    current = config
    
    # Navigate to the parent of the final key
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        elif not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
        
    # Set the value at the final key
    current[keys[-1]] = value
    
    return config 