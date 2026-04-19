"""Query parser for search syntax."""
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class TokenType(Enum):
    """Query token types."""
    WORD = auto()
    PHRASE = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    FIELD = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF = auto()


@dataclass
class Token:
    """Query token."""
    type: TokenType
    value: str = ""
    field_name: Optional[str] = None


@dataclass
class ParsedQuery:
    """Parsed search query."""
    fts_query: str = ""  # FTS5 MATCH query
    filters: dict = field(default_factory=dict)  # Non-FTS filters
    
    # Date filters
    after_date: Optional[str] = None
    before_date: Optional[str] = None
    year: Optional[int] = None
    
    # Field filters
    file_type: Optional[str] = None
    author: Optional[str] = None
    
    @property
    def has_fts_query(self) -> bool:
        return bool(self.fts_query.strip())
    
    @property
    def has_date_filters(self) -> bool:
        return self.after_date or self.before_date or self.year


def sanitize_fts_query(query: str) -> str:
    """
    Sanitize a query string for FTS5 MATCH clause.
    
    FTS5 has special syntax characters that cause syntax errors if not handled:
    - Quotes must be balanced
    - Colons are field specifiers
    - Parentheses must be balanced
    - Special chars like ?, *, ^, $, etc. can cause issues
    """
    if not query:
        return ""
    
    # Characters that have special meaning in FTS5 and should be removed/escaped
    # ? is particularly problematic as it's not a valid FTS5 operator
    special_chars = ['?', '*', '^', '$', '!', '@', '#', '%', '&', '=', '+', 
                     '[', ']', '{', '}', '|', '\\', '/', '<', '>', '`', '~']
    
    result = query
    for char in special_chars:
        result = result.replace(char, ' ')
    
    # Clean up multiple spaces
    result = ' '.join(result.split())
    
    return result


class QueryLexer:
    """Tokenize search query."""

    KEYWORDS = {"AND", "OR", "NOT"}
    FIELD_PATTERN = re.compile(r'^([a-zA-Z_]+):(.+)$')
    
    def __init__(self, query: str):
        self.query = query
        self.pos = 0
        self.length = len(query)

    def tokenize(self) -> list[Token]:
        """Tokenize query string."""
        tokens = []
        
        while self.pos < self.length:
            self._skip_whitespace()
            if self.pos >= self.length:
                break
            
            char = self.query[self.pos]
            
            if char == '"':
                tokens.append(self._read_phrase())
            elif char == '(':
                tokens.append(Token(TokenType.LPAREN, "("))
                self.pos += 1
            elif char == ')':
                tokens.append(Token(TokenType.RPAREN, ")"))
                self.pos += 1
            else:
                tokens.append(self._read_word())
        
        tokens.append(Token(TokenType.EOF))
        return tokens

    def _skip_whitespace(self) -> None:
        while self.pos < self.length and self.query[self.pos].isspace():
            self.pos += 1

    def _read_phrase(self) -> Token:
        """Read quoted phrase."""
        self.pos += 1  # Skip opening quote
        start = self.pos
        
        while self.pos < self.length and self.query[self.pos] != '"':
            self.pos += 1
        
        value = self.query[start:self.pos]
        
        if self.pos < self.length:
            self.pos += 1  # Skip closing quote
        
        return Token(TokenType.PHRASE, value)

    def _read_word(self) -> Token:
        """Read word or keyword."""
        start = self.pos
        
        while self.pos < self.length and not self.query[self.pos].isspace() and self.query[self.pos] not in '()"':
            self.pos += 1
        
        value = self.query[start:self.pos]
        upper = value.upper()
        
        # Check for keywords
        if upper in self.KEYWORDS:
            return Token(TokenType[upper], value)
        
        # Check for field:value
        match = self.FIELD_PATTERN.match(value)
        if match:
            field_name = match.group(1).lower()
            field_value = match.group(2)
            return Token(TokenType.FIELD, field_value, field_name=field_name)
        
        return Token(TokenType.WORD, value)


class QueryParser:
    """Parse search queries into FTS5 queries and filters."""

    # Fields that go into FTS5 search
    FTS_FIELDS = {"filename", "content"}
    
    # Fields that become SQL filters
    FILTER_FIELDS = {"type", "author", "after", "before", "year"}

    def __init__(self):
        self.tokens: list[Token] = []
        self.pos = 0

    def parse(self, query: str) -> ParsedQuery:
        """Parse query string into ParsedQuery."""
        self.tokens = QueryLexer(query).tokenize()
        self.pos = 0
        
        result = ParsedQuery()
        fts_parts = []
        
        while not self._is_at_end():
            token = self._current()
            
            if token.type == TokenType.FIELD:
                self._handle_field(token, result, fts_parts)
            elif token.type == TokenType.PHRASE:
                fts_parts.append(f'"{token.value}"')
            elif token.type == TokenType.WORD:
                fts_parts.append(token.value)
            elif token.type in (TokenType.AND, TokenType.OR, TokenType.NOT):
                fts_parts.append(token.type.name)
            elif token.type == TokenType.LPAREN:
                fts_parts.append("(")
            elif token.type == TokenType.RPAREN:
                fts_parts.append(")")
            
            self._advance()
        
        result.fts_query = sanitize_fts_query(" ".join(fts_parts))
        return result

    def _handle_field(self, token: Token, result: ParsedQuery, fts_parts: list) -> None:
        """Handle field:value token."""
        field = token.field_name
        value = token.value
        
        if field in self.FTS_FIELDS:
            # FTS5 column search
            fts_parts.append(f"{field}:{value}")
        elif field == "type":
            result.file_type = value.lower().lstrip(".")
        elif field == "author":
            result.author = value
        elif field == "after":
            result.after_date = self._normalize_date(value)
        elif field == "before":
            result.before_date = self._normalize_date(value)
        elif field == "year":
            try:
                result.year = int(value)
            except ValueError:
                pass

    def _normalize_date(self, value: str) -> Optional[str]:
        """Normalize date string to ISO format."""
        # Handle YYYY format
        if re.match(r'^\d{4}$', value):
            return f"{value}-01-01"
        
        # Handle YYYY-MM-DD format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', value):
            return value
        
        # Try to parse other formats
        try:
            from dateutil.parser import parse
            parsed = parse(value)
            return parsed.date().isoformat()
        except:
            return None

    def _current(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        token = self._current()
        self.pos += 1
        return token

    def _is_at_end(self) -> bool:
        return self._current().type == TokenType.EOF


def parse_query(query: str) -> ParsedQuery:
    """Parse a search query string."""
    return QueryParser().parse(query)
