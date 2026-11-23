"""Exercise panel dispatch using fake bridge capacity and role responses."""

import contextlib
import io
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import consult_argon as consult


def resources(profiles=0, tabs=0):
    return {"ok": True, "max_agent_profiles": 3, "max_agent_tabs": 6,
            "active_agent_profiles_count": profiles, "active_agent_tabs": tabs}


class PanelTests(unittest.TestCase):
    def setUp(self):
        workspace = tempfile.TemporaryDirectory()
        self.addCleanup(workspace.cleanup)
        self.root = Path(workspace.name)

    def test_dry_run_cli_manifest_redacts_and_performs_no_dispatch_or_write(self):
        secret = "fixture_secret_927"
        (self.root / ".env").write_text(f"KEY={secret}\n", encoding="utf-8")
        (self.root / "prompt.txt").write_text("Analyze the migration.", encoding="utf-8")
        (self.root / "input.txt").write_text(f"Secret value {secret}\n", encoding="utf-8")
        (self.root / "example.py").write_text("def check():\n    return True\n", encoding="utf-8")
        stdout = io.StringIO()
        argv = ["consult_argon.py", "--panel", "architecture", "--project", str(self.root),
                "--prompt-file", str(self.root / "prompt.txt"), "-f", "input.txt",
                "--pack", "example.py#check", "--dry-run"]
        with (
            patch.object(sys, "argv", argv),
            patch.object(consult, "run_single_consultation") as runner,
            patch.object(consult, "_fetch_bridge_resources") as fetch,
            contextlib.redirect_stdout(stdout),
            self.assertRaises(SystemExit) as exit_code,
        ):
            consult.main()
        self.assertEqual(exit_code.exception.code, 0)
        manifest = json.loads(stdout.getvalue())
        self.assertTrue(manifest["ok"])
        self.assertEqual(manifest["status"], "planned")
        self.assertEqual(manifest["max_workers"], 2)
        self.assertEqual(manifest["redaction_count"], 1)
        self.assertEqual([role["name"] for role in manifest["roles"]], ["argon-architect", "neon-critic"])
        self.assertFalse(Path(manifest["manifest"]).exists())
        self.assertFalse(Path(manifest["context_bundle"]).exists())
        self.assertNotIn(secret, stdout.getvalue())
        runner.assert_not_called()
        fetch.assert_not_called()

    def test_parallel_roles_share_one_bundle_and_preserve_disagreement(self):
        rendezvous = threading.Barrier(2, timeout=2)
        (self.root / ".env").write_text("FIXTURE=fixture_secret_927\n", encoding="utf-8")
        (self.root / "input.txt").write_text("Content fixture_secret_927\n", encoding="utf-8")

        def run(**role):
            self.assertEqual(role["surface"], "aistudio")
            self.assertEqual(len(role["files"]), 1)
            context = Path(role["files"][0]).read_text(encoding="utf-8")
            self.assertIn("Content [REDACTED_ENV_SECRET]", context)
            self.assertNotIn("fixture_secret_927", context)
            rendezvous.wait()
            if role["model"] == "gemini-4-argon":
                return {"ok": True, "response": "Recommendation: Move forward."}
            return {"ok": True, "response": "Recommendation: Pause migration."}

        with patch.object(consult, "_fetch_bridge_resources", return_value=resources()), \
             patch.object(consult, "run_single_consultation", side_effect=run) as runner:
            result = consult.run_consultation_panel("review", "Task", self.root, files=["input.txt"])
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["workers"], 2)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(len({tuple(call.kwargs["files"]) for call in runner.call_args_list}), 1)
        self.assertEqual(len({call.kwargs["session_id"] for call in runner.call_args_list}), 2)
        report = Path(result["manifest"]).read_text(encoding="utf-8")
        self.assertIn("Recommendation: Move forward.", report)
        self.assertIn("Recommendation: Pause migration.", report)
        self.assertTrue(all(Path(role["output"]).is_file() for role in result["roles"]))

    def test_one_profile_slot_runs_serially_and_records_partial_failure(self):
        ordered = []

        def run(**role):
            ordered.append(role["model"])
            if role["model"] == "gemini-4-neon":
                raise RuntimeError("Fixture role unavailable")
            return {"ok": True, "text": "Argon recommendation."}

        output = self.root / "review.md"
        with patch.object(consult, "_fetch_bridge_resources", return_value=resources(profiles=2)), \
             patch.object(consult, "run_single_consultation", side_effect=run):
            result = consult.run_consultation_panel("critic", "Critique the plan.", self.root, output=output)
        self.assertEqual(ordered, ["gemini-4-neon", "gemini-4-argon"])
        self.assertEqual(result["workers"], 1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "partial")
        manifest = output.read_text(encoding="utf-8")
        self.assertIn("Fixture role unavailable", manifest)
        self.assertIn("Argon recommendation.", manifest)

    def test_no_tab_capacity_skips_all_roles(self):
        with patch.object(consult, "_fetch_bridge_resources", return_value=resources(tabs=6)), \
             patch.object(consult, "run_single_consultation") as runner:
            result = consult.run_consultation_panel("architecture", "Task", self.root)
        runner.assert_not_called()
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["workers"], 0)


if __name__ == "__main__":
    unittest.main()
