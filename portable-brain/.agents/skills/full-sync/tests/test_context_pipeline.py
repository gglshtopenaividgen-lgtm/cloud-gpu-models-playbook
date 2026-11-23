#!/usr/bin/env python3
"""Unit tests for Wave 2A Context Compiler, 2-Layer Redaction, & 4-Pass Conversation Slicer."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

FULL_SYNC_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(FULL_SYNC_SCRIPTS))

import offload_context_compiler as occ
import conversation_distiller as cd
import skill_reconciler as sr


class TestContextPipeline(unittest.TestCase):
    def test_two_layer_redaction_regex_and_exact_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env_file = root / ".env.local"
            env_file.write_text('CUSTOM_DB_PASS="UltraSecretValue98765"\nPORT=3000\n', encoding="utf-8")

            dummy_sk = "sk-" + "1234567890abcdefghijklmno"
            dummy_google = "AIzaSy" + "DummyGoogleKey1234567890123456789"
            sample = (
                f"key={dummy_sk}\n"
                f"google={dummy_google}\n"
                "raw=UltraSecretValue98765\n"
                "keep_port=3000\n"
            )
            scrubbed, hits = occ.redact_two_layer(sample, roots=[root])
            self.assertNotIn(dummy_sk, scrubbed)
            self.assertNotIn(dummy_google, scrubbed)
            self.assertNotIn("UltraSecretValue98765", scrubbed)
            self.assertIn("keep_port=3000", scrubbed)
            self.assertGreaterEqual(hits, 3)

    def test_incremental_ast_cache_hit_and_stability(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = root / "app.py"
            src.write_text("class Engine:\n    def run(self, x):\n        return x\n\ndef helper(a, b):\n    return a + b\n", encoding="utf-8")
            (root / "constraints.md").write_text("- Always use Python 3.14\n", encoding="utf-8")

            out1, st1 = occ.compile_offload_context(root, full=True)
            self.assertTrue(out1.exists())
            text = out1.read_text(encoding="utf-8")
            self.assertIn("class Engine (run)", text)
            self.assertIn("def helper(a, b)", text)

            # Second incremental run must hit cache (<350ms, cache_hits >= 1, cache_misses == 0)
            out2, st2 = occ.compile_offload_context(root, full=False)
            self.assertGreaterEqual(st2["cache_hits"], 1)
            self.assertEqual(st2["cache_misses"], 0)
            self.assertLess(st2["elapsed_ms"], 350.0)

    def test_four_pass_conversation_slice_and_blind_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("PROD_SECRET=MyTopSecretPassphrase123\n", encoding="utf-8")
            transcript = root / "transcript.jsonl"
            steps = [
                {
                    "step_index": 1,
                    "type": "USER_INPUT",
                    "source": "USER_EXPLICIT",
                    "content": "Never leak MyTopSecretPassphrase123 and always keep 13 universal skills.",
                },
                {
                    "step_index": 2,
                    "type": "PLANNER_RESPONSE",
                    "source": "MODEL",
                    "status": "DONE",
                    "content": "ASSIST_RATIONALE_MARKER we will edit server.py carefully.",
                    "tool_calls": [{"name": "edit_file", "arguments": {"Path": "C:/repo/server.py"}}],
                },
            ]
            transcript.write_text("\n".join(json.dumps(s) for s in steps), encoding="utf-8")

            # Normal slice includes assistant response, breadcrumbs, override ledger, and redacts .env secret
            res_full = cd.build_clean_conversation_slice(root, transcript_path=transcript, blind=False)
            full_txt = Path(res_full["output_path"]).read_text(encoding="utf-8")
            self.assertIn("[USER_OVERRIDE_LEDGER]", full_txt)
            self.assertIn("[TOOL] edit_file server.py", full_txt)
            self.assertIn("ASSIST_RATIONALE_MARKER", full_txt)
            self.assertNotIn("MyTopSecretPassphrase123", full_txt)

            # Blind slice strips assistant rationale completely
            res_blind = cd.build_clean_conversation_slice(root, transcript_path=transcript, blind=True)
            blind_txt = Path(res_blind["output_path"]).read_text(encoding="utf-8")
            self.assertIn("[TOOL] edit_file server.py", blind_txt)
            self.assertNotIn("ASSIST_RATIONALE_MARKER", blind_txt)
            self.assertNotIn("MyTopSecretPassphrase123", blind_txt)

    def test_skill_overlay_fenced_preserve_and_stale_ref_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ov_dir = root / ".agents" / "skill_overlays"
            ov_dir.mkdir(parents=True, exist_ok=True)
            ov_file = ov_dir / "browser-operator.md"
            ov_file.write_text(
                "# Custom Header\nHUMAN_NOTE_KEEP_ME\n\n"
                "<!-- BEGIN AUTO-SYNC -->\nOLD_BLOCK\n<!-- END AUTO-SYNC -->\n\n"
                "HUMAN_FOOTER_KEEP_ME\n"
                "Broken link: `scripts/does_not_exist_123.py`\n",
                encoding="utf-8",
            )
            p, changed = sr.sync_project_skill_overlay(root, "browser-operator", "NEW_SYNCED_BLOCK")
            self.assertTrue(changed)
            updated = p.read_text(encoding="utf-8")
            self.assertIn("HUMAN_NOTE_KEEP_ME", updated)
            self.assertIn("HUMAN_FOOTER_KEEP_ME", updated)
            self.assertIn("NEW_SYNCED_BLOCK", updated)
            self.assertNotIn("OLD_BLOCK", updated)

            stale = sr.check_stale_skill_refs(sr.BRAIN_ROOT, [root])
            self.assertTrue(any(s["missing_ref"] == "scripts/does_not_exist_123.py" and s["tag"] == "[STALE_REF]" for s in stale))


if __name__ == "__main__":
    unittest.main()
