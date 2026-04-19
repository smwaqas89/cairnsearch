"""Date extraction from text content."""
import re
from datetime import datetime
from typing import Optional
from dateutil.parser import parse as dateutil_parse


# Common date patterns
DATE_PATTERNS = [
    r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',                    # 01/15/2023 or 1/15/23
    r'\b\d{4}-\d{2}-\d{2}\b',                          # 2023-01-15
    r'\b\d{1,2}-\d{1,2}-\d{2,4}\b',                    # 01-15-2023
    r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}\b',  # January 15, 2023
    r'\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}\b',  # 15 January 2023
]


def extract_dates(text: str, max_dates: int = 50) -> list[str]:
    """
    Extract dates from text and return as ISO format strings.
    
    Args:
        text: Text to search for dates
        max_dates: Maximum number of dates to return
        
    Returns:
        List of dates in ISO format (YYYY-MM-DD), sorted and deduplicated
    """
    dates = set()
    
    for pattern in DATE_PATTERNS:
        for match in re.findall(pattern, text, re.IGNORECASE):
            try:
                parsed = dateutil_parse(match, fuzzy=False)
                # Only include reasonable dates (1900-2100)
                if 1900 <= parsed.year <= 2100:
                    dates.add(parsed.date().isoformat())
                if len(dates) >= max_dates:
                    break
            except (ValueError, OverflowError):
                continue
        if len(dates) >= max_dates:
            break
    
    return sorted(dates)


def normalize_date(date_str: Optional[str]) -> Optional[str]:
    """
    Normalize a date string to ISO format.
    
    Args:
        date_str: Date string in any format
        
    Returns:
        Date in ISO format (YYYY-MM-DD) or None if unparseable
    """
    if not date_str:
        return None
    try:
        parsed = dateutil_parse(date_str, fuzzy=True)
        return parsed.date().isoformat()
    except (ValueError, OverflowError):
        return None


def is_date_after(date_str: str, threshold: str) -> bool:
    """Check if date_str is after threshold date."""
    try:
        date = datetime.fromisoformat(date_str).date()
        threshold_date = datetime.fromisoformat(threshold).date()
        return date > threshold_date
    except ValueError:
        return False


def is_date_before(date_str: str, threshold: str) -> bool:
    """Check if date_str is before threshold date."""
    try:
        date = datetime.fromisoformat(date_str).date()
        threshold_date = datetime.fromisoformat(threshold).date()
        return date < threshold_date
    except ValueError:
        return False
