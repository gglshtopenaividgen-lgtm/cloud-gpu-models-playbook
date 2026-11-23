#!/usr/bin/env python3
"""
Auto-Skill Dynamic Catalog Synchronizer
Scans all available skills in Central Brain (.agents/skills/), extracts YAML frontmatter,
identifies Universal vs. Project-Specific scopes, compiles the structured JSON registry,
generates references/catalog.md, and dynamically patches auto-skill/SKILL.md between sentinel markers.
Mirrors updates to D:\\agentic\\skills\\auto-skill.
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
AUTO_SKILL_DIR = SCRIPT_DIR.parent
BRAIN_SKILLS_DIR = AUTO_SKILL_DIR.parent
BRAIN_ROOT = BRAIN_SKILLS_DIR.parent.parent
brain_project_skills = BRAIN_ROOT / "project_skills"


def _to_host_path(raw: Any) -> Path:
    """Translate Windows drive paths (C:\\...) to WSL /mnt/<drive>/... when running on POSIX."""
    s = str(raw).strip().strip("\"'")
    if os.name == "posix":
        m = re.match(r"^([A-Za-z]):[/\\]*(.*)$", s)
        if m:
            drive, rest = m.group(1).lower(), m.group(2).replace("\\", "/")
            mnt_base = Path(f"/mnt/{drive}")
            if mnt_base.exists():
                return mnt_base / rest if rest else mnt_base
    return Path(s)


def _infer_host_home(brain_root: Path) -> Path:
    """Resolve Windows host home even inside WSL with custom HOME=.agy_pro2."""
    if os.name == "posix":
        parts = brain_root.resolve().parts
        if len(parts) >= 5 and parts[1] == "mnt" and parts[3].lower() == "users":
            cand = Path("/") / parts[1] / parts[2] / parts[3] / parts[4]
            if cand.is_dir():
                return cand
    return Path.home()


def safe_copytree(src: Path, dst: Path) -> None:
    """Recursively copy directory tree ignoring DrvFs chmod/copystat permission errors."""
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in files:
            src_file = Path(root) / f
            dst_file = target_dir / f
            try:
                shutil.copyfile(src_file, dst_file)
            except Exception:
                pass


HOST_HOME = _infer_host_home(BRAIN_ROOT)
USER_HOME = HOST_HOME
BUILTIN_SKILLS_DIR = HOST_HOME / ".gemini" / "antigravity" / "builtin" / "skills"
CONFIG_SKILLS_DIR = HOST_HOME / ".gemini" / "config" / "skills"
CONFIG_SKILLS_JSON = HOST_HOME / ".gemini" / "config" / "skills.json"

_vault_cand = _to_host_path(r"<AGENTIC_VAULT>\skills")
_vault_base = _to_host_path(r"<AGENTIC_VAULT>")
VAULT_SKILLS_DIR = _vault_cand if _vault_base.exists() else None

SENTINEL_START = "<!-- SKILLS-CATALOG:START -->"
SENTINEL_END = "<!-- SKILLS-CATALOG:END -->"


# Explicit Project-Specific Mappings (Restricted scope in project_skills)
PROJECT_SPECIFIC_MAP = {
    "srm-student-portal-engineer": "FLH-ONE (SRM Learn)",
    "srm-academia-portal-engineer": "FLH-ONE (SRM Academia)",
    "appwrite-cloud-architect": "flh-music (Appwrite Backend)",
    "audiophile-audio-engine": "flh-music (Web Audio DSP)",
    "living-npc-and-causality-architect": "krpg / AWAKEN1 (NPC Causality)",
    "narrative-world-architect": "krpg / AWAKEN1 (World Lore)",
    "asset-studio-pro": "krpg / AWAKEN1 (Asset Forge)",
    "poma-offline-engine": "PKREA (POMA Offline Disassembly)",
}

CATEGORY_MAP = {
    "Cognitive, Reasoning & Memory Architecture": [
        "hermes-agent-core",
        "deep-thinking",
        "auto-skill",
        "full-sync",
    ],
    "Code Quality, Audit & Verification Architecture": [
        "exhaustive-audit-and-repair",
        "rea",
    ],
    "Document, Presentation & OCR Engineering": [
        "document-forge",
    ],
    "Frontend, UI Design & Browser Automation": [
        "ui-design-engine",
        "browser-operator",
    ],
    "Compute, Internal Tooling & Frontier AI": [
        "external-resource",
        "internal-tools",
        "offload",
        "web-search-orchestrator",
    ],
    "Project-Specific Domain Skills": [
        "srm-student-portal-engineer",
        "srm-academia-portal-engineer",
        "appwrite-cloud-architect",
        "audiophile-audio-engine",
        "living-npc-and-causality-architect",
        "narrative-world-architect",
        "asset-studio-pro",
        "poma-offline-engine",
    ],
}


def parse_skill_md(skill_path: Path) -> Dict[str, Any]:
    content = skill_path.read_text(encoding="utf-8", errors="replace")
    name = skill_path.parent.name
    try:
        rel_path = str(skill_path.relative_to(BRAIN_ROOT)).replace("\\", "/")
    except Exception:
        rel_path = str(skill_path).replace("\\", "/")
    skill_info = {
        "name": name,
        "description": "No description provided.",
        "path": str(skill_path),
        "rel_path": rel_path,
        "category": "General Capabilities",

        "scope": "Universal",
        "target_project": "ALL",
    }

    # Detect Scope from Project-Specific Map
    if name in PROJECT_SPECIFIC_MAP:
        skill_info["scope"] = f"Project: {PROJECT_SPECIFIC_MAP[name]}"
        skill_info["target_project"] = PROJECT_SPECIFIC_MAP[name]

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            raw_yaml = parts[1]
            name_match = re.search(r"^name:\s*(.+)$", raw_yaml, re.MULTILINE)
            desc_match = re.search(r"^description:\s*(?:>-\s*)?(.+?)(?=\n[a-zA-Z_-]+:|\Z)", raw_yaml, re.DOTALL | re.MULTILINE)
            scope_match = re.search(r"^scope:\s*(.+)$", raw_yaml, re.MULTILINE)
            target_proj_match = re.search(r"^target_project:\s*(.+)$", raw_yaml, re.MULTILINE)

            if name_match:
                skill_info["name"] = name_match.group(1).strip().strip("\"'")
            if desc_match:
                clean_desc = re.sub(r"\s+", " ", desc_match.group(1)).strip().strip("\"'")
                skill_info["description"] = clean_desc
            if target_proj_match:
                tproj = target_proj_match.group(1).strip().strip("\"'")
                skill_info["target_project"] = tproj.upper()
                skill_info["scope"] = f"Project: {tproj.upper()}"
            elif scope_match and scope_match.group(1).strip().strip("\"'") == "project":
                skill_info["scope"] = f"Project: {PROJECT_SPECIFIC_MAP.get(name, 'SPECIFIC')}"

    # Categorize
    for cat, members in CATEGORY_MAP.items():
        if skill_info["name"] in members:
            skill_info["category"] = cat
            break

    return skill_info


def scan_skills() -> List[Dict[str, Any]]:
    skills = []
    universal_names = set()
    # 1. Universal Skills in Brain (.agents/skills)
    if BRAIN_SKILLS_DIR.exists():
        for item in sorted(BRAIN_SKILLS_DIR.iterdir()):
            if item.is_dir():
                skill_md = item / "SKILL.md"
                if skill_md.exists():
                    info = parse_skill_md(skill_md)
                    skills.append(info)
                    universal_names.update({item.name.casefold(), info["name"].casefold()})

    # 2. Project-Specific Skills in Brain (project_skills/<project>/<skill>)
    if brain_project_skills.exists():
        for proj_dir in sorted(brain_project_skills.iterdir()):
            if proj_dir.is_dir() and proj_dir.name != "_universal_candidates":
                for item in sorted(proj_dir.iterdir()):
                    if item.is_dir():
                        skill_md = item / "SKILL.md"
                        if skill_md.exists():
                            info = parse_skill_md(skill_md)
                            if {item.name.casefold(), info["name"].casefold()} & universal_names:
                                continue
                            info["scope"] = f"Project: {proj_dir.name}"
                            info["target_project"] = proj_dir.name
                            skills.append(info)
    return skills


def generate_catalog_markdown(skills: List[Dict[str, Any]]) -> str:
    universal = [s for s in skills if s.get("scope") == "Universal"]
    project = [s for s in skills if s.get("scope") != "Universal"]

    lines = [
        "### 🌐 Universal Multi-Project Skills (Active Globally in Central Brain)",
        "",
        "| # | Skill Name | Category | Primary Purpose & Trigger Scope |",
        "|:---|:---|:---|:---|",
    ]
    for idx, s in enumerate(universal, 1):
        desc = s["description"]
        if len(desc) > 130:
            desc = desc[:127] + "..."
        lines.append(f"| **{idx}** | **`{s['name']}`** | {s['category']} | {desc} |")

    if project:
        lines.extend([
            "",
            "### 🔒 Project-Specific Skills (Archived in `brain/project_skills/`)",
            "",
            "> *These skills are scoped strictly to individual projects and loaded within their local workspaces.*",
            "",
            "| # | Skill Name | Target Project | Category | Summary |",
            "|:---|:---|:---|:---|:---|",
        ])
        for idx, s in enumerate(project, 1):
            desc = s["description"]
            if len(desc) > 110:
                desc = desc[:107] + "..."
            lines.append(f"| **{idx}** | **`{s['name']}`** | `{s.get('target_project', 'SPECIFIC')}` | {s['category']} | {desc} |")

    return "\n".join(lines)


def sync_to_antigravity(skills: List[Dict[str, Any]]):
    # Only mirror to Antigravity global config if running in an Antigravity environment
    if not (USER_HOME / ".gemini").exists():
        print("  [i] Standalone/portable environment detected (skipping local ~/.gemini registration).")
        return

    try:
        BUILTIN_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_SKILLS_DIR.mkdir(parents=True, exist_ok=True)

        # 1. Mirror every universal brain skill into builtin and config
        for skill_info in skills:
            if skill_info.get("scope") != "Universal":
                continue
            skill_path = Path(skill_info["path"]).parent
            if skill_path.exists() and skill_path.is_dir():
                target_builtin = BUILTIN_SKILLS_DIR / skill_path.name
                safe_copytree(skill_path, target_builtin)
                target_config = CONFIG_SKILLS_DIR / skill_path.name
                safe_copytree(skill_path, target_config)

        # Also mirror to Path.home() / ".gemini" / "config" / "skills" if Path.home() != HOST_HOME
        if Path.home() != HOST_HOME:
            local_config_skills = Path.home() / ".gemini" / "config" / "skills"
            local_config_skills.mkdir(parents=True, exist_ok=True)
            for skill_info in skills:
                if skill_info.get("scope") != "Universal":
                    continue
                skill_path = Path(skill_info["path"]).parent
                if skill_path.exists() and skill_path.is_dir():
                    safe_copytree(skill_path, local_config_skills / skill_path.name)

        # 2. Gather all skills in BUILTIN_SKILLS_DIR for JSON manifests
        all_builtin_meta = []
        for s_dir in sorted(BUILTIN_SKILLS_DIR.iterdir()):
            if s_dir.is_dir() and (s_dir / "SKILL.md").exists():
                s_name = s_dir.name
                try:
                    txt = (s_dir / "SKILL.md").read_text(encoding="utf-8", errors="replace")
                    nm = re.search(r"^name:\s*([^\r\n]+)", txt, re.MULTILINE)
                    if nm:
                        s_name = nm.group(1).strip().strip("\"'")
                except Exception:
                    pass
                all_builtin_meta.append({
                    "name": s_name,
                    "path": f"{BUILTIN_SKILLS_DIR.as_posix()}/{s_dir.name}",
                    "enabled": True,
                    "scope": "global"
                })

        # 3. Write skills.json
        manifest = {
            "$schema": "https://antigravity.google.com/schemas/skills-v2.json",
            "entries": [
                {"path": BRAIN_SKILLS_DIR.as_posix()},
                {"path": CONFIG_SKILLS_DIR.as_posix()},
                {"path": BUILTIN_SKILLS_DIR.as_posix()}
            ],
            "skills": all_builtin_meta
        }
        CONFIG_SKILLS_JSON.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(f"  [+] Synced {len(skills)} skills to Antigravity slash discovery & updated {CONFIG_SKILLS_JSON}")
    except Exception as e:
        print(f"  [!] Notice: Could not sync to Antigravity global config: {e}")


def sync_catalog(mirror_antigravity: bool = False):
    print("[AutoSkill] Scanning skills across Central Brain...")
    skills = scan_skills()
    print(f"[AutoSkill] Found {len(skills)} verified skill(s).")

    # 1. Save JSON Registry
    registry_file = AUTO_SKILL_DIR / "references" / "skill_registry.json"
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    registry_file.write_text(json.dumps(skills, indent=2), encoding="utf-8")
    print(f"  [+] Saved registry: {registry_file}")

    # 2. Save Markdown Catalog Reference
    catalog_file = AUTO_SKILL_DIR / "references" / "catalog.md"
    catalog_md = f"# Complete Agent Skills Catalog (Total: {len(skills)})\n\n" + generate_catalog_markdown(skills)
    catalog_file.write_text(catalog_md, encoding="utf-8")
    print(f"  [+] Saved catalog: {catalog_file}")

    # 3. Notice: auto-skill/SKILL.md front door is kept clean and lightweight (<= 6 KB);
    # the 51-row table is preserved strictly in references/catalog.md and not embedded here.

    # 4. Mirror to D:\\agentic\\skills\\auto-skill
    if VAULT_SKILLS_DIR and VAULT_SKILLS_DIR.exists():
        vault_auto_skill = VAULT_SKILLS_DIR / "auto-skill"
        try:
            safe_copytree(AUTO_SKILL_DIR, vault_auto_skill)
            print(f"  [+] Mirrored auto-skill to {vault_auto_skill}")
        except Exception as e:
            print(f"  [!] Notice: Vault mirror skipped/partial: {e}")

    # 5. Mirror to Antigravity Builtin & Config Skills ONLY if explicit opt-in flag is provided
    if mirror_antigravity:
        sync_to_antigravity(skills)
    else:
        print("  [i] Skipping ~/.gemini copy (pass --mirror-antigravity to opt-in).")

    print(f"[AutoSkill] Dynamic catalog synchronization complete! ({len(skills)} skills active)")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Auto-Skill Dynamic Catalog Synchronizer")
    parser.add_argument("--mirror-antigravity", action="store_true", help="Opt-in flag to copy universal skills to ~/.gemini/antigravity directories")
    args = parser.parse_args()
    sync_catalog(mirror_antigravity=args.mirror_antigravity)
