"""Preview, quarantine, and restore the managed Antigravity skill mirrors."""

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


BRAIN_ROOT = Path(__file__).resolve().parents[4]
MANAGED_SKILLS = frozenset({
    "auto-skill", "browser-operator", "deep-thinking", "document-forge",
    "exhaustive-audit-and-repair", "external-resource", "full-sync",
    "hermes-agent-core", "internal-tools", "offload", "rea", "ui-design-engine",
    "web-search-orchestrator",
})
ROOTS = {
    "config": Path("config/skills"),
    "builtin": Path("antigravity/builtin/skills"),
    "runtime": Path("antigravity/skills"),
}
LEGACY = {"batch-asset-generator", "cloud-gpu-deployment"}
RUN_NAME = re.compile(r"archive_skill_mirrors_\d{8}T\d{6}Z_[a-f0-9]{8}")


class DedupeError(ValueError):
    pass


def _names(root_id):
    return MANAGED_SKILLS | LEGACY if root_id == "config" else MANAGED_SKILLS


def _absolute(path):
    return Path(os.path.abspath(path))


def _assert_plain_path(path):
    for component in (*reversed(path.parents), path):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        _assert_not_link(component, info)


def _assert_not_link(path, info):
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise DedupeError(f"Refusing junction, symlink, or reparse point: {path}")


def _read_config(gemini_root):
    path = gemini_root / "config/skills.json"
    _assert_plain_path(path)
    return path, path.read_bytes()


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _tree_digest(root):
    _assert_plain_path(root)
    if not root.is_dir():
        raise DedupeError(f"Expected a skill directory: {root}")
    tree = hashlib.sha256()
    for current, dirs, files in os.walk(root):
        current = Path(current)
        dirs.sort()
        for name in sorted(dirs + files):
            entry = current / name
            info = entry.lstat()
            _assert_not_link(entry, info)
            rel = entry.relative_to(root).as_posix()
            if stat.S_ISDIR(info.st_mode):
                record = (rel, "directory")
            elif stat.S_ISREG(info.st_mode):
                with entry.open("rb") as file:
                    record = (rel, hashlib.file_digest(file, "sha256").hexdigest())
            else:
                raise DedupeError(f"Unsupported file in skill directory: {entry}")
            tree.update(json.dumps(record, ensure_ascii=True).encode("ascii") + b"\n")
    return tree.hexdigest()


def _copy_plain_tree(source, destination):
    def verify_directory(current, names):
        current = Path(current)
        _assert_plain_path(current)
        for name in names:
            path = current / name
            _assert_not_link(path, path.lstat())
        return []

    shutil.copytree(source, destination, symlinks=True, ignore=verify_directory)


def _config_path(item):
    value = item.get("path") if isinstance(item, dict) else None
    return _absolute(Path(value).expanduser()) if isinstance(value, str) and Path(value).expanduser().is_absolute() else None


def _rewritten_config(raw, canonical, mirrors):
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise DedupeError("skills.json must contain an object.")
    for key in ("entries", "skills"):
        if key in data and not isinstance(data[key], list):
            raise DedupeError(f"skills.json field {key} must be a list.")
    managed = {root / name for root_id, root in mirrors.items() for name in _names(root_id)}
    unused_roots = {
        root for root_id, root in mirrors.items() if root_id != "builtin"
        and (not root.exists() or all(child in managed for child in root.iterdir()))
    }
    previous = list(data.get("entries", []))
    data["entries"] = [
        item for item in previous
        if _config_path(item) not in (unused_roots | managed)
    ]
    for root in (canonical, mirrors["builtin"]):
        if not any(_config_path(item) == root for item in data["entries"]):
            data["entries"].append({"path": root.as_posix()})
    if "skills" in data:
        # Keep unrelated registrations and intentional disables. Move managed
        # disables to the canonical path so cutover preserves their policy.
        rewritten = []
        for item in data["skills"]:
            path = _config_path(item)
            if path not in managed:
                rewritten.append(item)
            elif item.get("enabled") is False and path.name in MANAGED_SKILLS:
                rewritten.append({**item, "path": (canonical / path.name).as_posix()})
        data["skills"] = rewritten
    old = json.loads(raw.decode("utf-8-sig"))
    return raw if old == data else (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _backup_dir(archive_root, run_name):
    if not RUN_NAME.fullmatch(run_name):
        raise DedupeError(f"Invalid transaction ID: {run_name}")
    target = archive_root / run_name
    _assert_plain_path(target)
    return target


def _holding_dir(gemini_root, run_name):
    return gemini_root / f".brain-skill-dedupe-{run_name}"


def build_plan(brain_root, gemini_root, archive_root):
    brain_root, gemini_root, archive_root = map(_absolute, (brain_root, gemini_root, archive_root))
    if any(a.is_relative_to(b) or b.is_relative_to(a)
           for a, b in ((gemini_root, brain_root), (gemini_root, archive_root), (brain_root, archive_root))):
        raise DedupeError("Brain, Gemini, and archive roots must be separate.")
    canonical = brain_root / ".agents/skills"
    _assert_plain_path(canonical)
    for name in sorted(MANAGED_SKILLS):
        skill = canonical / name / "SKILL.md"
        _assert_plain_path(skill)
        if not skill.is_file():
            raise DedupeError(f"Missing canonical skill: {skill}")
    mirrors = {label: gemini_root / rel for label, rel in ROOTS.items()}
    for root in mirrors.values():
        _assert_plain_path(root)
    config_path, raw = _read_config(gemini_root)
    replacement = _rewritten_config(raw, canonical, mirrors)
    run_name = datetime.now(timezone.utc).strftime("archive_skill_mirrors_%Y%m%dT%H%M%SZ_") + uuid4().hex[:8]
    archive = _backup_dir(archive_root, run_name)
    holding = _holding_dir(gemini_root, run_name)
    moves = []
    for root_id, root in mirrors.items():
        for name in sorted(_names(root_id)):
            source = root / name
            _assert_plain_path(source)
            if not source.exists():
                continue
            moves.append({
                "root_id": root_id, "skill": name, "digest": _tree_digest(source),
                "source": str(source), "backup": str(archive / "mirrors" / root_id / name),
                "holding": str(holding / root_id / name),
            })
    plan = {
        "version": 1, "run_name": run_name, "gemini_root": str(gemini_root),
        "status": "planned", "archive": str(archive), "config_path": str(config_path),
        "config_before": _sha(raw), "config_after": _sha(replacement), "moves": moves,
    }
    return plan, raw, replacement


def _atomic_write(path, data):
    _assert_plain_path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temp = Path(file.name)
        try:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
            file.close()
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def _journal(archive, plan):
    _atomic_write(archive / "manifest.json", (json.dumps(plan, indent=2) + "\n").encode("utf-8"))


@contextmanager
def _locked(gemini_root):
    path = gemini_root / ".brain-skill-dedupe.lock"
    _assert_plain_path(path)
    with path.open("a+b") as lock:
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise DedupeError("Another mirror cutover or rollback is running.") from error
        yield


def _move_paths(gemini_root, archive, plan, item):
    root_id, name = item.get("root_id"), item.get("skill")
    if root_id not in ROOTS or name not in _names(root_id):
        raise DedupeError("Manifest contains an unmanaged mirror.")
    source = gemini_root / ROOTS[root_id] / name
    backup = archive / "mirrors" / root_id / name
    holding = _holding_dir(gemini_root, plan["run_name"]) / root_id / name
    for path in (source, backup, holding):
        _assert_plain_path(path)
    return source, backup, holding


def _restore(gemini_root, archive, plan):
    config_path, current = _read_config(gemini_root)
    config_backup = archive / "skills.json.before"
    _assert_plain_path(config_backup)
    original = config_backup.read_bytes()
    current_digest = _sha(current)
    if _sha(original) != plan["config_before"] or current_digest not in {plan["config_before"], plan["config_after"]}:
        raise DedupeError("skills.json changed outside the transaction. Resolve the conflict before rollback.")
    restore = []
    for item in plan["moves"]:
        source, backup, holding = _move_paths(gemini_root, archive, plan, item)
        if source.exists():
            if _tree_digest(source) != item["digest"]:
                raise DedupeError(f"Rollback would overwrite a changed skill: {source}")
            continue
        candidate = holding if holding.exists() else backup
        if _tree_digest(candidate) != item["digest"]:
            raise DedupeError(f"Backup differs from the recorded digest: {candidate}")
        restore.append((candidate, source, candidate == holding, item["digest"]))
    for candidate, source, use_rename, digest in restore:
        _assert_plain_path(source)
        if source.exists():
            raise DedupeError(f"Skill appeared during rollback: {source}")
        source.parent.mkdir(parents=True, exist_ok=True)
        if use_rename:
            if _tree_digest(candidate) != digest:
                raise DedupeError(f"Local recovery changed during rollback: {candidate}")
            candidate.rename(source)
        else:
            # Stage on the destination volume, then publish the complete tree.
            parent = _holding_dir(gemini_root, plan["run_name"])
            parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix="restore-", dir=parent)) / "skill"
            _copy_plain_tree(candidate, stage)
            if _tree_digest(stage) != digest:
                raise DedupeError(f"Backup changed during rollback: {candidate}")
            stage.rename(source)
            stage.parent.rmdir()
    if current_digest != plan["config_before"]:
        if _sha(config_path.read_bytes()) != current_digest:
            raise DedupeError("skills.json changed during rollback.")
        _atomic_write(config_path, original)
    plan["status"] = "rolled_back"
    _journal(archive, plan)


def apply_cutover(brain_root, gemini_root, archive_root):
    gemini_root = _absolute(gemini_root)
    plan, _, _ = build_plan(brain_root, gemini_root, archive_root)
    if not plan["moves"] and plan["config_before"] == plan["config_after"]:
        return None
    with _locked(gemini_root):
        plan, original, replacement = build_plan(brain_root, gemini_root, archive_root)
        if not plan["moves"] and original == replacement:
            return None
        archive = Path(plan["archive"])
        if not archive.parent.is_dir():
            raise DedupeError(f"Archive root is unavailable: {archive.parent}")
        archive.mkdir()
        _atomic_write(archive / "skills.json.before", original)
        _atomic_write(archive / "skills.json.after", replacement)
        plan["status"] = "backing_up"
        _journal(archive, plan)
        mutated = False
        try:
            for item in plan["moves"]:
                source, backup, _ = _move_paths(gemini_root, archive, plan, item)
                backup.parent.mkdir(parents=True, exist_ok=True)
                _copy_plain_tree(source, backup)
                if _tree_digest(backup) != item["digest"]:
                    raise DedupeError(f"Mirror changed while being copied: {source}")
            plan["status"] = "quarantining"
            _journal(archive, plan)
            for item in plan["moves"]:
                source, _, holding = _move_paths(gemini_root, archive, plan, item)
                if _tree_digest(source) != item["digest"] or holding.exists():
                    raise DedupeError(f"Mirror changed before quarantine: {source}")
                holding.parent.mkdir(parents=True, exist_ok=True)
                source.rename(holding)
                mutated = True
            config_path, current = _read_config(gemini_root)
            if current != original:
                raise DedupeError("skills.json changed during cutover.")
            if original != replacement:
                _atomic_write(config_path, replacement)
                mutated = True
            plan["status"] = "applied"
            _journal(archive, plan)
        except (OSError, ValueError) as error:
            try:
                if mutated:
                    _restore(gemini_root, archive, plan)
                else:
                    plan["status"] = "aborted"
                    _journal(archive, plan)
            except (OSError, ValueError) as recovery_error:
                raise DedupeError(f"{error}. Recovery stopped: {recovery_error}. Manifest: {archive / 'manifest.json'}") from error
            raise DedupeError(f"{error}. Manifest: {archive / 'manifest.json'}") from error
        return archive / "manifest.json"


def rollback(manifest, gemini_root, archive_root):
    manifest, gemini_root, archive_root = map(_absolute, (manifest, gemini_root, archive_root))
    if manifest.name != "manifest.json" or manifest.parent.parent != archive_root:
        raise DedupeError("Choose a manifest directly under the configured archive root.")
    archive = _backup_dir(archive_root, manifest.parent.name)
    _assert_plain_path(manifest)
    with _locked(gemini_root):
        plan = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            not isinstance(plan, dict) or plan.get("version") != 1 or plan.get("run_name") != archive.name
            or plan.get("gemini_root") != str(gemini_root)
            or not isinstance(plan.get("moves"), list)
            or not all(isinstance(item, dict) for item in plan["moves"])
            or plan.get("status") not in {"quarantining", "applied", "rolled_back"}
        ):
            raise DedupeError("Manifest is invalid or cannot be rolled back.")
        _restore(gemini_root, archive, plan)


def _preview(plan, original, replacement):
    diff = "".join(difflib.unified_diff(
        original.decode("utf-8-sig").splitlines(keepends=True),
        replacement.decode("utf-8-sig").splitlines(keepends=True),
        fromfile="skills.json.before", tofile="skills.json.after",
    ))
    lines = [
        "# Antigravity skill mirror deduplication preview",
        "",
        f"- Mirrors to quarantine: {len(plan['moves'])}",
        f"- Proposed archive: `{plan['archive']}`",
        f"- Configuration: `{plan['config_path']}`",
        "- The timestamp and transaction ID are allocated again at apply time.",
        "",
        "Each mirror is copied to the archive, verified, and renamed out of discovery into local recovery storage.",
        "",
    ]
    for item in plan["moves"]:
        lines.extend((f"- `{item['source']}`", f"  - Archive: `{item['backup']}`",
                      f"  - Local recovery: `{item['holding']}`", f"  - SHA-256: `{item['digest']}`"))
    lines.extend(("", "## Proposed configuration diff", "", "```diff", diff.rstrip() or "(no changes)", "```"))
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", type=Path, metavar="MANIFEST")
    parser.add_argument("--brain-root", type=Path, default=BRAIN_ROOT)
    parser.add_argument("--gemini-root", type=Path, default=Path.home() / ".gemini")
    parser.add_argument("--archive-root", type=Path, default=Path("<AGENTIC_VAULT>"))
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable dry-run plan")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            plan, original, replacement = build_plan(args.brain_root, args.gemini_root, args.archive_root)
            if args.json:
                print(json.dumps({**plan, "replacement": json.loads(replacement.decode("utf-8-sig"))}, indent=2))
            else:
                print(_preview(plan, original, replacement), end="")
        elif args.apply:
            result = apply_cutover(args.brain_root, args.gemini_root, args.archive_root)
            print(f"Applied. Rollback manifest: {result}" if result else "No managed changes required.")
        else:
            rollback(args.rollback, args.gemini_root, args.archive_root)
            print(f"Rolled back: {args.rollback}")
        return 0
    except (KeyError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
