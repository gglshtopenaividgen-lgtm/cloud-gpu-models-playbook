#!/usr/bin/env python3
"""
gemini_deep_research.py - Autonomous Gemini Deep Research via Argon Bridge & Shared Fleet.

> ⛔ EXECUTION-FIRST MANDATE:
> This is an executable CLI engine. NEVER call read_file or view_file on this script.
> Always execute directly via run_command:
> python C:\\Users\\Flh\\Desktop\\brain\\.agents\\skills\\web-search-orchestrator\\scripts\\gemini_deep_research.py "<topic>" -o temp_read/report.md

Features:
1. Dynamic Shared Fleet Negotiation: Automatically picks the optimal IDLE Google One AI Premium profile
   with the lowest usage, or honors --profile if specified.
2. Lease Arbitration & Heartbeat: Registers active lease in bridge_profile_locks.json with 20s renewal
   heartbeats so other agents see the active research task in --status without collisions.
3. High-Effort Technical Prompt Synthesis: Generates structured, anti-slop, agent-digestible research mandates.
4. Auto-Confirms Plan & Long-Polls: Drives gemini.google.com via trusted CDP bridge, confirms research plan,
   and harvests formatted Markdown with deduplicated citations.
5. Observability & Safe Cleanup: Reports live 5-hour quota and cleans temporary sidebar chat unless --keep-chat is given.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Resolve bridge directory
BRIDGE_PATH = Path(__file__).resolve().parent.parent.parent / "browser-operator" / "argon_bridge"
if str(BRIDGE_PATH) not in sys.path:
    sys.path.insert(0, str(BRIDGE_PATH))

try:
    from gemini_brain_driver import GeminiBrainDriver
    from profile_lock_manager import (
        acquire_profile_lease,
        renew_profile_lease,
        release_profile_lease,
        get_live_profile_status,
        pick_optimal_idle_profile,
    )
except ImportError as e:
    GeminiBrainDriver = None
    acquire_profile_lease = None
    renew_profile_lease = None
    release_profile_lease = None
    get_live_profile_status = None
    pick_optimal_idle_profile = None


def generate_prompt(topic: str, context: str, key_questions: List[str]) -> str:
    """Synthesizes a high-density, anti-slop prompt mandate for Deep Research."""
    questions_formatted = "\n".join([f"- {q.strip()}" for q in key_questions if q.strip()])

    prompt = f"""# GEMINI DEEP RESEARCH MANDATE — HIGH-EFFORT TECHNICAL INTELLIGENCE DOSSIER

> **DIRECTIVE FOR GEMINI**: You are conducting an exhaustive, multi-pass deep research mission on behalf of an autonomous AI software architecture system. The resulting intelligence will be ingested directly into persistent agent memory.

---

## 1. PRIMARY RESEARCH OBJECTIVE
**Topic**: {topic}

**Context & Background**:
{context}

---

## 2. SPECIFIC TECHNICAL INQUIRIES & CRITICAL VECTORS
{questions_formatted if questions_formatted else "- Exhaustively investigate the architectural blueprints, official APIs, production configurations, and real-world failure patterns for this topic."}

---

## 3. STRICT COMPILATION & OUTPUT INVARIANTS (MANDATORY)

1. **MAXIMUM EFFORT & RECURSIVE SEARCH DEPTH**:
   - Execute the deepest possible search chain: examine official documentation, GitHub repositories, RFCs, bug trackers, release notes, and real-world production incident postmortems.
   - Do NOT stop at high-level summaries or landing pages. Retrieve exact version numbers, configuration flags, edge cases, error codes, and workarounds.

2. **ABSOLUTE ZERO MARKETING & CONVERSATIONAL SLOP**:
   - Eliminate all introductory filler (e.g. "In this comprehensive guide...", "Certainly! Let's explore...").
   - Eliminate all concluding pleasantries and generic motivational sign-offs.
   - Avoid generic high-level advice; every claim must be backed by technical specifics or code examples.

3. **STRUCTURED AGENT-DIGESTIBLE FORMATTING**:
   - **Markdown Tables First**: Compile comparative metrics, pricing tiers, latency benchmarks, and feature parity matrices into clear Markdown tables.
   - **Production Code Blocks**: Provide complete, copy-pasteable configuration files (JSON, YAML, Python, TypeScript, Shell) with verified options.
   - **Failure Modes & Anti-Patterns**: Explicitly detail what breaks, known race conditions, deprecated APIs, and common traps.
   - **Executive Architecture Recommendations**: Provide a 1-2 paragraph conclusion stating the exact recommended technical path.

---
*Ready for immediate execution in Gemini Deep Research.*
"""
    return prompt.strip()


def run_autonomous_deep_research(
    topic: str,
    context: str = "General multi-agent system engineering context.",
    questions: Optional[List[str]] = None,
    profile: Optional[str] = None,
    output_path: Optional[str] = None,
    auto_clean: bool = True,
    timeout_sec: int = 900,
    model: Optional[str] = None,
    thinking: Optional[str] = None,
    mode: str = "chat",
) -> Dict[str, Any]:
    """Drives Deep Research ('4 Neon' High in Chat mode) or Task research ('4 Neon' High in Task mode) via Argon Bridge & shared fleet."""
    if not GeminiBrainDriver or not acquire_profile_lease:
        return {"ok": False, "error": f"Argon Bridge components not available at {BRIDGE_PATH}."}

    mode_norm = (mode or "chat").strip().lower()
    use_deep_research = (mode_norm == "chat")
    target_model = model or "4 Neon"
    target_thinking = (thinking or "High").title()

    agent_id = f"deep_research_{int(time.time() * 1000)}"
    task_desc = f"{'Task Research' if mode_norm == 'task' else 'Deep Research'}: {topic[:35]}"

    # 1. Acquire surface-scoped profile lease on gemini_web_neon bucket
    target_profile, lease_err = acquire_profile_lease(
        agent_id=agent_id,
        preferred_profile=profile,
        task=task_desc,
        deep_research=use_deep_research,
        lease_seconds=timeout_sec,
        surface="gemini_web",
        bucket="gemini_web_neon",
    )

    if not target_profile:
        return {
            "ok": False,
            "error": f"Failed to acquire profile lease: {lease_err}",
        }

    # 2. Start heartbeat thread to renew lease every 20s
    stop_heartbeat = threading.Event()

    def _heartbeat_worker():
        while not stop_heartbeat.wait(20.0):
            try:
                renew_profile_lease(target_profile, agent_id, extend_seconds=120.0)
            except Exception:
                pass

    heartbeat_thread = threading.Thread(target=_heartbeat_worker, daemon=True)
    heartbeat_thread.start()

    prompt = generate_prompt(topic, context, questions or [])
    sid = None

    try:
        print(
            f"[GeminiDeepResearch] Profile acquired: '{target_profile}' | Mode={mode_norm} | "
            f"Model={target_model} ({target_thinking or 'N/A'}) | Task='{task_desc}'"
        )
        print(f"[GeminiDeepResearch] Timeout: {timeout_sec}s | Auto-clean: {auto_clean}")

        driver = GeminiBrainDriver(default_profile=target_profile)
        sid = driver.create_session(new_chat=True, profile_dir=target_profile)

        res = driver.ask(
            session_id=sid,
            prompt=prompt,
            deep_research=use_deep_research,
            model=target_model,
            thinking=target_thinking,
            mode=mode_norm,
            check_usage=True,
            timeout_sec=timeout_sec,
        )

        if res.get("ok"):
            response_text = res.get("response", "")
            chat_id = res.get("chat_id")
            rich_data = res.get("rich", {})
            usage_data = res.get("usage", {})

            if output_path:
                p = Path(output_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(response_text, encoding="utf-8")
                print(f"[GeminiDeepResearch] Saved research report to: {p}")

            if auto_clean:
                print(f"[GeminiDeepResearch] Auto-cleaning sidebar chat {chat_id or sid}...")
                try:
                    driver.delete_session(sid, profile=target_profile)
                except Exception as ce:
                    print(f"[GeminiDeepResearch] Warning auto-cleaning chat: {ce}", file=sys.stderr)

            return {
                "ok": True,
                "topic": topic,
                "session_id": sid,
                "profile": target_profile,
                "chat_id": chat_id,
                "mode": res.get("mode", mode_norm),
                "model": res.get("model", target_model),
                "thinking": res.get("thinking", target_thinking),
                "char_count": len(response_text),
                "response": response_text,
                "rich": rich_data,
                "usage": usage_data,
                "duration_seconds": res.get("duration_seconds", 0.0),
            }
        else:
            if auto_clean and sid:
                try:
                    driver.delete_session(sid, profile=target_profile)
                except Exception:
                    pass
            return {"ok": False, "error": res.get("error", "Deep Research failed"), "profile": target_profile}

    finally:
        # Stop heartbeat and release lease
        stop_heartbeat.set()
        try:
            release_profile_lease(target_profile, agent_id)
            print(f"[GeminiDeepResearch] Released profile lease on '{target_profile}'.")
        except Exception as re:
            print(f"[GeminiDeepResearch] Warning releasing lease: {re}", file=sys.stderr)


def print_fleet_status():
    """Prints live observability status table for all 6 Google One AI Premium profiles."""
    if not get_live_profile_status:
        print("Argon Bridge profile lock manager not available.", file=sys.stderr)
        return

    status = get_live_profile_status()
    print("\n" + "=" * 96)
    print(" LIVE GOOGLE ONE AI PREMIUM FLEET: SHARED RESEARCH OBSERVABILITY & QUOTA")
    print("=" * 96)
    print(f"{'PROFILE':<12} {'ACCOUNT':<14} {'STATUS':<10} {'5H USAGE':<12} {'WEEKLY':<12} {'HOLDER / AGENT':<22} {'TASK':<16}")
    print("-" * 96)
    for prof, info in status.items():
        p_name = info.get("name", prof)
        if len(p_name) > 13:
            p_name = p_name[:11] + ".."
        st = info.get("status", "UNKNOWN")
        cur_u = f"{info.get('current_usage_percent')}%" if info.get("current_usage_percent") is not None else "-"
        wk_u = f"{info.get('weekly_usage_percent')}%" if info.get("weekly_usage_percent") is not None else "-"
        holder = info.get("holder") or "-"
        if len(holder) > 21:
            holder = holder[:19] + ".."
        task = info.get("task") or "-"
        if len(task) > 15:
            task = task[:13] + ".."
        print(f"{prof:<12} {p_name:<14} {st:<10} {cur_u:<12} {wk_u:<12} {holder:<22} {task:<16}")
    print("=" * 96 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Gemini Deep Research via Argon Bridge & Shared Fleet")
    parser.add_argument("topic_pos", nargs="?", default=None, help="Main research topic (positional)")
    parser.add_argument("--topic", dest="topic_flag", default=None, help="Main research topic (flag)")
    parser.add_argument("--context", default="General multi-agent system engineering context.", help="Background context")
    parser.add_argument("--questions", "-q", nargs="+", default=[], help="Specific questions or technical vectors")
    parser.add_argument("--profile", default=None, help="Target specific Chrome profile (defaults to Waterfall Drain Tier 1 Alt Pool)")
    parser.add_argument("--model", default="4 Neon", help="Target Gemini Web model (default: '4 Neon' High; 4 Hydrogen/4 Carbon are blocked)")
    parser.add_argument("--thinking", default="High", choices=["Low", "Medium", "High"], help="Thinking level (default: High)")
    parser.add_argument("--mode", default="chat", choices=["chat", "task"], help="Gemini segmented mode ('chat' = Deep Research, 'task' = parallel subagent Task research)")
    parser.add_argument("--task", action="store_true", help="Shortcut for --mode task (parallel cloud subagent research on 4 Neon High)")
    parser.add_argument("--status", action="store_true", help="Display live profile fleet visibility, active agent leases, and usage telemetry")
    parser.add_argument("--output", "-o", default=None, help="Save markdown report to file path in temp_read/")
    parser.add_argument("--keep-chat", action="store_true", help="Keep the chat in the sidebar (do not auto-delete)")
    parser.add_argument("--timeout", type=int, default=900, help="Deep research timeout in seconds (default: 900s)")
    parser.add_argument("--prompt-only", action="store_true", help="Only generate and print the prompt text without executing")
    parser.add_argument("--json", action="store_true", help="Output raw JSON response")

    args = parser.parse_args()

    if args.status:
        print_fleet_status()
        return

    topic = args.topic_pos or args.topic_flag
    if not topic:
        parser.error("A topic is required (e.g. python gemini_deep_research.py 'Post-Quantum Cryptography') or use --status")

    if args.prompt_only:
        print(generate_prompt(topic, args.context, args.questions))
        return

    effective_mode = "task" if getattr(args, "task", False) else args.mode

    # Execute autonomously by default
    result = run_autonomous_deep_research(
        topic=topic,
        context=args.context,
        questions=args.questions,
        profile=args.profile,
        output_path=args.output,
        auto_clean=not args.keep_chat,
        timeout_sec=args.timeout,
        model=args.model,
        thinking=args.thinking,
        mode=effective_mode,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    elif result.get("ok"):
        print("\n" + "=" * 80)
        res_model = (result.get("model") or args.model or "4 Hydrogen").upper()
        res_mode = (result.get("mode") or effective_mode).upper()
        print(f" GEMINI {res_model} [{res_mode}] RESEARCH DOSSIER (Profile: {result.get('profile')} | Duration: {result.get('duration_seconds')}s)")
        print("=" * 80)
        print(result.get("response"))
        print("=" * 80)
        if result.get("usage"):
            u = result.get("usage")
            print(f"Live Quota: {u.get('current_usage_percent')}% used ({u.get('current_reset')}) | Weekly: {u.get('weekly_usage_percent')}% used\n")
    else:
        print(f"Error during Deep Research: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
