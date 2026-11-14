#!/usr/bin/env python3
"""
Hermes Rapid Turn-1 Memory Recall CLI
Part of hermes-agent-core universal skill.
Queries SQLite + FTS5 BM25 memory index and user profile store with zero external dependencies.
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

try:
    from hybrid_memory_engine import HermesHybridRecallAdapter
except ImportError:
    try:
        from .hybrid_memory_engine import HermesHybridRecallAdapter
    except ImportError:
        HermesHybridRecallAdapter = None

DEFAULT_DB = Path.home() / ".gemini" / "antigravity" / "hermes_global_memory.db"

def search_hybrid(query: str, limit: int = 5):
    """Executes dual-signal hybrid search combining FTS5 BM25 and character n-gram RRF."""
    if not DEFAULT_DB.exists():
        print(f"[!] Hermes DB not found at: {DEFAULT_DB}")
        return

    if not HermesHybridRecallAdapter:
        print("[!] Hybrid memory engine not available. Falling back to FTS5 search.")
        search_fts(query, limit)
        return

    engine = HermesHybridRecallAdapter.create_hybrid_index_from_sqlite(str(DEFAULT_DB))
    results = engine.search(query, limit=limit)

    if not results:
        # Fallback to search_fts if no results from hybrid
        search_fts(query, limit)
        return

    print(f"\n=================================================================")
    print(f"HERMES HYBRID MEMORY RECALL (FTS5 + N-Gram + RRF): '{query}' ({len(results)} results)")
    print(f"=================================================================")
    for r in results:
        lex_str = f"#{r.lexical_rank}" if r.lexical_rank else "None"
        sem_str = f"#{r.semantic_rank} ({r.semantic_similarity:.2f})" if r.semantic_rank else "None"
        print(f"\n[Memory #{r.id}] {r.title}")
        print(f"  RRF Score: {r.rrf_score:.4f} | Lexical Rank: {lex_str} | Semantic Rank: {sem_str}")
        print(f"  Tags: {r.tags}")
        print(f"  Content: {r.content[:300]}...")

def search_fts(query: str, limit: int = 5):
    """Executes full-text search against episodic memories via FTS5."""
    if not DEFAULT_DB.exists():
        print(f"[!] Hermes DB not found at: {DEFAULT_DB}")
        return

    conn = sqlite3.connect(DEFAULT_DB)
    cur = conn.cursor()

    try:
        # Sanitize query: quote phrase if contains hyphen or special chars
        clean_terms = []
        for term in query.split():
            clean = term.replace('"', '""')
            if "-" in clean or ":" in clean or "*" in clean:
                clean_terms.append(f'"{clean}"')
            else:
                clean_terms.append(clean)
        fts_query = " ".join(clean_terms)

        rows = []
        try:
            sql = """
            SELECT e.id, e.project_name, e.category, e.title, e.content, e.tags, e.created_at
            FROM episodic_memories e
            JOIN episodic_memories_fts f ON e.id = f.rowid
            WHERE episodic_memories_fts MATCH ?
            ORDER BY rank
            LIMIT ?;
            """
            cur.execute(sql, (fts_query, limit))
            rows = cur.fetchall()
        except sqlite3.OperationalError:
            # Fallback if FTS syntax error
            pass

        if not rows:
            # Fallback to LIKE
            like_sql = """
            SELECT id, project_name, category, title, content, tags, created_at
            FROM episodic_memories
            WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?
            ORDER BY id DESC
            LIMIT ?;
            """
            kw = f"%{query}%"
            cur.execute(like_sql, (kw, kw, kw, limit))
            rows = cur.fetchall()

        if not rows:
            print(f"[Hermes Recall] No memories found matching: '{query}'")
            return

        print(f"\n=================================================================")
        print(f"HERMES MEMORY RECALL: '{query}' ({len(rows)} results)")
        print(f"=================================================================")
        for r in rows:
            print(f"\n[Memory #{r[0]}] [{r[2].upper()}] {r[3]} (Project: {r[1]})")
            print(f"Created: {r[6]} | Tags: {r[5]}")
            print(f"Content: {r[4]}")
    finally:
        conn.close()

def get_profile():
    """Fetches user profile preferences."""
    if not DEFAULT_DB.exists():
        print(f"[!] Hermes DB not found at: {DEFAULT_DB}")
        return

    conn = sqlite3.connect(DEFAULT_DB)
    cur = conn.cursor()
    cur.execute("SELECT key, category, value, confidence FROM user_profiles ORDER BY category, key")
    rows = cur.fetchall()
    conn.close()

    print(f"\n=================================================================")
    print(f"HERMES USER DIALECTICAL PROFILE & PREFERENCES ({len(rows)} entries)")
    print(f"=================================================================")
    current_cat = None
    for r in rows:
        cat = r[1]
        if cat != current_cat:
            print(f"\n[{cat.upper()}]:")
            current_cat = cat
        print(f"  • {r[0]}: {r[2]} (confidence: {r[3]})")

def get_recent(limit: int = 5):
    """Fetches most recent episodic memories."""
    if not DEFAULT_DB.exists():
        print(f"[!] Hermes DB not found at: {DEFAULT_DB}")
        return

    conn = sqlite3.connect(DEFAULT_DB)
    cur = conn.cursor()
    cur.execute("SELECT id, project_name, category, title, content, created_at FROM episodic_memories ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()

    print(f"\n=================================================================")
    print(f"HERMES RECENT EPISODIC MEMORIES (Last {len(rows)})")
    print(f"=================================================================")
    for r in rows:
        print(f"\n[#{r[0]}] [{r[2].upper()}] {r[3]} (Project: {r[1]} | {r[5]})")
        print(f"  {r[4][:250]}...")

def main():
    parser = argparse.ArgumentParser(description="Hermes Rapid Turn-1 Memory Recall CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Search
    p_search = subparsers.add_parser("search", help="Search memories by keyword using FTS5 or Hybrid RRF")
    p_search.add_argument("query", help="Keyword or search phrase")
    p_search.add_argument("--limit", type=int, default=5, help="Max results")
    p_search.add_argument("--fts-only", action="store_true", help="Force classic FTS5 search instead of hybrid RRF")

    # Profile
    subparsers.add_parser("profile", help="Display dialectical user profile and preferences")

    # Recent
    p_recent = subparsers.add_parser("recent", help="Show recent episodic memories")
    p_recent.add_argument("--limit", type=int, default=5, help="Number of recent memories")

    args = parser.parse_args()

    if args.command == "search":
        if args.fts_only:
            search_fts(args.query, args.limit)
        else:
            search_hybrid(args.query, args.limit)
    elif args.command == "profile":
        get_profile()
    elif args.command == "recent":
        get_recent(args.limit)

if __name__ == "__main__":
    main()
