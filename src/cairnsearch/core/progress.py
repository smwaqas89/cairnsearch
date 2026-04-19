"""Progress tracking for crash recovery and resumable indexing."""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any
from enum import Enum

from cairnsearch.config import get_config


logger = logging.getLogger(__name__)


class ProgressStage(Enum):
    """Processing stages for progress tracking."""
    QUEUED = "queued"
    EXTRACTING = "extracting"
    OCR = "ocr"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DocumentProgress:
    """Progress state for a single document."""
    file_path: str
    filename: str
    stage: ProgressStage
    started_at: datetime
    updated_at: datetime
    
    # Stage-specific progress
    total_pages: int = 0
    processed_pages: int = 0
    total_chunks: int = 0
    processed_chunks: int = 0
    total_embeddings: int = 0
    processed_embeddings: int = 0
    
    # Checkpoints
    last_completed_page: int = -1
    last_completed_chunk: int = -1
    last_completed_embedding: int = -1
    
    # Error tracking
    error: Optional[str] = None
    retry_count: int = 0
    
    # Partial results
    extracted_text: Optional[str] = None
    chunks_data: Optional[str] = None  # JSON serialized
    
    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "filename": self.filename,
            "stage": self.stage.value,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "total_pages": self.total_pages,
            "processed_pages": self.processed_pages,
            "total_chunks": self.total_chunks,
            "processed_chunks": self.processed_chunks,
            "total_embeddings": self.total_embeddings,
            "processed_embeddings": self.processed_embeddings,
            "last_completed_page": self.last_completed_page,
            "last_completed_chunk": self.last_completed_chunk,
            "last_completed_embedding": self.last_completed_embedding,
            "error": self.error,
            "retry_count": self.retry_count,
            "extracted_text": self.extracted_text,
            "chunks_data": self.chunks_data,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DocumentProgress":
        data = data.copy()
        data["stage"] = ProgressStage(data["stage"])
        data["started_at"] = datetime.fromisoformat(data["started_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ProgressTracker:
    """
    Tracks processing progress for crash recovery.
    
    Persists progress to disk so processing can resume after crashes.
    """
    
    PROGRESS_FILENAME = "progress.json"
    CHECKPOINT_INTERVAL = 5  # Save checkpoint every N items
    
    def __init__(self, progress_path: Optional[Path] = None):
        config = get_config()
        self.progress_path = progress_path or (
            config.get_data_dir() / "progress"
        )
        self.progress_path.mkdir(parents=True, exist_ok=True)
        
        self._progress_file = self.progress_path / self.PROGRESS_FILENAME
        self._progress: Dict[str, DocumentProgress] = {}
        self._dirty = False
        self._last_save = time.time()
        
        self._load_progress()
    
    def _load_progress(self) -> None:
        """Load progress from disk."""
        if not self._progress_file.exists():
            return
        
        try:
            with open(self._progress_file, 'r') as f:
                data = json.load(f)
            
            for file_path, progress_data in data.items():
                try:
                    self._progress[file_path] = DocumentProgress.from_dict(progress_data)
                except Exception as e:
                    logger.warning(f"Failed to load progress for {file_path}: {e}")
            
            logger.info(f"Loaded progress for {len(self._progress)} documents")
        except Exception as e:
            logger.error(f"Failed to load progress file: {e}")
    
    def _save_progress(self, force: bool = False) -> None:
        """Save progress to disk."""
        if not self._dirty and not force:
            return
        
        # Rate limit saves
        if not force and time.time() - self._last_save < 1.0:
            return
        
        try:
            data = {
                file_path: progress.to_dict()
                for file_path, progress in self._progress.items()
            }
            
            # Atomic write
            temp_file = self._progress_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)
            
            temp_file.replace(self._progress_file)
            self._dirty = False
            self._last_save = time.time()
        except Exception as e:
            logger.error(f"Failed to save progress: {e}")
    
    def start_document(
        self,
        file_path: str,
        filename: str,
        total_pages: int = 0,
    ) -> DocumentProgress:
        """Start tracking a new document."""
        file_path = str(file_path)
        
        progress = DocumentProgress(
            file_path=file_path,
            filename=filename,
            stage=ProgressStage.EXTRACTING,
            started_at=datetime.now(),
            updated_at=datetime.now(),
            total_pages=total_pages,
        )
        
        self._progress[file_path] = progress
        self._dirty = True
        self._save_progress()
        
        return progress
    
    def get_progress(self, file_path: str) -> Optional[DocumentProgress]:
        """Get progress for a document."""
        return self._progress.get(str(file_path))
    
    def update_stage(
        self,
        file_path: str,
        stage: ProgressStage,
        **kwargs,
    ) -> Optional[DocumentProgress]:
        """Update processing stage."""
        file_path = str(file_path)
        progress = self._progress.get(file_path)
        
        if progress is None:
            return None
        
        progress.stage = stage
        progress.updated_at = datetime.now()
        
        # Update any additional fields
        for key, value in kwargs.items():
            if hasattr(progress, key):
                setattr(progress, key, value)
        
        self._dirty = True
        self._save_progress()
        
        return progress
    
    def update_page_progress(
        self,
        file_path: str,
        processed_pages: int,
        total_pages: Optional[int] = None,
    ) -> None:
        """Update page processing progress."""
        file_path = str(file_path)
        progress = self._progress.get(file_path)
        
        if progress is None:
            return
        
        progress.processed_pages = processed_pages
        progress.last_completed_page = processed_pages - 1
        progress.updated_at = datetime.now()
        
        if total_pages is not None:
            progress.total_pages = total_pages
        
        self._dirty = True
        
        # Checkpoint periodically
        if processed_pages % self.CHECKPOINT_INTERVAL == 0:
            self._save_progress()
    
    def update_chunk_progress(
        self,
        file_path: str,
        processed_chunks: int,
        total_chunks: Optional[int] = None,
    ) -> None:
        """Update chunk processing progress."""
        file_path = str(file_path)
        progress = self._progress.get(file_path)
        
        if progress is None:
            return
        
        progress.processed_chunks = processed_chunks
        progress.last_completed_chunk = processed_chunks - 1
        progress.updated_at = datetime.now()
        
        if total_chunks is not None:
            progress.total_chunks = total_chunks
        
        self._dirty = True
        
        if processed_chunks % self.CHECKPOINT_INTERVAL == 0:
            self._save_progress()
    
    def update_embedding_progress(
        self,
        file_path: str,
        processed_embeddings: int,
        total_embeddings: Optional[int] = None,
    ) -> None:
        """Update embedding progress."""
        file_path = str(file_path)
        progress = self._progress.get(file_path)
        
        if progress is None:
            return
        
        progress.processed_embeddings = processed_embeddings
        progress.last_completed_embedding = processed_embeddings - 1
        progress.updated_at = datetime.now()
        
        if total_embeddings is not None:
            progress.total_embeddings = total_embeddings
        
        self._dirty = True
        
        if processed_embeddings % self.CHECKPOINT_INTERVAL == 0:
            self._save_progress()
    
    def save_checkpoint(
        self,
        file_path: str,
        extracted_text: Optional[str] = None,
        chunks_data: Optional[List[dict]] = None,
    ) -> None:
        """Save a checkpoint with partial results."""
        file_path = str(file_path)
        progress = self._progress.get(file_path)
        
        if progress is None:
            return
        
        if extracted_text is not None:
            progress.extracted_text = extracted_text
        
        if chunks_data is not None:
            progress.chunks_data = json.dumps(chunks_data)
        
        progress.updated_at = datetime.now()
        self._dirty = True
        self._save_progress(force=True)
    
    def complete_document(self, file_path: str) -> None:
        """Mark document as completed and remove from progress."""
        file_path = str(file_path)
        
        if file_path in self._progress:
            del self._progress[file_path]
            self._dirty = True
            self._save_progress()
    
    def fail_document(self, file_path: str, error: str) -> None:
        """Mark document as failed."""
        file_path = str(file_path)
        progress = self._progress.get(file_path)
        
        if progress is None:
            return
        
        progress.stage = ProgressStage.FAILED
        progress.error = error
        progress.retry_count += 1
        progress.updated_at = datetime.now()
        
        self._dirty = True
        self._save_progress(force=True)
    
    def get_incomplete_documents(self) -> List[DocumentProgress]:
        """Get all documents with incomplete processing."""
        return [
            p for p in self._progress.values()
            if p.stage not in [ProgressStage.COMPLETED, ProgressStage.FAILED]
        ]
    
    def get_failed_documents(self) -> List[DocumentProgress]:
        """Get all failed documents."""
        return [
            p for p in self._progress.values()
            if p.stage == ProgressStage.FAILED
        ]
    
    def get_resumable_documents(self, max_retries: int = 3) -> List[DocumentProgress]:
        """Get documents that can be resumed."""
        incomplete = self.get_incomplete_documents()
        failed = [
            p for p in self.get_failed_documents()
            if p.retry_count < max_retries
        ]
        return incomplete + failed
    
    def get_stats(self) -> dict:
        """Get progress statistics."""
        total = len(self._progress)
        
        by_stage = {}
        for progress in self._progress.values():
            stage = progress.stage.value
            by_stage[stage] = by_stage.get(stage, 0) + 1
        
        return {
            "total": total,
            "by_stage": by_stage,
            "incomplete": len(self.get_incomplete_documents()),
            "failed": len(self.get_failed_documents()),
            "resumable": len(self.get_resumable_documents()),
        }
    
    def clear_completed(self) -> int:
        """Remove all completed entries."""
        to_remove = [
            path for path, progress in self._progress.items()
            if progress.stage == ProgressStage.COMPLETED
        ]
        
        for path in to_remove:
            del self._progress[path]
        
        if to_remove:
            self._dirty = True
            self._save_progress()
        
        return len(to_remove)
    
    def flush(self) -> None:
        """Force save all progress."""
        self._save_progress(force=True)
