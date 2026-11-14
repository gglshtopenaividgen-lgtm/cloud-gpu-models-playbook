"""
Hermes Skill Synthesizer
Automates the creation of standardized Antigravity/Hermes skills (SKILL.md).
Captures repeatable procedures, cloud workflows, and debugging runbooks into reusable modular knowledge.
"""

import argparse
import re
from pathlib import Path

try:
    from hermes_memory import register_skill
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).parent))
    from hermes_memory import register_skill


SKILL_TEMPLATE = """---
name: {name}
description: >-
  {description}
---

# {title}

{overview}

---

## 1. When to Activate This Skill

Activate this skill whenever:
{triggers_list}

---

## 2. Core Execution Protocol

{instructions}

---

## 3. Strict Invariants & Boundaries

{invariants}

---

## 4. Verification & Testing Checklist

- [ ] Execute procedure according to protocol steps.
- [ ] Confirm zero runtime errors or unhandled exceptions.
- [ ] Record any newly encountered edge cases to `context/mistakes.md`.
"""


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def synthesize_skill(name: str, description: str, instructions: str, triggers: list, invariants: str, output_dir: Path, db_path: Path = None) -> Path:
    skill_slug = slugify(name)
    skill_dir = output_dir / skill_slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"

    triggers_formatted = "\n".join(f"- {t.strip()}" for t in triggers if t.strip())
    if not triggers_formatted:
        triggers_formatted = "- Working on tasks matching this skill's scope."

    title = name.replace("-", " ").title()
    overview = f"This skill provides standardized execution procedures and domain guardrails for **{title}**."

    content = SKILL_TEMPLATE.format(
        name=skill_slug,
        description=description.strip(),
        title=title,
        overview=overview,
        triggers_list=triggers_formatted,
        instructions=instructions.strip(),
        invariants=invariants.strip() if invariants else "- Preserve all existing functionality and avoid breaking changes."
    )

    with open(skill_file, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"[SkillSynthesizer] Generated skill '{skill_slug}' at: {skill_file}")

    # Register in Hermes memory
    register_skill(
        skill_name=skill_slug,
        description=description,
        path=str(skill_file),
        triggers="; ".join(triggers),
        db_path=db_path
    )

    return skill_file


def main():
    parser = argparse.ArgumentParser(description="Hermes Skill Synthesizer")
    parser.add_argument("--name", required=True, help="Skill name slug (e.g. cloudflare-r2-sync)")
    parser.add_argument("--description", required=True, help="Short description for progressive disclosure")
    parser.add_argument("--instructions", required=True, help="Step-by-step procedure/runbook")
    parser.add_argument("--triggers", default="", help="Comma-separated trigger phrases")
    parser.add_argument("--invariants", default="", help="Safety rules and invariants")
    parser.add_argument("--out-dir", default=".agents/skills", help="Directory where skill will be placed")
    parser.add_argument("--db", default=None, help="Custom SQLite DB path")

    args = parser.parse_args()
    triggers = [t.strip() for t in args.triggers.split(",") if t.strip()]
    output_dir = Path(args.out_dir)
    db_path = Path(args.db) if args.db else None

    synthesize_skill(
        name=args.name,
        description=args.description,
        instructions=args.instructions,
        triggers=triggers,
        invariants=args.invariants,
        output_dir=output_dir,
        db_path=db_path
    )


if __name__ == "__main__":
    main()
