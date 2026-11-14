#!/usr/bin/env python3
"""validate_internal_tool.py - Linter & validator for skills, MCP servers, and Chrome extensions."""

import argparse
import json
import os
import sys
from pathlib import Path


def validate_skill(path: Path) -> bool:
    print(f"[Validate] Checking Skill: {path.resolve()}...")
    skill_md = path / "SKILL.md" if path.is_dir() else path
    if not skill_md.exists() or skill_md.name != "SKILL.md":
        print(f"❌ Error: SKILL.md not found at {skill_md}")
        return False

    content = skill_md.read_text(encoding="utf-8")
    lines = content.splitlines()

    # 1. Frontmatter check
    if not (lines[0].strip() == "---" and "---" in lines[1:]):
        print("❌ Error: Missing YAML frontmatter ('---')")
        return False

    # 2. Check for nested SKILL.md in subdirectories (bloat hazard)
    if path.is_dir():
        nested_skills = list(path.glob("**/SKILL.md"))
        if len(nested_skills) > 1:
            print(f"❌ Critical Error: Found {len(nested_skills)} nested SKILL.md files! This will cause Antigravity discovery bloat:")
            for ns in nested_skills:
                print(f"   - {ns.resolve()}")
            return False

    # 3. Token count check (<150 lines recommended)
    if len(lines) > 200:
        print(f"⚠️ Warning: Root SKILL.md is {len(lines)} lines long. Consider moving domain logic to playbooks/*.md to prevent system prompt bloat.")

    print(f"✅ Skill {path.name} is valid and compliant!")
    return True


def validate_chrome_extension(path: Path) -> bool:
    print(f"[Validate] Checking Chrome Extension: {path.resolve()}...")
    manifest_p = path / "manifest.json" if path.is_dir() else path
    if not manifest_p.exists():
        print(f"❌ Error: manifest.json not found at {manifest_p}")
        return False

    try:
        data = json.loads(manifest_p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Error: manifest.json is invalid JSON: {e}")
        return False

    if data.get("manifest_version") != 3:
        print(f"❌ Error: manifest_version must be 3 (found {data.get('manifest_version')})")
        return False

    if "background" in data and not data["background"].get("service_worker"):
        print("❌ Error: MV3 requires background.service_worker")
        return False

    print(f"✅ Chrome Extension {data.get('name', path.name)} is valid MV3!")
    return True


def main():
    parser = argparse.ArgumentParser(description="Validate skills, extensions, and internal tools")
    parser.add_argument("target", help="Path to directory or file to validate")
    args = parser.parse_args()

    target_p = Path(args.target)
    if not target_p.exists():
        print(f"Error: Target path does not exist: {target_p}")
        sys.exit(1)

    if target_p.is_dir() and (target_p / "manifest.json").exists():
        ok = validate_chrome_extension(target_p)
    elif target_p.is_dir() and (target_p / "SKILL.md").exists():
        ok = validate_skill(target_p)
    elif target_p.name == "SKILL.md":
        ok = validate_skill(target_p.parent)
    elif target_p.name == "manifest.json":
        ok = validate_chrome_extension(target_p.parent)
    else:
        print(f"Unknown tool type for: {target_p}")
        sys.exit(1)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
