"""Structured logging for document processing."""
import json
import logging
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, Generator
import threading


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields
        if hasattr(record, "structured_data"):
            log_data.update(record.structured_data)
        
        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add context from thread-local storage
        ctx = _log_context.get()
        if ctx:
            log_data["context"] = ctx
        
        return json.dumps(log_data)


@dataclass
class LogContext:
    """Context for structured logging."""
    doc_id: Optional[int] = None
    file_path: Optional[str] = None
    filename: Optional[str] = None
    stage: Optional[str] = None
    operation: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {}
        if self.doc_id is not None:
            result["doc_id"] = self.doc_id
        if self.file_path:
            result["file_path"] = self.file_path
        if self.filename:
            result["filename"] = self.filename
        if self.stage:
            result["stage"] = self.stage
        if self.operation:
            result["operation"] = self.operation
        result.update(self.extra)
        return result


# Thread-local storage for log context
_log_context = threading.local()


def _get_context() -> Optional[Dict[str, Any]]:
    """Get current log context."""
    ctx = getattr(_log_context, "context", None)
    if ctx:
        return ctx.to_dict()
    return None


_log_context.get = _get_context


class StructuredLogger:
    """
    Structured logger for document processing.
    
    Features:
    - JSON formatted output
    - Context propagation
    - Timing measurements
    - Document/stage context
    """
    
    def __init__(
        self,
        name: str = "cairnsearch",
        level: int = logging.INFO,
        structured: bool = True,
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)
        
        if structured:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(StructuredFormatter())
            self.logger.addHandler(handler)
    
    @contextmanager
    def context(
        self,
        doc_id: Optional[int] = None,
        file_path: Optional[str] = None,
        filename: Optional[str] = None,
        stage: Optional[str] = None,
        operation: Optional[str] = None,
        **extra,
    ) -> Generator[None, None, None]:
        """Context manager for setting log context."""
        old_context = getattr(_log_context, "context", None)
        
        _log_context.context = LogContext(
            doc_id=doc_id,
            file_path=file_path,
            filename=filename,
            stage=stage,
            operation=operation,
            extra=extra,
        )
        
        try:
            yield
        finally:
            _log_context.context = old_context
    
    @contextmanager
    def timed(
        self,
        operation: str,
        level: int = logging.INFO,
    ) -> Generator[Dict[str, Any], None, None]:
        """Context manager for timing operations."""
        timing = {"operation": operation, "start_time": time.time()}
        
        try:
            yield timing
        finally:
            timing["duration_ms"] = (time.time() - timing["start_time"]) * 1000
            self.log(
                level,
                f"{operation} completed",
                duration_ms=timing["duration_ms"],
            )
    
    def log(
        self,
        level: int,
        message: str,
        **kwargs,
    ) -> None:
        """Log with structured data."""
        extra = {"structured_data": kwargs}
        self.logger.log(level, message, extra=extra)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info level."""
        self.log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning level."""
        self.log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error level."""
        self.log(logging.ERROR, message, **kwargs)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug level."""
        self.log(logging.DEBUG, message, **kwargs)
    
    def document_start(
        self,
        doc_id: int,
        file_path: str,
        filename: str,
    ) -> None:
        """Log document processing start."""
        self.info(
            "Document processing started",
            doc_id=doc_id,
            file_path=file_path,
            filename=filename,
            stage="start",
        )
    
    def document_complete(
        self,
        doc_id: int,
        filename: str,
        duration_ms: float,
        chunks: int,
        tokens: int,
    ) -> None:
        """Log document processing completion."""
        self.info(
            "Document processing completed",
            doc_id=doc_id,
            filename=filename,
            stage="complete",
            duration_ms=duration_ms,
            chunks=chunks,
            tokens=tokens,
        )
    
    def document_error(
        self,
        doc_id: int,
        filename: str,
        error: str,
        stage: str,
    ) -> None:
        """Log document processing error."""
        self.error(
            "Document processing failed",
            doc_id=doc_id,
            filename=filename,
            stage=stage,
            error=error,
        )
    
    def extraction_complete(
        self,
        doc_id: int,
        filename: str,
        method: str,
        pages: int,
        duration_ms: float,
    ) -> None:
        """Log extraction completion."""
        self.info(
            "Extraction completed",
            doc_id=doc_id,
            filename=filename,
            stage="extraction",
            method=method,
            pages=pages,
            duration_ms=duration_ms,
        )
    
    def ocr_complete(
        self,
        doc_id: int,
        filename: str,
        pages_processed: int,
        avg_confidence: float,
        duration_ms: float,
    ) -> None:
        """Log OCR completion."""
        self.info(
            "OCR completed",
            doc_id=doc_id,
            filename=filename,
            stage="ocr",
            pages_processed=pages_processed,
            avg_confidence=avg_confidence,
            duration_ms=duration_ms,
        )
    
    def chunking_complete(
        self,
        doc_id: int,
        filename: str,
        chunks: int,
        duration_ms: float,
    ) -> None:
        """Log chunking completion."""
        self.info(
            "Chunking completed",
            doc_id=doc_id,
            filename=filename,
            stage="chunking",
            chunks=chunks,
            duration_ms=duration_ms,
        )
    
    def embedding_complete(
        self,
        doc_id: int,
        filename: str,
        embeddings: int,
        duration_ms: float,
    ) -> None:
        """Log embedding completion."""
        self.info(
            "Embedding completed",
            doc_id=doc_id,
            filename=filename,
            stage="embedding",
            embeddings=embeddings,
            duration_ms=duration_ms,
        )


def get_structured_logger(name: str = "cairnsearch") -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)
