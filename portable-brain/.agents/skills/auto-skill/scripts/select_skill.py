#!/usr/bin/env python3
"""
Auto-Skill Interactive Selector
Enables instant CLI querying and selection across all active skills.
Supports scope filtering (Universal vs. Project-Specific).
Usage:
    python select_skill.py                    # Interactive list of all skills with scope badges
    python select_skill.py <query>            # Search skills by keyword/domain
    python select_skill.py --universal        # Filter only Universal skills (safe for any project)
    python select_skill.py --project project-web  # Filter skills scoped to a specific project
"""

import argparse
import json
import sys
from pathlib import Path

REGISTRY_PATH = Path(__file__).parent.parent / "references" / "skill_registry.json"


def load_skills():
    if not REGISTRY_PATH.exists():
        from sync_catalog import sync_catalog
        sync_catalog()

    try:
        return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def search_skills(query: str = None, category: str = None, universal_only: bool = False, project: str = None):
    skills = load_skills()
    filtered = []

    q = query.lower() if query else None
    c = category.lower() if category else None
    p = project.lower() if project else None

    for s in skills:
        # Filter Universal Only
        if universal_only and s.get("scope") != "Universal":
            continue

        # Filter Project Specific
        if p and p not in s.get("scope", "").lower() and s.get("scope") != "Universal":
            continue

        matches_q = True
        matches_c = True

        if q:
            searchable = f"{s['name']} {s['category']} {s['scope']} {s['description']}".lower()
            tokens = q.split()
            matches_q = q in searchable or any(tok in searchable for tok in tokens)

        if c:
            matches_c = c in s["category"].lower()

        if matches_q and matches_c:
            filtered.append(s)

    return filtered


def main():
    parser = argparse.ArgumentParser(description="Auto-Skill Selector")
    parser.add_argument("query", nargs="?", default=None, help="Search keywords (e.g. 'pdf', 'react', 'audio')")
    parser.add_argument("--query", "-q", dest="query_flag", default=None, help="Search keywords flag")
    parser.add_argument("--cat", default=None, help="Filter by category")
    parser.add_argument("--universal", action="store_true", help="Show ONLY universal skills (safe for any project)")
    parser.add_argument("--project", default=None, help="Filter by target project (e.g. 'project-web')")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")

    args = parser.parse_args()
    effective_query = args.query_flag or args.query
    results = search_skills(effective_query, args.cat, args.universal, args.project)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    if not results:
        print(f"[AutoSkill] No skills found matching filters.")
        return

    print("==================================================")
    print(f"  Auto-Skill Selector — {len(results)} Available Skill(s)")
    if args.universal:
        print("  Filter: 🌐 UNIVERSAL SKILLS ONLY (Safe for all projects)")
    if args.project:
        print(f"  Filter: 🔒 PROJECT SCOPED TO: {args.project.upper()}")
    print("==================================================")

    current_cat = None
    for idx, s in enumerate(results, 1):
        if s["category"] != current_cat:
            current_cat = s["category"]
            print(f"\n📂 [{current_cat.upper()}]")

        is_universal = s.get("scope") == "Universal"
        badge = "🌐 UNIVERSAL" if is_universal else f"🔒 {s.get('scope').upper()}"

        brain_root = Path(__file__).resolve().parents[4]
        rel = s.get("rel_path")

        resolved_path = (brain_root / rel).resolve() if rel else Path(s["path"])
        display_path = str(resolved_path) if resolved_path.exists() else s.get("rel_path", s["path"])

        print(f"  {idx}. \033[1m{s['name']}\033[0m  [{badge}]")
        print(f"     Path: {display_path}")
        print(f"     Desc: {s['description'][:140]}...")
        if not is_universal:
            print(f"     ⚠️ CAUTION: Scoped specifically to {s.get('target_project')}. Do NOT use in other projects.")
        print()


    print("--------------------------------------------------")
    print("To activate a skill, load its SKILL.md into context or run its scripts.")
    print("==================================================")


if __name__ == "__main__":
    main()
