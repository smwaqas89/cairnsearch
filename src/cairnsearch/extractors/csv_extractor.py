"""CSV text extraction."""
import csv
from pathlib import Path

from .base import BaseExtractor, ExtractionResult


class CsvExtractor(BaseExtractor):
    """Extract text from CSV files."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".csv", ".tsv"]

    def extract(self, file_path: Path) -> ExtractionResult:
        try:
            delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","
            
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                rows = []
                for row in reader:
                    if any(cell.strip() for cell in row):
                        rows.append(" | ".join(row))
            
            text = "\n".join(rows)

            return ExtractionResult(
                success=True,
                text=text,
                metadata={},
                extraction_method="direct"
            )
        except Exception as e:
            return ExtractionResult(success=False, error=str(e))
