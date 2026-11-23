"""
Agent Experiential Memory Engine (SQLite + FTS5)
Conforms to the Nous Research Hermes / agentskills.io standard.
Pure Python 3.14 Standard Library (sqlite3, dataclasses, json, re, pathlib, time).
"""

from __future__ import annotations

import dataclasses
import json
import logging
import pathlib
import re
import sqlite3
import time
from typing import Literal

logger = logging.getLogger("MemoryEngine")

# Strict Character Budget Limits
USER_MD_CHAR_LIMIT = 1375
MEMORY_MD_CHAR_LIMIT = 2200
TOTAL_INJECTION_BUDGET = 3500


@dataclasses.dataclass(slots=True, frozen=True)
class MemoryRecord:
    id: str
    scope: Literal["global", "project"]
    project_id: str | None
    category: Literal["preference", "invariant", "procedural", "architectural"]
    title: str
    content: str
    evidence: str
    confidence: float
    created_at: int
    updated_at: int


@dataclasses.dataclass(slots=True, frozen=True)
class RetrievalResult:
    id: str
    title: str
    content: str
    category: str
    scope: str
    score: float


class MemoryEngine:
    """High-performance local memory engine backed by SQLite FTS5 and Markdown mirrors."""

    def __init__(self, db_path: pathlib.Path, project_id: str | None = None) -> None:
        self.db_path = db_path
        self.project_id = project_id
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.isolation_level = None
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA synchronous = NORMAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._init_database()

    def _init_database(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                scope TEXT NOT NULL CHECK(scope IN ('global', 'project')),
                project_id TEXT,
                category TEXT NOT NULL CHECK(category IN ('preference', 'invariant', 'procedural', 'architectural')),
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                evidence TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                access_count INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_mem_lookup 
            ON memories(scope, project_id, category);

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                title,
                content,
                evidence,
                content='memories',
                content_rowid='rowid',
                tokenize='unicode61 remove_diacritics 2'
            );

            CREATE TRIGGER IF NOT EXISTS trg_mem_ins AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, title, content, evidence)
                VALUES (new.rowid, new.title, new.content, new.evidence);
            END;

            CREATE TRIGGER IF NOT EXISTS trg_mem_del AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, title, content, evidence)
                VALUES('delete', old.rowid, old.title, old.content, old.evidence);
            END;

            CREATE TRIGGER IF NOT EXISTS trg_mem_upd AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, title, content, evidence)
                VALUES('delete', old.rowid, old.title, old.content, old.evidence);
                INSERT INTO memories_fts(rowid, title, content, evidence)
                VALUES (new.rowid, new.title, new.content, new.evidence);
            END;
        """)
        self._conn.commit()

    def upsert_memory(self, record: MemoryRecord) -> None:
        sql = """
            INSERT INTO memories (
                id, scope, project_id, category, title, content, evidence, confidence, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                evidence = excluded.evidence,
                confidence = excluded.confidence,
                updated_at = excluded.updated_at;
        """
        with self._conn:
            self._conn.execute(sql, (
                record.id, record.scope, record.project_id, record.category,
                record.title, record.content, record.evidence, record.confidence,
                record.created_at, record.updated_at
            ))

    def search(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        clean_query = re.sub(r"[^\w\s]", " ", query).strip()
        if not clean_query:
            return []

        tokens = clean_query.split()
        fts_query = " OR ".join(f'"{t}"*' for t in tokens)

        sql = """
            SELECT 
                m.id, m.title, m.content, m.category, m.scope,
                bm25(memories_fts, 10.0, 5.0, 1.0) AS rank
            FROM memories_fts
            JOIN memories m ON memories_fts.rowid = m.rowid
            WHERE memories_fts MATCH ?
              AND (m.scope = 'global' OR m.project_id = ?)
            ORDER BY rank ASC
            LIMIT ?;
        """
        cursor = self._conn.execute(sql, (fts_query, self.project_id, limit))
        results = [
            RetrievalResult(
                id=row[0],
                title=row[1],
                content=row[2],
                category=row[3],
                scope=row[4],
                score=row[5]
            )
            for row in cursor.fetchall()
        ]

        if results:
            ids = [r.id for r in results]
            placeholders = ",".join("?" * len(ids))
            with self._conn:
                self._conn.execute(
                    f"UPDATE memories SET access_count = access_count + 1 WHERE id IN ({placeholders})",
                    ids
                )

        return results

    def mine_transcript_stream(self, transcript_jsonl_path: pathlib.Path) -> list[MemoryRecord]:
        if not transcript_jsonl_path.exists():
            return []

        candidates: list[MemoryRecord] = []
        now = int(time.time())

        correction_regex = re.compile(
            r"(?i)\b(?:don'?t|never|always|prefer|stop using|must use|make sure|avoid)\b\s+([^.!?\n]+)"
        )

        with transcript_jsonl_path.open("r", encoding="utf-8", errors="replace") as f:
            for line_idx, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    turn = json.loads(line)
                except Exception:
                    continue

                role = turn.get("source") or turn.get("role")
                text = turn.get("content", "")

                if role in ("USER", "user", "USER_EXPLICIT"):
                    match = correction_regex.search(text)
                    if match:
                        matched_rule = match.group(0).strip()
                        rec_id = f"mem_mine_{now}_{line_idx}"
                        record = MemoryRecord(
                            id=rec_id,
                            scope="project" if self.project_id else "global",
                            project_id=self.project_id,
                            category="invariant" if any(k in matched_rule.lower() for k in ("never", "always", "avoid")) else "preference",
                            title=f"Rule: {matched_rule[:45]}...",
                            content=matched_rule,
                            evidence=text[:250],
                            confidence=0.95,
                            created_at=now,
                            updated_at=now
                        )
                        self.upsert_memory(record)
                        candidates.append(record)

        return candidates

    def generate_markdown_mirrors(
        self, 
        user_md_path: pathlib.Path, 
        memory_md_path: pathlib.Path,
        user_char_limit: int = USER_MD_CHAR_LIMIT,
        memory_char_limit: int = MEMORY_MD_CHAR_LIMIT
    ) -> tuple[int, int]:
        user_md_path.parent.mkdir(parents=True, exist_ok=True)
        memory_md_path.parent.mkdir(parents=True, exist_ok=True)

        cursor = self._conn.execute("""
            SELECT category, title, content FROM memories 
            WHERE scope = 'global' AND category = 'preference'
            ORDER BY access_count DESC, updated_at DESC;
        """)
        user_lines = ["# USER PROFILE (Dialectical State)\n\n"]
        for cat, title, content in cursor.fetchall():
            line = f"- **{title}**: {content}\n"
            if sum(len(x) for x in user_lines) + len(line) <= user_char_limit:
                user_lines.append(line)
        user_content = "".join(user_lines).strip()
        user_md_path.write_text(user_content, encoding="utf-8")

        cursor = self._conn.execute("""
            SELECT category, title, content FROM memories 
            WHERE scope = 'project' OR (scope = 'global' AND category != 'preference')
            ORDER BY access_count DESC, updated_at DESC;
        """)
        mem_lines = ["# PROJECT & SYSTEM MEMORY\n\n"]
        for cat, title, content in cursor.fetchall():
            line = f"- [{cat.upper()}] **{title}**: {content}\n"
            if sum(len(x) for x in mem_lines) + len(line) <= memory_char_limit:
                mem_lines.append(line)
        memory_content = "".join(mem_lines).strip()
        memory_md_path.write_text(memory_content, encoding="utf-8")

        return len(user_content), len(memory_content)

    def assemble_system_prompt_injection(self, current_user_query: str) -> str:
        dynamic_hits = self.search(current_user_query, limit=2)
        dyn_lines = ["\n## RELEVANT PAST EXPERIENCES (Retrieved)"]
        for hit in dynamic_hits:
            dyn_lines.append(f"- **{hit.title}**: {hit.content}")
        dyn_block = "\n".join(dyn_lines) if len(dyn_lines) > 1 else ""

        total_budget = TOTAL_INJECTION_BUDGET
        dyn_block = dyn_block[:500]
        remaining = total_budget - len(dyn_block)

        user_budget = min(1200, remaining // 2)
        mem_budget = remaining - user_budget

        user_records = self._conn.execute("""
            SELECT title, content FROM memories WHERE scope = 'global'
            ORDER BY access_count DESC LIMIT 6;
        """).fetchall()
        u_lines = ["## USER PREFERENCES"]
        for t, c in user_records:
            line = f"- {t}: {c}"
            if sum(len(x) for x in u_lines) + len(line) < user_budget:
                u_lines.append(line)
        user_block = "\n".join(u_lines)

        proj_records = self._conn.execute("""
            SELECT category, title, content FROM memories 
            WHERE project_id = ? OR scope = 'project'
            ORDER BY access_count DESC LIMIT 8;
        """, (self.project_id,)).fetchall()
        p_lines = ["## PROJECT INVARIANTS"]
        for cat, t, c in proj_records:
            line = f"- [{cat}] {t}: {c}"
            if sum(len(x) for x in p_lines) + len(line) < mem_budget:
                p_lines.append(line)
        proj_block = "\n".join(p_lines)

        snapshot = f"{user_block}\n\n{proj_block}\n\n{dyn_block}".strip()
        return snapshot[:TOTAL_INJECTION_BUDGET]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Hermes Agent Experiential Memory Engine")
    parser.add_argument("action", choices=["search", "stats", "inject", "sync"], help="Action to perform")
    parser.add_argument("query", nargs="?", default="", help="Query string for search or inject")
    parser.add_argument("--db", type=pathlib.Path, default=None, help="Custom path to project_memory.db")
    parser.add_argument("--project", type=str, default="flh-one", help="Project identifier")

    args = parser.parse_args()

    db_path = args.db
    if not db_path:
        for candidate in [
            pathlib.Path.cwd() / ".hermes" / "project_memory.db",
            pathlib.Path(r"C:\Users\User\Desktop\flh-one\.hermes\project_memory.db"),
            pathlib.Path(r"./.hermes\project_memory.db"),
        ]:
            if candidate.exists():
                db_path = candidate
                break
        if not db_path:
            db_path = pathlib.Path.cwd() / ".hermes" / "project_memory.db"

    engine = MemoryEngine(db_path=db_path, project_id=args.project)

    if args.action == "stats":
        cur = engine._conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        cats = cur.execute("SELECT category, COUNT(*) FROM memories GROUP BY category").fetchall()
        print(f"📊 Hermes Memory Stats ({db_path.name}):")
        print(f"   Total Memories: {total}")
        for c, count in cats:
            print(f"   • {c.capitalize()}: {count}")

    elif args.action == "search":
        if not args.query:
            print("Please provide a search query.")
            return
        results = engine.search(args.query, limit=6)
        print(f"🔍 Search results for '{args.query}' in {db_path.name} ({len(results)} hit(s)):")
        for idx, r in enumerate(results, 1):
            print(f"\n  {idx}. [{r.category.upper()}] {r.title}")
            print(f"     {r.content}")
            print(f"     Rank score: {r.score:.2f}")

    elif args.action == "inject":
        prompt = engine.assemble_system_prompt_injection(args.query)
        print("🧠 Assembled System Prompt Injection Snapshot:")
        print(prompt)

    elif args.action == "sync":
        u_len, m_len = engine.generate_markdown_mirrors(
            user_md_path=db_path.parent.parent / "USER.md",
            memory_md_path=db_path.parent.parent / "MEMORY.md"
        )
        print(f"✅ Generated USER.md ({u_len} chars) and MEMORY.md ({m_len} chars).")


if __name__ == "__main__":
    main()

