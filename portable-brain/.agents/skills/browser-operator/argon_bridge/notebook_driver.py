#!/usr/bin/env python3
"""notebook_driver.py - Gemini Notebooks / NotebookLM Pro Project RAG Bucket Driver.

Automates Gemini Notebooks (https://gemini.google.com/notebook/<UUID>) over the
local Argon Bridge (http://127.0.0.1:9229/command) with:
  - 2-layer secret redaction (regex patterns + exact .env* literal scrubbing)
  - <= 12 Markdown bundle packing to preserve 280+ of 300 NotebookLM source slots
  - Surface-scoped profile leases (surface="notebook", bucket="notebooklm")
  - 3-stage popup defense (popup_healer.dismiss_blocking_popups)
  - 4 Neon High thinking enforcement & quota-exhaustion share/clone failover
  - Verified share-clone across profiles with source_count parity checks
  - Ledger-tracked cleanup across owner and all cloned profiles
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

ARGON_BRIDGE_DIR = Path(__file__).resolve().parent
if str(ARGON_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(ARGON_BRIDGE_DIR))

import popup_healer  # noqa: E402
import profile_lock_manager  # noqa: E402

BRIDGE_URL = "http://127.0.0.1:9229"
COMMAND_URL = f"{BRIDGE_URL}/command"
SURFACE = "notebook"
BUCKET = "notebooklm"

CREATE_NOTEBOOK_URL = "https://gemini.google.com/notebooks/create"
NOTEBOOK_URL_TEMPLATE = "https://gemini.google.com/notebook/{notebook_id}"
NOTEBOOKLM_URL_TEMPLATE = "https://notebooklm.google.com/notebook/{notebook_id}"

DEFAULT_MAX_BUNDLES = 12
NOTEBOOKLM_MAX_SLOTS = 300
DEFAULT_AGENT_ID = f"notebook_driver_{os.getpid()}"

EXCLUDED_DIRS = frozenset({
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    "nb_bundles",
})

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".bmp", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".pyd", ".pyc", ".pyo", ".class", ".jar",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".mp3", ".mp4", ".wav", ".ogg", ".flac", ".avi", ".mov", ".mkv", ".webm",
    ".db", ".sqlite", ".sqlite3", ".bin", ".dat", ".npy", ".npz", ".pt", ".onnx",
})

PRIORITY_CONTEXT_NAMES = frozenset({
    "mistakes.md",
    "ideas.md",
    "constraints.md",
    "agents.md",
    "file_map.md",
    "project_map.md",
    "readme.md",
})

NOTEBOOK_UUID_RE = re.compile(r"/notebook/([A-Za-z0-9_-]{8,})")

# Layer 1 Regex Secret Patterns
_RE_SK_KEY = re.compile(r"\bsk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{12,}\b")
_RE_GOOGLE_KEY = re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")
_RE_BEARER = re.compile(r"(?i)\bBearer\s+(?!\[REDACTED)[A-Za-z0-9._~+/=-]{8,}")
_RE_KV_QUOTED = re.compile(
    r"(?im)(['\"]?\b(?:password|passwd|pwd|secret|api_key|apikey|client_secret|access_token|auth_token|private_key)\b['\"]?\s*[:=]\s*)(['\"])(?!\[REDACTED)([^'\"\r\n]{4,})\2"
)
_RE_KV_UNQUOTED = re.compile(
    r"(?im)(\b(?:password|passwd|pwd|secret|api_key|apikey|client_secret|access_token|auth_token|private_key)\b\s*[:=]\s*)(?!\[REDACTED|['\"])([^\s'\",;}{]{4,})"
)
_RE_URL_CREDS = re.compile(r"(https?://[^:\s/@]+:)(?!\[REDACTED)([^@\s/]{4,})(@)")


class NotebookDriverError(Exception):
    """Base error for notebook_driver failures."""


class BridgeCommandError(NotebookDriverError):
    """Raised when an Argon Bridge /command invocation fails."""


class QuotaExhaustedError(NotebookDriverError):
    """Raised when NotebookLM / Gemini Notebook hits quota exhaustion."""


class SourceCountMismatchError(NotebookDriverError):
    """Raised when a cloned notebook's source count does not match its owner."""


class LedgerError(NotebookDriverError):
    """Raised on missing or invalid notebook ledger entries."""


def _utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def extract_notebook_id(url_or_id: str) -> Optional[str]:
    """Extracts a Gemini Notebook ID from a URL or returns a bare ID as-is."""
    raw = (url_or_id or "").strip()
    if not raw:
        return None
    match = NOTEBOOK_UUID_RE.search(raw)
    if match:
        return match.group(1)
    if "/" not in raw and " " not in raw and len(raw) >= 6:
        return raw
    return None


def build_notebook_urls(notebook_id: str) -> Tuple[str, str]:
    """Returns (gemini_notebook_url, notebooklm_url) for a notebook ID."""
    return (
        NOTEBOOK_URL_TEMPLATE.format(notebook_id=notebook_id),
        NOTEBOOKLM_URL_TEMPLATE.format(notebook_id=notebook_id),
    )


# ---------------------------------------------------------------------------
# 2-Layer Secret Redaction
# ---------------------------------------------------------------------------

def is_env_filename(filename: str) -> bool:
    """Returns True if filename is an env secret file (.env, .env.local, etc.)."""
    lower = filename.lower()
    return lower == ".env" or lower.startswith(".env.")


def _parse_env_value(raw_val: str) -> str:
    val = raw_val.strip()
    if not val:
        return ""
    if (val.startswith('"') and val.endswith('"') and len(val) >= 2) or (
        val.startswith("'") and val.endswith("'") and len(val) >= 2
    ):
        return val[1:-1]
    if " #" in val:
        val = val.split(" #", 1)[0].strip()
    return val


def load_env_literals(project_root: Path, min_length: int = 8) -> List[str]:
    """Loads secret values (len >= min_length) into memory from .env* files under project_root."""
    root = Path(project_root)
    if not root.exists():
        return []

    literals: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        for fname in filenames:
            if not is_env_filename(fname):
                continue
            fpath = Path(dirpath) / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.startswith("export "):
                    stripped = stripped[7:].strip()
                if "=" not in stripped:
                    continue
                _, raw_val = stripped.split("=", 1)
                val = _parse_env_value(raw_val)
                if len(val) >= min_length:
                    literals.add(val)

    return sorted(literals, key=lambda s: (-len(s), s))


def redact_secrets(text: str, env_literals: Sequence[str] = ()) -> Tuple[str, int]:
    """Applies Layer 2 (.env* literal scrub) and Layer 1 (regex scrub) to text.

    Returns (scrubbed_text, total_replacements).
    """
    if not text:
        return text, 0

    scrubbed = text
    redactions = 0

    # Layer 2: Exact literal scrubbing from .env* values (longest first)
    for literal in env_literals:
        if literal and literal in scrubbed:
            occurrences = scrubbed.count(literal)
            scrubbed = scrubbed.replace(literal, "[REDACTED_ENV_SECRET]")
            redactions += occurrences

    # Layer 1: Regex patterns
    scrubbed, n = _RE_SK_KEY.subn("[REDACTED_SK_KEY]", scrubbed)
    redactions += n
    scrubbed, n = _RE_GOOGLE_KEY.subn("[REDACTED_GOOGLE_KEY]", scrubbed)
    redactions += n
    scrubbed, n = _RE_BEARER.subn("Bearer [REDACTED_TOKEN]", scrubbed)
    redactions += n
    scrubbed, n = _RE_KV_QUOTED.subn(r"\1\2[REDACTED_SECRET]\2", scrubbed)
    redactions += n
    scrubbed, n = _RE_KV_UNQUOTED.subn(r"\1[REDACTED_SECRET]", scrubbed)
    redactions += n
    scrubbed, n = _RE_URL_CREDS.subn(r"\1[REDACTED_SECRET]\3", scrubbed)
    redactions += n

    return scrubbed, redactions


# ---------------------------------------------------------------------------
# Project Packing (<= 12 Bundles)
# ---------------------------------------------------------------------------

def _is_binary_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(4096)
        return b"\x00" in chunk
    except OSError:
        return True


def _is_priority_context_file(rel_path: Path) -> bool:
    name_low = rel_path.name.lower()
    if name_low in PRIORITY_CONTEXT_NAMES:
        return True
    parts_low = {p.lower() for p in rel_path.parts}
    return "context" in parts_low or (".agents" in parts_low and "rules" in parts_low)


def _fence_lang(path: Path) -> str:
    ext = path.suffix.lower().lstrip(".")
    mapping = {
        "py": "python",
        "ts": "typescript",
        "tsx": "tsx",
        "js": "javascript",
        "jsx": "jsx",
        "md": "markdown",
        "json": "json",
        "yml": "yaml",
        "yaml": "yaml",
        "ps1": "powershell",
        "sh": "bash",
        "sql": "sql",
        "html": "html",
        "css": "css",
        "toml": "toml",
    }
    return mapping.get(ext, ext)


def collect_packable_files(
    project_root: Path,
    paths: Optional[Sequence[str]] = None,
    out_dir: Optional[Path] = None,
) -> List[Path]:
    """Discovers non-binary, non-.env* files under project_root (or explicit paths)."""
    root = Path(project_root).resolve()
    resolved_out = Path(out_dir).resolve() if out_dir else (root / "temp_read" / "nb_bundles").resolve()
    ledger_resolved = (root / "temp_read" / "notebook_ledger.json").resolve()

    candidates: List[Path] = []
    seen: set[Path] = set()

    def _maybe_add(fpath: Path) -> None:
        resolved = fpath.resolve()
        if resolved in seen or not resolved.is_file():
            return
        if resolved == ledger_resolved or resolved_out in resolved.parents:
            return
        if is_env_filename(resolved.name):
            return
        if any(part in EXCLUDED_DIRS for part in resolved.parts):
            return
        if _is_binary_file(resolved):
            return
        seen.add(resolved)
        candidates.append(resolved)

    targets: List[Path]
    if paths:
        targets = []
        for raw in paths:
            p = Path(raw)
            targets.append(p if p.is_absolute() else (root / p))
    else:
        targets = [root]

    for target in targets:
        if not target.exists():
            continue
        if target.is_file():
            _maybe_add(target)
        elif target.is_dir():
            for dirpath, dirnames, filenames in os.walk(target):
                current = Path(dirpath).resolve()
                if current == resolved_out or resolved_out in current.parents:
                    dirnames[:] = []
                    continue
                dirnames[:] = sorted(
                    d for d in dirnames
                    if d not in EXCLUDED_DIRS and (current / d).resolve() != resolved_out
                )
                for fname in sorted(filenames):
                    _maybe_add(current / fname)

    candidates.sort(key=lambda p: (0 if _is_priority_context_file(p.relative_to(root) if root in p.parents else p) else 1, str(p)))
    return candidates


def pack_project(
    project_path: str | Path,
    paths: Optional[Sequence[str]] = None,
    max_bundles: int = DEFAULT_MAX_BUNDLES,
    out_dir: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Packs scrubbed context and source files into <= max_bundles Markdown files."""
    if max_bundles < 1:
        raise ValueError("max_bundles must be >= 1")

    root = Path(project_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {root}")

    target_out = Path(out_dir).resolve() if out_dir else (root / "temp_read" / "nb_bundles")
    target_out.mkdir(parents=True, exist_ok=True)

    # Clear stale bundle_*.md files before writing fresh bundles
    for old_bundle in target_out.glob("bundle_*.md"):
        try:
            old_bundle.unlink()
        except OSError:
            pass

    env_literals = load_env_literals(root)
    files = collect_packable_files(root, paths=paths, out_dir=target_out)

    if not files:
        return {
            "ok": True,
            "project": str(root),
            "out_dir": str(target_out),
            "bundle_count": 0,
            "max_bundles": max_bundles,
            "remaining_slots": NOTEBOOKLM_MAX_SLOTS,
            "files_packed": 0,
            "redactions": 0,
            "bundles": [],
        }

    total_redactions = 0
    context_sections: List[Tuple[str, str, int]] = []
    source_sections: List[Tuple[str, str, int]] = []

    for fpath in files:
        try:
            rel = fpath.relative_to(root).as_posix()
        except ValueError:
            rel = fpath.name
        raw_text = fpath.read_text(encoding="utf-8", errors="replace")
        scrubbed, n_redacted = redact_secrets(raw_text, env_literals=env_literals)
        total_redactions += n_redacted

        lang = _fence_lang(fpath)
        fence = "````" if "```" in scrubbed else "```"
        section = f"## File: `{rel}`\n\n{fence}{lang}\n{scrubbed.rstrip()}\n{fence}\n"
        entry = (rel, section, len(section.encode("utf-8")))
        if _is_priority_context_file(Path(rel)):
            context_sections.append(entry)
        else:
            source_sections.append(entry)

    buckets: List[Dict[str, Any]] = []
    if context_sections and source_sections and max_bundles >= 2:
        buckets.append({
            "kind": "context",
            "files": [x[0] for x in context_sections],
            "sections": [x[1] for x in context_sections],
            "size": sum(x[2] for x in context_sections),
        })
        remaining_cap = max_bundles - 1
        src_bucket_count = min(remaining_cap, len(source_sections))
        src_buckets = [{"kind": "source", "files": [], "sections": [], "size": 0} for _ in range(src_bucket_count)]
        for rel, sec, sz in sorted(source_sections, key=lambda item: -item[2]):
            smallest = min(src_buckets, key=lambda b: b["size"])
            smallest["files"].append(rel)
            smallest["sections"].append(sec)
            smallest["size"] += sz
        buckets.extend(b for b in src_buckets if b["files"])
    else:
        all_sections = context_sections + source_sections
        bucket_count = min(max_bundles, len(all_sections))
        all_buckets = [{"kind": "mixed", "files": [], "sections": [], "size": 0} for _ in range(bucket_count)]
        for rel, sec, sz in sorted(all_sections, key=lambda item: -item[2]):
            smallest = min(all_buckets, key=lambda b: b["size"])
            smallest["files"].append(rel)
            smallest["sections"].append(sec)
            smallest["size"] += sz
        buckets.extend(b for b in all_buckets if b["files"])

    created_bundles: List[Dict[str, Any]] = []
    total_b = len(buckets)
    for idx, bucket in enumerate(buckets, start=1):
        fname = f"bundle_{idx:02d}_{bucket['kind']}.md"
        bpath = target_out / fname
        toc = "\n".join(f"- `{f}`" for f in bucket["files"])
        header = (
            f"# Project RAG Bundle {idx}/{total_b} ({bucket['kind']})\n\n"
            f"- **Project**: `{root.name}`\n"
            f"- **Files ({len(bucket['files'])})**:\n{toc}\n\n---\n\n"
        )
        body = header + "\n".join(bucket["sections"])
        bpath.write_text(body, encoding="utf-8")
        created_bundles.append({
            "path": str(bpath),
            "filename": fname,
            "kind": bucket["kind"],
            "file_count": len(bucket["files"]),
            "files": bucket["files"],
            "bytes": bpath.stat().st_size,
        })

    return {
        "ok": True,
        "project": str(root),
        "out_dir": str(target_out),
        "bundle_count": len(created_bundles),
        "max_bundles": max_bundles,
        "remaining_slots": NOTEBOOKLM_MAX_SLOTS - len(created_bundles),
        "files_packed": len(files),
        "redactions": total_redactions,
        "bundles": created_bundles,
    }


# ---------------------------------------------------------------------------
# Notebook Ledger CRUD
# ---------------------------------------------------------------------------

def get_ledger_path(project_path: str | Path) -> Path:
    return Path(project_path).resolve() / "temp_read" / "notebook_ledger.json"


def load_ledger(ledger_path: Path) -> Dict[str, Any]:
    if ledger_path.exists():
        try:
            raw = json.loads(ledger_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                notebooks = raw.get("notebooks")
                if isinstance(notebooks, dict):
                    return {"notebooks": notebooks}
        except Exception:
            pass
    return {"notebooks": {}}


def save_ledger(ledger_path: Path, ledger: Dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")


def upsert_notebook_entry(ledger_path: Path, entry: Dict[str, Any]) -> Dict[str, Any]:
    ledger = load_ledger(ledger_path)
    nb_id = entry["notebook_id"]
    ledger["notebooks"][nb_id] = entry
    save_ledger(ledger_path, ledger)
    return entry


def get_notebook_entry(ledger_path: Path, notebook_id_or_url: str) -> Dict[str, Any]:
    nb_id = extract_notebook_id(notebook_id_or_url) or notebook_id_or_url
    ledger = load_ledger(ledger_path)
    entry = ledger["notebooks"].get(nb_id)
    if not isinstance(entry, dict):
        raise LedgerError(f"Notebook '{nb_id}' not found in ledger: {ledger_path}")
    return entry


def verify_clone_source_count(owner_source_count: Optional[int], clone_source_count: Optional[int]) -> Tuple[bool, str]:
    """Validates that a cloned notebook matches the owner's source count."""
    if owner_source_count is None:
        return True, "owner_source_count_unknown"
    if clone_source_count is None:
        return False, f"Could not verify cloned source count (expected {owner_source_count})."
    if int(clone_source_count) != int(owner_source_count):
        return False, (
            f"Source count mismatch after clone: owner={owner_source_count}, clone={clone_source_count}."
        )
    return True, "ok"


# ---------------------------------------------------------------------------
# Argon Bridge REST Client (/command)
# ---------------------------------------------------------------------------

def _default_http_post(url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 5.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise BridgeCommandError(f"Bridge unreachable at {url}: {exc}") from exc
    except Exception as exc:
        raise BridgeCommandError(f"Bridge HTTP call failed: {exc}") from exc


@dataclass
class BridgeClient:
    """Thin client for Argon Bridge http://127.0.0.1:9229/command."""

    bridge_url: str = BRIDGE_URL
    post_fn: Callable[[str, Dict[str, Any], float], Dict[str, Any]] = _default_http_post

    @property
    def command_url(self) -> str:
        return f"{self.bridge_url.rstrip('/')}/command"

    def command(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        profile: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "action": action,
            "params": params or {},
            "timeout": timeout,
        }
        if profile:
            payload["profile"] = profile
        res = self.post_fn(self.command_url, payload, timeout)
        if not isinstance(res, dict):
            raise BridgeCommandError(f"Invalid bridge response for {action}: {res!r}")
        if not res.get("ok"):
            raise BridgeCommandError(res.get("error") or f"Bridge command '{action}' failed: {res}")
        return res

    def open_tab(self, url: str, profile: Optional[str] = None, active: bool = True, timeout: float = 30.0) -> int:
        res = self.command("OPEN_TAB", {"url": url, "active": active}, profile=profile, timeout=timeout)
        tab_id = res.get("tabId")
        if tab_id is None:
            raise BridgeCommandError(f"OPEN_TAB did not return tabId: {res}")
        return int(tab_id)

    def list_tabs(self, profile: Optional[str] = None, timeout: float = 15.0) -> List[Dict[str, Any]]:
        res = self.command("LIST_TABS", {}, profile=profile, timeout=timeout)
        tabs = res.get("tabs", [])
        return tabs if isinstance(tabs, list) else []

    def eval_dom(self, tab_id: int, code: str, profile: Optional[str] = None, timeout: float = 30.0) -> Any:
        res = self.command("EVAL_DOM", {"tabId": tab_id, "code": code}, profile=profile, timeout=timeout)
        return res.get("result")

    def eval_dom_raw(self, tab_id: int, code: str, profile: Optional[str] = None, timeout: float = 30.0) -> Dict[str, Any]:
        return self.command("EVAL_DOM", {"tabId": tab_id, "code": code}, profile=profile, timeout=timeout)

    def cdp_command(
        self,
        tab_id: int,
        method: str,
        cdp_params: Optional[Dict[str, Any]] = None,
        profile: Optional[str] = None,
        timeout: float = 30.0,
    ) -> Any:
        res = self.command(
            "CDP_COMMAND",
            {"tabId": tab_id, "method": method, "params": cdp_params or {}},
            profile=profile,
            timeout=timeout,
        )
        return res.get("result")

    def close_tab(self, tab_id: int, profile: Optional[str] = None, timeout: float = 15.0) -> bool:
        try:
            self.command("CLOSE_TAB", {"tabId": tab_id}, profile=profile, timeout=timeout)
            return True
        except BridgeCommandError:
            return False

    def capture_screenshot(self, tab_id: int, out_path: str, profile: Optional[str] = None) -> None:
        import base64

        res = self.cdp_command(tab_id, "Page.captureScreenshot", {"format": "png"}, profile=profile, timeout=15.0)
        if isinstance(res, dict) and res.get("data"):
            Path(out_path).write_bytes(base64.b64decode(res["data"]))


# ---------------------------------------------------------------------------
# DOM Snippets (Gemini Notebooks UI)
# ---------------------------------------------------------------------------

_JS_GET_NOTEBOOK_META = r"""(() => {
    const href = window.location.href || '';
    const titleEl = document.querySelector('input[aria-label*="title" i], [data-test-id="notebook-title"], .notebook-title, h1');
    const title = titleEl ? (titleEl.value !== undefined ? titleEl.value : titleEl.innerText || titleEl.textContent || '').trim() : document.title;
    const chips = Array.from(document.querySelectorAll('gem-source-list-chip, GEM-SOURCE-LIST-CHIP, .source-item, [data-test-id*="source-item"]'));
    let sourceCount = 0;
    const countBadge = document.querySelector('[data-test-id="source-count"], .source-count, .sources-header');
    if (countBadge) {
        const m = (countBadge.innerText || '').match(/(\d+)\s*sources?/i);
        if (m) sourceCount = parseInt(m[1], 10);
    }
    if (!sourceCount && chips.length) {
        sourceCount = chips.filter(c => !(c.getAttribute('aria-label') || '').toLowerCase().includes('add source')).length;
    }
    return { href, title, sourceCount };
})()"""

_JS_CLICK_ADD_SOURCES = r"""(() => {
    const sels = [
        'GEM-SOURCE-LIST-CHIP[aria-label="Add sources"]',
        'gem-source-list-chip[aria-label="Add sources"]',
        'button[aria-label="Add sources"]',
        '[aria-label*="Add sources" i]',
    ];
    for (const sel of sels) {
        const el = document.querySelector(sel);
        if (el) {
            el.click();
            const btn = el.querySelector('button, [role="button"]');
            if (btn) btn.click();
            return { clicked: true, selector: sel };
        }
    }
    const btns = Array.from(document.querySelectorAll('button, [role="button"], gem-source-list-chip'));
    const match = btns.find(b => ((b.getAttribute('aria-label') || b.innerText || '').toLowerCase().includes('add source')));
    if (match) {
        match.click();
        return { clicked: true, selector: 'text_match' };
    }
    return { clicked: false, error: 'Add sources chip not found' };
})()"""

_JS_CLICK_UPLOAD_FILE_OPTION = r"""(() => {
    const input = document.querySelector('input[type="file"]');
    if (input) return { ready: true, hasInput: true };
    const candidates = Array.from(document.querySelectorAll('button, [role="menuitem"], [role="button"], .upload-option'));
    const uploadBtn = candidates.find(el => {
        const t = ((el.getAttribute('aria-label') || el.innerText || '').trim().toLowerCase());
        return t.includes('upload') || t.includes('computer') || t.includes('choose file') || t.includes('local file');
    });
    if (uploadBtn) {
        uploadBtn.click();
        return { ready: true, clickedUploadOption: true, hasInput: Boolean(document.querySelector('input[type="file"]')) };
    }
    return { ready: false, hasInput: false };
})()"""

_JS_TRIGGER_DISCOVER_WEB_TEMPLATE = r"""((queryText) => {
    const candidates = Array.from(document.querySelectorAll('button, [role="menuitem"], [role="button"], a'));
    const discoverBtn = candidates.find(el => {
        const t = ((el.getAttribute('aria-label') || el.innerText || '').trim().toLowerCase());
        return t.includes('discover web') || t.includes('discover source') || t.includes('web source');
    });
    if (discoverBtn) {
        discoverBtn.click();
    }
    const input = document.querySelector('textarea[placeholder*="discover" i], input[placeholder*="discover" i], textarea[aria-label*="discover" i], input[aria-label*="search" i], mat-dialog-container textarea, mat-dialog-container input[type="text"]');
    if (!input) {
        return { ok: false, error: 'Discover web sources query input not found' };
    }
    const proto = input.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
    if (setter) setter.call(input, queryText);
    else input.value = queryText;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));

    const submitBtns = Array.from(document.querySelectorAll('mat-dialog-container button, [role="dialog"] button, button'));
    const submit = submitBtns.find(b => {
        if (b.disabled) return false;
        const t = ((b.getAttribute('aria-label') || b.innerText || '').trim().toLowerCase());
        return t === 'submit' || t === 'search' || t === 'discover' || t.includes('discover');
    });
    if (submit) {
        submit.click();
        return { ok: true, submitted: true, query: queryText };
    }
    return { ok: false, error: 'Discover submit button not found' };
})"""

_JS_IMPORT_DISCOVERED_SOURCES = r"""(() => {
    const btns = Array.from(document.querySelectorAll('mat-dialog-container button, [role="dialog"] button, button'));
    const imp = btns.find(b => {
        if (b.disabled) return false;
        const t = ((b.getAttribute('aria-label') || b.innerText || '').trim().toLowerCase());
        return t.startsWith('import') || t.includes('add selected') || t.includes('add sources');
    });
    if (imp) {
        imp.click();
        return { imported: true };
    }
    return { imported: false };
})()"""

_JS_ENSURE_4_NEON_HIGH = r"""(() => {
    const switchBtn = document.querySelector('button.input-area-switch, [data-test-id="model-selector"], button[aria-label*="model" i]');
    const bodyText = (switchBtn ? (switchBtn.innerText || switchBtn.getAttribute('aria-label') || '') : '').toLowerCase();
    const isNeon = bodyText.includes('4 neon') || bodyText.includes('neon');
    const isHigh = bodyText.includes('high') || Boolean(document.querySelector('[aria-pressed="true"][aria-label*="High" i], [aria-checked="true"][aria-label*="High" i]'));
    if (isNeon && isHigh) {
        return { ok: true, model: '4 Neon', thinking: 'High', switched: false };
    }
    if (switchBtn) switchBtn.click();
    const items = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], mat-option, button'));
    const neonItem = items.find(el => ((el.innerText || el.getAttribute('aria-label') || '').toLowerCase().includes('4 neon')));
    if (neonItem) neonItem.click();
    const highItem = Array.from(document.querySelectorAll('[role="menuitem"], [role="option"], button')).find(
        el => ((el.innerText || el.getAttribute('aria-label') || '').toLowerCase().includes('high'))
    );
    if (highItem) highItem.click();
    const afterText = (switchBtn ? (switchBtn.innerText || switchBtn.getAttribute('aria-label') || '') : '').toLowerCase();
    return {
        ok: afterText.includes('neon') || Boolean(neonItem),
        model: '4 Neon',
        thinking: 'High',
        switched: true
    };
})()"""

_JS_SUBMIT_NOTEBOOK_QUERY_TEMPLATE = r"""((promptText) => {
    const editor = document.querySelector('.ql-editor[contenteditable="true"], [role="textbox"][contenteditable="true"], textarea[aria-label*="prompt" i], textarea');
    if (!editor) return { ok: false, error: 'Notebook prompt editor not found' };
    editor.focus();
    if (editor.tagName === 'TEXTAREA') {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
        if (setter) setter.call(editor, promptText);
        else editor.value = promptText;
        editor.dispatchEvent(new Event('input', { bubbles: true }));
    } else {
        const p = editor.querySelector('p') || document.createElement('p');
        p.textContent = promptText;
        if (!p.parentElement) editor.appendChild(p);
        editor.dispatchEvent(new Event('input', { bubbles: true }));
    }
    const sendBtn = document.querySelector('button.send-button, button[aria-label*="Send" i], button[data-test-id="send-button"]');
    if (!sendBtn || sendBtn.disabled) {
        return { ok: false, error: 'Send button missing or disabled' };
    }
    sendBtn.click();
    return { ok: true, sent: true };
})"""

_JS_HARVEST_NOTEBOOK_RESPONSE = r"""(() => {
    const pageTxt = (document.body?.innerText || '').toLowerCase();
    const quotaHit = (
        pageTxt.includes('quota') && pageTxt.includes('exceeded')
    ) || pageTxt.includes('daily limit') || pageTxt.includes('reached your limit') || pageTxt.includes('rate limit');
    const responses = Array.from(document.querySelectorAll('model-response, .model-response-text, .response-container, [data-test-id="model-response"]'));
    const last = responses.length ? responses[responses.length - 1] : null;
    const text = last ? (last.innerText || last.textContent || '').trim() : '';
    const cites = last ? Array.from(last.querySelectorAll('a[href], button.citation-chip, [data-citation], .citation')).map(c => ({
        label: (c.innerText || c.getAttribute('aria-label') || '').trim(),
        href: c.getAttribute('href') || ''
    })).filter(c => c.label || c.href) : [];
    return { quota_exhausted: quotaHit, text, citations: cites };
})()"""

_JS_SHARE_AND_ALLOW_COPY = r"""(() => {
    const shareBtn = document.querySelector('button[aria-label*="Share" i], [data-test-id="share-button"]');
    if (shareBtn) shareBtn.click();
    const opts = Array.from(document.querySelectorAll('mat-option, [role="option"], [role="menuitem"], button, label, input[type="checkbox"]'));
    for (const el of opts) {
        const t = ((el.getAttribute('aria-label') || el.innerText || '').toLowerCase());
        if (t.includes('anyone with') && t.includes('link')) {
            el.click();
        }
        if (t.includes('allow copy') || t.includes('allow viewers to copy')) {
            const checked = el.checked || el.getAttribute('aria-checked') === 'true';
            if (!checked) el.click();
        }
    }
    const linkInput = document.querySelector('input[readonly][value*="gemini.google.com"], input[value*="/notebook/"], [data-test-id="share-link"]');
    const shareUrl = linkInput ? (linkInput.value || linkInput.innerText || '').trim() : window.location.href;
    const copyBtn = Array.from(document.querySelectorAll('button')).find(b => ((b.innerText || b.getAttribute('aria-label') || '').toLowerCase().includes('copy link')));
    if (copyBtn) copyBtn.click();
    return { ok: Boolean(shareUrl), share_url: shareUrl };
})()"""

_JS_CLONE_SHARED_NOTEBOOK = r"""(() => {
    const btns = Array.from(document.querySelectorAll('button, [role="button"], a'));
    const copyBtn = btns.find(b => {
        const t = ((b.getAttribute('aria-label') || b.innerText || '').trim().toLowerCase());
        return t.includes('copy notebook') || t.includes('duplicate') || t.includes('make a copy');
    });
    if (!copyBtn) return { ok: false, error: 'Copy/Duplicate notebook button not found' };
    copyBtn.click();
    return { ok: true, clicked: true };
})()"""

_JS_DELETE_NOTEBOOK = r"""(() => {
    const settingsBtn = document.querySelector('button[aria-label="Notebook settings"], button[aria-label*="Notebook settings" i]');
    if (!settingsBtn) return { ok: false, step: 'settings', error: 'Notebook settings button not found' };
    settingsBtn.click();

    const delBtn = document.querySelector('project-delete-button, .project-delete-button, [data-test-id="project-delete-button"], button[aria-label*="Delete notebook" i]')
        || Array.from(document.querySelectorAll('button, [role="menuitem"]')).find(el => ((el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase().includes('delete')));
    if (!delBtn) return { ok: false, step: 'delete_button', error: 'project-delete-button not found' };
    delBtn.click();

    const confirmBtn = Array.from(document.querySelectorAll('mat-dialog-container button, [role="dialog"] button, button')).find(el => {
        const t = ((el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase());
        return t === 'delete' || t === 'confirm' || t === 'delete notebook';
    });
    if (!confirmBtn) return { ok: false, step: 'confirm', error: 'Confirm delete button not found' };
    confirmBtn.click();
    return { ok: true, deleted: true };
})()"""


# ---------------------------------------------------------------------------
# NotebookDriver Orchestrator (Injectable for Offline Unit Tests)
# ---------------------------------------------------------------------------

class NotebookDriver:
    """High-level driver for Gemini Notebooks / NotebookLM Pro RAG Buckets."""

    def __init__(
        self,
        bridge: Optional[BridgeClient] = None,
        lease_acquire_fn: Optional[Callable[..., Tuple[Optional[str], Optional[str]]]] = None,
        lease_release_fn: Optional[Callable[..., bool]] = None,
        cooldown_fn: Optional[Callable[..., None]] = None,
        popup_dismiss_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        liveness_check_fn: Optional[Callable[[Callable[[str], Any]], Dict[str, Any]]] = None,
        sleep_fn: Callable[[float], None] = time.sleep,
        agent_id: str = DEFAULT_AGENT_ID,
    ) -> None:
        self.bridge = bridge or BridgeClient()
        self.lease_acquire_fn = lease_acquire_fn or profile_lock_manager.acquire_profile_lease
        self.lease_release_fn = lease_release_fn or profile_lock_manager.release_profile_lease
        self.cooldown_fn = cooldown_fn or profile_lock_manager.mark_bucket_cooldown
        self.popup_dismiss_fn = popup_dismiss_fn or popup_healer.dismiss_blocking_popups
        self.liveness_check_fn = liveness_check_fn or popup_healer.check_liveness
        self.sleep_fn = sleep_fn
        self.agent_id = agent_id

    def _acquire_notebook_lease(self, preferred_profile: Optional[str], task: str) -> str:
        prof, err = self.lease_acquire_fn(
            agent_id=self.agent_id,
            preferred_profile=preferred_profile,
            task=task,
            surface=SURFACE,
            bucket=BUCKET,
        )
        if not prof:
            raise NotebookDriverError(err or "Failed to acquire notebook profile lease.")
        return prof

    def _dismiss_popups(self, tab_id: int, profile: str, project_path: Path) -> Dict[str, Any]:
        return self.popup_dismiss_fn(
            eval_fn=lambda js: self.bridge.eval_dom_raw(tab_id, js, profile=profile),
            screenshot_fn=lambda out: self.bridge.capture_screenshot(tab_id, out, profile=profile),
            surface=SURFACE,
            project_root=project_path,
        )

    def _wait_for_notebook_url(self, tab_id: int, profile: str, timeout_s: float = 20.0) -> Tuple[str, str]:
        deadline = time.time() + timeout_s
        while time.time() <= deadline:
            tabs = self.bridge.list_tabs(profile=profile)
            for t in tabs:
                if int(t.get("id", -1)) == int(tab_id):
                    nb_id = extract_notebook_id(t.get("url", ""))
                    if nb_id:
                        return nb_id, t["url"]
            meta = self.bridge.eval_dom(tab_id, _JS_GET_NOTEBOOK_META, profile=profile)
            if isinstance(meta, dict):
                nb_id = extract_notebook_id(meta.get("href", ""))
                if nb_id:
                    return nb_id, meta["href"]
            self.sleep_fn(0.5)
        raise BridgeCommandError(f"Timed out waiting for /notebook/<UUID> redirect on tab {tab_id}.")

    def _read_meta(self, tab_id: int, profile: str) -> Dict[str, Any]:
        meta = self.bridge.eval_dom(tab_id, _JS_GET_NOTEBOOK_META, profile=profile)
        return meta if isinstance(meta, dict) else {}

    def create(
        self,
        title: str,
        project_path: str | Path,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a new Gemini Notebook and registers it in notebook_ledger.json."""
        project_root = Path(project_path).resolve()
        ledger_path = get_ledger_path(project_root)
        leased_profile = self._acquire_notebook_lease(profile, task=f"create:{title}")
        tab_id: Optional[int] = None
        try:
            tab_id = self.bridge.open_tab(CREATE_NOTEBOOK_URL, profile=leased_profile, active=True)
            nb_id, resolved_url = self._wait_for_notebook_url(tab_id, profile=leased_profile)
            self._dismiss_popups(tab_id, leased_profile, project_root)

            set_title_js = f"""(() => {{
                const inp = document.querySelector('input[aria-label*="title" i], [data-test-id="notebook-title"] input, [contenteditable="true"][aria-label*="title" i]');
                if (!inp) return {{ updated: false }};
                const title = {json.dumps(title)};
                if (inp.tagName === 'INPUT') {{
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                    if (setter) setter.call(inp, title);
                    else inp.value = title;
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    inp.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }} else {{
                    inp.textContent = title;
                    inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                }}
                return {{ updated: true }};
            }})()"""
            self.bridge.eval_dom(tab_id, set_title_js, profile=leased_profile)

            gemini_url, nblm_url = build_notebook_urls(nb_id)
            entry = {
                "notebook_id": nb_id,
                "url": resolved_url if "/notebook/" in resolved_url else gemini_url,
                "notebooklm_url": nblm_url,
                "title": title,
                "owner_profile": leased_profile,
                "clones": [],
                "source_count": 0,
                "created_at": _utc_now_iso(),
                "status": "ACTIVE",
            }
            upsert_notebook_entry(ledger_path, entry)
            return {"ok": True, "ledger_path": str(ledger_path), "notebook": entry}
        finally:
            if tab_id is not None:
                self.bridge.close_tab(tab_id, profile=leased_profile)
            self.lease_release_fn(leased_profile, agent_id=self.agent_id, surface=SURFACE)

    def add_sources(
        self,
        notebook_id_or_url: str,
        bundles_dir: str | Path,
        project_path: str | Path,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Uploads packed Markdown bundles to an existing notebook via CDP DOM.setFileInputFiles."""
        project_root = Path(project_path).resolve()
        ledger_path = get_ledger_path(project_root)
        entry = get_notebook_entry(ledger_path, notebook_id_or_url)
        target_profile = profile or entry["owner_profile"]

        bdir = Path(bundles_dir).resolve()
        if not bdir.exists():
            raise FileNotFoundError(f"Bundles directory does not exist: {bdir}")
        files = sorted(str(p.resolve()) for p in bdir.iterdir() if p.is_file() and not is_env_filename(p.name))
        if not files:
            raise NotebookDriverError(f"No bundle files found in {bdir}")

        leased_profile = self._acquire_notebook_lease(target_profile, task=f"add-sources:{entry['notebook_id']}")
        tab_id: Optional[int] = None
        try:
            tab_id = self.bridge.open_tab(entry["url"], profile=leased_profile, active=True)
            self._dismiss_popups(tab_id, leased_profile, project_root)

            add_res = self.bridge.eval_dom(tab_id, _JS_CLICK_ADD_SOURCES, profile=leased_profile)
            if isinstance(add_res, dict) and not add_res.get("clicked"):
                raise BridgeCommandError(add_res.get("error") or "Failed to click Add sources chip.")
            self.sleep_fn(0.4)

            self.bridge.eval_dom(tab_id, _JS_CLICK_UPLOAD_FILE_OPTION, profile=leased_profile)
            self.sleep_fn(0.3)

            self.bridge.cdp_command(tab_id, "DOM.enable", {}, profile=leased_profile)
            doc = self.bridge.cdp_command(tab_id, "DOM.getDocument", {"depth": -1, "pierce": True}, profile=leased_profile)
            root_id = (doc or {}).get("root", {}).get("nodeId")
            if not root_id:
                raise BridgeCommandError("DOM.getDocument did not return root.nodeId")

            qres = self.bridge.cdp_command(
                tab_id,
                "DOM.querySelector",
                {"nodeId": root_id, "selector": 'input[type="file"]'},
                profile=leased_profile,
            )
            input_node_id = (qres or {}).get("nodeId")
            if not input_node_id:
                raise BridgeCommandError("File input node (input[type='file']) not found via CDP DOM.querySelector")

            self.bridge.cdp_command(
                tab_id,
                "DOM.setFileInputFiles",
                {"nodeId": input_node_id, "files": files},
                profile=leased_profile,
            )
            self.sleep_fn(1.5)

            meta = self._read_meta(tab_id, leased_profile)
            dom_count = meta.get("sourceCount")
            prev_count = int(entry.get("source_count", 0) or 0)
            new_count = int(dom_count) if isinstance(dom_count, int) and dom_count > 0 else prev_count + len(files)
            entry["source_count"] = new_count
            upsert_notebook_entry(ledger_path, entry)

            return {
                "ok": True,
                "notebook_id": entry["notebook_id"],
                "uploaded_files": len(files),
                "source_count": new_count,
            }
        finally:
            if tab_id is not None:
                self.bridge.close_tab(tab_id, profile=leased_profile)
            self.lease_release_fn(leased_profile, agent_id=self.agent_id, surface=SURFACE)

    def discover_web(
        self,
        notebook_id_or_url: str,
        query: str,
        project_path: str | Path,
        profile: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Opens Add sources -> Discover web sources flow and triggers web discovery."""
        project_root = Path(project_path).resolve()
        ledger_path = get_ledger_path(project_root)
        entry = get_notebook_entry(ledger_path, notebook_id_or_url)
        target_profile = profile or entry["owner_profile"]

        leased_profile = self._acquire_notebook_lease(target_profile, task=f"discover-web:{entry['notebook_id']}")
        tab_id: Optional[int] = None
        try:
            tab_id = self.bridge.open_tab(entry["url"], profile=leased_profile, active=True)
            self._dismiss_popups(tab_id, leased_profile, project_root)

            add_res = self.bridge.eval_dom(tab_id, _JS_CLICK_ADD_SOURCES, profile=leased_profile)
            if isinstance(add_res, dict) and not add_res.get("clicked"):
                raise BridgeCommandError(add_res.get("error") or "Failed to click Add sources chip.")
            self.sleep_fn(0.4)

            js = f"{_JS_TRIGGER_DISCOVER_WEB_TEMPLATE}({json.dumps(query)})"
            disc_res = self.bridge.eval_dom(tab_id, js, profile=leased_profile)
            if not isinstance(disc_res, dict) or not disc_res.get("ok"):
                raise BridgeCommandError((disc_res or {}).get("error") or f"Discover web sources failed: {disc_res}")

            self.sleep_fn(2.0)
            imp_res = self.bridge.eval_dom(tab_id, _JS_IMPORT_DISCOVERED_SOURCES, profile=leased_profile)
            meta = self._read_meta(tab_id, leased_profile)
            if isinstance(meta.get("sourceCount"), int) and meta["sourceCount"] > entry.get("source_count", 0):
                entry["source_count"] = meta["sourceCount"]
                upsert_notebook_entry(ledger_path, entry)

            return {
                "ok": True,
                "notebook_id": entry["notebook_id"],
                "query": query,
                "imported": bool(isinstance(imp_res, dict) and imp_res.get("imported")),
                "source_count": entry.get("source_count", 0),
            }
        finally:
            if tab_id is not None:
                self.bridge.close_tab(tab_id, profile=leased_profile)
            self.lease_release_fn(leased_profile, agent_id=self.agent_id, surface=SURFACE)

    def _build_failover_guidance(self, entry: Dict[str, Any], exhausted_profile: str, project_root: Path) -> str:
        nb_id = entry["notebook_id"]
        active_clones = [c for c in entry.get("clones", []) if c.get("status") == "ACTIVE" and c.get("profile") != exhausted_profile]
        if active_clones:
            clone = active_clones[0]
            return (
                f"Profile '{exhausted_profile}' exhausted NotebookLM quota. "
                f"Use existing clone '{clone['notebook_id']}' on '{clone['profile']}' or run: "
                f"python notebook_driver.py query --notebook {clone['notebook_id']} \"<prompt>\" --profile \"{clone['profile']}\" --project \"{project_root}\""
            )
        return (
            f"Profile '{exhausted_profile}' exhausted NotebookLM quota. "
            f"Clone this notebook to another idle Pro profile via: "
            f"python notebook_driver.py share-clone --notebook {nb_id} --target-profile \"Profile 13\" --project \"{project_root}\""
        )

    def query(
        self,
        notebook_id_or_url: str,
        prompt: str,
        project_path: str | Path,
        out_file: Optional[str | Path] = None,
        profile: Optional[str] = None,
        poll_timeout_s: float = 120.0,
    ) -> Dict[str, Any]:
        """Enforces 4 Neon High thinking inside the notebook UI, queries, and harvests citations."""
        project_root = Path(project_path).resolve()
        ledger_path = get_ledger_path(project_root)
        entry = get_notebook_entry(ledger_path, notebook_id_or_url)

        target_url = entry["url"]
        target_profile = profile or entry["owner_profile"]
        if profile:
            for clone in entry.get("clones", []):
                if clone.get("profile") == profile and clone.get("status") == "ACTIVE":
                    target_url = clone["url"]
                    break

        leased_profile = self._acquire_notebook_lease(target_profile, task=f"query:{entry['notebook_id']}")
        tab_id: Optional[int] = None
        try:
            tab_id = self.bridge.open_tab(target_url, profile=leased_profile, active=True)
            self._dismiss_popups(tab_id, leased_profile, project_root)

            gate = self.bridge.eval_dom(tab_id, _JS_ENSURE_4_NEON_HIGH, profile=leased_profile)
            if not isinstance(gate, dict) or not gate.get("ok"):
                raise BridgeCommandError(f"Failed to enforce 4 Neon High thinking in notebook UI: {gate}")

            send_js = f"{_JS_SUBMIT_NOTEBOOK_QUERY_TEMPLATE}({json.dumps(prompt)})"
            send_res = self.bridge.eval_dom(tab_id, send_js, profile=leased_profile)
            if not isinstance(send_res, dict) or not send_res.get("ok"):
                raise BridgeCommandError((send_res or {}).get("error") or f"Failed to submit query: {send_res}")

            deadline = time.time() + poll_timeout_s
            last_text = ""
            stable_ticks = 0
            harvested: Dict[str, Any] = {}

            while time.time() <= deadline:
                liveness = self.liveness_check_fn(lambda js: self.bridge.eval_dom_raw(tab_id, js, profile=leased_profile))
                harvested = self.bridge.eval_dom(tab_id, _JS_HARVEST_NOTEBOOK_RESPONSE, profile=leased_profile) or {}
                if harvested.get("quota_exhausted"):
                    self.cooldown_fn(leased_profile, BUCKET, cooldown_seconds=1800, reason="notebooklm_quota_exhausted")
                    guidance = self._build_failover_guidance(entry, leased_profile, project_root)
                    raise QuotaExhaustedError(guidance)

                cur_text = str(harvested.get("text") or "").strip()
                if cur_text and not liveness.get("active"):
                    if cur_text == last_text:
                        stable_ticks += 1
                        if stable_ticks >= 1:
                            break
                    else:
                        stable_ticks = 0
                last_text = cur_text
                self.sleep_fn(1.0)

            answer_text = str(harvested.get("text") or "").strip()
            citations = harvested.get("citations") if isinstance(harvested.get("citations"), list) else []
            if not answer_text:
                raise BridgeCommandError("Timed out waiting for notebook query response.")

            formatted = self._format_query_markdown(entry, leased_profile, prompt, answer_text, citations)
            if out_file:
                out_path = Path(out_file)
                if not out_path.is_absolute():
                    out_path = project_root / out_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(formatted, encoding="utf-8")

            return {
                "ok": True,
                "notebook_id": entry["notebook_id"],
                "profile": leased_profile,
                "model": "4 Neon (High)",
                "answer": answer_text,
                "citations": citations,
                "out_file": str(out_file) if out_file else None,
            }
        finally:
            if tab_id is not None:
                self.bridge.close_tab(tab_id, profile=leased_profile)
            self.lease_release_fn(leased_profile, agent_id=self.agent_id, surface=SURFACE)

    @staticmethod
    def _format_query_markdown(
        entry: Dict[str, Any],
        profile: str,
        prompt: str,
        answer: str,
        citations: List[Dict[str, Any]],
    ) -> str:
        lines = [
            f"# Notebook Query: {entry.get('title', entry['notebook_id'])}",
            "",
            f"- **Notebook ID**: `{entry['notebook_id']}`",
            f"- **Profile**: `{profile}`",
            "- **Model**: `4 Neon (High)`",
            f"- **Prompt**: {prompt}",
            "",
            "## Response",
            "",
            answer,
        ]
        if citations:
            lines.extend(["", "## Citations", ""])
            for idx, cite in enumerate(citations, start=1):
                lbl = cite.get("label") or f"Citation {idx}"
                href = cite.get("href") or ""
                lines.append(f"{idx}. [{lbl}]({href})" if href else f"{idx}. {lbl}")
        return "\n".join(lines) + "\n"

    def share_clone(
        self,
        notebook_id_or_url: str,
        target_profile: str,
        project_path: str | Path,
    ) -> Dict[str, Any]:
        """Shares owner notebook (Anyone with link + Allow copy), clones onto target_profile, and verifies source_count."""
        project_root = Path(project_path).resolve()
        ledger_path = get_ledger_path(project_root)
        entry = get_notebook_entry(ledger_path, notebook_id_or_url)
        owner_profile = entry["owner_profile"]

        # Phase 1: Enable sharing & extract share URL on owner profile
        leased_owner = self._acquire_notebook_lease(owner_profile, task=f"share:{entry['notebook_id']}")
        owner_tab: Optional[int] = None
        share_url = entry["url"]
        owner_source_count: Optional[int] = entry.get("source_count")
        try:
            owner_tab = self.bridge.open_tab(entry["url"], profile=leased_owner, active=True)
            self._dismiss_popups(owner_tab, leased_owner, project_root)
            meta = self._read_meta(owner_tab, leased_owner)
            if isinstance(meta.get("sourceCount"), int) and meta["sourceCount"] > 0:
                owner_source_count = meta["sourceCount"]
                entry["source_count"] = owner_source_count

            share_res = self.bridge.eval_dom(owner_tab, _JS_SHARE_AND_ALLOW_COPY, profile=leased_owner)
            if not isinstance(share_res, dict) or not share_res.get("ok"):
                raise BridgeCommandError(f"Failed to configure Anyone-with-link + Allow copy on {owner_profile}: {share_res}")
            share_url = str(share_res.get("share_url") or entry["url"])
        finally:
            if owner_tab is not None:
                self.bridge.close_tab(owner_tab, profile=leased_owner)
            self.lease_release_fn(leased_owner, agent_id=self.agent_id, surface=SURFACE)

        # Phase 2: Open share URL on target_profile, clone, and verify source_count parity
        leased_target = self._acquire_notebook_lease(target_profile, task=f"clone:{entry['notebook_id']}")
        target_tab: Optional[int] = None
        try:
            target_tab = self.bridge.open_tab(share_url, profile=leased_target, active=True)
            self._dismiss_popups(target_tab, leased_target, project_root)
            clone_res = self.bridge.eval_dom(target_tab, _JS_CLONE_SHARED_NOTEBOOK, profile=leased_target)
            if not isinstance(clone_res, dict) or not clone_res.get("ok"):
                raise BridgeCommandError((clone_res or {}).get("error") or f"Failed to click Copy/Duplicate notebook: {clone_res}")

            clone_id, clone_url = self._wait_for_notebook_url(target_tab, profile=leased_target)
            clone_meta = self._read_meta(target_tab, leased_target)
            clone_source_count = clone_meta.get("sourceCount")

            matched, reason = verify_clone_source_count(owner_source_count, clone_source_count)
            if not matched:
                raise SourceCountMismatchError(reason)

            _, clone_nblm_url = build_notebook_urls(clone_id)
            clone_record = {
                "notebook_id": clone_id,
                "url": clone_url if "/notebook/" in clone_url else build_notebook_urls(clone_id)[0],
                "notebooklm_url": clone_nblm_url,
                "profile": leased_target,
                "source_count": int(clone_source_count) if clone_source_count is not None else owner_source_count,
                "cloned_from": entry["notebook_id"],
                "created_at": _utc_now_iso(),
                "status": "ACTIVE",
            }
            entry.setdefault("clones", []).append(clone_record)
            upsert_notebook_entry(ledger_path, entry)

            return {
                "ok": True,
                "owner_notebook_id": entry["notebook_id"],
                "owner_profile": leased_owner,
                "clone": clone_record,
                "verified_source_count": clone_record["source_count"],
            }
        finally:
            if target_tab is not None:
                self.bridge.close_tab(target_tab, profile=leased_target)
            self.lease_release_fn(leased_target, agent_id=self.agent_id, surface=SURFACE)

    def _delete_single_notebook(self, url: str, profile: str, project_root: Path, label: str) -> None:
        leased = self._acquire_notebook_lease(profile, task=f"cleanup:{label}")
        tab_id: Optional[int] = None
        try:
            tab_id = self.bridge.open_tab(url, profile=leased, active=True)
            self._dismiss_popups(tab_id, leased, project_root)
            del_res = self.bridge.eval_dom(tab_id, _JS_DELETE_NOTEBOOK, profile=leased)
            if not isinstance(del_res, dict) or not del_res.get("ok"):
                raise BridgeCommandError((del_res or {}).get("error") or f"Failed to delete notebook at {url}: {del_res}")
            self.sleep_fn(0.5)
        finally:
            if tab_id is not None:
                self.bridge.close_tab(tab_id, profile=leased)
            self.lease_release_fn(leased, agent_id=self.agent_id, surface=SURFACE)

    def cleanup(
        self,
        project_path: str | Path,
        notebook_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deletes active notebooks across owner and all cloned profiles and marks ledger DELETED."""
        project_root = Path(project_path).resolve()
        ledger_path = get_ledger_path(project_root)
        ledger = load_ledger(ledger_path)
        notebooks = ledger.get("notebooks", {})

        target_id = extract_notebook_id(notebook_id) if notebook_id else None
        deleted_items: List[Dict[str, str]] = []
        errors: List[Dict[str, str]] = []

        for nb_id, entry in notebooks.items():
            if not isinstance(entry, dict):
                continue
            if target_id and nb_id != target_id:
                continue
            if entry.get("status") == "DELETED":
                continue

            clone_failures = False
            for clone in entry.get("clones", []):
                if not isinstance(clone, dict) or clone.get("status") == "DELETED":
                    continue
                try:
                    self._delete_single_notebook(
                        clone["url"],
                        clone["profile"],
                        project_root,
                        label=f"clone:{clone.get('notebook_id', nb_id)}",
                    )
                    clone["status"] = "DELETED"
                    clone["deleted_at"] = _utc_now_iso()
                    deleted_items.append({"role": "clone", "notebook_id": clone.get("notebook_id", ""), "profile": clone["profile"]})
                except Exception as exc:
                    clone_failures = True
                    errors.append({"role": "clone", "notebook_id": clone.get("notebook_id", ""), "profile": clone.get("profile", ""), "error": str(exc)})

            try:
                self._delete_single_notebook(
                    entry["url"],
                    entry["owner_profile"],
                    project_root,
                    label=f"owner:{nb_id}",
                )
                if not clone_failures:
                    entry["status"] = "DELETED"
                else:
                    entry["status"] = "PARTIAL_DELETE"
                entry["deleted_at"] = _utc_now_iso()
                deleted_items.append({"role": "owner", "notebook_id": nb_id, "profile": entry["owner_profile"]})
            except Exception as exc:
                errors.append({"role": "owner", "notebook_id": nb_id, "profile": entry.get("owner_profile", ""), "error": str(exc)})

        save_ledger(ledger_path, ledger)
        return {
            "ok": len(errors) == 0,
            "ledger_path": str(ledger_path),
            "deleted": deleted_items,
            "errors": errors,
        }


# ---------------------------------------------------------------------------
# CLI Interface
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notebook_driver.py",
        description="Gemini Notebooks / NotebookLM Pro Project RAG Bucket Driver via Argon Bridge.",
    )
    parser.add_argument(
        "--cleanup-notebooks",
        action="store_true",
        help="Alias flag to clean up active notebooks in --project ledger.",
    )
    parser.add_argument("--project", help="Project root path (used with --cleanup-notebooks).")
    sub = parser.add_subparsers(dest="command")

    p_pack = sub.add_parser("pack", help="Pack scrubbed project files into <= 12 Markdown bundles.")
    p_pack.add_argument("--project", required=True, help="Project root directory.")
    p_pack.add_argument("--paths", nargs="*", help="Optional explicit relative/absolute paths to pack.")
    p_pack.add_argument("--max-bundles", type=int, default=DEFAULT_MAX_BUNDLES, help="Max bundle count (default: 12).")
    p_pack.add_argument("--out-dir", help="Optional output directory (default: <project>/temp_read/nb_bundles).")

    p_create = sub.add_parser("create", help="Create a new Gemini Notebook and record it in notebook_ledger.json.")
    p_create.add_argument("--title", required=True, help="Notebook title.")
    p_create.add_argument("--project", required=True, help="Project root directory.")
    p_create.add_argument("--profile", help="Optional preferred Chrome profile dir (e.g. 'Profile 14').")

    p_add = sub.add_parser("add-sources", help="Attach packed bundles via CDP DOM.setFileInputFiles.")
    p_add.add_argument("--notebook", required=True, help="Notebook ID or URL.")
    p_add.add_argument("--bundles", required=True, help="Directory of Markdown bundles.")
    p_add.add_argument("--project", required=True, help="Project root directory.")
    p_add.add_argument("--profile", help="Optional Chrome profile override.")

    p_disc = sub.add_parser("discover-web", help="Trigger Discover web sources inside a notebook.")
    p_disc.add_argument("--notebook", required=True, help="Notebook ID or URL.")
    p_disc.add_argument("--query", required=True, help="Web discovery query.")
    p_disc.add_argument("--project", required=True, help="Project root directory.")
    p_disc.add_argument("--profile", help="Optional Chrome profile override.")

    p_query = sub.add_parser("query", help="Query a notebook using 4 Neon High thinking and harvest citations.")
    p_query.add_argument("--notebook", required=True, help="Notebook ID or URL.")
    p_query.add_argument("prompt", help="Query prompt.")
    p_query.add_argument("-o", "--output", help="Optional Markdown output file path.")
    p_query.add_argument("--project", required=True, help="Project root directory.")
    p_query.add_argument("--profile", help="Optional Chrome profile override (e.g. clone profile).")

    p_clone = sub.add_parser("share-clone", help="Share owner notebook and clone onto a target profile.")
    p_clone.add_argument("--notebook", required=True, help="Notebook ID or URL.")
    p_clone.add_argument("--target-profile", required=True, help="Target Chrome profile dir (e.g. 'Profile 13').")
    p_clone.add_argument("--project", required=True, help="Project root directory.")

    p_clean = sub.add_parser("cleanup", help="Delete active notebooks across owner and all cloned profiles.")
    p_clean.add_argument("--project", required=True, help="Project root directory.")
    p_clean.add_argument("--notebook", help="Optional specific notebook ID to delete.")

    return parser


def main(argv: Optional[Sequence[str]] = None, driver: Optional[NotebookDriver] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    drv = driver or NotebookDriver()

    try:
        if args.cleanup_notebooks and not args.command:
            if not args.project:
                parser.error("--cleanup-notebooks requires --project <path>")
            res = drv.cleanup(project_path=args.project)
        elif args.command == "pack":
            res = pack_project(
                project_path=args.project,
                paths=args.paths,
                max_bundles=args.max_bundles,
                out_dir=args.out_dir,
            )
        elif args.command == "create":
            res = drv.create(title=args.title, project_path=args.project, profile=args.profile)
        elif args.command == "add-sources":
            res = drv.add_sources(
                notebook_id_or_url=args.notebook,
                bundles_dir=args.bundles,
                project_path=args.project,
                profile=args.profile,
            )
        elif args.command == "discover-web":
            res = drv.discover_web(
                notebook_id_or_url=args.notebook,
                query=args.query,
                project_path=args.project,
                profile=args.profile,
            )
        elif args.command == "query":
            res = drv.query(
                notebook_id_or_url=args.notebook,
                prompt=args.prompt,
                project_path=args.project,
                out_file=args.output,
                profile=args.profile,
            )
        elif args.command == "share-clone":
            res = drv.share_clone(
                notebook_id_or_url=args.notebook,
                target_profile=args.target_profile,
                project_path=args.project,
            )
        elif args.command == "cleanup":
            res = drv.cleanup(project_path=args.project, notebook_id=args.notebook)
        else:
            parser.print_help()
            return 2

        print(json.dumps(res, indent=2))
        return 0 if res.get("ok", True) else 1
    except QuotaExhaustedError as exc:
        print(f"[QUOTA_EXHAUSTED] {exc}", file=sys.stderr)
        return 3
    except NotebookDriverError as exc:
        print(f"[NotebookDriverError] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
