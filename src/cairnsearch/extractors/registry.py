"""Extractor registry - routes file types to extractors."""
from pathlib import Path
from typing import Optional

from .base import BaseExtractor, ExtractionResult
from .pdf_extractor import PDFExtractor
from .docx_extractor import DocxExtractor, DocExtractor
from .xlsx_extractor import XlsxExtractor
from .csv_extractor import CsvExtractor
from .html_extractor import HtmlExtractor
from .txt_extractor import TxtExtractor
from .ocr_extractor import OcrExtractor


class ExtractorRegistry:
    """Registry of file extractors."""

    def __init__(self):
        self._extractors: list[BaseExtractor] = [
            PDFExtractor(),
            DocxExtractor(),
            DocExtractor(),  # Old .doc format
            XlsxExtractor(),
            CsvExtractor(),
            HtmlExtractor(),
            TxtExtractor(),
            OcrExtractor(),
        ]
        self._extension_map: dict[str, BaseExtractor] = {}
        self._build_extension_map()

    def _build_extension_map(self) -> None:
        """Build mapping of extensions to extractors."""
        for extractor in self._extractors:
            for ext in extractor.supported_extensions:
                self._extension_map[ext.lower()] = extractor

    def get_extractor(self, file_path: Path) -> Optional[BaseExtractor]:
        """Get extractor for file based on extension."""
        ext = file_path.suffix.lower()
        return self._extension_map.get(ext)

    def can_extract(self, file_path: Path) -> bool:
        """Check if we have an extractor for this file type."""
        return self.get_extractor(file_path) is not None

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract text from file using appropriate extractor."""
        extractor = self.get_extractor(file_path)
        if extractor is None:
            return ExtractionResult(
                success=False,
                error=f"No extractor for file type: {file_path.suffix}"
            )
        return extractor.extract(file_path)

    def supported_extensions(self) -> list[str]:
        """Get list of all supported extensions."""
        return sorted(self._extension_map.keys())


# Global registry instance
_registry: Optional[ExtractorRegistry] = None


def get_registry() -> ExtractorRegistry:
    """Get the global extractor registry."""
    global _registry
    if _registry is None:
        _registry = ExtractorRegistry()
    return _registry
