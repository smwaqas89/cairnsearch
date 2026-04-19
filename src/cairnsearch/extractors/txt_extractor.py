"""Plain text extraction."""
from pathlib import Path

from .base import BaseExtractor, ExtractionResult


class TxtExtractor(BaseExtractor):
    """Extract text from plain text files."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".txt", ".md", ".rst", ".log", ".json", ".xml", ".yaml", ".yml"]

    def extract(self, file_path: Path) -> ExtractionResult:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()

            return ExtractionResult(
                success=True,
                text=text,
                metadata={},
                extraction_method="direct"
            )
        except Exception as e:
            return ExtractionResult(success=False, error=str(e))
