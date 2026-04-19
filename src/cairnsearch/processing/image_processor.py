"""Enhanced image processor with OCR and form detection."""
import io
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any

from cairnsearch.config import get_config
from cairnsearch.core.models import (
    ProcessingResult, ExtractionMetadata, PageInfo, PageType,
    GuardrailLimits, OCRConfidence,
)
from cairnsearch.core.exceptions import ProcessingError, GuardrailExceeded, OCRError
from cairnsearch.core.guardrails import GuardrailEnforcer
from cairnsearch.core.subprocess_runner import SubprocessRunner


logger = logging.getLogger(__name__)


@dataclass
class ImageAnalysis:
    """Analysis results for an image."""
    has_text: bool
    has_graphics: bool
    is_document: bool  # Looks like a scanned document
    is_photograph: bool
    text_regions: List[Dict[str, Any]] = field(default_factory=list)
    graphic_regions: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ImageOCRResult:
    """OCR result for an image."""
    text: str
    confidence: float
    word_boxes: List[Dict[str, Any]]
    layout_analysis: Optional[Dict[str, Any]] = None
    form_fields: Optional[Dict[str, Any]] = None


class EnhancedImageProcessor:
    """
    Enhanced image processor with:
    - Text vs graphics detection
    - High-quality OCR with preprocessing
    - Form field extraction
    - Confidence tracking
    - Bounding box data
    """
    
    SUPPORTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"]
    
    def __init__(
        self,
        limits: Optional[GuardrailLimits] = None,
        target_dpi: int = 300,
        use_subprocess: bool = True,
    ):
        self.config = get_config()
        self.limits = limits or GuardrailLimits()
        self.target_dpi = target_dpi
        self.use_subprocess = use_subprocess
        self.guardrails = GuardrailEnforcer(self.limits)
        
        self._subprocess = SubprocessRunner(
            timeout=120,  # 2 minutes for images
            max_retries=1,
        )
    
    def process(self, file_path: Path) -> ProcessingResult:
        """
        Process an image file with OCR.
        
        Args:
            file_path: Path to image file
            
        Returns:
            ProcessingResult with OCR text and metadata
        """
        start_time = time.time()
        file_path = Path(file_path)
        
        self.guardrails.start_processing()
        
        try:
            # Check file size
            size_bytes = file_path.stat().st_size
            max_size = self.limits.max_image_size_mb * 1024 * 1024
            if size_bytes > max_size:
                return ProcessingResult(
                    success=False,
                    error=f"Image size {size_bytes / (1024*1024):.1f}MB exceeds limit {self.limits.max_image_size_mb}MB",
                    error_stage="validation",
                    processing_time_ms=(time.time() - start_time) * 1000,
                )
            
            # Check if OCR is enabled
            if not self.config.ocr.enabled:
                return ProcessingResult(
                    success=False,
                    error="OCR is disabled in configuration",
                    error_stage="config",
                    processing_time_ms=(time.time() - start_time) * 1000,
                )
            
            # Process in subprocess for safety
            if self.use_subprocess:
                result = self._subprocess.run_with_retry(
                    self._process_image_internal,
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
                return self._process_image_internal(str(file_path))
                
        except Exception as e:
            logger.exception(f"Image processing failed: {e}")
            return ProcessingResult(
                success=False,
                error=str(e),
                error_stage="extraction",
                processing_time_ms=(time.time() - start_time) * 1000,
            )
    
    def _process_image_internal(self, file_path: str) -> ProcessingResult:
        """Internal image processing."""
        from PIL import Image
        
        start_time = time.time()
        file_path = Path(file_path)
        
        # Open image
        try:
            img = Image.open(file_path)
        except Exception as e:
            return ProcessingResult(
                success=False,
                error=f"Failed to open image: {e}",
                error_stage="open",
                processing_time_ms=(time.time() - start_time) * 1000,
            )
        
        # Analyze image
        analysis = self._analyze_image(img)
        
        # Perform OCR if image has text
        if analysis.has_text or analysis.is_document:
            ocr_result = self._perform_ocr(img)
        else:
            ocr_result = ImageOCRResult(
                text="",
                confidence=0.0,
                word_boxes=[],
            )
        
        # Create page info
        page_info = PageInfo(
            page_num=1,
            page_type=PageType.SCANNED,
            text=ocr_result.text,
            ocr_confidence=ocr_result.confidence,
            ocr_data={
                "word_boxes": ocr_result.word_boxes,
                "layout": ocr_result.layout_analysis,
            },
        )
        
        # Extract form fields if present
        if analysis.is_document and ocr_result.form_fields:
            page_info.key_value_pairs = ocr_result.form_fields.get("key_values", [])
            page_info.checkboxes = ocr_result.form_fields.get("checkboxes", [])
        
        # Determine confidence level
        if page_info.confidence_level == OCRConfidence.LOW:
            page_info.warnings.append("Low OCR confidence - results may be unreliable")
        
        # Build metadata
        metadata = ExtractionMetadata(
            file_path=str(file_path),
            filename=file_path.name,
            file_type=file_path.suffix.lower().lstrip('.'),
            page_count=1,
            extraction_method="ocr",
            processing_time_ms=(time.time() - start_time) * 1000,
            total_chars=len(ocr_result.text),
            avg_ocr_confidence=ocr_result.confidence,
            low_confidence_pages=[1] if page_info.confidence_level == OCRConfidence.LOW else [],
            has_forms=bool(ocr_result.form_fields),
            warnings=page_info.warnings,
        )
        metadata.metadata = {
            "image_size": f"{img.width}x{img.height}",
            "image_mode": img.mode,
            "has_text": analysis.has_text,
            "has_graphics": analysis.has_graphics,
            "is_document": analysis.is_document,
        }
        
        return ProcessingResult(
            success=True,
            text=ocr_result.text,
            pages=[page_info],
            metadata=metadata,
            warnings=page_info.warnings,
            processing_time_ms=(time.time() - start_time) * 1000,
        )
    
    def _analyze_image(self, img) -> ImageAnalysis:
        """Analyze image content."""
        from PIL import Image
        import numpy as np
        
        # Convert to grayscale for analysis
        if img.mode != 'L':
            gray = img.convert('L')
        else:
            gray = img
        
        # Get histogram
        histogram = gray.histogram()
        
        # Calculate statistics
        total_pixels = sum(histogram)
        
        # Check for text characteristics
        # Documents tend to have bimodal histograms (light background, dark text)
        # Count pixels in dark and light regions
        dark_pixels = sum(histogram[:64])  # Very dark
        light_pixels = sum(histogram[192:])  # Very light
        
        dark_ratio = dark_pixels / total_pixels
        light_ratio = light_pixels / total_pixels
        
        # Check for document-like characteristics
        is_document = (light_ratio > 0.6 and dark_ratio > 0.05) or \
                     (light_ratio > 0.4 and dark_ratio > 0.1)
        
        # Check for text presence (high contrast edges)
        # Simplified check - real implementation would use edge detection
        has_text = is_document or (dark_ratio > 0.05 and light_ratio > 0.3)
        
        # Check for graphics
        # Photos have smoother histograms
        histogram_variance = sum((h - total_pixels/256)**2 for h in histogram)
        is_photograph = histogram_variance < (total_pixels * 100)
        
        has_graphics = is_photograph or (not is_document and dark_ratio > 0.2)
        
        return ImageAnalysis(
            has_text=has_text,
            has_graphics=has_graphics,
            is_document=is_document,
            is_photograph=is_photograph,
        )
    
    def _perform_ocr(self, img) -> ImageOCRResult:
        """Perform OCR with preprocessing."""
        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        except ImportError:
            raise OCRError("OCR dependencies not installed")
        
        config = get_config()
        
        # Preprocess image
        processed = self._preprocess_image(img)
        
        # OCR with detailed output
        custom_config = r'--oem 3 --psm 6'
        
        # Get detailed OCR data
        ocr_data = pytesseract.image_to_data(
            processed,
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
                    "word_num": ocr_data['word_num'][i],
                })
        
        # Calculate average confidence
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        # Get full text
        text = pytesseract.image_to_string(
            processed,
            lang=config.ocr.language,
            config=custom_config,
        ).strip()
        
        # Try to detect form fields
        form_fields = self._detect_form_fields(text, word_boxes)
        
        # Get layout analysis
        layout = self._analyze_layout(word_boxes)
        
        return ImageOCRResult(
            text=text,
            confidence=avg_confidence / 100.0,
            word_boxes=word_boxes,
            layout_analysis=layout,
            form_fields=form_fields,
        )
    
    def _preprocess_image(self, img):
        """Preprocess image for OCR."""
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
        
        # Convert to RGB if necessary
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        
        # Convert to grayscale
        if img.mode != 'L':
            img = img.convert('L')
        
        # Resize if too small
        min_dimension = 1000
        if img.width < min_dimension or img.height < min_dimension:
            scale = max(min_dimension / img.width, min_dimension / img.height)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Auto-contrast
        img = ImageOps.autocontrast(img)
        
        # Denoise
        img = img.filter(ImageFilter.MedianFilter(size=3))
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        
        # Binarize (Otsu-like threshold)
        histogram = img.histogram()
        total = sum(histogram)
        sum_total = sum(i * histogram[i] for i in range(256))
        
        sum_bg = 0
        weight_bg = 0
        max_var = 0
        threshold = 127
        
        for i in range(256):
            weight_bg += histogram[i]
            if weight_bg == 0:
                continue
            weight_fg = total - weight_bg
            if weight_fg == 0:
                break
            
            sum_bg += i * histogram[i]
            mean_bg = sum_bg / weight_bg
            mean_fg = (sum_total - sum_bg) / weight_fg
            
            var = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
            if var > max_var:
                max_var = var
                threshold = i
        
        img = img.point(lambda p: 255 if p > threshold else 0)
        
        return img
    
    def _detect_form_fields(
        self,
        text: str,
        word_boxes: List[Dict],
    ) -> Optional[Dict[str, List]]:
        """Detect form fields from OCR results."""
        import re
        
        result = {
            "key_values": [],
            "checkboxes": [],
        }
        
        # Detect key-value patterns in text
        kv_patterns = [
            r'([A-Za-z][A-Za-z\s]+):\s*(.+)',
            r'([A-Za-z][A-Za-z\s]+)\s{2,}(.+)',
        ]
        
        lines = text.split('\n')
        for line in lines[:50]:  # Limit processing
            for pattern in kv_patterns:
                match = re.match(pattern, line.strip())
                if match:
                    key, value = match.groups()
                    key = key.strip()
                    value = value.strip()
                    if len(key) > 2 and len(key) < 50 and len(value) > 0:
                        result["key_values"].append({
                            "key": key,
                            "value": value,
                        })
                        break
        
        # Detect checkbox patterns
        checkbox_patterns = [
            r'\[([xX\s])\]',  # [x] or [ ]
            r'\(([xX\s])\)',  # (x) or ( )
            r'□|☐|☑|☒',      # Unicode checkboxes
        ]
        
        for line in lines:
            for pattern in checkbox_patterns[:2]:
                matches = re.findall(pattern, line)
                for match in matches:
                    result["checkboxes"].append({
                        "checked": match.lower() == 'x',
                        "line": line.strip(),
                    })
        
        return result if (result["key_values"] or result["checkboxes"]) else None
    
    def _analyze_layout(self, word_boxes: List[Dict]) -> Dict[str, Any]:
        """Analyze document layout from word boxes."""
        if not word_boxes:
            return {}
        
        # Group by blocks and lines
        blocks = {}
        for box in word_boxes:
            block_num = box.get("block_num", 0)
            if block_num not in blocks:
                blocks[block_num] = []
            blocks[block_num].append(box)
        
        return {
            "block_count": len(blocks),
            "word_count": len(word_boxes),
            "avg_word_confidence": sum(b["confidence"] for b in word_boxes) / len(word_boxes),
        }
