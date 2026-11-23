#!/usr/bin/env python3
"""offload_context_compiler.py - 2-Layer Secret Redaction & Incremental Offload Context Compiler.

Builds <project>/context/offload_context.md in <350ms on incremental hits using
<project>/context/.offload_ast_cache.json (mtime+size keyed AST skeletons for Python/TS/JS)
with cache-stable prefix ordering for high prompt cache reuse.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LAYER1_REGEX_RULES: List[Tuple[re.Pattern[str], str]] = [
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"gh[pousr]_[a-zA-Z0-9]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"github_pat_[a-zA-Z0-9_]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{35}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_KEY]"),
    (re.compile(r"eyJ[a-zA-Z0-9_-]{10,}\.eyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}"), "[REDACTED_JWT]"),
    (re.compile(r"(?i)\bbearer\s+[a-zA-Z0-9_\-\.]{20,}"), "Bearer [REDACTED_TOKEN]"),
    (re.compile(r"(?i)(?:postgres|postgresql|mysql|mongodb(?:\+srv)?|redis)://[^:\s]+:[^@\s]+@"), "[REDACTED_DB_URI]://"),
    (
        re.compile(r'(?i)\b(password|passwd|secret|api[_-]?key|access[_-]?token|private[_-]?key|client[_-]?secret)\s*[:=]\s*["\']?[^"\'\s\n]{6,}["\']?'),
        r"\1: [REDACTED]",
    ),
]

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".next",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    "temp_read",
    ".worktrees",
}

TS_JS_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?(function|class|interface|type|const|enum)\s+([A-Za-z0-9_$]+)",
    re.MULTILINE,
)


def collect_env_secrets(roots: Optional[List[Path]] = None, min_len: int = 8) -> List[str]:
    """Loads exact secret values (len >= min_len) from .env* files into memory only for scrubbing."""
    search_roots = list(roots or [Path(r"./")])
    secrets: set[str] = set()
    for root in search_roots:
        if not root or not root.exists():
            continue
        for p in root.glob(".env*"):
            if not p.is_file():
                continue
            try:
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    _, val = s.split("=", 1)
                    val = val.strip().strip("\"'")
                    if len(val) >= min_len and val.lower() not in ("localhost", "127.0.0.1", "development", "production"):
                        secrets.add(val)
            except Exception:
                continue
    # Longest first so partial substrings don't leak leftovers
    return sorted(secrets, key=len, reverse=True)


def redact_two_layer(text: str, roots: Optional[List[Path]] = None) -> Tuple[str, int]:
    """Applies Layer 1 regex redaction + Layer 2 exact .env* literal value scrubbing."""
    if not text:
        return "", 0
    total_hits = 0
    out = text
    for pattern, repl in LAYER1_REGEX_RULES:
        out, n = pattern.subn(repl, out)
        total_hits += n

    for secret in collect_env_secrets(roots):
        if secret in out:
            occurrences = out.count(secret)
            out = out.replace(secret, "[REDACTED_ENV_SECRET]")
            total_hits += occurrences
    return out, total_hits


def _extract_python_symbols(path: Path) -> List[str]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(src)
    except Exception:
        return []
    symbols: List[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith("_")]
            m_str = f" ({', '.join(methods[:6])})" if methods else ""
            symbols.append(f"class {node.name}{m_str}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            args = [a.arg for a in node.args.args[:5] if a.arg != "self"]
            symbols.append(f"def {node.name}({', '.join(args)})")
    return symbols[:18]


def _extract_ts_symbols(path: Path) -> List[str]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    matches = TS_JS_EXPORT_RE.findall(src)
    return [f"{kind} {name}" for kind, name in matches[:18]]


def _iter_source_files(project_root: Path, full: bool = False) -> List[Path]:
    exts = {".py", ".ts", ".tsx", ".js", ".jsx"}
    found: List[Path] = []
    for dirpath, dirnames, filenames in os.walk(project_root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not (not full and d.startswith(".") and d != ".agents"))
        for fname in sorted(filenames):
            p = Path(dirpath) / fname
            if p.suffix.lower() in exts:
                found.append(p)
    return found


def _read_tail_lines(path: Path, max_lines: int = 25) -> str:
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _git_volatile_tail(project_root: Path) -> str:
    parts: List[str] = []
    try:
        st = subprocess.run(["git", "-C", str(project_root), "status", "--short"], capture_output=True, text=True, timeout=3)
        if st.returncode == 0 and st.stdout.strip():
            parts.append("### Working Tree Status\n```text\n" + "\n".join(st.stdout.strip().splitlines()[:25]) + "\n```")
    except Exception:
        pass
    try:
        lg = subprocess.run(["git", "-C", str(project_root), "log", "-n", "5", "--oneline"], capture_output=True, text=True, timeout=3)
        if lg.returncode == 0 and lg.stdout.strip():
            parts.append("### Recent Commits\n```text\n" + lg.stdout.strip() + "\n```")
    except Exception:
        pass
    return "\n\n".join(parts)


def _atomic_write_text(path: Path, text: str) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def compile_offload_context(project_root: Path, full: bool = False, dry_run: bool = False) -> Tuple[Path, Dict[str, Any]]:
    """Incrementally compiles <project_root>/context/offload_context.md in cache-stable prefix order."""
    t0 = time.perf_counter()
    root = Path(project_root).resolve()
    ctx_dir = root / "context"
    cache_path = ctx_dir / ".offload_ast_cache.json"
    out_path = ctx_dir / "offload_context.md"

    cache: Dict[str, Any] = {}
    if not full and cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    eligible = _iter_source_files(root, full=full)
    files = eligible if full else eligible[:180]
    omitted_files = [path.relative_to(root).as_posix() for path in eligible[len(files):]]
    new_cache: Dict[str, Any] = {}
    skeleton_lines: List[str] = []
    cache_hits = 0
    cache_misses = 0

    for fp in files:
        try:
            stat = fp.stat()
        except OSError:
            continue
        rel = fp.relative_to(root).as_posix()
        prev = cache.get(rel)
        if prev and prev.get("mtime_ns") == stat.st_mtime_ns and prev.get("size") == stat.st_size:
            syms = prev.get("symbols", [])
            cache_hits += 1
        else:
            syms = _extract_python_symbols(fp) if fp.suffix.lower() == ".py" else _extract_ts_symbols(fp)
            cache_misses += 1
        new_cache[rel] = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size, "symbols": syms}
        if syms:
            if len(skeleton_lines) < 120:
                skeleton_lines.append(f"- `{rel}`: " + "; ".join(syms[:10]))
            else:
                omitted_files.append(rel)

    # Cache-stable prefix order: (1) Identity & Constraints, (2) File Map & AST Skeletons, (3) Architecture/Ideas/Mistakes, (4) Volatile Tail
    constraints_tail = _read_tail_lines(root / "constraints.md", 30) or _read_tail_lines(root / "context" / "constraints.md", 30)
    ideas_tail = _read_tail_lines(root / "ideas.md", 25) or _read_tail_lines(root / "context" / "ideas.md", 25)
    mistakes_tail = _read_tail_lines(root / "mistakes.md", 25) or _read_tail_lines(root / "context" / "mistakes.md", 25)
    file_map_preview = _read_tail_lines(root / "file_map.md", 35)
    volatile_tail = _git_volatile_tail(root)

    sections = [
        f"# Compiled Offload Context :: {root.name}",
        "## 1. Project Identity & Active Constraints\n" + (constraints_tail or "_No constraints excerpt found._"),
        "## 2. File Map & AST Symbol Skeletons\n"
        + (f"### File Map Excerpt\n{file_map_preview}\n\n" if file_map_preview else "")
        + ("\n".join(skeleton_lines) if skeleton_lines else "_No exported symbols extracted._"),
        "## 3. Recent Ideas & Mistakes\n"
        + (f"### Ideas\n{ideas_tail}\n\n" if ideas_tail else "")
        + (f"### Mistakes\n{mistakes_tail}\n" if mistakes_tail else ""),
        "## 4. Volatile Git State\n" + (volatile_tail or "_Clean / non-git workspace._"),
        "## 5. Compilation Metadata\n"
        + f"Mode: {'FULL' if full else 'INCREMENTAL'} | Source Files Scanned: {len(files)}"
        + f" | Omitted by budget: {len(omitted_files)}"
        + ("\n\n" + "\n".join(f"- `{path}`" for path in sorted(omitted_files)[:25]) if omitted_files else "")
        + (f"\n- {len(omitted_files) - 25} more omitted paths" if len(omitted_files) > 25 else ""),
    ]
    raw_doc = "\n\n".join(sections).strip() + "\n"
    scrubbed_doc, redaction_count = redact_two_layer(raw_doc, roots=[root, Path(r"./")])

    if not dry_run:
        ctx_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(cache_path, json.dumps(new_cache))
        _atomic_write_text(out_path, scrubbed_doc)

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    stats = {
        "ok": True,
        "output_path": str(out_path),
        "elapsed_ms": elapsed_ms,
        "files_scanned": len(files),
        "files_omitted": len(omitted_files),
        "cache_hits": cache_hits,
        "cache_misses": cache_misses,
        "redaction_count": redaction_count,
        "bytes": len(scrubbed_doc.encode("utf-8")),
        "est_tokens": int(len(scrubbed_doc) / 3.8),
        "dry_run": dry_run,
    }
    return out_path, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile cache-stable, secret-scrubbed offload_context.md.")
    parser.add_argument("--project", default=".", help="Target project root directory")
    parser.add_argument("--full", action="store_true", help="Rebuild AST cache completely without incremental hits")
    parser.add_argument("--dry-run", action="store_true", help="Compute stats without writing files")
    parser.add_argument("--json", action="store_true", help="Output JSON telemetry")
    args = parser.parse_args()

    out_path, stats = compile_offload_context(Path(args.project), full=args.full, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print(f"[OffloadCompiler] Compiled {out_path} in {stats['elapsed_ms']}ms ({stats['files_scanned']} files, hits={stats['cache_hits']}, redactions={stats['redaction_count']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
