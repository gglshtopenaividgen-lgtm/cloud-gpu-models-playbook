"""Exercise cross-process consultation coordination without network calls."""

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import consult_argon as consult


class ConsultationDedupTests(unittest.TestCase):
    def setUp(self):
        fixture = tempfile.TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)
        self.directory = self.root / "temp_read"
        self.request = {"prompt": "Review one design", "surface": "aistudio", "model": "gemini-4-neon",
                        "system_skill": "plan_verifier"}

    def _overlap(self, runner, **extra):
        entered = threading.Event()
        waiting = threading.Event()
        release = threading.Event()
        original_collect = consult._collect_inflight

        def dispatch(**kwargs):
            entered.set()
            if not release.wait(8):
                raise RuntimeError("fixture timed out")
            return runner(**kwargs)

        def collect(*args, **kwargs):
            waiting.set()
            return original_collect(*args, **kwargs)

        with (
            patch.object(consult, "run_single_consultation", side_effect=dispatch) as mock,
            patch.object(consult, "_collect_inflight", side_effect=collect),
            patch.object(consult, "INFLIGHT_POLL", 0.01),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            owner = pool.submit(consult.consult_with_dedupe, self.root, **self.request)
            self.assertTrue(entered.wait(4))
            follower = pool.submit(consult.consult_with_dedupe, self.root, **self.request, **extra)
            try:
                self.assertTrue(waiting.wait(4))
            finally:
                release.set()
            first = owner.result(timeout=8)
            second = follower.result(timeout=8)
            self.assertEqual(mock.call_count, 1)
        self.assertEqual(list(self.directory.glob(".inflight_*.json")), [])
        return first, second

    def test_identical_callers_collect_one_reply_and_honor_follower_output(self):
        output = self.root / "follower.md"
        owner, follower = self._overlap(
            lambda **_: {"ok": True, "response": "Shared model answer"}, output_path=str(output),
        )
        self.assertEqual(owner, {"ok": True, "response": "Shared model answer"})
        self.assertEqual(follower, {**owner, "deduplicated": True})
        self.assertEqual(output.read_text(encoding="utf-8"), owner["response"])

        # The feature coordinates simultaneous callers. Finished runs are not cache hits.
        with patch.object(consult, "run_single_consultation", return_value={"ok": True}) as runner:
            consult.consult_with_dedupe(self.root, **self.request)
        runner.assert_called_once()

    def test_failed_owner_returns_same_failure_to_follower(self):
        def fail(**_):
            raise RuntimeError("Fixture bridge failed")

        owner, follower = self._overlap(fail)
        self.assertEqual(owner, {"ok": False, "error": "Fixture bridge failed"})
        self.assertEqual(follower, {**owner, "deduplicated": True})

    def test_dead_process_marker_is_replaced(self):
        process = subprocess.Popen([sys.executable, "-c", "pass"])
        process.wait(timeout=10)
        self.assertFalse(consult._consult_pid_alive(process.pid))
        self.assertTrue(consult._consult_pid_alive(os.getpid()))
        self.directory.mkdir()
        key = consult._consultation_key(self.root, self.request)
        marker = self.directory / f".inflight_{key}.json"
        consult._atomic_consult_json(marker, {
            "owner": "a" * 32, "pid": process.pid, "started_at": time.time(),
            "output_path": str(self.root / "not-owned.md"),
        })
        with patch.object(consult, "run_single_consultation", return_value={"ok": True}) as runner:
            self.assertTrue(consult.consult_with_dedupe(self.root, **self.request)["ok"])
        runner.assert_called_once()
        self.assertFalse(marker.exists())
        self.assertFalse((self.root / "not-owned.md").exists())

    def test_changed_context_digest_and_route_prevent_false_matches(self):
        attachment = self.root / "context.txt"
        request = {**self.request, "files": [str(attachment)]}
        attachment.write_text("Previous repository state", encoding="utf-8")
        first = consult._consultation_key(self.root, request)
        attachment.write_text("Updated repository state", encoding="utf-8")
        second = consult._consultation_key(self.root, request)
        self.assertNotEqual(first, second)
        self.assertNotEqual(second, consult._consultation_key(self.root, {**request, "search": True}))
        panel_one = {**request, "session_id": "role-1", "files": ["first.md"]}
        panel_two = {**request, "session_id": "role-2", "files": ["second.md"]}
        self.assertEqual(
            consult._consultation_key(self.root, panel_one, "shared-bundle", True),
            consult._consultation_key(self.root, panel_two, "shared-bundle", True),
        )

    def test_continued_conversation_skips_deduplication(self):
        with patch.object(consult, "run_single_consultation", return_value={"ok": True}) as runner:
            consult.consult_with_dedupe(self.root, **self.request, continue_session=True)
        runner.assert_called_once_with(**self.request, continue_session=True)
        self.assertFalse(self.directory.exists())


if __name__ == "__main__":
    unittest.main()
