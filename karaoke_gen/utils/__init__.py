"""
Utility functions for the karaoke_gen package.
"""

# Import utility modules
from karaoke_gen.utils import config
from karaoke_gen.utils import date
from karaoke_gen.utils import file
from karaoke_gen.utils import logging
from karaoke_gen.utils import path
from karaoke_gen.utils import string
from karaoke_gen.utils import validation

# Re-export functions from config module
from karaoke_gen.utils.config import (
    load_config_file,
    save_config_file,
    get_config_value,
    set_config_value,
    merge_configs,
    validate_required_config_keys,
    get_nested_config_value,
    set_nested_config_value,
)

# Re-export functions from date module
from karaoke_gen.utils.date import (
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

# Re-export functions from file module
from karaoke_gen.utils.file import (
    sanitize_filename,
    ensure_directory_exists,
    backup_existing_files,
    file_exists,
    copy_file,
    move_file,
    delete_file,
    create_zip_file,
    execute_command,
)

# Re-export functions from logging module
from karaoke_gen.utils.logging import (
    setup_logger,
    get_log_level_from_string,
    configure_logger_from_config,
    log_section,
    log_subsection,
    log_dict,
    log_exception,
)

# Re-export functions from path module
from karaoke_gen.utils.path import (
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
)

# Re-export functions from string module
from karaoke_gen.utils.string import (
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
)

# Re-export functions from validation module
from karaoke_gen.utils.validation import (
    is_url,
    is_file,
    is_directory,
    prompt_user_confirmation_or_raise_exception,
    prompt_user_bool,
    validate_input_parameters_for_features,
)
