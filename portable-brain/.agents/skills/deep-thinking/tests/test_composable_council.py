#!/usr/bin/env python3
"""Unit tests for Wave 2C Composable Context Router, Dual-Surface Dispatch, & Split-Brain Council."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEEP_THINKING_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(DEEP_THINKING_SCRIPTS))

import consult_argon as ca
import cognitive_orchestrator as co


class TestComposableRouterAndCouncil(unittest.TestCase):
    def test_dual_surface_routing_and_blocked_models(self):
        # Standard consulting defaults to AI Studio Playground gemini-4-argon
        r_default = ca.resolve_consult_surface()
        self.assertEqual(r_default["surface"], "aistudio")
        self.assertEqual(r_default["model"], "gemini-4-argon")

        # Deep Research & Task default to Gemini Web 4 Neon High
        r_dr = ca.resolve_consult_surface(deep_research=True)
        self.assertEqual(r_dr["surface"], "web")
        self.assertEqual(r_dr["model"], "4 Neon")
        self.assertEqual(r_dr["thinking"], "High")

        r_task = ca.resolve_consult_surface(task_mode=True)
        self.assertEqual(r_task["surface"], "web")
        self.assertEqual(r_task["model"], "4 Neon")
        self.assertEqual(r_task["mode"], "task")

        with self.assertRaises(ValueError):
            ca.resolve_consult_surface(model="gemini-4-hydrogen")
        with self.assertRaises(ValueError):
            ca.resolve_consult_surface(model="4 Carbon")

    def test_composable_dry_run_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.local").write_text("SECRET_TOKEN=SecretDryRunVal999\n", encoding="utf-8")
            (root / "sample.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")

            # 1. --fresh attaches nothing except scrubbed prompt
            proc_fresh = subprocess.run(
                [sys.executable, str(DEEP_THINKING_SCRIPTS / "consult_argon.py"), "hello", "--fresh", "--dry-run", "--project", str(root)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_fresh.returncode, 0, proc_fresh.stderr)
            d_fresh = json.loads(proc_fresh.stdout)
            self.assertEqual(d_fresh["context"]["files"], [])
            self.assertEqual(d_fresh["route"]["surface"], "aistudio")
            self.assertEqual(d_fresh["max_output_tokens"], 800000)
            self.assertFalse(d_fresh["tools"]["search"])

            # 2. -O -C 5 --blind dry-run attaches offload+blind slice & sets falsifier_blind skill
            proc_comp = subprocess.run(
                [sys.executable, str(DEEP_THINKING_SCRIPTS / "consult_argon.py"), "review SecretDryRunVal999", "-O", "-C", "5", "--blind", "--dry-run", "--project", str(root)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_comp.returncode, 0, proc_comp.stderr)
            d_comp = json.loads(proc_comp.stdout)
            self.assertEqual(d_comp["system_skill"], "falsifier_blind")
            self.assertNotIn("SecretDryRunVal999", d_comp["prompt_preview"])
            self.assertGreaterEqual(d_comp["context"]["redaction_count"], 1)

    def test_split_brain_council_bounded_rounds_and_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "constraints.md").write_text("- Never wipe brain files.\n", encoding="utf-8")

            dry = co.run_adversarial_council("Design queue", mode="plan", project_root=root, rounds=5, dry_run=True)
            self.assertEqual(dry["rounds"], 2)  # Clamped to max 2 rounds
            roles = [r["role"] for r in dry["roles"]]
            self.assertEqual(roles, ["Architect", "Falsifier (Blind)", "Plan Verifier"])

            # Full mocked run: Round 1 Blind Falsifier flags BLOCKER, Round 2 passes
            calls = []

            def fake_consult(**kw):
                calls.append(kw)
                if len(calls) == 2:
                    return {"ok": True, "response": "BLOCKER: missing lock cleanup"}
                return {"ok": True, "response": "VERDICT: PASS"}

            res = co.run_adversarial_council("Design queue", mode="full", project_root=root, rounds=2, consult_fn=fake_consult)
            self.assertEqual(res["rounds_executed"], 2)
            self.assertEqual(res["verdict"], "VERIFIED")
            self.assertTrue(Path(res["report_path"]).exists())
            # mode='full' includes 4th role Grounded Researcher (web task)
            self.assertEqual(calls[3]["surface"], "web")
            self.assertEqual(calls[3]["mode"], "task")


if __name__ == "__main__":
    unittest.main()
