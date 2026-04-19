"""Semantic chunker with intelligent document splitting."""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

from cairnsearch.core.models import ChunkMetadata, GuardrailLimits, PageInfo
from cairnsearch.core.exceptions import ChunkingError, GuardrailExceeded
from cairnsearch.core.guardrails import GuardrailEnforcer


logger = logging.getLogger(__name__)


class ChunkType(Enum):
    """Types of chunks."""
    TEXT = "text"
    TABLE = "table"
    FORM_FIELD = "form_field"
    OCR = "ocr"
    HEADING = "heading"
    LIST = "list"
    CODE = "code"


@dataclass
class SemanticChunk:
    """A semantically meaningful chunk."""
    id: str
    doc_id: int
    file_path: str
    filename: str
    content: str
    chunk_type: ChunkType
    chunk_index: int
    
    # Position info
    page_num: Optional[int] = None
    section: Optional[str] = None
    start_char: int = 0
    end_char: int = 0
    
    # OCR info
    is_ocr: bool = False
    ocr_confidence: Optional[float] = None
    
    # Table info
    table_id: Optional[str] = None
    
    # Excel info
    sheet_name: Optional[str] = None
    row_numbers: Optional[List[int]] = None
    
    # Token counts
    token_count: int = 0
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_chunk_metadata(self) -> ChunkMetadata:
        """Convert to ChunkMetadata."""
        return ChunkMetadata(
            chunk_id=self.id,
            doc_id=self.doc_id,
            file_path=self.file_path,
            filename=self.filename,
            page_num=self.page_num,
            section=self.section,
            chunk_type=self.chunk_type.value,
            ocr_confidence=self.ocr_confidence,
            is_ocr=self.is_ocr,
            table_id=self.table_id,
            row_numbers=self.row_numbers,
            sheet_name=self.sheet_name,
            start_char=self.start_char,
            end_char=self.end_char,
            token_count=self.token_count,
        )


class SemanticChunker:
    """
    Semantic document chunker with:
    - Section/heading detection
    - List preservation
    - Table separation
    - OCR chunk handling
    - Token-aware splitting
    - Guardrail enforcement
    """
    
    CHARS_PER_TOKEN = 4
    
    HEADING_PATTERNS = [
        r'^#{1,6}\s+(.+)$',
        r'^([A-Z][A-Z\s]+)$',
        r'^\d+\.\s+(.+)$',
        r'^[IVXLCDM]+\.\s+(.+)$',
        r'^(?:Chapter|Section|Part)\s+\d+',
    ]
    
    LIST_PATTERNS = [
        r'^\s*[-*•]\s+',
        r'^\s*\d+[.)]\s+',
        r'^\s*[a-z][.)]\s+',
    ]
    
    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        min_chunk_size: int = 50,
        max_chunk_size: int = 2000,
        limits: Optional[GuardrailLimits] = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.limits = limits or GuardrailLimits()
        self.guardrails = GuardrailEnforcer(self.limits)
    
    def chunk_document(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        content: str,
        pages: Optional[List[PageInfo]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[SemanticChunk]:
        """Chunk a document semantically."""
        if not content:
            return []
        
        self.guardrails.start_processing()
        self.guardrails.enforce(self.guardrails.check_char_count(len(content)))
        
        chunks: List[SemanticChunk] = []
        
        if pages:
            chunks = self._chunk_with_pages(doc_id, file_path, filename, pages, metadata)
        else:
            chunks = self._chunk_by_structure(doc_id, file_path, filename, content, metadata)
        
        self.guardrails.enforce(self.guardrails.check_chunk_count(len(chunks)))
        
        return chunks
    
    def _chunk_with_pages(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        pages: List[PageInfo],
        metadata: Optional[Dict[str, Any]],
    ) -> List[SemanticChunk]:
        """Chunk document with page awareness."""
        chunks = []
        chunk_index = 0
        
        for page in pages:
            if page.tables:
                for table in page.tables:
                    table_chunk = self._create_table_chunk(
                        doc_id, file_path, filename, table, page.page_num, chunk_index, metadata
                    )
                    if table_chunk:
                        chunks.append(table_chunk)
                        chunk_index += 1
            
            if page.key_value_pairs:
                form_chunk = self._create_form_chunk(
                    doc_id, file_path, filename, page.key_value_pairs, page.page_num, chunk_index, metadata
                )
                if form_chunk:
                    chunks.append(form_chunk)
                    chunk_index += 1
            
            page_chunks = self._chunk_text(
                doc_id, file_path, filename, page.text, chunk_index,
                page_num=page.page_num,
                is_ocr=page.page_type.value in ['scanned', 'ocr'],
                ocr_confidence=page.ocr_confidence,
                metadata=metadata,
            )
            chunks.extend(page_chunks)
            chunk_index += len(page_chunks)
            
            if len(chunks) > self.limits.max_chunks_per_page * page.page_num:
                break
        
        return chunks
    
    def _chunk_by_structure(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        content: str,
        metadata: Optional[Dict[str, Any]],
    ) -> List[SemanticChunk]:
        """Chunk document by semantic structure."""
        chunks = []
        chunk_index = 0
        sections = self._split_by_sections(content)
        
        for section_title, section_content in sections:
            section_chunks = self._chunk_text(
                doc_id, file_path, filename, section_content, chunk_index,
                section=section_title, metadata=metadata
            )
            chunks.extend(section_chunks)
            chunk_index += len(section_chunks)
        
        return chunks
    
    def _split_by_sections(self, content: str) -> List[Tuple[Optional[str], str]]:
        """Split content by section headings."""
        sections = []
        current_section = None
        current_content = []
        
        for line in content.split('\n'):
            is_heading = False
            heading_text = None
            
            for pattern in self.HEADING_PATTERNS:
                match = re.match(pattern, line.strip(), re.MULTILINE)
                if match:
                    is_heading = True
                    heading_text = match.group(1) if match.groups() else line.strip()
                    break
            
            if is_heading:
                if current_content:
                    sections.append((current_section, '\n'.join(current_content)))
                current_section = heading_text
                current_content = [line]
            else:
                current_content.append(line)
        
        if current_content:
            sections.append((current_section, '\n'.join(current_content)))
        
        if not sections:
            sections = [(None, content)]
        
        return sections
    
    def _chunk_text(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        text: str,
        start_index: int,
        page_num: Optional[int] = None,
        section: Optional[str] = None,
        is_ocr: bool = False,
        ocr_confidence: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[SemanticChunk]:
        """Chunk text content."""
        if not text or not text.strip():
            return []
        
        chunks = []
        max_chars = self.chunk_size * self.CHARS_PER_TOKEN
        overlap_chars = self.chunk_overlap * self.CHARS_PER_TOKEN
        min_chars = self.min_chunk_size * self.CHARS_PER_TOKEN
        
        paragraphs = re.split(r'\n\s*\n', text)
        current_chunk = ""
        current_start = 0
        char_pos = 0
        
        for para in paragraphs:
            para_len = len(para)
            
            if para_len > max_chars:
                if current_chunk.strip() and len(current_chunk.strip()) >= min_chars:
                    chunks.append(self._create_text_chunk(
                        doc_id, file_path, filename, current_chunk.strip(),
                        start_index + len(chunks), current_start, char_pos,
                        page_num, section, is_ocr, ocr_confidence, metadata
                    ))
                
                sub_chunks = self._split_long_text(para, max_chars, overlap_chars)
                for sub in sub_chunks:
                    if sub.strip() and len(sub.strip()) >= min_chars:
                        chunks.append(self._create_text_chunk(
                            doc_id, file_path, filename, sub.strip(),
                            start_index + len(chunks), char_pos, char_pos + len(sub),
                            page_num, section, is_ocr, ocr_confidence, metadata
                        ))
                
                current_chunk = ""
                current_start = char_pos + para_len
                char_pos += para_len
                continue
            
            if len(current_chunk) + para_len > max_chars:
                if current_chunk.strip() and len(current_chunk.strip()) >= min_chars:
                    chunks.append(self._create_text_chunk(
                        doc_id, file_path, filename, current_chunk.strip(),
                        start_index + len(chunks), current_start, char_pos,
                        page_num, section, is_ocr, ocr_confidence, metadata
                    ))
                
                overlap = current_chunk[-overlap_chars:] if len(current_chunk) > overlap_chars else current_chunk
                space = overlap.find(' ')
                if space > 0:
                    overlap = overlap[space + 1:]
                
                current_chunk = overlap + para
                current_start = char_pos - len(overlap)
            else:
                current_chunk += "\n\n" + para if current_chunk else para
            
            char_pos += para_len + 2
        
        if current_chunk.strip() and len(current_chunk.strip()) >= min_chars:
            chunks.append(self._create_text_chunk(
                doc_id, file_path, filename, current_chunk.strip(),
                start_index + len(chunks), current_start, char_pos,
                page_num, section, is_ocr, ocr_confidence, metadata
            ))
        
        return chunks
    
    def _split_long_text(self, text: str, max_chars: int, overlap_chars: int) -> List[str]:
        """Split long text by sentences."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        chunks = []
        current = ""
        
        for sentence in sentences:
            if len(sentence) > max_chars:
                if current:
                    chunks.append(current)
                for i in range(0, len(sentence), max_chars - overlap_chars):
                    chunks.append(sentence[i:i + max_chars])
                current = ""
            elif len(current) + len(sentence) > max_chars:
                chunks.append(current)
                current = sentence
            else:
                current += " " + sentence if current else sentence
        
        if current:
            chunks.append(current)
        
        return chunks
    
    def _create_text_chunk(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        content: str,
        chunk_index: int,
        start_char: int,
        end_char: int,
        page_num: Optional[int],
        section: Optional[str],
        is_ocr: bool,
        ocr_confidence: Optional[float],
        metadata: Optional[Dict[str, Any]],
    ) -> SemanticChunk:
        """Create a text chunk."""
        return SemanticChunk(
            id=f"{doc_id}_{chunk_index}",
            doc_id=doc_id,
            file_path=file_path,
            filename=filename,
            content=content,
            chunk_type=ChunkType.OCR if is_ocr else ChunkType.TEXT,
            chunk_index=chunk_index,
            page_num=page_num,
            section=section,
            start_char=start_char,
            end_char=end_char,
            is_ocr=is_ocr,
            ocr_confidence=ocr_confidence,
            token_count=len(content) // self.CHARS_PER_TOKEN,
            metadata=metadata or {},
        )
    
    def _create_table_chunk(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        table_data: Dict[str, Any],
        page_num: int,
        chunk_index: int,
        metadata: Optional[Dict[str, Any]],
    ) -> Optional[SemanticChunk]:
        """Create a chunk for a table."""
        table_id = table_data.get("table_id", f"table_{page_num}_{chunk_index}")
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        
        lines = []
        if headers:
            lines.append(" | ".join(str(h) for h in headers))
            lines.append("-" * 40)
        for row in rows[:100]:
            lines.append(" | ".join(str(cell) for cell in row))
        
        content = "\n".join(lines)
        if not content.strip():
            return None
        
        return SemanticChunk(
            id=f"{doc_id}_{chunk_index}_table",
            doc_id=doc_id,
            file_path=file_path,
            filename=filename,
            content=content,
            chunk_type=ChunkType.TABLE,
            chunk_index=chunk_index,
            page_num=page_num,
            table_id=table_id,
            token_count=len(content) // self.CHARS_PER_TOKEN,
            metadata={"table_headers": headers, "row_count": len(rows), **(metadata or {})},
        )
    
    def _create_form_chunk(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        form_fields: List[Dict[str, Any]],
        page_num: int,
        chunk_index: int,
        metadata: Optional[Dict[str, Any]],
    ) -> Optional[SemanticChunk]:
        """Create a chunk for form fields."""
        if not form_fields:
            return None
        
        lines = []
        for field in form_fields[:50]:
            key = field.get("key", "")
            value = field.get("value", "")
            if key and value:
                lines.append(f"{key}: {value}")
        
        content = "\n".join(lines)
        if not content.strip():
            return None
        
        return SemanticChunk(
            id=f"{doc_id}_{chunk_index}_form",
            doc_id=doc_id,
            file_path=file_path,
            filename=filename,
            content=content,
            chunk_type=ChunkType.FORM_FIELD,
            chunk_index=chunk_index,
            page_num=page_num,
            token_count=len(content) // self.CHARS_PER_TOKEN,
            metadata={"field_count": len(form_fields), **(metadata or {})},
        )
    
    def estimate_chunks(self, content: str) -> int:
        """Estimate number of chunks for content."""
        if not content:
            return 0
        chunk_chars = self.chunk_size * self.CHARS_PER_TOKEN
        effective = chunk_chars - (self.chunk_overlap * self.CHARS_PER_TOKEN)
        return max(1, (len(content) + effective - 1) // effective)
