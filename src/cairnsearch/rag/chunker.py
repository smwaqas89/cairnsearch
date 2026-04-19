"""Document chunking for RAG pipeline."""
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Chunk:
    """A chunk of document text."""
    id: str                    # Unique chunk ID
    doc_id: int               # Parent document ID
    file_path: str            # Source file path
    filename: str             # Source filename
    content: str              # Chunk text
    chunk_index: int          # Position in document
    start_char: int           # Start position in original text
    end_char: int             # End position in original text
    metadata: dict = field(default_factory=dict)


class DocumentChunker:
    """
    Split documents into overlapping chunks for RAG.
    
    Uses semantic boundaries (paragraphs, sentences) when possible,
    with a fallback to character-based splitting.
    """

    def __init__(
        self,
        chunk_size: int = 500,        # Target tokens per chunk
        chunk_overlap: int = 50,       # Overlap between chunks
        min_chunk_size: int = 100,     # Don't create tiny chunks
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        # Rough approximation: 1 token ≈ 4 characters
        self.chars_per_token = 4

    def chunk_document(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> list[Chunk]:
        """
        Split document into chunks.
        
        Args:
            doc_id: Document ID from database
            file_path: Source file path
            filename: Source filename
            content: Full document text
            metadata: Additional metadata to include
            
        Returns:
            List of Chunk objects
        """
        if not content:
            return []
        
        # Clean and normalize content
        content = content.strip()
        if not content:
            return []
        
        # For very short content, create a single chunk
        if len(content) < self.min_chunk_size * self.chars_per_token:
            if len(content) >= 20:  # At least 20 chars
                return [self._create_chunk(
                    doc_id, file_path, filename, content,
                    0, 0, len(content), metadata
                )]
            return []

        # Calculate character limits
        max_chars = self.chunk_size * self.chars_per_token
        overlap_chars = self.chunk_overlap * self.chars_per_token
        min_chars = 50  # Lower minimum to capture small documents

        # Split into paragraphs first
        paragraphs = self._split_paragraphs(content)
        
        # Build chunks from paragraphs
        chunks = []
        current_chunk = ""
        current_start = 0
        char_position = 0

        for para in paragraphs:
            para_len = len(para)
            
            # If single paragraph is too long, split it further
            if para_len > max_chars:
                # Save current chunk if exists
                if current_chunk.strip():
                    chunks.append(self._create_chunk(
                        doc_id, file_path, filename, current_chunk.strip(),
                        len(chunks), current_start, char_position, metadata
                    ))
                
                # Split long paragraph into sentences
                sentence_chunks = self._split_long_text(para, max_chars, overlap_chars)
                for sent_chunk in sentence_chunks:
                    chunks.append(self._create_chunk(
                        doc_id, file_path, filename, sent_chunk.strip(),
                        len(chunks), char_position, char_position + len(sent_chunk), metadata
                    ))
                
                current_chunk = ""
                current_start = char_position + para_len
                char_position += para_len
                continue

            # Check if adding paragraph exceeds limit
            if len(current_chunk) + para_len > max_chars:
                # Save current chunk
                if current_chunk.strip() and len(current_chunk.strip()) >= min_chars:
                    chunks.append(self._create_chunk(
                        doc_id, file_path, filename, current_chunk.strip(),
                        len(chunks), current_start, char_position, metadata
                    ))
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap(current_chunk, overlap_chars)
                current_chunk = overlap_text + para
                current_start = char_position - len(overlap_text)
            else:
                current_chunk += para
            
            char_position += para_len

        # Don't forget the last chunk
        if current_chunk.strip() and len(current_chunk.strip()) >= min_chars:
            chunks.append(self._create_chunk(
                doc_id, file_path, filename, current_chunk.strip(),
                len(chunks), current_start, char_position, metadata
            ))

        return chunks

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs, preserving boundaries."""
        paragraphs = re.split(r'\n\s*\n', text)
        result = []
        for i, para in enumerate(paragraphs):
            result.append(para)
            if i < len(paragraphs) - 1:
                result[-1] += "\n\n"
        return result

    def _split_long_text(self, text: str, max_chars: int, overlap_chars: int) -> list[str]:
        """Split long text by sentences, then by characters if needed."""
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current = ""
        
        for sentence in sentences:
            if len(sentence) > max_chars:
                if current:
                    chunks.append(current)
                    current = ""
                
                for i in range(0, len(sentence), max_chars - overlap_chars):
                    chunk = sentence[i:i + max_chars]
                    chunks.append(chunk)
            elif len(current) + len(sentence) > max_chars:
                chunks.append(current)
                current = sentence
            else:
                current += " " + sentence if current else sentence
        
        if current:
            chunks.append(current)
        
        return chunks

    def _get_overlap(self, text: str, overlap_chars: int) -> str:
        """Get overlap text from end of previous chunk."""
        if len(text) <= overlap_chars:
            return text
        
        overlap = text[-overlap_chars:]
        space_pos = overlap.find(" ")
        if space_pos > 0:
            overlap = overlap[space_pos + 1:]
        
        return overlap

    def _create_chunk(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
        content: str,
        index: int,
        start: int,
        end: int,
        metadata: Optional[dict],
    ) -> Chunk:
        """Create a Chunk object with unique ID."""
        chunk_id = f"{doc_id}_{index}"
        return Chunk(
            id=chunk_id,
            doc_id=doc_id,
            file_path=file_path,
            filename=filename,
            content=content,
            chunk_index=index,
            start_char=start,
            end_char=end,
            metadata=metadata or {},
        )
