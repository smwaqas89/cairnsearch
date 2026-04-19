"""Text extractors module."""
from .base import BaseExtractor, ExtractionResult
from .registry import ExtractorRegistry, get_registry
from .metadata import extract_dates, normalize_date

__all__ = [
    "BaseExtractor", "ExtractionResult",
    "ExtractorRegistry", "get_registry",
    "extract_dates", "normalize_date",
]
