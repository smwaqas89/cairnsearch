"""API routes for system health and metrics."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import logging


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/system", tags=["system"])


class SystemHealth(BaseModel):
    """Response model for system health."""
    pending_jobs: int
    processing_jobs: int
    failed_jobs: int
    completed_jobs: int
    error_rate_1h: float
    error_rate_24h: float
    avg_processing_time_ms: float
    documents_per_hour: float
    quarantine_count: int
    total_chunks: int
    embedding_cost_usd: float
    llm_cost_usd: float
    alerts: List[Dict[str, Any]]
    timestamp: str


class DocumentMetricsResponse(BaseModel):
    """Response model for document metrics."""
    doc_id: int
    file_path: str
    filename: str
    total_time_ms: float
    extraction_time_ms: float
    ocr_time_ms: float
    chunking_time_ms: float
    embedding_time_ms: float
    page_count: int
    chunk_count: int
    token_count: int
    error_count: int
    timestamp: str


class AggregatedStats(BaseModel):
    """Response model for aggregated statistics."""
    period_hours: int
    documents_processed: int
    avg_processing_time_ms: float
    total_chunks: int
    total_tokens: int
    total_errors: int
    avg_ocr_confidence: Optional[float]
    costs_by_service: Dict[str, Dict[str, Any]]


class AlertResponse(BaseModel):
    """Response model for an alert."""
    alert_type: str
    severity: str
    message: str
    timestamp: str
    file_path: Optional[str]
    doc_id: Optional[int]
    resolved: bool


@router.get("/health", response_model=SystemHealth)
async def get_health():
    """Get system health status."""
    from cairnsearch.indexer import EnhancedIndexManager
    from cairnsearch.monitoring import AlertManager, MetricsCollector
    
    manager = EnhancedIndexManager()
    stats = manager.get_stats()
    
    metrics = MetricsCollector()
    session = metrics.get_session_stats()
    
    alerts_mgr = AlertManager()
    active_alerts = alerts_mgr.get_active_alerts()
    
    docs_processed = session.get("documents_processed", 1) or 1
    
    return SystemHealth(
        pending_jobs=stats.get("pending", 0),
        processing_jobs=0,
        failed_jobs=stats.get("failed", 0),
        completed_jobs=stats.get("indexed_count", 0),
        error_rate_1h=metrics.get_error_rate(hours=1),
        error_rate_24h=metrics.get_error_rate(hours=24),
        avg_processing_time_ms=session.get("total_processing_time_ms", 0) / docs_processed,
        documents_per_hour=session.get("documents_per_hour", 0),
        quarantine_count=stats.get("quarantine", {}).get("total", 0),
        total_chunks=stats.get("deduplication", {}).get("total_chunks", 0),
        embedding_cost_usd=session.get("embedding_cost_usd", 0),
        llm_cost_usd=session.get("llm_cost_usd", 0),
        alerts=[a.to_dict() for a in active_alerts[:10]],
        timestamp=datetime.now().isoformat(),
    )


@router.get("/metrics", response_model=List[DocumentMetricsResponse])
async def get_document_metrics(
    hours: int = 24,
    limit: int = 100,
):
    """Get document processing metrics."""
    from cairnsearch.monitoring import MetricsCollector
    
    metrics = MetricsCollector()
    start_time = datetime.now() - timedelta(hours=hours)
    
    doc_metrics = metrics.get_document_metrics(
        start_time=start_time,
        limit=limit,
    )
    
    return [
        DocumentMetricsResponse(
            doc_id=m.doc_id,
            file_path=m.file_path,
            filename=m.filename,
            total_time_ms=m.total_time_ms,
            extraction_time_ms=m.extraction_time_ms,
            ocr_time_ms=m.ocr_time_ms,
            chunking_time_ms=m.chunking_time_ms,
            embedding_time_ms=m.embedding_time_ms,
            page_count=m.page_count,
            chunk_count=m.chunk_count,
            token_count=m.token_count,
            error_count=m.error_count,
            timestamp=m.timestamp.isoformat(),
        )
        for m in doc_metrics
    ]


@router.get("/metrics/aggregated", response_model=AggregatedStats)
async def get_aggregated_stats(hours: int = 24):
    """Get aggregated statistics."""
    from cairnsearch.monitoring import MetricsCollector
    
    metrics = MetricsCollector()
    stats = metrics.get_aggregated_stats(hours=hours)
    
    return AggregatedStats(**stats)


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts(
    severity: Optional[str] = None,
    resolved: Optional[bool] = None,
    hours: int = 24,
    limit: int = 100,
):
    """Get system alerts."""
    from cairnsearch.monitoring import AlertManager, AlertSeverity
    
    alerts_mgr = AlertManager()
    
    sev = AlertSeverity(severity) if severity else None
    alerts = alerts_mgr.get_alerts(
        severity=sev,
        resolved=resolved,
        hours=hours,
        limit=limit,
    )
    
    return [
        AlertResponse(
            alert_type=a.alert_type.value,
            severity=a.severity.value,
            message=a.message,
            timestamp=a.timestamp.isoformat(),
            file_path=a.file_path,
            doc_id=a.doc_id,
            resolved=a.resolved,
        )
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int, note: Optional[str] = None):
    """Resolve an alert."""
    from cairnsearch.monitoring import AlertManager
    
    alerts_mgr = AlertManager()
    success = alerts_mgr.resolve_alert(alert_id, note)
    
    return {
        "success": success,
        "message": "Alert resolved" if success else "Failed to resolve alert",
    }


@router.get("/deduplication")
async def get_deduplication_stats():
    """Get deduplication statistics."""
    from cairnsearch.core import DeduplicationManager
    
    dedup = DeduplicationManager()
    stats = dedup.get_stats()
    duplicates = dedup.find_duplicates(min_occurrences=2)
    
    return {
        **stats,
        "duplicates": duplicates[:20],
    }


@router.get("/audit")
async def get_audit_log(
    action: Optional[str] = None,
    hours: int = 24,
    limit: int = 100,
):
    """Get audit log entries."""
    from cairnsearch.security import AuditLogger, AuditAction
    
    audit = AuditLogger()
    start_time = datetime.now() - timedelta(hours=hours)
    
    act = AuditAction(action) if action else None
    events = audit.query(
        action=act,
        start_time=start_time,
        limit=limit,
    )
    
    return [e.to_dict() for e in events]
