---
name: document-forge
description: "Universal document engineering powerhouse: convert, parse, edit, fill forms, calculate formulas, redline, and OCR across PDF, DOCX, PPTX, XLSX, and images. Automatically orchestrates Google Slides (gslides) for decks/PPTs and Google Docs (gdocs) for documents/PDFs."
---

# Document Forge: Universal Document, Presentation & OCR Engine

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/document-forge.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill document-forge`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` and CLI tools (`gslides`, `gdocs`) are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands.

---

## 1. Smart Routing Decision Matrix

| Output / Task Desired | Primary Engine | Local / Fallback Tool | Why Selected |
|:---|:---|:---|:---|
| **Slide Deck (`.pptx` / `.pdf`)** | **`gslides`** | `python-pptx`, `soffice.py` | 16:9 canvas (`720 × 405 pt`), visual verification via `export-thumbnail` |
| **Document / Report (`.docx` / `.pdf`)**| **`gdocs`** | `python-docx`, `docx-js` | Native markdown compilation, `--auto-fit-tables` column balancing |
| **Spreadsheets & Formulas (`.xlsx`)** | **`openpyxl` + `recalc.py`** | `pandas` | Headless formula evaluation via LibreOffice calc |
| **Scanned Documents & OCR** | **`ocr_engine.py`** | `convert_doc.py` | CPU/ONNX RapidOCR without Tesseract dependencies |
| **Digital PDF Parsing & Form Fill** | **`pymupdf4llm`** | `fill_pdf_form_with_annotations.py`| Sub-second Markdown extraction, form annotation filling |

---

## 2. Presentation & Document Invariants

- **`gslides` Visual Integrity**: Enforce strict 16:9 bounds (`720 × 405 pt`). Always inspect slide layout via `gslides export-thumbnail` before final delivery to ensure zero text card overlaps.
- **`gdocs` Table Formatting**: Always pass `--auto-fit-tables` when compiling markdown to eliminate horizontal margin clipping.
- **Deliverables Location**: Place generated documents and PDFs strictly in `<active-project>/temp_read/`.

---

## 3. Core CLI Commands

```bash
# 1. Create and populate presentation deck
gslides create --title "Architecture Overview"
gslides add-slide --layout TITLE_AND_BODY --title "System Topology"
gslides export --format pdf --out temp_read/deck.pdf

# 2. Compile document with auto-fit tables
gdocs mutate import-md --file temp_read/report.md --auto-fit-tables
gdocs export --format docx --out temp_read/report.docx

# 3. Universal document conversion to markdown
python .agents/skills/document-forge/scripts/convert_doc.py input.pdf -o temp_read/output.md

# 4. Perform local OCR on image or scanned document
python .agents/skills/document-forge/scripts/ocr_engine.py scan.png -o temp_read/ocr_text.md

# 5. Evaluate formulas in spreadsheet headless
python .agents/skills/document-forge/scripts/recalc.py data.xlsx
```

---

## 4. References & Format Guides

- [Format Conversions & OCR Guide](references/format_and_ocr_guide.md) — Complete parameter guide for `gslides`, `gdocs`, and local tools.
- [Document Engineering & OCR Reference](references/document_engineering_and_ocr_guide.md) — Architectural deep-dive on OCR pipelines.
- [Presentation Design Guidelines](references/guidelines_presentation_design.md) — 16:9 coordinate grid and typography rules.
- [Report & DOCX Guidelines](references/guidelines_report_and_docx.md) — Professional layout and table balancing standards.
- [PDF Reference & Forms Guide](references/pdf_reference.md) — Interactive PDF form-filling and parsing protocols.