---
name: ui-design-engine
description: "Universal frontend design engine & quality orchestrator: dynamic archetype router, 15-point anti-slop verification, dark glassmorphism tokens, and component scaffolders."
---

# UI Design Engine: Frontend Architecture & Anti-Slop Orchestrator

> **Step-0 Project Overlay**: Before executing, check if `<active-project>/.agents/skill_overlays/ui-design-engine.md` exists (via `python .agents/skills/auto-skill/scripts/resolve_skill_overlay.py --project <root> --skill ui-design-engine`).

> [!IMPORTANT]
> ⛔ **EXECUTION-FIRST MANDATE**: Scripts in `scripts/` are executable software tools, NOT documentation. Never ask the user to run them or read them passively. Execute immediately via shell commands. When invoking Windows binaries from WSL, append `< /dev/null`.

The UI Design Engine eliminates "AI slop" (purple-cyan washes, floating card soup, Inter-only typography, broken mobile viewports) by dynamically selecting tokens, typography, and geometry based on project archetype.

---

## 1. Dynamic Archetype Routing

| Archetype | Typography | Geometry & Cards | Density & Spacing |
|:---|:---|:---|:---|
| **SaaS Dashboard** | Outfit + Geist + JetBrains Mono | Subtle borders (`1px solid rgba(255,255,255,0.08)`), rounded-lg | 36-40px compact table rows, bento layout |
| **Mobile PWA** | Inter / System Font | Floating action docks, touch-optimized cards | $\ge 44	ext{px}$ touch targets, thumb-zone controls |
| **Game / HUD** | Pixel / Cabinet Grotesk | High-contrast neon accents, glassmorphic panels | Full-bleed viewports, audio-reactive cards |
| **Document Editor** | Newsreader / Sentient | Minimal distraction, centered container | `max-w-[68ch]` content column, fluid clamp typography |

---

## 2. 15-Point Anti-Slop Quality Gate

1. **Anti-Purple Rule**: Zero generic purple-cyan-blue gradient washes on dark backgrounds.
2. **Mobile Ergonomics**: Touch targets strictly $\ge 44	ext{px}$; zero horizontal scroll at widths $\le 375	ext{px}$.
3. **Contrast & Hierarchy**: Adhere to WCAG AA contrast standards.
4. **State Completeness**: Every view must implement functional empty, loading, and error states.
5. **Fluid Typography**: Use `clamp()` for headings to prevent mobile wrapping anomalies.

---

## 3. Core CLI Commands

```bash
# 1. Query UI tokens and layout specs by archetype
python .agents/skills/ui-design-engine/scripts/select_ui_resource.py "dashboard"

# 2. Query mobile touch patterns
python .agents/skills/ui-design-engine/scripts/select_ui_resource.py "mobile touch player"

# 3. Scaffold component bundle
python .agents/skills/ui-design-engine/scripts/scaffold_ui.py --archetype saas --name user-table
```

---

## 4. References & Design Guidelines

- [Design Tokens, Archetypes & Anti-Slop Guide](references/design_tokens_and_archetypes.md)
- [Anti-Slop Rules Reference](references/anti_slop_rules.md)
- [Design Systems Guidelines](references/guidelines_design_systems.md)
- [Tokens & Glassmorphism Reference](references/tokens_and_glassmorphism.md)
- [Archetype Guidelines](references/guidelines_archetypes.md)