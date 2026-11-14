#!/usr/bin/env python3
"""
Dynamic UI/UX Architecture & Resource Router (Mini Auto-Skill for UI)
Part of ui-design-engine universal skill.
Given a project type or design goal, outputs the optimal:
- Design tokens & Liquid Glass CSS variables
- Typographic pairings (Display + Body + Tabular Mono)
- Archetype layout geometry & mobile touch bounds
- 10-Point Anti-Slop Verification Checklist
"""

import argparse
import json
import sys
from typing import Dict, Any

ARCHETYPES = {
    "saas-dashboard": {
        "name": "High-Density Operations & SaaS Dashboard",
        "best_for": "Cloud consoles, analytics dashboards, data engines, CRM systems",
        "typography": {
            "display": "Outfit (SemiBold, -0.02em tracking)",
            "body": "Geist Sans (Regular/Medium)",
            "mono": "JetBrains Mono (tabular-nums)"
        },
        "layout": "Persistent collapsible sidebar (240px -> 64px) + sticky glass header (56px) + bento layout grid (grid-cols-12 gap-4)",
        "accent": "Emerald #10b981 or Crisp White #f8fafc with Slate-950 #020617 background",
        "data_density": "Table row height 40px compact, text-left, numeric-right tabular-nums, 6px solid status dot chips",
        "tokens": {
            "background": "224 71% 4%",
            "foreground": "210 40% 98%",
            "card": "222 47% 7%",
            "border": "217 33% 18% / 0.6",
            "primary": "210 40% 98%"
        }
    },
    "mobile-app": {
        "name": "Mobile Ergonomics & PWA Studio",
        "best_for": "Mobile productivity apps, on-the-go tools, audio/touch workstations",
        "typography": {
            "display": "Plus Jakarta Sans / Outfit",
            "body": "Geist Sans (Medium for enhanced touch legibility)",
            "mono": "JetBrains Mono"
        },
        "layout": "Lower 35% thumb-zone action cluster + floating bottom dock (pb-[calc(5rem+env(safe-area-inset-bottom))])",
        "accent": "Directional high-contrast glow, haptic visual squash (active:scale-[0.98])",
        "touch_bounds": "Strict min-height 44px, min-width 44px, zero horizontal overflow at <=375px",
        "tokens": {
            "background": "224 71% 3%",
            "foreground": "210 40% 98%",
            "card": "222 47% 6%",
            "border": "217 33% 20% / 0.7",
            "primary": "210 40% 98%"
        }
    },
    "game-canvas": {
        "name": "Game Canvas & Audio-Reactive HUD",
        "best_for": "WebGL2 games, 2.5D RPGs, canvas node graphs, audio synths, visualizers",
        "typography": {
            "display": "Pixeloid / Silkscreen / Space Grotesk",
            "body": "VT323 / IBM Plex Mono",
            "mono": "JetBrains Mono"
        },
        "layout": "Fixed full-bleed canvas (z-0) + pointer-events-none HUD overlay (z-10) with interactive glass nodes",
        "accent": "Gold specular edges (border-amber-500/30) on Obsidian glass (#09090b) or Neon Cyan/Emerald",
        "styling": "CRT scanlines, Web Audio AnalyserNode CSS custom properties sync (--bass-energy)",
        "tokens": {
            "background": "0 0% 4%",
            "foreground": "45 100% 96%",
            "card": "0 0% 7%",
            "border": "45 90% 45% / 0.4",
            "primary": "45 90% 55%"
        }
    },
    "document-editor": {
        "name": "Distraction-Free Document & TipTap Editor",
        "best_for": "Rich text documents, markdown studios, collaborative notes, knowledge bases",
        "typography": {
            "display": "Newsreader / Sentient (Italic accents)",
            "body": "Switzer / Plus Jakarta Sans (leading-relaxed 1.7)",
            "mono": "Fragment Mono"
        },
        "layout": "Constrained reading column max-w-[68ch] or max-w-prose + floating bubble & slash command menus",
        "accent": "Subdued white-on-slate glass with inset active markers and KaTeX scrollable blocks",
        "tokens": {
            "background": "220 20% 6%",
            "foreground": "210 40% 98%",
            "card": "220 20% 9%",
            "border": "217 20% 20% / 0.5",
            "primary": "210 40% 98%"
        }
    },
    "interactive-artifact": {
        "name": "Self-Contained Standalone HTML/React Artifact",
        "best_for": "Single-file interactive prototypes, data visualizers, educational walkthroughs",
        "typography": {
            "display": "Outfit (SemiBold)",
            "body": "Geist Sans",
            "mono": "JetBrains Mono"
        },
        "layout": "Self-contained card frame with inlined CSS/JS, Tailwind 3.4, and shadcn theming",
        "accent": "Liquid Glass specular highlights with dark slate backdrop",
        "tokens": {
            "background": "224 71% 4%",
            "foreground": "210 40% 98%",
            "card": "222 47% 8%",
            "border": "217 33% 20% / 0.6",
            "primary": "210 40% 98%"
        }
    },
    "editorial-portfolio": {
        "name": "Editorial Portfolio & Creative Showcase",
        "best_for": "Creative studios, founder portfolios, narrative landing pages, case studies",
        "typography": {
            "display": "Cabinet Grotesk / Sentient (tracking-tight)",
            "body": "General Sans / Switzer",
            "mono": "Geist Mono"
        },
        "layout": "Asymmetric 12-column grid + fluid clamp typography + restrained motion curves",
        "accent": "Crimson Rose #e11d48 on Obsidian #09090b",
        "tokens": {
            "background": "240 10% 4%",
            "foreground": "0 0% 98%",
            "card": "240 10% 7%",
            "border": "240 10% 16% / 0.5",
            "primary": "346 77% 50%"
        }
    }
}

ANTI_SLOP_CHECKLIST = [
    "1. NO PURPLE/CYAN GRADIENTS: Monochromatic tonal elevation (Slate/Zinc #020617) with directional light.",
    "2. NON-DEFAULT FONT PAIRING: Use intentional pairings (Display + Body + Tabular Mono), never raw default Inter-only.",
    "3. MOBILE TOUCH TARGET >= 44PX: Every button, toggle, and link satisfies min-h-[44px] or touch pad expansion.",
    "4. ZERO VIEWPORT OVERFLOW: Viewport stays strictly within bounds down to 375px with zero horizontal scrollbars.",
    "5. VISIBLE-BY-DEFAULT MOTION: Core content never starts at opacity: 0; layouts remain 100% functional without JS.",
    "6. NO HOVER BOOPS: Buttons never jump upward on hover; state changes are tonal (background tint, border glow).",
    "7. VERIFIED OPTICAL CENTERING: Badges, glyphs, and numbers are optically and mathematically centered.",
    "8. CONTRAST COMPLIANCE: All text clears WCAG 2.1 AA/AAA contrast ratios against translucent glass surfaces.",
    "9. CONTAINED SPECULAR GLOWS: Inset top lips (inset 0 1px 0 rgba(255,255,255,0.12)), no cut-off blur boxes.",
    "10. AUTHENTIC COPYWRITING: Zero corporate AI filler ('seamlessly', 'unleash', 'empower', 'dive in').",
    "11. NO UNJUSTIFIED CARDS: Content rests directly on canvas unless discrete, draggable, or dismissible.",
    "12. SPATIAL RHYTHM: All spacing adheres strictly to 4px/8px multiples.",
    "13. TABULAR NUMERICS: Financial metrics, timestamps, and hashes locked to tabular-nums font-mono.",
    "14. EQUALIZED BASELINES: Multi-column comparison cards have buttons anchored to the bottom via mt-auto.",
    "15. STYLED FORM PRIMITIVES: Native select dropdowns and inputs have custom dark glass styling."
]

def route_ui(project_type: str, json_mode: bool = False):
    arch = ARCHETYPES.get(project_type.lower())
    if not arch:
        print(f"Error: Unknown project type '{project_type}'. Choices: {list(ARCHETYPES.keys())}", file=sys.stderr)
        sys.exit(1)

    result = {
        "archetype": arch,
        "anti_slop_checklist": ANTI_SLOP_CHECKLIST
    }

    if json_mode:
        print(json.dumps(result, indent=2))
        return

    print("=================================================================")
    print(f"UI/UX ARCHETYPE ROUTE: {arch['name'].upper()}")
    print("=================================================================")
    print(f"Best For:     {arch['best_for']}")
    print(f"Layout Spec:  {arch['layout']}")
    print("\nTypography System:")
    print(f"  • Display:  {arch['typography']['display']}")
    print(f"  • Body:     {arch['typography']['body']}")
    print(f"  • Mono:     {arch['typography']['mono']}")
    print("\nAccent & Highlights:")
    print(f"  • Accent:   {arch['accent']}")
    if "touch_bounds" in arch:
        print(f"  • Bounds:   {arch['touch_bounds']}")
    if "data_density" in arch:
        print(f"  • Density:  {arch['data_density']}")

    print("\nLiquid Glass CSS Tokens (OKLCH/HSL):")
    for k, v in arch["tokens"].items():
        print(f"  --{k.ljust(12)}: {v};")

    print("\n-----------------------------------------------------------------")
    print("10-POINT MANDATORY ANTI-SLOP PRE-FLIGHT CHECKLIST:")
    print("-----------------------------------------------------------------")
    for check in ANTI_SLOP_CHECKLIST:
        print(f"  [ ] {check}")
    print()

def main():
    parser = argparse.ArgumentParser(description="Dynamic UI/UX Architecture & Resource Router (ui-design-engine)")
    parser.add_argument("type", choices=list(ARCHETYPES.keys()), help="Target UI archetype")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()
    route_ui(args.type, args.json)

if __name__ == "__main__":
    main()
