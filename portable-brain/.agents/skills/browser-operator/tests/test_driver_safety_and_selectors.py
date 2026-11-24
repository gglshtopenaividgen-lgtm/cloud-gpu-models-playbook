#!/usr/bin/env python3
"""Unit tests for Bridge V4.1 Driver Safety & Live DOM Selector Fixes."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ARGON_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "argon_bridge"
if str(ARGON_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(ARGON_BRIDGE_DIR))

import aistudio_subagent as ais
import gemini_brain_driver as gbd


class TestAIStudioDriverSafetyAndHydration(unittest.TestCase):
    def test_wait_for_aistudio_ready_waits_for_complete_and_reinjects_helpers(self):
        probe_calls = {"n": 0}
        gen_calls = {"n": 0}
        injected_helpers = []

        def fake_api(endpoint, method="GET", payload=None, timeout=30.0):
            params = (payload or {}).get("params", {})
            code = params.get("code", "")
            if "window.__agyStudio = {" in code:
                injected_helpers.append(True)
                return {"ok": True, "result": True}
            if "document.readyState" in code and "hasApp" in code:
                probe_calls["n"] += 1
                if probe_calls["n"] == 1:
                    return {"ok": True, "result": {"ready": False, "readyState": "loading", "href": "https://aistudio.google.com/prompts/new_chat?model=gemini-4-argon", "bodyLen": 0, "hasApp": False}}
                return {"ok": True, "result": {"ready": True, "readyState": "complete", "href": "https://aistudio.google.com/prompts/new_chat?model=gemini-4-argon", "bodyLen": 1200, "hasApp": True}}
            if "assertActiveModel" in code:
                # Simulate initial hydration wipe on first probe, then clean card after re-injection
                if len(injected_helpers) < 2:
                    return {"ok": True, "result": {"hasHelper": False, "href": "https://aistudio.google.com/prompts/new_chat", "readyState": "complete", "title": "Google AI Studio"}}
                return {"ok": True, "result": {"hasHelper": True, "href": "https://aistudio.google.com/prompts/new_chat", "readyState": "complete", "title": "Google AI Studio", "card": {"ok": True, "actual": "Gemini 4 Argon"}}}
            if "getGenerationStatus(" in code:
                gen_calls["n"] += 1
                if gen_calls["n"] == 1:
                    return {"ok": True, "result": {"is_generating": False, "answer_turns_count": 0, "text_length": 0, "has_answer": False}}
                return {"ok": True, "result": {"is_generating": False, "answer_turns_count": 1, "text_length": 12, "has_answer": True}}
            if "harvestRichContent(" in code:
                return {"ok": True, "result": {"ok": True, "text": "OK_ARGON_V41", "thoughts": ""}}
            if "window.location.href" in code:
                return {"ok": True, "result": "https://aistudio.google.com/prompts/new_chat?model=gemini-4-argon"}
            return {"ok": True, "result": {"ok": True}}

        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(ais, "profile_lock_manager", None),
                mock.patch.object(ais, "popup_healer", None),
                mock.patch.object(ais, "ensure_extension_ready", return_value={"dir_name": "Profile 14"}),
                mock.patch.object(ais, "find_or_open_ai_studio_tab", return_value=(101, True)),
                mock.patch.object(ais, "reclaim_finished_tab"),
                mock.patch.object(ais, "call_bridge_api", side_effect=fake_api),
                mock.patch.object(ais.time, "sleep", return_value=None),
            ):
                res = ais.ask_ai_studio(
                    prompt="test",
                    output_file=str(Path(tmp) / "out.md"),
                    poll_interval_sec=0.01,
                )

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["text"], "OK_ARGON_V41")
        self.assertEqual(probe_calls["n"], 2)
        self.assertGreaterEqual(len(injected_helpers), 2)

    def test_model_assertion_failure_captures_screenshot_and_surfaces_url(self):
        shots = []

        def fake_api(endpoint, method="GET", payload=None, timeout=30.0):
            params = (payload or {}).get("params", {})
            code = params.get("code", "")
            if "document.readyState" in code and "hasApp" in code:
                return {"ok": True, "result": {"ready": True, "readyState": "complete", "href": "https://aistudio.google.com/prompts/new_chat", "bodyLen": 500, "hasApp": True}}
            if "assertActiveModel" in code:
                return {"ok": False, "error": "Execution context destroyed"}
            if "window.location.href" in code:
                return {"ok": True, "result": "https://aistudio.google.com/prompts/new_chat"}
            return {"ok": True, "result": {"ok": True}}

        with (
            mock.patch.object(ais, "profile_lock_manager", None),
            mock.patch.object(ais, "popup_healer", None),
            mock.patch.object(ais, "ensure_extension_ready", return_value={"dir_name": "Profile 14"}),
            mock.patch.object(ais, "find_or_open_ai_studio_tab", return_value=(101, True)),
            mock.patch.object(ais, "capture_tab_screenshot", side_effect=lambda c, t, p: shots.append(p) or True),
            mock.patch.object(ais, "reclaim_finished_tab"),
            mock.patch.object(ais, "call_bridge_api", side_effect=fake_api),
            mock.patch.object(ais.time, "sleep", return_value=None),
        ):
            res = ais.ask_ai_studio(prompt="test", poll_interval_sec=0.01)

        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "MODEL_ASSERTION_FAILED")
        self.assertIn("Execution context destroyed", res["error"])
        self.assertTrue(any("aistudio_model_fail_diag.png" in s for s in shots))


class TestGeminiDriverSafetyAndSelectors(unittest.TestCase):
    def test_ensure_bridge_running_refuses_spawn_inside_exebox(self):
        driver = gbd.GeminiBrainDriver(default_profile="Profile 14")
        with (
            mock.patch.object(gbd.urllib.request, "urlopen", side_effect=OSError("connection refused")),
            mock.patch.object(gbd.GeminiBrainDriver, "_get_current_desktop_name", return_value="exebox-123"),
            mock.patch.object(gbd.subprocess, "Popen") as popen_mock,
            mock.patch.object(gbd.sys, "platform", "win32"),
            mock.patch.dict(os.environ, {}, clear=False),
            mock.patch.object(gbd.time, "sleep", return_value=None),
        ):
            os.environ.pop("AGY_ALLOW_HEADLESS_BRIDGE", None)
            ok = driver.ensure_bridge_running()

        self.assertFalse(ok)
        popen_mock.assert_not_called()

    def test_zero_turn_delete_session_skips_sidebar_delete_and_closes_tab(self):
        with tempfile.TemporaryDirectory() as tmp:
            driver = gbd.GeminiBrainDriver(default_profile="Profile 14")
            orig_reg = gbd.REGISTRY_PATH
            try:
                gbd.REGISTRY_PATH = Path(tmp) / "reg.json"
                driver.registry = {
                    "s_empty": {
                        "session_id": "s_empty",
                        "profile": "Profile 14",
                        "tab_id": 555,
                        "own_tab": False,
                        "chat_id": None,
                        "url": "https://gemini.google.com/app",
                        "turns": 0,
                    }
                }
                calls = []

                def fake_api(endpoint, payload=None, method="POST", timeout=30.0, profile=None):
                    calls.append((endpoint, payload))
                    return {"ok": True, "result": "https://gemini.google.com/app"}

                driver._call_api = fake_api
                driver._call_api_raw = fake_api

                res = driver.delete_session("s_empty", profile="Profile 14", close_tab=True)

                self.assertTrue(res.get("ok"), res)
                self.assertTrue(res.get("skipped_sidebar_delete"))
                self.assertNotIn("s_empty", driver.registry)
                self.assertTrue(any((p or {}).get("action") == "CLOSE_TAB" and (p or {}).get("params", {}).get("tabId") == 555 for _, p in calls))
                self.assertFalse(any("actions-menu-button" in str((p or {}).get("params", {}).get("code", "")) for _, p in calls))
            finally:
                gbd.REGISTRY_PATH = orig_reg

    def test_deep_research_selectors_support_gem_menu_item_and_zero_state_wake(self):
        driver = gbd.GeminiBrainDriver(default_profile="Profile 14")
        driver.wait_for_page_ready = lambda *a, **k: {"ready": True}
        driver.ensure_execution_mode = lambda *a, **k: {"ok": True, "mode": "chat"}
        driver._nudge_compositor = lambda *a, **k: None

        seen_codes = []
        clicked_dr = {"v": False}

        def fake_exec(tab_id, code, timeout=30.0, profile=None):
            seen_codes.append(code)
            if "input-area-v2" in code:
                return {"ok": True, "result": clicked_dr["v"]}
            if "Boolean(mt)" in code:
                return {"ok": True, "result": True}
            if "mouseenter" in code:
                return {"ok": True, "result": True}
            if "dr.click()" in code:
                clicked_dr["v"] = True
                return {"ok": True, "result": True}
            return {"ok": True, "result": False}

        driver.execute_js = fake_exec
        self.assertTrue(driver.ensure_deep_research(101, profile="Profile 14"))
        self.assertTrue(clicked_dr["v"])
        self.assertTrue(any("gem-menu-item" in c for c in seen_codes))


if __name__ == "__main__":
    unittest.main()
