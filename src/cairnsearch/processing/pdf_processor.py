"""Enhanced PDF processor with per-page classification and advanced OCR."""
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

from cairnsearch.config import get_config
from cairnsearch.core.models import (
    PageType, PageInfo, ProcessingResult, ExtractionMetadata,
    ChunkMetadata, OCRConfidence, GuardrailLimits,
)
from cairnsearch.core.exceptions import ProcessingError, GuardrailExceeded, OCRError
from cairnsearch.core.guardrails import GuardrailEnforcer
from cairnsearch.core.subprocess_runner import SubprocessRunner


logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Result from OCR processing."""
    text: str
    confidence: float
    word_boxes: List[dict] = field(default_factory=list)  # Bounding boxes
    reading_order: List[int] = field(default_factory=list)
    raw_data: Optional[dict] = None
    
    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "word_boxes": self.word_boxes,
            "reading_order": self.reading_order,
        }


@dataclass
class TableData:
    """Extracted table data."""
    table_id: str
    page_num: int
    headers: List[str]
    rows: List[List[str]]
    bounding_box: Optional[dict] = None
    confidence: float = 1.0
    
    def to_dict(self) -> dict:
        return {
            "table_id": self.table_id,
            "page_num": self.page_num,
            "headers": self.headers,
            "rows": self.rows,
            "bounding_box": self.bounding_box,
            "confidence": self.confidence,
        }
    
    def to_text(self) -> str:
        """Convert table to readable text."""
        lines = []
        if self.headers:
            lines.append(" | ".join(self.headers))
            lines.append("-" * 40)
        for row in self.rows:
            lines.append(" | ".join(str(cell) for cell in row))
        return "\n".join(lines)


class EnhancedPDFProcessor:
    """
    Enhanced PDF processor with:
    - Per-page digital/scanned classification
    - Intelligent OCR routing
    - Table detection and extraction
    - Form field detection
    - Header/footer removal
    - Text normalization
    - Structured JSON OCR output
    """
    
    # Thresholds for page classification
    SCANNED_THRESHOLD_CHARS = 50  # Chars per page below this = scanned
    TEXT_DENSITY_THRESHOLD = 0.001  # Text area / page area
    
    def __init__(
        self,
        limits: Optional[GuardrailLimits] = None,
        ocr_dpi: int = 300,
        use_subprocess: bool = True,
    ):
        self.config = get_config()
        self.limits = limits or GuardrailLimits()
        self.ocr_dpi = ocr_dpi
        self.use_subprocess = use_subprocess
        self.guardrails = GuardrailEnforcer(self.limits)
        
        # Subprocess runner for native code
        self._subprocess = SubprocessRunner(
            timeout=self.limits.max_processing_time_seconds,
            max_retries=1,
        )
    
    def process(self, file_path: Path) -> ProcessingResult:
        """
        Process a PDF file with enhanced extraction.
        
        Args:
            file_path: Path to PDF file
            
        Returns:
            ProcessingResult with pages, text, and metadata
        """
        start_time = time.time()
        file_path = Path(file_path)
        
        self.guardrails.start_processing()
        
        try:
            # Check file size
            self.guardrails.enforce(
                self.guardrails.check_file_size(file_path.stat().st_size)
            )
            
            # Process in subprocess for safety
            if self.use_subprocess:
                result = self._subprocess.run_with_retry(
                    self._process_pdf_internal,
                    str(file_path),
                )
                if not result.success:
                    return ProcessingResult(
                        success=False,
                        error=result.error,
                        error_stage="subprocess",
                        processing_time_ms=(time.time() - start_time) * 1000,
                    )
                return result.return_value
            else:
                return self._process_pdf_internal(str(file_path))
                
        except GuardrailExceeded as e:
            return ProcessingResult(
                success=False,
                error=str(e),
                error_stage="guardrails",
                processing_time_ms=(time.time() - start_time) * 1000,
            )
        except Exception as e:
            logger.exception(f"PDF processing failed: {e}")
            return ProcessingResult(
                success=False,
                error=str(e),
                error_stage="extraction",
                processing_time_ms=(time.time() - start_time) * 1000,
            )
    
    def _process_pdf_internal(self, file_path: str) -> ProcessingResult:
        """Internal PDF processing (runs in subprocess)."""
        import fitz  # PyMuPDF
        
        start_time = time.time()
        file_path = Path(file_path)
        
        doc = fitz.open(file_path)
        page_count = len(doc)
        
        # Check page limit
        if page_count > self.limits.max_pages:
            doc.close()
            raise GuardrailExceeded(
                f"Page count {page_count} exceeds limit {self.limits.max_pages}",
                "max_pages",
                self.limits.max_pages,
                page_count,
            )
        
        # Get document metadata
        doc_metadata = doc.metadata or {}
        
        # Process each page
        pages: List[PageInfo] = []
        all_text_parts = []
        tables: List[TableData] = []
        warnings = []
        total_chars = 0
        ocr_pages_count = 0
        ocr_confidences = []
        
        for page_num in range(page_count):
            page = doc[page_num]
            
            # Classify page type
            page_type = self._classify_page(page)
            
            # Extract based on type
            if page_type == PageType.DIGITAL:
                page_info = self._extract_digital_page(page, page_num)
            elif page_type == PageType.SCANNED:
                # Check OCR page limit
                if ocr_pages_count >= self.limits.max_ocr_pages:
                    warnings.append(f"OCR page limit reached at page {page_num + 1}")
                    page_info = PageInfo(
                        page_num=page_num + 1,
                        page_type=PageType.SCANNED,
                        text="[OCR limit exceeded]",
                        warnings=["OCR skipped due to page limit"],
                    )
                else:
                    page_info = self._extract_scanned_page(page, page_num)
                    ocr_pages_count += 1
                    if page_info.ocr_confidence:
                        ocr_confidences.append(page_info.ocr_confidence)
            else:  # MIXED
                page_info = self._extract_mixed_page(page, page_num)
                if page_info.ocr_confidence:
                    ocr_confidences.append(page_info.ocr_confidence)
            
            # Detect tables
            page_tables = self._detect_tables(page, page_num)
            if page_tables:
                tables.extend(page_tables)
                page_info.tables = [t.to_dict() for t in page_tables]
            
            # Detect forms/checkboxes
            form_fields = self._detect_form_fields(page, page_num)
            if form_fields:
                page_info.key_value_pairs = form_fields.get("key_values", [])
                page_info.checkboxes = form_fields.get("checkboxes", [])
            
            # Remove headers/footers
            cleaned_text = self._remove_headers_footers(
                page_info.text, page_num, page_count
            )
            page_info.text = cleaned_text
            page_info.has_header = len(cleaned_text) < len(page_info.text)
            
            pages.append(page_info)
            all_text_parts.append(f"[Page {page_num + 1}]\n{page_info.text}")
            total_chars += len(page_info.text)
            
            # Add warnings
            if page_info.confidence_level == OCRConfidence.LOW:
                warnings.append(f"Page {page_num + 1} has low OCR confidence")
            
            warnings.extend(page_info.warnings)
        
        doc.close()
        
        # Combine text
        full_text = "\n\n".join(all_text_parts)
        
        # Normalize text
        full_text = self._normalize_text(full_text)
        
        # Calculate average OCR confidence
        avg_ocr_confidence = None
        if ocr_confidences:
            avg_ocr_confidence = sum(ocr_confidences) / len(ocr_confidences)
        
        # Low confidence pages
        low_confidence_pages = [
            p.page_num for p in pages
            if p.confidence_level == OCRConfidence.LOW
        ]
        
        # Determine extraction method
        if ocr_pages_count == 0:
            extraction_method = "direct"
        elif ocr_pages_count == page_count:
            extraction_method = "ocr"
        else:
            extraction_method = "hybrid"
        
        # Build metadata
        metadata = ExtractionMetadata(
            file_path=str(file_path),
            filename=file_path.name,
            file_type="pdf",
            page_count=page_count,
            title=doc_metadata.get("title"),
            author=doc_metadata.get("author"),
            created_date=self._parse_pdf_date(doc_metadata.get("creationDate")),
            modified_date=self._parse_pdf_date(doc_metadata.get("modDate")),
            extraction_method=extraction_method,
            processing_time_ms=(time.time() - start_time) * 1000,
            total_chars=total_chars,
            avg_ocr_confidence=avg_ocr_confidence,
            low_confidence_pages=low_confidence_pages,
            has_tables=len(tables) > 0,
            warnings=warnings,
        )
        
        return ProcessingResult(
            success=True,
            text=full_text,
            pages=pages,
            metadata=metadata,
            warnings=warnings,
            processing_time_ms=(time.time() - start_time) * 1000,
        )
    
    def _classify_page(self, page) -> PageType:
        """Classify a page as digital, scanned, or mixed."""
        import fitz
        
        # Get text
        text = page.get_text().strip()
        text_len = len(text)
        
        # Get images
        images = page.get_images()
        
        # Calculate page area
        page_area = page.rect.width * page.rect.height
        
        # Calculate image coverage
        image_coverage = 0
        for img in images:
            try:
                img_rect = page.get_image_bbox(img)
                if img_rect:
                    image_coverage += img_rect.width * img_rect.height
            except:
                pass
        
        image_ratio = image_coverage / page_area if page_area > 0 else 0
        
        # Decision logic
        if text_len < self.SCANNED_THRESHOLD_CHARS:
            # Very little text
            if image_ratio > 0.3:
                return PageType.SCANNED
            return PageType.UNKNOWN
        elif image_ratio > 0.5 and text_len < 500:
            # Large image with some text - likely scanned
            return PageType.SCANNED
        elif image_ratio > 0.3 and text_len > 100:
            # Mixed - has both significant images and text
            return PageType.MIXED
        else:
            # Mostly text
            return PageType.DIGITAL
    
    def _extract_digital_page(self, page, page_num: int) -> PageInfo:
        """Extract text from a digital PDF page."""
        text = page.get_text()
        
        return PageInfo(
            page_num=page_num + 1,
            page_type=PageType.DIGITAL,
            text=text,
            ocr_confidence=1.0,
        )
    
    def _extract_scanned_page(self, page, page_num: int) -> PageInfo:
        """Extract text from a scanned page using OCR."""
        try:
            ocr_result = self._perform_ocr(page)
            
            return PageInfo(
                page_num=page_num + 1,
                page_type=PageType.SCANNED,
                text=ocr_result.text,
                ocr_confidence=ocr_result.confidence,
                ocr_data={
                    "word_boxes": ocr_result.word_boxes,
                    "reading_order": ocr_result.reading_order,
                },
            )
        except Exception as e:
            logger.warning(f"OCR failed for page {page_num + 1}: {e}")
            return PageInfo(
                page_num=page_num + 1,
                page_type=PageType.SCANNED,
                text="",
                ocr_confidence=0.0,
                warnings=[f"OCR failed: {str(e)}"],
            )
    
    def _extract_mixed_page(self, page, page_num: int) -> PageInfo:
        """Extract text from a mixed page (digital text + scanned images)."""
        # First get existing digital text
        digital_text = page.get_text().strip()
        
        # Then OCR any images that might contain text
        try:
            ocr_result = self._perform_ocr(page)
            
            # Compare and merge
            if len(ocr_result.text) > len(digital_text) * 1.5:
                # OCR found significantly more - use OCR
                final_text = ocr_result.text
                confidence = ocr_result.confidence
            elif len(digital_text) > len(ocr_result.text) * 1.5:
                # Digital found more - use digital
                final_text = digital_text
                confidence = 1.0
            else:
                # Similar amounts - prefer digital (more reliable)
                final_text = digital_text
                confidence = 0.9
            
            return PageInfo(
                page_num=page_num + 1,
                page_type=PageType.MIXED,
                text=final_text,
                ocr_confidence=confidence,
                ocr_data={"word_boxes": ocr_result.word_boxes} if confidence < 1.0 else None,
            )
        except Exception as e:
            return PageInfo(
                page_num=page_num + 1,
                page_type=PageType.MIXED,
                text=digital_text,
                ocr_confidence=0.8,
                warnings=[f"OCR portion failed: {str(e)}"],
            )
    
    def _perform_ocr(self, page) -> OCRResult:
        """Perform OCR on a page with preprocessing and confidence tracking."""
        import fitz
        
        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter
        except ImportError:
            raise OCRError("OCR dependencies not installed")
        
        # Render page at high DPI
        mat = fitz.Matrix(self.ocr_dpi / 72, self.ocr_dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        
        # Preprocess image
        img = self._preprocess_image_for_ocr(img)
        
        # OCR with detailed output
        config = get_config()
        custom_config = r'--oem 3 --psm 6'
        
        # Get detailed OCR data with bounding boxes
        ocr_data = pytesseract.image_to_data(
            img,
            lang=config.ocr.language,
            config=custom_config,
            output_type=pytesseract.Output.DICT,
        )
        
        # Build result
        words = []
        confidences = []
        word_boxes = []
        
        for i in range(len(ocr_data['text'])):
            text = ocr_data['text'][i].strip()
            conf = int(ocr_data['conf'][i])
            
            if text and conf > 0:
                words.append(text)
                confidences.append(conf)
                word_boxes.append({
                    "text": text,
                    "confidence": conf / 100.0,
                    "x": ocr_data['left'][i],
                    "y": ocr_data['top'][i],
                    "width": ocr_data['width'][i],
                    "height": ocr_data['height'][i],
                    "block_num": ocr_data['block_num'][i],
                    "line_num": ocr_data['line_num'][i],
                })
        
        # Calculate average confidence
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Get text with reading order
        text = pytesseract.image_to_string(
            img,
            lang=config.ocr.language,
            config=custom_config,
        ).strip()
        
        return OCRResult(
            text=text,
            confidence=avg_confidence / 100.0,
            word_boxes=word_boxes,
            reading_order=list(range(len(word_boxes))),
        )
    
    def _preprocess_image_for_ocr(self, img):
        """Preprocess image for better OCR accuracy."""
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        
        # Convert to grayscale
        if img.mode != 'L':
            img = img.convert('L')
        
        # Deskew (simple approach)
        # Note: Full deskew requires more sophisticated processing
        
        # Denoise with median filter
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        # Auto-contrast
        img = ImageOps.autocontrast(img)
        
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        
        # Binarization (Otsu-like)
        # Calculate threshold
        histogram = img.histogram()
        total_pixels = sum(histogram)
        sum_total = sum(i * histogram[i] for i in range(256))
        
        sum_bg = 0
        weight_bg = 0
        max_variance = 0
        threshold = 127
        
        for i in range(256):
            weight_bg += histogram[i]
            if weight_bg == 0:
                continue
            weight_fg = total_pixels - weight_bg
            if weight_fg == 0:
                break
            
            sum_bg += i * histogram[i]
            mean_bg = sum_bg / weight_bg
            mean_fg = (sum_total - sum_bg) / weight_fg
            
            variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
            if variance > max_variance:
                max_variance = variance
                threshold = i
        
        img = img.point(lambda p: 255 if p > threshold else 0)
        
        return img
    
    def _detect_tables(self, page, page_num: int) -> List[TableData]:
        """Detect and extract tables from a page."""
        tables = []
        
        try:
            # Use PyMuPDF's table detection
            page_tables = page.find_tables()
            
            for i, table in enumerate(page_tables):
                # Extract table data
                try:
                    extracted = table.extract()
                    if not extracted:
                        continue
                    
                    # First row as headers
                    headers = [str(cell) if cell else "" for cell in extracted[0]]
                    rows = [
                        [str(cell) if cell else "" for cell in row]
                        for row in extracted[1:]
                    ]
                    
                    # Get bounding box
                    bbox = table.bbox if hasattr(table, 'bbox') else None
                    
                    tables.append(TableData(
                        table_id=f"table_{page_num}_{i}",
                        page_num=page_num + 1,
                        headers=headers,
                        rows=rows,
                        bounding_box={
                            "x0": bbox[0], "y0": bbox[1],
                            "x1": bbox[2], "y1": bbox[3],
                        } if bbox else None,
                    ))
                except Exception as e:
                    logger.debug(f"Failed to extract table {i} on page {page_num}: {e}")
        except AttributeError:
            # Old PyMuPDF version without find_tables
            pass
        except Exception as e:
            logger.debug(f"Table detection failed on page {page_num}: {e}")
        
        return tables
    
    def _detect_form_fields(self, page, page_num: int) -> Dict[str, List]:
        """Detect form fields like key-value pairs and checkboxes."""
        result = {
            "key_values": [],
            "checkboxes": [],
        }
        
        try:
            # Detect PDF form widgets
            widgets = page.widgets()
            if widgets:
                for widget in widgets:
                    field_type = widget.field_type
                    field_name = widget.field_name
                    field_value = widget.field_value
                    
                    if field_type == 2:  # Checkbox
                        result["checkboxes"].append({
                            "name": field_name,
                            "checked": field_value == "Yes",
                            "rect": list(widget.rect),
                        })
                    elif field_type == 7:  # Text field
                        result["key_values"].append({
                            "key": field_name,
                            "value": field_value or "",
                            "rect": list(widget.rect),
                        })
        except Exception as e:
            logger.debug(f"Form field detection failed on page {page_num}: {e}")
        
        # Also try to detect key-value patterns in text
        text = page.get_text()
        kv_patterns = [
            r'([A-Za-z][A-Za-z\s]+):\s*(.+)',  # Label: Value
            r'([A-Za-z][A-Za-z\s]+)\s{2,}(.+)',  # Label    Value
        ]
        
        for pattern in kv_patterns:
            matches = re.findall(pattern, text[:2000])  # Limit search
            for key, value in matches[:20]:  # Limit results
                key = key.strip()
                value = value.strip()
                if len(key) > 2 and len(key) < 50 and len(value) > 0:
                    result["key_values"].append({
                        "key": key,
                        "value": value,
                        "source": "pattern",
                    })
        
        return result
    
    def _remove_headers_footers(
        self,
        text: str,
        page_num: int,
        total_pages: int,
    ) -> str:
        """Remove common headers and footers."""
        lines = text.split('\n')
        
        if len(lines) < 3:
            return text
        
        # Common patterns to remove
        header_patterns = [
            r'^Page\s+\d+\s*(of\s+\d+)?$',
            r'^\d+\s*$',  # Just page number
            r'^-\s*\d+\s*-$',  # - 1 -
            r'^©.*\d{4}',  # Copyright
            r'^CONFIDENTIAL',
            r'^DRAFT',
        ]
        
        footer_patterns = header_patterns + [
            r'^\s*\d+\s*/\s*\d+\s*$',  # 1/5
        ]
        
        # Check first few lines for headers
        cleaned_lines = []
        skip_top = 0
        for i, line in enumerate(lines[:3]):
            line_stripped = line.strip()
            is_header = False
            for pattern in header_patterns:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    is_header = True
                    break
            if is_header:
                skip_top = i + 1
            else:
                break
        
        # Check last few lines for footers
        skip_bottom = 0
        for i, line in enumerate(reversed(lines[-3:])):
            line_stripped = line.strip()
            is_footer = False
            for pattern in footer_patterns:
                if re.match(pattern, line_stripped, re.IGNORECASE):
                    is_footer = True
                    break
            if is_footer:
                skip_bottom = i + 1
            else:
                break
        
        # Apply filtering
        if skip_bottom > 0:
            lines = lines[skip_top:-skip_bottom]
        else:
            lines = lines[skip_top:]
        
        return '\n'.join(lines)
    
    def _normalize_text(self, text: str) -> str:
        """Normalize extracted text."""
        # Fix hyphenation
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)
        
        # Normalize whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Normalize Unicode
        import unicodedata
        text = unicodedata.normalize('NFKC', text)
        
        # Fix common OCR errors
        replacements = {
            'ﬁ': 'fi',
            'ﬂ': 'fl',
            '—': '-',
            '"': '"',
            '"': '"',
            ''': "'",
            ''': "'",
            '…': '...',
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text.strip()
    
    def _parse_pdf_date(self, date_str: Optional[str]) -> Optional[str]:
        """Parse PDF date format to ISO format."""
        if not date_str:
            return None
        try:
            if date_str.startswith("D:"):
                date_str = date_str[2:]
            if len(date_str) >= 8:
                year = date_str[0:4]
                month = date_str[4:6]
                day = date_str[6:8]
                return f"{year}-{month}-{day}"
        except:
            pass
        return None
    
    def normalize_pdf(self, file_path: Path) -> Optional[Path]:
        """
        Try to normalize a PDF that failed parsing.
        
        Returns path to normalized PDF or None if failed.
        """
        try:
            import fitz
            
            # Open and re-save the PDF
            doc = fitz.open(file_path)
            
            # Create temp file
            import tempfile
            fd, temp_path = tempfile.mkstemp(suffix='.pdf')
            os.close(fd)
            
            # Save with full garbage collection
            doc.save(temp_path, garbage=4, deflate=True)
            doc.close()
            
            return Path(temp_path)
        except Exception as e:
            logger.warning(f"PDF normalization failed: {e}")
            return None


def _serialize_page_info(page: PageInfo) -> dict:
    """Serialize PageInfo for subprocess transfer."""
    return {
        "page_num": page.page_num,
        "page_type": page.page_type.value,
        "text": page.text,
        "ocr_confidence": page.ocr_confidence,
        "ocr_data": page.ocr_data,
        "tables": page.tables,
        "key_value_pairs": page.key_value_pairs,
        "checkboxes": page.checkboxes,
        "has_header": page.has_header,
        "has_footer": page.has_footer,
        "warnings": page.warnings,
    }
