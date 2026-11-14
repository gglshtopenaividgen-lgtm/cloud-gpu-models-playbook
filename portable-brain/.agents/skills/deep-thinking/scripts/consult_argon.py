#!/usr/bin/env python3
r"""consult_argon.py - Gemini 4 Argon Cognitive Engine for deep-thinking.

========================================================================================
⛔ EXECUTION-FIRST & ZERO-WRAPPER MANDATE FOR AGENTS & SUBAGENTS:
- 🛑 NEVER create intermediate Python wrapper scripts (e.g. run_argon_query.py)!
- 🛑 NEVER waste turns inspecting CLI args (--help) or over-thinking how to invoke!
- 🛑 DO NOT read this script using read_file or view_file!
- 🛑 DO NOT fall back to GCP Vertex AI (custom_tools/api_router/argon.py) which burns paid credits!
- EXECUTE DIRECTLY on Turn 1 via run_command:
    1. Normal Prompt (Ideas, Architecture, Planning with High Thinking):
       python <BRAIN_ROOT>/.agents/skills/deep-thinking/scripts/consult_argon.py "<prompt>" -o temp_read/ans.md
    2. Long / Multi-line Prompt (zero shell escaping issues):
       python <BRAIN_ROOT>/.agents/skills/deep-thinking/scripts/consult_argon.py --prompt-file temp_read/prompt.md -o temp_read/ans.md
    3. Deep Research (Exhaustive 20+ sources):
       python <BRAIN_ROOT>/.agents/skills/deep-thinking/scripts/consult_argon.py "<topic>" --deep-research -o temp_read/research.md
========================================================================================

Shared Compute Fleet & Observability:
- All 6 Google One AI Premium profiles are available to any agent across any task or workspace.
- Agents can inspect live fleet status (--status) to see which profiles are IDLE vs BUSY and their usage %.
- Agents can explicitly select a profile (--profile "Profile X") or let the tool auto-pick the idle profile with lowest usage.
- Supports programmatic file uploading (codebases, logs, context) and automatic sidebar cleanup.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Link to argon_bridge driver in browser-operator
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from argon_context_packer import build_selective_context_bundle, record_session_turn
except ImportError as e:
    print(f"[ConsultArgon] Warning importing argon_context_packer: {e}", file=sys.stderr)
    build_selective_context_bundle = None
    record_session_turn = None

BRIDGE_DIR = Path(__file__).resolve().parents[2] / "browser-operator" / "argon_bridge"
sys.path.insert(0, str(BRIDGE_DIR))

try:
    from gemini_brain_driver import GeminiBrainDriver
    from profile_lock_manager import (
        acquire_profile_lease,
        release_profile_lease,
        get_live_profile_status,
        pick_optimal_idle_profile,
    )
except ImportError as e:
    print(f"[ConsultArgon] Error importing from {BRIDGE_DIR}: {e}", file=sys.stderr)
    GeminiBrainDriver = None
    acquire_profile_lease = None
    release_profile_lease = None
    get_live_profile_status = None
    pick_optimal_idle_profile = None



def consult_argon_api(
    prompt: str,
    files: Optional[List[str]] = None,
    thinking: str = "High",
    output_path: Optional[str] = None,
    allow_paid_api_fallback: bool = False,
) -> Dict[str, Any]:
    """Tier-2 Route: Calls Gemini 4 Argon via Google Cloud Vertex AI API (argon.py)."""
    import subprocess
    api_script = Path("<WORKSPACE_ROOT>/api_router/argon.py")
    if not api_script.exists():
        return {"ok": False, "error": f"Vertex AI Argon script not found at {api_script}"}

    cmd = [sys.executable, str(api_script), "-q", prompt, "--thinking", thinking.lower(), "--json"]
    for fp in (files or []):
        cmd.extend(["-f", fp])

    print(f"[ConsultArgon-API] ⚡ Routing to Gemini 4 Argon via Vertex AI API (Thinking: {thinking}, Files: {len(files or [])})...")
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    dur = round(time.time() - t0, 1)
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip()}

    try:
        data = json.loads(proc.stdout.strip())
        resp_text = data.get("response") or data.get("text") or proc.stdout.strip()
    except Exception:
        resp_text = proc.stdout.strip()

    if output_path:
        out_p = Path(output_path)
        if not out_p.is_absolute():
            out_p = Path("<BRAIN_ROOT>") / out_p
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(resp_text, encoding="utf-8")
        print(f"[ConsultArgon-API] Saved response to {out_p.as_posix()}")

    return {
        "ok": True,
        "profile": "Vertex-AI-API (<GCP_PROJECT_ID>)",
        "thinking": thinking,
        "response": resp_text,
        "duration_seconds": dur,
        "via_api": True,
    }


def consult_argon_web(prompt: str,
    files: Optional[List[str]] = None,
    thinking: str = "High",
    deep_research: bool = False,
    auto_clean: bool = True,  # Keep conversation intact by default; clean only when explicitly requested
    profile: Optional[str] = None,
    session_id: Optional[str] = None,
    new_chat: bool = True,
    own_tab: bool = False,
    output_path: Optional[str] = None,
    allow_paid_api_fallback: bool = False,
) -> Dict[str, Any]:
    """Consults Gemini 4 Argon via the live browser bridge on gemini.google.com."""
    driver = None
    sid = None
    target_prof = profile
    lease_acquired = False
    agent_id = session_id or f"agent_{int(time.time()*1000)}"

    if not GeminiBrainDriver:
        if not allow_paid_api_fallback:
            return {"ok": False, "error": "GeminiBrainDriver unavailable and paid API fallback is blocked."}
        print("[ConsultArgon] All browser profiles offline or exhausted. Failing over to Vertex AI Argon API...", file=sys.stderr)
        return consult_argon_api(
            prompt=prompt,
            files=files,
            thinking=thinking,
            output_path=output_path,
        )

    if acquire_profile_lease:
        target_prof, err = acquire_profile_lease(
            agent_id=agent_id,
            preferred_profile=profile,
            task=prompt[:40] if prompt else "cognition",
            session_id=session_id,
            deep_research=deep_research,
        )
        if err or not target_prof:
            if not allow_paid_api_fallback:
                return {"ok": False, "error": f"Failed to acquire profile lease: {err}. Paid API fallback is blocked."}
            print("[ConsultArgon] All browser profiles offline or exhausted. Failing over to Vertex AI Argon API...", file=sys.stderr)
            return consult_argon_api(
                prompt=prompt,
                files=files,
                thinking=thinking,
                output_path=output_path,
            )
        lease_acquired = True

    try:
        driver = GeminiBrainDriver(default_profile=target_prof)
        sid = driver.create_session(
            session_id=session_id,
            new_chat=new_chat,
            own_tab=own_tab,
            profile_dir=target_prof
        )

        timeout_sec = 1500.0 if deep_research else 300.0
        print(f"[ConsultArgon] Consulting Gemini 4 Argon (Profile: {target_prof or 'optimal'}, Thinking: {thinking}, Files: {len(files or [])}, Timeout: {timeout_sec}s)...")
        res = driver.ask(
            session_id=sid,
            prompt=prompt,
            files=files,
            deep_research=deep_research,
            thinking=thinking,
            timeout_sec=timeout_sec,
            check_usage=True,
        )

        # Automatic failover if primary profile is rate-limited
        if not res.get("ok") and res.get("rate_limited") and acquire_profile_lease:
            print(f"[ConsultArgon] ⚠️ Profile '{target_prof}' rate-limited. Auto-negotiating next optimal idle profile in fleet...", file=sys.stderr)
            if release_profile_lease:
                release_profile_lease(target_prof, agent_id=agent_id)
                lease_acquired = False
            next_prof, err = acquire_profile_lease(
                agent_id=agent_id,
                preferred_profile=None,
                task=f"failover: {prompt[:30]}",
                session_id=None,
                deep_research=deep_research,
            )
            if not err and next_prof:
                target_prof = next_prof
                lease_acquired = True
                print(f"[ConsultArgon] 🔄 Re-routing query to failover profile '{target_prof}'...", file=sys.stderr)
                driver = GeminiBrainDriver(default_profile=target_prof)
                sid = driver.create_session(new_chat=True, own_tab=own_tab, profile_dir=target_prof)
                res = driver.ask(
                    session_id=sid,
                    prompt=prompt,
                    files=files,
                    deep_research=deep_research,
                    thinking=thinking,
                    timeout_sec=timeout_sec,
                    check_usage=True,
                )

        # Failover to Vertex AI Argon API if browser attempt did not succeed
        if not res.get("ok"):
            if not allow_paid_api_fallback:
                err_m = res.get("error") or "Browser query failed"
                print(f"[ConsultArgon] ❌ Browser attempt failed: {err_m}", file=sys.stderr)
                print("[ConsultArgon] ⛔ Paid Vertex AI API fallback is BLOCKED. (Pass --allow-paid-api-fallback to override).", file=sys.stderr)
                return {"ok": False, "error": f"Browser attempt failed: {err_m}. Paid API fallback blocked."}
            print("[ConsultArgon] All browser profiles offline or exhausted. Failing over to Vertex AI Argon API...", file=sys.stderr)
            return consult_argon_api(
                prompt=prompt,
                files=files,
                thinking=thinking,
                output_path=output_path,
            )

        response_text = res.get("response", "")
        chat_id = res.get("chat_id")
        rich_data = res.get("rich", {})
        usage_data = res.get("usage", {})

        # Optionally save response to output file
        if output_path:
            out_p = Path(output_path)
            if not out_p.is_absolute():
                out_p = Path("<BRAIN_ROOT>") / out_p
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(response_text, encoding="utf-8")
            print(f"[ConsultArgon] Saved response to {out_p.as_posix()}")

        return {
            "ok": True,
            "session_id": sid,
            "profile": res.get("profile"),
            "chat_id": chat_id,
            "thinking": thinking,
            "deep_research": deep_research,
            "response": response_text,
            "rich": rich_data,
            "usage": usage_data,
            "duration_seconds": res.get("duration_seconds", 0.0),
        }
    finally:
        if auto_clean and driver and sid:
            try:
                print(f"[ConsultArgon] 🧹 Purging temporary automated chat from sidebar on '{target_prof or 'active'}'...")
                del_res = driver.delete_session(sid, profile=target_prof)
                print(f"[ConsultArgon] Sidebar purge result: {del_res}")
            except Exception as e:
                print(f"[ConsultArgon] Warning during sidebar purge: {e}", file=sys.stderr)
        if lease_acquired and release_profile_lease and target_prof:
            release_profile_lease(target_prof, agent_id=agent_id)


def main():
    parser = argparse.ArgumentParser(description="Consult Gemini 4 Argon (High Thinking & Deep Research) for Deep Thinking")
    parser.add_argument("prompt", nargs="?", default=None, help="The question, hypothesis, or architectural task")
    parser.add_argument("-q", "--question", dest="question_flag", help="Alternative flag for prompt")
    parser.add_argument("--profile", default=None, help="Explicitly target a specific Chrome profile (e.g. 'Profile 13', 'Profile 14'); if omitted, auto-selects optimal idle profile")
    parser.add_argument("--status", action="store_true", help="Display live profile fleet visibility, active agent leases, and usage telemetry")
    parser.add_argument("-f", "--file", "--upload", nargs="+", dest="files", help="File paths to attach into the prompt box")
    parser.add_argument("--pack", "-p", nargs="*", default=[], help="Smart code/file slicer specs (e.g. file.py, file.py:10-80, file.py#ClassName) to bundle into selective context")
    parser.add_argument("--auto-context", dest="auto_context", action="store_true", default=True, help="Automatically pack selective context (Hermes RRF memory, top ideas/mistakes/constraints, file_map, and AST code slices) into temp_read/argon_context_bundle.md and attach via -f (DEFAULT: True for thinking mode)")
    parser.add_argument("--no-auto-context", dest="auto_context", action="store_false", help="Disable automatic selective context bundling")
    parser.add_argument("--project", default=None, help="Explicit project scope for selective context packing (auto-detected if omitted)")
    parser.add_argument("--thinking", default="High", choices=["Low", "Medium", "High"], help="Thinking level budget")
    parser.add_argument("--deep-research", action="store_true", help="Enable Gemini Deep Research mode")
    parser.add_argument("--usage", action="store_true", help="Audit and display live usage quota on profile without sending prompt")
    parser.add_argument("--clean", "--delete", dest="clean", action="store_true", default=True, help="Delete the chat from sidebar after turn completes (DEFAULT: True)")
    parser.add_argument("--no-clean", "--keep", dest="clean", action="store_false", help="Keep the chat alive in sidebar (use for multi-turn debugging)")
    parser.add_argument("--allow-paid-api-fallback", action="store_true", default=False, help="Explicitly allow falling back to paid Vertex AI API if all browser profiles fail (DEFAULT: False)")
    parser.add_argument("--api", action="store_true", help="Tier-2 Route: Call Gemini 4 Argon via Google Cloud Vertex AI API (use when explicitly requested or when all 6 browser accounts hit quota)")
    parser.add_argument("--new-tab", action="store_true", help="Open a dedicated new tab instead of reusing existing Gemini tab")
    parser.add_argument("--continue", dest="continue_session", action="store_true", help="Continue in existing chat session without starting a new chat")
    parser.add_argument("--session-id", default=None, help="Specific session ID to track or continue multi-turn threads")
    parser.add_argument("-o", "--output", help="Save markdown response to file path in temp_read/")
    parser.add_argument("--prompt-file", "--file-prompt", default=None, help="Path to text or markdown file containing prompt (ideal for multi-line prompts, eliminates shell escaping)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")

    args = parser.parse_args()

    if args.status:
        if get_live_profile_status:
            stat = get_live_profile_status()
            print("\n" + "=" * 96)
            print(" LIVE GOOGLE ONE AI PREMIUM FLEET: PROFILE VISIBILITY & USAGE TELEMETRY")
            print("=" * 96)
            print(f"{'PROFILE':<12} {'ACCOUNT':<14} {'STATUS':<10} {'5H USAGE':<12} {'WEEKLY':<12} {'HOLDER / AGENT':<22} {'TASK':<16}")
            print("-" * 96)
            for p, d in stat.items():
                u_curr = f"{d.get('current_usage_percent')}% used" if d.get('current_usage_percent') is not None else "-"
                u_wk = f"{d.get('weekly_usage_percent')}% used" if d.get('weekly_usage_percent') is not None else "-"
                holder = str(d.get('holder') or "-")
                task = str(d.get('task') or "-")[:15]
                acct = str(d.get('name') or p)[:13]
                print(f"{p:<12} {acct:<14} {d.get('status'):<10} {u_curr:<12} {u_wk:<12} {holder:<22} {task:<16}")
            print("=" * 96 + "\n")
        sys.exit(0)

    if args.usage:
        driver = GeminiBrainDriver(default_profile=args.profile)
        prof = args.profile or "Profile 14"
        info = driver.get_usage_limit(profile=prof)
        print(f"\n" + "=" * 60)
        print(f" LIVE GEMINI QUOTA AUDIT: {prof}")
        print("=" * 60)
        print(f"Plan:                  {info.get('plan')}")
        print(f"Current Usage:         {info.get('current_usage_percent')}% used")
        print(f"Current Window Resets: {info.get('current_reset')}")
        print(f"Weekly Limit:          {info.get('weekly_usage_percent')}% used")
        print(f"Weekly Resets:         {info.get('weekly_reset')}")
        print(f"Should Rotate:         {info.get('should_rotate')}")
        print("=" * 60 + "\n")
        sys.exit(0)

    prompt_text = args.prompt or args.question_flag

    # Read prompt from file via --prompt-file, positional @file, or piped stdin
    if getattr(args, "prompt_file", None):
        p_path = Path(args.prompt_file)
        if p_path.exists():
            prompt_text = p_path.read_text(encoding="utf-8")
        else:
            print(f"Error: Prompt file '{args.prompt_file}' not found.", file=sys.stderr)
            sys.exit(1)
    elif prompt_text and prompt_text.startswith("@") and len(prompt_text) > 1 and Path(prompt_text[1:]).exists():
        prompt_text = Path(prompt_text[1:]).read_text(encoding="utf-8")
    elif not prompt_text and not sys.stdin.isatty():
        try:
            stdin_content = sys.stdin.read().strip()
            if stdin_content:
                prompt_text = stdin_content
        except Exception:
            pass

    if not prompt_text:
        parser.print_help()
        sys.exit(1)

    # Automatic Selective Context-Packing Pipeline (Zero Full-File Dumping)
    attached_files = list(args.files or [])
    context_telemetry = None
    should_pack = (args.auto_context and not args.deep_research) or bool(args.pack)
    if should_pack and build_selective_context_bundle:
        try:
            bundle_path, context_telemetry = build_selective_context_bundle(
                prompt=prompt_text,
                pack_specs=args.pack,
                explicit_project=args.project,
                session_id=args.session_id,
            )
            if bundle_path and bundle_path not in attached_files:
                attached_files.insert(0, bundle_path)
            print(
                f"[ConsultArgon] 📦 Selective Context Packed -> {bundle_path} "
                f"(Project: {context_telemetry.get('active_project')}, "
                f"Hermes RRF: {context_telemetry.get('hermes_memories_count')}, "
                f"Ideas: {context_telemetry.get('ideas_selected')}, "
                f"Mistakes: {context_telemetry.get('mistakes_selected')}, "
                f"Code Slices: {context_telemetry.get('code_slices_count')}, "
                f"Noise Reduction: {context_telemetry.get('noise_reduction_pct')}%)"
            )
        except Exception as e:
            print(f"[ConsultArgon] Note on selective context packing: {e}", file=sys.stderr)
    args.files = attached_files if attached_files else None

    # Keep session alive on intermediate multi-turn steps unless --clean was explicitly forced
    should_clean = False if args.continue_session and "--clean" not in sys.argv and "--delete" not in sys.argv else args.clean

    if getattr(args, "api", False):
        result = consult_argon_api(
            prompt=prompt_text,
            files=args.files,
            thinking=args.thinking,
            output_path=args.output,
            allow_paid_api_fallback=args.allow_paid_api_fallback,
        )
    else:
        result = consult_argon_web(
            prompt=prompt_text,
            files=args.files,
            thinking=args.thinking,
            deep_research=args.deep_research,
            auto_clean=should_clean,
            profile=args.profile,
            session_id=args.session_id,
            new_chat=not args.continue_session,
            own_tab=args.new_tab,
            output_path=args.output,
            allow_paid_api_fallback=args.allow_paid_api_fallback,
        )
        # Automatic Tier-2 API Failover if all browser accounts fail or rate-limit (BLOCKED unless explicit)
        if not result.get("ok") and args.allow_paid_api_fallback:
            print("[ConsultArgon] All browser profiles offline or exhausted. Failing over to Vertex AI Argon API...", file=sys.stderr)
            result = consult_argon_api(
                prompt=prompt_text,
                files=args.files,
                thinking=args.thinking,
                output_path=args.output,
            )
        elif not result.get("ok"):
            print(f"\n[ConsultArgon] ❌ Execution Failed: {result.get('error')}", file=sys.stderr)
            print("[ConsultArgon] ⛔ Paid Vertex AI API fallback was blocked to protect cloud budget.", file=sys.stderr)
            sys.exit(2)

    if result.get("ok") and args.session_id and record_session_turn:
        try:
            ledger_file = record_session_turn(
                session_id=args.session_id,
                prompt=prompt_text,
                response=result.get("response", ""),
                profile=str(result.get("profile") or ""),
                chat_url=str(result.get("chat_id") or ""),
            )
            result["session_ledger"] = str(ledger_file)
        except Exception:
            pass
    if context_telemetry:
        result["context_telemetry"] = context_telemetry

    if args.json:
        print(json.dumps(result, indent=2))
    elif result.get("ok"):
        print("\n" + "=" * 80)
        print(f" GEMINI 4 ARGON REASONING CORE (Profile: {result.get('profile')} | Thinking: {result.get('thinking')} | Duration: {result.get('duration_seconds')}s)")
        print("=" * 80)
        print(result.get("response"))
        print("=" * 80)
        if result.get("usage"):
            u = result.get("usage")
            print(f"Live Quota: {u.get('current_usage_percent')}% used ({u.get('current_reset')}) | Weekly: {u.get('weekly_usage_percent')}% used\n")
    else:
        print(f"Error consulting Argon: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
