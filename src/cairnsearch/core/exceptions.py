"""Custom exceptions for document processing."""
from typing import Optional


class ProcessingError(Exception):
    """Base exception for document processing errors."""
    
    def __init__(
        self,
        message: str,
        stage: str = "unknown",
        recoverable: bool = True,
        details: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.recoverable = recoverable
        self.details = details


class GuardrailExceeded(ProcessingError):
    """Raised when processing exceeds guardrail limits."""
    
    def __init__(
        self,
        message: str,
        limit_name: str,
        limit_value: int | float,
        actual_value: int | float,
        stage: str = "validation",
    ):
        super().__init__(message, stage=stage, recoverable=False)
        self.limit_name = limit_name
        self.limit_value = limit_value
        self.actual_value = actual_value


class SubprocessCrash(ProcessingError):
    """Raised when a subprocess crashes (SIGSEGV, etc.)."""
    
    def __init__(
        self,
        message: str,
        exit_code: int,
        signal: Optional[int] = None,
        stdout: Optional[str] = None,
        stderr: Optional[str] = None,
        stage: str = "subprocess",
    ):
        super().__init__(message, stage=stage, recoverable=True)
        self.exit_code = exit_code
        self.signal = signal
        self.stdout = stdout
        self.stderr = stderr


class QuarantineError(ProcessingError):
    """Raised when quarantine operations fail."""
    
    def __init__(self, message: str, file_path: str):
        super().__init__(message, stage="quarantine", recoverable=False)
        self.file_path = file_path


class SecurityError(ProcessingError):
    """Raised for security-related issues."""
    
    def __init__(
        self,
        message: str,
        security_type: str = "general",
        file_path: Optional[str] = None,
    ):
        super().__init__(message, stage="security", recoverable=False)
        self.security_type = security_type
        self.file_path = file_path


class OCRError(ProcessingError):
    """Raised when OCR processing fails."""
    
    def __init__(
        self,
        message: str,
        page_num: Optional[int] = None,
        confidence: Optional[float] = None,
    ):
        super().__init__(message, stage="ocr", recoverable=True)
        self.page_num = page_num
        self.confidence = confidence


class EmbeddingError(ProcessingError):
    """Raised when embedding generation fails."""
    
    def __init__(
        self,
        message: str,
        provider: str = "unknown",
        batch_size: Optional[int] = None,
    ):
        super().__init__(message, stage="embedding", recoverable=True)
        self.provider = provider
        self.batch_size = batch_size


class ChunkingError(ProcessingError):
    """Raised when document chunking fails."""
    
    def __init__(
        self,
        message: str,
        chunk_index: Optional[int] = None,
    ):
        super().__init__(message, stage="chunking", recoverable=True)
        self.chunk_index = chunk_index


class ExtractionError(ProcessingError):
    """Raised when text extraction fails."""
    
    def __init__(
        self,
        message: str,
        file_type: str = "unknown",
        page_num: Optional[int] = None,
    ):
        super().__init__(message, stage="extraction", recoverable=True)
        self.file_type = file_type
        self.page_num = page_num


class RateLimitError(ProcessingError):
    """Raised when rate limits are hit."""
    
    def __init__(
        self,
        message: str,
        service: str,
        retry_after: Optional[float] = None,
    ):
        super().__init__(message, stage="rate_limit", recoverable=True)
        self.service = service
        self.retry_after = retry_after


class CostLimitError(ProcessingError):
    """Raised when cost limits are exceeded."""
    
    def __init__(
        self,
        message: str,
        current_cost: float,
        limit: float,
    ):
        super().__init__(message, stage="cost", recoverable=False)
        self.current_cost = current_cost
        self.limit = limit
