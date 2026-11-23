# UI Design Engine: Design Tokens, Archetypes & Anti-Slop Guide

Technical specifications for archetype selection, design tokens, and anti-slop quality gates.

---

## 1. Archetype Specifications

| Archetype | Typography | Geometry | Spacing & Density | Best For |
|---|---|---|---|---|
| **SaaS Dashboard** | Outfit + Geist + JetBrains Mono | Subtle borders (`1px solid rgba(255,255,255,0.08)`), rounded-lg | Compact rows (36-40px), bento layout | Analytics, monitoring, developer portals |
| **Mobile PWA** | Inter / System Font | Floating action docks, touch-optimized cards | $\ge 44	ext{px}$ touch targets, thumb-zone controls | Mobile web apps, responsive client portals |
| **Game / HUD** | Pixel / Cabinet Grotesk | High-contrast neon accents, glassmorphic panels | Full-bleed viewports, audio-reactive cards | Interactive simulations, gaming dashboards |
| **Document Editor** | Newsreader / Sentient | Minimal distraction, centered container | `max-w-[68ch]` content column, fluid clamp typography | Long-form writing, publishing platforms |

---

## 2. Anti-Slop Quality Checklist Summary

1. No generic AI purple-cyan gradient washes.
2. Touch targets must be $\ge 44	ext{px}$ on mobile.
3. No horizontal viewport overflow at widths $\le 375	ext{px}$.
4. High-contrast accessible text adhering to WCAG AA standards.
5. Functional empty, loading, and error states on all data containers.
