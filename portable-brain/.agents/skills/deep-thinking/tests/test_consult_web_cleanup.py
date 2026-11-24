"""Test consultation cleanup without reaching the browser bridge."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import consult_argon as consult


class GeminiWebCleanupTests(unittest.TestCase):
    def setUp(self):
        self.profile = "Profile 14"
        self.driver = Mock()
        self.driver.create_session.return_value = "fixture"
        self.driver.registry = {"fixture": {"tab_id": 42}}
        self.driver.tab_id = None
        self.driver.ask.return_value = {"ok": True, "response": "Fixture answer"}
        for name, replacement in (
            ("GeminiBrainDriver", Mock(return_value=self.driver)),
            ("acquire_profile_lease", Mock(return_value=(self.profile, None))),
            ("release_profile_lease", Mock()),
            ("resolve_execution_route", None),
        ):
            mocked = patch.object(consult, name, replacement)
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_default_cleanup_closes_tabs_after_success_and_failures(self):
        for outcome in ("success", "failure", "exception"):
            with self.subTest(outcome=outcome):
                self.driver.delete_session.reset_mock()
                if outcome == "success":
                    self.assertTrue(consult.consult_argon_web("fixture")["ok"])
                elif outcome == "failure":
                    self.driver.ask.return_value = {"ok": False, "error": "fixture failed"}
                    self.assertFalse(consult.consult_argon_web("fixture")["ok"])
                else:
                    self.driver.ask.side_effect = RuntimeError("fixture exception")
                    with self.assertRaisesRegex(RuntimeError, "fixture exception"):
                        consult.consult_argon_web("fixture")
                self.driver.delete_session.assert_called_once_with(
                    "fixture", profile=self.profile, close_tab=True,
                )
        self.assertEqual(consult.release_profile_lease.call_count, 3)

    def test_keep_tab_flows_through_unified_web_dispatch(self):
        self.assertTrue(consult.run_single_consultation("fixture", surface="web", keep_tab=True)["ok"])
        self.driver.delete_session.assert_called_once_with("fixture", profile=self.profile, close_tab=False)
        self.driver._call_api.assert_not_called()

    def test_failure_without_auto_clean_closes_only_using_agent_guard(self):
        self.driver.ask.return_value = {"ok": False, "error": "fixture failed"}
        self.assertFalse(consult.consult_argon_web("fixture", auto_clean=False)["ok"])
        self.driver.delete_session.assert_not_called()
        self.driver._call_api.assert_called_once_with(
            "/command",
            {"action": "CLOSE_TAB", "agent_guarded": True, "params": {"tabId": 42}},
            profile=self.profile,
        )

    def test_explicit_no_auto_clean_preserves_success_or_opted_in_tab(self):
        self.assertTrue(consult.consult_argon_web("fixture", auto_clean=False)["ok"])
        self.driver.ask.return_value = {"ok": False, "error": "fixture failed"}
        self.assertFalse(consult.consult_argon_web("fixture", auto_clean=False, keep_tab=True)["ok"])
        self.driver.delete_session.assert_not_called()
        self.driver._call_api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
