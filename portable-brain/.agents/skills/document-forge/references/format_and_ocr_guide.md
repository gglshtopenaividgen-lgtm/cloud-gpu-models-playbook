# Document Forge: Format Conversions, OCR Recipes & Cloud Workspace Guide

Detailed recipes for Google Docs (`gdocs`), Google Slides (`gslides`), OpenPyXL spreadsheets, and RapidOCR processing.

---

## 1. Google Slides (`gslides`) Engine

- **Strict Canvas Dimensions**: 16:9 ratio, fixed at `720 × 405 pt`.
- **Card and Text Balancing**:
  - Always enforce coordinate bounding to prevent text truncation and overlapping card shapes.
  - Export thumbnails (`gslides export-thumbnail --slide <n>`) to visually verify slide geometry.
- **CLI Commands**:
  ```bash
  gslides create --title "System Architecture Review"
  gslides add-slide --layout TITLE_AND_BODY --title "Component Topology"
  gslides export --format pdf --out temp_read/deck.pdf
  ```

---

## 2. Google Docs (`gdocs`) Engine

- **Markdown Import**: Use `mutate import-md --auto-fit-tables` to auto-balance table widths and eliminate horizontal margin clipping.
- **CLI Commands**:
  ```bash
  gdocs create --title "Specification Report"
  gdocs mutate import-md --file input.md --auto-fit-tables
  gdocs export --format docx --out temp_read/report.docx
  ```

---

## 3. Local Document Conversion & OCR

- **RapidOCR Extraction**:
  ```bash
  python .agents/skills/document-forge/scripts/ocr_engine.py input_scan.pdf -o temp_read/ocr_text.md
  ```
- **LibreOffice Headless Recalculation**:
  ```bash
  python .agents/skills/document-forge/scripts/recalc.py input_sheet.xlsx
  ```
- **Docling / MarkItDown Universal Converter**:
  ```bash
  python .agents/skills/document-forge/scripts/convert_doc.py document.docx -o temp_read/output.md
  ```
