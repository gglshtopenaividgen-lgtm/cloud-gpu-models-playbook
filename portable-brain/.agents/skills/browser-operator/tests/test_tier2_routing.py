import io
import os
from contextlib import ExitStack, redirect_stderr
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

BRIDGE = Path(__file__).resolve().parents[1] / "argon_bridge"
sys.path.insert(0, str(BRIDGE))
import profile_lock_manager as locks
import profile_rotator as rotator


class TierRoutingTest(unittest.TestCase):
    alt = "Profile 14"
    other_alt = "Profile 13"
    daily = "Profile 16"
    other_daily = "Profile 7"

    def setup_fleet(self, *, interactive, opened=None, active=()):
        self.alt_info = {"has_bridge_extension": True, "current_usage_percent": 10}
        self.status = {
            self.alt: self.alt_info,
            self.other_alt: {"has_bridge_extension": True, "current_usage_percent": 10},
            self.daily: {"is_daily_driver": True, "has_bridge_extension": True},
            self.other_daily: {"is_daily_driver": True, "has_bridge_extension": True},
        }
        opened = set(opened if opened is not None else (self.daily, self.other_daily))
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch.object(locks, "ensure_bridge_running", return_value=True))
        stack.enter_context(patch.object(locks, "clean_expired_locks", return_value={}))
        stack.enter_context(patch.object(locks, "get_live_profile_status", return_value=self.status))
        stack.enter_context(patch.object(locks, "get_fleet_order", return_value=list(self.status)))
        self.resources = stack.enter_context(patch.object(locks, "_get_bridge_resources_json", return_value={
            "active_agent_profiles": list(active), "max_agent_profiles": 3,
        }))
        stack.enter_context(patch.object(locks, "_get_bridge_status_json", return_value={
            "interactive_desktop": interactive, "connected_extensions": [{"dir_name": profile} for profile in opened],
        }))
        stack.enter_context(patch.object(locks, "_is_profile_truly_open", side_effect=opened.__contains__))
        stack.enter_context(patch.object(locks, "ping_profile", return_value=True))
        self.quota = stack.enter_context(patch.object(locks, "is_bucket_available", return_value=True))
        self.cleanup = stack.enter_context(patch.object(locks, "_cleanup_idle_bridge_resources"))
        self.launch = stack.enter_context(patch.object(locks, "launch_profile_candidate", return_value=True))

    def test_interactive_opens_alt_even_when_personal_daily_drivers_are_open(self):
        self.setup_fleet(interactive=True)
        self.assertEqual(locks.pick_optimal_idle_profile(), self.alt)
        self.launch.assert_called_once_with(self.alt, max_open=3, auto_close_idle=True)
        self.resources.assert_called_once_with(reconcile=True)
        self.cleanup.assert_not_called()

    def test_noninteractive_never_borrows_daily_when_alt_has_quota(self):
        self.setup_fleet(interactive=False)
        unavailable = io.StringIO()
        with redirect_stderr(unavailable):
            self.assertIsNone(locks.pick_optimal_idle_profile())
        self.assertIn("TIER1_ROTATION_NEEDED", unavailable.getvalue())
        self.launch.assert_not_called()
        self.cleanup.assert_not_called()

    def test_daily_requires_exhaustion_or_explicit_permission(self):
        self.setup_fleet(interactive=False)
        self.alt_info["current_usage_percent"] = 95
        self.quota.side_effect = lambda profile, bucket=None: profile != self.other_alt
        self.assertEqual(locks.pick_optimal_idle_profile(bucket="gemini_web_neon"), self.daily)
        self.alt_info["current_usage_percent"] = 10
        self.assertEqual(locks.pick_optimal_idle_profile(allow_daily_driver=True), self.daily)
        self.assertEqual(locks.pick_optimal_idle_profile(explicit_preferred=self.other_daily), self.other_daily)

    def test_prefers_requested_closed_alt_but_default_drains_open_alt(self):
        self.setup_fleet(interactive=True, opened=[self.other_alt, self.daily])
        self.assertEqual(locks.pick_optimal_idle_profile(), self.other_alt)
        self.launch.assert_not_called()
        self.assertEqual(locks.pick_optimal_idle_profile(explicit_preferred=self.alt), self.alt)
        self.launch.assert_called_once_with(self.alt, max_open=3, auto_close_idle=True)

    def test_capacity_triggers_one_cleanup_and_refresh_before_retry(self):
        self.setup_fleet(interactive=True, active=[self.daily, self.other_daily, "Profile 12"])
        self.resources.side_effect = [
            {"active_agent_profiles": [self.daily, self.other_daily, "Profile 12"]},
            {"active_agent_profiles": [self.daily, self.other_daily]},
        ]
        self.assertEqual(locks.pick_optimal_idle_profile(), self.alt)
        self.cleanup.assert_called_once_with()
        self.assertEqual(self.resources.call_count, 2)
        self.launch.assert_called_once_with(self.alt, max_open=3, auto_close_idle=True)

    def test_rotator_does_not_count_personal_daily_driver_windows(self):
        target = SimpleNamespace(dir_name=self.alt, email="fixture@example.com",
                                 has_bridge_extension=True, is_daily_driver=False)
        profiles = {
            profile: {
                "is_open": profile != self.alt,
                "tabs_count": 1 if profile != self.alt else 0,
                "profile": target if profile == self.alt else SimpleNamespace(
                    is_daily_driver=profile in {self.daily, self.other_daily}
                ),
            }
            for profile in (self.alt, self.other_alt, self.daily, self.other_daily)
        }
        with (
            patch.object(rotator, "_resolve_profile", return_value=target),
            patch.object(rotator, "get_live_profile_states", return_value=(True, profiles)),
            patch.object(rotator, "_get_current_desktop_name", return_value="Default"),
            patch.object(rotator, "_get_bridge_resources", return_value={"ok": True}),
            patch.object(rotator, "ensure_shortcut_for_profile", return_value=Path("fixture.lnk")),
            patch.object(rotator.os, "startfile", create=True) as launch,
            patch.object(rotator, "close_idle_profile") as close,
        ):
            rc, result = rotator.open_profile(self.alt, force_local=True, no_wait=True, auto_close_idle=True)
        self.assertEqual(rc, 0)
        self.assertTrue(result["ok"])
        launch.assert_called_once()
        close.assert_not_called()

    def test_exebox_refuses_spawn_unless_explicitly_allowed(self):
        with (
            patch.object(locks.sys, "platform", "win32"),
            patch.object(rotator, "_get_current_desktop_name", return_value="exebox-fixture"),
            patch.object(subprocess, "Popen") as launch,
            patch.dict(os.environ, {"AGY_ALLOW_HEADLESS_BRIDGE": "0"}),
            patch.object(locks, "is_bridge_running", side_effect=[False, False, True]),
        ):
            errors = io.StringIO()
            with redirect_stderr(errors):
                self.assertFalse(locks.ensure_bridge_running(timeout=0))
            self.assertIn("exebox-fixture", errors.getvalue())
            launch.assert_not_called()
            with patch.dict(os.environ, {"AGY_ALLOW_HEADLESS_BRIDGE": "1"}):
                self.assertTrue(locks.ensure_bridge_running(timeout=0))
            launch.assert_called_once()

    def test_startup_wait_prefers_restarting_bridge_over_new_process(self):
        with (
            patch.object(locks, "is_bridge_running", side_effect=[False, True]) as probe,
            patch.object(locks.time, "sleep"),
            patch.object(subprocess, "Popen") as launch,
        ):
            self.assertTrue(locks.ensure_bridge_running())
        self.assertEqual(probe.call_count, 2)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
