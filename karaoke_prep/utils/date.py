"""
Date utility functions.
"""

import datetime
from typing import Optional, Union, Dict, Any


def get_current_timestamp() -> str:
    """
    Get the current timestamp in ISO 8601 format.
    
    Returns:
        The current timestamp in ISO 8601 format
    """
    return datetime.datetime.now().isoformat()


def get_current_date() -> str:
    """
    Get the current date in YYYY-MM-DD format.
    
    Returns:
        The current date in YYYY-MM-DD format
    """
    return datetime.date.today().isoformat()


def get_current_time() -> str:
    """
    Get the current time in HH:MM:SS format.
    
    Returns:
        The current time in HH:MM:SS format
    """
    return datetime.datetime.now().strftime("%H:%M:%S")


def format_date(date: Union[datetime.date, datetime.datetime, str], format_string: str = "%Y-%m-%d") -> str:
    """
    Format a date object or string as a string.
    
    Args:
        date: The date to format
        format_string: The format string to use
        
    Returns:
        The formatted date string
        
    Raises:
        ValueError: If the date is not a valid date object or string
    """
    if isinstance(date, str):
        try:
            date = datetime.datetime.fromisoformat(date)
        except ValueError:
            try:
                date = datetime.datetime.strptime(date, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date string: {date}")
    
    return date.strftime(format_string)


def parse_date(date_string: str, format_string: Optional[str] = None) -> datetime.date:
    """
    Parse a date string into a date object.
    
    Args:
        date_string: The date string to parse
        format_string: The format string to use (optional)
        
    Returns:
        The parsed date object
        
    Raises:
        ValueError: If the date string is not valid
    """
    if format_string:
        return datetime.datetime.strptime(date_string, format_string).date()
    
    try:
        return datetime.date.fromisoformat(date_string)
    except ValueError:
        try:
            return datetime.datetime.fromisoformat(date_string).date()
        except ValueError:
            raise ValueError(f"Invalid date string: {date_string}")


def get_date_components(date: Union[datetime.date, datetime.datetime, str]) -> Dict[str, int]:
    """
    Get the components of a date.
    
    Args:
        date: The date to get components from
        
    Returns:
        A dictionary with "year", "month", and "day" keys
        
    Raises:
        ValueError: If the date is not a valid date object or string
    """
    if isinstance(date, str):
        date = parse_date(date)
    
    return {
        "year": date.year,
        "month": date.month,
        "day": date.day,
    }


def add_days(date: Union[datetime.date, datetime.datetime, str], days: int) -> datetime.date:
    """
    Add days to a date.
    
    Args:
        date: The date to add days to
        days: The number of days to add
        
    Returns:
        The new date
        
    Raises:
        ValueError: If the date is not a valid date object or string
    """
    if isinstance(date, str):
        date = parse_date(date)
    
    return date + datetime.timedelta(days=days)


def days_between(start_date: Union[datetime.date, datetime.datetime, str], 
                 end_date: Union[datetime.date, datetime.datetime, str]) -> int:
    """
    Calculate the number of days between two dates.
    
    Args:
        start_date: The start date
        end_date: The end date
        
    Returns:
        The number of days between the dates
        
    Raises:
        ValueError: If either date is not a valid date object or string
    """
    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
    
    delta = end_date - start_date
    return delta.days


def is_date_in_range(date: Union[datetime.date, datetime.datetime, str],
                     start_date: Union[datetime.date, datetime.datetime, str],
                     end_date: Union[datetime.date, datetime.datetime, str]) -> bool:
    """
    Check if a date is within a range.
    
    Args:
        date: The date to check
        start_date: The start date of the range
        end_date: The end date of the range
        
    Returns:
        True if the date is within the range, False otherwise
        
    Raises:
        ValueError: If any date is not a valid date object or string
    """
    if isinstance(date, str):
        date = parse_date(date)
    
    if isinstance(start_date, str):
        start_date = parse_date(start_date)
    
    if isinstance(end_date, str):
        end_date = parse_date(end_date)
    
    return start_date <= date <= end_date


def get_month_name(month: int) -> str:
    """
    Get the name of a month.
    
    Args:
        month: The month number (1-12)
        
    Returns:
        The month name
        
    Raises:
        ValueError: If the month is not valid
    """
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month: {month}")
    
    return datetime.date(2000, month, 1).strftime("%B")


def get_day_of_week(date: Union[datetime.date, datetime.datetime, str]) -> str:
    """
    Get the day of the week for a date.
    
    Args:
        date: The date to get the day of the week for
        
    Returns:
        The day of the week
        
    Raises:
        ValueError: If the date is not a valid date object or string
    """
    if isinstance(date, str):
        date = parse_date(date)
    
    return date.strftime("%A") 