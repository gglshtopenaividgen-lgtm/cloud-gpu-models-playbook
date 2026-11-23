#!/usr/bin/env python3
"""
Portable Brain CLI - Universal Cross-Platform Discovery Engine
Works on Windows, macOS, and Linux.
Usage:
    python brain_cli.py select [query] [--universal]
    python brain_cli.py info
"""

import sys
import subprocess
from pathlib import Path

BRAIN_ROOT = Path(__file__).resolve().parent
AUTO_SKILL_SCRIPT = BRAIN_ROOT / ".agents" / "skills" / "auto-skill" / "scripts" / "select_skill.py"

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ["-h", "--help"]:
        print("Portable Brain CLI")
        print("Usage:")
        print("  python brain_cli.py select [query] [--universal]")
        print("  python brain_cli.py info")
        return

    cmd = sys.argv[1].lower()
    if cmd == "select":
        if AUTO_SKILL_SCRIPT.exists():
            args = [sys.executable, str(AUTO_SKILL_SCRIPT)] + sys.argv[2:]
            subprocess.run(args)
        else:
            print(f"[!] Auto-skill selector not found at {AUTO_SKILL_SCRIPT}")
    elif cmd == "info":
        print("==================================================")
        print("  Portable Brain: Universal Autonomous Skill Vault")
        print(f"  Root: {BRAIN_ROOT}")
        print("  Universal Skills: 13 powerhouses (.agents/skills/)")
        print("  Operating Rules: .agents/rules/")
        print("  Instructions: EXTERNAL_HARNESS_INSTRUCTIONS.md")
        print("==================================================")
    else:
        print(f"Unknown command: {cmd}. Available: select, info")

if __name__ == "__main__":
    main()
