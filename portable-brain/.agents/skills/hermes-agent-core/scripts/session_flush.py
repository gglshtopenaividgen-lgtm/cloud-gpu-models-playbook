#!/usr/bin/env python3
"""
Hermes Pre-Compaction Session Memory Flush Protocol
Part of hermes-agent-core universal skill.
Executes the two-phase compaction protocol inspired by Nous Research Hermes Agent:
1. Flushes critical architectural decisions to brain/ideas.md
2. Flushes regressions / anti-patterns to brain/mistakes.md
3. Persists episodic memories & session digests to ~/.gemini/antigravity/hermes_global_memory.db
"""

import argparse
import datetime
import os
import sqlite3
import sys
from pathlib import Path

BRAIN_DIR = Path(r"./")
IDEAS_FILE = BRAIN_DIR / "ideas.md"
MISTAKES_FILE = BRAIN_DIR / "mistakes.md"
DEFAULT_DB = Path.home() / ".gemini" / "antigravity" / "hermes_global_memory.db"

def append_to_ideas(decision: str, rationale: str = "", project: str = "universal"):
    """Appends an architectural decision to ideas.md under chronological header."""
    if not IDEAS_FILE.exists():
        print(f"[!] Warning: ideas.md not found at {IDEAS_FILE}")
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    entry = f"\n### Decision [{today}] ({project.upper()}): {decision}\n"
    if rationale:
        entry += f"- **Rationale & Impact**: {rationale}\n"
    entry += f"- **Committed At**: {datetime.datetime.now().strftime('%H:%M:%S IST')}\n"

    with open(IDEAS_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"[+] Logged decision to: {IDEAS_FILE}")

def append_to_mistakes(mistake: str, root_cause: str = "", prevention: str = "", project: str = "universal"):
    """Appends a bug or anti-pattern to mistakes.md."""
    if not MISTAKES_FILE.exists():
        print(f"[!] Warning: mistakes.md not found at {MISTAKES_FILE}")
        return

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    entry = f"\n### Mistake / Anti-Pattern [{today}] ({project.upper()}): {mistake}\n"
    if root_cause:
        entry += f"- **Root Cause**: {root_cause}\n"
    if prevention:
        entry += f"- **Prevention & Invariant**: {prevention}\n"

    with open(MISTAKES_FILE, "a", encoding="utf-8") as f:
        f.write(entry)
    print(f"[+] Logged anti-pattern to: {MISTAKES_FILE}")

def store_db_records(
    project: str,
    title: str,
    summary: str,
    decisions: str = "",
    lessons: str = "",
    tags: str = "",
    session_id: str = "active"
):
    """Stores episodic memory and session digest in SQLite."""
    if not DEFAULT_DB.exists():
        print(f"[!] Warning: hermes DB not found at {DEFAULT_DB}")
        return

    conn = sqlite3.connect(DEFAULT_DB)
    with conn:
        # Episodic memory
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO episodic_memories (project_name, category, title, content, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project, "milestone", title, summary, tags)
        )
        mem_id = cur.lastrowid
        print(f"[+] Inserted Episodic Memory #{mem_id}")

        # Session digest
        cur.execute(
            """
            INSERT INTO session_digests (session_id, project_name, summary, key_decisions, lessons_learned)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, project, summary, decisions, lessons)
        )
        dig_id = cur.lastrowid
        print(f"[+] Inserted Session Digest #{dig_id}")
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Hermes Pre-Compaction Memory Flush Protocol")
    parser.add_argument("--project", default="universal", help="Target project name (e.g. brain, flh-one, hi, krpg)")
    parser.add_argument("--title", required=True, help="Title of current milestone or task")
    parser.add_argument("--summary", required=True, help="Summary of changes and accomplishments")
    parser.add_argument("--decision", default="", help="Architectural decision to append to ideas.md")
    parser.add_argument("--rationale", default="", help="Rationale for decision")
    parser.add_argument("--mistake", default="", help="Mistake / bug identified to append to mistakes.md")
    parser.add_argument("--root-cause", default="", help="Root cause of mistake")
    parser.add_argument("--prevention", default="", help="Prevention rule for mistake")
    parser.add_argument("--tags", default="", help="Comma-separated search tags")
    parser.add_argument("--session-id", default="active-session", help="Conversation ID")

    args = parser.parse_args()

    print(f"\n[Hermes Session Flush] Commencing Pre-Compaction Memory Flush for [{args.project}]...")
    
    # 1. ideas.md
    if args.decision:
        append_to_ideas(args.decision, args.rationale, args.project)

    # 2. mistakes.md
    if args.mistake:
        append_to_mistakes(args.mistake, args.root_cause, args.prevention, args.project)

    # 3. SQLite persistent memory
    store_db_records(
        project=args.project,
        title=args.title,
        summary=args.summary,
        decisions=args.decision,
        lessons=args.mistake,
        tags=args.tags,
        session_id=args.session_id
    )

    print("[Hermes Session Flush] Memory flush complete. State successfully persisted to disk.\n")

if __name__ == "__main__":
    main()
