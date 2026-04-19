"""Core infrastructure for cairnsearch enhanced document processing."""
from .models import (
    ProcessingStatus,
    PageType,
    OCRConfidence,
    DocumentVersion,
    ProcessingResult,
    PageInfo,
    ChunkMetadata,
    ExtractionMetadata,
    FailureManifest,
    ProcessingMetrics,
    SystemHealth,
    GuardrailLimits,
)
from .exceptions import (
    ProcessingError,
    GuardrailExceeded,
    SubprocessCrash,
    QuarantineError,
    SecurityError,
)
from .guardrails import GuardrailEnforcer, check_guardrails
from .subprocess_runner import SubprocessRunner, run_in_subprocess
from .quarantine import QuarantineManager
from .progress import ProgressTracker
from .deduplication import DeduplicationManager

__all__ = [
    # Models
    "ProcessingStatus",
    "PageType", 
    "OCRConfidence",
    "DocumentVersion",
    "ProcessingResult",
    "PageInfo",
    "ChunkMetadata",
    "ExtractionMetadata",
    "FailureManifest",
    "ProcessingMetrics",
    "SystemHealth",
    "GuardrailLimits",
    # Exceptions
    "ProcessingError",
    "GuardrailExceeded",
    "SubprocessCrash",
    "QuarantineError",
    "SecurityError",
    # Managers
    "GuardrailEnforcer",
    "check_guardrails",
    "SubprocessRunner",
    "run_in_subprocess",
    "QuarantineManager",
    "ProgressTracker",
    "DeduplicationManager",
]
