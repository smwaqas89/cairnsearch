"""Form field extraction utilities."""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
import logging


logger = logging.getLogger(__name__)


@dataclass
class FormField:
    """Represents an extracted form field."""
    field_id: str
    field_type: str  # text, checkbox, radio, select, signature
    label: str
    value: Any
    
    # Position
    page_num: Optional[int] = None
    bounding_box: Optional[Dict[str, float]] = None
    
    # Quality
    confidence: float = 1.0
    source: str = "pattern"  # pattern, widget, ocr
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "field_id": self.field_id,
            "field_type": self.field_type,
            "label": self.label,
            "value": self.value,
            "page_num": self.page_num,
            "confidence": self.confidence,
            "source": self.source,
        }


@dataclass
class ExtractedForm:
    """Represents an extracted form."""
    form_id: str
    source: str  # pdf, image, html
    fields: List[FormField] = field(default_factory=list)
    
    # Metadata
    title: Optional[str] = None
    page_nums: List[int] = field(default_factory=list)
    
    def to_text(self) -> str:
        """Convert form to readable text."""
        lines = []
        if self.title:
            lines.append(f"Form: {self.title}")
            lines.append("=" * 40)
        for f in self.fields:
            if f.field_type == "checkbox":
                checked = "☑" if f.value else "☐"
                lines.append(f"{checked} {f.label}")
            else:
                lines.append(f"{f.label}: {f.value or '[empty]'}")
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "form_id": self.form_id,
            "source": self.source,
            "title": self.title,
            "fields": [f.to_dict() for f in self.fields],
        }


class FormExtractor:
    """
    Form field extraction from various sources.
    """
    
    # Key-value patterns
    KV_PATTERNS = [
        # Label: Value
        (r'^([A-Za-z][A-Za-z\s.,()-]{2,50}):\s*(.*)$', "colon"),
        # Label .... Value (dot leaders)
        (r'^([A-Za-z][A-Za-z\s]{2,50})\.{3,}\s*(.*)$', "dot_leader"),
        # Label ____ Value (underline leaders)
        (r'^([A-Za-z][A-Za-z\s]{2,50})_{3,}\s*(.*)$', "underline"),
        # Label    Value (multiple spaces)
        (r'^([A-Za-z][A-Za-z\s]{2,30})\s{3,}(.+)$', "space"),
    ]
    
    # Checkbox patterns
    CHECKBOX_PATTERNS = [
        (r'\[([xX✓])\]\s*(.+)', True),   # [x] Label
        (r'\[\s*\]\s*(.+)', False),       # [ ] Label
        (r'\(([xX✓])\)\s*(.+)', True),   # (x) Label
        (r'\(\s*\)\s*(.+)', False),       # ( ) Label
        (r'☑\s*(.+)', True),              # ☑ Label
        (r'☐\s*(.+)', False),             # ☐ Label
        (r'✓\s*(.+)', True),              # ✓ Label
    ]
    
    # Common form field labels
    COMMON_LABELS = [
        "name", "first name", "last name", "full name",
        "date", "date of birth", "dob",
        "address", "street", "city", "state", "zip", "country",
        "phone", "telephone", "mobile", "cell",
        "email", "e-mail",
        "signature", "sign",
        "ssn", "social security",
        "account", "account number",
        "amount", "total", "balance",
    ]
    
    def __init__(self):
        self._kv_patterns = [
            (re.compile(p, re.MULTILINE | re.IGNORECASE), name)
            for p, name in self.KV_PATTERNS
        ]
        
        self._checkbox_patterns = [
            (re.compile(p, re.MULTILINE), is_checked)
            for p, is_checked in self.CHECKBOX_PATTERNS
        ]
    
    def extract_from_text(
        self,
        text: str,
        page_num: Optional[int] = None,
    ) -> ExtractedForm:
        """Extract form fields from text."""
        fields = []
        field_id = 0
        
        # Extract key-value pairs
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Try each pattern
            for pattern, pattern_type in self._kv_patterns:
                match = pattern.match(line)
                if match:
                    label = match.group(1).strip()
                    value = match.group(2).strip() if match.lastindex >= 2 else ""
                    
                    # Validate label
                    if self._is_valid_label(label):
                        fields.append(FormField(
                            field_id=f"field_{field_id}",
                            field_type="text",
                            label=label,
                            value=value,
                            page_num=page_num,
                            confidence=0.8 if value else 0.6,
                            source=f"pattern_{pattern_type}",
                        ))
                        field_id += 1
                    break
            
            # Try checkbox patterns
            for pattern, is_checked in self._checkbox_patterns:
                match = pattern.match(line)
                if match:
                    label = match.group(1) if len(match.groups()) >= 1 else ""
                    if isinstance(is_checked, bool):
                        # Fixed checked state
                        pass
                    else:
                        # Captured checked state
                        label = match.group(2) if len(match.groups()) >= 2 else match.group(1)
                        is_checked = True
                    
                    if label:
                        fields.append(FormField(
                            field_id=f"field_{field_id}",
                            field_type="checkbox",
                            label=label.strip(),
                            value=is_checked,
                            page_num=page_num,
                            confidence=0.9,
                            source="pattern_checkbox",
                        ))
                        field_id += 1
                    break
        
        return ExtractedForm(
            form_id=f"form_page_{page_num or 0}",
            source="text",
            fields=fields,
            page_nums=[page_num] if page_num else [],
        )
    
    def _is_valid_label(self, label: str) -> bool:
        """Check if a string looks like a valid form label."""
        label_lower = label.lower().strip()
        
        # Too short or too long
        if len(label) < 2 or len(label) > 50:
            return False
        
        # Should contain letters
        if not any(c.isalpha() for c in label):
            return False
        
        # Check if it matches common labels
        for common in self.COMMON_LABELS:
            if common in label_lower:
                return True
        
        # General heuristics
        # Should not be all numbers
        if label.replace(' ', '').isdigit():
            return False
        
        # Should not start with special characters
        if label[0] in '.,;:!?-_':
            return False
        
        return True
    
    def extract_aligned_fields(
        self,
        text: str,
        word_boxes: List[Dict[str, Any]],
    ) -> List[FormField]:
        """
        Extract form fields using word position alignment.
        
        Looks for label-value pairs that are horizontally aligned.
        """
        if not word_boxes:
            return []
        
        fields = []
        
        # Group words by line (similar y position)
        lines = self._group_by_lines(word_boxes)
        
        for line_words in lines:
            # Sort by x position
            line_words.sort(key=lambda w: w['x'])
            
            # Look for label-value patterns
            for i in range(len(line_words) - 1):
                current = line_words[i]
                next_word = line_words[i + 1]
                
                # Check for gap (possible field separator)
                gap = next_word['x'] - (current['x'] + current['width'])
                
                if gap > current['width'] * 2:  # Significant gap
                    # Current might be label, next might be value
                    label = current['text']
                    value = ' '.join(w['text'] for w in line_words[i + 1:])
                    
                    if self._is_valid_label(label):
                        fields.append(FormField(
                            field_id=f"aligned_{len(fields)}",
                            field_type="text",
                            label=label,
                            value=value,
                            confidence=0.7,
                            source="alignment",
                        ))
                    break
        
        return fields
    
    def _group_by_lines(
        self,
        word_boxes: List[Dict[str, Any]],
        tolerance: float = 10,
    ) -> List[List[Dict[str, Any]]]:
        """Group words into lines based on y position."""
        if not word_boxes:
            return []
        
        # Sort by y position
        sorted_words = sorted(word_boxes, key=lambda w: w['y'])
        
        lines = []
        current_line = [sorted_words[0]]
        current_y = sorted_words[0]['y']
        
        for word in sorted_words[1:]:
            if abs(word['y'] - current_y) <= tolerance:
                current_line.append(word)
            else:
                lines.append(current_line)
                current_line = [word]
                current_y = word['y']
        
        if current_line:
            lines.append(current_line)
        
        return lines
    
    def detect_checkboxes(
        self,
        word_boxes: List[Dict[str, Any]],
    ) -> List[FormField]:
        """Detect checkboxes from OCR word boxes."""
        fields = []
        
        # Look for checkbox characters
        checkbox_chars = {'☐', '☑', '☒', '□', '■', '▢', '▣'}
        
        for i, word in enumerate(word_boxes):
            text = word['text'].strip()
            
            if text in checkbox_chars:
                is_checked = text in {'☑', '☒', '■', '▣'}
                
                # Find associated label (next words on same line)
                label_parts = []
                for j in range(i + 1, min(i + 10, len(word_boxes))):
                    next_word = word_boxes[j]
                    # Check if on same line
                    if abs(next_word['y'] - word['y']) < 10:
                        label_parts.append(next_word['text'])
                    else:
                        break
                
                if label_parts:
                    fields.append(FormField(
                        field_id=f"checkbox_{len(fields)}",
                        field_type="checkbox",
                        label=' '.join(label_parts),
                        value=is_checked,
                        confidence=0.8,
                        source="ocr_checkbox",
                    ))
        
        return fields
