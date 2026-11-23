#!/usr/bin/env python3
"""
select_ui_resource.py - Dynamic UI Architecture & Resource Selector (Mini Auto-Skill for UI)
Part of ui-design-engine universal skill.

Allows agents and developers to query UI resources, archetypes, and anti-slop guidelines:
  python select_ui_resource.py "mobile player with touch controls"
  python select_ui_resource.py "high density admin dashboard"
  python select_ui_resource.py "anti-slop checklist"
  python select_ui_resource.py "dark glassmorphism tokens"
"""

import sys
import json
import argparse
from pathlib import Path

SKILL_ROOT = Path(__file__).parent.parent
REGISTRY_FILE = SKILL_ROOT / "references" / "ui_registry.json"

def load_registry():
    if not REGISTRY_FILE.exists():
        return {}
    return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))

def query_ui(query_str: str, json_mode: bool = False):
    registry = load_registry()
    archetypes = registry.get("archetypes", {})
    query = query_str.lower().strip()

    # Check for direct anti-slop or design system query
    if any(k in query for k in ["slop", "anti-slop", "checklist", "gate", "rules"]):
        anti_slop_path = SKILL_ROOT / "references" / "guidelines_anti_slop.md"
        if anti_slop_path.exists():
            print(f"\n[UI Selector] Matching Resource: Anti-Slop Codex ({anti_slop_path.name})")
            print("=" * 65)
            content = anti_slop_path.read_text(encoding="utf-8")
            # print first 50 lines
            print("\n".join(content.splitlines()[:50]))
            print(f"\n... Full guidelines: {anti_slop_path}")
            return

    if any(k in query for k in ["glass", "tokens", "css", "typography", "font", "dials", "liveliness"]):
        ds_path = SKILL_ROOT / "references" / "guidelines_design_systems.md"
        if ds_path.exists():
            print(f"\n[UI Selector] Matching Resource: Design Systems & Glassmorphism ({ds_path.name})")
            print("=" * 65)
            content = ds_path.read_text(encoding="utf-8")
            print("\n".join(content.splitlines()[:55]))
            print(f"\n... Full guidelines: {ds_path}")
            return

    # Match Archetypes by score
    scores = {}
    for arch_key, arch_data in archetypes.items():
        score = 0
        if arch_key in query:
            score += 10
        if query in arch_data.get("name", "").lower():
            score += 8
        for kw in arch_data.get("best_for", []):
            if kw.lower() in query or query in kw.lower():
                score += 5
        scores[arch_key] = score

    best_match = max(scores.items(), key=lambda x: x[1])
    arch_key = best_match[0] if best_match[1] > 0 else "saas-dashboard"
    arch = archetypes.get(arch_key, {})

    if json_mode:
        print(json.dumps({"selected_archetype": arch_key, "data": arch}, indent=2))
        return

    print("=================================================================")
    print(f"🎨 UI SELECTOR: SELECTED ARCHETYPE -> {arch.get('name', arch_key).upper()}")
    print("=================================================================")
    print(f"Key:          {arch_key}")
    print(f"Best For:     {', '.join(arch.get('best_for', []))}")
    print(f"Layout Spec:  {arch.get('layout')}")
    if "touch_bounds" in arch:
        print(f"Touch Bounds: {arch.get('touch_bounds')}")
    if "density" in arch:
        print(f"Data Density: {arch.get('density')}")

    print("\nTypography Pairing:")
    for role, font in arch.get("typography", {}).items():
        print(f"  • {role.capitalize().ljust(10)}: {font}")

    print("\nPrimary CSS Glass Tokens:")
    for token, val in arch.get("primary_tokens", {}).items():
        print(f"  --{token.ljust(12)}: {val};")

    print("\nReference Guidelines:")
    print(f"  • Anti-Slop Codex:     {SKILL_ROOT / 'references' / 'guidelines_anti_slop.md'}")
    print(f"  • Design System & CSS: {SKILL_ROOT / 'references' / 'guidelines_design_systems.md'}")
    print(f"  • Archetype Blueprint: {SKILL_ROOT / 'references' / 'guidelines_archetypes.md'}")
    print("=================================================================\n")

def main():
    parser = argparse.ArgumentParser(description="Dynamic UI Resource & Archetype Selector (Mini Auto-Skill for UI)")
    parser.add_argument("query", nargs="?", default="", help="Search query or project UI requirement")
    parser.add_argument("--project", type=str, default="", help="Project name (e.g. flh-one, flh-music, krpg, hi)")
    parser.add_argument("--json", action="store_true", help="Output JSON format")
    args = parser.parse_args()

    project_map = {
        "flh-one": "saas dashboard high density student analytics mobile",
        "flh-music": "mobile audio player touch workstation",
        "krpg": "game canvas hud webgl full bleed",
        "hi": "standalone interactive novel widget",
        "cult_game": "canvas game hud narrative",
    }

    effective_query = args.query
    if args.project:
        mapped = project_map.get(args.project.lower(), args.project)
        effective_query = f"{mapped} {args.query}".strip()
    if not effective_query:
        effective_query = "dashboard"

    query_ui(effective_query, args.json)

if __name__ == "__main__":
    main()
