#!/usr/bin/env python3
"""
Selective Context-Packing Framework for Argon Brain (`argon_context_packer.py`)
===============================================================================
Intelligently retrieves, filters, slices, and bundles relevant context for Argon
High-Thinking consultations WITHOUT dumping entire files.

Sources Integrated (Zero Blind Dumping):
1. Project Router (`project_map.md` & `<project>/file_map.md`):
   - Identifies the active project and strictly excludes foreign project entries.
   - Extracts only matching subsystem rows from `file_map.md`.
2. Hermes Hybrid Memory (`hermes_global_memory.db` via RRF = FTS5 BM25 + N-gram TF-IDF):
   - Pulls compact Dialectical User Profile + Top-K matching episodic memories.
3. Selective Markdown Section Retriever (`constraints.md`, `ideas.md`, `mistakes.md`):
   - Parses thousands of lines into discrete `###` / `##` semantic blocks.
   - Scores each block via BM25 + subword character n-gram overlap + project tag match.
   - Selects ONLY the Top-K highest-signal constraints, ideas, and mistakes.
4. Smart AST & Keyword-Window Code Slicer (`--pack <file[:start-end|#Symbol]>`):
   - Supports explicit line ranges (`file.py:50-120`) and symbol slices (`file.py#MyClass`).
   - For large files (>160 lines), generates a compact AST structural signature outline
     plus only the top keyword-relevant functions/classes, bounded by a strict budget.
5. Client-Side Shadow Session Ledger (`temp_read/sessions/<session_id>.jsonl`):
   - Preserves multi-turn continuity across profile rotations or Tier-2 API failover.
"""

import ast
import json
import math
import os
import re
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BRAIN_ROOT = Path(r"./")
HERMES_SCRIPTS = BRAIN_ROOT / ".agents" / "skills" / "hermes-agent-core" / "scripts"
if str(HERMES_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(HERMES_SCRIPTS))

# Project routing map (from brain/project_map.md)
PROJECT_REGISTRY: Dict[str, Dict[str, str]] = {
    "flh-one": {
        "root": r"C:\Users\User\Desktop\flh-one",
        "tags": "flh-one,srm,portal,next,tiptap,supabase,vm1,vm2,litellm",
    },
    "hi": {
        "root": r"C:\Users\User\Desktop\PJCT\hi",
        "tags": "hi,kaggle,colab,modal,gpu,tpu,t4,gguf,sdxl,gradio,abliterated",
    },
    "AWAKEN1": {
        "root": r"C:\Users\User\Desktop\PJCT\AWAKEN1",
        "tags": "awaken1,krpg,seoul,manhwa,threejs,ccd,winskel,npc,causality",
    },
    "flh-music": {
        "root": r"C:\Users\User\Desktop\appwrite\flh-music",
        "tags": "flh-music,music,audio,dsp,eq,harman,lrclib,lyrics,appwrite,spotify",
    },
    "mineserver": {
        "root": r"C:\Users\User\Desktop\PJCT\mineserver",
        "tags": "mineserver,minecraft,paper,fabric,geyser,floodgate,ver_backup",
    },
    "cult_game": {
        "root": r"C:\Users\User\Desktop\PJCT\cult_game",
        "tags": "cult_game,cultivator,xianxia,isometric,seelie,realm",
    },
    "custom_tools": {
        "root": r"C:\Users\User\Desktop\PJCT\custom_tools",
        "tags": "custom_tools,api_router,gateway,vertex,maas,md-view,vlc,bulk_generator",
    },
    "PKREA": {
        "root": r"<PROJECTS_ROOT>\PKREA",
        "tags": "pkrea,rea,reverse,binary,disassembly,deobfuscation,apk,wasm",
    },
    "brain": {
        "root": r"./",
        "tags": "brain,argon,gemini,skill,subagent,hermes,search,driver,bridge,profile",
    },
}

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "what", "how", "why",
    "when", "where", "which", "who", "will", "would", "should", "could", "have",
    "has", "had", "been", "were", "was", "are", "is", "be", "to", "of", "in",
    "on", "at", "by", "an", "a", "or", "as", "it", "its", "into", "about",
    "use", "using", "used", "make", "sure", "properly", "also", "then", "than",
    "can", "you", "we", "our", "all", "any", "some", "more", "most", "other",
    "give", "ask", "stuff", "proper", "properly", "like", "file", "files",
}


def tokenize(text: str) -> List[str]:
    """Extracts normalized alphanumeric & identifier tokens excluding stopwords."""
    raw = re.findall(r"[a-zA-Z0-9_]{2,}", text.lower())
    tokens = []
    for t in raw:
        if t not in STOPWORDS and not t.isdigit():
            tokens.append(t)
            # Also split snake_case / camelCase parts
            if "_" in t:
                for part in t.split("_"):
                    if len(part) >= 3 and part not in STOPWORDS:
                        tokens.append(part)
    return tokens


def char_ngrams(text: str, n: int = 3) -> Counter:
    """Computes character n-gram multiset for subword similarity."""
    clean = re.sub(r"\s+", " ", text.lower().strip())
    if len(clean) < n:
        return Counter({clean: 1})
    return Counter(clean[i : i + n] for i in range(len(clean) - n + 1))


def cosine_counter(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    common = set(a.keys()) & set(b.keys())
    num = sum(a[k] * b[k] for k in common)
    if num == 0:
        return 0.0
    den_a = math.sqrt(sum(v * v for v in a.values()))
    den_b = math.sqrt(sum(v * v for v in b.values()))
    return num / (den_a * den_b) if (den_a and den_b) else 0.0


def detect_active_project(prompt: str, explicit_project: Optional[str] = None, cwd: Optional[str] = None) -> str:
    """Identifies the active project from explicit flag, CWD, or prompt tokens."""
    if explicit_project:
        for k in PROJECT_REGISTRY:
            if k.lower() == explicit_project.lower():
                return k
        if explicit_project.lower() == "krpg":
            return "AWAKEN1"

    work_dir = os.path.abspath(cwd or os.getcwd()).lower()
    for proj, info in PROJECT_REGISTRY.items():
        if proj != "brain" and os.path.abspath(info["root"]).lower() in work_dir:
            return proj

    # Score prompt against project tags
    prompt_lower = prompt.lower()
    best_proj = "brain"
    best_hits = 0
    for proj, info in PROJECT_REGISTRY.items():
        if proj == "brain":
            continue
        tags = [t.strip() for t in info["tags"].split(",")]
        hits = sum(2 if f" {t} " in f" {prompt_lower} " else (1 if t in prompt_lower else 0) for t in tags)
        if hits > best_hits:
            best_hits = hits
            best_proj = proj

    return best_proj if best_hits >= 2 else "brain"


def is_foreign_project_section(header: str, body: str, active_project: str) -> bool:
    """Returns True if a markdown section explicitly belongs to a different project."""
    combined = header.lower()
    foreign_markers = {
        "flh-one": ["(flh-one)", "[flh-one", "srm student portal", "srm_cards"],
        "hi": ["(hi)", "[hi synced", "(kaggle/hi)"],
        "AWAKEN1": ["(krpg)", "[krpg synced", "(awaken1)", "chrono awakening"],
        "flh-music": ["(flh-music)", "[flh music synced", "apple music lyrics-first"],
        "mineserver": ["(mineserver)", "papermc"],
        "cult_game": ["(cult_game)", "eternal cultivator"],
        "custom_tools": ["(custom_tools)", "[custom_tools synced"],
        "PKREA": ["(pkrea)"],
    }
    for proj, markers in foreign_markers.items():
        if proj.lower() == active_project.lower():
            continue
        for m in markers:
            if m in combined:
                return True
    return False


def chunk_markdown_sections(md_text: str) -> List[Dict[str, str]]:
    """Splits a Markdown file into discrete sections by ## or ### headings."""
    lines = md_text.splitlines()
    sections: List[Dict[str, str]] = []
    cur_header = "Overview"
    cur_lines: List[str] = []

    for line in lines:
        if re.match(r"^#{2,3}\s+", line):
            if cur_lines:
                body = "\n".join(cur_lines).strip()
                if len(body) > 25:
                    sections.append({"header": cur_header, "body": body})
            cur_header = line.strip()
            cur_lines = [line]
        else:
            cur_lines.append(line)

    if cur_lines:
        body = "\n".join(cur_lines).strip()
        if len(body) > 25:
            sections.append({"header": cur_header, "body": body})
    return sections


def retrieve_top_sections(
    sections: List[Dict[str, str]],
    query_tokens: List[str],
    query_ngrams: Counter,
    active_project: str,
    top_k: int = 5,
    max_section_chars: int = 1200,
) -> List[Dict[str, str]]:
    """Scores and selects the Top-K most relevant markdown sections (BM25 + N-gram + Recency)."""
    if not sections:
        return []

    filtered = [
        (idx, s)
        for idx, s in enumerate(sections)
        if not is_foreign_project_section(s["header"], s["body"], active_project)
    ]
    if not filtered:
        filtered = list(enumerate(sections))

    q_counts = Counter(query_tokens)
    total_docs = len(filtered)
    df: Counter = Counter()
    doc_tokens_list = []

    for _, s in filtered:
        dtoks = tokenize(s["header"] + " " + s["body"])
        doc_tokens_list.append(dtoks)
        for ut in set(dtoks):
            df[ut] += 1

    avg_dl = sum(len(dt) for dt in doc_tokens_list) / max(1, total_docs)
    k1, b = 1.5, 0.75

    scored = []
    for pos, ((orig_idx, s), dtoks) in enumerate(zip(filtered, doc_tokens_list)):
        tf = Counter(dtoks)
        dl = len(dtoks)
        bm25 = 0.0
        for qt, qf in q_counts.items():
            if qt in tf:
                idf = math.log(1.0 + (total_docs - df[qt] + 0.5) / (df[qt] + 0.5))
                denom = tf[qt] + k1 * (1.0 - b + b * (dl / max(1.0, avg_dl)))
                bm25 += idf * ((tf[qt] * (k1 + 1.0)) / denom)

        # Header exact token match bonus
        header_toks = set(tokenize(s["header"]))
        header_overlap = sum(1.5 for qt in q_counts if qt in header_toks)

        # Character n-gram similarity on header + first 300 chars
        snippet_ngrams = char_ngrams(s["header"] + " " + s["body"][:350])
        ngram_sim = cosine_counter(query_ngrams, snippet_ngrams) * 4.0

        # Active project tag bonus
        proj_bonus = 2.0 if f"({active_project.lower()})" in s["header"].lower() else 0.0

        # Mild recency bonus for later entries in append-only ledgers
        recency_bonus = (orig_idx / max(1, len(sections))) * 0.8

        total_score = bm25 + header_overlap + ngram_sim + proj_bonus + recency_bonus
        scored.append((total_score, orig_idx, s))

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = []
    for score, orig_idx, s in scored[:top_k]:
        body = s["body"]
        if len(body) > max_section_chars:
            body = body[:max_section_chars].rsplit("\n", 1)[0] + "\n  ...[truncated for density]..."
        selected.append({"header": s["header"], "body": body, "score": round(score, 2)})

    return selected


def recall_hermes_context(prompt: str, active_project: str, top_k: int = 5) -> Tuple[str, List[Dict]]:
    """Queries HermesHybridRecallAdapter for user dialectical profile and top relevant memories."""
    profile_lines = []
    memories = []
    try:
        import sqlite3
        from hybrid_memory_engine import HermesHybridRecallAdapter

        db_path = Path.home() / ".gemini" / "antigravity" / "hermes_global_memory.db"
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                rows = conn.execute(
                    "SELECT key, category, value FROM user_profiles ORDER BY id DESC LIMIT 8"
                ).fetchall()
                for r in rows:
                    profile_lines.append(f"- **[{r[1]}] {r[0]}**: {r[2]}")
            except Exception:
                pass
            finally:
                conn.close()

            engine = HermesHybridRecallAdapter.create_hybrid_index_from_sqlite(str(db_path))
            results = engine.search(prompt, limit=top_k)
            for r in results:
                memories.append({
                    "id": r.id,
                    "category": r.tags.split(",")[0] if r.tags else "memory",
                    "title": r.title,
                    "content": r.content,
                    "rrf_score": r.rrf_score,
                })
    except Exception as e:
        profile_lines.append(f"- *(Hermes recall notice: {e})*")

    return "\n".join(profile_lines), memories


def slice_code_file(
    spec: str,
    query_tokens: List[str],
    cwd: Optional[str] = None,
    max_file_chars: int = 6500,
) -> Optional[Dict[str, str]]:
    """
    Smart code slicer supporting:
    - `path/to/file.py:100-220` (explicit line range)
    - `path/to/file.py#SymbolName` (AST function/class extraction)
    - `path/to/file.py` (if <=160 lines: full file; if >160 lines: AST outline + top keyword windows)
    """
    raw_spec = spec.strip()
    line_range: Optional[Tuple[int, int]] = None
    target_symbol: Optional[str] = None

    if "#" in raw_spec and not raw_spec.startswith("#"):
        file_part, sym_part = raw_spec.rsplit("#", 1)
        raw_spec = file_part
        target_symbol = sym_part.strip()
    elif re.search(r":(\d+)(?:-(\d+))?$", raw_spec):
        m = re.search(r":(\d+)(?:-(\d+))?$", raw_spec)
        if m:
            start_l = int(m.group(1))
            end_l = int(m.group(2) or (start_l + 80))
            line_range = (max(1, start_l), end_l)
            raw_spec = raw_spec[: m.start()]

    path = Path(raw_spec)
    if not path.is_absolute():
        base = Path(cwd or os.getcwd())
        if (base / path).exists():
            path = (base / path).resolve()
        elif (BRAIN_ROOT / path).exists():
            path = (BRAIN_ROOT / path).resolve()

    if not path.exists() or not path.is_file():
        return None

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    lines = content.splitlines()
    total_lines = len(lines)

    def format_numbered(start_1based: int, end_1based: int) -> str:
        s = max(1, start_1based)
        e = min(total_lines, end_1based)
        out = [f"{i:4d} | {lines[i - 1]}" for i in range(s, e + 1)]
        return "\n".join(out)

    # Case 1: Explicit line range
    if line_range:
        sliced = format_numbered(line_range[0], line_range[1])
        return {
            "path": str(path),
            "mode": f"lines {line_range[0]}-{min(total_lines, line_range[1])} of {total_lines}",
            "content": sliced[:max_file_chars],
            "raw_chars": len(content),
        }

    # Case 2: Small file (<= 160 lines and <= max_file_chars)
    if total_lines <= 160 and len(content) <= max_file_chars and not target_symbol:
        return {
            "path": str(path),
            "mode": f"complete ({total_lines} lines)",
            "content": format_numbered(1, total_lines),
            "raw_chars": len(content),
        }

    # Case 3: Python AST Outline + Target Symbol or Top Keyword-Relevant Definitions
    if path.suffix.lower() == ".py":
        try:
            tree = ast.parse(content)
            outline = []
            blocks = []
            q_set = set(query_tokens)

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start_l = node.lineno
                    end_l = getattr(node, "end_lineno", start_l + 30)
                    kind = "class" if isinstance(node, ast.ClassDef) else "def"
                    sig = f"{kind} {node.name} (L{start_l}-L{end_l})"
                    if isinstance(node, ast.ClassDef):
                        methods = [
                            f"{m.name}(L{m.lineno})"
                            for m in node.body
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                        ]
                        if methods:
                            sig += ": " + ", ".join(methods[:12])
                    outline.append(f"  - {sig}")

                    block_src = "\n".join(lines[start_l - 1 : end_l])
                    block_toks = set(tokenize(node.name + " " + block_src))
                    score = sum(2.5 if qt in node.name.lower() else (1.0 if qt in block_toks else 0.0) for qt in q_set)
                    if target_symbol and target_symbol.lower() in node.name.lower():
                        score += 100.0
                    blocks.append((score, start_l, end_l, node.name))

                    # Also index methods inside large classes
                    if isinstance(node, ast.ClassDef) and (end_l - start_l) > 80:
                        for m in node.body:
                            if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                ms, me = m.lineno, getattr(m, "end_lineno", m.lineno + 25)
                                m_src = "\n".join(lines[ms - 1 : me])
                                m_toks = set(tokenize(m.name + " " + m_src))
                                m_score = sum(
                                    3.0 if qt in m.name.lower() else (1.0 if qt in m_toks else 0.0) for qt in q_set
                                )
                                if target_symbol and target_symbol.lower() in m.name.lower():
                                    m_score += 100.0
                                blocks.append((m_score, ms, me, f"{node.name}.{m.name}"))

            blocks.sort(key=lambda x: x[0], reverse=True)
            chosen_snippets = []
            used_lines = set()
            budget = max_file_chars - min(1500, len("\n".join(outline)))

            for score, s_l, e_l, bname in blocks:
                if score <= 0 and chosen_snippets:
                    break
                # Skip large whole-class block if we're better off picking specific methods
                if (e_l - s_l) > 120 and len(blocks) > 2 and not (target_symbol and target_symbol.lower() == bname.lower()):
                    continue
                if any(l in used_lines for l in range(s_l, e_l + 1)):
                    continue
                snip = f"# --- Relevant Symbol: {bname} (L{s_l}-L{e_l}, relevance={score:.1f}) ---\n" + format_numbered(
                    s_l, min(e_l, s_l + 95)
                )
                if sum(len(x) for x in chosen_snippets) + len(snip) > budget and chosen_snippets:
                    break
                chosen_snippets.append(snip)
                used_lines.update(range(s_l, e_l + 1))
                if len(chosen_snippets) >= 4:
                    break

            assembled = "## AST Structural Outline:\n" + "\n".join(outline[:30]) + "\n\n" + "\n\n".join(chosen_snippets)
            return {
                "path": str(path),
                "mode": f"AST-sliced ({len(chosen_snippets)} top blocks from {total_lines} lines)",
                "content": assembled[:max_file_chars],
                "raw_chars": len(content),
            }
        except Exception:
            pass

    # Case 4: Non-Python or Fallback Keyword Window Slicer (chunks of 45 lines)
    window_size = 45
    q_set = set(query_tokens)
    windows = []
    for start in range(1, total_lines + 1, window_size):
        end = min(total_lines, start + window_size - 1)
        chunk_str = "\n".join(lines[start - 1 : end])
        ctoks = set(tokenize(chunk_str))
        score = sum(1.0 for qt in q_set if qt in ctoks)
        if target_symbol and target_symbol.lower() in chunk_str.lower():
            score += 50.0
        windows.append((score, start, end))

    windows.sort(key=lambda x: x[0], reverse=True)
    selected_win = sorted(windows[:3], key=lambda x: x[1])
    parts = [
        f"# --- Window L{s}-L{e} (score={sc:.1f}) ---\n" + format_numbered(s, e) for sc, s, e in selected_win
    ]
    return {
        "path": str(path),
        "mode": f"window-sliced ({len(selected_win)} windows from {total_lines} lines)",
        "content": ("\n\n".join(parts))[:max_file_chars],
        "raw_chars": len(content),
    }


def compress_code_content(content: str, file_path: str = "") -> str:
    """
    Compresses code or markdown content by stripping verbose comments/whitespace
    and extracting structural symbol outlines (repomix / Python-outline style).
    """
    ext = Path(file_path).suffix.lower() if file_path else ""

    # Strategy 1: Python AST Symbol Outline Compression
    if ext == ".py":
        has_line_nums = bool(re.search(r"^\s*\d+\s*\|\s*", content, re.MULTILINE))
        clean_src = re.sub(r"^\s*\d+\s*\|\s*", "", content, flags=re.MULTILINE) if has_line_nums else content
        try:
            tree = ast.parse(clean_src)
            outlines: List[str] = []
            for node in tree.body:
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    outlines.append(ast.unparse(node))
                elif isinstance(node, ast.ClassDef):
                    bases = [ast.unparse(b) for b in node.bases]
                    base_str = f"({', '.join(bases)})" if bases else ""
                    outlines.append(f"class {node.name}{base_str}:")
                    doc = ast.get_docstring(node)
                    if doc:
                        outlines.append(f'    """{doc[:120].strip()}"""')
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            prefix = "async def" if isinstance(item, ast.AsyncFunctionDef) else "def"
                            args_str = ast.unparse(item.args)
                            ret_str = f" -> {ast.unparse(item.returns)}" if item.returns else ""
                            outlines.append(f"    {prefix} {item.name}({args_str}){ret_str}: ...")
                            mdoc = ast.get_docstring(item)
                            if mdoc:
                                outlines.append(f'        """{mdoc[:80].strip()}"""')
                        elif isinstance(item, ast.AnnAssign):
                            outlines.append(f"    {ast.unparse(item)}")
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                    args_str = ast.unparse(node.args)
                    ret_str = f" -> {ast.unparse(node.returns)}" if node.returns else ""
                    outlines.append(f"{prefix} {node.name}({args_str}){ret_str}: ...")
                    fdoc = ast.get_docstring(node)
                    if fdoc:
                        outlines.append(f'    """{fdoc[:100].strip()}"""')
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    assign_str = ast.unparse(node)
                    if len(assign_str) < 140:
                        outlines.append(assign_str)
            if outlines:
                return "\n".join(outlines)
        except Exception:
            pass

    # Strategy 2: Regex / Token structural comment & whitespace stripper
    has_line_nums = bool(re.search(r"^\s*\d+\s*\|\s*", content, re.MULTILINE))
    lines = content.splitlines()
    processed_lines = []
    in_block_comment = False

    for line in lines:
        raw_code = re.sub(r"^\s*\d+\s*\|\s*", "", line) if has_line_nums else line
        stripped = raw_code.strip()

        # Multiline comment handling
        if in_block_comment:
            if "*/" in stripped:
                in_block_comment = False
            continue
        if stripped.startswith("/*"):
            if "*/" not in stripped:
                in_block_comment = True
            continue

        # Skip standalone single-line comments (# or //)
        if stripped.startswith("#") and not stripped.startswith("#!") and not stripped.startswith("# ---"):
            continue
        if stripped.startswith("//"):
            continue

        # Strip inline comments
        if "//" in raw_code and not ('"' in raw_code or "'" in raw_code):
            raw_code = raw_code.split("//", 1)[0].rstrip()
        elif "#" in raw_code and not ('"' in raw_code or "'" in raw_code or raw_code.strip().startswith("#")):
            raw_code = raw_code.split("#", 1)[0].rstrip()

        # Collapse whitespace
        if not raw_code.strip():
            if processed_lines and processed_lines[-1] != "":
                processed_lines.append("")
        else:
            processed_lines.append(raw_code.rstrip())

    result = "\n".join(processed_lines)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


def auto_discover_files_in_prompt(prompt: str, active_project: str, cwd: Optional[str] = None) -> List[str]:
    """Detects file paths or script names referenced inside the prompt."""
    found = []
    proj_root = Path(PROJECT_REGISTRY.get(active_project, {}).get("root", str(BRAIN_ROOT)))
    candidates = re.findall(r"(?:[a-zA-Z]:[\\/][^\s\"'`<>|]+|[a-zA-Z0-9_./\\-]+\.(?:py|ts|tsx|js|json|md|sh))", prompt)
    for cand in candidates:
        cand_clean = cand.strip(".,;:()[]")
        # Avoid re-packing the massive raw ledgers since we already section-retrieve them
        if Path(cand_clean).name.lower() in ("ideas.md", "mistakes.md", "constraints.md", "project_map.md"):
            continue
        for base in [Path(cwd or os.getcwd()), proj_root, BRAIN_ROOT]:
            p = base / cand_clean if not Path(cand_clean).is_absolute() else Path(cand_clean)
            if p.exists() and p.is_file():
                resolved = str(p.resolve())
                if resolved not in found:
                    found.append(resolved)
                break
    return found[:4]


def extract_relevant_file_map(active_project: str, query_tokens: List[str]) -> str:
    """Extracts only the matching lines/subsystems from `<project>/file_map.md`."""
    proj_root = Path(PROJECT_REGISTRY.get(active_project, {}).get("root", str(BRAIN_ROOT)))
    fmap_path = proj_root / "file_map.md"
    if not fmap_path.exists():
        fmap_path = BRAIN_ROOT / "file_map.md"
    if not fmap_path.exists():
        return ""

    try:
        text = fmap_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    sections = chunk_markdown_sections(text)
    if len(sections) <= 2:
        return text[:1800]

    top = retrieve_top_sections(
        sections,
        query_tokens,
        char_ngrams(" ".join(query_tokens)),
        active_project=active_project,
        top_k=3,
        max_section_chars=700,
    )
    return "\n\n".join(s["body"] for s in top)


def load_session_history(session_id: Optional[str], max_turns: int = 4) -> str:
    """Loads recent turns from client-side shadow session ledger if session_id is provided."""
    if not session_id:
        return ""
    ledger_path = BRAIN_ROOT / "temp_read" / "sessions" / f"{session_id}.jsonl"
    if not ledger_path.exists():
        return ""
    turns = []
    try:
        for line in ledger_path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.strip():
                turns.append(json.loads(line))
    except Exception:
        return ""
    recent = turns[-max_turns:]
    out = []
    for idx, t in enumerate(recent, 1):
        q = (t.get("prompt") or "")[:400]
        a = (t.get("response") or "")[:900]
        out.append(f"### Prior Turn {idx} ({t.get('timestamp', '')})\n- **User**: {q}\n- **Argon**: {a}")
    return "\n\n".join(out)


def record_session_turn(session_id: str, prompt: str, response: str, profile: str, chat_url: Optional[str] = None) -> Path:
    """Appends a completed consultation turn to `temp_read/sessions/<session_id>.jsonl`."""
    sess_dir = BRAIN_ROOT / "temp_read" / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = sess_dir / f"{session_id}.jsonl"
    entry = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "session_id": session_id,
        "profile": profile,
        "chat_url": chat_url,
        "prompt": prompt,
        "response": response,
    }
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return ledger_path


def build_selective_context_bundle(
    prompt: str,
    pack_specs: Optional[List[str]] = None,
    explicit_project: Optional[str] = None,
    session_id: Optional[str] = None,
    output_path: Optional[str] = None,
    max_total_chars: int = 24000,
    cwd: Optional[str] = None,
    compress: bool = False,
) -> Tuple[str, Dict]:
    """
    Executes the 6-Stage Selective Context-Packing Pipeline and writes a compact,
    high-signal Markdown context bundle to `temp_read/argon_context_bundle.md`.
    Returns `(bundle_file_path, telemetry_dict)`.
    """
    active_project = detect_active_project(prompt, explicit_project=explicit_project, cwd=cwd)
    pack_specs = list(pack_specs or [])

    # Auto-discover any local files referenced in the prompt
    auto_files = auto_discover_files_in_prompt(prompt, active_project=active_project, cwd=cwd)
    for af in auto_files:
        if af not in pack_specs:
            pack_specs.append(af)

    # Combine prompt + packed filenames for query token extraction
    seed_text = prompt + " " + " ".join(Path(p.split(":")[0].split("#")[0]).stem for p in pack_specs)
    query_tokens = tokenize(seed_text)
    if not query_tokens:
        query_tokens = [active_project.lower(), "architecture"]
    query_ngrams = char_ngrams(seed_text)

    raw_bytes_scanned = 0

    # 1. Hermes Hybrid Memory Recall
    user_profile_md, hermes_memories = recall_hermes_context(prompt, active_project=active_project, top_k=5)

    # 2. Selective Constraints Retrieval
    constraints_path = BRAIN_ROOT / "constraints.md"
    top_constraints = []
    if constraints_path.exists():
        c_text = constraints_path.read_text(encoding="utf-8", errors="replace")
        raw_bytes_scanned += len(c_text)
        c_sections = chunk_markdown_sections(c_text)
        top_constraints = retrieve_top_sections(
            c_sections, query_tokens, query_ngrams, active_project=active_project, top_k=3, max_section_chars=900
        )

    # 3. Selective Ideas Retrieval (Universal + Project-Local)
    ideas_sections = []
    for ipath in [
        BRAIN_ROOT / "ideas.md",
        BRAIN_ROOT / "projects" / active_project / "ideas.md",
        Path(PROJECT_REGISTRY.get(active_project, {}).get("root", "")) / "context" / "ideas.md",
    ]:
        if ipath.exists() and ipath.is_file():
            itext = ipath.read_text(encoding="utf-8", errors="replace")
            raw_bytes_scanned += len(itext)
            ideas_sections.extend(chunk_markdown_sections(itext))
    top_ideas = retrieve_top_sections(
        ideas_sections, query_tokens, query_ngrams, active_project=active_project, top_k=5, max_section_chars=850
    )

    # 4. Selective Mistakes & Anti-Patterns Retrieval (Universal + Project-Local)
    mistakes_sections = []
    for mpath in [
        BRAIN_ROOT / "mistakes.md",
        BRAIN_ROOT / "projects" / active_project / "mistakes.md",
        Path(PROJECT_REGISTRY.get(active_project, {}).get("root", "")) / "context" / "mistakes.md",
    ]:
        if mpath.exists() and mpath.is_file():
            mtext = mpath.read_text(encoding="utf-8", errors="replace")
            raw_bytes_scanned += len(mtext)
            mistakes_sections.extend(chunk_markdown_sections(mtext))
    top_mistakes = retrieve_top_sections(
        mistakes_sections, query_tokens, query_ngrams, active_project=active_project, top_k=5, max_section_chars=850
    )

    # 5. Relevant Subsystem File Map
    file_map_slice = extract_relevant_file_map(active_project, query_tokens)

    # 6. Smart Code Slices (`--pack`)
    code_slices = []
    per_file_budget = max(3500, min(7500, (max_total_chars // 2) // max(1, len(pack_specs))))
    for spec in pack_specs:
        sliced = slice_code_file(spec, query_tokens=query_tokens, cwd=cwd, max_file_chars=per_file_budget)
        if sliced:
            raw_bytes_scanned += sliced["raw_chars"]
            if compress:
                compressed_content = compress_code_content(sliced["content"], sliced["path"])
                sliced["content"] = compressed_content
                sliced["mode"] += " [compressed]"
            code_slices.append(sliced)

    # 7. Shadow Session History (if continuing a multi-turn session)
    session_md = load_session_history(session_id)

    # Assemble High-Density Markdown Bundle
    parts = [
        "# ARGON SELECTIVE CONTEXT BUNDLE (SURGICAL RETRIEVAL — ZERO FULL-FILE DUMP)",
        f"- **Active Project Scope**: `{active_project}` (`{PROJECT_REGISTRY.get(active_project, {}).get('root', '')}`)",
        f"- **Extracted Query Signals**: `{', '.join( list(dict.fromkeys(query_tokens))[:14] )}`",
        f"- **Retrieval Method**: Hybrid BM25 + Character 3-Gram Cosine RRF + AST Code Slicing",
        "",
    ]

    if user_profile_md or hermes_memories:
        parts.append("## 1. Hermes Episodic Memory & User Dialectical Profile (Top RRF Matches)")
        if user_profile_md:
            parts.append("### User Non-Negotiables:")
            parts.append(user_profile_md)
        if hermes_memories:
            parts.append("### Recalled Past Milestones & Fixes:")
            for m in hermes_memories:
                parts.append(
                    f"- **[{m.get('category', 'memory').upper()}] {m.get('title', '')}** "
                    f"(RRF={m.get('rrf_score', 0):.4f}): {(m.get('content') or '')[:380]}"
                )
        parts.append("")

    if top_constraints:
        parts.append(f"## 2. Active Architectural Constraints (Top {len(top_constraints)} Relevant Sections)")
        for c in top_constraints:
            parts.append(c["body"])
            parts.append("")

    if top_ideas:
        parts.append(f"## 3. Relevant Architectural Decisions from `ideas.md` (Top {len(top_ideas)} of {len(ideas_sections)} Sections)")
        for idea in top_ideas:
            parts.append(idea["body"])
            parts.append("")

    if top_mistakes:
        parts.append(f"## 4. Relevant Past Mistakes & Anti-Patterns from `mistakes.md` (Top {len(top_mistakes)} of {len(mistakes_sections)} Sections)")
        for mk in top_mistakes:
            parts.append(mk["body"])
            parts.append("")

    if file_map_slice:
        parts.append(f"## 5. Relevant Project File Map (`{active_project}/file_map.md` Slice)")
        parts.append(file_map_slice)
        parts.append("")

    if session_md:
        parts.append(f"## 6. Prior Multi-Turn Session Context (`{session_id}`)")
        parts.append(session_md)
        parts.append("")

    if code_slices:
        parts.append(f"## 7. Targeted Code Slices ({len(code_slices)} Files — AST & Keyword Windowed)")
        for cs in code_slices:
            parts.append(f"### File: `{cs['path']}` ({cs['mode']})")
            parts.append("```")
            parts.append(cs["content"])
            parts.append("```")
            parts.append("")

    bundle_text = "\n".join(parts)
    if compress:
        bundle_text = re.sub(r"\n{3,}", "\n\n", bundle_text)

    if len(bundle_text) > max_total_chars:
        bundle_text = bundle_text[:max_total_chars].rsplit("\n", 1)[0] + "\n\n...[Bundle capped at max_total_chars budget]...\n"

    # Enforce 2-layer secret redaction (regex + exact .env* values) before writing bundle
    full_sync_scripts = BRAIN_ROOT / ".agents" / "skills" / "full-sync" / "scripts"
    if str(full_sync_scripts) not in sys.path:
        sys.path.insert(0, str(full_sync_scripts))
    try:
        import offload_context_compiler as occ
        proj_root = Path(PROJECT_REGISTRY.get(active_project, {}).get("root", str(BRAIN_ROOT)))
        bundle_text, _ = occ.redact_two_layer(bundle_text, roots=[proj_root, BRAIN_ROOT])
    except Exception:
        pass

    reduction_pct = (
        round((1.0 - (len(bundle_text) / max(1, raw_bytes_scanned))) * 100.0, 1)
        if raw_bytes_scanned > len(bundle_text)
        else 0.0
    )
    compress_tag = " (Compressed)" if compress else ""
    header_stats = (
        f"- **Compression Telemetry{compress_tag}**: Scanned `{raw_bytes_scanned:,}` chars across ledgers/code -> "
        f"Packed `{len(bundle_text):,}` chars (`{reduction_pct}%` noise reduction)\n"
    )
    bundle_text = bundle_text.replace(
        "- **Retrieval Method**: Hybrid BM25 + Character 3-Gram Cosine RRF + AST Code Slicing\n",
        "- **Retrieval Method**: Hybrid BM25 + Character 3-Gram Cosine RRF + AST Code Slicing\n" + header_stats,
        1,
    )

    if not output_path:
        out_dir = Path(cwd or os.getcwd()) / "temp_read"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "argon_context_bundle.md"
    else:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)

    out_file.write_text(bundle_text, encoding="utf-8")

    telemetry = {
        "active_project": active_project,
        "bundle_path": str(out_file.resolve()),
        "raw_chars_scanned": raw_bytes_scanned,
        "bundle_chars": len(bundle_text),
        "noise_reduction_pct": reduction_pct,
        "compressed": compress,
        "hermes_memories_count": len(hermes_memories),
        "ideas_selected": f"{len(top_ideas)}/{len(ideas_sections)}",
        "mistakes_selected": f"{len(top_mistakes)}/{len(mistakes_sections)}",
        "code_slices_count": len(code_slices),
    }
    return str(out_file.resolve()), telemetry


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Selective Context Packer for Argon Brain")
    p.add_argument("prompt", help="Query or architectural prompt for Argon")
    p.add_argument("--pack", "-p", nargs="*", default=[], help="Code files, line slices (file.py:10-50), or symbols (file.py#Func)")
    p.add_argument("--project", default=None, help="Explicit project name override")
    p.add_argument("--session-id", default=None, help="Optional multi-turn session ID")
    p.add_argument("--output", "-o", default=None, help="Custom output bundle path")
    p.add_argument("--max-chars", type=int, default=24000, help="Hard character budget for bundle")
    p.add_argument("--compress", "-c", action="store_true", help="Compress code & text context by stripping verbose comments/whitespace and extracting symbol outlines (repomix-style outline)")
    args = p.parse_args()

    bpath, stats = build_selective_context_bundle(
        prompt=args.prompt,
        pack_specs=args.pack,
        explicit_project=args.project,
        session_id=args.session_id,
        output_path=args.output,
        max_total_chars=args.max_chars,
        compress=args.compress,
    )
    print(json.dumps(stats, indent=2))
