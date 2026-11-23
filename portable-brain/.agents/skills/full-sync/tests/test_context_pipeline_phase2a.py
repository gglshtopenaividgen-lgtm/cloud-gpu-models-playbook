import json
from pathlib import Path
import py_compile
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from conversation_distiller import ConversationDistiller, clean_turn_text, is_low_signal_clause
from context_promoter import ContextPromoter


class ContextPipelineTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.transcript = self.root / "turns.jsonl"
        self.full = self.root / "full.jsonl"
        self.state = self.root / "state.json"
        self.conv = {
            "conversation_id": "fixture",
            "source": "app",
            "transcript_path": self.transcript,
            "transcript_full_path": self.full,
        }

    def processor(self):
        distiller = ConversationDistiller(self.root, self.root, self.root, self.state, include_history=True)
        distiller._resolve_conv_workspace = lambda _: ("brain", self.root)
        distiller._upsert_hermes = lambda **kwargs: None
        return distiller

    def turn(self, step, **extra):
        return json.dumps({
            "step_index": step,
            "type": "USER_INPUT",
            "content": "Always validate deployment manifests before production rollouts",
            **extra,
        }) + "\n"

    def test_low_signal(self):
        processor = self.processor()
        for clause in (
            "Don't get it why are we still trying the same approach",
            "Never use @[Quote] for the current task",
            "Always use production pipelines (when possible",
            "Never leave the damn app in the current state",
            "Always configure the deployment context for...",
            "Always configure the deployment environment for",
        ):
            self.assertTrue(is_low_signal_clause(clause), clause)
        turn = json.loads(self.turn(1, content="Always validate deployment manifests before production rollouts?"))
        self.assertEqual(processor._extract_items_from_turn(turn, self.conv), [])

    def test_recursive_ledger_excerpt_is_removed(self):
        excerpt = (
            "### Decision [2026-11-23] (BRAIN): Keep the existing deployment design\n"
            "178: - [2026-11-23] [INVARIANT] Always use a named deployment service\n"
            "Fixed: The worker now validates the transaction before publishing.\n"
        )
        self.assertEqual(
            clean_turn_text(excerpt),
            "Fixed: The worker now validates the transaction before publishing.",
        )

    def test_replay_and_repaired_partial_read(self):
        self.transcript.write_text(self.turn(1) + '{"step_index":', encoding="utf-8")
        self.assertEqual(self.processor().process_conversation(self.conv)["status"], "failed")
        self.assertFalse(self.state.exists())
        self.transcript.write_text(self.turn(1) + self.turn(2, content="Always retain rollback snapshots before production schema migrations"), encoding="utf-8")
        result = self.processor().process_conversation(self.conv)
        self.assertEqual(result["status"], "distilled")
        self.assertEqual((self.root / "constraints.md").read_text(encoding="utf-8").count("[INVARIANT]"), 2)
        self.assertEqual(self.processor().process_conversation(self.conv)["status"], "fast_skipped")
        cursor = json.loads(self.state.read_text(encoding="utf-8"))["conversations"]["app:fixture"]
        self.assertEqual(cursor["last_distilled_step_index"], 2)
        self.assertEqual(cursor["source"], "app")

    def test_truncation_requires_full_turn(self):
        self.transcript.write_text(self.turn(1, truncated_fields=["content"]), encoding="utf-8")
        self.assertEqual(self.processor().process_conversation(self.conv)["status"], "failed")
        self.assertFalse(self.state.exists())
        self.full.write_text(self.turn(1), encoding="utf-8")
        self.assertEqual(self.processor().process_conversation(self.conv)["entries"], 1)

    def test_write_failure_preserves_cursor(self):
        self.transcript.write_text(self.turn(1), encoding="utf-8")
        with patch.object(ConversationDistiller, "_append_to_target_file", side_effect=OSError("fixture")):
            self.assertEqual(self.processor().process_conversation(self.conv)["status"], "failed")
        self.assertFalse(self.state.exists())

    def test_promotion_requires_scope_and_deduplicates_by_origin(self):
        root_ledger = self.root / "constraints.md"
        root_ledger.write_text("# Constraints\n", encoding="utf-8")
        doc = "### Shipping rules\nUse AWS Lambda for this project.\n\n### [Universal] Review changes\nReview deployment diffs before publishing.\n"
        for slug in ("first", "second"):
            location = self.root / slug
            location.mkdir()
            (location / "constraints.md").write_text(doc, encoding="utf-8")
            self.assertEqual(ContextPromoter(self.root).process_project(slug, location)["promoted_constraints"], 1)
            self.assertEqual(ContextPromoter(self.root).process_project(slug, location)["promoted_constraints"], 0)
        self.assertNotIn("Shipping rules", root_ledger.read_text(encoding="utf-8"))
        self.assertEqual(root_ledger.read_text(encoding="utf-8").count("Review deployment diffs"), 2)
        self.assertIn("Shipping rules", (self.root / "projects" / "first" / "constraints.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as output:
        for name in ("conversation_distiller.py", "context_promoter.py"):
            py_compile.compile(str(SCRIPTS / name), cfile=str(Path(output) / (name + "c")), doraise=True)
        py_compile.compile(__file__, cfile=str(Path(output) / "fixture.pyc"), doraise=True)
    unittest.main()

