"""Table extraction and processing utilities."""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import re
import logging


logger = logging.getLogger(__name__)


@dataclass
class ExtractedTable:
    """Represents an extracted table."""
    table_id: str
    source: str  # pdf, excel, html, text
    page_num: Optional[int] = None
    sheet_name: Optional[str] = None
    
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    
    # Position
    bounding_box: Optional[Dict[str, float]] = None
    start_row: Optional[int] = None
    end_row: Optional[int] = None
    
    # Quality
    confidence: float = 1.0
    has_merged_cells: bool = False
    
    def to_text(self) -> str:
        """Convert table to readable text."""
        lines = []
        if self.headers:
            lines.append(" | ".join(str(h) for h in self.headers))
            lines.append("-" * 40)
        for row in self.rows:
            lines.append(" | ".join(str(cell) if cell is not None else "" for cell in row))
        return "\n".join(lines)
    
    def to_markdown(self) -> str:
        """Convert table to markdown format."""
        lines = []
        if self.headers:
            lines.append("| " + " | ".join(str(h) for h in self.headers) + " |")
            lines.append("| " + " | ".join("---" for _ in self.headers) + " |")
        for row in self.rows:
            lines.append("| " + " | ".join(str(cell) if cell is not None else "" for cell in row) + " |")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "table_id": self.table_id,
            "source": self.source,
            "page_num": self.page_num,
            "sheet_name": self.sheet_name,
            "headers": self.headers,
            "rows": self.rows,
            "bounding_box": self.bounding_box,
            "confidence": self.confidence,
        }


class TableExtractor:
    """
    Table extraction utilities for various sources.
    """
    
    def extract_from_text(self, text: str) -> List[ExtractedTable]:
        """
        Extract tables from plain text using pattern matching.
        Detects ASCII/Unicode tables and delimiter-separated data.
        """
        tables = []
        
        # Try to detect delimiter-separated tables
        delim_tables = self._extract_delimiter_tables(text)
        tables.extend(delim_tables)
        
        # Try to detect ASCII art tables
        ascii_tables = self._extract_ascii_tables(text)
        tables.extend(ascii_tables)
        
        return tables
    
    def _extract_delimiter_tables(self, text: str) -> List[ExtractedTable]:
        """Extract tables using common delimiters."""
        tables = []
        
        # Common delimiters to try
        delimiters = ['\t', '|', ';', ',']
        
        lines = text.split('\n')
        
        for delim in delimiters:
            table_lines = []
            current_col_count = 0
            
            for line in lines:
                cells = line.split(delim)
                
                if len(cells) >= 2:
                    # Check if this could be part of a table
                    if current_col_count == 0:
                        current_col_count = len(cells)
                        table_lines = [cells]
                    elif len(cells) == current_col_count:
                        table_lines.append(cells)
                    else:
                        # Column count changed, save current table if valid
                        if len(table_lines) >= 3:
                            tables.append(self._create_table_from_rows(
                                table_lines, f"text_delim_{len(tables)}"
                            ))
                        table_lines = [cells]
                        current_col_count = len(cells)
                else:
                    if len(table_lines) >= 3:
                        tables.append(self._create_table_from_rows(
                            table_lines, f"text_delim_{len(tables)}"
                        ))
                    table_lines = []
                    current_col_count = 0
            
            # Don't forget last table
            if len(table_lines) >= 3:
                tables.append(self._create_table_from_rows(
                    table_lines, f"text_delim_{len(tables)}"
                ))
        
        return tables
    
    def _extract_ascii_tables(self, text: str) -> List[ExtractedTable]:
        """Extract ASCII art tables."""
        tables = []
        
        # Pattern for table borders
        border_pattern = r'^[\s]*[+|][-+|]+[+|][\s]*$'
        
        lines = text.split('\n')
        table_start = None
        table_lines = []
        
        for i, line in enumerate(lines):
            if re.match(border_pattern, line):
                if table_start is None:
                    table_start = i
                table_lines.append(line)
            elif table_start is not None:
                # Check if this is a data row
                if '|' in line:
                    table_lines.append(line)
                else:
                    # End of table
                    if len(table_lines) >= 3:
                        table = self._parse_ascii_table(table_lines, f"ascii_{len(tables)}")
                        if table:
                            tables.append(table)
                    table_start = None
                    table_lines = []
        
        return tables
    
    def _parse_ascii_table(self, lines: List[str], table_id: str) -> Optional[ExtractedTable]:
        """Parse an ASCII art table."""
        data_rows = []
        
        for line in lines:
            if '|' in line and not re.match(r'^[\s]*[+|][-+|]+[+|][\s]*$', line):
                # Data row
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                if cells:
                    data_rows.append(cells)
        
        if len(data_rows) < 2:
            return None
        
        return ExtractedTable(
            table_id=table_id,
            source="text",
            headers=data_rows[0],
            rows=data_rows[1:],
            confidence=0.8,
        )
    
    def _create_table_from_rows(
        self,
        rows: List[List[str]],
        table_id: str,
    ) -> ExtractedTable:
        """Create table from row data."""
        # Clean cells
        cleaned_rows = []
        for row in rows:
            cleaned_row = [cell.strip() for cell in row]
            cleaned_rows.append(cleaned_row)
        
        # First row as headers
        headers = cleaned_rows[0]
        data_rows = cleaned_rows[1:]
        
        return ExtractedTable(
            table_id=table_id,
            source="text",
            headers=headers,
            rows=data_rows,
            confidence=0.7,
        )
    
    def merge_tables(self, tables: List[ExtractedTable]) -> List[ExtractedTable]:
        """Merge related tables (e.g., split across pages)."""
        if len(tables) <= 1:
            return tables
        
        merged = []
        current = None
        
        for table in tables:
            if current is None:
                current = table
            elif self._tables_compatible(current, table):
                # Merge rows
                current.rows.extend(table.rows)
            else:
                merged.append(current)
                current = table
        
        if current:
            merged.append(current)
        
        return merged
    
    def _tables_compatible(self, t1: ExtractedTable, t2: ExtractedTable) -> bool:
        """Check if two tables can be merged."""
        # Same number of columns
        if len(t1.headers) != len(t2.headers):
            return False
        
        # Similar headers
        for h1, h2 in zip(t1.headers, t2.headers):
            if h1.lower() != h2.lower():
                return False
        
        return True
