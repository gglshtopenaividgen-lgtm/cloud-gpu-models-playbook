"""
Hermes Persistent Memory Engine (SQLite + FTS5)
Provides cross-session recall, dialectical user modeling, episodic memory, and full-text search.
Zero external dependencies (uses standard Python sqlite3 with FTS5).
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".gemini" / "antigravity" / "hermes_global_memory.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    key TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    value TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS episodic_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL,
    category TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS episodic_memories_fts USING fts5(
    title,
    content,
    tags,
    content='episodic_memories',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS episodic_ai AFTER INSERT ON episodic_memories BEGIN
    INSERT INTO episodic_memories_fts(rowid, title, content, tags) VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS episodic_ad AFTER DELETE ON episodic_memories BEGIN
    INSERT INTO episodic_memories_fts(episodic_memories_fts, rowid, title, content, tags) VALUES('delete', old.id, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS episodic_au AFTER UPDATE ON episodic_memories BEGIN
    INSERT INTO episodic_memories_fts(episodic_memories_fts, rowid, title, content, tags) VALUES('delete', old.id, old.title, old.content, old.tags);
    INSERT INTO episodic_memories_fts(rowid, title, content, tags) VALUES (new.id, new.title, new.content, new.tags);
END;

CREATE TABLE IF NOT EXISTS session_digests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    project_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    key_decisions TEXT,
    lessons_learned TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skills_registry (
    skill_name TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    path TEXT NOT NULL,
    triggers TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def get_connection(db_path: Path = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = None):
    conn = get_connection(db_path)
    with conn:
        conn.executescript(SCHEMA_SQL)
    conn.close()
    print(f"[HermesMemory] Database initialized successfully at: {db_path or DEFAULT_DB_PATH}")


def set_user_profile(key: str, category: str, value: str, confidence: float = 1.0, db_path: Path = None):
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO user_profiles (key, category, value, confidence, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                category=excluded.category,
                value=excluded.value,
                confidence=excluded.confidence,
                updated_at=CURRENT_TIMESTAMP
            """,
            (key, category, value, confidence)
        )
    conn.close()
    print(f"[HermesMemory] Profile updated: [{category}] {key} = {value}")


def get_user_profile(category: str = None, db_path: Path = None):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    if category:
        cursor.execute("SELECT key, category, value, confidence, updated_at FROM user_profiles WHERE category = ?", (category,))
    else:
        cursor.execute("SELECT key, category, value, confidence, updated_at FROM user_profiles ORDER BY category, key")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def store_memory(project_name: str, category: str, title: str, content: str, tags: str = "", db_path: Path = None):
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO episodic_memories (project_name, category, title, content, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_name, category, title, content, tags)
        )
        mem_id = cursor.lastrowid
    conn.close()
    print(f"[HermesMemory] Stored memory #{mem_id} ({category}): {title}")
    return mem_id


def search_memory(query: str, limit: int = 5, db_path: Path = None):
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT m.id, m.project_name, m.category, m.title, m.content, m.tags, m.created_at,
                   rank
            FROM episodic_memories_fts fts
            JOIN episodic_memories m ON fts.rowid = m.id
            WHERE episodic_memories_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, limit)
        )
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        clean_query = f"%{query}%"
        cursor.execute(
            """
            SELECT id, project_name, category, title, content, tags, created_at, 0 as rank
            FROM episodic_memories
            WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (clean_query, clean_query, clean_query, limit)
        )
        rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def store_digest(session_id: str, project_name: str, summary: str, decisions: str = "", lessons: str = "", db_path: Path = None):
    conn = get_connection(db_path)
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO session_digests (session_id, project_name, summary, key_decisions, lessons_learned)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_id, project_name, summary, decisions, lessons)
        )
        digest_id = cursor.lastrowid
    conn.close()
    print(f"[HermesMemory] Stored session digest #{digest_id} for session {session_id}")
    return digest_id


def register_skill(skill_name: str, description: str, path: str, triggers: str = "", db_path: Path = None):
    conn = get_connection(db_path)
    with conn:
        conn.execute(
            """
            INSERT INTO skills_registry (skill_name, description, path, triggers)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(skill_name) DO UPDATE SET
                description=excluded.description,
                path=excluded.path,
                triggers=excluded.triggers,
                created_at=CURRENT_TIMESTAMP
            """,
            (skill_name, description, path, triggers)
        )
    conn.close()
    print(f"[HermesMemory] Registered skill '{skill_name}' -> {path}")


def main():
    parser = argparse.ArgumentParser(description="Hermes Memory Engine CLI")
    parser.add_argument("--db", type=str, default=None, help="Custom database file path")

    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # init
    subparsers.add_parser("init", help="Initialize memory database schema")

    # store
    store_p = subparsers.add_parser("store", help="Store an episodic memory")
    store_p.add_argument("--project", required=True, help="Project name")
    store_p.add_argument("--category", required=True, help="Category (architecture, bug_fix, decision, preference)")
    store_p.add_argument("--title", required=True, help="Short summary/title")
    store_p.add_argument("--content", required=True, help="Detailed content")
    store_p.add_argument("--tags", default="", help="Comma-separated tags")

    # search
    search_p = subparsers.add_parser("search", help="Search memory using FTS5")
    search_p.add_argument("query", help="Search query keywords")
    search_p.add_argument("--limit", type=int, default=5, help="Result limit")

    # profile
    profile_p = subparsers.add_parser("profile", help="Manage user dialectical profile")
    profile_p.add_argument("--get", action="store_true", help="Print user profile")
    profile_p.add_argument("--category", default=None, help="Filter by category")
    profile_p.add_argument("--set-key", default=None, help="Profile attribute key")
    profile_p.add_argument("--set-val", default=None, help="Profile attribute value")

    # digest
    digest_p = subparsers.add_parser("digest", help="Store a session summary digest")
    digest_p.add_argument("--session-id", required=True, help="Session / Conversation ID")
    digest_p.add_argument("--project", required=True, help="Project name")
    digest_p.add_argument("--summary", required=True, help="Executive summary of accomplishments")
    digest_p.add_argument("--decisions", default="", help="Decisions made")
    digest_p.add_argument("--lessons", default="", help="Lessons or mistakes avoided")

    args = parser.parse_args()
    db_path = Path(args.db) if args.db else None

    if args.command == "init":
        init_db(db_path)
    elif args.command == "store":
        store_memory(args.project, args.category, args.title, args.content, args.tags, db_path)
    elif args.command == "search":
        results = search_memory(args.query, args.limit, db_path)
        if not results:
            print(f"[HermesMemory] No memories found matching: '{args.query}'")
        else:
            print(f"[HermesMemory] Found {len(results)} match(es) for '{args.query}':")
            for r in results:
                print(f"  [{r['category'].upper()}] {r['title']} (Project: {r['project_name']})")
                print(f"    Content: {r['content'][:200]}...")
                if r['tags']:
                    print(f"    Tags: {r['tags']}")
    elif args.command == "profile":
        if args.set_key and args.set_val:
            cat = args.category or "preferences"
            set_user_profile(args.set_key, cat, args.set_val, db_path=db_path)
        else:
            profile = get_user_profile(args.category, db_path)
            print(json.dumps(profile, indent=2))
    elif args.command == "digest":
        store_digest(args.session_id, args.project, args.summary, args.decisions, args.lessons, db_path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
