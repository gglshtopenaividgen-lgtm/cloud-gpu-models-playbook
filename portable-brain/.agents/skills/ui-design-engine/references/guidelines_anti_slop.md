# The Anti-Slop UI/UX Codex for AI Agents

> **Synthesized from Hallmark (Together AI), Anti-Slop (38 Rules), and Pols.dev Design Laws**  
> **Mandatory Quality Guardrails for Autonomous AI Agents Generating User Interfaces**

---

## 1. The 12 Deadly Anti-Patterns of "AI Slop"

LLMs default to "slop" because statistical averaging drives them toward the median of their training set (predominantly 2021-era Vercel/Tailwind templates). Any appearance of these 12 patterns constitutes an immediate review failure:

### 1. Purple/Cyan Gradient Soup & Candy Auroras
*   **The Slop**: `bg-gradient-to-r from-indigo-500 via-purple-500 to-cyan-400` splashed across headings, CTA buttons, and ambient backgrounds; blurred pastel blobs (`mix-blend-mode: multiply`).
*   **The Fix**: Monochromatic tonal surfaces (Slate `#020617` or Zinc `#09090b`) with a single directional overhead light source (`inset 0 1px 0 rgba(255,255,255,0.12)`) and intentional brand-specific accent tokens.

### 2. Floating Card Syndrome & Uniform Drop Shadows
*   **The Slop**: Wrapping every paragraph and list item inside `rounded-2xl border border-slate-800 shadow-xl hover:-translate-y-1`.
*   **The Fix**: Structural chunking using negative space, subtle hairline dividing rules, background tonal shifts, and borderless bento alignments. Shadows must be directional and low-offset (`0 2px 4px rgba(0,0,0,0.2)`).

### 3. The Eyebrow Pill Cliché & Decorative Ticks
*   **The Slop**: Placing a tiny capsule badge (`rounded-full px-3 py-1 text-xs uppercase bg-purple-500/10`) with a Sparkles emoji (✨) or a 30px fading hairline tick above every headline.
*   **The Fix**: Quiet typographic kickers with crisp size/weight contrast, or dropping eyebrows entirely. Lead with the message.

### 4. The Stock Split Hero & Faux macOS Window Mockups
*   **The Slop**: Left: Eyebrow, gradient h1, 2-line subtitle, primary glowing CTA + ghost button. Right: CSS "macOS window" with traffic-light dots holding fake kanban cards or a `quickstart.ts` snippet.
*   **The Fix**: Bespoke asymmetrical compositions: full-width data visualization surfaces, interactive functional tools immediately usable on turn-1, or clean editorial typography with authentic photography.

### 5. The Kitchen-Sink Card
*   **The Slop**: Stacking an icon in a colored squircle tile, category tag, title, description, metadata pills, hairline divider, initials avatar, and glowing "Add" button into a single 320px box.
*   **The Fix**: Relentless visual pruning: maximum 3 elements per card (Primary Entity, Contextual Metric/Status, and Action Trigger).

### 6. The Invisible-Content Motion Trap
*   **The Slop**: Initializing DOM elements at `opacity: 0` via Framer Motion (`initial={{ opacity: 0 }}`) or scroll reveals. When JS hydrates late, fails, or runs in background tabs, the section renders as an empty void.
*   **The Fix**: **Content Visible by Default Law**: Motion applies strictly to already-visible elements on hover/focus/state changes. Entrance animations must fail open (`animation-fill-mode: backwards`).

### 7. Flat Value Washes & Low Contrast
*   **The Slop**: Mid-gray text (`text-slate-500`) against dark gray backgrounds (`bg-slate-900`) yielding unreadable 2.5:1 contrast ratios.
*   **The Fix**: Strict adherence to WCAG 2.1 AAA for body text ($\ge 7:1$) and AA for large display text ($\ge 4.5:1$). High-contrast token pairing: foreground `#f8fafc` on dark `#020617`, muted `#94a3b8`.

### 8. Ragged Comparison Columns & Misaligned CTAs
*   **The Slop**: In 3-tier pricing grids or feature comparisons, cards have uneven heights because copy lengths differ; buttons float at different baselines.
*   **The Fix**: Equalized column heights (`grid grid-cols-3 items-stretch`), dedicated CSS subgrid or flex-col wrappers with `mt-auto` anchoring action buttons to the bottom edge.

### 9. The Chronic Centering Miss & Cut-Off Borders
*   **The Slop**: Numbers visually floating 2px off-center in circles; descenders (`g, y, p`) sliced flat by `overflow-hidden` or tight `clip-path`.
*   **The Fix**: Optical centering verification (`dominant-baseline: central` in SVG; vertical clearance `py-1` buffers in CSS).

### 10. Broken Mobile Viewports & Horizontal Overflow
*   **The Slop**: Hardcoded pixel widths (`w-[600px]`), unpadded text touching screen edges, and $24\text{px}$ touch targets.
*   **The Fix**: Fluid-first rules: `w-full max-w-full overflow-x-hidden`, responsive container queries, standard $\ge 44\text{px}$ touch targets (`min-h-[44px] min-w-[44px]`), and mandatory viewport padding (`px-4 sm:px-6`).

### 11. Unstyled Native Form Controls & All-Caps Inputs
*   **The Slop**: Default OS gray `<select>` dropdowns; missing `:focus-visible` styling; applying `uppercase` transform to email/password fields.
*   **The Fix**: Complete restyling of form primitives: custom SVG chevrons, explicit `text-transform: none !important;`, and high-visibility accessible focus rings (`focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2`).

### 12. Synthetic AI Copywriting & Corporate Slop
*   **The Slop**: Filler text like *"Delve into the seamless tapestry of next-gen workflows,"* *"Empower your velocity,"* or *"Oops! Our server hit a hiccup!"*
*   **The Fix**: Authentic, direct, engineer-to-engineer tone. Precise technical nouns, actionable error states with root causes, and zero marketing fluff.

---

## 2. The Three-Tier Rule System

*   **Tier 1: Hard Gates (Non-Negotiable - Immediate Reject)**:
    - *Zero Invisible Initial State*: All content rendered and visible without animation.
    - *Touch Target Minimum*: $\ge 44\text{px} \times 44\text{px}$ on all interactive controls.
    - *Zero Viewport Bleed*: 100% responsive down to $375\text{px}$ with zero horizontal scrollbars.
    - *WCAG Contrast*: $\ge 7:1$ body contrast against background.
    - *Form Control Integrity*: No uppercase inputs, custom styled select dropdowns.
*   **Tier 2: Purpose Gates (Forbidden Without Functional Justification)**:
    - *No Unjustified Cards*: Content lives directly on the surface unless discrete/draggable/dismissible.
    - *No Ambient Shadows*: Shadows only for z-index elevation (modals, dropdowns, floating docks).
    - *No Decorative Gradients*: Forbidden on text and button fills unless explicitly requested.
    - *No Decorative Eyebrow Tags*: Headings lead with typography.
*   **Tier 3: Quality Locks (Craft & Polish)**:
    - *4px/8px Spatial Rhythm*: All padding/margin/gap locked to multiples of $4\text{px}$ / $8\text{px}$.
    - *Specular Directional Lighting*: Top-lip specular highlight (`inset 0 1px 0 rgba(255,255,255,0.12)`).
    - *Tabular Numbers*: Financial/metrics locked to `tabular-nums font-mono`.

---

## 3. The 15-Point Pre-Flight Verification Gate

Before committing or delivering any UI component, verify every checkpoint:

- [ ] 1. **No Gradients**: Zero text or background rainbow gradient fills.
- [ ] 2. **Tonal Elevation**: Surfaces elevate via luminance shifts (Slate-950 $\to$ Slate-900), not drop-shadow soup.
- [ ] 3. **Specular Top Lip**: Elevated cards feature `inset 0 1px 0 rgba(255,255,255,0.12)`.
- [ ] 4. **No Unjustified Cards**: Background content rests directly on the canvas where possible.
- [ ] 5. **Visible by Default**: Zero elements start at `opacity: 0`.
- [ ] 6. **Touch Bounds $\ge 44\text{px}$**: Every button, tab, link, or toggle satisfies `min-h-[44px] min-w-[44px]`.
- [ ] 7. **Zero $375\text{px}$ Bleed**: Page verified on 375px mobile viewport with zero horizontal scrolling.
- [ ] 8. **WCAG AAA/AA Contrast**: Text is `#f8fafc` on dark, muted text is `#94a3b8` (never unreadable mid-gray).
- [ ] 9. **4px/8px Spacing**: All spacing (`p-2`, `p-4`, `p-6`, `gap-3`, `gap-4`) conforms to the 4px/8px rhythm.
- [ ] 10. **Tabular Numerics**: All numbers, metrics, and timestamps use `tabular-nums font-mono`.
- [ ] 11. **Equalized Baselines**: Multi-column comparison cards have buttons anchored to the bottom via `mt-auto`.
- [ ] 12. **Optical Centering**: Badges, glyphs, and status dot chips are verified optically centered.
- [ ] 13. **Styled Form Primitives**: Native select dropdowns, checkboxes, and text inputs have custom dark glass styling.
- [ ] 14. **No Hover Boops**: Buttons never jump vertically on hover; state transitions are tonal.
- [ ] 15. **Authentic Copywriting**: Zero corporate AI filler (*"seamlessly"*, *"delve"*, *"unleash"*, *"empower"*).
