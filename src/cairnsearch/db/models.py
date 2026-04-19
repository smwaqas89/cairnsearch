"""Database models as dataclasses."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import json


@dataclass
class FileMeta:
    """File metadata for change detection."""
    path: str
    hash: str
    size_bytes: int
    file_mtime: float
    indexed_at: Optional[str] = None
    status: str = "pending"
    error_msg: Optional[str] = None
    needs_ocr: bool = False

    def to_tuple(self) -> tuple:
        return (
            self.path, self.hash, self.size_bytes, self.file_mtime,
            self.indexed_at, self.status, self.error_msg, self.needs_ocr
        )


@dataclass
class Document:
    """Indexed document."""
    id: Optional[int] = None
    file_path: str = ""
    filename: str = ""
    file_type: str = ""
    content: Optional[str] = None
    page_count: Optional[int] = None
    doc_title: Optional[str] = None
    doc_author: Optional[str] = None
    doc_created: Optional[str] = None
    doc_modified: Optional[str] = None
    detected_dates: list[str] = field(default_factory=list)
    extraction_method: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_insert_tuple(self) -> tuple:
        return (
            self.file_path, self.filename, self.file_type, self.content,
            self.page_count, self.doc_title, self.doc_author, self.doc_created,
            self.doc_modified, json.dumps(self.detected_dates), self.extraction_method
        )

    @classmethod
    def from_row(cls, row) -> "Document":
        dates = row["detected_dates"]
        if dates:
            dates = json.loads(dates)
        else:
            dates = []
        return cls(
            id=row["id"],
            file_path=row["file_path"],
            filename=row["filename"],
            file_type=row["file_type"],
            content=row["content"],
            page_count=row["page_count"],
            doc_title=row["doc_title"],
            doc_author=row["doc_author"],
            doc_created=row["doc_created"],
            doc_modified=row["doc_modified"],
            detected_dates=dates,
            extraction_method=row["extraction_method"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass
class Job:
    """Job queue entry."""
    id: Optional[int] = None
    file_path: str = ""
    job_type: str = "index"  # index, reindex, delete
    priority: int = 0
    status: str = "pending"  # pending, processing, done, failed
    attempts: int = 0
    max_attempts: int = 3
    error_msg: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_insert_tuple(self) -> tuple:
        return (self.file_path, self.job_type, self.priority)

    @classmethod
    def from_row(cls, row) -> "Job":
        return cls(
            id=row["id"],
            file_path=row["file_path"],
            job_type=row["job_type"],
            priority=row["priority"],
            status=row["status"],
            attempts=row["attempts"],
            max_attempts=row["max_attempts"],
            error_msg=row["error_msg"],
            created_at=row["created_at"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
        )


@dataclass
class SearchResult:
    """Search result with snippets."""
    id: int
    file_path: str
    filename: str
    file_type: str
    score: float
    snippets: list[str]
    doc_title: Optional[str] = None
    doc_author: Optional[str] = None
    doc_created: Optional[str] = None
    page_count: Optional[int] = None


@dataclass
class SearchResponse:
    """Complete search response."""
    query: str
    total: int
    page: int
    page_size: int
    took_ms: float
    results: list[SearchResult]
