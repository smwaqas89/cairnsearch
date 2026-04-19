"""Enhanced progress tracking API with Server-Sent Events."""
import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from enum import Enum
import threading
import logging


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/progress", tags=["progress"])


class IndexingStage(str, Enum):
    """Stages of indexing process."""
    SCANNING = "scanning"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    SAVING = "saving"
    COMPLETE = "complete"
    FAILED = "failed"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class FileStatus(str, Enum):
    """Status of individual file processing."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    WARNING = "warning"  # Success with issues (low OCR confidence)
    FAILED = "failed"
    SKIPPED = "skipped"


class FileProgress(BaseModel):
    """Progress info for a single file."""
    file_path: str
    filename: str
    status: FileStatus
    stage: Optional[str] = None
    progress_percent: int = 0
    chunks_created: int = 0
    ocr_confidence: Optional[float] = None
    error_message: Optional[str] = None
    time_taken_ms: Optional[float] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class IndexingSession(BaseModel):
    """Overall indexing session progress."""
    session_id: str
    status: IndexingStage
    folder_path: str
    
    # Counts
    total_files: int = 0
    processed_files: int = 0
    successful_files: int = 0
    warning_files: int = 0
    failed_files: int = 0
    skipped_files: int = 0
    
    # Progress
    overall_percent: int = 0
    current_file: Optional[str] = None
    current_stage: Optional[str] = None
    
    # Timing
    started_at: str
    estimated_remaining_seconds: Optional[int] = None
    files_per_second: float = 0
    
    # Results
    total_chunks: int = 0
    total_tokens: int = 0
    
    # Controls
    is_paused: bool = False
    is_cancelled: bool = False


# In-memory storage for active sessions
_sessions: Dict[str, IndexingSession] = {}
_file_progress: Dict[str, Dict[str, FileProgress]] = {}  # session_id -> {file_path -> progress}
_session_lock = threading.Lock()


def create_session(folder_path: str, total_files: int) -> str:
    """Create a new indexing session."""
    session_id = str(uuid.uuid4())[:8]
    
    session = IndexingSession(
        session_id=session_id,
        status=IndexingStage.SCANNING,
        folder_path=folder_path,
        total_files=total_files,
        started_at=datetime.now().isoformat(),
    )
    
    with _session_lock:
        _sessions[session_id] = session
        _file_progress[session_id] = {}
    
    return session_id


def update_session(
    session_id: str,
    status: Optional[IndexingStage] = None,
    processed_files: Optional[int] = None,
    successful_files: Optional[int] = None,
    warning_files: Optional[int] = None,
    failed_files: Optional[int] = None,
    current_file: Optional[str] = None,
    current_stage: Optional[str] = None,
    total_chunks: Optional[int] = None,
    total_tokens: Optional[int] = None,
) -> Optional[IndexingSession]:
    """Update session progress."""
    with _session_lock:
        if session_id not in _sessions:
            return None
        
        session = _sessions[session_id]
        
        if status is not None:
            session.status = status
        if processed_files is not None:
            session.processed_files = processed_files
        if successful_files is not None:
            session.successful_files = successful_files
        if warning_files is not None:
            session.warning_files = warning_files
        if failed_files is not None:
            session.failed_files = failed_files
        if current_file is not None:
            session.current_file = current_file
        if current_stage is not None:
            session.current_stage = current_stage
        if total_chunks is not None:
            session.total_chunks = total_chunks
        if total_tokens is not None:
            session.total_tokens = total_tokens
        
        # Calculate percentages and rates
        if session.total_files > 0:
            session.overall_percent = int((session.processed_files / session.total_files) * 100)
        
        # Calculate processing rate
        started = datetime.fromisoformat(session.started_at)
        elapsed = (datetime.now() - started).total_seconds()
        if elapsed > 0 and session.processed_files > 0:
            session.files_per_second = session.processed_files / elapsed
            remaining = session.total_files - session.processed_files
            session.estimated_remaining_seconds = int(remaining / session.files_per_second)
        
        return session


def update_file_progress(
    session_id: str,
    file_path: str,
    filename: str,
    status: FileStatus,
    stage: Optional[str] = None,
    progress_percent: int = 0,
    chunks_created: int = 0,
    ocr_confidence: Optional[float] = None,
    error_message: Optional[str] = None,
    time_taken_ms: Optional[float] = None,
) -> None:
    """Update progress for a specific file."""
    with _session_lock:
        if session_id not in _file_progress:
            _file_progress[session_id] = {}
        
        now = datetime.now().isoformat()
        
        if file_path not in _file_progress[session_id]:
            _file_progress[session_id][file_path] = FileProgress(
                file_path=file_path,
                filename=filename,
                status=status,
                started_at=now,
            )
        
        fp = _file_progress[session_id][file_path]
        fp.status = status
        fp.stage = stage
        fp.progress_percent = progress_percent
        fp.chunks_created = chunks_created
        fp.ocr_confidence = ocr_confidence
        fp.error_message = error_message
        fp.time_taken_ms = time_taken_ms
        
        if status in [FileStatus.SUCCESS, FileStatus.WARNING, FileStatus.FAILED, FileStatus.SKIPPED]:
            fp.completed_at = now


def get_session(session_id: str) -> Optional[IndexingSession]:
    """Get session by ID."""
    with _session_lock:
        return _sessions.get(session_id)


def get_file_progress(session_id: str) -> List[FileProgress]:
    """Get all file progress for a session."""
    with _session_lock:
        if session_id not in _file_progress:
            return []
        return list(_file_progress[session_id].values())


def pause_session(session_id: str) -> bool:
    """Pause an indexing session."""
    with _session_lock:
        if session_id in _sessions:
            _sessions[session_id].is_paused = True
            _sessions[session_id].status = IndexingStage.PAUSED
            return True
        return False


def resume_session(session_id: str) -> bool:
    """Resume a paused session."""
    with _session_lock:
        if session_id in _sessions:
            _sessions[session_id].is_paused = False
            _sessions[session_id].status = IndexingStage.EXTRACTING
            return True
        return False


def cancel_session(session_id: str) -> bool:
    """Cancel an indexing session."""
    with _session_lock:
        if session_id in _sessions:
            _sessions[session_id].is_cancelled = True
            _sessions[session_id].status = IndexingStage.CANCELLED
            return True
        return False


def cleanup_session(session_id: str) -> None:
    """Clean up a completed session."""
    with _session_lock:
        _sessions.pop(session_id, None)
        _file_progress.pop(session_id, None)


# API Endpoints

@router.get("/sessions")
async def list_sessions() -> Dict[str, Any]:
    """List all active indexing sessions."""
    with _session_lock:
        return {
            "sessions": [s.model_dump() for s in _sessions.values()],
            "total": len(_sessions),
        }


@router.get("/sessions/{session_id}")
async def get_session_status(session_id: str) -> Dict[str, Any]:
    """Get detailed status of an indexing session."""
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    files = get_file_progress(session_id)
    
    return {
        "session": session.model_dump(),
        "files": [f.model_dump() for f in files[-50:]],  # Last 50 files
        "total_files_tracked": len(files),
    }


@router.get("/sessions/{session_id}/stream")
async def stream_session_progress(session_id: str):
    """Stream session progress via Server-Sent Events."""
    
    async def event_generator():
        last_processed = 0
        last_file_count = 0
        
        while True:
            session = get_session(session_id)
            
            if not session:
                yield f"data: {json.dumps({'error': 'Session not found'})}\n\n"
                break
            
            # Send session update
            yield f"data: {json.dumps({'type': 'session', 'data': session.model_dump()})}\n\n"
            
            # Send new file updates
            files = get_file_progress(session_id)
            if len(files) > last_file_count:
                new_files = files[last_file_count:]
                for f in new_files:
                    yield f"data: {json.dumps({'type': 'file', 'data': f.model_dump()})}\n\n"
                last_file_count = len(files)
            
            # Check if complete
            if session.status in [IndexingStage.COMPLETE, IndexingStage.FAILED, IndexingStage.CANCELLED]:
                yield f"data: {json.dumps({'type': 'complete', 'data': session.model_dump()})}\n\n"
                break
            
            await asyncio.sleep(0.5)  # Update every 500ms
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


@router.post("/sessions/{session_id}/pause")
async def pause_indexing(session_id: str) -> Dict[str, Any]:
    """Pause an indexing session."""
    if pause_session(session_id):
        return {"message": "Session paused", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/sessions/{session_id}/resume")
async def resume_indexing(session_id: str) -> Dict[str, Any]:
    """Resume a paused session."""
    if resume_session(session_id):
        return {"message": "Session resumed", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@router.post("/sessions/{session_id}/cancel")
async def cancel_indexing(session_id: str) -> Dict[str, Any]:
    """Cancel an indexing session."""
    if cancel_session(session_id):
        return {"message": "Session cancelled", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """Delete/cleanup a session."""
    cleanup_session(session_id)
    return {"message": "Session cleaned up", "session_id": session_id}
