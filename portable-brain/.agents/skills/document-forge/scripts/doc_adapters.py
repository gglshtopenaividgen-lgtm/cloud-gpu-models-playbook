"""
Unified Document Engineering & OCR Adapters for Autonomous AI Agents
File: doc_adapters.py
Location: <BRAIN_ROOT>/temp_read/doc_adapters.py

Modules Included:
1. UnifiedDocIngest: Multi-tier fallback router (PyMuPDF4LLM -> RapidOCR / Docling)
2. AgentPptxEngine: 16:9 Widescreen Layout Engine with Card Containers & Metric Callouts
3. AgentDocxEngine: Executive Report Generator with DXA Table Auto-fitting & cantSplit
4. DocxRedlineAdapter: Programmatic Tracked Changes (w:ins / w:del)
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# ---------------------------------------------------------------------------
# 1. Multi-Tier Document Ingestion Router
# ---------------------------------------------------------------------------

class UnifiedDocIngest:
    """
    Intelligent document ingest router:
    - Tier 0: Digital PDF -> PyMuPDF4LLM (sub-second vector markdown extraction)
    - Tier 1: Scanned raster / image -> RapidOCR (ultra-fast ONNX runtime, CPU-friendly)
    - Tier 2: Heavy multi-column / academic -> Docling (MIT, DocLayNet + TableFormer)
    """

    @staticmethod
    def is_digital_pdf(pdf_path: str, min_chars_per_page: int = 50) -> bool:
        """Determines whether a PDF has an embedded text layer or is a scanned raster image."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(pdf_path)
            sample_pages = min(len(doc), 3)
            for i in range(sample_pages):
                text = doc[i].get_text()
                if len(text.strip()) >= min_chars_per_page:
                    doc.close()
                    return True
            doc.close()
            return False
        except ImportError:
            # Fallback heuristic if PyMuPDF is not installed
            return True

    @classmethod
    def ingest_to_markdown(cls, file_path: str) -> str:
        """Route to optimal ingestion engine based on file type and raster status."""
        ext = Path(file_path).suffix.lower()

        if ext == ".pdf":
            if cls.is_digital_pdf(file_path):
                try:
                    import pymupdf4llm
                    return pymupdf4llm.to_markdown(file_path)
                except ImportError:
                    pass
            
            # Scanned PDF or PyMuPDF4LLM fallback -> Try Docling
            try:
                from docling.document_converter import DocumentConverter
                converter = DocumentConverter()
                result = converter.convert(file_path)
                return result.document.export_to_markdown()
            except ImportError:
                pass

        elif ext in [".png", ".jpg", ".jpeg", ".webp"]:
            # Image OCR -> RapidOCR (ONNX)
            try:
                from rapidocr_onnxruntime import RapidOCR
                engine = RapidOCR()
                result, _ = engine(file_path)
                if not result:
                    return ""
                lines = [item[1] for item in result]
                return "\n".join(lines)
            except ImportError:
                pass

        elif ext in [".docx", ".pptx", ".xlsx", ".html"]:
            try:
                from docling.document_converter import DocumentConverter
                converter = DocumentConverter()
                result = converter.convert(file_path)
                return result.document.export_to_markdown()
            except ImportError:
                pass

        # Final generic fallback
        return f"[WARN: No suitable parser found for {file_path}. Install pymupdf4llm, docling, or rapidocr_onnxruntime.]"


# ---------------------------------------------------------------------------
# 2. Agent PPTX Engine (16:9 Strict Coordinate Grid & Visual Hierarchy)
# ---------------------------------------------------------------------------

class AgentPptxEngine:
    """
    Programmatic 16:9 Presentation Generator enforcing:
    - 13.333" x 7.500" standard widescreen canvas
    - Safe margins (0.8" X, 0.6" Y)
    - Action-oriented takeaway headers + category kickers
    - Card container architecture (ROUNDED_RECTANGLE)
    - Large metric hero callouts (48pt stat + 12pt uppercase label)
    - Anti-slop scannability (bolded leads, max 5 bullets per card)
    """

    def __init__(self):
        try:
            from pptx import Presentation
            from pptx.util import Inches, Pt
            from pptx.enum.text import PP_ALIGN
            from pptx.dml.color import RGBColor
            from pptx.enum.shapes import MSO_SHAPE
        except ImportError:
            raise ImportError("python-pptx is required. Run: pip install python-pptx")

        self.prs = Presentation()
        # Enforce 16:9 Widescreen
        self.prs.slide_width = Inches(13.333)
        self.prs.slide_height = Inches(7.500)
        self.blank_layout = self.prs.slide_layouts[6]  # Blank slide

        # Design Tokens (Slate Executive Palette)
        self.C_BG = RGBColor(248, 250, 252)        # Slate 50 (Slide Canvas)
        self.C_CARD_BG = RGBColor(255, 255, 255)   # Pure White Card
        self.C_CARD_BORDER = RGBColor(226, 232, 240)# Slate 200 Border
        self.C_KICKER = RGBColor(79, 70, 229)      # Indigo 600 (Category Kicker)
        self.C_TITLE = RGBColor(15, 23, 42)        # Slate 900 (Action Headline)
        self.C_SUBTITLE = RGBColor(100, 116, 139)  # Slate 500
        self.C_BODY = RGBColor(51, 65, 85)         # Slate 700
        self.C_METRIC = RGBColor(15, 23, 42)       # Slate 900
        self.C_METRIC_LABEL = RGBColor(79, 70, 229)# Indigo Accent

    def add_header(self, slide, kicker: str, title: str, subtitle: Optional[str] = None):
        """Creates the hierarchical header band with category kicker and action headline."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import MSO_ANCHOR

        header_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(11.733), Inches(1.3))
        tf = header_box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        # Paragraph 1: Kicker
        p_kicker = tf.paragraphs[0]
        p_kicker.text = kicker.upper()
        p_kicker.font.size = Pt(11)
        p_kicker.font.bold = True
        p_kicker.font.color.rgb = self.C_KICKER
        p_kicker.space_after = Pt(2)

        # Paragraph 2: Takeaway Title
        p_title = tf.add_paragraph()
        p_title.text = title
        p_title.font.size = Pt(26)
        p_title.font.bold = True
        p_title.font.color.rgb = self.C_TITLE
        p_title.space_after = Pt(4)

        # Paragraph 3: Subtitle / Context (Optional)
        if subtitle:
            p_sub = tf.add_paragraph()
            p_sub.text = subtitle
            p_sub.font.size = Pt(13)
            p_sub.font.color.rgb = self.C_SUBTITLE

    def add_card(self, slide, left: float, top: float, width: float, height: float):
        """Adds a rounded rectangle card container with neutral border."""
        from pptx.util import Inches, Pt
        from pptx.enum.shapes import MSO_SHAPE

        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        card.fill.solid()
        card.fill.fore_color.rgb = self.C_CARD_BG
        card.line.color.rgb = self.C_CARD_BORDER
        card.line.width = Pt(1.0)
        return card

    def add_card_content(self, slide, left: float, top: float, width: float, height: float,
                         card_title: str, bullets: List[Tuple[str, str]],
                         metric: Optional[str] = None, metric_label: Optional[str] = None):
        """
        Populates a card with:
        - Optional Hero Metric (e.g., '42%', '10x') + Label
        - Card Subtitle
        - Bullets with bold leads
        """
        from pptx.util import Inches, Pt

        # 1. Background Card Shape
        self.add_card(slide, left, top, width, height)

        # 2. Text Frame inside the card (internal padding 0.3")
        pad = 0.3
        tb = slide.shapes.add_textbox(Inches(left + pad), Inches(top + pad), Inches(width - 2 * pad), Inches(height - 2 * pad))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0

        p_idx = 0
        if metric:
            p_metric = tf.paragraphs[0]
            p_metric.text = metric
            p_metric.font.size = Pt(44)
            p_metric.font.bold = True
            p_metric.font.color.rgb = self.C_METRIC
            p_metric.space_after = Pt(0)
            p_idx += 1

            if metric_label:
                p_ml = tf.add_paragraph()
                p_ml.text = metric_label.upper()
                p_ml.font.size = Pt(10)
                p_ml.font.bold = True
                p_ml.font.color.rgb = self.C_METRIC_LABEL
                p_ml.space_after = Pt(10)

        p_ct = tf.paragraphs[0] if (metric is None and p_idx == 0) else tf.add_paragraph()
        p_ct.text = card_title
        p_ct.font.size = Pt(16)
        p_ct.font.bold = True
        p_ct.font.color.rgb = self.C_TITLE
        p_ct.space_after = Pt(8)

        # Add bullets with bold lead words
        for lead, rest in bullets:
            p_b = tf.add_paragraph()
            p_b.space_after = Pt(6)

            r_lead = p_b.add_run()
            r_lead.text = f"• {lead}: "
            r_lead.font.bold = True
            r_lead.font.size = Pt(12)
            r_lead.font.color.rgb = self.C_TITLE

            r_rest = p_b.add_run()
            r_rest.text = rest
            r_rest.font.bold = False
            r_rest.font.size = Pt(12)
            r_rest.font.color.rgb = self.C_BODY

    def create_three_card_slide(self, kicker: str, title: str, cards_data: List[Dict[str, Any]], subtitle: Optional[str] = None):
        """Creates a standardized 3-column executive summary slide."""
        slide = self.prs.slides.add_slide(self.blank_layout)
        self.add_header(slide, kicker, title, subtitle)

        total_width = 11.733  # 13.333 - 2 * 0.8
        gap = 0.35
        card_w = (total_width - (2 * gap)) / 3.0  # ~3.67"
        card_h = 4.80
        top_y = 2.10

        for i, data in enumerate(cards_data[:3]):
            card_x = 0.80 + i * (card_w + gap)
            self.add_card_content(
                slide=slide,
                left=card_x,
                top=top_y,
                width=card_w,
                height=card_h,
                card_title=data.get("title", ""),
                bullets=data.get("bullets", []),
                metric=data.get("metric"),
                metric_label=data.get("metric_label")
            )
        return slide

    def save(self, output_path: str):
        self.prs.save(output_path)


# ---------------------------------------------------------------------------
# 3. Agent DOCX Engine (Typographic Rhythm, DXA Table Auto-fitting, cantSplit)
# ---------------------------------------------------------------------------

class AgentDocxEngine:
    """
    Executive Report Generator with:
    - 8.5" x 11" US Letter (12,240 x 15,840 dxa) with 1" margins
    - Printable body width = 9,360 dxa (6.5 inches)
    - Table column balancing, tblHeader repeating, cantSplit prevention
    - Modular typographic hierarchy (Major Third 1.25)
    """

    def __init__(self):
        try:
            import docx
            from docx.shared import Inches, Pt, RGBColor
            from docx.enum.text import WD_ALIGN_PARAGRAPH
            from docx.oxml import OxmlElement
            from docx.oxml.ns import qn
        except ImportError:
            raise ImportError("python-docx is required. Run: pip install python-docx")

        self.doc = docx.Document()
        
        # Configure Page Geometry (US Letter, 1" Margins)
        section = self.doc.sections[0]
        section.page_width = Inches(8.5)
        section.page_height = Inches(11.0)
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)

        self.TOTAL_DXA = 9360  # 6.5 inches in DXA (1440 * 6.5)

    def add_heading_1(self, text: str):
        """Adds Heading 1 with keep_with_next guardrail."""
        from docx.shared import Pt, RGBColor
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.size = Pt(18)
        run.font.bold = True
        run.font.color.rgb = RGBColor(15, 23, 42)
        return p

    def add_heading_2(self, text: str):
        """Adds Heading 2 with keep_with_next guardrail."""
        from docx.shared import Pt, RGBColor
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
        run = p.add_run(text)
        run.font.size = Pt(14)
        run.font.bold = True
        run.font.color.rgb = RGBColor(30, 41, 59)
        return p

    def add_body(self, text: str):
        """Adds body text with 1.25x line height and no redundant empty lines."""
        from docx.shared import Pt, RGBColor
        p = self.doc.add_paragraph()
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(6)
        p.paragraph_format.line_spacing = 1.25
        run = p.add_run(text)
        run.font.size = Pt(10.5)
        run.font.color.rgb = RGBColor(51, 65, 85)
        return p

    def add_auto_fit_table(self, headers: List[str], rows: List[List[str]], col_proportions: Optional[List[float]] = None):
        """
        Creates an enterprise-grade table:
        - Exact DXA width distribution totaling exactly 9360 dxa
        - tblHeader enabled on row 0
        - cantSplit enabled on all rows
        - Header cell shading and subtle cell borders
        """
        from docx.oxml import OxmlElement, parse_xml
        from docx.oxml.ns import qn, nsdecls
        from docx.shared import Pt, RGBColor

        num_cols = len(headers)
        if not col_proportions:
            col_proportions = [1.0 / num_cols] * num_cols

        # Normalize proportions
        sum_p = sum(col_proportions)
        col_widths_dxa = [int((p / sum_p) * self.TOTAL_DXA) for p in col_proportions]

        table = self.doc.add_table(rows=len(rows) + 1, cols=num_cols)
        table.autofit = False

        # Apply Table Properties: alignment center
        tblPr = table._tbl.tblPr
        tblW = OxmlElement('w:tblW')
        tblW.set(qn('w:w'), str(self.TOTAL_DXA))
        tblW.set(qn('w:type'), 'dxa')
        tblPr.append(tblW)

        # 1. Format Header Row
        hdr_row = table.rows[0]
        trPr = hdr_row._tr.get_or_add_trPr()
        trPr.append(OxmlElement('w:tblHeader'))
        trPr.append(OxmlElement('w:cantSplit'))

        for i, title in enumerate(headers):
            cell = hdr_row.cells[i]
            cell.width = col_widths_dxa[i]
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(4)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(title)
            run.font.bold = True
            run.font.size = Pt(10)
            run.font.color.rgb = RGBColor(15, 23, 42)

            # Cell shading (Light Slate #F1F5F9)
            shd = parse_xml(r'<w:shd {} w:fill="F1F5F9"/>'.format(nsdecls('w')))
            cell._tc.get_or_add_tcPr().append(shd)

        # 2. Format Body Rows
        for r_idx, row_data in enumerate(rows):
            row = table.rows[r_idx + 1]
            trPr = row._tr.get_or_add_trPr()
            trPr.append(OxmlElement('w:cantSplit'))  # Never split across pages mid-row

            # Zebra striping for even rows
            bg_color = "F8FAFC" if (r_idx % 2 == 1) else "FFFFFF"

            for c_idx, val in enumerate(row_data):
                cell = row.cells[c_idx]
                cell.width = col_widths_dxa[c_idx]
                p = cell.paragraphs[0]
                p.paragraph_format.space_before = Pt(3)
                p.paragraph_format.space_after = Pt(3)
                run = p.add_run(str(val))
                run.font.size = Pt(9.5)
                run.font.color.rgb = RGBColor(51, 65, 85)

                if bg_color != "FFFFFF":
                    shd = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), bg_color))
                    cell._tc.get_or_add_tcPr().append(shd)

        self.doc.add_paragraph().paragraph_format.space_after = Pt(6)
        return table

    def save(self, output_path: str):
        self.doc.save(output_path)


# ---------------------------------------------------------------------------
# 4. Programmatic Tracked Changes (Redlining) Adapter
# ---------------------------------------------------------------------------

class DocxRedlineAdapter:
    """
    Injects OpenXML Tracked Changes:
    - w:ins for inserted text
    - w:del for deleted text
    Allows agents to act as legal/compliance redliners.
    """

    @staticmethod
    def add_tracked_insertion(paragraph, text: str, author: str = "AI Agent", date_iso: str = "2026-10-07T12:00:00Z"):
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsdecls

        xml = (
            f'<w:ins {nsdecls("w")} w:id="101" w:author="{author}" w:date="{date_iso}">'
            f'  <w:r>'
            f'    <w:rPr><w:color w:val="15803D"/></w:rPr>'  # Green text
            f'    <w:t>{text}</w:t>'
            f'  </w:r>'
            f'</w:ins>'
        )
        ins_elem = parse_xml(xml)
        paragraph._p.append(ins_elem)

    @staticmethod
    def add_tracked_deletion(paragraph, text: str, author: str = "AI Agent", date_iso: str = "2026-10-07T12:00:00Z"):
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsdecls

        xml = (
            f'<w:del {nsdecls("w")} w:id="102" w:author="{author}" w:date="{date_iso}">'
            f'  <w:r>'
            f'    <w:rPr><w:strike/><w:color w:val="B91C1C"/></w:rPr>'  # Strikethrough Red
            f'    <w:delText>{text}</w:delText>'
            f'  </w:r>'
            f'</w:del>'
        )
        del_elem = parse_xml(xml)
        paragraph._p.append(del_elem)
