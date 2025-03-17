"""
Karaoke Generator package.

This package provides tools for generating karaoke videos with synchronized lyrics.
It handles the entire process from downloading audio and lyrics to creating the final
video with title screens, synchronized lyrics, and distribution options.
"""

__version__ = "0.50.0"

# Import legacy classes for backward compatibility
from karaoke_prep.legacy import KaraokePrep, KaraokeFinalise

# Import core components
from karaoke_prep.controller import KaraokeController
from karaoke_prep.core import ProjectConfig, Track, KaraokeGenError

# Import services
from karaoke_prep.services import (
    MainService,
    AudioService,
    LyricsService,
    MediaService,
    VideoService,
    DistributionService,
)

# Import utility functions
from karaoke_prep.utils import (
    # Config utilities
    load_config_file,
    save_config_file,
    get_config_value,
    set_config_value,
    merge_configs,
    validate_required_config_keys,
    get_nested_config_value,
    set_nested_config_value,
    
    # File utilities
    sanitize_filename,
    ensure_directory_exists,
    backup_existing_files,
    file_exists,
    copy_file,
    move_file,
    delete_file,
    create_zip_file,
    execute_command,
    
    # Logging utilities
    setup_logger,
    get_log_level_from_string,
    configure_logger_from_config,
    log_section,
    log_subsection,
    log_dict,
    log_exception,
    
    # Path utilities
    normalize_path,
    join_paths,
    get_absolute_path,
    get_relative_path,
    get_parent_directory,
    get_filename,
    get_filename_without_extension,
    get_file_extension,
    create_directory,
    delete_directory,
    list_files,
    list_directories,
    get_file_info,
    find_files_by_extension,
    copy_directory,
    move_directory,
    get_directory_size,
    
    # String utilities
    slugify,
    truncate_string,
    extract_artist_and_title,
    format_duration,
    format_filesize,
    strip_html_tags,
    normalize_whitespace,
    extract_urls,
    replace_placeholders,
    generate_random_string,
    
    # Validation utilities
    is_url,
    is_file,
    is_directory,
    prompt_user_confirmation_or_raise_exception,
    prompt_user_bool,
    validate_input_parameters_for_features,
    
    # Date utilities
    get_current_timestamp,
    get_current_date,
    get_current_time,
    format_date,
    parse_date,
    get_date_components,
    add_days,
    days_between,
    is_date_in_range,
    get_month_name,
    get_day_of_week,
)

__all__ = [
    # Version
    "__version__",
    
    # Legacy classes
    "KaraokePrep",
    "KaraokeFinalise",
    
    # Core components
    "KaraokeController",
    "ProjectConfig",
    "Track",
    "KaraokeGenError",
    
    # Services
    "MainService",
    "AudioService",
    "LyricsService",
    "MediaService",
    "VideoService",
    "DistributionService",
    
    # Config utilities
    "load_config_file",
    "save_config_file",
    "get_config_value",
    "set_config_value",
    "merge_configs",
    "validate_required_config_keys",
    "get_nested_config_value",
    "set_nested_config_value",
    
    # File utilities
    "sanitize_filename",
    "ensure_directory_exists",
    "backup_existing_files",
    "file_exists",
    "copy_file",
    "move_file",
    "delete_file",
    "create_zip_file",
    "execute_command",
    
    # Logging utilities
    "setup_logger",
    "get_log_level_from_string",
    "configure_logger_from_config",
    "log_section",
    "log_subsection",
    "log_dict",
    "log_exception",
    
    # Path utilities
    "normalize_path",
    "join_paths",
    "get_absolute_path",
    "get_relative_path",
    "get_parent_directory",
    "get_filename",
    "get_filename_without_extension",
    "get_file_extension",
    "create_directory",
    "delete_directory",
    "list_files",
    "list_directories",
    "get_file_info",
    "find_files_by_extension",
    "copy_directory",
    "move_directory",
    "get_directory_size",
    
    # String utilities
    "slugify",
    "truncate_string",
    "extract_artist_and_title",
    "format_duration",
    "format_filesize",
    "strip_html_tags",
    "normalize_whitespace",
    "extract_urls",
    "replace_placeholders",
    "generate_random_string",
    
    # Validation utilities
    "is_url",
    "is_file",
    "is_directory",
    "prompt_user_confirmation_or_raise_exception",
    "prompt_user_bool",
    "validate_input_parameters_for_features",
    
    # Date utilities
    "get_current_timestamp",
    "get_current_date",
    "get_current_time",
    "format_date",
    "parse_date",
    "get_date_components",
    "add_days",
    "days_between",
    "is_date_in_range",
    "get_month_name",
    "get_day_of_week",
]
