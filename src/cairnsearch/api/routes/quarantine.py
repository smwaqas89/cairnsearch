"""API routes for quarantine management."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import logging

from cairnsearch.core import QuarantineManager, FailureManifest


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quarantine", tags=["quarantine"])

# Global quarantine manager (initialized on first use)
_quarantine: Optional[QuarantineManager] = None


def get_quarantine() -> QuarantineManager:
    global _quarantine
    if _quarantine is None:
        _quarantine = QuarantineManager()
    return _quarantine


class QuarantineItem(BaseModel):
    """Response model for quarantined item."""
    file_path: str
    filename: str
    reason: str
    stage: str
    timestamp: str
    retry_count: int
    max_retries: int
    recoverable: bool
    error_details: Optional[str] = None


class QuarantineStats(BaseModel):
    """Response model for quarantine statistics."""
    total: int
    recoverable: int
    permanently_skipped: int
    by_stage: dict
    by_reason: dict


class RetryRequest(BaseModel):
    """Request model for retry operation."""
    file_path: str
    ocr_only: bool = False


class SkipRequest(BaseModel):
    """Request model for skip operation."""
    file_path: str


@router.get("/list", response_model=List[QuarantineItem])
async def list_quarantined(
    recoverable_only: bool = False,
    stage: Optional[str] = None,
    limit: int = 100,
):
    """List quarantined documents."""
    quarantine = get_quarantine()
    manifests = quarantine.list_quarantined(
        recoverable_only=recoverable_only,
        stage=stage,
        limit=limit,
    )
    
    return [
        QuarantineItem(
            file_path=m.file_path,
            filename=m.filename,
            reason=m.reason,
            stage=m.stage,
            timestamp=m.timestamp.isoformat(),
            retry_count=m.retry_count,
            max_retries=m.max_retries,
            recoverable=m.recoverable,
            error_details=m.error_details,
        )
        for m in manifests
    ]


@router.get("/stats", response_model=QuarantineStats)
async def get_stats():
    """Get quarantine statistics."""
    quarantine = get_quarantine()
    stats = quarantine.get_stats()
    return QuarantineStats(**stats)


@router.get("/item/{file_path:path}", response_model=QuarantineItem)
async def get_item(file_path: str):
    """Get details for a specific quarantined item."""
    quarantine = get_quarantine()
    manifest = quarantine.get_manifest(file_path)
    
    if manifest is None:
        raise HTTPException(status_code=404, detail="Item not found in quarantine")
    
    return QuarantineItem(
        file_path=manifest.file_path,
        filename=manifest.filename,
        reason=manifest.reason,
        stage=manifest.stage,
        timestamp=manifest.timestamp.isoformat(),
        retry_count=manifest.retry_count,
        max_retries=manifest.max_retries,
        recoverable=manifest.recoverable,
        error_details=manifest.error_details,
    )


@router.post("/retry")
async def retry_item(request: RetryRequest):
    """Retry processing a quarantined document."""
    from cairnsearch.indexer import EnhancedIndexManager
    
    quarantine = get_quarantine()
    
    if not quarantine.is_quarantined(request.file_path):
        raise HTTPException(status_code=404, detail="Item not found in quarantine")
    
    if not quarantine.can_retry(request.file_path):
        raise HTTPException(status_code=400, detail="Maximum retries exceeded")
    
    # Use enhanced index manager
    manager = EnhancedIndexManager()
    success, doc_id = manager.index_file(request.file_path)
    
    return {
        "success": success,
        "doc_id": doc_id,
        "message": "Reprocessing successful" if success else "Reprocessing failed",
    }


@router.post("/skip")
async def skip_item(request: SkipRequest):
    """Mark a document to be permanently skipped."""
    quarantine = get_quarantine()
    
    if not quarantine.is_quarantined(request.file_path):
        raise HTTPException(status_code=404, detail="Item not found in quarantine")
    
    success = quarantine.skip_permanently(request.file_path)
    
    return {
        "success": success,
        "message": "Item marked as permanently skipped" if success else "Failed to skip item",
    }


@router.delete("/release/{file_path:path}")
async def release_item(file_path: str):
    """Release a document from quarantine."""
    quarantine = get_quarantine()
    
    if not quarantine.is_quarantined(file_path):
        raise HTTPException(status_code=404, detail="Item not found in quarantine")
    
    success = quarantine.release(file_path)
    
    return {
        "success": success,
        "message": "Item released from quarantine" if success else "Failed to release item",
    }


@router.post("/cleanup")
async def cleanup_old(days: int = 30):
    """Remove old quarantine entries."""
    quarantine = get_quarantine()
    removed = quarantine.cleanup_old(days=days)
    
    return {
        "removed": removed,
        "message": f"Removed {removed} entries older than {days} days",
    }
