"""Resolve a registered project's typed tuning for a canonical Brain skill."""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path, PureWindowsPath
from urllib.parse import urlsplit


SKILL_ROOT = Path(__file__).resolve().parents[1]
BRAIN_ROOT = SKILL_ROOT.parents[2]
SLUG = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")
PROJECT_ROW = re.compile(r"^\|\s*\*\*`([^ `]+)`[^|]*\|[^|]*\|\s*`([^`]+)`\s*\|")


class OverlayError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def registered_projects(brain_root=BRAIN_ROOT):
    brain_root = Path(brain_root).resolve()
    projects = {"brain": brain_root}
    for line in (brain_root / "project_map.md").read_text(encoding="utf-8-sig").splitlines():
        match = PROJECT_ROW.match(line)
        if match and match[1].casefold() != "brain":
            if match[1].casefold() in {slug.casefold() for slug in projects}:
                raise OverlayError("invalid_registry", f"Duplicate project slug: {match[1]}")
            projects[match[1]] = Path(match[2]).resolve()
    return projects


def resolve_project(project=None, workspaces=(), *, cwd=None, brain_root=BRAIN_ROOT):
    projects = registered_projects(brain_root)
    if project:
        project_path = Path(project).resolve()
        for slug, root in projects.items():
            if slug.casefold() == str(project).casefold() or root == project_path:
                if not root.is_dir():
                    raise OverlayError("missing_project", f"Registered project is unavailable: {slug}")
                return slug, root
        raise OverlayError("unknown_project", f"Unregistered project: {project}")

    def containing_project(path):
        path = Path(path).resolve()
        matches = [(slug, root) for slug, root in projects.items() if path.is_relative_to(root)]
        return max(matches, key=lambda pair: len(pair[1].parts)) if matches else None

    matches = {
        match for workspace in workspaces if workspace
        if (match := containing_project(workspace)) is not None
    }
    projects_only = sorted(match for match in matches if match[0] != "brain")
    if len(projects_only) > 1:
        raise OverlayError("ambiguous_project", f"Select --project from: {', '.join(slug for slug, _ in projects_only)}")
    if projects_only:
        return projects_only[0]
    if workspaces and matches == {("brain", projects["brain"])}:
        if all(Path(path).resolve().is_relative_to(projects["brain"]) for path in workspaces if path):
            return "brain", projects["brain"]
        raise OverlayError("unknown_project", "Brain is attached to an unregistered workspace. Select --project.")
    match = containing_project(cwd or Path.cwd()) if not workspaces else None
    if match:
        return match
    raise OverlayError("unknown_project", "Select a registered --project or supply registered --workspaces.")


def relative_path(root, value):
    if not isinstance(value, str) or not value or "\0" in value:
        raise OverlayError("invalid_path", "Expected a nonempty project-relative path.")
    windows = PureWindowsPath(value)
    parts = value.replace("\\", "/").split("/")
    if windows.anchor or ".." in parts or ":" in value:
        raise OverlayError("invalid_path", f"Expected a project-relative path: {value}")
    resolved = (root / Path(*parts)).resolve()
    if not resolved.is_relative_to(root):
        raise OverlayError("path_escape", f"Path escapes the project: {value}")
    return resolved


def _yaml(raw, label):
    # YAML is only needed for projects that actually use an overlay or profile.
    try:
        import yaml
    except ImportError as error:
        raise OverlayError("missing_dependency", "Install PyYAML to read configured overlays.") from error

    class UniqueLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            result = super().construct_mapping(node, deep)
            if len(result) != len(node.value):
                raise ValueError("duplicate mapping key")
            return result

    try:
        document = yaml.load(raw, Loader=UniqueLoader)
    except (ValueError, yaml.YAMLError) as error:
        # YAML diagnostics can quote input values. Keep them out of host logs.
        raise OverlayError("invalid_yaml", f"Malformed YAML in {label}.") from error
    if not isinstance(document, dict):
        raise OverlayError("invalid_schema", f"Expected a mapping in {label}.")
    return document


def _schema(root):
    file = root / ".agents/skills/auto-skill/references/overlay_schemas.json"
    return json.loads(file.read_text(encoding="utf-8"))


def _document(data, slug, allowed, *, skill=None):
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise OverlayError("invalid_schema", "Expected schema_version: 1.")
    if data.get("project") != slug or (skill is not None and data.get("skill") != skill):
        raise OverlayError("identity_mismatch", "Overlay or profile project/skill does not match its destination.")
    unknown = data.keys() - allowed
    if unknown:
        raise OverlayError("invalid_schema", f"Unknown document field: {sorted(str(key) for key in unknown)[0]}")


def _validate_settings(settings, rules, root):
    if not isinstance(settings, dict):
        raise OverlayError("invalid_setting", "settings must be a mapping.")
    for name, value in settings.items():
        kind = rules.get(name)
        if kind == "boolean" and type(value) is bool:
            continue
        if not isinstance(value, str) or len(value) > 256:
            raise OverlayError("invalid_setting", f"Invalid setting: {name}")
        if kind == "id" and SLUG.fullmatch(value):
            continue
        if kind == "path":
            relative_path(root, value)
            continue
        if kind == "local_url":
            try:
                url = urlsplit(value)
                if (
                    url.scheme in {"http", "https"} and url.hostname in {"localhost", "127.0.0.1", "::1"}
                    and url.username is None and url.password is None and not url.query and not url.fragment
                    and not re.search(r"[\s`'\"|;&<>$]", value)
                ):
                    url.port  # Reject invalid ports.
                    continue
            except ValueError:
                pass
        if isinstance(kind, list) and value in kind:
            continue
        raise OverlayError("invalid_setting", f"Unknown or invalid setting: {name}")


def _read_bytes(path, limit):
    with path.open("rb") as file:
        raw = file.read(limit + 1)
    if len(raw) > limit:
        raise OverlayError("invalid_schema", f"{path.name} exceeds {limit} bytes.")
    return raw


def _overlay_data(raw, skill, slug):
    raw = raw.removeprefix(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
    match = re.fullmatch(rb"---\n(.*?)\n---(?:\n(.*))?", raw, re.DOTALL)
    if not match:
        raise OverlayError("invalid_schema", f"{skill}.md needs YAML frontmatter.")
    body = match[2] or b""
    if len(body) > 2048:
        raise OverlayError("invalid_schema", f"{skill}.md body exceeds 2,048 bytes.")
    data = _yaml(match[1], f"{skill}.md")
    _document(data, slug, {"schema_version", "project", "skill", "settings", "references"}, skill=skill)
    return data, body.decode("utf-8").strip()


def overlay_digest(root, skill, canonical, profile_raw, overlay_raw):
    digest = hashlib.sha256()
    inputs = (
        os.path.normcase(str(root)).encode("utf-8"), skill.encode("utf-8"),
        canonical.read_bytes(), profile_raw, overlay_raw,
    )
    for value in inputs:
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def overlay_file_ticket(slug, root, skill, canonical):
    """Describe a present overlay without parsing it in a read hook."""
    profile = relative_path(root, ".agents/project_profile.yaml")
    overlay = relative_path(root, f".agents/skill_overlays/{skill}.md")
    if not overlay.is_file():
        return None
    profile_raw = _read_bytes(profile, 8192) if profile.is_file() else b""
    overlay_raw = _read_bytes(overlay, 8192)
    return {
        "project": slug, "skill": skill, "overlay_path": str(overlay),
        "digest": overlay_digest(root, skill, canonical, profile_raw, overlay_raw),
    }


def resolve_overlay(slug, root, skill, *, brain_root=BRAIN_ROOT, template=None):
    root = Path(root).resolve()
    brain_root = Path(brain_root).resolve()
    schemas = _schema(brain_root)
    if skill not in schemas:
        raise OverlayError("unknown_skill", f"Unknown universal skill: {skill}")
    canonical = brain_root / ".agents/skills" / skill / "SKILL.md"
    if not canonical.is_file():
        raise OverlayError("missing_skill", f"Canonical skill file is unavailable: {skill}")
    profile = relative_path(root, ".agents/project_profile.yaml")
    overlay = relative_path(root, f".agents/skill_overlays/{skill}.md")
    profile_exists = profile.is_file()
    profile_raw = _read_bytes(profile, 8192) if profile_exists else b""
    settings = {}
    if profile_exists:
        data = _yaml(profile_raw, "project_profile.yaml")
        _document(data, slug, {"schema_version", "project", "settings"})
        profile_settings = data.get("settings", {})
        all_rules = {key: rule for skill_rules in schemas.values() for key, rule in skill_rules.items()}
        _validate_settings(profile_settings, all_rules, root)
        settings = {key: value for key, value in profile_settings.items() if key in schemas[skill]}
    references = []
    body = ""
    source = Path(template) if template else overlay
    exists = source.is_file()
    overlay_raw = _read_bytes(source, 8192) if exists else b""
    if exists:
        data, body = _overlay_data(overlay_raw, skill, slug)
        overrides = data.get("settings", {})
        _validate_settings(overrides, schemas[skill], root)
        settings.update(overrides)
        declared = data.get("references", [])
        if not isinstance(declared, list) or len(declared) > 12:
            raise OverlayError("invalid_path", "references must be a list of at most 12 project-relative paths.")
        references = [str(relative_path(root, path)) for path in declared]
    return {
        "schema_version": 1,
        "project": slug,
        "project_root": str(root),
        "skill": skill,
        "canonical_path": str(canonical),
        "overlay_path": str(overlay) if exists else None,
        "settings": settings,
        "references": references,
        "digest": overlay_digest(root, skill, canonical, profile_raw, overlay_raw),
        "body": body,
    }


def list_overlays(slug, root, *, brain_root=BRAIN_ROOT):
    directory = relative_path(root, ".agents/skill_overlays")
    return [resolve_overlay(slug, root, path.stem, brain_root=brain_root)
            for path in sorted(directory.glob("*.md"))]


def require_project_overlay(project_arg, skill_slug, optional_fallback=True, *, brain_root=BRAIN_ROOT):
    """Resolve an activation payload or report a missing required project overlay."""
    slug, root = resolve_project(project_arg, brain_root=brain_root)
    payload = resolve_overlay(slug, root, skill_slug, brain_root=brain_root)
    if payload["overlay_path"] is None and not optional_fallback:
        raise OverlayError("missing_overlay", f"Project {slug} has no overlay for {skill_slug}.")
    return payload


def install_overlays(slug, root, *, dry_run=False, brain_root=BRAIN_ROOT):
    templates = Path(brain_root) / ".agents/skills/auto-skill/templates/project_overlays" / slug
    entries = []
    for template in sorted(templates.glob("*.md")):
        payload = resolve_overlay(slug, root, template.stem, brain_root=brain_root, template=template)
        destination = Path(payload["overlay_path"])
        raw = template.read_bytes()
        if destination.exists() and not destination.is_file():
            raise OverlayError("install_conflict", f"Expected an overlay file at {destination}.")
        status = "unchanged" if destination.is_file() and destination.read_bytes() == raw else (
            "kept_existing" if destination.is_file() else "would_install" if dry_run else "installed"
        )
        entries.append((template, destination, raw, status, payload["digest"]))
    if not entries:
        raise OverlayError("missing_templates", f"No templates are available for {slug}.")
    if not dry_run:
        for _, destination, raw, status, _ in entries:
            if status == "installed":
                destination.parent.mkdir(parents=True, exist_ok=True)
                try:
                    with destination.open("xb") as file:
                        file.write(raw)
                except FileExistsError as error:
                    raise OverlayError("install_conflict", f"An overlay appeared concurrently at {destination}.") from error
    return [{"path": str(destination), "status": status, "template_digest": digest}
            for _, destination, _, status, digest in entries]


def _markdown(payload):
    lines = [f"## {payload['project']} / {payload['skill']}", f"Canonical skill: {payload['canonical_path']}"]
    if payload["overlay_path"]:
        lines.extend((f"Overlay: {payload['overlay_path']}", f"Digest: {payload['digest']}"))
    else:
        lines.append("Project overlay: absent. Use canonical defaults with any supported profile settings.")
    if payload["settings"]:
        lines.append("Settings: " + json.dumps(payload["settings"], sort_keys=True, ensure_ascii=False))
    if payload["references"]:
        lines.extend(("Project references:", *(f"- {path}" for path in payload["references"])))
    if payload["body"]:
        lines.extend(("", payload["body"]))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", help="Registered project root or slug")
    parser.add_argument("--workspaces", help="Semicolon-separated workspace roots")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--skill", help="Canonical skill slug")
    actions.add_argument("--list", action="store_true", help="List active project overlays")
    actions.add_argument("--validate-all", action="store_true", help="Validate active overlays across registered projects")
    actions.add_argument("--install-overlays", action="store_true", help="Install missing templates without overwriting existing overlays")
    fmt = parser.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="Machine-readable output")
    fmt.add_argument("--markdown", action="store_true", help="Render skill resolution as Markdown (default for --skill)")
    parser.add_argument("--dry-run", action="store_true", help="Preview template installation without writes")
    args = parser.parse_args(argv)
    if args.dry_run and not args.install_overlays:
        parser.error("--dry-run requires --install-overlays")
    if args.install_overlays and not args.project:
        parser.error("--install-overlays requires an explicit --project")
    try:
        if args.validate_all:
            projects = registered_projects()
            payload = {
                "schema_version": 1,
                "projects": [
                    {"project": slug, "available": root.is_dir(),
                     "overlays": list_overlays(slug, root) if root.is_dir() else []}
                    for slug, root in projects.items()
                ],
            }
        else:
            workspaces = tuple(path.strip() for path in (args.workspaces or "").split(";") if path.strip())
            slug, root = resolve_project(args.project, workspaces)
            payload = {"schema_version": 1, "project": slug, "project_root": str(root)}
            if args.skill:
                payload = resolve_overlay(slug, root, args.skill)
            elif args.list:
                payload["overlays"] = list_overlays(slug, root)
            else:
                payload["install"] = install_overlays(slug, root, dry_run=args.dry_run)
        if args.skill and not args.json:
            print(_markdown(payload))
        else:
            print(json.dumps(payload, ensure_ascii=True, indent=2))
        return 0
    except (OverlayError, OSError, UnicodeError, ValueError) as error:
        code = error.code if isinstance(error, OverlayError) else "read_error"
        print(json.dumps({"error": {"code": code, "message": str(error)}}), file=sys.stdout if args.json else sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
