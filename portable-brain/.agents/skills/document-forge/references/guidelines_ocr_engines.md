# Agent Guidelines: Modern Open-Source OCR & Document Understanding Engines

> **Universal Benchmark & Operational Guide for Document Parsing**  
> **Compares Docling, Marker, Surya, Nougat, RapidOCR, Tesseract, and PyMuPDF4LLM**

---

## 1. Engine Decision & Routing Matrix

| Scenario | Primary Engine | Secondary Engine | Rationale |
|---|---|---|---|
| **Native Digital PDF (Vector text layer exists)** | **`pymupdf4llm`** | `markitdown` | Sub-50ms CPU execution, zero vision hallucinations, extracts markdown tables perfectly. |
| **Scanned Documents, Forms & Receipts (CPU-Only VM)** | **`rapidocr_onnxruntime`** | `docling` (CPU mode) | Lightweight ONNX engine (15–50ms/crop), no gigabyte PyTorch weights, zero C++ builds. |
| **Enterprise Documents (PDF, DOCX, PPTX, XLSX)** | **`docling`** (IBM Research) | `pymupdf4llm` + `python-docx` | Permissive MIT license, unifies multiple formats into a single `DoclingDocument` AST with cell-level table tracking. |
| **Dense Academic Papers & LaTeX Math (GPU Server)** | **`marker-pdf`** (Datalab) | `nougat` (Meta AI) | Exceptional formula parsing, high GPU throughput (15–120 pgs/s). |
| **Multi-Language Scans (90+ Languages)** | **`surya-ocr`** (Datalab) | `tesseract` | Line-level polygon detection, reading order, multi-lingual scripts. |
| **Legacy Linux Servers** | **`tesseract`** | `rapidocr` | Pre-installed package on standard distributions (`apt-get install tesseract-ocr`). |

---

## 2. Benchmark Summary

1. **Docling (IBM Research - MIT)**:
   - *Best all-rounder for autonomous agents*.
   - Ingests PDF, DOCX, PPTX, XLSX, HTML, and images.
   - Outputs: Markdown, JSON AST, DoclingDocument.
   - Command: `docling "input.pdf" --to md --to json --output ./out/`
2. **PyMuPDF4LLM (Artifex - AGPL-3.0 / Commercial)**:
   - *Sub-second vector extractor*.
   - CPU throughput: 10–40ms per page (1,000+ pages/min).
   - Caveat: **Zero OCR capability**. Scanned rasters return blank text.
   - Command: `pymupdf4llm -o document.md input.pdf`
3. **RapidOCR (RapidAI - Apache 2.0)**:
   - *Lightweight CPU ONNX inference*.
   - Uses PP-OCRv4 (DBNet + SVTR). Footprint: ~150MB.
   - Latency: 15–50ms per crop, ~200ms per full page.
   - Python: `from rapidocr_onnxruntime import RapidOCR; engine = RapidOCR(); res, _ = engine("receipt.png")`
4. **Marker (Datalab - GPL-3.0 + RAIL)**:
   - *Frontier academic math & table extraction on GPU*.
   - Command: `marker_single input.pdf --output_dir ./out/ --output_format markdown`
5. **Surya (Datalab - GPL-3.0)**:
   - *Layout analysis, line detection & reading order*.
   - Command: `surya_ocr input.pdf --langs en --output_dir ./results`
6. **Nougat (Meta AI - CC-BY-NC-4.0)**:
   - *Autoregressive vision transformer for academic papers*.
   - High GPU requirement (12GB+ VRAM). High hallucination rate on non-academic forms.

---

## 3. Autonomous Agent Ingestion Hierarchy

```
Input File
   │
   ├── Is it Digital Vector PDF?
   │      └── YES ──► pymupdf4llm (Instant sub-50ms parse)
   │
   ├── Is it an Office File (.docx, .pptx, .xlsx)?
   │      └── YES ──► docling OR markitdown / python-docx / openpyxl
   │
   ├── Is it a Scanned Image / Low-Resource Environment?
   │      └── YES ──► rapidocr_onnxruntime (ONNX CPU, ~200ms)
   │
   └── Is it a Dense Academic Paper on GPU?
          └── YES ──► marker-pdf (GPU LaTeX formulas)
```
