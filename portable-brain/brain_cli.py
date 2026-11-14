#!/usr/bin/env python3
"""
Mobile Brain Universal CLI
Cross-platform command center for Mobile Brain. Works on Windows, macOS, and Linux.
Usage:
    python brain_cli.py select [query] [--universal] [--project <proj>]
    python brain_cli.py sync
    python brain_cli.py info
"""

import sys
import subprocess
from pathlib import Path

BRAIN_ROOT = Path(__file__).resolve().parent
AUTO_SKILL_SCRIPT = BRAIN_ROOT / ".agents" / "skills" / "auto-skill" / "scripts" / "select_skill.py"
SYNC_SCRIPT = BRAIN_ROOT / ".agents" / "skills" / "auto-skill" / "scripts" / "sync_catalog.py"

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print("Mobile Brain CLI")
        print("Usage:")
        print("  python brain_cli.py select [query] [--universal] [--project <proj>]")
        print("  python brain_cli.py sync")
        print("  python brain_cli.py info")
        return

    cmd = sys.argv[1].lower()
    if cmd == "select":
        args = [sys.executable, str(AUTO_SKILL_SCRIPT)] + sys.argv[2:]
        subprocess.run(args)
    elif cmd == "sync":
        args = [sys.executable, str(SYNC_SCRIPT)]
        subprocess.run(args)
    elif cmd == "info":
        print("==================================================")
        print("  Mobile Brain: Path-Independent Knowledge Vault   ")
        print(f"  Root: {BRAIN_ROOT}")
        print("  Universal Skills: 12 powerhouses (.agents/skills/)")
        print("  Operating Rules: .agents/rules/")
        print("  Instructions: EXTERNAL_HARNESS_INSTRUCTIONS.md")
        print("==================================================")
    else:
        print(f"Unknown command: {cmd}. Available: select, sync, info")

if __name__ == "__main__":
    main()
