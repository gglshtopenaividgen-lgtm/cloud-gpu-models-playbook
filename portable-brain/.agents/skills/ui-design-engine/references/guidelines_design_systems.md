# Agent Guidelines: Design Systems, Tokens & Dark Glassmorphism

> **Precision Design Engineering for Autonomous Agents**  
> **Integrates Liquid Glassmorphism, Specular Lighting, Anti-Default Typography, and Liveliness Dials**

---

## 1. Precision Dark Glassmorphism Token Architecture

Liquid glass is not a generic blurred rectangle. It simulates physical frosted glass illuminated by a directional raking key light from above:

```html
<!-- Precision Specular Dark Glass Container -->
<div class="relative overflow-hidden rounded-xl bg-slate-950/70 backdrop-blur-2xl border border-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.36)] before:absolute before:inset-x-0 before:top-0 before:h-[1px] before:bg-gradient-to-r before:from-transparent before:via-white/20 before:to-transparent">
  <!-- Content -->
  <div class="relative z-10 p-5">
    {children}
  </div>
</div>
```

### Key Physical Layers:
1. **Surface Base**: `bg-slate-950/70` or `bg-zinc-950/75` (high absorption to preserve legibility).
2. **Refractive Backdrop**: `backdrop-blur-2xl` (softens underlying content without visual vibration).
3. **Specular Top Lip**: `before:h-[1px] before:bg-gradient-to-r before:from-transparent before:via-white/20 before:to-transparent` (simulates edge highlight from overhead light).
4. **Boundary Outline**: `border border-white/10` (subtle specular definition).

---

## 2. Anti-Default Typography Architecture

Never cycle default Google fonts (reject Inter-only monotony, Space Grotesk cliché, and Cormorant Garamond luxury slop). Pair three distinct typefaces:

| Role | Recommended Faces | Weight & Tracking | When to Use |
|---|---|---|---|
| **Display / Headline** | `Outfit`, `Cabinet Grotesk`, `Sentient`, `Newsreader` | Bold / SemiBold, tracking `-0.02em` to `-0.03em` | Page titles, hero statements, category headlines. |
| **Body / Prose** | `Geist Sans`, `Switzer`, `General Sans`, `system-ui` | Regular / Medium, line-height $1.5\times$ to $1.7\times$ | Long-form reading, explanations, table values. |
| **Tabular Data / Code** | `Geist Mono`, `JetBrains Mono` | Medium, `tabular-nums` | Numerics, metrics, latency timestamps, hashes, code. |

### Fluid Clamp Scale (Zero Breakpoint Jumps):
```css
:root {
  --text-display: clamp(2.25rem, 5vw + 1rem, 4.5rem);
  --text-h1:      clamp(1.75rem, 3vw + 0.75rem, 3rem);
  --text-h2:      clamp(1.35rem, 2vw + 0.5rem, 2rem);
  --text-body:    clamp(0.95rem, 0.5vw + 0.75rem, 1.05rem);
  --text-caption: clamp(0.75rem, 0.25vw + 0.65rem, 0.85rem);
}
```

---

## 3. Liveliness Toolkit Dials

Configure these three dials per task to establish consistent personality:

| Dial | Range | 1 (Subdued) | 3 (Balanced) | 5 (High-Voltage) |
|---|---|---|---|---|
| **ENERGY** | 1 to 5 | Monochromatic slate/zinc, 1 accent color, zero glow. | Balanced SaaS, crisp emerald/sky accents, subtle specular rims. | High-contrast brutalist or neon cyberpunk, intense glows. |
| **RHYTHM** | 1 to 5 | Strict tabular data-grid, uniform 40px rows, fixed widths. | Bento grid with prominent hero card and secondary stats. | Asymmetric editorial offsets, overlapping layers, staggered layouts. |
| **MOTION** | 1 to 5 | Zero CSS transitions, instantaneous state changes. | Subtle 150–200ms ease-out transitions on hover/focus only. | Physics-based spring animations, layout morphs, interactive particles. |

---

## 4. Color Elevation & Semantic System (Slate Monolith)

```css
:root {
  /* Surface Elevation */
  --surface-canvas:      #020617; /* Slate 950 - Root canvas */
  --surface-raised:      #0f172a; /* Slate 900 - Card surfaces */
  --surface-elevated:    #1e293b; /* Slate 800 - Modals / Drawers */
  --surface-overlay:     rgba(2, 6, 23, 0.85);

  /* Borders & Highlights */
  --border-subtle:       rgba(255, 255, 255, 0.08);
  --border-specular:     rgba(255, 255, 255, 0.16);
  --highlight-top:       rgba(255, 255, 255, 0.20);

  /* Typography */
  --text-primary:        #f8fafc; /* Slate 50  - High contrast 15:1 */
  --text-secondary:      #cbd5e1; /* Slate 300 - Body text 10:1 */
  --text-muted:          #94a3b8; /* Slate 400 - Captions 6.5:1 */
  --text-disabled:       #64748b; /* Slate 500 - Disabled 4.5:1 */

  /* Accents */
  --accent-emerald:      #10b981; /* Success / Active / Online */
  --accent-sky:          #38bdf8; /* Informational / Link */
  --accent-amber:        #f59e0b; /* Warning / Quota nearing */
  --accent-rose:         #f43f5e; /* Danger / Error */
}
```
