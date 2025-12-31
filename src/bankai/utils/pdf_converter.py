"""
PDF to Image Converter

Converts PDF pages to images for OCR and table detection processing.
"""

from pdf2image import convert_from_path
from PIL import Image
from pathlib import Path
from typing import List
import tempfile


class PDF2ImageConvertor:
    """Convert PDF pages to images."""
    
    def __init__(self, dpi: int = 400):
        """
        Initialize the PDF to Image converter.
        
        Args:
            dpi: Resolution for image conversion (default: 400)
                Higher DPI = better OCR accuracy but slower processing
                300: Standard quality, faster
                400: High quality, recommended for financial docs
                500: Very high quality, slowest
        """
        self.dpi = dpi
    
    def convert(self, pdf_path: str) -> List[Image.Image]:
        """
        Convert all pages of a PDF to images.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            List of PIL Image objects, one per page
        """
        pdf_path = Path(pdf_path)
        
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")
        
        print(f"Converting PDF to images (DPI: {self.dpi})...")
        
        # Convert PDF to list of images
        images = convert_from_path(
            str(pdf_path),
            dpi=self.dpi,
            fmt='jpeg'
        )
        
        print(f"✓ Converted {len(images)} page(s)")
        
        return images
    
    def save_images(self, images: List[Image.Image], output_dir: str = None) -> List[str]:
        """
        Save images to disk.
        
        Args:
            images: List of PIL Image objects
            output_dir: Directory to save images (default: temp directory)
            
        Returns:
            List of paths to saved images
        """
        if output_dir is None:
            output_dir = tempfile.mkdtemp()
        
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        saved_paths = []
        for i, img in enumerate(images):
            img_path = output_path / f"page_{i+1}.jpg"
            img.save(str(img_path), 'JPEG')
            saved_paths.append(str(img_path))
        
        print(f"✓ Saved {len(saved_paths)} image(s) to {output_dir}")
        
        return saved_paths
