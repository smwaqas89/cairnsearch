"""Vector storage for RAG."""
import json
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import logging
import math

from .config import get_rag_config
from .chunker import Chunk


logger = logging.getLogger(__name__)


@dataclass
class VectorSearchResult:
    """Result from vector search."""
    chunk_id: str
    doc_id: int
    file_path: str
    filename: str
    content: str
    score: float
    metadata: dict


class VectorStore:
    """SQLite-based vector store with cosine similarity search."""
    
    def __init__(self, db_path: Optional[Path] = None):
        config = get_rag_config()
        if db_path is None:
            db_path = Path(config.vector_store_path).expanduser() / "vectors.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent performance
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                content TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                metadata TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_file_path ON chunks(file_path)")
        conn.commit()
        conn.close()
    
    def add_chunks(self, chunks: list[Chunk], embeddings: list[list[float]]) -> int:
        """Add chunks with their embeddings."""
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings")
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        added = 0
        for chunk, embedding in zip(chunks, embeddings):
            try:
                embedding_blob = json.dumps(embedding).encode()
                metadata_json = json.dumps(chunk.metadata) if chunk.metadata else None
                
                cursor.execute("""
                    INSERT OR REPLACE INTO chunks 
                    (chunk_id, doc_id, file_path, filename, content, chunk_index, embedding, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk.id, chunk.doc_id, chunk.file_path, chunk.filename,
                    chunk.content, chunk.chunk_index, embedding_blob, metadata_json,
                ))
                added += 1
            except Exception as e:
                logger.error(f"Failed to add chunk {chunk.id}: {e}")
        
        conn.commit()
        conn.close()
        return added
    
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        file_path_filter: Optional[str] = None,
    ) -> list[VectorSearchResult]:
        """Search for similar chunks using cosine similarity."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if file_path_filter:
            cursor.execute(
                "SELECT chunk_id, doc_id, file_path, filename, content, embedding, metadata "
                "FROM chunks WHERE file_path = ?",
                (file_path_filter,)
            )
        else:
            cursor.execute(
                "SELECT chunk_id, doc_id, file_path, filename, content, embedding, metadata "
                "FROM chunks"
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        results = []
        for row in rows:
            chunk_id, doc_id, file_path, filename, content, embedding_blob, metadata_json = row
            stored_embedding = json.loads(embedding_blob.decode())
            similarity = self._cosine_similarity(query_embedding, stored_embedding)
            metadata = json.loads(metadata_json) if metadata_json else {}
            
            results.append(VectorSearchResult(
                chunk_id=chunk_id, doc_id=doc_id, file_path=file_path,
                filename=filename, content=content, score=similarity, metadata=metadata,
            ))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]
    
    def delete_by_doc_id(self, doc_id: int) -> int:
        """Delete all chunks for a document."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    
    def get_stats(self) -> dict:
        """Get vector store statistics."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        total_chunks = cursor.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        total_docs = cursor.execute("SELECT COUNT(DISTINCT doc_id) FROM chunks").fetchone()[0]
        conn.close()
        return {"total_chunks": total_chunks, "total_documents": total_docs, "db_path": str(self.db_path)}
    
    def clear(self) -> int:
        """Clear all chunks."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM chunks")
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
    
    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)
    
    def get_document_embedding(self, doc_id: int) -> Optional[list[float]]:
        """Get average embedding for a document (centroid of all chunks)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT embedding FROM chunks WHERE doc_id = ?",
            (doc_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return None
        
        # Calculate centroid (average) of all chunk embeddings
        embeddings = [json.loads(row[0].decode()) for row in rows]
        
        if not embeddings:
            return None
        
        dim = len(embeddings[0])
        centroid = [0.0] * dim
        
        for emb in embeddings:
            for i, val in enumerate(emb):
                centroid[i] += val
        
        n = len(embeddings)
        centroid = [v / n for v in centroid]
        
        return centroid
    
    def find_similar_documents(
        self,
        embedding: list[float],
        exclude_doc_id: Optional[int] = None,
        top_k: int = 10,
        min_similarity: float = 0.0,
    ) -> list[tuple[int, float]]:
        """
        Find documents similar to the given embedding.
        
        Returns list of (doc_id, similarity_score) tuples.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT DISTINCT doc_id FROM chunks"
        )
        doc_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        # Calculate similarity for each document
        similarities = []
        for doc_id in doc_ids:
            if doc_id == exclude_doc_id:
                continue
            
            doc_embedding = self.get_document_embedding(doc_id)
            if doc_embedding:
                sim = self._cosine_similarity(embedding, doc_embedding)
                if sim >= min_similarity:
                    similarities.append((doc_id, sim))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]
    
    def get_chunk_count(self, doc_id: int) -> int:
        """Get number of chunks for a document."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM chunks WHERE doc_id = ?",
            (doc_id,)
        )
        count = cursor.fetchone()[0]
        conn.close()
        return count
