"""OCR extraction for images with preprocessing for better accuracy."""
from pathlib import Path
import logging

from .base import BaseExtractor, ExtractionResult
from cairnsearch.config import get_config

logger = logging.getLogger(__name__)


class OcrExtractor(BaseExtractor):
    """Extract text from images using Tesseract OCR with preprocessing."""

    @property
    def supported_extensions(self) -> list[str]:
        return [".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".gif", ".webp"]

    def extract(self, file_path: Path) -> ExtractionResult:
        config = get_config()
        
        if not config.ocr.enabled:
            return ExtractionResult(
                success=False,
                error="OCR is disabled in configuration"
            )

        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageFilter
            
            img = Image.open(file_path)
            
            # Convert to RGB if necessary
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Preprocessing for better OCR
            img = self._preprocess_image(img)
            
            # OCR with optimized config
            custom_config = r'--oem 3 --psm 6'  # LSTM OCR Engine, assume uniform text block
            text = pytesseract.image_to_string(
                img, 
                lang=config.ocr.language,
                config=custom_config
            )
            
            text = text.strip()
            
            if not text:
                # Try with different PSM mode
                text = pytesseract.image_to_string(
                    img, 
                    lang=config.ocr.language,
                    config='--oem 3 --psm 3'  # Fully automatic page segmentation
                )
                text = text.strip()

            return ExtractionResult(
                success=True,
                text=text,
                metadata={
                    "page_count": 1,
                    "image_size": f"{img.width}x{img.height}",
                },
                extraction_method="ocr"
            )
        except ImportError as e:
            return ExtractionResult(
                success=False, 
                error="pytesseract or PIL not installed. Run: pip install pytesseract pillow"
            )
        except Exception as e:
            logger.warning(f"OCR failed for {file_path}: {e}")
            return ExtractionResult(success=False, error=str(e))
    
    def _preprocess_image(self, img):
        """Preprocess image for better OCR accuracy."""
        from PIL import Image, ImageEnhance, ImageFilter
        
        # Convert to grayscale
        if img.mode != 'L':
            img = img.convert('L')
        
        # Resize if too small (OCR works better with larger images)
        min_size = 1000
        if img.width < min_size or img.height < min_size:
            scale = max(min_size / img.width, min_size / img.height)
            new_size = (int(img.width * scale), int(img.height * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        # Sharpen
        img = img.filter(ImageFilter.SHARPEN)
        
        # Binarization (convert to black and white)
        threshold = 150
        img = img.point(lambda p: 255 if p > threshold else 0)
        
        return img
