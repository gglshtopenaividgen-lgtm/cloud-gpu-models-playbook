#!/usr/bin/env python3
"""
Universal Multi-Format Document Converter (MarkItDown + PyMuPDF4LLM)
Part of the document-forge universal skill.
Converts PDF, DOCX, PPTX, XLSX, CSV, HTML, and images into clean, LLM-ready Markdown or JSON.
"""

import argparse
import os
import sys
from pathlib import Path

def convert_document(file_path: str, output_path: str = None, engine: str = "auto", max_lines: int = 0) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    markdown_content = ""

    # Strategy 1: PyMuPDF4LLM for high-speed digital PDF layout & tables
    if ext == ".pdf" and engine in ("auto", "pymupdf"):
        try:
            import pymupdf4llm
            markdown_content = pymupdf4llm.to_markdown(str(path))
        except Exception as e:
            if engine == "pymupdf":
                raise e
            # Fallback to MarkItDown
            pass

    # Strategy 2: MarkItDown for universal Office & multimedia formats
    if not markdown_content:
        from markitdown import MarkItDown
        md_engine = MarkItDown()
        result = md_engine.convert(str(path))
        markdown_content = result.text_content

    # Truncate if requested
    lines = markdown_content.splitlines()
    if max_lines > 0 and len(lines) > max_lines:
        markdown_content = "\n".join(lines[:max_lines]) + f"\n\n... [Truncated at {max_lines} lines]"

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(markdown_content, encoding="utf-8")
        print(f"[+] Converted '{path.name}' -> '{out_p}' ({len(lines)} lines)")
    else:
        print(markdown_content)

    return markdown_content

def main():
    parser = argparse.ArgumentParser(description="Universal Multi-Format Document Converter")
    parser.add_argument("file", help="Input file path (.pdf, .docx, .pptx, .xlsx, .csv, .html, etc.)")
    parser.add_argument("--output", "-o", default=None, help="Output markdown file path")
    parser.add_argument("--engine", choices=["auto", "pymupdf", "markitdown"], default="auto", help="Conversion engine")
    parser.add_argument("--max-lines", type=int, default=0, help="Limit output to first N lines")

    args = parser.parse_args()

    try:
        convert_document(args.file, args.output, args.engine, args.max_lines)
    except Exception as e:
        print(f"Error converting document: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
