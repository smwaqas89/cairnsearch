"""Core data models for enhanced document processing."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Any
import json


class ProcessingStatus(Enum):
    """Document processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"
    QUARANTINED = "quarantined"
    SKIPPED = "skipped"


class PageType(Enum):
    """Type classification for PDF pages."""
    DIGITAL = "digital"
    SCANNED = "scanned"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class OCRConfidence(Enum):
    """OCR confidence levels."""
    HIGH = "high"      # > 85%
    MEDIUM = "medium"  # 60-85%
    LOW = "low"        # < 60%


@dataclass
class DocumentVersion:
    """Tracks document versions for change detection."""
    file_hash: str           # SHA-256 of file
    content_hash: str        # SHA-256 of extracted content
    version: int
    created_at: datetime
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "file_hash": self.file_hash,
            "content_hash": self.content_hash,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class PageInfo:
    """Information about a single page."""
    page_num: int
    page_type: PageType
    text: str
    ocr_confidence: Optional[float] = None
    ocr_data: Optional[dict] = None  # Bounding boxes, reading order
    tables: list = field(default_factory=list)
    key_value_pairs: list = field(default_factory=list)
    checkboxes: list = field(default_factory=list)
    has_header: bool = False
    has_footer: bool = False
    warnings: list = field(default_factory=list)
    
    @property
    def confidence_level(self) -> OCRConfidence:
        """Get OCR confidence level."""
        if self.ocr_confidence is None:
            return OCRConfidence.HIGH
        if self.ocr_confidence > 0.85:
            return OCRConfidence.HIGH
        elif self.ocr_confidence > 0.60:
            return OCRConfidence.MEDIUM
        return OCRConfidence.LOW


@dataclass
class ChunkMetadata:
    """Metadata attached to each chunk."""
    chunk_id: str
    doc_id: int
    file_path: str
    filename: str
    page_num: Optional[int] = None
    section: Optional[str] = None
    chunk_type: str = "text"  # text, table, form_field, ocr
    ocr_confidence: Optional[float] = None
    is_ocr: bool = False
    table_id: Optional[str] = None
    row_numbers: Optional[list] = None  # For Excel
    sheet_name: Optional[str] = None    # For Excel
    bounding_box: Optional[dict] = None
    start_char: int = 0
    end_char: int = 0
    token_count: int = 0
    
    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "file_path": self.file_path,
            "filename": self.filename,
            "page_num": self.page_num,
            "section": self.section,
            "chunk_type": self.chunk_type,
            "ocr_confidence": self.ocr_confidence,
            "is_ocr": self.is_ocr,
            "table_id": self.table_id,
            "row_numbers": self.row_numbers,
            "sheet_name": self.sheet_name,
            "bounding_box": self.bounding_box,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "token_count": self.token_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "ChunkMetadata":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ExtractionMetadata:
    """Full extraction metadata for a document."""
    doc_id: Optional[int] = None
    file_path: str = ""
    filename: str = ""
    file_type: str = ""
    file_hash: str = ""
    content_hash: str = ""
    version: int = 1
    
    # Page info
    page_count: int = 0
    pages: list = field(default_factory=list)  # List[PageInfo]
    
    # Document metadata
    title: Optional[str] = None
    author: Optional[str] = None
    created_date: Optional[str] = None
    modified_date: Optional[str] = None
    
    # Processing info
    extraction_method: str = "direct"
    processing_time_ms: float = 0
    total_chars: int = 0
    total_tokens: int = 0
    chunk_count: int = 0
    
    # Quality indicators
    avg_ocr_confidence: Optional[float] = None
    low_confidence_pages: list = field(default_factory=list)
    has_tables: bool = False
    has_forms: bool = False
    
    # Warnings and issues
    warnings: list = field(default_factory=list)
    pii_detected: bool = False
    pii_tags: list = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "file_path": self.file_path,
            "filename": self.filename,
            "file_type": self.file_type,
            "file_hash": self.file_hash,
            "content_hash": self.content_hash,
            "version": self.version,
            "page_count": self.page_count,
            "title": self.title,
            "author": self.author,
            "created_date": self.created_date,
            "modified_date": self.modified_date,
            "extraction_method": self.extraction_method,
            "processing_time_ms": self.processing_time_ms,
            "total_chars": self.total_chars,
            "total_tokens": self.total_tokens,
            "chunk_count": self.chunk_count,
            "avg_ocr_confidence": self.avg_ocr_confidence,
            "low_confidence_pages": self.low_confidence_pages,
            "has_tables": self.has_tables,
            "has_forms": self.has_forms,
            "warnings": self.warnings,
            "pii_detected": self.pii_detected,
            "pii_tags": self.pii_tags,
        }


@dataclass
class ProcessingResult:
    """Result from document processing."""
    success: bool
    text: Optional[str] = None
    pages: list = field(default_factory=list)  # List[PageInfo]
    chunks: list = field(default_factory=list)  # Ready-to-index chunks
    metadata: Optional[ExtractionMetadata] = None
    error: Optional[str] = None
    error_stage: Optional[str] = None
    warnings: list = field(default_factory=list)
    processing_time_ms: float = 0
    
    @property
    def should_quarantine(self) -> bool:
        """Check if document should be quarantined."""
        return not self.success and self.error is not None


@dataclass 
class FailureManifest:
    """Manifest for quarantined documents."""
    file_path: str
    filename: str
    reason: str
    stage: str  # extraction, ocr, chunking, embedding, etc.
    timestamp: datetime
    retry_count: int = 0
    max_retries: int = 3
    error_details: Optional[str] = None
    stack_trace: Optional[str] = None
    subprocess_exit_code: Optional[int] = None
    recoverable: bool = True
    metadata: dict = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "filename": self.filename,
            "reason": self.reason,
            "stage": self.stage,
            "timestamp": self.timestamp.isoformat(),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "error_details": self.error_details,
            "stack_trace": self.stack_trace,
            "subprocess_exit_code": self.subprocess_exit_code,
            "recoverable": self.recoverable,
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: dict) -> "FailureManifest":
        data = data.copy()
        if isinstance(data.get("timestamp"), str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ProcessingMetrics:
    """Per-document processing metrics."""
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
    table_count: int = 0
    
    # Errors
    error_count: int = 0
    warning_count: int = 0
    retry_count: int = 0
    
    # Quality
    avg_ocr_confidence: Optional[float] = None
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
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
            "table_count": self.table_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "retry_count": self.retry_count,
            "avg_ocr_confidence": self.avg_ocr_confidence,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class SystemHealth:
    """System-wide health metrics."""
    # Queue metrics
    pending_jobs: int = 0
    processing_jobs: int = 0
    failed_jobs: int = 0
    completed_jobs: int = 0
    
    # Error rates
    error_rate_1h: float = 0.0
    error_rate_24h: float = 0.0
    
    # Performance
    avg_processing_time_ms: float = 0
    documents_per_hour: float = 0
    
    # Resource usage
    quarantine_count: int = 0
    total_chunks: int = 0
    total_tokens: int = 0
    
    # Cost tracking
    embedding_cost_usd: float = 0.0
    llm_cost_usd: float = 0.0
    
    # Alerts
    alerts: list = field(default_factory=list)
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        return {
            "pending_jobs": self.pending_jobs,
            "processing_jobs": self.processing_jobs,
            "failed_jobs": self.failed_jobs,
            "completed_jobs": self.completed_jobs,
            "error_rate_1h": self.error_rate_1h,
            "error_rate_24h": self.error_rate_24h,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "documents_per_hour": self.documents_per_hour,
            "quarantine_count": self.quarantine_count,
            "total_chunks": self.total_chunks,
            "total_tokens": self.total_tokens,
            "embedding_cost_usd": self.embedding_cost_usd,
            "llm_cost_usd": self.llm_cost_usd,
            "alerts": self.alerts,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class GuardrailLimits:
    """Configurable guardrail limits."""
    # Page/row limits
    max_pages: int = 1000
    max_rows_per_sheet: int = 100000
    max_sheets: int = 50
    
    # Character/token limits
    max_chars_per_document: int = 10_000_000  # 10M chars
    max_tokens_per_document: int = 2_000_000  # 2M tokens
    max_chars_per_chunk: int = 8000
    max_tokens_per_chunk: int = 2000
    
    # Chunk limits
    max_chunks_per_document: int = 5000
    max_chunks_per_page: int = 100
    
    # Processing limits
    max_processing_time_seconds: int = 300  # 5 minutes
    max_ocr_pages: int = 200
    
    # Cost limits
    max_embedding_tokens_per_doc: int = 500_000
    max_cost_per_doc_usd: float = 1.0
    
    # File size limits
    max_file_size_mb: int = 500
    max_image_size_mb: int = 50
    
    @classmethod
    def from_config(cls, config: dict) -> "GuardrailLimits":
        return cls(**{k: v for k, v in config.items() if k in cls.__dataclass_fields__})
    
    def to_dict(self) -> dict:
        return {
            "max_pages": self.max_pages,
            "max_rows_per_sheet": self.max_rows_per_sheet,
            "max_sheets": self.max_sheets,
            "max_chars_per_document": self.max_chars_per_document,
            "max_tokens_per_document": self.max_tokens_per_document,
            "max_chars_per_chunk": self.max_chars_per_chunk,
            "max_tokens_per_chunk": self.max_tokens_per_chunk,
            "max_chunks_per_document": self.max_chunks_per_document,
            "max_chunks_per_page": self.max_chunks_per_page,
            "max_processing_time_seconds": self.max_processing_time_seconds,
            "max_ocr_pages": self.max_ocr_pages,
            "max_embedding_tokens_per_doc": self.max_embedding_tokens_per_doc,
            "max_cost_per_doc_usd": self.max_cost_per_doc_usd,
            "max_file_size_mb": self.max_file_size_mb,
            "max_image_size_mb": self.max_image_size_mb,
        }
