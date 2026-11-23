#!/usr/bin/env python3
"""
Unit tests for Wave 6B:
- Auto-Reaper for Blank Tabs & Unused Tier-1 Alt Profiles (server.py + profile_rotator.py)
- Zero-Touch Daily Driver Protection (Profile 7, 8, 9, 16)
- AI Studio Subagent Clean Tab Closure (with fallback to park_tab_about_blank)
- Gemini Brain Driver delete_session / delete_chat Retry & Clean Tab Closure
"""

import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from aiohttp.test_utils import AioHTTPTestCase

ARGON_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "argon_bridge"
if str(ARGON_BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(ARGON_BRIDGE_DIR))

import server as srv
import profile_lock_manager as plm
import profile_manager as pm
import profile_rotator as pr
import aistudio_subagent as ais
import gemini_brain_driver as gbd


class TestBlankTabReaperServer(AioHTTPTestCase):
    async def get_application(self):
        return srv.create_app()

    async def asyncSetUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_res = srv.RESOURCES_FILE
        self._orig_locks = plm.LOCKS_FILE
        srv.RESOURCES_FILE = Path(self._tmp.name) / "bridge_agent_resources.json"
        plm.LOCKS_FILE = Path(self._tmp.name) / "bridge_profile_locks.json"
        srv.CONNECTED_CLIENTS.clear()
        await super().asyncSetUp()

    async def asyncTearDown(self):
        await super().asyncTearDown()
        srv.RESOURCES_FILE = self._orig_res
        plm.LOCKS_FILE = self._orig_locks
        srv.CONNECTED_CLIENTS.clear()
        self._tmp.cleanup()

    async def test_cleanup_idle_endpoint_returns_json(self):
        """POST /cleanup/idle responds with ok: True and status counts."""
        resp = await self.client.post("/cleanup/idle", json={"idle_seconds": 0.0})
        self.assertEqual(resp.status, 200)
        data = await resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("closed_blank_tabs", data)
        self.assertIn("closed_idle_profiles", data)

    async def test_reap_closes_blank_tabs_on_tier1_alt_and_preserves_real_tabs(self):
        """Tier-1 Alt profile with real + blank tabs closes ONLY blank tabs."""
        p14 = pm.ChromeProfile(
            dir_name="Profile 14", name="Alt 14", email="alt14@example.com",
            gaia_name="Alt 14", ai_subscription_tier=1, is_ai_premium=True,
            avatar_path="", is_daily_driver=False, last_used=time.time() - 300,
        )
        srv.CONNECTED_CLIENTS["c_14"] = {
            "dir_name": "Profile 14", "email": "alt14@example.com", "last_ping": time.time() - 300,
        }

        tabs_list = [
            {"id": 101, "url": "https://flow.google.com/workbench", "windowId": 1},
            {"id": 102, "url": "about:blank", "windowId": 1},
            {"id": 103, "url": "chrome://newtab/", "windowId": 1},
        ]

        closed_tab_ids = []

        async def mock_send(action, params=None, preferred_profile=None, timeout=30.0, **kwargs):
            if action == "LIST_TABS":
                return {"ok": True, "tabs": tabs_list}
            if action == "CLOSE_TAB":
                closed_tab_ids.append((params or {}).get("tabId"))
                return {"ok": True}
            return {"ok": False}

        with mock.patch.object(pm, "get_all_profiles", return_value=[p14]), \
             mock.patch.object(plm, "clean_expired_locks", return_value={}), \
             mock.patch.object(srv, "send_extension_command", side_effect=mock_send):
            res = await srv.reap_idle_tabs_and_profiles(idle_seconds=0.0)

        self.assertEqual(len(res["closed_blank_tabs"]), 2)
        self.assertEqual(sorted(closed_tab_ids), [102, 103])
        self.assertNotIn(101, closed_tab_ids)

    async def test_reap_skips_daily_drivers_completely(self):
        """Daily Driver profiles (Profile 7, 8, 9, 16) are NEVER touched."""
        daily_profiles = []
        for idx, dir_name in enumerate(("Profile 7", "Profile 8", "Profile 9", "Profile 16")):
            p = pm.ChromeProfile(
                dir_name=dir_name, name=f"Daily {dir_name}", email=f"daily{idx}@gmail.com",
                gaia_name=f"Daily {dir_name}", ai_subscription_tier=1, is_ai_premium=True,
                avatar_path="", is_daily_driver=True, last_used=time.time() - 500,
            )
            daily_profiles.append(p)
            srv.CONNECTED_CLIENTS[f"c_{dir_name}"] = {
                "dir_name": dir_name, "email": f"daily{idx}@gmail.com", "last_ping": time.time() - 500,
            }

        tabs_list = [
            {"id": 201, "url": "about:blank", "windowId": 1},
            {"id": 202, "url": "chrome://newtab", "windowId": 1},
        ]

        closed_tab_ids = []

        async def mock_send(action, params=None, preferred_profile=None, timeout=30.0, **kwargs):
            if action == "LIST_TABS":
                return {"ok": True, "tabs": tabs_list}
            if action == "CLOSE_TAB":
                closed_tab_ids.append((params or {}).get("tabId"))
                return {"ok": True}
            return {"ok": False}

        with mock.patch.object(pm, "get_all_profiles", return_value=daily_profiles), \
             mock.patch.object(plm, "clean_expired_locks", return_value={}), \
             mock.patch.object(srv, "send_extension_command", side_effect=mock_send):
            res = await srv.reap_idle_tabs_and_profiles(idle_seconds=0.0)

        self.assertEqual(len(res["closed_blank_tabs"]), 0)
        self.assertEqual(len(res["closed_idle_profiles"]), 0)
        self.assertEqual(closed_tab_ids, [])

    async def test_reap_skips_profiles_with_active_leases(self):
        """Tier-1 Alt profile is skipped if actively leased in profile_lock_manager."""
        p13 = pm.ChromeProfile(
            dir_name="Profile 13", name="Alt 13", email="alt13@example.com",
            gaia_name="Alt 13", ai_subscription_tier=1, is_ai_premium=True,
            avatar_path="", is_daily_driver=False, last_used=time.time() - 300,
        )
        srv.CONNECTED_CLIENTS["c_13"] = {
            "dir_name": "Profile 13", "email": "alt13@example.com", "last_ping": time.time() - 300,
        }

        tabs_list = [{"id": 301, "url": "about:blank", "windowId": 1}]
        closed_tab_ids = []

        async def mock_send(action, params=None, preferred_profile=None, timeout=30.0, **kwargs):
            if action == "LIST_TABS":
                return {"ok": True, "tabs": tabs_list}
            if action == "CLOSE_TAB":
                closed_tab_ids.append((params or {}).get("tabId"))
                return {"ok": True}
            return {"ok": False}

        active_locks = {"Profile 13::lock": {"profile": "Profile 13", "held_by": "pid_1234"}}
        with mock.patch.object(pm, "get_all_profiles", return_value=[p13]), \
             mock.patch.object(plm, "clean_expired_locks", return_value=active_locks), \
             mock.patch.object(srv, "send_extension_command", side_effect=mock_send):
            res = await srv.reap_idle_tabs_and_profiles(idle_seconds=0.0)

        self.assertEqual(len(res["closed_blank_tabs"]), 0)
        self.assertEqual(len(res["closed_idle_profiles"]), 0)
        self.assertEqual(closed_tab_ids, [])

    async def test_reap_closes_idle_all_blank_profile(self):
        """When all tabs on an idle Tier-1 Alt profile are blank, closing them releases the profile."""
        p14 = pm.ChromeProfile(
            dir_name="Profile 14", name="Alt 14", email="alt14@example.com",
            gaia_name="Alt 14", ai_subscription_tier=1, is_ai_premium=True,
            avatar_path="", is_daily_driver=False, last_used=time.time() - 300,
        )
        srv.CONNECTED_CLIENTS["c_14"] = {
            "dir_name": "Profile 14", "email": "alt14@example.com", "last_ping": time.time() - 300,
        }

        tabs_list = [
            {"id": 401, "url": "about:blank", "windowId": 1},
            {"id": 402, "url": "chrome://newtab/", "windowId": 1},
        ]
        closed_tab_ids = []

        async def mock_send(action, params=None, preferred_profile=None, timeout=30.0, **kwargs):
            if action == "LIST_TABS":
                return {"ok": True, "tabs": tabs_list}
            if action == "CLOSE_TAB":
                closed_tab_ids.append((params or {}).get("tabId"))
                return {"ok": True}
            return {"ok": False}

        with mock.patch.object(pm, "get_all_profiles", return_value=[p14]), \
             mock.patch.object(plm, "clean_expired_locks", return_value={}), \
             mock.patch.object(srv, "send_extension_command", side_effect=mock_send), \
             mock.patch.object(srv, "release_agent_launched_profile") as mock_rel:
            res = await srv.reap_idle_tabs_and_profiles(idle_seconds=0.0)

        self.assertEqual(len(res["closed_blank_tabs"]), 2)
        self.assertEqual(len(res["closed_idle_profiles"]), 1)
        self.assertEqual(sorted(closed_tab_ids), [401, 402])
        mock_rel.assert_called_once_with("Profile 14", clear_tabs=True)


class TestProfileRotatorCleanup(unittest.TestCase):
    def test_cleanup_idle_calls_http_endpoint(self):
        """profile_rotator.cleanup_idle invokes POST /cleanup/idle with idle_seconds."""
        with mock.patch.object(pr, "_http_json", return_value={"ok": True, "closed_blank_tabs": 1, "closed_idle_profiles": 0}) as mock_http:
            rc = pr.cleanup_idle(idle_seconds=15.0)
            self.assertEqual(rc, 0)
            mock_http.assert_called_once_with("POST", "/cleanup/idle", {"idle_seconds": 15.0})


class TestAIStudioSubagentTabReclaim(unittest.TestCase):
    def test_reclaim_finished_tab_closes_first(self):
        """reclaim_finished_tab calls CLOSE_TAB directly without parking at about:blank if successful."""
        with mock.patch.object(ais, "call_bridge_api", return_value={"ok": True}) as mock_call, \
             mock.patch.object(ais, "park_tab_about_blank") as mock_park:
            ais.reclaim_finished_tab("Profile 14", 555)
            mock_call.assert_called_once_with(
                "/command",
                method="POST",
                payload={"action": "CLOSE_TAB", "profile": "Profile 14", "agent_guarded": True, "params": {"tabId": 555}},
                timeout=5.0,
            )
            mock_park.assert_not_called()

    def test_reclaim_finished_tab_falls_back_to_park_on_failure(self):
        """reclaim_finished_tab falls back to park_tab_about_blank if CLOSE_TAB fails."""
        with mock.patch.object(ais, "call_bridge_api", return_value={"ok": False, "error": "tab closed"}), \
             mock.patch.object(ais, "park_tab_about_blank") as mock_park:
            ais.reclaim_finished_tab("Profile 14", 555)
            mock_park.assert_called_once_with("Profile 14", 555)


class TestGeminiBrainDriverDeleteRetry(unittest.TestCase):
    def setUp(self):
        self.driver = gbd.GeminiBrainDriver()
        self.driver.registry = {
            "test_sess": {
                "tab_id": 999,
                "chat_id": "abc123xyz",
                "profile": "Profile 14",
                "own_tab": True,
            }
        }

    def test_delete_session_retries_and_succeeds(self):
        """delete_session retries upon initial JS failure and navigates/re-injects helper."""
        call_count = [0]

        def mock_execute_js(tab_id, script, profile=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"ok": False, "error": "Simulated initial DOM failure"}
            return {"ok": True, "result": {"ok": True, "deleted_chat_id": "abc123xyz"}}

        with mock.patch.object(self.driver, "execute_js", side_effect=mock_execute_js), \
             mock.patch.object(self.driver, "_call_api", return_value={"ok": True}) as mock_api, \
             mock.patch.object(self.driver, "inject_helper") as mock_inj, \
             mock.patch("time.sleep"):
            res = self.driver.delete_session("test_sess", max_retries=2, close_tab=True)

        self.assertEqual(call_count[0], 2)
        self.assertTrue(res.get("ok"))
        self.assertEqual(res.get("result", {}).get("deleted_chat_id"), "abc123xyz")
        mock_inj.assert_called_once_with(999, profile="Profile 14")
        self.assertNotIn("test_sess", self.driver.registry)

    def test_delete_chat_alias(self):
        """delete_chat is an alias for delete_session."""
        with mock.patch.object(self.driver, "delete_session", return_value={"ok": True}) as mock_del:
            self.driver.delete_chat("test_sess", profile="Profile 14", max_retries=1, close_tab=False)
            mock_del.assert_called_once_with(session_id="test_sess", profile="Profile 14", max_retries=1, close_tab=False)


if __name__ == "__main__":
    unittest.main()
