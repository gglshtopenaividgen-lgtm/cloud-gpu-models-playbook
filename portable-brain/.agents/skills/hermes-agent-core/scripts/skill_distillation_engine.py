#!/usr/bin/env python3
"""
Transcript-to-Skill Distillation Engine
Conforms to the agentskills.io specification using Python 3.14 standard library.
Extracts verified successful commands and file mutations, parameterizes paths,
and outputs a validated SKILL.md.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ToolExecution:
    tool_name: str
    arguments: dict[str, Any]
    output: str
    exit_code: int = 0


@dataclass
class Trajectory:
    task_goal: str
    successful_executions: list[ToolExecution] = field(default_factory=list)
    file_modifications: list[str] = field(default_factory=list)


class SkillSynthesisEngine:
    def __init__(self, workspace_root: str = ""):
        self.workspace_root = workspace_root

    def parse_transcript(self, transcript_path: Path) -> Trajectory:
        trajectory = Trajectory(task_goal="Automated Procedure")
        if not transcript_path.exists():
            return trajectory

        with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue

                if record.get("source") in ("USER", "USER_EXPLICIT") or record.get("type") == "USER_INPUT":
                    if not trajectory.task_goal or trajectory.task_goal == "Automated Procedure":
                        trajectory.task_goal = record.get("content", "")[:120]
                    continue

                for tc in record.get("tool_calls", []):
                    tool_name = tc.get("name") or tc.get("tool_name", "")
                    args = tc.get("arguments") or tc.get("args", {})
                    output = record.get("content", "")
                    exit_code = 0 if "error" not in output.lower() else 1

                    if exit_code != 0:
                        continue

                    if tool_name in ("write_to_file", "replace_file_content"):
                        path = args.get("TargetFile") or args.get("path", "")
                        if path and path not in trajectory.file_modifications:
                            trajectory.file_modifications.append(path)

                    trajectory.successful_executions.append(
                        ToolExecution(tool_name, args, output, exit_code)
                    )
        return trajectory

    def parameterize_text(self, text: str) -> str:
        text = re.sub(r"[A-Za-z]:\\[\w+\\]+[\w+]", "<PROJECT_DIR>", text)
        text = re.sub(r"/(?:home|Users)/[\w+]+", "<USER_HOME>", text)
        return text

    def distill_runbook(self, trajectory: Trajectory, skill_slug: str) -> str:
        slug = re.sub(r"[^a-z0-9-]", "-", skill_slug.lower()).strip("-")
        slug = re.sub(r"-+", "-", slug)[:64]

        procedural_steps: list[str] = []
        step_idx = 1
        for exec_node in trajectory.successful_executions:
            if exec_node.tool_name in ("run_command", "bash", "powershell"):
                cmd = exec_node.arguments.get("CommandLine") or exec_node.arguments.get("command", "")
                if cmd:
                    clean_cmd = self.parameterize_text(cmd.strip())
                    procedural_steps.append(
                        f"{step_idx}. **Execute Command**:\n"
                        f"   ```powershell\n"
                        f"   {clean_cmd}\n"
                        f"   ```"
                    )
                    step_idx += 1
            elif exec_node.tool_name in ("write_to_file", "replace_file_content"):
                target = self.parameterize_text(
                    exec_node.arguments.get("TargetFile") or exec_node.arguments.get("path", "file")
                )
                procedural_steps.append(
                    f"{step_idx}. **Apply Updates to `{target}`**:\n"
                    f"   Ensure changes preserve existing exports, pass type checks (`npx tsc --noEmit`), and adhere to project invariants."
                )
                step_idx += 1

        steps_rendered = "\n".join(procedural_steps) if procedural_steps else "1. Step instructions."
        files_rendered = "\n".join([f"- `{self.parameterize_text(p)}`" for p in trajectory.file_modifications])

        skill_content = f"""---
name: {slug}
description: Automated runbook distilled from verified trajectory for {trajectory.task_goal[:120]}. Use when executing this workflow.
compatibility: Windows 11 PowerShell, Python 3.14+, Next.js 15
metadata:
  synthesized: "true"
---

# {slug.replace('-', ' ').title()}

## When to Use
Execute this runbook when handling tasks matching: `{trajectory.task_goal}`.

## Preconditions & Invariants
- Working directory must be clean or backed up via git stash.
- Dependencies must be installed and verified before running scripts.
- Never invoke broken subagents (`DeepCoder`/`DeepInvestigator`).

## Step-by-Step Procedure
{steps_rendered}

## Modified Target Artifacts
{files_rendered if files_rendered else "None recorded."}

## Verification & Confirmation
1. Verify that all process exit codes return `0`.
2. Run project-specific linter and test suites to confirm no regressions.
"""
        return skill_content


class SkillValidator:
    NAME_REGEX = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

    @classmethod
    def validate(cls, skill_dir: Path) -> tuple[bool, list[str]]:
        errors: list[str] = []
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.is_file():
            return False, ["Missing required SKILL.md file."]

        content = skill_file.read_text(encoding="utf-8")

        if not content.startswith("---"):
            return False, ["File must start with YAML frontmatter markers (---)."]

        parts = content.split("---", 2)
        if len(parts) < 3:
            return False, ["Malformed frontmatter: missing closing --- delimiter."]

        raw_yaml = parts[1]

        name_match = re.search(r"^name:\s*(.+)$", raw_yaml, re.MULTILINE)
        desc_match = re.search(r"^description:\s*(.+)$", raw_yaml, re.MULTILINE)

        if not name_match:
            errors.append("Missing required 'name' field in frontmatter.")
        else:
            name = name_match.group(1).strip()
            if not (1 <= len(name) <= 64):
                errors.append("Field 'name' must be between 1 and 64 characters.")
            if not cls.NAME_REGEX.match(name):
                errors.append(f"Field 'name' ('{name}') violates formatting constraints.")
            if skill_dir.name != name:
                errors.append(f"Parent directory name ('{skill_dir.name}') must match 'name' field ('{name}').")

        if not desc_match:
            errors.append("Missing required 'description' field in frontmatter.")
        else:
            desc = desc_match.group(1).strip()
            if not (1 <= len(desc) <= 1024):
                errors.append("Field 'description' must be between 1 and 1024 characters.")

        # Static Security Scan
        body = parts[2]
        suspicious_patterns = [
            (r"rmdir\s+/s\s+/q\s+C:\\", "Destructive recursive deletion detected."),
            (r"(?i)bearer\s+[a-z0-9_\-\.]{20,}", "Potential hardcoded bearer token detected."),
            (r"(?i)curl\s+-[^\n]*https?://", "Potential unauthorized exfiltration curl detected.")
        ]
        for pattern, msg in suspicious_patterns:
            if re.search(pattern, body):
                errors.append(f"Security Alert: {msg}")

        return (len(errors) == 0, errors)


def save_skill_and_sync(skill_dir: Path, skill_content: str) -> bool:
    """Save synthesized skill, validate, and trigger Auto-Skill dynamic catalog sync."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(skill_content, encoding="utf-8")

    is_valid, errors = SkillValidator.validate(skill_dir)
    if not is_valid:
        print(f"❌ Skill validation failed: {errors}")
        return False

    print(f"✅ Skill saved and verified at: {skill_file}")

    # Trigger Auto-Skill dynamic catalog synchronization
    try:
        import subprocess
        import sys
        sync_script = skill_dir.parents[0] / "auto-skill" / "scripts" / "sync_catalog.py"
        if not sync_script.exists():
            sync_script = Path(r"./.agents\skills\auto-skill\scripts\sync_catalog.py")
        if sync_script.exists():
            subprocess.run([sys.executable, str(sync_script)], check=False)
            print("🔄 Auto-Skill catalog updated automatically.")
    except Exception as e:
        print(f"⚠️ Auto-Skill sync warning: {e}")

    return True

