# Agent Guidelines: Presentation Engineering & PPTX 16:9 Design Systems

> **Universal Blueprint for AI Agents Authoring Presentations & Pitch Decks**  
> **Integrates Anthropic Claude Code PPTX Invariants, 16:9 Geometry, and Visual Anti-Slop Rules**

---

## 1. Canvas Geometry & 16:9 Coordinate Budget

Never generate slides using 4:3 legacy dimensions. All presentations must target **16:9 widescreen**.

| Environment | Canonical Dimensions | Safe Margin X | Safe Margin Y | Printable Budget |
|---|---|---|---|---|
| **python-pptx** | $13.333\text{ in} \times 7.500\text{ in}$ | $0.80\text{ in} - 12.53\text{ in}$ | $0.60\text{ in} - 6.90\text{ in}$ | Width: $11.733\text{ in}$, Height: $6.30\text{ in}$ |
| **PptxGenJS** (`LAYOUT_16x9`) | $10.0\text{ in} \times 5.625\text{ in}$ | $0.60\text{ in} - 9.40\text{ in}$ | $0.45\text{ in} - 5.17\text{ in}$ | Width: $8.80\text{ in}$, Height: $4.72\text{ in}$ |
| **Google Slides (`gslides`)** | $720\text{ pt} \times 405\text{ pt}$ | $30\text{ pt} - 690\text{ pt}$ | $20\text{ pt} - 385\text{ pt}$ | Width: $660\text{ pt}$, Height: $365\text{ pt}$ |

---

## 2. Visual Hierarchy & The 3-5-7 Rule

LLMs fail by generating "walls of text" with identical bullet points. Enforce structured visual hierarchy:

1. **Category Kicker**:
   - $10\text{–}11\text{pt}$ uppercase bold accent text placed $0.20"$ above the main headline.
   - Example: `INFRASTRUCTURE MIGRATION | Q3 RESULTS`
2. **Action-Oriented Headlines**:
   - Never write passive topic headers ("Architecture Overview", "Cost Analysis").
   - Always state the takeaway conclusion: *"Azure PostgreSQL Migration Eliminated 100% of Database Overages"*.
   - Size: $26\text{–}32\text{pt}$ Bold.
3. **Card Container Architecture**:
   - Group data into 2, 3, or 4 distinct cards (`ROUNDED_RECTANGLE`).
   - Card dimensions for 3-column layout ($13.333" \times 7.5"$ canvas):
     - Width: $3.64"$, Height: $4.40"$, Top: $2.10"$.
     - Card 1 Left: $0.80"$, Card 2 Left: $4.84"$, Card 3 Left: $8.88"$.
     - Inter-card gap: $0.40"$.
4. **Hero Metric Callouts**:
   - Major stats must feature large typography: **$44\text{–}56\text{pt}$ Bold numbers**, followed by a $10\text{–}12\text{pt}$ uppercase label.
5. **The 3-5-7 Anti-Crowding Rule**:
   - Maximum 3 to 5 cards per slide.
   - Maximum 5 to 7 bullet points or lines per card.
   - **Bold the first 2–4 words** of every bullet point for instant scannability.

---

## 3. Anthropic & Claude Code PPTX Footguns (Strict Invariants)

These errors corrupt PPTX files or crash PowerPoint:

1. **Hex Strings Must NEVER Contain `#` in PptxGenJS**:
   - ❌ `color: "#1E293B"`
   - ✅ `color: "1E293B"`
   - Passing `#` injects invalid XML tags into the drawing package.
2. **PptxGenJS Mutates Options In-Place**:
   - `PptxGenJS` converts inches/points into EMUs (English Metric Units) in-place on option objects.
   - **Never reuse an options dictionary** across multiple shapes or slides. Always clone or construct a fresh dictionary.
3. **Shadow Offsets Must Be Positive ($\ge 0$)**:
   - Negative shadow offsets crash the Office XML parser.
4. **Combo Charts Require Dual Axis Declarations**:
   - Any combo chart with secondary axes must declare **both** `valAxes` (two entries) and **both** `catAxes` (two entries). PowerPoint corrupts files with orphaned value axes.

---

## 4. Color Palettes (WCAG AA Compliant)

| Theme | Background | Primary Surface | Border | Text Dark | Accent |
|---|---|---|---|---|---|
| **Executive Dark** | `#020617` (Slate 950) | `#0F172A` (Slate 900) | `#1E293B` | `#F8FAFC` | `#38BDF8` (Sky) |
| **Clean Corporate** | `#F8FAFC` (Slate 50) | `#FFFFFF` (White) | `#E2E8F0` | `#0F172A` | `#2563EB` (Blue) |
| **Emerald Fintech** | `#020617` | `#064E3B` / Glass | `#047857` | `#ECFDF5` | `#10B981` (Emerald) |
