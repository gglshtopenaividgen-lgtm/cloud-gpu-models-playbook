#!/usr/bin/env python3
"""
Unit Tests for Browser Operator & Argon Bridge (Wave 1):
- 11-Profile Waterfall Drain & Tier 1 Alt -> Tier 2 Daily Driver Last Resort
- 4 Independent Quota Buckets, Surface-Scoped Locks, & Dead-PID Reaping
- Gemini Web 4 Neon High Routing + Hard Block on 4 Hydrogen & 4 Carbon
- AI Studio Playground Model Guard & Retired /apps Rejection
- 3-Stage Popup Self-Healer (Liveness Guard + Safe Whitelist + Anomaly Capture)
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ARGON_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "argon_bridge"
sys.path.insert(0, str(ARGON_BRIDGE_DIR))

import profile_manager as pm
import profile_lock_manager as plm
import gemini_brain_driver as gbd
import aistudio_subagent as ais
import popup_healer as ph


class TestProfileLockManagerWave1(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_locks_file = Path(self.temp_dir.name) / "test_locks.json"
        self.test_sessions_file = Path(self.temp_dir.name) / "test_sessions.json"
        self.test_quota_file = Path(self.temp_dir.name) / "test_quota.json"

        self.orig_locks_file = plm.LOCKS_FILE
        self.orig_sessions_file = plm.SESSIONS_FILE
        self.orig_quota_file = pm.QUOTA_STATE_PATH

        plm.LOCKS_FILE = self.test_locks_file
        plm.SESSIONS_FILE = self.test_sessions_file
        pm.QUOTA_STATE_PATH = self.test_quota_file

    def tearDown(self):
        plm.LOCKS_FILE = self.orig_locks_file
        plm.SESSIONS_FILE = self.orig_sessions_file
        pm.QUOTA_STATE_PATH = self.orig_quota_file
        self.temp_dir.cleanup()

    def test_tier1_before_tier2_daily_drivers(self):
        """All Tier 1 Alt Pros must sort before Tier 2 Daily Drivers in get_fleet_order()."""
        order = plm.get_fleet_order()
        all_profs = {p.dir_name: p for p in pm.get_ai_premium_profiles()}
        self.assertGreaterEqual(len(order), 6)
        saw_daily = False
        for d in order:
            p = all_profs[d]
            if p.is_daily_driver:
                saw_daily = True
                self.assertIn(p.email.lower(), pm.DAILY_DRIVER_EMAILS)
            else:
                self.assertFalse(saw_daily, f"Tier 1 alt {d} appeared after a Daily Driver!")

    def test_surface_scoped_locks_and_dead_pid_reaping(self):
        """Surface-scoped locks allow AI Studio + Gemini Web concurrently, and dead PIDs are reaped."""
        now = time.time()
        plm._write_locks({
            "Profile 14::aistudio": {"agent_id": "a1", "expires_at": now + 200, "pid": 99999999},
            "Profile 13::aistudio": {"agent_id": "a2", "expires_at": now + 200},
        })
        with mock.patch.object(plm, "_is_pid_alive", side_effect=lambda pid: pid != 99999999):
            active = plm.clean_expired_locks()
        self.assertNotIn("Profile 14::aistudio", active)
        self.assertIn("Profile 13::aistudio", active)

        # Gemini Web lock on Profile 13 should NOT collide with Profile 13::aistudio
        with mock.patch.object(plm, "pick_optimal_idle_profile", return_value="Profile 13"):
            prof, err = plm.acquire_profile_lease(
                agent_id="web_agent", preferred_profile="Profile 13", surface="gemini_web", bucket="gemini_web_neon"
            )
        self.assertIsNone(err)
        self.assertEqual(prof, "Profile 13")
        locks = plm._read_locks()
        self.assertIn("Profile 13::aistudio", locks)
        self.assertIn("Profile 13::gemini_web", locks)

    def test_four_independent_quota_buckets_and_reauth(self):
        """Cooling down one bucket leaves other buckets on the same profile available."""
        plm.mark_bucket_cooldown("Profile 13", "aistudio_argon", cooldown_seconds=1800, reason="429")
        self.assertFalse(plm.is_bucket_available("Profile 13", "aistudio_argon"))
        self.assertTrue(plm.is_bucket_available("Profile 13", "aistudio_neon"))
        self.assertTrue(plm.is_bucket_available("Profile 13", "gemini_web_neon"))
        self.assertTrue(plm.is_bucket_available("Profile 13", "notebooklm"))

        plm.mark_profile_needs_reauth("Profile 13", "gemini_web")
        self.assertFalse(plm.is_bucket_available("Profile 13", "gemini_web_neon"))

    def test_eviction_marker_excludes_new_leases_and_is_cleared(self):
        profile = "Profile 13"
        with plm.idle_profile_eviction(profile) as acquired:
            self.assertTrue(acquired)
            self.assertTrue(plm.is_profile_evicting(profile))
            self.assertEqual(plm.clean_expired_locks(), {})
            with plm.idle_profile_eviction(profile) as second_acquired:
                self.assertFalse(second_acquired)
            with mock.patch.object(plm, "pick_optimal_idle_profile", return_value=profile):
                selected, error = plm.acquire_profile_lease("new-agent", surface="gemini_web")
            self.assertIsNone(selected)
            self.assertIn("being closed", error)
        self.assertFalse(plm.is_profile_evicting(profile))
        self.assertTrue(plm.is_bucket_available("Profile 13", "aistudio_neon"))
        plm.clear_needs_reauth("Profile 13", "gemini_web")
        self.assertTrue(plm.is_bucket_available("Profile 13", "gemini_web_neon"))

    def test_waterfall_drain_drains_open_tier1_before_closed_and_daily(self):
        """Waterfall Drain prefers already-open Tier 1 Alts and only falls back to Daily Drivers when all Tier 1 are unavailable."""
        fake_status = {
            "Profile 13": {"is_daily_driver": False, "current_usage_percent": 10},
            "Profile 14": {"is_daily_driver": False, "current_usage_percent": 10},
            "Profile 8": {"is_daily_driver": True, "current_usage_percent": 5},
        }
        with (
            mock.patch.object(plm, "ensure_bridge_running", return_value=True),
            mock.patch.object(plm, "clean_expired_locks", return_value={}),
            mock.patch.object(plm, "get_live_profile_status", return_value=fake_status),
            mock.patch.object(plm, "_get_bridge_resources_json", return_value={}),
            mock.patch.object(plm, "_get_bridge_status_json", return_value={"connected_extensions": [{"dir_name": "Profile 13"}], "interactive_desktop": False}),
            mock.patch.object(plm, "_is_profile_truly_open", side_effect=lambda p: p == "Profile 13"),
            mock.patch.object(plm, "ping_profile", return_value=True),
        ):
            chosen = plm.pick_optimal_idle_profile(
                preferred_order=["Profile 14", "Profile 13", "Profile 8"],
                surface="gemini_web",
                bucket="gemini_web_neon",
            )
            self.assertEqual(chosen, "Profile 13")

            # Exhaust Profile 13 & Profile 14 -> Daily Driver Profile 8 selected strictly as last resort when interactive host can open it
            plm.mark_bucket_cooldown("Profile 13", "gemini_web_neon", cooldown_seconds=600)
            plm.mark_bucket_cooldown("Profile 14", "gemini_web_neon", cooldown_seconds=600)
            with (
                mock.patch.object(plm, "_get_bridge_status_json", return_value={"connected_extensions": [{"dir_name": "Profile 13"}], "interactive_desktop": True}),
                mock.patch.object(plm, "launch_profile_candidate", return_value=True),
            ):
                fallback = plm.pick_optimal_idle_profile(
                    preferred_order=["Profile 14", "Profile 13", "Profile 8"],
                    surface="gemini_web",
                    bucket="gemini_web_neon",
                )
            self.assertEqual(fallback, "Profile 8")


class TestDualSurfaceRoutingAndGuards(unittest.TestCase):
    def test_gemini_web_routes_to_neon_high_and_blocks_hydrogen_carbon(self):
        for kw in ({}, {"deep_research": True}, {"mode": "task"}, {"mode": "task", "thinking": "High"}):
            route = gbd.resolve_execution_route(**kw)
            self.assertEqual(route["model"], "4 Neon")
            self.assertEqual(route["test_id"], "bard-mode-option-e6fa609c3fa255c0")
            self.assertEqual(route["thinking"], "High")

        with self.assertRaises(ValueError):
            gbd.resolve_execution_route(model="4 Hydrogen")
        with self.assertRaises(ValueError):
            gbd.resolve_execution_route(model="4 Carbon")

        # Legacy 4 Argon on Gemini Web auto-routes cleanly to 4 Neon
        legacy = gbd.resolve_execution_route(model="4 Argon")
        self.assertEqual(legacy["model"], "4 Neon")

    def test_ensure_model_task_mode_sets_neon_high(self):
        driver = gbd.GeminiBrainDriver(default_profile="Profile 13")
        driver.wait_for_page_ready = lambda *a, **k: {"ready": True}

        def fake_exec(tab_id, script, profile=None):
            if "gem-segmented-button-action" in script and "targetBtn.click()" in script:
                return {"ok": True, "result": {"ok": True, "mode": "task", "selected": True}}
            if "gem-segmented-button-action" in script:
                return {"ok": True, "result": {"hasToggle": True, "hasTarget": True, "alreadySelected": True}}
            if "const hasModel =" in script:
                return {"ok": True, "result": {"hasBtn": True, "matches": True, "text": "Neon\nHigh", "aria": "Open mode picker, currently Neon High", "cx": 100, "cy": 200}}
            return {"ok": True, "result": None}

        driver.execute_js = fake_exec
        res = driver.ensure_model_and_thinking(1, model="4 Neon", thinking="High", mode="task", profile="Profile 13")
        self.assertTrue(res.get("ok"), res)
        self.assertEqual(res.get("model"), "4 Neon")
        self.assertEqual(res.get("thinking"), "High")

    def test_aistudio_model_guard_and_retired_apps(self):
        self.assertEqual(ais.validate_aistudio_model("argon"), "gemini-4-argon")
        self.assertEqual(ais.validate_aistudio_model("gemini-4-neon"), "gemini-4-neon")
        with self.assertRaises(ValueError):
            ais.validate_aistudio_model("gemini-4-hydrogen")
        with self.assertRaises(ValueError):
            ais.validate_aistudio_model("gemini-4-carbon")

        retired = ais.ask_ai_studio(prompt="test", surface="apps")
        self.assertFalse(retired["ok"])
        self.assertEqual(retired["code"], "SURFACE_RETIRED")


class TestThreeStagePopupHealer(unittest.TestCase):
    def test_stage1_liveness_guard_prevents_dismissal(self):
        def fake_eval(js):
            if "stop_button_visible" in js:
                return {"result": {"active": True, "reasons": ["subagents_running"]}}
            raise AssertionError("Should not run dismiss JS when Stage 1 liveness is active!")

        res = ph.dismiss_blocking_popups(eval_fn=fake_eval, surface="gemini_web")
        self.assertTrue(res.get("liveness_active"))
        self.assertFalse(res.get("blocked"))

    def test_stage3_captures_unknown_modal_telemetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def fake_eval(js):
                if "stop_button_visible" in js:
                    return {"result": {"active": False, "reasons": []}}
                return {
                    "result": {
                        "ok": True,
                        "dismissed_count": 0,
                        "clicked": [],
                        "blocked": True,
                        "anomaly": {"tag": "MAT-DIALOG-CONTAINER", "buttons": [{"label": "connect drive"}]},
                    }
                }

            def fake_shot(out_p):
                Path(out_p).write_bytes(b"PNG")

            res = ph.dismiss_blocking_popups(eval_fn=fake_eval, screenshot_fn=fake_shot, surface="aistudio", project_root=root)
            self.assertTrue(res["blocked"])
            self.assertTrue(Path(res["anomaly_json"]).exists())
            self.assertTrue(Path(res["anomaly_screenshot"]).exists())


if __name__ == "__main__":
    unittest.main()
