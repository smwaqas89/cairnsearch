"""Index manager - coordinates extraction and database updates."""
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

from cairnsearch.config import get_config
from cairnsearch.db import Database, Document, FileMeta
from cairnsearch.extractors import get_registry, extract_dates
from .hasher import hash_file


logger = logging.getLogger(__name__)


class IndexManager:
    """Manages document indexing operations."""

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.registry = get_registry()
        self.config = get_config()
        self._rag_engine = None

    def _get_rag_engine(self):
        """Lazy-load RAG engine to avoid import issues."""
        if self._rag_engine is None:
            try:
                from cairnsearch.rag import RAGEngine
                rag_config = self.config.rag
                if rag_config.enabled:
                    self._rag_engine = RAGEngine(db=self.db)
                    logger.info("RAG engine initialized for auto-embedding")
            except Exception as e:
                logger.warning(f"RAG engine not available: {e}")
                self._rag_engine = False  # Mark as unavailable
        return self._rag_engine if self._rag_engine else None

    def index_file(self, file_path: Path) -> bool:
        """
        Index a single file.
        
        Args:
            file_path: Path to file to index
            
        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path).resolve()
        
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return False

        if not self.registry.can_extract(file_path):
            logger.debug(f"Unsupported file type: {file_path}")
            return False

        # Check file size limit
        max_size = self.config.indexer.max_file_size_mb * 1024 * 1024
        if file_path.stat().st_size > max_size:
            logger.warning(f"File too large: {file_path}")
            return False

        try:
            # Compute hash for change detection
            file_hash = hash_file(file_path, self.config.indexer.hash_algorithm)
            stat = file_path.stat()
            
            # Check if file already indexed with same hash
            existing = self._get_file_meta(str(file_path))
            if existing and existing["hash"] == file_hash:
                logger.debug(f"File unchanged: {file_path}")
                return True

            # Extract text
            result = self.registry.extract(file_path)
            if not result.success:
                self._update_file_meta_error(str(file_path), file_hash, stat, result.error)
                logger.error(f"Extraction failed for {file_path}: {result.error}")
                return False

            # Extract dates from content
            detected_dates = []
            if result.text:
                detected_dates = extract_dates(result.text)

            # Create document record
            doc = Document(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=file_path.suffix.lower().lstrip("."),
                content=result.text,
                page_count=result.page_count,
                doc_title=result.title,
                doc_author=result.author,
                doc_created=result.created_date,
                doc_modified=result.modified_date,
                detected_dates=detected_dates,
                extraction_method=result.extraction_method,
            )

            # Update database
            doc_id = self._upsert_document(doc, file_hash, stat)
            logger.info(f"Indexed: {file_path}")
            
            # Auto-create RAG embeddings
            if doc_id and result.text:
                self._index_for_rag(doc_id, str(file_path), file_path.name, result.text)
            
            return True

        except Exception as e:
            logger.exception(f"Error indexing {file_path}: {e}")
            return False

    def _index_for_rag(self, doc_id: int, file_path: str, filename: str, content: str):
        """Create RAG embeddings for a document."""
        try:
            rag_engine = self._get_rag_engine()
            if rag_engine:
                chunks_added = rag_engine.index_document(
                    doc_id=doc_id,
                    file_path=file_path,
                    filename=filename,
                    content=content,
                )
                if chunks_added > 0:
                    logger.info(f"Created {chunks_added} RAG chunks for {filename}")
        except Exception as e:
            logger.warning(f"RAG indexing failed for {filename}: {e}")

    def delete_file(self, file_path: str) -> bool:
        """Remove file from index."""
        try:
            with self.db.connection() as conn:
                conn.execute("DELETE FROM documents WHERE file_path = ?", (file_path,))
                conn.execute("DELETE FROM files_meta WHERE path = ?", (file_path,))
                conn.commit()
            logger.info(f"Deleted from index: {file_path}")
            return True
        except Exception as e:
            logger.exception(f"Error deleting {file_path}: {e}")
            return False

    def reindex_all(self) -> tuple[int, int]:
        """
        Reindex all watched folders.
        
        Returns:
            Tuple of (success_count, failure_count)
        """
        success = 0
        failed = 0
        
        for folder in self.config.get_watch_folders():
            if not folder.exists():
                logger.warning(f"Watch folder not found: {folder}")
                continue
            
            for file_path in self._iter_files(folder):
                if self.index_file(file_path):
                    success += 1
                else:
                    failed += 1
        
        return success, failed

    def get_stats(self) -> dict:
        """Get indexing statistics."""
        with self.db.connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            by_type = conn.execute(
                "SELECT file_type, COUNT(*) FROM documents GROUP BY file_type"
            ).fetchall()
            pending = conn.execute(
                "SELECT COUNT(*) FROM files_meta WHERE status = 'pending'"
            ).fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM files_meta WHERE status = 'failed'"
            ).fetchone()[0]
        
        return {
            "indexed_count": total,
            "pending": pending,
            "failed": failed,
            "by_type": {row[0]: row[1] for row in by_type},
        }

    def _iter_files(self, folder: Path):
        """Iterate over indexable files in folder."""
        ignore_patterns = self.config.watcher.ignore_patterns
        supported_exts = self.registry.supported_extensions()
        
        for file_path in folder.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Check ignore patterns
            if any(file_path.match(p) for p in ignore_patterns):
                continue
            
            # Check if any parent matches ignore patterns
            if any(
                parent.name in ignore_patterns or 
                any(parent.match(p) for p in ignore_patterns)
                for parent in file_path.parents
            ):
                continue
            
            # Check extension
            if file_path.suffix.lower() not in supported_exts:
                continue
            
            yield file_path

    def _get_file_meta(self, path: str) -> Optional[dict]:
        """Get file metadata from database."""
        rows = self.db.execute(
            "SELECT * FROM files_meta WHERE path = ?", (path,)
        )
        return dict(rows[0]) if rows else None

    def _upsert_document(self, doc: Document, file_hash: str, stat) -> Optional[int]:
        """Insert or update document in database. Returns doc_id."""
        now = datetime.now().isoformat()
        
        with self.db.connection() as conn:
            # Upsert files_meta
            conn.execute("""
                INSERT INTO files_meta (path, hash, size_bytes, file_mtime, indexed_at, status)
                VALUES (?, ?, ?, ?, ?, 'indexed')
                ON CONFLICT(path) DO UPDATE SET
                    hash = excluded.hash,
                    size_bytes = excluded.size_bytes,
                    file_mtime = excluded.file_mtime,
                    indexed_at = excluded.indexed_at,
                    status = 'indexed',
                    error_msg = NULL
            """, (doc.file_path, file_hash, stat.st_size, stat.st_mtime, now))
            
            # Upsert documents
            conn.execute("""
                INSERT INTO documents (
                    file_path, filename, file_type, content, page_count,
                    doc_title, doc_author, doc_created, doc_modified,
                    detected_dates, extraction_method
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    filename = excluded.filename,
                    file_type = excluded.file_type,
                    content = excluded.content,
                    page_count = excluded.page_count,
                    doc_title = excluded.doc_title,
                    doc_author = excluded.doc_author,
                    doc_created = excluded.doc_created,
                    doc_modified = excluded.doc_modified,
                    detected_dates = excluded.detected_dates,
                    extraction_method = excluded.extraction_method,
                    updated_at = datetime('now')
            """, doc.to_insert_tuple())
            
            conn.commit()
            
            # Get the doc_id
            result = conn.execute(
                "SELECT id FROM documents WHERE file_path = ?", (doc.file_path,)
            ).fetchone()
            
            return result[0] if result else None

    def _update_file_meta_error(self, path: str, file_hash: str, stat, error: str) -> None:
        """Update file metadata with error status."""
        now = datetime.now().isoformat()
        
        with self.db.connection() as conn:
            conn.execute("""
                INSERT INTO files_meta (path, hash, size_bytes, file_mtime, indexed_at, status, error_msg)
                VALUES (?, ?, ?, ?, ?, 'failed', ?)
                ON CONFLICT(path) DO UPDATE SET
                    hash = excluded.hash,
                    size_bytes = excluded.size_bytes,
                    file_mtime = excluded.file_mtime,
                    indexed_at = excluded.indexed_at,
                    status = 'failed',
                    error_msg = excluded.error_msg
            """, (path, file_hash, stat.st_size, stat.st_mtime, now, error))
            conn.commit()
