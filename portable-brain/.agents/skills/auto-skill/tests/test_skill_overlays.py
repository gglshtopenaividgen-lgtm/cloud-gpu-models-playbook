import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


AUTO_SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO_SKILL / "scripts"))
import resolve_skill_overlay as resolver


class OverlayFixture(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.workspace = Path(fixture.name)
        self.brain = self.workspace / "brain"
        self.project = self.workspace / "hi"
        self.other = self.workspace / "AWAKEN1"
        self.project.mkdir()
        self.other.mkdir()
        map_path = self.brain / "project_map.md"
        self.write(map_path, f"| **`hi` (Cloud GPU)** | Lab | `{self.project}` | Map |\n"
                             f"| **`AWAKEN1`** (formerly `krpg`) | Game | `{self.other}` | Map |\n")
        schema = ".agents/skills/auto-skill/references/overlay_schemas.json"
        self.write(self.brain / schema, (resolver.BRAIN_ROOT / schema).read_text(encoding="utf-8"))
        for name in ("deep-thinking", "external-resource"):
            self.write(self.brain / f".agents/skills/{name}/SKILL.md", f"# {name}")
        self.destination = self.project / ".agents/skill_overlays/deep-thinking.md"

    @staticmethod
    def write(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def overlay(self, *, project="hi", skill="deep-thinking", body="Project review guidance.", fields=""):
        return (f"---\nschema_version: 1\nproject: {project}\nskill: {skill}\n"
                f"{fields}---\n\n{body}\n")

    def resolve(self):
        return resolver.resolve_overlay("hi", self.project, "deep-thinking", brain_root=self.brain)

    def test_merge_profile_overlay_and_resolve_normalized_references(self):
        self.write(self.project / ".agents/project_profile.yaml",
                   "schema_version: 1\nproject: hi\nsettings:\n  review_mode: research\n"
                   "  verify_cmd: lab-tests\n  workload_profile: lab\n")
        self.write(self.destination, self.overlay(fields="settings:\n  review_mode: architecture\nreferences:\n  - context/guide.md\n"))
        result = self.resolve()
        self.assertEqual(result["settings"], {"review_mode": "architecture", "verify_cmd": "lab-tests"})
        self.assertEqual(result["references"], [str((self.project / "context/guide.md").resolve())])
        self.assertEqual(result["body"], "Project review guidance.")
        self.assertEqual(result["digest"], self.resolve()["digest"])
        self.write(self.destination, self.overlay(body="Updated."))
        self.assertNotEqual(result["digest"], self.resolve()["digest"])

    def test_missing_overlay_uses_defaults(self):
        payload = self.resolve()
        self.assertIsNone(payload["overlay_path"])
        self.assertEqual(payload["settings"], {})
        self.assertEqual(resolver.list_overlays("hi", self.project, brain_root=self.brain), [])

    def test_require_project_overlay_resolves_or_reports_absence(self):
        with self.assertRaises(resolver.OverlayError) as error:
            resolver.require_project_overlay("hi", "deep-thinking", False, brain_root=self.brain)
        self.assertEqual(error.exception.code, "missing_overlay")
        self.write(self.destination, self.overlay())
        payload = resolver.require_project_overlay(self.project, "deep-thinking", False, brain_root=self.brain)
        self.assertEqual(payload, self.resolve())
        self.write(Path(payload["canonical_path"]), "# Updated canonical instructions")
        self.assertNotEqual(payload["digest"], self.resolve()["digest"])

    def test_skill_read_hook_logs_ticket_and_leaves_unrelated_reads_alone(self):
        hook_path = resolver.BRAIN_ROOT / ".agents/hooks/session_overlay_hook.py"
        spec = importlib.util.spec_from_file_location("session_overlay_hook", hook_path)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        self.write(self.destination, self.overlay())
        payload = {
            "hookEventName": "PreToolUse", "workspacePaths": [str(self.brain), str(self.project)],
            "toolCall": {"name": "read_file", "args": {"AbsolutePath": str(self.brain / ".agents/skills/deep-thinking/SKILL.md")}},
        }
        log = io.StringIO()
        with mock.patch.object(hook, "BRAIN_ROOT", self.brain), redirect_stderr(log):
            self.assertEqual(hook.handle(payload), {"decision": "allow"})
            payload["toolCall"]["args"]["AbsolutePath"] = str(self.destination)
            self.assertEqual(hook.handle(payload), {"decision": "allow"})
        ticket = json.loads(log.getvalue())
        self.assertEqual(ticket["digest"], self.resolve()["digest"])
        self.assertEqual(ticket["overlay_path"], str(self.destination))

    def test_invalid_data_and_identity(self):
        examples = (
            (self.overlay(project="AWAKEN1"), "identity_mismatch"),
            (self.overlay(skill="external-resource"), "identity_mismatch"),
            (self.overlay(fields="settings: [\n"), "invalid_yaml"),
            (self.overlay(fields="project: hi\n"), "invalid_yaml"),
            (self.overlay(fields="settings:\n  verify_cmd: 'npm run && echo wrong'\n"), "invalid_setting"),
            (self.overlay(fields="settings:\n  permit_cloud_spend: true\n"), "invalid_setting"),
            (self.overlay(body="á" * 1025), "invalid_schema"),
            (self.overlay().replace("schema_version: 1", "schema_version: true"), "invalid_schema"),
        )
        for content, error_code in examples:
            with self.subTest(error_code=error_code, content=content[:80]):
                self.write(self.destination, content)
                with self.assertRaises(resolver.OverlayError) as error:
                    self.resolve()
                self.assertEqual(error.exception.code, error_code)

    def test_traversal_rejected(self):
        for path in ("../outside.md", "..\\outside.md", "C:\\outside.md", "/outside.md", "C:outside.md"):
            with self.subTest(path=path):
                with self.assertRaises(resolver.OverlayError):
                    resolver.relative_path(self.project, path)

    def test_escape_through_link_or_windows_junction(self):
        link = self.project / "escape"
        if os.name == "nt":
            result = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(self.other)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(link.rmdir)
        else:
            link.symlink_to(self.other, target_is_directory=True)
        self.write(self.destination, self.overlay(fields="references:\n  - escape/guide.md\n"))
        with self.assertRaises(resolver.OverlayError) as error:
            self.resolve()
        self.assertEqual(error.exception.code, "path_escape")

    def test_cofolder_disambiguation(self):
        self.assertEqual(resolver.resolve_project(workspaces=[self.brain, self.project], brain_root=self.brain),
                         ("hi", self.project.resolve()))
        self.assertEqual(resolver.resolve_project("awaken1", [self.brain, self.project, self.other], brain_root=self.brain),
                         ("AWAKEN1", self.other.resolve()))
        with self.assertRaises(resolver.OverlayError) as error:
            resolver.resolve_project(workspaces=[self.brain, self.project, self.other], brain_root=self.brain)
        self.assertEqual(error.exception.code, "ambiguous_project")
        with self.assertRaises(resolver.OverlayError) as error:
            resolver.resolve_project(workspaces=[self.brain, self.workspace / "unknown"], brain_root=self.brain)
        self.assertEqual(error.exception.code, "unknown_project")

    def test_install_preview_and_preserve_existing_overlay(self):
        template = self.brain / ".agents/skills/auto-skill/templates/project_overlays/hi/deep-thinking.md"
        self.write(template, self.overlay())
        preview = resolver.install_overlays("hi", self.project, dry_run=True, brain_root=self.brain)
        self.assertEqual(preview[0]["status"], "would_install")
        self.assertFalse(self.destination.exists())
        result = resolver.install_overlays("hi", self.project, brain_root=self.brain)
        self.assertEqual(result[0]["status"], "installed")
        self.assertEqual(self.resolve()["digest"], result[0]["template_digest"])
        content = self.overlay(body="User owns this local revision.")
        self.write(self.destination, content)
        result = resolver.install_overlays("hi", self.project, brain_root=self.brain)
        self.assertEqual(result[0]["status"], "kept_existing")
        self.assertEqual(self.destination.read_text(encoding="utf-8"), content)


if __name__ == "__main__":
    unittest.main()
