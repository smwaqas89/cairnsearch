"""PII (Personally Identifiable Information) detection."""
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional, Dict, Set
import logging


logger = logging.getLogger(__name__)


class PIIType(Enum):
    """Types of PII that can be detected."""
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    DATE_OF_BIRTH = "date_of_birth"
    PASSPORT = "passport"
    DRIVERS_LICENSE = "drivers_license"
    BANK_ACCOUNT = "bank_account"
    IP_ADDRESS = "ip_address"
    NAME = "name"
    MEDICAL_RECORD = "medical_record"


@dataclass
class PIIMatch:
    """A detected PII match."""
    pii_type: PIIType
    value: str
    start: int
    end: int
    confidence: float
    context: str  # Surrounding text
    
    def to_dict(self) -> Dict:
        return {
            "type": self.pii_type.value,
            "value": self.value,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
        }


class PIIDetector:
    """
    Detects PII in text using pattern matching and heuristics.
    
    Features:
    - Multiple PII type detection
    - Confidence scoring
    - Context extraction
    - Redaction support
    """
    
    # SSN patterns (various formats)
    SSN_PATTERNS = [
        r'\b\d{3}-\d{2}-\d{4}\b',  # 123-45-6789
        r'\b\d{3}\s\d{2}\s\d{4}\b',  # 123 45 6789
        r'\b\d{9}\b',  # 123456789 (context-dependent)
    ]
    
    # Credit card patterns
    CC_PATTERNS = [
        r'\b4\d{3}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Visa
        r'\b5[1-5]\d{2}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Mastercard
        r'\b3[47]\d{2}[\s-]?\d{6}[\s-]?\d{5}\b',  # Amex
        r'\b6(?:011|5\d{2})[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b',  # Discover
    ]
    
    # Email pattern
    EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    # Phone patterns (US-centric but flexible)
    PHONE_PATTERNS = [
        r'\b\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b',
        r'\b\+1[\s.-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b',
        r'\b1[\s.-]?\d{3}[\s.-]?\d{3}[\s.-]?\d{4}\b',
    ]
    
    # IP address pattern
    IP_PATTERN = r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    
    # Date patterns that might be DOB
    DOB_PATTERNS = [
        r'\b(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/(?:19|20)\d{2}\b',
        r'\b(?:0[1-9]|[12]\d|3[01])/(?:0[1-9]|1[0-2])/(?:19|20)\d{2}\b',
        r'\b(?:19|20)\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])\b',
    ]
    
    # Context keywords that suggest PII
    SSN_CONTEXT = {'ssn', 'social security', 'ss#', 'social sec'}
    DOB_CONTEXT = {'dob', 'birth', 'born', 'birthday', 'date of birth'}
    NAME_CONTEXT = {'name', 'applicant', 'patient', 'customer', 'employee'}
    
    def __init__(
        self,
        detect_types: Optional[Set[PIIType]] = None,
        min_confidence: float = 0.5,
        context_window: int = 50,
    ):
        """
        Initialize PII detector.
        
        Args:
            detect_types: Types of PII to detect (None = all)
            min_confidence: Minimum confidence to report
            context_window: Characters of context to capture
        """
        self.detect_types = detect_types or set(PIIType)
        self.min_confidence = min_confidence
        self.context_window = context_window
        
        # Compile patterns
        self._ssn_patterns = [re.compile(p) for p in self.SSN_PATTERNS]
        self._cc_patterns = [re.compile(p) for p in self.CC_PATTERNS]
        self._email_pattern = re.compile(self.EMAIL_PATTERN)
        self._phone_patterns = [re.compile(p) for p in self.PHONE_PATTERNS]
        self._ip_pattern = re.compile(self.IP_PATTERN)
        self._dob_patterns = [re.compile(p) for p in self.DOB_PATTERNS]
    
    def detect(self, text: str) -> List[PIIMatch]:
        """
        Detect all PII in text.
        
        Returns:
            List of PIIMatch objects
        """
        matches = []
        text_lower = text.lower()
        
        # Detect each type
        if PIIType.SSN in self.detect_types:
            matches.extend(self._detect_ssn(text, text_lower))
        
        if PIIType.CREDIT_CARD in self.detect_types:
            matches.extend(self._detect_credit_card(text))
        
        if PIIType.EMAIL in self.detect_types:
            matches.extend(self._detect_email(text))
        
        if PIIType.PHONE in self.detect_types:
            matches.extend(self._detect_phone(text))
        
        if PIIType.IP_ADDRESS in self.detect_types:
            matches.extend(self._detect_ip(text))
        
        if PIIType.DATE_OF_BIRTH in self.detect_types:
            matches.extend(self._detect_dob(text, text_lower))
        
        # Filter by confidence
        matches = [m for m in matches if m.confidence >= self.min_confidence]
        
        # Remove duplicates (same position)
        seen = set()
        unique_matches = []
        for m in matches:
            key = (m.start, m.end)
            if key not in seen:
                seen.add(key)
                unique_matches.append(m)
        
        return unique_matches
    
    def _detect_ssn(self, text: str, text_lower: str) -> List[PIIMatch]:
        """Detect SSN patterns."""
        matches = []
        
        for pattern in self._ssn_patterns:
            for match in pattern.finditer(text):
                value = match.group()
                start, end = match.span()
                
                # Calculate confidence based on context
                context = self._get_context(text_lower, start, end)
                has_ssn_context = any(kw in context for kw in self.SSN_CONTEXT)
                
                # 9-digit number without dashes needs context
                if len(value) == 9 and value.isdigit():
                    confidence = 0.9 if has_ssn_context else 0.3
                else:
                    confidence = 0.95 if has_ssn_context else 0.7
                
                # Validate SSN format
                digits = ''.join(c for c in value if c.isdigit())
                if len(digits) == 9:
                    # SSN rules: first 3 digits can't be 000, 666, or 900-999
                    first_three = int(digits[:3])
                    if first_three in (0, 666) or first_three >= 900:
                        confidence *= 0.5
                
                matches.append(PIIMatch(
                    pii_type=PIIType.SSN,
                    value=value,
                    start=start,
                    end=end,
                    confidence=confidence,
                    context=self._get_context(text, start, end),
                ))
        
        return matches
    
    def _detect_credit_card(self, text: str) -> List[PIIMatch]:
        """Detect credit card numbers."""
        matches = []
        
        for pattern in self._cc_patterns:
            for match in pattern.finditer(text):
                value = match.group()
                start, end = match.span()
                
                # Validate with Luhn algorithm
                digits = ''.join(c for c in value if c.isdigit())
                if self._luhn_check(digits):
                    confidence = 0.95
                else:
                    confidence = 0.5
                
                matches.append(PIIMatch(
                    pii_type=PIIType.CREDIT_CARD,
                    value=value,
                    start=start,
                    end=end,
                    confidence=confidence,
                    context=self._get_context(text, start, end),
                ))
        
        return matches
    
    def _detect_email(self, text: str) -> List[PIIMatch]:
        """Detect email addresses."""
        matches = []
        
        for match in self._email_pattern.finditer(text):
            value = match.group()
            start, end = match.span()
            
            # Higher confidence for common domains
            common_domains = {'gmail.com', 'yahoo.com', 'outlook.com', 'hotmail.com'}
            domain = value.split('@')[1].lower()
            confidence = 0.95 if domain in common_domains else 0.9
            
            matches.append(PIIMatch(
                pii_type=PIIType.EMAIL,
                value=value,
                start=start,
                end=end,
                confidence=confidence,
                context=self._get_context(text, start, end),
            ))
        
        return matches
    
    def _detect_phone(self, text: str) -> List[PIIMatch]:
        """Detect phone numbers."""
        matches = []
        
        for pattern in self._phone_patterns:
            for match in pattern.finditer(text):
                value = match.group()
                start, end = match.span()
                
                # Basic validation
                digits = ''.join(c for c in value if c.isdigit())
                if len(digits) >= 10:
                    confidence = 0.85
                else:
                    confidence = 0.6
                
                matches.append(PIIMatch(
                    pii_type=PIIType.PHONE,
                    value=value,
                    start=start,
                    end=end,
                    confidence=confidence,
                    context=self._get_context(text, start, end),
                ))
        
        return matches
    
    def _detect_ip(self, text: str) -> List[PIIMatch]:
        """Detect IP addresses."""
        matches = []
        
        for match in self._ip_pattern.finditer(text):
            value = match.group()
            start, end = match.span()
            
            # Lower confidence for common private/local IPs
            if value.startswith(('192.168.', '10.', '172.', '127.')):
                confidence = 0.6
            else:
                confidence = 0.8
            
            matches.append(PIIMatch(
                pii_type=PIIType.IP_ADDRESS,
                value=value,
                start=start,
                end=end,
                confidence=confidence,
                context=self._get_context(text, start, end),
            ))
        
        return matches
    
    def _detect_dob(self, text: str, text_lower: str) -> List[PIIMatch]:
        """Detect dates that appear to be dates of birth."""
        matches = []
        
        for pattern in self._dob_patterns:
            for match in pattern.finditer(text):
                value = match.group()
                start, end = match.span()
                
                # Check context for DOB indicators
                context = self._get_context(text_lower, start, end)
                has_dob_context = any(kw in context for kw in self.DOB_CONTEXT)
                
                if has_dob_context:
                    confidence = 0.9
                else:
                    confidence = 0.3  # Just a date, not necessarily DOB
                
                matches.append(PIIMatch(
                    pii_type=PIIType.DATE_OF_BIRTH,
                    value=value,
                    start=start,
                    end=end,
                    confidence=confidence,
                    context=self._get_context(text, start, end),
                ))
        
        return matches
    
    def _get_context(self, text: str, start: int, end: int) -> str:
        """Get surrounding context for a match."""
        ctx_start = max(0, start - self.context_window)
        ctx_end = min(len(text), end + self.context_window)
        return text[ctx_start:ctx_end]
    
    def _luhn_check(self, number: str) -> bool:
        """Validate number with Luhn algorithm."""
        def digits_of(n):
            return [int(d) for d in str(n)]
        
        digits = digits_of(number)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d * 2))
        
        return checksum % 10 == 0
    
    def redact(
        self,
        text: str,
        matches: Optional[List[PIIMatch]] = None,
        replacement: str = "[REDACTED]",
    ) -> str:
        """
        Redact PII from text.
        
        Args:
            text: Original text
            matches: PII matches to redact (or None to detect)
            replacement: Replacement text
            
        Returns:
            Text with PII redacted
        """
        if matches is None:
            matches = self.detect(text)
        
        # Sort by position (reverse order for replacement)
        matches = sorted(matches, key=lambda m: m.start, reverse=True)
        
        result = text
        for match in matches:
            result = result[:match.start] + replacement + result[match.end:]
        
        return result
    
    def get_pii_types(self, text: str) -> Set[PIIType]:
        """Get the types of PII found in text."""
        matches = self.detect(text)
        return {m.pii_type for m in matches}
    
    def has_pii(self, text: str) -> bool:
        """Check if text contains any PII."""
        return len(self.detect(text)) > 0
    
    def get_summary(self, text: str) -> Dict:
        """Get summary of PII found in text."""
        matches = self.detect(text)
        
        by_type = {}
        for match in matches:
            type_name = match.pii_type.value
            if type_name not in by_type:
                by_type[type_name] = 0
            by_type[type_name] += 1
        
        return {
            "total_matches": len(matches),
            "by_type": by_type,
            "pii_detected": len(matches) > 0,
        }
