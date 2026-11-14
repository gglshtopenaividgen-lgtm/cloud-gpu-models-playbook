#!/usr/bin/env python3
"""
rea_runner.py - Universal Execution Bridge for REA (Reverse Engineer Anything)
Part of Central Brain 'rea' skill.

Usage:
    python rea_runner.py check
    python rea_runner.py analyze-js /path/to/app
    python rea_runner.py analyze-binary /path/to/binary
    python rea_runner.py inspect-apk /path/to/app.apk
    python rea_runner.py run <raw_command> [args...]
"""

import sys
import os
import json
import subprocess
import shutil
from pathlib import Path

def run_npx_rea(args: list[str], json_output: bool = True) -> tuple[int, str]:
    """Executes rea-agents via npx or local binary."""
    # Check if npm/npx is installed
    npx_cmd = shutil.which("npx") or shutil.which("npx.cmd")
    if not npx_cmd:
        return 1, "❌ Error: 'npx' is not found on PATH. Node.js is required to run REA."

    cmd = [npx_cmd, "-y", "rea-agents@latest"] + args
    if json_output and "--json" not in args and "setup" not in args:
        cmd.append("--json")

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        output = res.stdout.strip() or res.stderr.strip()
        return res.returncode, output
    except Exception as e:
        return 1, f"❌ Execution failed: {e}"

def check_environment():
    """Checks host environment and prerequisites for REA modalities."""
    print("==================================================")
    print("      REA ENVIRONMENT & PROVIDER DIAGNOSTICS      ")
    print("==================================================")

    # 1. Node.js
    node = shutil.which("node")
    if node:
        try:
            v = subprocess.run([node, "-v"], capture_output=True, text=True).stdout.strip()
            print(f"  ✅ Node.js:  Found ({v})")
        except Exception:
            print("  ⚠️ Node.js:  Found, but failed to query version")
    else:
        print("  ❌ Node.js:  Missing (Required for JS/Electron analysis & CLI)")

    # 2. Java / JDK (for JADX and Ghidra)
    java = shutil.which("java")
    if java:
        try:
            res = subprocess.run([java, "-version"], capture_output=True, text=True)
            v = (res.stderr or res.stdout).splitlines()[0]
            print(f"  ✅ Java:     Found ({v})")
        except Exception:
            print("  ⚠️ Java:     Found, but failed to query version")
    else:
        print("  ℹ️ Java:     Missing (Required for Android JADX & Ghidra)")

    # 3. ADB (for Android device inspection)
    adb = shutil.which("adb")
    if adb:
        print("  ✅ ADB:      Found")
    else:
        print("  ℹ️ ADB:      Not on PATH (Required for live Android debugging)")

    # 4. Ghidra
    ghidra_home = os.environ.get("GHIDRA_HOME") or os.environ.get("GHIDRA_INSTALL_DIR")
    if ghidra_home and Path(ghidra_home).exists():
        print(f"  ✅ Ghidra:   Found at {ghidra_home}")
    else:
        print("  ℹ️ Ghidra:   Not configured via GHIDRA_HOME (Optional for deep native RE)")

    print("==================================================")
    print("Ready to run REA commands via 'npx -y rea-agents@latest'.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python rea_runner.py [check|analyze-js|analyze-binary|inspect-apk|run] [args...]")
        sys.exit(0)

    action = sys.argv[1].lower()
    extra_args = sys.argv[2:]

    if action == "check":
        check_environment()
    elif action == "analyze-js":
        if not extra_args:
            print("Error: Specify path to JS/Electron directory or ASAR.")
            sys.exit(1)
        code, out = run_npx_rea(["analyze-javascript-application", extra_args[0]])
        print(out)
        sys.exit(code)
    elif action == "analyze-binary":
        if not extra_args:
            print("Error: Specify path to binary file.")
            sys.exit(1)
        code, out = run_npx_rea(["analyze-native-binary", extra_args[0]])
        print(out)
        sys.exit(code)
    elif action == "inspect-apk":
        if not extra_args:
            print("Error: Specify path to APK file.")
            sys.exit(1)
        code, out = run_npx_rea(["inspect-android-package", extra_args[0]])
        print(out)
        sys.exit(code)
    elif action == "run":
        code, out = run_npx_rea(extra_args)
        print(out)
        sys.exit(code)
    else:
        # Default: pass arguments directly to REA
        code, out = run_npx_rea([action] + extra_args)
        print(out)
        sys.exit(code)

if __name__ == "__main__":
    main()
