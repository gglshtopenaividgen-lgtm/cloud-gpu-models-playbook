"""Antigravity mirror migration tests against temporary roots."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import dedupe_antigravity_mirrors as dedupe


class MirrorTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.workspace = Path(fixture.name)
        self.brain = self.workspace / "brain"
        self.gemini = self.workspace / ".gemini"
        self.archive = self.workspace / "vault"
        self.archive.mkdir()
        self.canonical = self.brain / ".agents/skills"
        self.codex = self.workspace / ".agents/skills/auto-skill"
        self.write(self.codex / "SKILL.md", "Unrelated to migration")
        for name in dedupe.MANAGED_SKILLS:
            self.write(self.canonical / name / "SKILL.md", name)
        self.config = self.gemini / "config/skills.json"
        self.config_mirror = self.gemini / "config/skills/auto-skill"
        self.legacy = self.gemini / "config/skills/batch-asset-generator"
        self.builtin_mirror = self.gemini / "antigravity/builtin/skills/offload"
        self.runtime_mirror = self.gemini / "antigravity/skills/full-sync"
        self.genuine = self.gemini / "antigravity/builtin/skills/run-workflow"
        self.unrelated = self.gemini / "config/skills/private-skill"
        self.mirrors = (self.config_mirror, self.legacy, self.builtin_mirror, self.runtime_mirror)
        for directory in (*self.mirrors, self.genuine, self.unrelated):
            self.write(directory / "SKILL.md", directory.name)
        self.data = {
            "$schema": "known-schema",
            "entries": [{"path": self.config_mirror.parent.as_posix(), "mode": "existing"},
                        {"path": self.runtime_mirror.parent.as_posix()},
                        {"path": (self.workspace / "unrelated").as_posix()}],
            "skills": [
                {"name": path.name, "path": path.as_posix(), "enabled": path != self.builtin_mirror}
                for path in (self.config_mirror, self.builtin_mirror, self.genuine, self.unrelated)
            ],
        }
        self.original = json.dumps(self.data, separators=(",", ":")).encode()
        self.config.write_bytes(self.original)

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def preview(self):
        return dedupe.build_plan(self.brain, self.gemini, self.archive)

    def apply(self):
        return dedupe.apply_cutover(self.brain, self.gemini, self.archive)

    def test_preview_targets_only_named_mirrors_and_preserves_custom_config(self):
        plan, original, replacement = self.preview()
        self.assertEqual({Path(item["source"]) for item in plan["moves"]}, set(self.mirrors))
        self.assertEqual(original, self.original)
        rewritten = json.loads(replacement)
        self.assertEqual(rewritten["$schema"], self.data["$schema"])
        self.assertIn(self.data["entries"][0], rewritten["entries"])
        self.assertIn(self.data["entries"][2], rewritten["entries"])
        self.assertNotIn(self.data["entries"][1], rewritten["entries"])
        self.assertTrue(all(item in rewritten["skills"] for item in self.data["skills"][2:]))
        self.assertIn({"name": "offload", "path": (self.canonical / "offload").as_posix(), "enabled": False},
                      rewritten["skills"])
        self.assertTrue(all(source.exists() for source in self.mirrors))
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(list(self.archive.iterdir()), [])
        self.assertFalse((self.gemini / ".brain-skill-dedupe.lock").exists())

    def test_cutover_rollback_and_replay(self):
        manifest = self.apply()
        plan = json.loads(manifest.read_text(encoding="utf-8"))
        self.assertEqual(plan["status"], "applied")
        self.assertEqual((manifest.parent / "skills.json.before").read_bytes(), self.original)
        self.assertTrue(all(not path.exists() for path in self.mirrors))
        self.assertTrue(all(Path(item["backup"]).is_dir() for item in plan["moves"]))
        self.assertTrue(all(path.is_dir() for path in (self.genuine, self.unrelated, self.codex)))
        self.assertIsNone(self.apply())
        # Remove one local holding tree in the isolated fixture to exercise the D: backup route.
        missing = Path(plan["moves"][0]["holding"])
        (missing / "SKILL.md").unlink()
        missing.rmdir()
        dedupe.rollback(manifest, self.gemini, self.archive)
        dedupe.rollback(manifest, self.gemini, self.archive)
        self.assertTrue(all(path.is_dir() for path in self.mirrors))
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["status"], "rolled_back")

    def test_rollback_refuses_configuration_drift(self):
        manifest = self.apply()
        self.config.write_text('{"entries":[],"new":true}', encoding="utf-8")
        with self.assertRaisesRegex(dedupe.DedupeError, "changed outside"):
            dedupe.rollback(manifest, self.gemini, self.archive)
        self.assertTrue(all(not path.exists() for path in self.mirrors))

    def test_quarantine_failure_restores_previous_paths(self):
        original_rename = Path.rename
        failing_source = self.legacy

        def rename(path, target):
            if path == failing_source:
                raise OSError("simulated rename failure")
            return original_rename(path, target)

        with patch.object(Path, "rename", rename):
            with self.assertRaisesRegex(dedupe.DedupeError, "simulated rename failure"):
                self.apply()
        self.assertTrue(all(path.is_dir() for path in self.mirrors))
        self.assertEqual(self.config.read_bytes(), self.original)
        manifest = next(self.archive.glob("*/manifest.json"))
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["status"], "rolled_back")

    def test_recover_a_transaction_interrupted_mid_quarantine(self):
        original_rename = Path.rename

        def rename(path, target):
            if path == self.legacy:
                raise KeyboardInterrupt
            return original_rename(path, target)

        with patch.object(Path, "rename", rename), self.assertRaises(KeyboardInterrupt):
            self.apply()
        self.assertFalse(self.config_mirror.exists())
        manifest = next(self.archive.glob("*/manifest.json"))
        self.assertEqual(json.loads(manifest.read_text(encoding="utf-8"))["status"], "quarantining")
        dedupe.rollback(manifest, self.gemini, self.archive)
        self.assertTrue(all(path.is_dir() for path in self.mirrors))
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_rejects_nested_windows_junction_and_never_follows_it(self):
        link = self.config_mirror / "escape"
        if os.name == "nt":
            cmd = ["cmd.exe", "/c", "mklink", "/J", str(link), str(self.genuine)]
            result = subprocess.run(cmd, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.addCleanup(link.rmdir)
        else:
            link.symlink_to(self.genuine, target_is_directory=True)
        with self.assertRaisesRegex(dedupe.DedupeError, "junction"):
            self.preview()
        self.assertTrue((self.genuine / "SKILL.md").exists())
        self.assertEqual(list(self.archive.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
