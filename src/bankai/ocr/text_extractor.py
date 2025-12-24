"""
OCR Text Extraction Module

Extracts text from images using Tesseract OCR.
"""

import pytesseract
from PIL import Image
from typing import List, Tuple, Dict
import numpy as np


class TextExtract:
    """Extract text from images using OCR."""
    
    def __init__(self, lang: str = 'eng'):
        """
        Initialize the OCR text extractor.
        
        Args:
            lang: Language for OCR (default: 'eng' for English)
        """
        self.lang = lang
        
        # Test if tesseract is available
        try:
            pytesseract.get_tesseract_version()
        except Exception as e:
            raise RuntimeError(
                "Tesseract OCR not found. Please install it:\n"
                "  Linux: sudo apt-get install tesseract-ocr\n"
                "  macOS: brew install tesseract\n"
                "  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki"
            )
    
    def extract_text(self, image: Image.Image) -> str:
        """
        Extract all text from an image.
        
        Args:
            image: PIL Image object
            
        Returns:
            Extracted text as string
        """
        text = pytesseract.image_to_string(image, lang=self.lang)
        return text
    
    def extract_text_from_region(
        self, 
        image: Image.Image, 
        bbox: Tuple[int, int, int, int]
    ) -> str:
        """
        Extract text from a specific region of an image.
        
        Args:
            image: PIL Image object
            bbox: Bounding box as (x_min, y_min, x_max, y_max)
            
        Returns:
            Extracted text as string
        """
        # Crop image to bounding box
        cropped = image.crop(bbox)
        
        # Extract text
        text = self.extract_text(cropped)
        
        return text.strip()
    
    def extract_text_with_boxes(
        self, 
        image: Image.Image
    ) -> List[Dict[str, any]]:
        """
        Extract text with bounding box information.
        
        Args:
            image: PIL Image object
            
        Returns:
            List of dictionaries with 'text', 'x', 'y', 'width', 'height'
        """
        data = pytesseract.image_to_data(image, lang=self.lang, output_type=pytesseract.Output.DICT)
        
        results = []
        n_boxes = len(data['text'])
        
        for i in range(n_boxes):
            text = data['text'][i].strip()
            if text:  # Only include non-empty text
                results.append({
                    'text': text,
                    'x': data['left'][i],
                    'y': data['top'][i],
                    'width': data['width'][i],
                    'height': data['height'][i],
                    'confidence': data['conf'][i]
                })
        
        return results
    
    def extract_from_table_cell(
        self,
        image: Image.Image,
        cell_bbox: Tuple[int, int, int, int],
        padding: int = 2
    ) -> str:
        """
        Extract text from a table cell with padding adjustments.
        
        Args:
            image: PIL Image object
            cell_bbox: Cell bounding box (x_min, y_min, x_max, y_max)
            padding: Pixels to remove from each edge (default: 2)
            
        Returns:
            Extracted text as string
        """
        x_min, y_min, x_max, y_max = cell_bbox
        
        # Add padding to avoid borders
        x_min += padding
        y_min += padding
        x_max -= padding
        y_max -= padding
        
        # Ensure valid coordinates
        x_min = max(0, x_min)
        y_min = max(0, y_min)
        x_max = min(image.width, x_max)
        y_max = min(image.height, y_max)
        
        if x_max <= x_min or y_max <= y_min:
            return ""
        
        return self.extract_text_from_region(image, (x_min, y_min, x_max, y_max))
