"""Guardrail enforcement for document processing."""
import time
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Any
from functools import wraps

from .models import GuardrailLimits, ProcessingMetrics
from .exceptions import GuardrailExceeded


logger = logging.getLogger(__name__)


@dataclass
class GuardrailCheck:
    """Result of a guardrail check."""
    passed: bool
    limit_name: str
    limit_value: int | float
    actual_value: int | float
    message: str = ""


class GuardrailEnforcer:
    """Enforces processing guardrails."""
    
    def __init__(self, limits: Optional[GuardrailLimits] = None):
        self.limits = limits or GuardrailLimits()
        self._start_time: Optional[float] = None
        self._current_tokens = 0
        self._current_cost = 0.0
        self._current_chunks = 0
    
    def start_processing(self) -> None:
        """Start timing for processing."""
        self._start_time = time.time()
        self._current_tokens = 0
        self._current_cost = 0.0
        self._current_chunks = 0
    
    def check_file_size(self, size_bytes: int) -> GuardrailCheck:
        """Check file size limit."""
        max_bytes = self.limits.max_file_size_mb * 1024 * 1024
        passed = size_bytes <= max_bytes
        return GuardrailCheck(
            passed=passed,
            limit_name="max_file_size_mb",
            limit_value=self.limits.max_file_size_mb,
            actual_value=size_bytes / (1024 * 1024),
            message=f"File size {size_bytes / (1024*1024):.1f}MB exceeds limit {self.limits.max_file_size_mb}MB"
            if not passed else ""
        )
    
    def check_page_count(self, page_count: int) -> GuardrailCheck:
        """Check page count limit."""
        passed = page_count <= self.limits.max_pages
        return GuardrailCheck(
            passed=passed,
            limit_name="max_pages",
            limit_value=self.limits.max_pages,
            actual_value=page_count,
            message=f"Page count {page_count} exceeds limit {self.limits.max_pages}"
            if not passed else ""
        )
    
    def check_char_count(self, char_count: int) -> GuardrailCheck:
        """Check character count limit."""
        passed = char_count <= self.limits.max_chars_per_document
        return GuardrailCheck(
            passed=passed,
            limit_name="max_chars_per_document",
            limit_value=self.limits.max_chars_per_document,
            actual_value=char_count,
            message=f"Character count {char_count:,} exceeds limit {self.limits.max_chars_per_document:,}"
            if not passed else ""
        )
    
    def check_token_count(self, token_count: int) -> GuardrailCheck:
        """Check token count limit."""
        passed = token_count <= self.limits.max_tokens_per_document
        return GuardrailCheck(
            passed=passed,
            limit_name="max_tokens_per_document", 
            limit_value=self.limits.max_tokens_per_document,
            actual_value=token_count,
            message=f"Token count {token_count:,} exceeds limit {self.limits.max_tokens_per_document:,}"
            if not passed else ""
        )
    
    def check_chunk_count(self, chunk_count: int) -> GuardrailCheck:
        """Check chunk count limit."""
        passed = chunk_count <= self.limits.max_chunks_per_document
        return GuardrailCheck(
            passed=passed,
            limit_name="max_chunks_per_document",
            limit_value=self.limits.max_chunks_per_document,
            actual_value=chunk_count,
            message=f"Chunk count {chunk_count} exceeds limit {self.limits.max_chunks_per_document}"
            if not passed else ""
        )
    
    def check_processing_time(self) -> GuardrailCheck:
        """Check processing time limit."""
        if self._start_time is None:
            return GuardrailCheck(
                passed=True,
                limit_name="max_processing_time_seconds",
                limit_value=self.limits.max_processing_time_seconds,
                actual_value=0,
            )
        
        elapsed = time.time() - self._start_time
        passed = elapsed <= self.limits.max_processing_time_seconds
        return GuardrailCheck(
            passed=passed,
            limit_name="max_processing_time_seconds",
            limit_value=self.limits.max_processing_time_seconds,
            actual_value=elapsed,
            message=f"Processing time {elapsed:.1f}s exceeds limit {self.limits.max_processing_time_seconds}s"
            if not passed else ""
        )
    
    def check_sheet_count(self, sheet_count: int) -> GuardrailCheck:
        """Check Excel sheet count limit."""
        passed = sheet_count <= self.limits.max_sheets
        return GuardrailCheck(
            passed=passed,
            limit_name="max_sheets",
            limit_value=self.limits.max_sheets,
            actual_value=sheet_count,
            message=f"Sheet count {sheet_count} exceeds limit {self.limits.max_sheets}"
            if not passed else ""
        )
    
    def check_row_count(self, row_count: int) -> GuardrailCheck:
        """Check Excel row count limit."""
        passed = row_count <= self.limits.max_rows_per_sheet
        return GuardrailCheck(
            passed=passed,
            limit_name="max_rows_per_sheet",
            limit_value=self.limits.max_rows_per_sheet,
            actual_value=row_count,
            message=f"Row count {row_count:,} exceeds limit {self.limits.max_rows_per_sheet:,}"
            if not passed else ""
        )
    
    def check_ocr_pages(self, ocr_pages: int) -> GuardrailCheck:
        """Check OCR page count limit."""
        passed = ocr_pages <= self.limits.max_ocr_pages
        return GuardrailCheck(
            passed=passed,
            limit_name="max_ocr_pages",
            limit_value=self.limits.max_ocr_pages,
            actual_value=ocr_pages,
            message=f"OCR page count {ocr_pages} exceeds limit {self.limits.max_ocr_pages}"
            if not passed else ""
        )
    
    def check_cost(self, cost_usd: float) -> GuardrailCheck:
        """Check cost limit."""
        passed = cost_usd <= self.limits.max_cost_per_doc_usd
        return GuardrailCheck(
            passed=passed,
            limit_name="max_cost_per_doc_usd",
            limit_value=self.limits.max_cost_per_doc_usd,
            actual_value=cost_usd,
            message=f"Cost ${cost_usd:.4f} exceeds limit ${self.limits.max_cost_per_doc_usd:.2f}"
            if not passed else ""
        )
    
    def add_tokens(self, tokens: int) -> None:
        """Track tokens for cost calculation."""
        self._current_tokens += tokens
    
    def add_chunks(self, chunks: int) -> None:
        """Track chunk count."""
        self._current_chunks += chunks
    
    def add_cost(self, cost: float) -> None:
        """Track cost."""
        self._current_cost += cost
    
    def enforce(self, check: GuardrailCheck, abort: bool = True) -> None:
        """Enforce a guardrail check, optionally aborting on failure."""
        if not check.passed:
            logger.warning(f"Guardrail exceeded: {check.message}")
            if abort:
                raise GuardrailExceeded(
                    message=check.message,
                    limit_name=check.limit_name,
                    limit_value=check.limit_value,
                    actual_value=check.actual_value,
                )
    
    def enforce_all(
        self,
        file_size: Optional[int] = None,
        page_count: Optional[int] = None,
        char_count: Optional[int] = None,
        token_count: Optional[int] = None,
        chunk_count: Optional[int] = None,
        sheet_count: Optional[int] = None,
        row_count: Optional[int] = None,
        ocr_pages: Optional[int] = None,
        cost_usd: Optional[float] = None,
        abort: bool = True,
    ) -> list[GuardrailCheck]:
        """Enforce multiple guardrails at once."""
        checks = []
        
        if file_size is not None:
            checks.append(self.check_file_size(file_size))
        if page_count is not None:
            checks.append(self.check_page_count(page_count))
        if char_count is not None:
            checks.append(self.check_char_count(char_count))
        if token_count is not None:
            checks.append(self.check_token_count(token_count))
        if chunk_count is not None:
            checks.append(self.check_chunk_count(chunk_count))
        if sheet_count is not None:
            checks.append(self.check_sheet_count(sheet_count))
        if row_count is not None:
            checks.append(self.check_row_count(row_count))
        if ocr_pages is not None:
            checks.append(self.check_ocr_pages(ocr_pages))
        if cost_usd is not None:
            checks.append(self.check_cost(cost_usd))
        
        # Always check processing time
        checks.append(self.check_processing_time())
        
        for check in checks:
            self.enforce(check, abort=abort)
        
        return checks


def check_guardrails(limits: Optional[GuardrailLimits] = None):
    """Decorator to enforce guardrails on a function."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            enforcer = GuardrailEnforcer(limits)
            enforcer.start_processing()
            
            # Inject enforcer into kwargs if function accepts it
            import inspect
            sig = inspect.signature(func)
            if 'guardrail_enforcer' in sig.parameters:
                kwargs['guardrail_enforcer'] = enforcer
            
            try:
                result = func(*args, **kwargs)
                return result
            except GuardrailExceeded:
                raise
            except Exception as e:
                # Check time limit on any exception
                enforcer.enforce(enforcer.check_processing_time())
                raise
        
        return wrapper
    return decorator
