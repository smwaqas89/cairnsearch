"""Deduplication manager for idempotent indexing."""
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple, Set
import sqlite3

from cairnsearch.config import get_config
from .models import DocumentVersion


logger = logging.getLogger(__name__)


@dataclass
class ContentFingerprint:
    """Fingerprint for content deduplication."""
    content_hash: str
    chunk_hashes: List[str]
    token_count: int
    chunk_count: int
    
    def to_dict(self) -> dict:
        return {
            "content_hash": self.content_hash,
            "chunk_hashes": self.chunk_hashes,
            "token_count": self.token_count,
            "chunk_count": self.chunk_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ContentFingerprint":
        return cls(**data)


class DeduplicationManager:
    """
    Manages deduplication for idempotent indexing.
    
    Uses file hash + content hash to detect duplicates and
    track document versions.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        config = get_config()
        if db_path is None:
            db_path = config.get_data_dir() / "dedup.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize deduplication database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        
        conn.executescript("""
            -- Document versions
            CREATE TABLE IF NOT EXISTS document_versions (
                file_path TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT
            );
            
            -- Chunk hashes for deduplication
            CREATE TABLE IF NOT EXISTS chunk_hashes (
                chunk_hash TEXT PRIMARY KEY,
                doc_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                created_at TEXT NOT NULL
            );
            
            -- Content hashes for cross-document dedup
            CREATE TABLE IF NOT EXISTS content_hashes (
                content_hash TEXT PRIMARY KEY,
                file_paths TEXT NOT NULL,  -- JSON array
                first_seen TEXT NOT NULL,
                occurrence_count INTEGER DEFAULT 1
            );
            
            -- Indexes
            CREATE INDEX IF NOT EXISTS idx_versions_file_hash ON document_versions(file_hash);
            CREATE INDEX IF NOT EXISTS idx_versions_content_hash ON document_versions(content_hash);
            CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunk_hashes(doc_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON chunk_hashes(file_path);
        """)
        
        conn.commit()
        conn.close()
    
    def compute_file_hash(self, file_path: Path, algorithm: str = "sha256") -> str:
        """Compute hash of file contents."""
        hasher = hashlib.new(algorithm)
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def compute_content_hash(self, content: str) -> str:
        """Compute hash of extracted content."""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def compute_chunk_hash(self, chunk_content: str) -> str:
        """Compute hash of a single chunk."""
        # Normalize whitespace for consistent hashing
        normalized = ' '.join(chunk_content.split())
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()[:16]
    
    def get_version(self, file_path: str) -> Optional[DocumentVersion]:
        """Get the current version of a document."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        row = conn.execute(
            "SELECT * FROM document_versions WHERE file_path = ?",
            (file_path,)
        ).fetchone()
        
        conn.close()
        
        if row is None:
            return None
        
        return DocumentVersion(
            file_hash=row["file_hash"],
            content_hash=row["content_hash"],
            version=row["version"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    def check_file_changed(
        self,
        file_path: str,
        file_hash: str,
    ) -> Tuple[bool, Optional[DocumentVersion]]:
        """
        Check if a file has changed since last indexing.
        
        Returns:
            Tuple of (has_changed, existing_version)
        """
        version = self.get_version(file_path)
        
        if version is None:
            return True, None
        
        if version.file_hash != file_hash:
            return True, version
        
        return False, version
    
    def check_content_changed(
        self,
        file_path: str,
        content_hash: str,
    ) -> Tuple[bool, Optional[DocumentVersion]]:
        """
        Check if content has changed since last indexing.
        
        Returns:
            Tuple of (has_changed, existing_version)
        """
        version = self.get_version(file_path)
        
        if version is None:
            return True, None
        
        if version.content_hash != content_hash:
            return True, version
        
        return False, version
    
    def is_duplicate_content(self, content_hash: str, exclude_path: Optional[str] = None) -> List[str]:
        """
        Check if content is duplicate of another document.
        
        Returns:
            List of file paths with same content
        """
        conn = sqlite3.connect(self.db_path)
        
        row = conn.execute(
            "SELECT file_paths FROM content_hashes WHERE content_hash = ?",
            (content_hash,)
        ).fetchone()
        
        conn.close()
        
        if row is None:
            return []
        
        paths = json.loads(row[0])
        
        if exclude_path:
            paths = [p for p in paths if p != exclude_path]
        
        return paths
    
    def is_duplicate_chunk(self, chunk_hash: str) -> Optional[Tuple[int, str, int]]:
        """
        Check if a chunk is a duplicate.
        
        Returns:
            Tuple of (doc_id, file_path, chunk_index) if duplicate, None otherwise
        """
        conn = sqlite3.connect(self.db_path)
        
        row = conn.execute(
            "SELECT doc_id, file_path, chunk_index FROM chunk_hashes WHERE chunk_hash = ?",
            (chunk_hash,)
        ).fetchone()
        
        conn.close()
        
        return row
    
    def get_existing_chunk_hashes(self, doc_id: int) -> Set[str]:
        """Get all chunk hashes for a document."""
        conn = sqlite3.connect(self.db_path)
        
        rows = conn.execute(
            "SELECT chunk_hash FROM chunk_hashes WHERE doc_id = ?",
            (doc_id,)
        ).fetchall()
        
        conn.close()
        
        return {row[0] for row in rows}
    
    def register_document(
        self,
        file_path: str,
        file_hash: str,
        content_hash: str,
        metadata: Optional[dict] = None,
    ) -> DocumentVersion:
        """Register a new document or update existing."""
        now = datetime.now()
        conn = sqlite3.connect(self.db_path)
        
        # Check existing version
        existing = self.get_version(file_path)
        version = (existing.version + 1) if existing else 1
        
        # Update document_versions
        if existing:
            conn.execute("""
                UPDATE document_versions 
                SET file_hash = ?, content_hash = ?, version = ?, 
                    updated_at = ?, metadata = ?
                WHERE file_path = ?
            """, (
                file_hash, content_hash, version, now.isoformat(),
                json.dumps(metadata) if metadata else None, file_path
            ))
        else:
            conn.execute("""
                INSERT INTO document_versions 
                (file_path, file_hash, content_hash, version, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                file_path, file_hash, content_hash, version,
                now.isoformat(), now.isoformat(),
                json.dumps(metadata) if metadata else None
            ))
        
        # Update content_hashes
        existing_content = conn.execute(
            "SELECT file_paths FROM content_hashes WHERE content_hash = ?",
            (content_hash,)
        ).fetchone()
        
        if existing_content:
            paths = json.loads(existing_content[0])
            if file_path not in paths:
                paths.append(file_path)
            conn.execute("""
                UPDATE content_hashes 
                SET file_paths = ?, occurrence_count = ?
                WHERE content_hash = ?
            """, (json.dumps(paths), len(paths), content_hash))
        else:
            conn.execute("""
                INSERT INTO content_hashes (content_hash, file_paths, first_seen)
                VALUES (?, ?, ?)
            """, (content_hash, json.dumps([file_path]), now.isoformat()))
        
        conn.commit()
        conn.close()
        
        return DocumentVersion(
            file_hash=file_hash,
            content_hash=content_hash,
            version=version,
            created_at=existing.created_at if existing else now,
            metadata=metadata or {},
        )
    
    def register_chunks(
        self,
        doc_id: int,
        file_path: str,
        chunks: List[Tuple[int, str]],  # List of (chunk_index, content)
    ) -> Tuple[List[int], List[int]]:
        """
        Register chunk hashes for a document.
        
        Args:
            doc_id: Document ID
            file_path: File path
            chunks: List of (chunk_index, chunk_content) tuples
            
        Returns:
            Tuple of (new_chunk_indices, duplicate_chunk_indices)
        """
        now = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        
        # Get existing hashes for this document
        existing_hashes = self.get_existing_chunk_hashes(doc_id)
        
        new_indices = []
        duplicate_indices = []
        
        for chunk_index, content in chunks:
            chunk_hash = self.compute_chunk_hash(content)
            
            # Check if this exact hash exists
            existing = conn.execute(
                "SELECT doc_id, chunk_index FROM chunk_hashes WHERE chunk_hash = ?",
                (chunk_hash,)
            ).fetchone()
            
            if existing:
                # Duplicate found
                if existing[0] == doc_id:
                    # Same document, skip
                    duplicate_indices.append(chunk_index)
                else:
                    # Cross-document duplicate
                    duplicate_indices.append(chunk_index)
                    logger.debug(
                        f"Duplicate chunk found: doc {doc_id} chunk {chunk_index} "
                        f"matches doc {existing[0]} chunk {existing[1]}"
                    )
            else:
                # New chunk
                conn.execute("""
                    INSERT OR REPLACE INTO chunk_hashes 
                    (chunk_hash, doc_id, file_path, chunk_index, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (chunk_hash, doc_id, file_path, chunk_index, now))
                new_indices.append(chunk_index)
        
        conn.commit()
        conn.close()
        
        return new_indices, duplicate_indices
    
    def remove_document(self, file_path: str) -> bool:
        """Remove a document from deduplication tracking."""
        conn = sqlite3.connect(self.db_path)
        
        # Get content hash before removal
        row = conn.execute(
            "SELECT content_hash FROM document_versions WHERE file_path = ?",
            (file_path,)
        ).fetchone()
        
        if row:
            content_hash = row[0]
            
            # Update content_hashes
            content_row = conn.execute(
                "SELECT file_paths FROM content_hashes WHERE content_hash = ?",
                (content_hash,)
            ).fetchone()
            
            if content_row:
                paths = json.loads(content_row[0])
                paths = [p for p in paths if p != file_path]
                
                if paths:
                    conn.execute("""
                        UPDATE content_hashes 
                        SET file_paths = ?, occurrence_count = ?
                        WHERE content_hash = ?
                    """, (json.dumps(paths), len(paths), content_hash))
                else:
                    conn.execute(
                        "DELETE FROM content_hashes WHERE content_hash = ?",
                        (content_hash,)
                    )
        
        # Remove document version
        conn.execute(
            "DELETE FROM document_versions WHERE file_path = ?",
            (file_path,)
        )
        
        # Remove chunk hashes
        conn.execute(
            "DELETE FROM chunk_hashes WHERE file_path = ?",
            (file_path,)
        )
        
        conn.commit()
        conn.close()
        
        return True
    
    def get_stats(self) -> dict:
        """Get deduplication statistics."""
        conn = sqlite3.connect(self.db_path)
        
        total_docs = conn.execute(
            "SELECT COUNT(*) FROM document_versions"
        ).fetchone()[0]
        
        total_chunks = conn.execute(
            "SELECT COUNT(*) FROM chunk_hashes"
        ).fetchone()[0]
        
        unique_content = conn.execute(
            "SELECT COUNT(*) FROM content_hashes"
        ).fetchone()[0]
        
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM content_hashes WHERE occurrence_count > 1"
        ).fetchone()[0]
        
        conn.close()
        
        return {
            "total_documents": total_docs,
            "total_chunks": total_chunks,
            "unique_content_hashes": unique_content,
            "duplicate_content_count": duplicates,
        }
    
    def find_duplicates(self, min_occurrences: int = 2) -> List[dict]:
        """Find content that appears in multiple documents."""
        conn = sqlite3.connect(self.db_path)
        
        rows = conn.execute("""
            SELECT content_hash, file_paths, occurrence_count 
            FROM content_hashes 
            WHERE occurrence_count >= ?
            ORDER BY occurrence_count DESC
        """, (min_occurrences,)).fetchall()
        
        conn.close()
        
        return [
            {
                "content_hash": row[0],
                "file_paths": json.loads(row[1]),
                "occurrence_count": row[2],
            }
            for row in rows
        ]
    
    def cleanup(self) -> int:
        """Remove orphaned entries."""
        conn = sqlite3.connect(self.db_path)
        
        # Remove chunk hashes for non-existent documents
        deleted = conn.execute("""
            DELETE FROM chunk_hashes 
            WHERE file_path NOT IN (SELECT file_path FROM document_versions)
        """).rowcount
        
        # Remove empty content hashes
        deleted += conn.execute("""
            DELETE FROM content_hashes WHERE occurrence_count = 0
        """).rowcount
        
        conn.commit()
        conn.close()
        
        return deleted
