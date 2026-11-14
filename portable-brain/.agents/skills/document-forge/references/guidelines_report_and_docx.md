# Agent Guidelines: DOCX, PDF & Report Engineering

> **Universal Blueprint for AI Agents Generating Professional Documents & Executive Reports**  
> **Integrates DXA Column Budgeting, OOXML Invariants, Typographic Scales, and Redlining**

---

## 1. Typographic Rhythm & Modular Scales

1. **Modular Scale (1.25 Major Third)**:
   - Document Title: $26\text{ pt}$ Bold, Line Spacing $1.15\times$, Space After $12\text{ pt}$.
   - Heading 1: $18\text{ pt}$ Bold, Space Before $16\text{ pt}$, Space After $6\text{ pt}$, `keep_with_next = True`.
   - Heading 2: $14\text{ pt}$ Semi-Bold, Space Before $12\text{ pt}$, Space After $4\text{ pt}$, `keep_with_next = True`.
   - Body Paragraph: $10.5\text{ pt}$ Regular, Line Spacing $1.25\times$, Space After $6\text{ pt}$, Space Before $0\text{ pt}$.
2. **Zero Empty Paragraphs**:
   - Never insert `\n\n` or empty `<w:p>` blocks to force vertical space.
   - Adjust paragraph spacing exclusively through `paragraph_format.space_after` and `space_before`.
3. **Widow/Orphan & Page Break Guardrails**:
   - Always set `keep_with_next = True` on all heading styles. This prevents orphaned headings resting at the bottom of a page.
   - Enforce `widow_control = True` on body styles.

---

## 2. Table Auto-Fitting & DXA Mathematical Invariants

`python-docx` by default produces unstable tables that clip beyond printable margins. To ensure 100% stability:

- **The DXA Metric**:
  $$1\text{ inch} = 1440\text{ dxa} \quad (\text{twips; } 1/20 \text{ of a point})$$
- **US Letter Printable Budget ($1.0"$ Margins)**:
  $$\text{Page Width} = 8.5 \times 1440 = 12,240\text{ dxa}$$
  $$\text{Margins (Left + Right)} = 2.0 \times 1440 = 2,880\text{ dxa}$$
  $$\text{Printable Column Budget} = 9,360\text{ dxa}$$
- **Three Essential OOXML Table Rules**:
  1. `w:tblHeader`: Inject into row 0 `<w:trPr>` so header rows repeat automatically when tables split across page breaks.
  2. `w:cantSplit`: Inject into every `<w:trPr>` so individual rows never break across page boundaries.
  3. Explicit Column Sum: Every cell `<w:tcW>` and column `<w:gridCol>` must have an explicit width in `dxa` that sums exactly to the total table budget ($9,360\text{ dxa}$).

---

## 3. Tracked Changes (Redlining) & Comments

When reviewing legal documents or technical specifications:

- **Tracked Insertions**:
  ```xml
  <w:ins w:id="1" w:author="AI Reviewer" w:date="2026-10-07T12:00:00Z">
    <w:r><w:t>approved modification</w:t></w:r>
  </w:ins>
  ```
- **Tracked Deletions**:
  ```xml
  <w:del w:id="2" w:author="AI Reviewer" w:date="2026-10-07T12:00:00Z">
    <w:r><w:delText>deprecated clause</w:delText></w:r>
  </w:del>
  ```
- **Inline Comments**:
  Anchor via `<w:commentRangeStart w:id="1"/>` and `<w:commentRangeEnd w:id="1"/>`, pointing to entries in `word/comments.xml`.

---

## 4. Headless PDF Compilation

- When converting `.docx` or `.md` to print-ready `.pdf`:
  - Primary CLI: `python .../document-forge/scripts/office/soffice.py "document.docx" "document.pdf"`
  - Headless LibreOffice wrapper enforces timeout protection (30s) and terminates background daemon leaks.
