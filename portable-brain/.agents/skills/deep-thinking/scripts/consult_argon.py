#!/usr/bin/env python3
r"""consult_argon.py - Dual-Surface Frontier Cognitive & Research Router.

========================================================================================
EXECUTION-FIRST MANDATE:
- Do NOT read this script passively or wrap it in temporary runner scripts.
- Consulting & Audits (Default -> AI Studio Playground: gemini-4-argon / gemini-4-neon):
    python ./.agents\skills\deep-thinking\scripts\consult_argon.py "<prompt>" -o temp_read/ans.md
- Deep Research / Cloud Subagent Tasks (Gemini Web: 4 Neon High):
    python ./.agents\skills\deep-thinking\scripts\consult_argon.py "<topic>" --deep-research -o temp_read/research.md
    python ./.agents\skills\deep-thinking\scripts\consult_argon.py "<task>" --task -o temp_read/task_out.md
- Split-Brain Adversarial Council (bounded <= 2 rounds):
    python ./.agents\skills\deep-thinking\scripts\consult_argon.py "<proposal>" --council plan -O -C 8
========================================================================================
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

SCRIPT_DIR = Path(__file__).resolve().parent
BRAIN_ROOT = Path(__file__).resolve().parents[4]
AUTO_SKILL_SCRIPTS = BRAIN_ROOT / ".agents" / "skills" / "auto-skill" / "scripts"
FULL_SYNC_SCRIPTS = BRAIN_ROOT / ".agents" / "skills" / "full-sync" / "scripts"
BRIDGE_DIR = BRAIN_ROOT / ".agents" / "skills" / "browser-operator" / "argon_bridge"

for p in (SCRIPT_DIR, FULL_SYNC_SCRIPTS, BRIDGE_DIR, AUTO_SKILL_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from argon_context_packer import build_selective_context_bundle, record_session_turn, slice_code_file
except ImportError:
    build_selective_context_bundle = None
    record_session_turn = None
    slice_code_file = None

try:
    import offload_context_compiler as occ
    import conversation_distiller as cd
except ImportError:
    occ = None
    cd = None

try:
    from gemini_brain_driver import GeminiBrainDriver, resolve_execution_route
    import aistudio_subagent as ais
    from profile_lock_manager import (
        acquire_profile_lease,
        release_profile_lease,
        get_live_profile_status,
    )
except ImportError:
    GeminiBrainDriver = None
    resolve_execution_route = None
    ais = None
    acquire_profile_lease = None
    release_profile_lease = None
    get_live_profile_status = None


def resolve_consult_surface(
    surface: Optional[str] = None,
    deep_research: bool = False,
    task_mode: bool = False,
    mode: str = "chat",
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Determines canonical Dual-Surface route & hard-blocks Hydrogen/Carbon."""
    raw_model = (model or "").strip().lower()
    if any(b in raw_model for b in ("hydrogen", "carbon")):
        raise ValueError(
            f"Model '{model}' is blocked in browser bridges. "
            "Use gemini-4-argon / gemini-4-neon on AI Studio Playground or 4 Neon on Gemini Web."
        )

    m_norm = "task" if task_mode else (mode or "chat").strip().lower()
    if deep_research or m_norm == "task":
        chosen_surface = (surface or "web").strip().lower()
    else:
        chosen_surface = (surface or "aistudio").strip().lower()

    if chosen_surface == "aistudio":
        chosen_model = ais.validate_aistudio_model(model) if ais else ("gemini-4-neon" if "neon" in raw_model else "gemini-4-argon")
        return {"surface": "aistudio", "model": chosen_model, "mode": "playground", "thinking": "High"}

    # Gemini Web -> strictly 4 Neon + High
    chosen_model = "4 Neon"
    if raw_model and "argon" not in raw_model and "neon" not in raw_model and "flash" not in raw_model:
        chosen_model = model or "4 Neon"
    return {
        "surface": "web",
        "model": chosen_model,
        "mode": "chat" if deep_research else m_norm,
        "thinking": "High",
    }


def _resolve_project_root(explicit_project: Optional[str]) -> Path:
    if explicit_project:
        cand = Path(explicit_project)
        if cand.exists():
            return cand.resolve()
        # Lookup named workspace sibling under Desktop / PJCT
        for base in (BRAIN_ROOT.parent, BRAIN_ROOT.parent / "PJCT", Path(r"<PROJECTS_ROOT>")):
            if (base / explicit_project).is_dir():
                return (base / explicit_project).resolve()
    cwd = Path.cwd().resolve()
    if (cwd / ".agents").is_dir() or (cwd / ".git").is_dir():
        return cwd
    return BRAIN_ROOT


def build_composable_context(
    prompt: str,
    project_root: Path,
    explicit_project: Optional[str] = None,
    files: Optional[List[str]] = None,
    pack_specs: Optional[List[str]] = None,
    fresh: bool = False,
    attach_offload: bool = False,
    full_offload: bool = False,
    attach_chat: Optional[int] = None,
    blind: bool = False,
    auto_context: bool = False,
    compress: bool = False,
    session_id: Optional[str] = None,
    dry_run: bool = False,
) -> Tuple[str, List[str], Dict[str, Any]]:
    """Assembles requested context components + 2-layer secret scrubbing without forced bloat."""
    attached: List[str] = []
    seen: set[str] = set()
    total_redactions = 0

    def _add_file(p_str: str) -> None:
        rp = str(Path(p_str).resolve()) if Path(p_str).exists() else p_str
        if rp not in seen:
            seen.add(rp)
            attached.append(rp)

    for fp in (files or []):
        p = Path(fp)
        if not p.is_absolute() and (project_root / p).exists():
            p = project_root / p
        elif not p.is_absolute() and (BRAIN_ROOT / p).exists():
            p = BRAIN_ROOT / p
        _add_file(str(p))

    telemetry: Dict[str, Any] = {
        "project_root": str(project_root),
        "fresh": fresh,
        "blind": blind,
        "attached_offload": False,
        "attached_chat_turns": None,
        "redaction_count": 0,
    }

    if not fresh:
        if (attach_offload or full_offload) and occ:
            out_offload, off_stats = occ.compile_offload_context(project_root, full=full_offload, dry_run=dry_run)
            telemetry["attached_offload"] = True
            telemetry["offload_stats"] = off_stats
            total_redactions += int(off_stats.get("redaction_count", 0))
            if out_offload.exists():
                _add_file(str(out_offload))

        if attach_chat is not None and cd:
            slice_out = project_root / "temp_read" / ("clean_conversation_slice_blind.md" if blind else "clean_conversation_slice.md")
            sl_res = cd.build_clean_conversation_slice(
                project_root=project_root,
                max_turns=max(1, int(attach_chat)),
                blind=blind,
                out_path=slice_out,
            )
            telemetry["attached_chat_turns"] = int(attach_chat)
            telemetry["slice_stats"] = sl_res
            total_redactions += int(sl_res.get("redaction_count", 0))
            if Path(sl_res["output_path"]).exists():
                _add_file(sl_res["output_path"])

        if (auto_context or pack_specs) and build_selective_context_bundle and not blind:
            try:
                bpath, pack_tel = build_selective_context_bundle(
                    prompt=prompt,
                    pack_specs=pack_specs or [],
                    explicit_project=explicit_project or project_root.name,
                    session_id=session_id,
                    compress=compress,
                )
                telemetry["pack_telemetry"] = pack_tel
                if bpath:
                    _add_file(bpath)
            except Exception as e:
                telemetry["pack_warning"] = str(e)

    scrubbed_prompt = prompt
    if occ:
        scrubbed_prompt, p_red = occ.redact_two_layer(prompt, roots=[project_root, BRAIN_ROOT])
        total_redactions += p_red

    # Estimate bytes/tokens across prompt + all attached files
    total_bytes = len(scrubbed_prompt.encode("utf-8"))
    for fp in attached:
        try:
            if Path(fp).is_file():
                total_bytes += Path(fp).stat().st_size
        except OSError:
            pass
    telemetry["redaction_count"] = total_redactions
    telemetry["files"] = attached
    telemetry["total_bytes"] = total_bytes
    telemetry["est_tokens"] = int(total_bytes / 3.8)
    return scrubbed_prompt, attached, telemetry


def consult_argon_api(
    prompt: str,
    files: Optional[List[str]] = None,
    thinking: str = "High",
    output_path: Optional[str] = None,
    allow_paid_api_fallback: bool = False,
) -> Dict[str, Any]:
    """Tier-2 Route: Calls Gemini 4 Argon via Google Cloud Vertex AI API (explicit --api only)."""
    import subprocess
    api_script = Path(r"C:\Users\User\Desktop\PJCT\custom_tools\api_router\argon.py")
    if not api_script.exists():
        return {"ok": False, "error": f"Vertex AI Argon script not found at {api_script}"}

    cmd = [sys.executable, str(api_script), "-q", prompt, "--thinking", thinking.lower(), "--json"]
    for fp in (files or []):
        cmd.extend(["-f", fp])

    print(f"[ConsultArgon-API] Routing to Gemini 4 Argon via Vertex AI API (Thinking: {thinking})...")
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
            out_p = BRAIN_ROOT / out_p
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(resp_text, encoding="utf-8")
    return {"ok": True, "profile": "Vertex-AI-API", "thinking": thinking, "response": resp_text, "duration_seconds": dur, "via_api": True}


def consult_argon_web(
    prompt: str,
    files: Optional[List[str]] = None,
    thinking: Optional[str] = "High",
    deep_research: bool = False,
    auto_clean: bool = True,
    profile: Optional[str] = None,
    session_id: Optional[str] = None,
    new_chat: bool = True,
    own_tab: bool = False,
    output_path: Optional[str] = None,
    allow_paid_api_fallback: bool = False,
    model: Optional[str] = None,
    mode: str = "chat",
    keep_tab: bool = False,
) -> Dict[str, Any]:
    """Routes Gemini Web queries exclusively to `4 Neon` + `High` Thinking."""
    driver = None
    sid = None
    target_prof = profile
    lease_acquired = False
    had_error = True
    agent_id = session_id or f"agent_{int(time.time() * 1000)}"
    route = resolve_execution_route(model=model, thinking=thinking, mode=mode, deep_research=deep_research) if resolve_execution_route else {
        "mode": "chat" if deep_research else mode,
        "model": "4 Neon",
        "thinking": thinking or "High",
    }

    if not GeminiBrainDriver:
        return {"ok": False, "error": "GeminiBrainDriver unavailable."}

    if acquire_profile_lease:
        target_prof, err = acquire_profile_lease(
            agent_id=agent_id,
            preferred_profile=profile,
            task=prompt[:40] if prompt else "gemini_web",
            session_id=session_id,
            deep_research=deep_research,
            surface="gemini_web",
            bucket="gemini_web_neon",
        )
        if err or not target_prof:
            if allow_paid_api_fallback:
                return consult_argon_api(prompt=prompt, files=files, thinking=route["thinking"], output_path=output_path)
            return {"ok": False, "error": f"Failed to acquire gemini_web lease: {err}"}
        lease_acquired = True

    try:
        driver = GeminiBrainDriver(default_profile=target_prof)
        sid = driver.create_session(session_id=session_id, new_chat=new_chat, own_tab=own_tab, profile_dir=target_prof)
        timeout_sec = 1500 if deep_research else (600 if route["mode"] == "task" else 300)
        res = driver.ask(
            session_id=sid,
            prompt=prompt,
            files=files,
            deep_research=deep_research,
            model=route["model"],
            thinking=route["thinking"],
            mode=route["mode"],
            timeout_sec=timeout_sec,
            check_usage=True,
        )
        if not res.get("ok"):
            return {"ok": False, "error": res.get("error") or "Gemini Web execution failed"}
        response_text = res.get("response", "")
        if output_path:
            out_p = Path(output_path)
            if not out_p.is_absolute():
                out_p = BRAIN_ROOT / out_p
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(response_text, encoding="utf-8")
        had_error = False
        return {
            "ok": True,
            "surface": "web",
            "session_id": sid,
            "profile": res.get("profile"),
            "chat_id": res.get("chat_id"),
            "mode": res.get("mode", route["mode"]),
            "model": res.get("model", route["model"]),
            "thinking": res.get("thinking", route["thinking"]),
            "response": response_text,
            "rich": res.get("rich", {}),
            "usage": res.get("usage", {}),
            "duration_seconds": res.get("duration_seconds", 0.0),
        }
    finally:
        if driver is not None and sid:
            try:
                if auto_clean:
                    driver.delete_session(sid, profile=target_prof, close_tab=not keep_tab)
                elif had_error and not keep_tab:
                    meta = driver.registry.get(sid) or {}
                    tab_id = driver.tab_id or meta.get("tab_id")
                    if tab_id is not None:
                        driver._call_api(
                            "/command",
                            {"action": "CLOSE_TAB", "agent_guarded": True, "params": {"tabId": tab_id}},
                            profile=target_prof,
                        )
            except Exception:
                pass
        if lease_acquired and release_profile_lease and target_prof:
            release_profile_lease(target_prof, agent_id=agent_id, surface="gemini_web")


def run_single_consultation(
    prompt: str,
    surface: Optional[str] = None,
    model: Optional[str] = None,
    mode: str = "chat",
    thinking: str = "High",
    files: Optional[List[str]] = None,
    system_skill: Optional[str] = None,
    system_instructions: Optional[str] = None,
    search: bool = False,
    code_exec: bool = False,
    url_context: bool = False,
    max_output_tokens: int = 800000,
    deep_research: bool = False,
    profile: Optional[str] = None,
    session_id: Optional[str] = None,
    continue_session: bool = False,
    own_tab: bool = False,
    auto_clean: bool = True,
    keep_tab: bool = False,
    output_path: Optional[str] = None,
    allow_paid_api_fallback: bool = False,
) -> Dict[str, Any]:
    """Unified programmatic consultation dispatcher across AI Studio Playground and Gemini Web."""
    route = resolve_consult_surface(
        surface=surface,
        deep_research=deep_research,
        task_mode=(mode == "task"),
        mode=mode,
        model=model,
    )
    if route["surface"] == "aistudio":
        if not ais:
            return {"ok": False, "error": "aistudio_subagent unavailable."}
        res = ais.ask_ai_studio(
            prompt=prompt,
            context_files=files,
            preferred_profile=profile,
            model_name=route["model"],
            system_instructions=system_instructions,
            system_skill=system_skill,
            thinking=thinking,
            max_output_tokens=max_output_tokens,
            search=search,
            code_exec=code_exec,
            url_context=url_context,
            output_file=output_path,
            session_id=session_id,
            continue_chat=continue_session,
            keep_tab=keep_tab,
        )
        if res.get("ok") and "response" not in res:
            res["response"] = res.get("text", "")
        return res

    # Gemini Web route (Deep Research / Task / explicit --surface web)
    web_prompt = prompt
    if system_skill and ais:
        try:
            web_prompt = f"### SYSTEM PERSONA\n{ais.resolve_system_skill(system_skill)}\n\n{prompt}"
        except Exception:
            pass
    return consult_argon_web(
        prompt=web_prompt,
        files=files,
        thinking=thinking,
        deep_research=deep_research,
        auto_clean=auto_clean,
        profile=profile,
        session_id=session_id,
        new_chat=not continue_session,
        own_tab=own_tab,
        keep_tab=keep_tab,
        output_path=output_path,
        allow_paid_api_fallback=allow_paid_api_fallback,
        model=route["model"],
        mode=route["mode"],
    )


INFLIGHT_MAX_AGE = 300
INFLIGHT_HEARTBEAT = 20
INFLIGHT_POLL = 0.25


def _consultation_key(project_root, request, context_digest=None, temporary_session=False):
    route = dict(request)
    prompt = route.pop("prompt")
    files = route.pop("files", None) or []
    route.pop("output_path", None)
    if temporary_session:
        route.pop("session_id", None)
    if context_digest is None:
        context = hashlib.sha256()
        for filename in files:
            path = Path(filename)
            with path.open("rb") as file:
                file_hash = hashlib.file_digest(file, "sha256").hexdigest()
            context.update(json.dumps([path.name, file_hash]).encode("utf-8"))
        context_digest = context.hexdigest()
    identity = {
        "project": os.path.normcase(str(project_root.resolve())),
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "context": context_digest,
        "route": route,
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()[:16]


@contextmanager
def _consult_state_lock(directory):
    with (directory / ".consult_dedup.lock").open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield


def _atomic_consult_json(path, value):
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
        try:
            json.dump(value, file, default=str)
            file.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _read_inflight(marker):
    try:
        result = json.loads(marker.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (FileNotFoundError, ValueError):
        return {}


def _consult_pid_alive(pid):
    if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            exit_code = wintypes.DWORD()
            return not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return False
    return True


def _inflight_live(state):
    updated = state.get("heartbeat_at", state.get("started_at"))
    owner = state.get("owner")
    return (
        isinstance(owner, str) and re.fullmatch(r"[0-9a-f]{32}", owner)
        and type(updated) in (int, float) and 0 <= time.time() - updated < INFLIGHT_MAX_AGE
        and _consult_pid_alive(state.get("pid"))
    )


def _collect_inflight(marker, owner, result_path, output):
    print("[ConsultDedup] Waiting for in-flight consultation...", file=sys.stderr)
    deadline = time.monotonic() + INFLIGHT_MAX_AGE
    while True:
        # Synchronize the owner check with publication. Once the marker changes,
        # the previous owner either published its result or abandoned the run.
        with _consult_state_lock(marker.parent):
            result = _read_inflight(result_path)
            if result:
                break
            state = _read_inflight(marker)
            if state.get("owner") != owner or not _inflight_live(state):
                return {"ok": False, "error": "In-flight consultation ended without a result."}
        if time.monotonic() >= deadline:
            return {"ok": False, "error": "Timed out waiting for the in-flight consultation."}
        time.sleep(INFLIGHT_POLL)
    if result.get("ok") and output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(result.get("response") or result.get("text") or ""), encoding="utf-8")
        if "output_path" in result:
            result["output_path"] = str(path)
    result["deduplicated"] = True
    return result


def consult_with_dedupe(project_root, *, context_digest=None, temporary_session=False, **request):
    """Join an identical live browser consultation without reusing a finished run."""
    if request.get("continue_session"):
        return run_single_consultation(**request)
    try:
        key = _consultation_key(project_root, request, context_digest, temporary_session)
        directory = project_root / "temp_read"
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / f".inflight_{key}.json"

        def result_for(owner):
            return directory / f".consult_result_{key}_{owner}.json"

        with _consult_state_lock(directory):
            state = _read_inflight(marker)
            join = _inflight_live(state)
            if join:
                owner = state["owner"]
            else:
                owner = uuid4().hex
                state = {
                    "owner": owner, "pid": os.getpid(), "started_at": time.time(),
                    "output_path": str(result_for(owner)),
                    "route": {name: request.get(name) for name in ("surface", "model", "mode", "system_skill")},
                }
                _atomic_consult_json(marker, state)
                expire_before = time.time() - INFLIGHT_MAX_AGE * 2
                for path in directory.glob(".consult_result_*.json"):
                    if not re.fullmatch(r"\.consult_result_[0-9a-f]{16}_[0-9a-f]{32}\.json", path.name):
                        continue
                    try:
                        if path.stat().st_mtime < expire_before:
                            path.unlink()
                    except OSError:
                        pass
        result_path = result_for(owner)
        if join:
            return _collect_inflight(marker, owner, result_path, request.get("output_path"))

        stopped = threading.Event()

        def heartbeat():
            while not stopped.wait(INFLIGHT_HEARTBEAT):
                try:
                    with _consult_state_lock(directory):
                        if _read_inflight(marker).get("owner") != owner:
                            return
                        _atomic_consult_json(marker, {**state, "heartbeat_at": time.time()})
                except OSError:
                    return

        worker = threading.Thread(target=heartbeat, daemon=True)
        worker.start()
        result = {"ok": False, "error": "In-flight consultation was interrupted."}
        try:
            result = run_single_consultation(**request)
            return result
        except Exception as error:
            result = {"ok": False, "error": str(error)}
            return result
        finally:
            stopped.set()
            worker.join()
            with _consult_state_lock(directory):
                if _read_inflight(marker).get("owner") == owner:
                    try:
                        _atomic_consult_json(result_path, result)
                    finally:
                        marker.unlink(missing_ok=True)
    except OSError as error:
        return {"ok": False, "error": f"Consultation coordination failed: {error}"}


PANEL_PRESETS = {
    "architecture": (
        ("argon-architect", "gemini-4-argon", "architect", False),
        ("neon-critic", "gemini-4-neon", "falsifier_blind", True),
    ),
    "review": (
        ("argon-reviewer", "gemini-4-argon", "plan_verifier", False),
        ("neon-falsifier", "gemini-4-neon", "falsifier_blind", True),
    ),
    "critic": (
        ("neon-critic", "gemini-4-neon", "falsifier_blind", False),
        ("argon-architect", "gemini-4-argon", "architect", False),
    ),
}


def _panel_context(prompt: str, project_root: Path, files: List[str], pack_specs: List[str]):
    """Build one scrubbed text bundle in memory without reading implicit history."""
    if occ is None:
        raise ValueError("Panel context redaction is unavailable.")
    parts = ["# Panel context", "", "## Shared task", "", prompt]
    for value in files:
        path = Path(value)
        if not path.is_absolute():
            path = project_root / path
        try:
            content = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValueError(f"Panel attachments must be UTF-8 text: {path}") from error
        parts.extend(("", f"## Attachment: {path.name}", "", content))
    for spec in pack_specs:
        if slice_code_file is None:
            raise ValueError("Explicit code slicing is unavailable.")
        # Resolve relative specs against the project and keep the optional range/symbol suffix.
        if not Path(spec).is_absolute():
            spec = str(project_root / spec)
        sliced = slice_code_file(spec, re.findall(r"[A-Za-z0-9_]+", prompt.lower()), cwd=str(project_root))
        if not sliced:
            raise ValueError(f"Could not resolve panel code slice: {spec}")
        parts.extend(("", f"## Code context: {Path(sliced['path']).name}", "", sliced["content"]))
    scrubbed, redactions = occ.redact_two_layer("\n".join(parts), roots=[project_root, BRAIN_ROOT])
    return scrubbed.encode("utf-8"), redactions


def _panel_capacity(resources: Dict[str, Any]) -> int:
    if not resources.get("ok"):
        return 1  # Conservative when the bridge does not expose its current inventory.
    try:
        free_profiles = min(3, int(resources.get("max_agent_profiles", 3))) - int(resources["active_agent_profiles_count"])
        free_tabs = min(6, int(resources.get("max_agent_tabs", 6))) - int(resources["active_agent_tabs"])
    except (KeyError, TypeError, ValueError):
        return 1
    return max(0, min(2, free_profiles, free_tabs))


def _panel_report(result: Dict[str, Any]) -> str:
    lines = [
        f"# {result['preset'].title()} consultation panel",
        "",
        f"Shared context SHA-256: `{result['context_digest']}`",
        f"Status: {result['status']}",
        "",
        "Independent recommendations and objections follow in preset order. Differences remain open for review.",
    ]
    for role in result["roles"]:
        lines.extend(("", f"## {role['name']} ({role['model']})"))
        if role.get("error"):
            lines.extend(("", f"Error: {role['error']}"))
        if role.get("response"):
            lines.extend(("", role["response"]))
    return "\n".join(lines) + "\n"


def run_consultation_panel(
    preset: str,
    prompt: str,
    project_root: Path,
    *,
    files: Optional[List[str]] = None,
    pack_specs: Optional[List[str]] = None,
    output: Optional[Path] = None,
    max_output_tokens: int = 800000,
    dry_run: bool = False,
) -> Dict[str, Any]:
    context, redactions = _panel_context(prompt, project_root, files or [], pack_specs or [])
    run_id = f"panel_{preset}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}"
    output = output or project_root / "temp_read"
    manifest = output / f"{run_id}.md" if output.is_dir() or not output.suffix else output
    bundle = manifest.parent / f"{run_id}_context.md"
    roles = [
        {"name": name, "model": model, "system_skill": persona, "blind": blind,
         "output": str(manifest.parent / f"{run_id}_{name}.md")}
        for name, model, persona, blind in PANEL_PRESETS[preset]
    ]
    result = {
        "ok": True, "dry_run": dry_run, "preset": preset, "surface": "aistudio", "status": "planned",
        "manifest": str(manifest), "context_bundle": str(bundle), "context_digest": hashlib.sha256(context).hexdigest(),
        "context_bytes": len(context), "redaction_count": redactions, "max_workers": 2,
        "max_output_tokens": max_output_tokens, "search": False, "roles": roles,
    }
    if dry_run:
        return result

    manifest.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_bytes(context)
    workers = _panel_capacity(_fetch_bridge_resources())
    result["workers"] = workers

    def dispatch(role):
        if not workers:
            return {**role, "ok": False, "error": "No agent profile or tab capacity is available."}
        request = (
            "Review the shared task and evidence in the attached panel context independently. "
            "Give a recommendation, supporting evidence, and objections or uncertainties under separate headings."
        )
        if role["blind"]:
            request += " Form your judgment from the shared evidence without assuming any prior recommendations are correct."
        try:
            response = consult_with_dedupe(
                project_root, context_digest=result["context_digest"], temporary_session=True,
                prompt=request, surface="aistudio", model=role["model"], files=[str(bundle)],
                system_skill=role["system_skill"], max_output_tokens=max_output_tokens,
                session_id=f"{run_id}-{role['name']}",
            )
        except Exception as error:
            response = {"ok": False, "error": str(error)}
        body = str(response.get("response") or response.get("text") or "").strip()
        if response.get("ok") and body:
            body, _ = occ.redact_two_layer(body, roots=[project_root, BRAIN_ROOT])
            try:
                Path(role["output"]).write_text(body + "\n", encoding="utf-8")
            except OSError:
                return {**role, "ok": False, "response": body, "error": "Could not save the standalone role output."}
            return {**role, "ok": True, "response": body}
        message, _ = occ.redact_two_layer(
            str(response.get("error") or "Role returned no response."), roots=[project_root, BRAIN_ROOT],
        )
        return {**role, "ok": False, "error": message}

    if workers == 2:
        with ThreadPoolExecutor(max_workers=2) as pool:
            result["roles"] = list(pool.map(dispatch, roles))
    else:
        result["roles"] = [dispatch(role) for role in roles]
    succeeded = sum(role["ok"] for role in result["roles"])
    result["ok"] = succeeded == len(roles)
    result["status"] = "complete" if result["ok"] else "partial" if succeeded else "failed"
    manifest.write_text(_panel_report(result), encoding="utf-8")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dual-Surface Frontier Consulting & Research Router (AI Studio + Gemini Web)")
    parser.add_argument("prompt", nargs="?", default=None, help="The question, hypothesis, or architectural task")
    parser.add_argument("-q", "--question", dest="question_flag", help="Alternative flag for prompt")
    parser.add_argument("--profile", default=None, help="Explicit Chrome profile; defaults to Waterfall Drain (Tier 1 Alts -> Tier 2 Daily Drivers last)")
    parser.add_argument("--status", action="store_true", help="Display live 11-profile fleet visibility, quota buckets & leases")
    parser.add_argument("--surface", choices=["aistudio", "web"], default=None, help="Target surface (default: aistudio for consulting, web for --deep-research/--task)")
    parser.add_argument("--model", default=None, help="Model (aistudio: gemini-4-argon|gemini-4-neon; web: 4 Neon). Hydrogen/Carbon are blocked.")
    parser.add_argument("--mode", default="chat", choices=["chat", "task"], help="Gemini Web segmented mode ('chat' or 'task')")
    parser.add_argument("--task", action="store_true", help="Run via Gemini Web Task mode (parallel cloud subagents on 4 Neon High)")
    parser.add_argument("--thinking", default="High", choices=["Low", "Medium", "High"], help="Thinking level (default: High)")
    parser.add_argument("--deep-research", action="store_true", help="Run Gemini Web Deep Research on 4 Neon High")
    parser.add_argument("--max-output-tokens", type=int, default=800000, help="AI Studio max output tokens (default: 800000, max: 1048576)")
    parser.add_argument("--search", choices=["on", "off"], default="off", help="AI Studio Grounding with Google Search (default: off)")
    parser.add_argument("--code-exec", choices=["on", "off"], default="off", help="AI Studio Code Execution toggle (default: off)")
    parser.add_argument("--url-context", choices=["on", "off"], default="off", help="AI Studio URL context toggle (default: off)")
    parser.add_argument("--system", default=None, help="Inline system instructions")
    parser.add_argument("--system-skill", default=None, help="Persona from .agents/gemini_skills/<name>.md (e.g. architect, falsifier_blind)")

    # Composable Deep Context Flags
    parser.add_argument("--fresh", action="store_true", help="Sterile fresh perspective (skips offload context, chat slice, and auto-context)")
    parser.add_argument("-O", "--attach-offload", action="store_true", help="Compile & attach <project>/context/offload_context.md")
    parser.add_argument("--full-offload", action="store_true", help="Rebuild full AST cache & attach offload_context.md")
    parser.add_argument("-C", "--attach-chat", nargs="?", const=15, type=int, default=None, help="Attach last N user turns via 4-pass slicer (default N=15)")
    parser.add_argument("--blind", action="store_true", help="Strip assistant rationale from chat slice & bias toward falsifier_blind review")
    parser.add_argument("-f", "--file", "--upload", nargs="+", dest="files", help="Explicit file paths to attach")
    parser.add_argument("--pack", "-p", nargs="*", default=[], help="Smart file/symbol slicer specs (e.g. file.py:10-80)")
    parser.add_argument("--compress", "-c", action="store_true", help="Compress packed code slices")
    parser.add_argument("--auto-context", dest="auto_context", action="store_true", default=False, help="Enable selective Hermes+ledger bundle alongside composable flags")
    parser.add_argument("--no-auto-context", dest="auto_context", action="store_false", help="Disable selective auto-context bundle")
    parser.add_argument("--project", default=None, help="Explicit project path or name")
    parser.add_argument("--dry-run", action="store_true", help="Preview assembled files, byte/token estimate, redactions, and target route without calling Chrome")

    # Split-Brain Adversarial Council
    reviews = parser.add_mutually_exclusive_group()
    reviews.add_argument("--council", choices=["plan", "diff", "full"], default=None, help="Run Split-Brain Adversarial Review Council")
    reviews.add_argument("--panel", choices=PANEL_PRESETS, help="Run two independent AI Studio perspectives")
    parser.add_argument("--rounds", type=int, default=2, choices=[1, 2], help="Max convergence rounds for --council (default: 2)")

    parser.add_argument("--usage", action="store_true", help="Audit Gemini Web usage quota")
    parser.add_argument("--clean", "--delete", dest="clean", action="store_true", default=True, help="Delete temporary web sidebar chat after turn (default: True)")
    parser.add_argument("--no-clean", "--keep", dest="clean", action="store_false", help="Retain sidebar chat")
    parser.add_argument("--keep-tab", action="store_true", help="Keep the browser tab open after the consultation")
    parser.add_argument("--allow-paid-api-fallback", action="store_true", default=False, help="Allow paid Vertex AI failover if requested")
    parser.add_argument("--api", action="store_true", help="Tier-2 Vertex AI Argon API route (explicit only)")
    parser.add_argument("--new-tab", action="store_true", help="Open dedicated new Gemini Web tab")
    parser.add_argument("--continue", dest="continue_session", action="store_true", help="Continue existing chat thread")
    parser.add_argument("--session-id", default=None, help="Session ID for multi-turn tracking")
    parser.add_argument("-o", "--output", help="Save markdown output path")
    parser.add_argument("--prompt-file", "--file-prompt", default=None, help="Read prompt from markdown/text file")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    return parser


def _fetch_bridge_resources(timeout: float = 2.5) -> Dict[str, Any]:
    """Fetches global agent fleet budget from bridge GET /resources (graceful offline fallback)."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:9229/resources", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("ok"):
                return data
    except Exception:
        pass
    return {
        "ok": False,
        "max_agent_profiles": 3,
        "max_agent_tabs": 6,
        "active_agent_profiles": [],
        "active_agent_profiles_count": 0,
        "active_agent_tabs": 0,
    }


def format_status_banner(resources: Optional[Dict[str, Any]] = None) -> str:
    res = resources if isinstance(resources, dict) else _fetch_bridge_resources()
    p_cnt = int(res.get("active_agent_profiles_count", len(res.get("active_agent_profiles") or [])))
    p_max = int(res.get("max_agent_profiles", 3))
    t_cnt = int(res.get("active_agent_tabs", 0))
    t_max = int(res.get("max_agent_tabs", 6))
    return f"Agent Fleet Budget: Profiles [{p_cnt}/{p_max}] | Tabs [{t_cnt}/{t_max}] (User tabs & windows strictly protected)"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.panel and (
        args.status or args.usage or args.api or args.allow_paid_api_fallback or args.task or args.deep_research
        or args.mode != "chat" or args.surface == "web" or args.model or args.profile or args.system
        or args.system_skill or args.continue_session or args.keep_tab or args.new_tab or args.search == "on"
        or args.code_exec == "on" or args.url_context == "on" or args.attach_offload or args.full_offload
        or args.attach_chat is not None or args.auto_context or args.compress or args.session_id
        or args.thinking != "High" or args.blind
    ):
        parser.error("--panel uses dedicated AI Studio roles and explicit file/code context. Remove conflicting options.")

    if args.status:
        if get_live_profile_status:
            stat = get_live_profile_status()
            res = _fetch_bridge_resources()
            if args.json:
                print(json.dumps({"agent_fleet_budget": res, "profiles": stat}, indent=2))
            else:
                banner = format_status_banner(res)
                rows = "\n".join(
                    f"{p:<11} | {d.get('tier_bucket'):<19} | {d.get('status'):<8} | ext={d.get('has_bridge_extension')} | {d.get('email')}"
                    for p, d in stat.items()
                )
                print(f"\n{banner}\n{rows}\n")
        sys.exit(0)

    if args.usage:
        driver = GeminiBrainDriver(default_profile=args.profile)
        prof = args.profile or "Profile 13"
        print(json.dumps(driver.get_usage_limit(profile=prof), indent=2))
        sys.exit(0)

    prompt_text = args.prompt or args.question_flag
    if args.prompt_file:
        p_path = Path(args.prompt_file)
        if not p_path.exists():
            print(f"Error: Prompt file '{args.prompt_file}' not found.", file=sys.stderr)
            sys.exit(1)
        prompt_text = p_path.read_text(encoding="utf-8")
    elif prompt_text and prompt_text.startswith("@") and len(prompt_text) > 1 and Path(prompt_text[1:]).exists():
        prompt_text = Path(prompt_text[1:]).read_text(encoding="utf-8")
    elif not prompt_text and not sys.stdin.isatty():
        prompt_text = sys.stdin.read().strip()

    if not prompt_text:
        parser.print_help()
        sys.exit(1)

    if args.panel:
        try:
            project_root = _resolve_project_root(args.project)
            if args.project and not Path(args.project).is_dir():
                from resolve_skill_overlay import resolve_project
                _, project_root = resolve_project(args.project)
            panel = run_consultation_panel(
                preset=args.panel, prompt=prompt_text, project_root=project_root, files=args.files,
                pack_specs=args.pack, output=Path(args.output) if args.output else None,
                max_output_tokens=args.max_output_tokens, dry_run=args.dry_run,
            )
        except (ValueError, OSError) as error:
            parser.exit(1, f"Error: {error}\n")
        print(json.dumps(panel, indent=2) if args.json or args.dry_run else
              f"Panel {panel['status']}: {panel['manifest']}")
        sys.exit(0 if panel["ok"] else 1)

    project_root = _resolve_project_root(args.project)
    system_skill = args.system_skill or ("falsifier_blind" if args.blind else None)

    if args.council:
        import cognitive_orchestrator as co
        c_res = co.run_adversarial_council(
            topic_or_prompt=prompt_text,
            mode=args.council,
            files=args.files,
            project_root=project_root,
            rounds=args.rounds,
            dry_run=args.dry_run,
            out_path=Path(args.output) if args.output else None,
            profile=args.profile,
        )
        print(json.dumps(c_res, indent=2) if (args.json or args.dry_run) else c_res.get("response", ""))
        sys.exit(0 if c_res.get("ok") else 1)

    route = resolve_consult_surface(
        surface=args.surface,
        deep_research=args.deep_research,
        task_mode=args.task,
        mode=args.mode,
        model=args.model,
    )

    scrubbed_prompt, attached_files, ctx_tel = build_composable_context(
        prompt=prompt_text,
        project_root=project_root,
        explicit_project=args.project,
        files=args.files,
        pack_specs=args.pack,
        fresh=args.fresh,
        attach_offload=args.attach_offload,
        full_offload=args.full_offload,
        attach_chat=args.attach_chat,
        blind=args.blind,
        auto_context=args.auto_context,
        compress=args.compress,
        session_id=args.session_id,
        dry_run=args.dry_run,
    )

    if args.dry_run:
        preview = {
            "ok": True,
            "dry_run": True,
            "route": route,
            "system_skill": system_skill,
            "max_output_tokens": args.max_output_tokens,
            "tools": {"search": args.search == "on", "code_exec": args.code_exec == "on", "url_context": args.url_context == "on"},
            "context": ctx_tel,
            "prompt_preview": scrubbed_prompt[:240],
        }
        print(json.dumps(preview, indent=2))
        sys.exit(0)

    if args.api:
        result = consult_argon_api(
            prompt=scrubbed_prompt,
            files=attached_files or None,
            thinking=args.thinking,
            output_path=args.output,
            allow_paid_api_fallback=args.allow_paid_api_fallback,
        )
    else:
        should_clean = False if args.continue_session and "--clean" not in sys.argv and "--delete" not in sys.argv else args.clean
        result = consult_with_dedupe(
            project_root,
            prompt=scrubbed_prompt,
            surface=route["surface"],
            model=route["model"],
            mode=route["mode"],
            thinking=args.thinking,
            files=attached_files or None,
            system_skill=system_skill,
            system_instructions=args.system,
            search=(args.search == "on"),
            code_exec=(args.code_exec == "on"),
            url_context=(args.url_context == "on"),
            max_output_tokens=args.max_output_tokens,
            deep_research=args.deep_research,
            profile=args.profile,
            session_id=args.session_id,
            continue_session=args.continue_session,
            own_tab=args.new_tab,
            auto_clean=should_clean,
            keep_tab=args.keep_tab,
            output_path=args.output,
            allow_paid_api_fallback=args.allow_paid_api_fallback,
        )

    result["context_telemetry"] = ctx_tel
    if args.json:
        print(json.dumps(result, indent=2))
    elif result.get("ok"):
        print(result.get("response", ""))
    else:
        print(f"Error: {result.get('error')}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
