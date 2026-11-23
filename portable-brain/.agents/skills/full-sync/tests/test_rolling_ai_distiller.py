import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from conversation_distiller import ConversationDistiller, _parse_ai_proposal


class RollingDistillerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.transcript = self.root / "transcript.jsonl"
        self.full = self.root / "transcript_full.jsonl"
        self.state = self.root / "state.json"
        self.secret = "SyntheticLiteralSecretForFixture"
        (self.root / ".env").write_text(f"FIXTURE_VALUE={self.secret}\n", encoding="utf-8")
        (self.root / "ideas.md").write_text(f"Historical context {self.secret}\n", encoding="utf-8")
        self.conv = {
            "conversation_id": "fixture",
            "source": "app",
            "transcript_path": self.transcript,
            "transcript_full_path": self.full,
        }
        self.proposal = {
            "new_decisions": ["Use reviewable proposals (fixture, step 2)"],
            "new_mistakes": [],
            "new_constraints": ["Verify durable writes (fixture, step 2)"],
            "updated_rolling_summary": "Reviewable proposal with durable verification",
        }
        self.transcript.write_text(self.turn(1, "Old turn already watermarked.") +
                                   self.turn(2, f"Unprocessed decision {self.secret}"), encoding="utf-8")
        first_line_size = len(self.turn(1, "Old turn already watermarked.").encode())
        self.state.write_text(json.dumps({
            "schema_version": 1,
            "conversations": {"app:fixture": {
                "last_distilled_step_index": 1,
                "transcript_size_bytes": first_line_size,
            }},
            "emitted_hashes": [],
        }), encoding="utf-8")

    def turn(self, step, message, **extra):
        return json.dumps({
            "step_index": step, "source": "USER", "type": "USER_INPUT",
            "content": message, **extra,
        }) + "\n"

    def processor(self, dry_run=False):
        engine = ConversationDistiller(
            self.root, self.root, self.root, self.state, dry_run=dry_run, include_history=True,
        )
        engine.registry.match_path = lambda path: ("brain", self.root)
        engine._resolve_conv_workspace = lambda _: ("brain", self.root)
        engine.discover_conversations = lambda **kwargs: [self.conv]
        return engine

    def reply(self, value):
        def respond(command, **kwargs):
            Path(command[command.index("-o") + 1]).write_text(value, encoding="utf-8")
            return subprocess.CompletedProcess(command, 0)
        return respond

    def test_dry_run_sends_nothing_and_redacts_delta_and_snapshot(self):
        original_state = self.state.read_bytes()
        with patch("conversation_distiller.subprocess.run") as transport:
            report = self.processor(dry_run=True).run_ai_studio(self.root)
        transport.assert_not_called()
        self.assertEqual(report["status"], "dry_run")
        self.assertEqual(report["delta_turns"], 1)
        self.assertEqual(report["redaction_count"], 2)
        self.assertEqual(self.state.read_bytes(), original_state)
        bundle = Path(report["bundle_path"]).read_text(encoding="utf-8")
        self.assertIn("Historical context", bundle)
        self.assertIn("Unprocessed decision", bundle)
        self.assertNotIn("Old turn already watermarked", bundle)
        self.assertNotIn(self.secret, bundle)

    def test_valid_response_advances_ai_cursor_only_and_merges_next_delta(self):
        self.proposal["updated_rolling_summary"] += f" {self.secret}"
        rendered = "Response metadata\n~~~json\n" + json.dumps(self.proposal) + "\n~~~\n"
        with patch("conversation_distiller.subprocess.run", side_effect=self.reply(rendered)) as transport:
            processor = self.processor()
            report = processor.run_ai_studio(self.root)
            self.assertEqual(processor.run_ai_studio(self.root)["status"], "no_delta")
        transport.assert_called_once()
        self.assertEqual(report["status"], "proposed")
        self.assertNotIn(self.secret, Path(report["summary_path"]).read_text(encoding="utf-8"))
        state = json.loads(self.state.read_text(encoding="utf-8"))
        self.assertEqual(state["conversations"]["app:fixture"]["last_distilled_step_index"], 1)
        self.assertEqual(state["ai_studio"]["brain"]["conversations"]["app:fixture"]["last_distilled_step_index"], 2)
        with self.transcript.open("a", encoding="utf-8", newline="") as handle:
            handle.write(self.turn(3, "Third turn only."))
        report = self.processor(dry_run=True).run_ai_studio(self.root)
        bundle = Path(report["bundle_path"]).read_text(encoding="utf-8")
        self.assertEqual(report["delta_turns"], 1)
        self.assertIn("Third turn only", bundle)
        self.assertIn("Reviewable proposal", bundle)
        self.assertNotIn("Unprocessed decision", bundle)
        self.assertNotIn(self.secret, self.state.read_text(encoding="utf-8"))

    def test_invalid_response_and_failed_subprocess_preserve_original_state(self):
        original = self.state.read_bytes()
        for responder in (self.reply('{"new_decisions": []}'),
                          lambda command, **kwargs: subprocess.CompletedProcess(command, 8)):
            with self.subTest(responder=responder):
                with patch("conversation_distiller.subprocess.run", side_effect=responder):
                    with self.assertRaises(ValueError):
                        self.processor().run_ai_studio(self.root)
                self.assertEqual(self.state.read_bytes(), original)
                self.assertFalse((self.root / "temp_read/distill_ai_summary_brain.md").exists())
                self.assertFalse((self.root / "temp_read/.distill_ai_response_brain.tmp").exists())

    def test_parses_json_or_one_markdown_fence_and_rejects_empty_or_corrupt_fields(self):
        proposal = json.dumps(self.proposal)
        self.assertEqual(_parse_ai_proposal(proposal), self.proposal)
        self.assertEqual(_parse_ai_proposal(f"~~~json\n{proposal}\n~~~\n"), self.proposal)
        for obj in ({**self.proposal, "updated_rolling_summary": " "},
                    {**self.proposal, "new_constraints": [""]}, []):
            with self.assertRaises(ValueError):
                _parse_ai_proposal(json.dumps(obj))

    def test_force_rescans_and_missing_full_transcript_preserves_state(self):
        original = self.state.read_bytes()
        report = self.processor(dry_run=True).run_ai_studio(self.root, force=True)
        self.assertEqual(report["delta_turns"], 2)
        self.transcript.write_text(self.turn(3, "Clipped delta", truncated_fields=["content"]), encoding="utf-8")
        with patch("conversation_distiller.subprocess.run") as transport:
            with self.assertRaises(ValueError):
                self.processor().run_ai_studio(self.root)
        transport.assert_not_called()
        self.assertEqual(self.state.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
