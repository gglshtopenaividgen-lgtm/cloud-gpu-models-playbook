#!/usr/bin/env python3
"""
Docling Forge: High-Fidelity Document & Table Converter (docling_forge.py)
========================================================================
Part of the document-forge universal skill.

Lightweight MIT Docling integration wrapper for converting PDF, DOCX, PPTX,
XLSX, and images into clean, structured Markdown with TableFormer tables.

Architecture & Strategy:
1. Native Docling Engine (Primary):
   If `docling` is installed, uses IBM's DocumentConverter with TableFormer
   neural table recognition and layout analysis for state-of-the-art document
   understanding.
2. High-Fidelity Zero-Weight Fallback (Secondary):
   If `docling` is not installed (e.g. to avoid multi-gigabyte PyTorch/CUDA wheels),
   gracefully falls back to:
   - PDF: `pymupdf4llm` (layout-aware GitHub Flavored Markdown + tables)
   - PDF Secondary: `pypdf` (pure-Python text & page extraction)
   - DOCX: `markitdown` + `python-docx` (XML table grid extraction)
   - PPTX: `markitdown` + `python-pptx` (slide container extraction)
   - XLSX: `openpyxl` + `markitdown` (cell formatting & formulas)
   Outputs clear non-blocking guidance for optional native docling installation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Check native Docling availability
try:
    import docling
    from docling.document_converter import DocumentConverter
    HAS_DOCLING = True
except ImportError:
    HAS_DOCLING = False
    DocumentConverter = None

# Check fallback libraries
try:
    import pymupdf4llm
    HAS_PYMUPDF4LLM = True
except ImportError:
    HAS_PYMUPDF4LLM = False

try:
    import pypdf
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    from markitdown import MarkItDown
    HAS_MARKITDOWN = True
except ImportError:
    HAS_MARKITDOWN = False

try:
    import docx
    HAS_PYTHON_DOCX = True
except ImportError:
    HAS_PYTHON_DOCX = False

try:
    import pptx
    HAS_PYTHON_PPTX = True
except ImportError:
    HAS_PYTHON_PPTX = False


def is_docling_available() -> bool:
    """Returns True if IBM Docling package is installed."""
    return HAS_DOCLING


def get_engine_status() -> Dict[str, Any]:
    """Returns status of native Docling and fallback document libraries."""
    return {
        "native_docling": HAS_DOCLING,
        "pymupdf4llm": HAS_PYMUPDF4LLM,
        "pypdf": HAS_PYPDF,
        "markitdown": HAS_MARKITDOWN,
        "python_docx": HAS_PYTHON_DOCX,
        "python_pptx": HAS_PYTHON_PPTX,
        "primary_engine": "IBM Docling (Native)" if HAS_DOCLING else "Universal Fallback (PyMuPDF4LLM + MarkItDown + PyPDF)",
    }


def convert_pdf_fallback(file_path: Path) -> str:
    """Converts PDF using PyMuPDF4LLM or PyPDF fallback."""
    if HAS_PYMUPDF4LLM:
        try:
            return pymupdf4llm.to_markdown(str(file_path))
        except Exception as e:
            print(f"[DoclingForge] PyMuPDF4LLM warning: {e}. Falling back to PyPDF...", file=sys.stderr)

    if HAS_PYPDF:
        try:
            reader = pypdf.PdfReader(str(file_path))
            pages_text = []
            for idx, page in enumerate(reader.pages, 1):
                p_text = page.extract_text() or ""
                pages_text.append(f"## Page {idx}\n\n{p_text.strip()}")
            return "\n\n---\n\n".join(pages_text)
        except Exception as e:
            print(f"[DoclingForge] PyPDF extraction error: {e}", file=sys.stderr)

    if HAS_MARKITDOWN:
        try:
            md = MarkItDown()
            res = md.convert(str(file_path))
            return res.text_content
        except Exception as e:
            print(f"[DoclingForge] MarkItDown extraction error: {e}", file=sys.stderr)

    raise RuntimeError("No suitable PDF conversion engine available (install pymupdf4llm, pypdf, or docling).")


def convert_docx_fallback(file_path: Path) -> str:
    """Converts DOCX preserving tables and headings."""
    if HAS_MARKITDOWN:
        try:
            md = MarkItDown()
            res = md.convert(str(file_path))
            return res.text_content
        except Exception:
            pass

    if HAS_PYTHON_DOCX:
        try:
            doc = docx.Document(str(file_path))
            parts = []
            for p in doc.paragraphs:
                if p.text.strip():
                    if p.style.name.startswith("Heading 1"):
                        parts.append(f"# {p.text.strip()}")
                    elif p.style.name.startswith("Heading 2"):
                        parts.append(f"## {p.text.strip()}")
                    elif p.style.name.startswith("Heading 3"):
                        parts.append(f"### {p.text.strip()}")
                    else:
                        parts.append(p.text.strip())

            # Extract tables as markdown tables
            for tbl in doc.tables:
                rows_md = []
                for r_idx, row in enumerate(tbl.rows):
                    cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                    rows_md.append("| " + " | ".join(cells) + " |")
                    if r_idx == 0:
                        rows_md.append("| " + " | ".join(["---"] * len(cells)) + " |")
                if rows_md:
                    parts.append("\n" + "\n".join(rows_md) + "\n")
            return "\n\n".join(parts)
        except Exception as e:
            print(f"[DoclingForge] python-docx extraction error: {e}", file=sys.stderr)

    raise RuntimeError("No suitable DOCX engine available.")


def convert_pptx_fallback(file_path: Path) -> str:
    """Converts PPTX slides into structured Markdown."""
    if HAS_MARKITDOWN:
        try:
            md = MarkItDown()
            res = md.convert(str(file_path))
            return res.text_content
        except Exception:
            pass

    if HAS_PYTHON_PPTX:
        try:
            prs = pptx.Presentation(str(file_path))
            parts = []
            for s_idx, slide in enumerate(prs.slides, 1):
                slide_lines = [f"## Slide {s_idx}"]
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            t = para.text.strip()
                            if t:
                                slide_lines.append(f"- {t}")
                    elif shape.has_table:
                        tbl = shape.table
                        rows_md = []
                        for r_idx, row in enumerate(tbl.rows):
                            cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                            rows_md.append("| " + " | ".join(cells) + " |")
                            if r_idx == 0:
                                rows_md.append("| " + " | ".join(["---"] * len(cells)) + " |")
                        if rows_md:
                            slide_lines.append("\n" + "\n".join(rows_md) + "\n")
                parts.append("\n".join(slide_lines))
            return "\n\n---\n\n".join(parts)
        except Exception as e:
            print(f"[DoclingForge] python-pptx extraction error: {e}", file=sys.stderr)

    raise RuntimeError("No suitable PPTX engine available.")


def convert_to_markdown(
    file_path: str | Path,
    output_path: Optional[str | Path] = None,
    max_lines: int = 0,
    tables_only: bool = False,
) -> str:
    """
    Main conversion entrypoint.
    Executes native Docling if available; otherwise uses high-fidelity fallbacks.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Document file not found: {path}")

    ext = path.suffix.lower()
    markdown_content = ""
    engine_used = ""

    # Strategy 1: Native IBM Docling Engine
    if HAS_DOCLING and DocumentConverter is not None:
        try:
            converter = DocumentConverter()
            result = converter.convert(str(path))
            markdown_content = result.document.export_to_markdown()
            engine_used = "IBM Docling (Native + TableFormer)"
        except Exception as e:
            print(f"[DoclingForge] Native Docling error: {e}. Switching to fallback...", file=sys.stderr)

    # Strategy 2: High-Fidelity Fallback Engines
    if not markdown_content:
        if ext == ".pdf":
            markdown_content = convert_pdf_fallback(path)
            engine_used = "PyMuPDF4LLM + PyPDF Fallback"
        elif ext in (".docx", ".doc"):
            markdown_content = convert_docx_fallback(path)
            engine_used = "MarkItDown + python-docx Fallback"
        elif ext in (".pptx", ".ppt"):
            markdown_content = convert_pptx_fallback(path)
            engine_used = "MarkItDown + python-pptx Fallback"
        else:
            # General multimedia / spreadsheet / text formats
            if HAS_MARKITDOWN:
                md = MarkItDown()
                result = md.convert(str(path))
                markdown_content = result.text_content
                engine_used = "MarkItDown Universal Engine"
            else:
                try:
                    markdown_content = path.read_text(encoding="utf-8", errors="replace")
                    engine_used = "Direct Text Ingestion"
                except Exception as e:
                    raise RuntimeError(f"Unable to read file '{path.name}': {e}")

    # Process tables only if requested
    if tables_only:
        lines = markdown_content.splitlines()
        table_lines = []
        in_table = False
        for line in lines:
            if line.strip().startswith("|") and line.strip().endswith("|"):
                table_lines.append(line)
                in_table = True
            elif in_table:
                table_lines.append("")
                in_table = False
        markdown_content = "\n".join(table_lines).strip()

    # Apply max_lines budget if requested
    lines = markdown_content.splitlines()
    if max_lines > 0 and len(lines) > max_lines:
        markdown_content = "\n".join(lines[:max_lines]) + f"\n\n... [Content truncated at {max_lines} lines]"

    if output_path:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(markdown_content, encoding="utf-8")
        print(f"[+] Converted '{path.name}' -> '{out_p}' ({len(lines)} lines, Engine: {engine_used})")
    
    return markdown_content


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Docling Forge: High-Fidelity Document & Table Converter (MIT Docling + Fallback Engine)"
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Input document path (.pdf, .docx, .pptx, .xlsx, .html, etc.)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Path to write the output Markdown file",
    )
    parser.add_argument(
        "--max-lines",
        type=int,
        default=0,
        help="Maximum lines of Markdown to output (0 for unlimited)",
    )
    parser.add_argument(
        "--tables-only",
        action="store_true",
        help="Extract and output only tabular sections",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Display library availability and Docling engine diagnostics",
    )
    args = parser.parse_args()

    if args.info:
        status = get_engine_status()
        print("\n" + "=" * 60)
        print(" DOCLING FORGE ENGINE DIAGNOSTICS")
        print("=" * 60)
        for k, v in status.items():
            badge = "✅ Available" if v is True else ("❌ Not Available" if v is False else str(v))
            print(f"  {k:<20}: {badge}")
        print("-" * 60)
        if not HAS_DOCLING:
            print("  Notice: IBM Docling native package is not installed.")
            print("  Zero-weight high-fidelity fallbacks (PyMuPDF4LLM, MarkItDown, PyPDF) are active.")
            print("  To enable native IBM Docling + TableFormer: pip install docling")
        print("=" * 60 + "\n")
        return 0

    if not args.file:
        parser.print_help()
        return 1

    try:
        content = convert_to_markdown(
            file_path=args.file,
            output_path=args.output,
            max_lines=args.max_lines,
            tables_only=args.tables_only,
        )
        if not args.output:
            print(content)
        return 0
    except Exception as e:
        print(f"Error during document conversion: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
