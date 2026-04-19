"""Metrics collection for system monitoring."""
import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging


logger = logging.getLogger(__name__)


@dataclass
class DocumentMetrics:
    """Metrics for a processed document."""
    doc_id: int
    file_path: str
    filename: str
    
    # Timing
    total_time_ms: float = 0
    extraction_time_ms: float = 0
    ocr_time_ms: float = 0
    chunking_time_ms: float = 0
    embedding_time_ms: float = 0
    
    # Counts
    page_count: int = 0
    chunk_count: int = 0
    token_count: int = 0
    char_count: int = 0
    table_count: int = 0
    
    # Quality
    avg_ocr_confidence: Optional[float] = None
    
    # Errors
    error_count: int = 0
    warning_count: int = 0
    retry_count: int = 0
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "file_path": self.file_path,
            "filename": self.filename,
            "total_time_ms": self.total_time_ms,
            "extraction_time_ms": self.extraction_time_ms,
            "ocr_time_ms": self.ocr_time_ms,
            "chunking_time_ms": self.chunking_time_ms,
            "embedding_time_ms": self.embedding_time_ms,
            "page_count": self.page_count,
            "chunk_count": self.chunk_count,
            "token_count": self.token_count,
            "char_count": self.char_count,
            "table_count": self.table_count,
            "avg_ocr_confidence": self.avg_ocr_confidence,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "retry_count": self.retry_count,
            "timestamp": self.timestamp.isoformat(),
        }


class MetricsCollector:
    """
    Collects and stores system metrics.
    
    Features:
    - Per-document metrics
    - System-wide aggregations
    - Time-series storage
    - Cost tracking
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        from cairnsearch.config import get_config
        config = get_config()
        if db_path is None:
            db_path = config.get_data_dir() / "metrics.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
        # In-memory counters for current session
        self._session_start = datetime.now()
        self._docs_processed = 0
        self._errors = 0
        self._total_chunks = 0
        self._total_tokens = 0
        self._total_time_ms = 0
        self._embedding_cost = 0.0
        self._llm_cost = 0.0
    
    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS document_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                total_time_ms REAL,
                extraction_time_ms REAL,
                ocr_time_ms REAL,
                chunking_time_ms REAL,
                embedding_time_ms REAL,
                page_count INTEGER,
                chunk_count INTEGER,
                token_count INTEGER,
                char_count INTEGER,
                table_count INTEGER,
                avg_ocr_confidence REAL,
                error_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                timestamp TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS system_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                timestamp TEXT NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS cost_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service TEXT NOT NULL,
                operation TEXT NOT NULL,
                tokens INTEGER,
                cost_usd REAL NOT NULL,
                timestamp TEXT NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_doc_metrics_timestamp ON document_metrics(timestamp);
            CREATE INDEX IF NOT EXISTS idx_system_metrics_name ON system_metrics(metric_name, timestamp);
            CREATE INDEX IF NOT EXISTS idx_cost_service ON cost_tracking(service, timestamp);
        """)
        
        conn.commit()
        conn.close()
    
    def record_document(self, metrics: DocumentMetrics) -> int:
        """Record metrics for a processed document."""
        conn = sqlite3.connect(self.db_path)
        
        cursor = conn.execute("""
            INSERT INTO document_metrics (
                doc_id, file_path, filename,
                total_time_ms, extraction_time_ms, ocr_time_ms,
                chunking_time_ms, embedding_time_ms,
                page_count, chunk_count, token_count, char_count, table_count,
                avg_ocr_confidence, error_count, warning_count, retry_count,
                timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            metrics.doc_id, metrics.file_path, metrics.filename,
            metrics.total_time_ms, metrics.extraction_time_ms, metrics.ocr_time_ms,
            metrics.chunking_time_ms, metrics.embedding_time_ms,
            metrics.page_count, metrics.chunk_count, metrics.token_count,
            metrics.char_count, metrics.table_count,
            metrics.avg_ocr_confidence, metrics.error_count, metrics.warning_count,
            metrics.retry_count, metrics.timestamp.isoformat(),
        ))
        
        metric_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Update session counters
        self._docs_processed += 1
        self._errors += metrics.error_count
        self._total_chunks += metrics.chunk_count
        self._total_tokens += metrics.token_count
        self._total_time_ms += metrics.total_time_ms
        
        return metric_id
    
    def record_system_metric(self, name: str, value: float) -> None:
        """Record a system metric."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO system_metrics (metric_name, metric_value, timestamp) VALUES (?, ?, ?)",
            (name, value, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    def record_cost(
        self,
        service: str,
        operation: str,
        tokens: int,
        cost_usd: float,
    ) -> None:
        """Record API cost."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO cost_tracking (service, operation, tokens, cost_usd, timestamp) VALUES (?, ?, ?, ?, ?)",
            (service, operation, tokens, cost_usd, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
        
        if service == "embedding":
            self._embedding_cost += cost_usd
        elif service in ("llm", "claude", "openai"):
            self._llm_cost += cost_usd
    
    def get_document_metrics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[DocumentMetrics]:
        """Get document metrics."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        query = "SELECT * FROM document_metrics WHERE 1=1"
        params = []
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        conn.close()
        
        return [
            DocumentMetrics(
                doc_id=row["doc_id"],
                file_path=row["file_path"],
                filename=row["filename"],
                total_time_ms=row["total_time_ms"] or 0,
                extraction_time_ms=row["extraction_time_ms"] or 0,
                ocr_time_ms=row["ocr_time_ms"] or 0,
                chunking_time_ms=row["chunking_time_ms"] or 0,
                embedding_time_ms=row["embedding_time_ms"] or 0,
                page_count=row["page_count"] or 0,
                chunk_count=row["chunk_count"] or 0,
                token_count=row["token_count"] or 0,
                char_count=row["char_count"] or 0,
                table_count=row["table_count"] or 0,
                avg_ocr_confidence=row["avg_ocr_confidence"],
                error_count=row["error_count"] or 0,
                warning_count=row["warning_count"] or 0,
                retry_count=row["retry_count"] or 0,
                timestamp=datetime.fromisoformat(row["timestamp"]),
            )
            for row in rows
        ]
    
    def get_aggregated_stats(
        self,
        hours: int = 24,
    ) -> Dict[str, Any]:
        """Get aggregated statistics."""
        conn = sqlite3.connect(self.db_path)
        
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        # Document stats
        doc_stats = conn.execute("""
            SELECT 
                COUNT(*) as total,
                AVG(total_time_ms) as avg_time,
                SUM(chunk_count) as total_chunks,
                SUM(token_count) as total_tokens,
                SUM(error_count) as total_errors,
                AVG(avg_ocr_confidence) as avg_ocr_conf
            FROM document_metrics
            WHERE timestamp >= ?
        """, (cutoff,)).fetchone()
        
        # Cost stats
        cost_stats = conn.execute("""
            SELECT 
                service,
                SUM(tokens) as total_tokens,
                SUM(cost_usd) as total_cost
            FROM cost_tracking
            WHERE timestamp >= ?
            GROUP BY service
        """, (cutoff,)).fetchall()
        
        conn.close()
        
        return {
            "period_hours": hours,
            "documents_processed": doc_stats[0] or 0,
            "avg_processing_time_ms": doc_stats[1] or 0,
            "total_chunks": doc_stats[2] or 0,
            "total_tokens": doc_stats[3] or 0,
            "total_errors": doc_stats[4] or 0,
            "avg_ocr_confidence": doc_stats[5],
            "costs_by_service": {
                row[0]: {"tokens": row[1], "cost_usd": row[2]}
                for row in cost_stats
            },
        }
    
    def get_session_stats(self) -> Dict[str, Any]:
        """Get current session statistics."""
        session_duration = (datetime.now() - self._session_start).total_seconds()
        docs_per_hour = (self._docs_processed / session_duration) * 3600 if session_duration > 0 else 0
        
        return {
            "session_start": self._session_start.isoformat(),
            "session_duration_seconds": session_duration,
            "documents_processed": self._docs_processed,
            "documents_per_hour": docs_per_hour,
            "total_errors": self._errors,
            "total_chunks": self._total_chunks,
            "total_tokens": self._total_tokens,
            "total_processing_time_ms": self._total_time_ms,
            "embedding_cost_usd": self._embedding_cost,
            "llm_cost_usd": self._llm_cost,
            "total_cost_usd": self._embedding_cost + self._llm_cost,
        }
    
    def get_error_rate(self, hours: int = 1) -> float:
        """Calculate error rate over period."""
        conn = sqlite3.connect(self.db_path)
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        result = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN error_count > 0 THEN 1 ELSE 0 END) as with_errors
            FROM document_metrics
            WHERE timestamp >= ?
        """, (cutoff,)).fetchone()
        
        conn.close()
        
        total = result[0] or 0
        with_errors = result[1] or 0
        
        return (with_errors / total) if total > 0 else 0.0
    
    def cleanup(self, days: int = 30) -> int:
        """Remove old metrics."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        deleted = 0
        
        for table in ["document_metrics", "system_metrics", "cost_tracking"]:
            cursor = conn.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,))
            deleted += cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted
