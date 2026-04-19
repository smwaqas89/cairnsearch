"""Alert management for system monitoring."""
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
import logging


logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertType(Enum):
    """Types of alerts."""
    PROCESSING_FAILURE = "processing_failure"
    REPEATED_FAILURES = "repeated_failures"
    CHUNK_EXPLOSION = "chunk_explosion"
    HIGH_ERROR_RATE = "high_error_rate"
    COST_THRESHOLD = "cost_threshold"
    QUEUE_BACKLOG = "queue_backlog"
    LOW_OCR_CONFIDENCE = "low_ocr_confidence"
    QUARANTINE_FULL = "quarantine_full"
    DISK_SPACE = "disk_space"
    CUSTOM = "custom"


@dataclass
class Alert:
    """An alert event."""
    alert_type: AlertType
    severity: AlertSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Context
    file_path: Optional[str] = None
    doc_id: Optional[int] = None
    
    # Details
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Resolution
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "file_path": self.file_path,
            "doc_id": self.doc_id,
            "details": self.details,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_note": self.resolution_note,
        }


class AlertManager:
    """
    Manages system alerts.
    
    Features:
    - Alert creation and storage
    - Threshold-based alerting
    - Alert deduplication
    - Notification callbacks
    """
    
    # Default thresholds
    DEFAULT_THRESHOLDS = {
        "error_rate_warning": 0.1,  # 10%
        "error_rate_critical": 0.3,  # 30%
        "chunk_explosion_threshold": 1000,
        "queue_backlog_warning": 100,
        "queue_backlog_critical": 500,
        "cost_daily_warning": 10.0,  # USD
        "cost_daily_critical": 50.0,
        "quarantine_warning": 50,
        "quarantine_critical": 200,
        "repeated_failure_threshold": 3,
    }
    
    def __init__(
        self,
        db_path: Optional[Path] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        from cairnsearch.config import get_config
        config = get_config()
        if db_path is None:
            db_path = config.get_data_dir() / "alerts.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.thresholds = {**self.DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._callbacks: List[Callable[[Alert], None]] = []
        self._recent_alerts: Dict[str, datetime] = {}
        
        self._init_db()
    
    def _init_db(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                file_path TEXT,
                doc_id INTEGER,
                details TEXT,
                resolved BOOLEAN DEFAULT FALSE,
                resolved_at TEXT,
                resolution_note TEXT
            );
            
            CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp);
            CREATE INDEX IF NOT EXISTS idx_alerts_severity ON alerts(severity);
            CREATE INDEX IF NOT EXISTS idx_alerts_resolved ON alerts(resolved);
        """)
        
        conn.commit()
        conn.close()
    
    def add_callback(self, callback: Callable[[Alert], None]) -> None:
        """Add a callback to be called when alerts are created."""
        self._callbacks.append(callback)
    
    def create_alert(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        file_path: Optional[str] = None,
        doc_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        dedupe_minutes: int = 5,
    ) -> Optional[int]:
        """
        Create an alert.
        
        Args:
            alert_type: Type of alert
            severity: Severity level
            message: Alert message
            file_path: Related file path
            doc_id: Related document ID
            details: Additional details
            dedupe_minutes: Skip duplicate alerts within this window
            
        Returns:
            Alert ID or None if deduplicated
        """
        # Check for duplicate
        dedupe_key = f"{alert_type.value}:{file_path or ''}:{message[:50]}"
        if dedupe_key in self._recent_alerts:
            last_alert = self._recent_alerts[dedupe_key]
            if datetime.now() - last_alert < timedelta(minutes=dedupe_minutes):
                logger.debug(f"Skipping duplicate alert: {dedupe_key}")
                return None
        
        alert = Alert(
            alert_type=alert_type,
            severity=severity,
            message=message,
            file_path=file_path,
            doc_id=doc_id,
            details=details or {},
        )
        
        # Store alert
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            INSERT INTO alerts (
                alert_type, severity, message, timestamp,
                file_path, doc_id, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            alert.alert_type.value,
            alert.severity.value,
            alert.message,
            alert.timestamp.isoformat(),
            alert.file_path,
            alert.doc_id,
            json.dumps(alert.details),
        ))
        
        alert_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Update dedupe tracker
        self._recent_alerts[dedupe_key] = datetime.now()
        
        # Log
        log_method = {
            AlertSeverity.INFO: logger.info,
            AlertSeverity.WARNING: logger.warning,
            AlertSeverity.ERROR: logger.error,
            AlertSeverity.CRITICAL: logger.critical,
        }[severity]
        log_method(f"Alert [{alert_type.value}]: {message}")
        
        # Call callbacks
        for callback in self._callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
        
        return alert_id
    
    def check_error_rate(self, rate: float) -> None:
        """Check error rate and create alerts if needed."""
        if rate >= self.thresholds["error_rate_critical"]:
            self.create_alert(
                AlertType.HIGH_ERROR_RATE,
                AlertSeverity.CRITICAL,
                f"Critical error rate: {rate:.1%}",
                details={"error_rate": rate},
            )
        elif rate >= self.thresholds["error_rate_warning"]:
            self.create_alert(
                AlertType.HIGH_ERROR_RATE,
                AlertSeverity.WARNING,
                f"High error rate: {rate:.1%}",
                details={"error_rate": rate},
            )
    
    def check_chunk_explosion(
        self,
        chunk_count: int,
        file_path: str,
        doc_id: Optional[int] = None,
    ) -> None:
        """Check for chunk explosion."""
        if chunk_count >= self.thresholds["chunk_explosion_threshold"]:
            self.create_alert(
                AlertType.CHUNK_EXPLOSION,
                AlertSeverity.WARNING,
                f"Document created {chunk_count} chunks",
                file_path=file_path,
                doc_id=doc_id,
                details={"chunk_count": chunk_count},
            )
    
    def check_repeated_failures(
        self,
        file_path: str,
        failure_count: int,
    ) -> None:
        """Check for repeated processing failures."""
        if failure_count >= self.thresholds["repeated_failure_threshold"]:
            self.create_alert(
                AlertType.REPEATED_FAILURES,
                AlertSeverity.ERROR,
                f"Document failed {failure_count} times",
                file_path=file_path,
                details={"failure_count": failure_count},
            )
    
    def check_queue_backlog(self, pending_count: int) -> None:
        """Check queue backlog."""
        if pending_count >= self.thresholds["queue_backlog_critical"]:
            self.create_alert(
                AlertType.QUEUE_BACKLOG,
                AlertSeverity.CRITICAL,
                f"Queue backlog: {pending_count} pending jobs",
                details={"pending_count": pending_count},
            )
        elif pending_count >= self.thresholds["queue_backlog_warning"]:
            self.create_alert(
                AlertType.QUEUE_BACKLOG,
                AlertSeverity.WARNING,
                f"Queue backlog: {pending_count} pending jobs",
                details={"pending_count": pending_count},
            )
    
    def check_daily_cost(self, cost_usd: float) -> None:
        """Check daily cost."""
        if cost_usd >= self.thresholds["cost_daily_critical"]:
            self.create_alert(
                AlertType.COST_THRESHOLD,
                AlertSeverity.CRITICAL,
                f"Daily cost exceeded: ${cost_usd:.2f}",
                details={"cost_usd": cost_usd},
            )
        elif cost_usd >= self.thresholds["cost_daily_warning"]:
            self.create_alert(
                AlertType.COST_THRESHOLD,
                AlertSeverity.WARNING,
                f"Daily cost warning: ${cost_usd:.2f}",
                details={"cost_usd": cost_usd},
            )
    
    def resolve_alert(
        self,
        alert_id: int,
        note: Optional[str] = None,
    ) -> bool:
        """Resolve an alert."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("""
            UPDATE alerts
            SET resolved = TRUE, resolved_at = ?, resolution_note = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), note, alert_id))
        
        updated = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return updated
    
    def get_alerts(
        self,
        severity: Optional[AlertSeverity] = None,
        alert_type: Optional[AlertType] = None,
        resolved: Optional[bool] = None,
        hours: int = 24,
        limit: int = 100,
    ) -> List[Alert]:
        """Query alerts."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        query = "SELECT * FROM alerts WHERE timestamp >= ?"
        params = [(datetime.now() - timedelta(hours=hours)).isoformat()]
        
        if severity:
            query += " AND severity = ?"
            params.append(severity.value)
        if alert_type:
            query += " AND alert_type = ?"
            params.append(alert_type.value)
        if resolved is not None:
            query += " AND resolved = ?"
            params.append(resolved)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(query, params).fetchall()
        conn.close()
        
        return [
            Alert(
                alert_type=AlertType(row["alert_type"]),
                severity=AlertSeverity(row["severity"]),
                message=row["message"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                file_path=row["file_path"],
                doc_id=row["doc_id"],
                details=json.loads(row["details"]) if row["details"] else {},
                resolved=bool(row["resolved"]),
                resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
                resolution_note=row["resolution_note"],
            )
            for row in rows
        ]
    
    def get_active_alerts(self) -> List[Alert]:
        """Get unresolved alerts."""
        return self.get_alerts(resolved=False, hours=168)  # Last week
    
    def get_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        conn = sqlite3.connect(self.db_path)
        
        total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
        unresolved = conn.execute("SELECT COUNT(*) FROM alerts WHERE resolved = FALSE").fetchone()[0]
        
        by_severity = dict(conn.execute(
            "SELECT severity, COUNT(*) FROM alerts GROUP BY severity"
        ).fetchall())
        
        by_type = dict(conn.execute(
            "SELECT alert_type, COUNT(*) FROM alerts GROUP BY alert_type"
        ).fetchall())
        
        conn.close()
        
        return {
            "total": total,
            "unresolved": unresolved,
            "by_severity": by_severity,
            "by_type": by_type,
        }
    
    def cleanup(self, days: int = 30) -> int:
        """Remove old resolved alerts."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "DELETE FROM alerts WHERE resolved = TRUE AND timestamp < ?",
            (cutoff,)
        )
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted
