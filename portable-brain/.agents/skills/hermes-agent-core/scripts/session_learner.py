"""
Hermes Session Learner
Analyzes conversation transcripts (transcript.jsonl) to extract user preferences,
architectural decisions, resolved errors, and operational patterns.
Updates persistent memory and dialectical user models.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Any

try:
    from hermes_memory import store_memory, set_user_profile, store_digest
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).parent))
    from hermes_memory import store_memory, set_user_profile, store_digest


CORRECTION_PATTERNS = [
    r"(?:never|don'?t|do not)\s+(?:use|write|execute|touch|change|import)\s+([^\n.]+)",
    r"(?:always|must)\s+(?:use|follow|include|keep|maintain)\s+([^\n.]+)",
    r"(?:stop|stop doing)\s+([^\n.]+)",
    r"(?:instead of|rather than)\s+([^\n.]+)",
    r"(?:preference|prefer)\s+([^\n.]+)",
]


def parse_transcript(transcript_path: Path) -> List[Dict[str, Any]]:
    steps = []
    if not transcript_path.exists():
        print(f"[SessionLearner] Transcript not found: {transcript_path}")
        return steps

    with open(transcript_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                steps.append(data)
            except json.JSONDecodeError:
                continue
    return steps


def analyze_transcript(steps: List[Dict[str, Any]], project_name: str, session_id: str, db_path: Path = None):
    user_messages = []
    assistant_responses = []
    tool_calls = []
    system_errors = []

    for step in steps:
        source = step.get("source")
        step_type = step.get("type")
        content = step.get("content", "")

        if source == "USER" or step_type == "USER_INPUT":
            if content:
                user_messages.append(content)
        elif source == "SYSTEM" and "error" in content.lower():
            system_errors.append(content)
        elif source == "MODEL" and step_type == "PLANNER_RESPONSE":
            if content:
                assistant_responses.append(content)
            for tc in step.get("tool_calls", []):
                tool_calls.append(tc)

    print(f"[SessionLearner] Analyzed session {session_id}: {len(user_messages)} user prompt(s), {len(assistant_responses)} model response(s), {len(system_errors)} error(s).")

    # 1. Extract user preferences & corrections
    extracted_preferences = []
    for msg in user_messages:
        for pattern in CORRECTION_PATTERNS:
            matches = re.finditer(pattern, msg, re.IGNORECASE)
            for m in matches:
                clean_pref = m.group(0).strip()
                if len(clean_pref) > 10 and clean_pref not in extracted_preferences:
                    extracted_preferences.append(clean_pref)

    for pref in extracted_preferences:
        key = f"pref_{abs(hash(pref)) % 1000000}"
        set_user_profile(key, "learned_preference", pref, confidence=0.85, db_path=db_path)

    # 2. Extract system errors / failure modes
    for err in system_errors[:3]:
        clean_err = err[:300].replace("\n", " ")
        store_memory(
            project_name=project_name,
            category="failure_mode",
            title=f"Error encountered in {project_name}",
            content=clean_err,
            tags="runtime_error,debugging",
            db_path=db_path
        )

    # 3. Create session summary digest
    if user_messages:
        summary_title = user_messages[0][:150].replace("\n", " ")
        all_pref_text = "; ".join(extracted_preferences) if extracted_preferences else "None detected"
        store_digest(
            session_id=session_id,
            project_name=project_name,
            summary=f"Initial request: {summary_title}",
            decisions=f"Total turns: {len(steps)}, Tools called: {len(tool_calls)}",
            lessons=all_pref_text,
            db_path=db_path
        )

    print(f"[SessionLearner] Learning cycle complete. {len(extracted_preferences)} preference(s) recorded.")


def main():
    parser = argparse.ArgumentParser(description="Hermes Session Learner")
    parser.add_argument("--transcript", required=True, help="Path to transcript.jsonl")
    parser.add_argument("--project", default="general", help="Project name")
    parser.add_argument("--session-id", default="unknown", help="Conversation ID")
    parser.add_argument("--db", default=None, help="Custom SQLite DB path")

    args = parser.parse_args()
    db_path = Path(args.db) if args.db else None
    transcript_path = Path(args.transcript)

    steps = parse_transcript(transcript_path)
    if steps:
        analyze_transcript(steps, args.project, args.session_id, db_path)


if __name__ == "__main__":
    main()
