"""Enhanced index manager with all new features integrated."""
import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
import logging

from cairnsearch.config import get_config
from cairnsearch.db import Database, Document


logger = logging.getLogger(__name__)


class EnhancedIndexManager:
    """
    Enhanced index manager with subprocess isolation, guardrails,
    quarantine, deduplication, progress tracking, PII detection,
    structured logging, metrics, and alerting.
    """
    
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.config = get_config()
        
        # Lazy load components to avoid import cycles
        self._guardrails = None
        self._quarantine = None
        self._progress = None
        self._dedup = None
        self._pdf_processor = None
        self._excel_processor = None
        self._image_processor = None
        self._chunker = None
        self._normalizer = None
        self._pii_detector = None
        self._audit = None
        self._metrics = None
        self._alerts = None
        self._slog = None
        self._rag_engine = None
        self._registry = None
    
    @property
    def guardrails(self):
        if self._guardrails is None:
            from cairnsearch.core import GuardrailEnforcer, GuardrailLimits
            self._guardrails = GuardrailEnforcer(GuardrailLimits())
        return self._guardrails
    
    @property
    def quarantine(self):
        if self._quarantine is None:
            from cairnsearch.core import QuarantineManager
            self._quarantine = QuarantineManager()
        return self._quarantine
    
    @property
    def progress(self):
        if self._progress is None:
            from cairnsearch.core import ProgressTracker
            self._progress = ProgressTracker()
        return self._progress
    
    @property
    def dedup(self):
        if self._dedup is None:
            from cairnsearch.core import DeduplicationManager
            self._dedup = DeduplicationManager()
        return self._dedup
    
    @property
    def pdf_processor(self):
        if self._pdf_processor is None:
            from cairnsearch.processing import EnhancedPDFProcessor
            self._pdf_processor = EnhancedPDFProcessor()
        return self._pdf_processor
    
    @property
    def excel_processor(self):
        if self._excel_processor is None:
            from cairnsearch.processing import EnhancedExcelProcessor
            self._excel_processor = EnhancedExcelProcessor()
        return self._excel_processor
    
    @property
    def image_processor(self):
        if self._image_processor is None:
            from cairnsearch.processing import EnhancedImageProcessor
            self._image_processor = EnhancedImageProcessor()
        return self._image_processor
    
    @property
    def chunker(self):
        if self._chunker is None:
            from cairnsearch.processing import SemanticChunker
            self._chunker = SemanticChunker()
        return self._chunker
    
    @property
    def normalizer(self):
        if self._normalizer is None:
            from cairnsearch.processing import TextNormalizer
            self._normalizer = TextNormalizer()
        return self._normalizer
    
    @property
    def pii_detector(self):
        if self._pii_detector is None:
            from cairnsearch.security import PIIDetector
            self._pii_detector = PIIDetector()
        return self._pii_detector
    
    @property
    def audit(self):
        if self._audit is None:
            from cairnsearch.security import AuditLogger
            self._audit = AuditLogger()
        return self._audit
    
    @property
    def metrics(self):
        if self._metrics is None:
            from cairnsearch.monitoring import MetricsCollector
            self._metrics = MetricsCollector()
        return self._metrics
    
    @property
    def alerts(self):
        if self._alerts is None:
            from cairnsearch.monitoring import AlertManager
            self._alerts = AlertManager()
        return self._alerts
    
    @property
    def slog(self):
        if self._slog is None:
            from cairnsearch.monitoring import StructuredLogger
            self._slog = StructuredLogger()
        return self._slog
    
    @property
    def registry(self):
        if self._registry is None:
            from cairnsearch.extractors import get_registry
            self._registry = get_registry()
        return self._registry
    
    def _get_rag_engine(self):
        if self._rag_engine is None:
            try:
                from cairnsearch.rag import RAGEngine
                if self.config.rag.enabled:
                    self._rag_engine = RAGEngine(db=self.db)
            except Exception as e:
                logger.warning(f"RAG engine not available: {e}")
                self._rag_engine = False
        return self._rag_engine if self._rag_engine else None
    
    def index_file(self, file_path: Path) -> Tuple[bool, Optional[int]]:
        """Index a single file with all enhanced features."""
        from cairnsearch.core import GuardrailExceeded, SubprocessCrash
        from cairnsearch.core.models import ProcessingResult, ExtractionMetadata
        from cairnsearch.monitoring import DocumentMetrics
        from cairnsearch.security import AuditAction
        from cairnsearch.extractors import extract_dates
        
        file_path = Path(file_path).resolve()
        start_time = time.time()
        
        doc_metrics = DocumentMetrics(
            doc_id=0, file_path=str(file_path), filename=file_path.name
        )
        
        try:
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}")
                return False, None
            
            # Check file size
            size_bytes = file_path.stat().st_size
            self.guardrails.start_processing()
            self.guardrails.enforce(self.guardrails.check_file_size(size_bytes))
            
            # Compute file hash
            file_hash = self.dedup.compute_file_hash(file_path)
            
            # Check if unchanged
            changed, existing = self.dedup.check_file_changed(str(file_path), file_hash)
            if not changed:
                logger.debug(f"File unchanged: {file_path}")
                return True, None
            
            # Check quarantine
            if self.quarantine.is_quarantined(str(file_path)):
                if not self.quarantine.can_retry(str(file_path)):
                    logger.info(f"File permanently quarantined: {file_path}")
                    return False, None
                self.quarantine.increment_retry(str(file_path))
            
            # Start tracking
            self.progress.start_document(str(file_path), file_path.name)
            
            # Audit
            self.audit.log_action(
                AuditAction.EXTRACTION_START,
                resource_type="document",
                file_path=str(file_path),
            )
            
            # Process by type
            suffix = file_path.suffix.lower()
            extraction_start = time.time()
            
            if suffix == '.pdf':
                result = self.pdf_processor.process(file_path)
            elif suffix in ['.xlsx', '.xlsm', '.xls']:
                result = self.excel_processor.process(file_path)
            elif suffix in ['.png', '.jpg', '.jpeg', '.tiff', '.tif', '.bmp', '.gif', '.webp']:
                result = self.image_processor.process(file_path)
            else:
                result = self._legacy_extract(file_path)
            
            doc_metrics.extraction_time_ms = (time.time() - extraction_start) * 1000
            
            if not result.success:
                return self._handle_failure(
                    file_path, result.error, result.error_stage or "extraction",
                    doc_metrics, start_time
                )
            
            # Normalize text
            text = self.normalizer.normalize(result.text) if result.text else ""
            content_hash = self.dedup.compute_content_hash(text)
            
            # Detect PII
            pii_detected = False
            pii_tags = []
            if text:
                pii_matches = self.pii_detector.detect(text)
                if pii_matches:
                    pii_detected = True
                    pii_tags = list(set(m.pii_type.value for m in pii_matches))
            
            # Extract metadata
            metadata = result.metadata
            doc_metrics.page_count = metadata.page_count if metadata else 0
            doc_metrics.char_count = len(text)
            
            if metadata and metadata.avg_ocr_confidence:
                doc_metrics.avg_ocr_confidence = metadata.avg_ocr_confidence
            
            # Extract dates
            detected_dates = extract_dates(text) if text else []
            
            # Create document record
            doc = Document(
                file_path=str(file_path),
                filename=file_path.name,
                file_type=suffix.lstrip("."),
                content=text,
                page_count=metadata.page_count if metadata else None,
                doc_title=metadata.title if metadata else None,
                doc_author=metadata.author if metadata else None,
                doc_created=metadata.created_date if metadata else None,
                doc_modified=metadata.modified_date if metadata else None,
                detected_dates=detected_dates,
                extraction_method=metadata.extraction_method if metadata else "direct",
            )
            
            # Upsert
            doc_id = self._upsert_document(
                doc, file_hash, content_hash, pii_detected, pii_tags, file_path.stat()
            )
            doc_metrics.doc_id = doc_id
            
            # Chunk
            chunking_start = time.time()
            chunks = self.chunker.chunk_document(
                doc_id=doc_id,
                file_path=str(file_path),
                filename=file_path.name,
                content=text,
                pages=result.pages if hasattr(result, 'pages') else None,
            )
            doc_metrics.chunking_time_ms = (time.time() - chunking_start) * 1000
            doc_metrics.chunk_count = len(chunks)
            
            # Check chunk explosion
            self.alerts.check_chunk_explosion(len(chunks), str(file_path), doc_id)
            
            # RAG index
            if chunks and text:
                embedding_start = time.time()
                self._index_for_rag(doc_id, str(file_path), file_path.name, text)
                doc_metrics.embedding_time_ms = (time.time() - embedding_start) * 1000
            
            doc_metrics.token_count = len(text) // 4
            
            # Register dedup
            self.dedup.register_document(
                str(file_path), file_hash, content_hash,
                {"doc_id": doc_id, "chunk_count": len(chunks)}
            )
            
            # Complete
            self.progress.complete_document(str(file_path))
            
            if self.quarantine.is_quarantined(str(file_path)):
                self.quarantine.release(str(file_path))
            
            doc_metrics.total_time_ms = (time.time() - start_time) * 1000
            self.metrics.record_document(doc_metrics)
            
            self.audit.log_action(
                AuditAction.EXTRACTION_COMPLETE,
                resource_type="document",
                resource_id=str(doc_id),
                file_path=str(file_path),
            )
            
            logger.info(f"Indexed: {file_path} (doc_id={doc_id}, chunks={len(chunks)})")
            return True, doc_id
            
        except GuardrailExceeded as e:
            return self._handle_failure(
                file_path, str(e), "guardrails", doc_metrics, start_time, recoverable=False
            )
        except SubprocessCrash as e:
            return self._handle_failure(
                file_path, str(e), "subprocess", doc_metrics, start_time,
                subprocess_exit_code=e.exit_code
            )
        except Exception as e:
            logger.exception(f"Error indexing {file_path}: {e}")
            return self._handle_failure(
                file_path, str(e), "unknown", doc_metrics, start_time,
                stack_trace=traceback.format_exc()
            )
    
    def _handle_failure(
        self, file_path, error, stage, metrics, start_time,
        recoverable=True, subprocess_exit_code=None, stack_trace=None
    ):
        from cairnsearch.security import AuditAction
        
        metrics.total_time_ms = (time.time() - start_time) * 1000
        metrics.error_count = 1
        self.metrics.record_document(metrics)
        self.progress.fail_document(str(file_path), error)
        
        manifest = self.quarantine.quarantine(
            str(file_path), reason=error, stage=stage,
            error_details=error, stack_trace=stack_trace,
            subprocess_exit_code=subprocess_exit_code,
        )
        
        self.alerts.check_repeated_failures(str(file_path), manifest.retry_count)
        
        self.audit.log_action(
            AuditAction.EXTRACTION_FAILED,
            file_path=str(file_path),
            success=False,
            error_message=error,
        )
        
        self._update_file_meta_error(str(file_path), "", file_path.stat(), error)
        return False, None
    
    def _legacy_extract(self, file_path):
        from cairnsearch.core.models import ProcessingResult, ExtractionMetadata
        
        if not self.registry.can_extract(file_path):
            return ProcessingResult(
                success=False,
                error=f"Unsupported file type: {file_path.suffix}",
                error_stage="validation",
            )
        
        result = self.registry.extract(file_path)
        
        if not result.success:
            return ProcessingResult(success=False, error=result.error, error_stage="extraction")
        
        metadata = ExtractionMetadata(
            file_path=str(file_path),
            filename=file_path.name,
            file_type=file_path.suffix.lower().lstrip('.'),
            page_count=result.page_count or 0,
            title=result.title,
            author=result.author,
            extraction_method=result.extraction_method,
        )
        
        return ProcessingResult(success=True, text=result.text, metadata=metadata)
    
    def _upsert_document(self, doc, file_hash, content_hash, pii_detected, pii_tags, stat):
        now = datetime.now().isoformat()
        
        with self.db.connection() as conn:
            conn.execute("""
                INSERT INTO files_meta (path, hash, content_hash, size_bytes, file_mtime, indexed_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'indexed')
                ON CONFLICT(path) DO UPDATE SET
                    hash = excluded.hash, content_hash = excluded.content_hash,
                    size_bytes = excluded.size_bytes, file_mtime = excluded.file_mtime,
                    indexed_at = excluded.indexed_at, status = 'indexed', error_msg = NULL
            """, (doc.file_path, file_hash, content_hash, stat.st_size, stat.st_mtime, now))
            
            conn.execute("""
                INSERT INTO documents (
                    file_path, filename, file_type, content, page_count,
                    doc_title, doc_author, doc_created, doc_modified,
                    detected_dates, extraction_method, pii_detected, pii_tags
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    filename = excluded.filename, file_type = excluded.file_type,
                    content = excluded.content, page_count = excluded.page_count,
                    doc_title = excluded.doc_title, doc_author = excluded.doc_author,
                    doc_created = excluded.doc_created, doc_modified = excluded.doc_modified,
                    detected_dates = excluded.detected_dates, extraction_method = excluded.extraction_method,
                    pii_detected = excluded.pii_detected, pii_tags = excluded.pii_tags,
                    updated_at = datetime('now')
            """, (
                doc.file_path, doc.filename, doc.file_type, doc.content, doc.page_count,
                doc.doc_title, doc.doc_author, doc.doc_created, doc.doc_modified,
                json.dumps(doc.detected_dates) if doc.detected_dates else None,
                doc.extraction_method, pii_detected,
                json.dumps(pii_tags) if pii_tags else None,
            ))
            
            conn.commit()
            result = conn.execute(
                "SELECT id FROM documents WHERE file_path = ?", (doc.file_path,)
            ).fetchone()
            return result[0] if result else None
    
    def _update_file_meta_error(self, path, file_hash, stat, error):
        now = datetime.now().isoformat()
        with self.db.connection() as conn:
            conn.execute("""
                INSERT INTO files_meta (path, hash, size_bytes, file_mtime, indexed_at, status, error_msg)
                VALUES (?, ?, ?, ?, ?, 'failed', ?)
                ON CONFLICT(path) DO UPDATE SET
                    indexed_at = excluded.indexed_at, status = 'failed', error_msg = excluded.error_msg
            """, (path, file_hash or "", stat.st_size, stat.st_mtime, now, error))
            conn.commit()
    
    def _index_for_rag(self, doc_id, file_path, filename, content):
        try:
            rag = self._get_rag_engine()
            if rag:
                return rag.index_document(doc_id=doc_id, file_path=file_path, filename=filename, content=content)
        except Exception as e:
            logger.warning(f"RAG indexing failed: {e}")
        return 0
    
    def delete_file(self, file_path: str) -> bool:
        from cairnsearch.security import AuditAction
        try:
            self.dedup.remove_document(file_path)
            with self.db.connection() as conn:
                conn.execute("DELETE FROM documents WHERE file_path = ?", (file_path,))
                conn.execute("DELETE FROM files_meta WHERE path = ?", (file_path,))
                conn.commit()
            if self.quarantine.is_quarantined(file_path):
                self.quarantine.release(file_path)
            self.audit.log_action(AuditAction.DOCUMENT_DELETE, file_path=file_path)
            logger.info(f"Deleted: {file_path}")
            return True
        except Exception as e:
            logger.exception(f"Error deleting {file_path}: {e}")
            return False
    
    def get_stats(self) -> dict:
        with self.db.connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            by_type = dict(conn.execute(
                "SELECT file_type, COUNT(*) FROM documents GROUP BY file_type"
            ).fetchall())
            pending = conn.execute("SELECT COUNT(*) FROM files_meta WHERE status = 'pending'").fetchone()[0]
            failed = conn.execute("SELECT COUNT(*) FROM files_meta WHERE status = 'failed'").fetchone()[0]
        
        return {
            "indexed_count": total, "pending": pending, "failed": failed, "by_type": by_type,
            "quarantine": self.quarantine.get_stats(),
            "deduplication": self.dedup.get_stats(),
            "metrics": self.metrics.get_session_stats(),
        }
