# Agent Guidelines: The 6 Core UI Archetypes

> **Universal Blueprint for Selecting and Structuring Archetype Layouts**  
> **Part of ui-design-engine Mini Auto-Skill System**

---

## 1. High-Density SaaS & Operations Dashboard (`saas-dashboard`)

*   **Best For**: Cloud consoles, analytics dashboards, server monitors, CRM tools.
*   **Layout Blueprint**:
    - Persistent collapsed rail ($48\text{px}$) expandable to $220\text{px}$.
    - Sticky top utility/filter bar ($36\text{px}$–$44\text{px}$) with breadcrumbs and user status.
    - 12-column bento layout grid (`grid grid-cols-12 gap-4`).
*   **Row Density**:
    - Table rows strictly bounded to $36\text{px}$–$40\text{px}$ height (`py-2 px-3`). Never balloon to fluffy landing page heights.
*   **Alignment**:
    - Numeric metrics right-aligned in `tabular-nums font-mono`. Status columns use micro-badges ($6\text{px}$ ping dot + text).
*   **Typography**: Display: `Outfit`, Body: `Geist Sans`, Mono: `JetBrains Mono`.
*   **Empty State**: Active query filters with 1-click reset; zero fake vector illustrations.

---

## 2. Mobile PWA & Touch Workstations (`mobile-app`)

*   **Best For**: Mobile productivity apps, on-the-go tools, audio/touch workstations.
*   **Layout Blueprint**:
    - Primary thumb zone: Critical controls grouped in bottom 35% of the viewport.
    - Floating bottom dock with `pb-[calc(1rem+env(safe-area-inset-bottom))]`.
    - Edge padding: Mandatory `px-4` minimum.
*   **Touch Invariant**:
    - All targets evaluate to $\ge 44\text{px} \times 44\text{px}$ (`min-h-[44px] min-w-[44px]`).
    - Smaller icons wrap in negative margin hit buffers (`p-3 -m-3`).
*   **Zero Viewport Bleed**:
    - `w-full max-w-full overflow-x-hidden`. Strict testing on $375\text{px}$ screen width.
*   **Touch Traps**:
    - Wrap hover states in `@media (hover: hover)` to prevent sticky hover highlights on iOS Safari.

---

## 3. Game Canvas & Audio-Reactive HUD (`game-canvas`)

*   **Best For**: WebGL2 games, HTML5 Canvas 2.5D RPGs, audio synths, node visualizers.
*   **Layout Blueprint**:
    - Fixed full-bleed canvas layer (`fixed inset-0 z-0`).
    - Non-blocking HUD overlay (`pointer-events-none absolute inset-0 z-10`).
    - Interactive HUD cards selectively re-enable pointer interactions via `pointer-events-auto`.
*   **Telemetry**:
    - High-contrast monospace telemetry with subtle CRT framing (`border border-cyan-500/30 bg-black/80`).
*   **Audio-Reactive Meters**:
    - CSS custom properties bound to `AnalyserNode` frequency bins (`--bass-energy`, `--mid-energy`).

---

## 4. Document & TipTap Rich-Text Editor (`document-editor`)

*   **Best For**: Rich text notes, markdown studios, collaborative documents, study portals.
*   **Layout Blueprint**:
    - The Golden Reading Column: Text container strictly constrained to `max-w-[68ch] mx-auto`.
    - Editor surface uses `prose prose-slate prose-invert max-w-none` inside the constrained parent.
*   **Bubble Menus**:
    - Floating selection bubble menus (`@tiptap/extension-bubble-menu`) in dark glass with instant keyboard shortcuts (`⌘B`, `⌘I`, `⌘K`).
*   **Quiet Gutters**:
    - Block drag handles and line numbers remain invisible until line hover.

---

## 5. Standalone Interactive Artifact (`interactive-artifact`)

*   **Best For**: Single-file interactive prototypes, data visualizers, educational walkthroughs.
*   **Layout Blueprint**:
    - Self-contained frame with inlined CSS, bundled icons, and zero external font network delays.
    - Uses CSS Container Queries (`@container (min-width: 400px)`) to adapt smoothly across chat panels, modals, and fullscreen views.
*   **State Machine Isolation**:
    - Local `useReducer` or React state loops that never pollute global `window` scope.

---

## 6. Editorial Portfolio & Creative Showcase (`editorial-portfolio`)

*   **Best For**: Creative studios, founder portfolios, narrative landing pages, case studies.
*   **Layout Blueprint**:
    - Asymmetrical 12-column grid (`col-start-2 col-span-8`, `col-start-6 col-span-6`).
    - Dramatic fluid typography clamp: `text-[clamp(2.5rem,6vw,6rem)] font-light tracking-tight`.
*   **Restrained Motion**:
    - Luxurious transition curves (`duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]`) with zero bouncy cartoon physics.
