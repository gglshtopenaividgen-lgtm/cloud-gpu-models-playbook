# The Master Anti-Slop Design Matrix & Quality Checklist

> **Non-Negotiable Production Standards for AI-Generated User Interfaces**

---

## 1. The Core Anti-Slop Matrix

| Slop Tell / Anti-Pattern | Root Mechanism | Mandatory Production Alternative |
|---|---|---|
| **Purple/Indigo-to-Cyan Gradients** | Mode-collapse on AI SaaS landing templates | **Monochromatic Tonal Elevation**: Deep slate/zinc `#020617` or `#09090b` with directional raking light, desaturated accents, and single-source specular top lips. |
| **Inter Everywhere** | Defaulting to system-safe neutral grotesque | **Intentional Pairing**: Expressive display face (Outfit, Cabinet Grotesk, Sentient, Newsreader) + neutral workhorse (Geist Sans, Switzer) + true tabular mono (JetBrains Mono). |
| **Floating Card Soup** | Content arbitrarily partitioned into identical cards | **Structural Information Hierarchy**: Asymmetrical bento grids, inset "island" panels, hairline borders using surface-colored strokes, and whitespace-driven grouping. |
| **Icon in Colored Tile** | Canned startup visual filler | **Bare Mark Iconography**: Naked SVG glyphs with optical sizing, integrated directly into text baselines or structural anchors. No rounded squircle box. |
| **Eyebrow / Pill Badge Everywhere** | Artificial tagging on every header | **Clean Typographic Contrast**: High-contrast scale shifts, muted sublines, or sparse bracketed metadata `[v2.4]`. Never pill capsules with gradient backgrounds. |
| **Invisible-Content Trap** | `opacity: 0` entrance animations | **Visible-By-Default Invariant**: All layout and text must be 100% visible if CSS animation or JS fails. Animate `translate` or clip paths; never hide core content behind opacity reveals. |
| **Hover "Boop" (Translate-Y Jump)** | Buttons jumping upward on hover | **Clean Tonal State Shifts**: Background tint transition (150ms ease), border highlight intensification, or internal glyph micro-slide. Never bouncy vertical translations on buttons. |
| **Cut-Off Radial Glows** | Unbounded blur clipped by `overflow: hidden` | **Contained Specular Geometry**: Use `radial-gradient` masks within explicit bounding boxes or `box-shadow: inset` specular lips that cannot slice across container boundaries. |
| **Default All-Around Shadow** | Symmetric black fuzzy dropshadow halo | **Directional Low-Offset Light**: `0 1px 2px rgba(0,0,0,0.4)` + top lip specular highlight `inset 0 1px 0 rgba(255,255,255,0.08)`. |
| **Ragged Comparison Columns** | Variable copy lengths misaligning CTAs | **Grid Baseline Locking**: Independent card height synchronization with `grid-template-rows: subgrid` or flex-col with `mt-auto` anchoring CTAs to a shared baseline. |

---

## 2. The 10-Point Pre-Flight Verification Checklist

Before reporting ANY frontend task or artifact complete, verify:

- [ ] **1. No Purple Gradients**: No generic purple/cyan/blue-to-pink washes.
- [ ] **2. Non-Default Font Pairing**: Uses specific, deliberate typography pairings; not generic Inter-only.
- [ ] **3. Mobile Touch Target >= 44px**: All buttons, links, inputs have `min-h-[44px]` or touch expansion.
- [ ] **4. Zero Viewport Overflow**: Responsive down to 375px width without horizontal scrollbars.
- [ ] **5. Visible-by-Default Motion**: No core content starts at `opacity: 0` dependent on JS reveals.
- [ ] **6. No Hover Boops**: Buttons do not jump vertically on hover; state changes are tonal and crisp.
- [ ] **7. Verified Optical Centering**: Icons, numbers, and pills are mathematically and optically centered.
- [ ] **8. Contrast Ratio Compliance**: All text clears WCAG 2.1 AA/AAA contrast standards against dark glass.
- [ ] **9. Contained Specular Glows**: No cut-off radial glows clipped by container borders.
- [ ] **10. Authentic Copywriting**: Zero corporate AI buzzwords (*"seamlessly"*, *"delve"*, *"unleash"*, *"empower"*).
