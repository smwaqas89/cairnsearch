"""Generate highlighted snippets from search results."""
import re
from typing import Optional

from cairnsearch.config import get_config


class SnippetGenerator:
    """Generate highlighted text snippets from search results."""

    def __init__(
        self,
        snippet_length: Optional[int] = None,
        highlight_tag: Optional[str] = None,
    ):
        config = get_config()
        self.snippet_length = snippet_length or config.search.snippet_length
        self.highlight_tag = highlight_tag or config.search.highlight_tag

    def generate(self, text: str, query_terms: list[str], max_snippets: int = 3) -> list[str]:
        """
        Generate highlighted snippets containing query terms.
        
        Args:
            text: Full document text
            query_terms: Search terms to highlight
            max_snippets: Maximum number of snippets to return
            
        Returns:
            List of text snippets with highlighted terms
        """
        if not text or not query_terms:
            return []
        
        # Clean and normalize query terms
        terms = self._normalize_terms(query_terms)
        if not terms:
            return []
        
        # Build regex pattern for all terms
        pattern = self._build_pattern(terms)
        
        # Find all match positions
        matches = list(pattern.finditer(text))
        if not matches:
            # No matches, return start of document
            return [self._truncate(text, self.snippet_length)]
        
        # Generate snippets around matches
        snippets = []
        used_ranges = []
        
        for match in matches:
            if len(snippets) >= max_snippets:
                break
            
            start_pos = match.start()
            end_pos = match.end()
            
            # Check if this position overlaps with existing snippets
            if self._overlaps(start_pos, end_pos, used_ranges):
                continue
            
            # Extract snippet context
            snippet = self._extract_snippet(text, start_pos, end_pos)
            
            # Highlight all terms in snippet
            highlighted = self._highlight(snippet, pattern)
            
            snippets.append(highlighted)
            used_ranges.append((
                max(0, start_pos - self.snippet_length),
                min(len(text), end_pos + self.snippet_length)
            ))
        
        return snippets

    def _normalize_terms(self, query_terms: list[str]) -> list[str]:
        """Normalize and clean query terms."""
        normalized = []
        skip_words = {"AND", "OR", "NOT", ""}
        
        for term in query_terms:
            # Remove quotes
            term = term.strip('"\'')
            # Skip boolean operators
            if term.upper() in skip_words:
                continue
            # Skip field prefixes
            if ":" in term:
                _, term = term.split(":", 1)
            if term:
                normalized.append(term)
        
        return normalized

    def _build_pattern(self, terms: list[str]) -> re.Pattern:
        """Build regex pattern for matching terms."""
        # Escape special regex characters
        escaped = [re.escape(term) for term in terms]
        # Create alternation pattern with word boundaries
        pattern_str = r'\b(' + '|'.join(escaped) + r')\b'
        return re.compile(pattern_str, re.IGNORECASE)

    def _overlaps(self, start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
        """Check if position overlaps with existing ranges."""
        for r_start, r_end in ranges:
            if start < r_end and end > r_start:
                return True
        return False

    def _extract_snippet(self, text: str, match_start: int, match_end: int) -> str:
        """Extract snippet context around match."""
        half_length = self.snippet_length // 2
        
        # Calculate snippet boundaries
        start = max(0, match_start - half_length)
        end = min(len(text), match_end + half_length)
        
        # Adjust to word boundaries
        if start > 0:
            # Find previous space
            space_pos = text.rfind(" ", max(0, start - 20), start)
            if space_pos != -1:
                start = space_pos + 1
        
        if end < len(text):
            # Find next space
            space_pos = text.find(" ", end, min(len(text), end + 20))
            if space_pos != -1:
                end = space_pos
        
        snippet = text[start:end]
        
        # Add ellipsis
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."
        
        return snippet

    def _highlight(self, text: str, pattern: re.Pattern) -> str:
        """Highlight matches in text."""
        tag = self.highlight_tag
        
        def replacer(match):
            return f"<{tag}>{match.group(0)}</{tag}>"
        
        return pattern.sub(replacer, text)

    def _truncate(self, text: str, length: int) -> str:
        """Truncate text to length at word boundary."""
        if len(text) <= length:
            return text
        
        # Find last space before length
        space_pos = text.rfind(" ", 0, length)
        if space_pos == -1:
            return text[:length] + "..."
        
        return text[:space_pos] + "..."


def extract_query_terms(query: str) -> list[str]:
    """Extract searchable terms from query string."""
    terms = []
    
    # Extract quoted phrases
    phrase_pattern = re.compile(r'"([^"]+)"')
    for match in phrase_pattern.finditer(query):
        terms.append(match.group(1))
    
    # Remove phrases from query
    remaining = phrase_pattern.sub("", query)
    
    # Extract words (skip operators and field prefixes)
    skip_words = {"and", "or", "not"}
    for word in remaining.split():
        word = word.strip()
        if not word:
            continue
        if word.lower() in skip_words:
            continue
        if ":" in word:
            # Check if it's a searchable field
            field, value = word.split(":", 1)
            if field.lower() in ("filename", "content"):
                terms.append(value)
            continue
        terms.append(word)
    
    return terms
