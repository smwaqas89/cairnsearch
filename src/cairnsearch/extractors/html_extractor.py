"""HTML text extraction."""
from pathlib import Path
from bs4 import BeautifulSoup

from .base import BaseExtractor, ExtractionResult


class HtmlExtractor(BaseExtractor):
    """Extract text from HTML files."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".html", ".htm", ".xhtml"]

    def extract(self, file_path: Path) -> ExtractionResult:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            
            soup = BeautifulSoup(content, "lxml")
            
            # Remove script and style elements
            for element in soup(["script", "style", "meta", "link"]):
                element.decompose()
            
            # Get text
            text = soup.get_text(separator="\n", strip=True)
            
            # Extract title
            title = None
            title_tag = soup.find("title")
            if title_tag:
                title = title_tag.get_text(strip=True)

            return ExtractionResult(
                success=True,
                text=text,
                metadata={
                    "title": title,
                },
                extraction_method="direct"
            )
        except Exception as e:
            return ExtractionResult(success=False, error=str(e))
