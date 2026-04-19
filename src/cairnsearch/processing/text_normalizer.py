"""Text normalizer for cleaning and standardizing extracted text."""
import re
import unicodedata
from typing import Optional, List, Dict
import logging


logger = logging.getLogger(__name__)


class TextNormalizer:
    """
    Text normalizer with:
    - Unicode normalization
    - Whitespace normalization
    - Hyphenation fixing
    - OCR error correction
    - Boilerplate removal
    """
    
    # Common OCR character substitutions
    OCR_CORRECTIONS = {
        'ﬁ': 'fi',
        'ﬂ': 'fl',
        'ﬀ': 'ff',
        'ﬃ': 'ffi',
        'ﬄ': 'ffl',
        '—': '-',
        '–': '-',
        '"': '"',
        '"': '"',
        ''': "'",
        ''': "'",
        '…': '...',
        '­': '',  # Soft hyphen
        '\u00a0': ' ',  # Non-breaking space
        '\u2003': ' ',  # Em space
        '\u2002': ' ',  # En space
        '\u200b': '',  # Zero-width space
    }
    
    # Common boilerplate patterns
    BOILERPLATE_PATTERNS = [
        r'^Page\s+\d+\s*(of\s+\d+)?$',
        r'^\d+\s*$',
        r'^-\s*\d+\s*-$',
        r'^©.*\d{4}.*$',
        r'^All\s+[Rr]ights\s+[Rr]eserved\.?$',
        r'^CONFIDENTIAL.*$',
        r'^DRAFT.*$',
        r'^www\.[a-zA-Z0-9.-]+\.[a-z]+$',
        r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$',
    ]
    
    def __init__(
        self,
        fix_hyphenation: bool = True,
        normalize_unicode: bool = True,
        remove_boilerplate: bool = True,
        fix_ocr_errors: bool = True,
        min_line_length: int = 3,
    ):
        self.fix_hyphenation = fix_hyphenation
        self.normalize_unicode = normalize_unicode
        self.remove_boilerplate = remove_boilerplate
        self.fix_ocr_errors = fix_ocr_errors
        self.min_line_length = min_line_length
        
        self._boilerplate_regex = [
            re.compile(p, re.IGNORECASE | re.MULTILINE)
            for p in self.BOILERPLATE_PATTERNS
        ]
    
    def normalize(self, text: str) -> str:
        """Apply all normalizations to text."""
        if not text:
            return ""
        
        # Unicode normalization first
        if self.normalize_unicode:
            text = self._normalize_unicode(text)
        
        # Fix OCR errors
        if self.fix_ocr_errors:
            text = self._fix_ocr_errors(text)
        
        # Fix hyphenation
        if self.fix_hyphenation:
            text = self._fix_hyphenation(text)
        
        # Normalize whitespace
        text = self._normalize_whitespace(text)
        
        # Remove boilerplate
        if self.remove_boilerplate:
            text = self._remove_boilerplate(text)
        
        return text.strip()
    
    def _normalize_unicode(self, text: str) -> str:
        """Normalize Unicode to NFC form."""
        return unicodedata.normalize('NFC', text)
    
    def _fix_ocr_errors(self, text: str) -> str:
        """Fix common OCR character errors."""
        for old, new in self.OCR_CORRECTIONS.items():
            text = text.replace(old, new)
        return text
    
    def _fix_hyphenation(self, text: str) -> str:
        """Fix word hyphenation at line breaks."""
        # Fix hyphenated words at end of line
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
        
        # Fix words split across lines without hyphen (common OCR issue)
        # Only if the parts look like word fragments
        text = re.sub(
            r'([a-z]{2,})\n([a-z]{2,})',
            lambda m: m.group(1) + m.group(2) if self._looks_like_word(m.group(1) + m.group(2)) else m.group(0),
            text
        )
        
        return text
    
    def _looks_like_word(self, text: str) -> bool:
        """Check if text looks like a valid word."""
        # Simple heuristic: should be all letters, reasonable length
        return text.isalpha() and 4 <= len(text) <= 20
    
    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace characters."""
        # Replace multiple spaces with single space
        text = re.sub(r'[ \t]+', ' ', text)
        
        # Normalize line endings
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # Remove trailing whitespace from lines
        text = re.sub(r' +\n', '\n', text)
        
        # Collapse multiple blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text
    
    def _remove_boilerplate(self, text: str) -> str:
        """Remove common boilerplate text."""
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            stripped = line.strip()
            
            # Skip very short lines that are likely noise
            if len(stripped) < self.min_line_length:
                if stripped:  # Keep empty lines
                    continue
            
            # Check boilerplate patterns
            is_boilerplate = False
            for pattern in self._boilerplate_regex:
                if pattern.match(stripped):
                    is_boilerplate = True
                    break
            
            if not is_boilerplate:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def extract_clean_sentences(self, text: str) -> List[str]:
        """Extract clean sentences from text."""
        text = self.normalize(text)
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Clean and filter
        clean_sentences = []
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) >= 10:  # Minimum sentence length
                clean_sentences.append(sentence)
        
        return clean_sentences


class TableExtractor:
    """Placeholder for table extraction utilities."""
    pass


class FormExtractor:
    """Placeholder for form extraction utilities."""
    pass
