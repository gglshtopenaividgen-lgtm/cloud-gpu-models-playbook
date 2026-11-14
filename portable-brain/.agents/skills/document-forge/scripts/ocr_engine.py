#!/usr/bin/env python3
"""
High-Speed Local OCR Engine (RapidOCR ONNX Runtime + PyMuPDF)
Part of the document-forge universal skill.
Performs CPU/ONNX-accelerated OCR on scanned PDFs, images, receipts, screenshots, and diagrams.
Zero external Tesseract binary installer dependencies.
"""

import argparse
import json
import os
import sys
from pathlib import Path

def get_ocr_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR
        return RapidOCR()
    except ImportError:
        raise ImportError("rapidocr_onnxruntime is not installed. Run: pip install rapidocr-onnxruntime")

def ocr_image(image_path: str, engine=None) -> list:
    """Runs OCR on an image file and returns structured text blocks."""
    if engine is None:
        engine = get_ocr_engine()
    
    result, elapse = engine(image_path)
    if not result:
        return []
    
    # Format: list of [box, text, score]
    blocks = []
    for item in result:
        box, text, score = item
        blocks.append({
            "text": text,
            "confidence": float(score),
            "box": box
        })
    return blocks

def ocr_pdf(pdf_path: str, max_pages: int = 0, engine=None) -> dict:
    """Renders PDF pages to images in-memory and extracts OCR text."""
    import pymupdf

    if engine is None:
        engine = get_ocr_engine()

    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    pages_to_process = min(total_pages, max_pages) if max_pages > 0 else total_pages

    page_results = []
    full_text = []

    for pno in range(pages_to_process):
        page = doc[pno]
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        
        result, elapse = engine(img_bytes)
        page_text = []
        page_blocks = []
        if result:
            for item in result:
                box, text, score = item
                page_text.append(text)
                page_blocks.append({"text": text, "confidence": float(score)})

        page_str = "\n".join(page_text)
        full_text.append(f"--- Page {pno + 1} ---\n{page_str}")
        page_results.append({
            "page": pno + 1,
            "text": page_str,
            "blocks": page_blocks
        })

    doc.close()
    return {
        "file": str(pdf_path),
        "total_pages": total_pages,
        "processed_pages": pages_to_process,
        "full_text": "\n\n".join(full_text),
        "pages": page_results
    }

def main():
    parser = argparse.ArgumentParser(description="High-Speed Local OCR Engine (RapidOCR)")
    parser.add_argument("input", help="Image (.png, .jpg, .webp) or PDF (.pdf) file to OCR")
    parser.add_argument("--max-pages", type=int, default=0, help="Max PDF pages to process (0 = all)")
    parser.add_argument("--output", "-o", default=None, help="Save extracted text to file")
    parser.add_argument("--json", action="store_true", help="Output raw structured JSON with bounding boxes and confidence")

    args = parser.parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    ext = input_path.suffix.lower()
    engine = get_ocr_engine()

    if ext == ".pdf":
        res = ocr_pdf(str(input_path), max_pages=args.max_pages, engine=engine)
        if args.json:
            out_content = json.dumps(res, indent=2)
        else:
            out_content = res["full_text"]
    else:
        blocks = ocr_image(str(input_path), engine=engine)
        if args.json:
            out_content = json.dumps(blocks, indent=2)
        else:
            out_content = "\n".join([b["text"] for b in blocks])

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(out_content, encoding="utf-8")
        print(f"[+] OCR text saved to: {out_p}")
    else:
        print(out_content)

if __name__ == "__main__":
    main()
