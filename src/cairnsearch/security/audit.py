"""Audit logging for security and compliance."""
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
import hashlib


logger = logging.getLogger(__name__)


class AuditAction(Enum):
    """Types of auditable actions."""
    DOCUMENT_INDEX = "document_index"
    DOCUMENT_DELETE = "document_delete"
    DOCUMENT_ACCESS = "document_access"
    DOCUMENT_SEARCH = "document_search"
    PII_DETECTED = "pii_detected"
    PII_REDACTED = "pii_redacted"
    ENCRYPTION = "encryption"
    DECRYPTION = "decryption"
    EXTRACTION_START = "extraction_start"
    EXTRACTION_COMPLETE = "extraction_complete"
    EXTRACTION_FAILED = "extraction_failed"
    OCR_PERFORMED = "ocr_performed"
    QUARANTINE = "quarantine"
    QUERY = "query"
    RAG_QUERY = "rag_query"
    SETTINGS_CHANGE = "settings_change"
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    ERROR = "error"
    ALERT = "alert"


@dataclass
class AuditEvent:
    """An audit log event."""
    action: AuditAction
    timestamp: datetime
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    project_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    file_path: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "session_id": self.session_id,
            "project_id": self.project_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "file_path": self.file_path,
            "details": self.details,
            "success": self.success,
            "error_message": self.error_message,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class AuditLogger:
    """Audit logger for security and compliance."""
    
    def __init__(self, db_path: Optional[Path] = None):
        from cairnsearch.config import get_config
        config = get_config()
        if db_path is None:
            db_path = config.get_data_dir() / "audit.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                user_id TEXT,
                session_id TEXT,
                project_id TEXT,
                resource_type TEXT,
                resource_id TEXT,
                file_path TEXT,
                details TEXT,
                success BOOLEAN DEFAULT TRUE,
                error_message TEXT,
                ip_address TEXT,
                user_agent TEXT,
                checksum TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp);
            CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
            CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user_id);
        """)
        conn.commit()
        conn.close()
    
    def log(self, event: AuditEvent) -> int:
        conn = sqlite3.connect(self.db_path)
        checksum = hashlib.sha256(event.to_json().encode()).hexdigest()[:16]
        
        cursor = conn.execute("""
            INSERT INTO audit_log (
                action, timestamp, user_id, session_id, project_id,
                resource_type, resource_id, file_path, details,
                success, error_message, ip_address, user_agent, checksum
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event.action.value, event.timestamp.isoformat(),
            event.user_id, event.session_id, event.project_id,
            event.resource_type, event.resource_id, event.file_path,
            json.dumps(event.details), event.success, event.error_message,
            event.ip_address, event.user_agent, checksum,
        ))
        
        event_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return event_id
    
    def log_action(
        self,
        action: AuditAction,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        file_path: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        user_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> int:
        event = AuditEvent(
            action=action,
            timestamp=datetime.now(),
            user_id=user_id,
            project_id=project_id,
            resource_type=resource_type,
            resource_id=resource_id,
            file_path=file_path,
            details=details or {},
            success=success,
            error_message=error_message,
        )
        return self.log(event)
    
    def query(
        self,
        action: Optional[AuditAction] = None,
        user_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        
        if action:
            query += " AND action = ?"
            params.append(action.value)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
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
            AuditEvent(
                action=AuditAction(row["action"]),
                timestamp=datetime.fromisoformat(row["timestamp"]),
                user_id=row["user_id"],
                session_id=row["session_id"],
                project_id=row["project_id"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                file_path=row["file_path"],
                details=json.loads(row["details"]) if row["details"] else {},
                success=bool(row["success"]),
                error_message=row["error_message"],
            )
            for row in rows
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        conn = sqlite3.connect(self.db_path)
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        errors = conn.execute("SELECT COUNT(*) FROM audit_log WHERE success = 0").fetchone()[0]
        by_action = dict(conn.execute(
            "SELECT action, COUNT(*) FROM audit_log GROUP BY action"
        ).fetchall())
        conn.close()
        
        return {"total_events": total, "error_count": errors, "by_action": by_action}
    
    def cleanup(self, days: int = 90) -> int:
        cutoff = datetime.now() - timedelta(days=days)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("DELETE FROM audit_log WHERE timestamp < ?", (cutoff.isoformat(),))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted
