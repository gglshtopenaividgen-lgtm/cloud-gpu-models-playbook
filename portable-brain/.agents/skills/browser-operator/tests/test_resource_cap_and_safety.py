#!/usr/bin/env python3
"""Unit tests for Global Agent Resource Caps (3 profiles / 6 tabs), Strict Hands-Off
User-Tab Protection, /health & /resources endpoints, AI Studio reliability & recovery,
and Gemini Web Task-mode/network recovery.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aiohttp.test_utils import AioHTTPTestCase

ARGON_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "argon_bridge"
DEEP_THINKING_SCRIPTS = Path(__file__).resolve().parents[2] / "deep-thinking" / "scripts"
for p in (ARGON_BRIDGE_DIR, DEEP_THINKING_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import server as srv
import profile_lock_manager as plm
import profile_rotator as pr
import profile_manager as pm
import aistudio_subagent as ais
import gemini_brain_driver as gbd
import consult_argon as ca


class TestBridgeServerCapsAndProtection(AioHTTPTestCase):
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

    async def test_health_and_resources_endpoints(self):
        resp = await self.client.get("/health")
        self.assertEqual(resp.status, 200)
        h = await resp.json()
        self.assertTrue(h["ok"])
        self.assertEqual(h["status"], "online")
        self.assertIn("interactive_desktop", h)
        self.assertIn("pid", h)

        resp2 = await self.client.get("/resources")
        self.assertEqual(resp2.status, 200)
        r = await resp2.json()
        self.assertTrue(r["ok"])
        self.assertEqual(r["max_agent_profiles"], 3)
        self.assertEqual(r["max_agent_tabs"], 6)
        self.assertEqual(r["active_agent_profiles_count"], 0)
        self.assertEqual(r["active_agent_tabs"], 0)

    async def test_max_agent_tabs_and_profiles_429_and_release(self):
        next_tid = {"v": 100}

        async def fake_send(action, params=None, preferred_profile=None, timeout=30.0, *, client_id=None):
            if action == "OPEN_TAB":
                next_tid["v"] += 1
                return {"ok": True, "tabId": next_tid["v"]}
            if action == "CLOSE_TAB":
                return {"ok": True}
            return {"ok": True}

        with mock.patch.object(srv, "send_extension_command", side_effect=fake_send):
            # Open 6 tabs across 3 profiles (2 per profile) -> all succeed
            opened = []
            for prof in ("Profile 14", "Profile 13", "Profile 9"):
                for _ in range(2):
                    r = await self.client.post("/command", json={
                        "action": "OPEN_TAB",
                        "profile": prof,
                        "owner": "test_agent",
                        "surface": "aistudio",
                        "params": {"url": "https://aistudio.google.com/prompts/new_chat"},
                    })
                    self.assertEqual(r.status, 200)
                    body = await r.json()
                    self.assertTrue(body["ok"])
                    opened.append((prof, body["tabId"]))

            # 7th tab on existing profile -> 429 AGENT_CAPACITY_REACHED (MAX_AGENT_TABS=6)
            r_cap_tab = await self.client.post("/command", json={
                "action": "OPEN_TAB",
                "profile": "Profile 14",
                "params": {"url": "https://gemini.google.com/app"},
            })
            self.assertEqual(r_cap_tab.status, 429)
            body_tab = await r_cap_tab.json()
            self.assertEqual(body_tab["code"], "AGENT_CAPACITY_REACHED")
            self.assertEqual(body_tab["resources"]["active_agent_tabs"], 6)

            # Release 1 tab -> now 5 tabs across 3 profiles; opening on a 4th profile still returns 429!
            prof0, tid0 = opened[0]
            r_close = await self.client.post("/command", json={
                "action": "CLOSE_TAB",
                "profile": prof0,
                "agent_guarded": True,
                "params": {"tabId": tid0},
            })
            self.assertEqual(r_close.status, 200)

            r_cap_prof = await self.client.post("/command", json={
                "action": "OPEN_TAB",
                "profile": "Profile 16",
                "params": {"url": "https://gemini.google.com/app"},
            })
            self.assertEqual(r_cap_prof.status, 429)
            body_prof = await r_cap_prof.json()
            self.assertEqual(body_prof["code"], "AGENT_CAPACITY_REACHED")
            self.assertEqual(body_prof["resources"]["active_agent_profiles_count"], 3)

            # Opening on one of the 3 active profiles now succeeds (5 -> 6 tabs)
            r_ok = await self.client.post("/command", json={
                "action": "OPEN_TAB",
                "profile": "Profile 14",
                "params": {"url": "https://gemini.google.com/app"},
            })
            self.assertEqual(r_ok.status, 200)

    async def test_seven_concurrent_opens_admit_exactly_six(self):
        reached_capacity = asyncio.Event()
        release_opens = asyncio.Event()
        opened_profiles = []
        profiles = ("Profile 14", "Profile 13", "Profile 9")
        for profile in profiles:
            srv.CONNECTED_CLIENTS[profile] = {
                "dir_name": profile,
                "ws": mock.Mock(closed=False),
            }

        async def fake_send(action, params=None, preferred_profile=None, timeout=30.0, *, client_id=None):
            self.assertEqual(action, "OPEN_TAB")
            self.assertEqual(client_id, preferred_profile)
            opened_profiles.append(preferred_profile)
            tab_id = 600 + len(opened_profiles)
            if len(opened_profiles) == 6:
                reached_capacity.set()
            await release_opens.wait()
            return {"ok": True, "tabId": tab_id}

        async def open_tab(profile):
            response = await self.client.post("/command", json={
                "action": "OPEN_TAB", "profile": profile, "params": {"url": "about:blank"},
            })
            return response.status, await response.json()

        with mock.patch.object(srv, "send_extension_command", side_effect=fake_send):
            tasks = [
                asyncio.create_task(open_tab(profiles[index % len(profiles)]))
                for index in range(7)
            ]
            try:
                await asyncio.wait_for(reached_capacity.wait(), 5)
                done, _ = await asyncio.wait(tasks, timeout=5, return_when=asyncio.FIRST_COMPLETED)
                self.assertEqual(len(done), 1, "Exactly one request must be rejected before any open completes")
                status, body = next(iter(done)).result()
                self.assertEqual(status, 429)
                self.assertEqual(body["code"], "AGENT_CAPACITY_REACHED")
                self.assertEqual(len(opened_profiles), 6)
            finally:
                release_opens.set()
                results = await asyncio.wait_for(asyncio.gather(*tasks), 5)

        self.assertEqual(sorted(status for status, _ in results), [200] * 6 + [429])
        snapshot = await (await self.client.get("/resources")).json()
        self.assertEqual(snapshot["active_agent_tabs"], 6)
        self.assertEqual(snapshot["active_agent_profiles_count"], 3)

    async def test_seven_concurrent_opens_same_profile_with_asyncio_gather(self):
        profile = "Profile 14"
        srv.CONNECTED_CLIENTS[profile] = {
            "dir_name": profile,
            "ws": mock.Mock(closed=False),
        }
        reached_six = asyncio.Event()
        release_all = asyncio.Event()
        call_count = 0

        async def fake_send(action, params=None, preferred_profile=None, timeout=30.0, *, client_id=None, **kwargs):
            nonlocal call_count
            self.assertEqual(action, "OPEN_TAB")
            call_count += 1
            cur = call_count
            if cur == 6:
                reached_six.set()
            await release_all.wait()
            return {"ok": True, "tabId": 700 + cur}

        async def call_open():
            resp = await self.client.post("/command", json={
                "action": "OPEN_TAB",
                "profile": profile,
                "params": {"url": "about:blank"},
            })
            return resp.status, await resp.json()

        with mock.patch.object(srv, "send_extension_command", side_effect=fake_send):
            tasks = [asyncio.create_task(call_open()) for _ in range(7)]
            await asyncio.wait_for(reached_six.wait(), timeout=5.0)
            release_all.set()
            results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=5.0)

        statuses = [status for status, _ in results]
        self.assertEqual(statuses.count(200), 6)
        self.assertEqual(statuses.count(429), 1)
        rejected = [body for status, body in results if status == 429][0]
        self.assertEqual(rejected["code"], "AGENT_CAPACITY_REACHED")

        snapshot = await (await self.client.get("/resources")).json()
        self.assertEqual(snapshot["active_agent_tabs"], 6)
        self.assertEqual(snapshot["active_agent_profiles_count"], 1)

    async def test_reconciliation_preserves_open_completed_after_inventory_started(self):
        profile = "Profile 14"
        client_id = "profile-14-connection"
        srv.CONNECTED_CLIENTS[client_id] = {
            "dir_name": profile,
            "ws": mock.Mock(closed=False),
        }
        srv.register_agent_tab(profile, 501, owner="fixture")
        open_started = asyncio.Event()
        inventory_started = asyncio.Event()
        finish_open = asyncio.Event()
        finish_inventory = asyncio.Event()
        inventory_count = 0

        async def fake_send(action, params=None, preferred_profile=None, timeout=30.0, *, client_id=None):
            nonlocal inventory_count
            self.assertEqual(client_id, "profile-14-connection")
            self.assertEqual(preferred_profile, profile)
            if action == "OPEN_TAB":
                open_started.set()
                await finish_open.wait()
                return {"ok": True, "tabId": 502}
            self.assertEqual(action, "LIST_TABS")
            inventory_count += 1
            if inventory_count == 1:
                return {"ok": True, "tabs": [{"id": 501}]}
            inventory_started.set()
            await finish_inventory.wait()
            return {"ok": True, "tabs": []}

        with mock.patch.object(srv, "send_extension_command", side_effect=fake_send):
            tasks = [asyncio.create_task(self.client.post("/command", json={
                "action": "OPEN_TAB", "profile": profile, "params": {"url": "about:blank"},
            }))]
            try:
                await asyncio.wait_for(open_started.wait(), 5)
                tasks.append(asyncio.create_task(self.client.get("/resources?reconcile=1")))
                await asyncio.wait_for(inventory_started.wait(), 5)
                finish_open.set()
                response = await asyncio.wait_for(asyncio.shield(tasks[0]), 5)
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())["tabId"], 502)
                self.assertTrue(srv.is_agent_owned_tab(profile, 502))
                finish_inventory.set()
                response = await asyncio.wait_for(asyncio.shield(tasks[1]), 5)
                self.assertEqual(response.status, 200)
                snapshot = await response.json()
                self.assertEqual(set(snapshot["owned_tabs"][profile]), {"502"})
            finally:
                finish_open.set()
                finish_inventory.set()
                await asyncio.wait_for(asyncio.gather(*tasks), 5)

    async def test_user_tab_protected_on_close_and_park(self):
        srv.register_agent_tab("Profile 14", 501, owner="agent", surface="aistudio")

        async def fake_send(action, params=None, preferred_profile=None, timeout=30.0, *, client_id=None):
            return {"ok": True}

        with mock.patch.object(srv, "send_extension_command", side_effect=fake_send):
            # Unowned user tab 999 -> CLOSE_TAB refused (403 USER_TAB_PROTECTED)
            r1 = await self.client.post("/command", json={
                "action": "CLOSE_TAB",
                "profile": "Profile 14",
                "agent_guarded": True,
                "params": {"tabId": 999},
            })
            self.assertEqual(r1.status, 403)
            self.assertEqual((await r1.json())["code"], "USER_TAB_PROTECTED")

            # Missing tabId on guarded CLOSE_TAB -> 403 USER_TAB_PROTECTED
            r1_missing = await self.client.post("/command", json={
                "action": "CLOSE_TAB",
                "profile": "Profile 14",
                "agent_guarded": True,
                "params": {},
            })
            self.assertEqual(r1_missing.status, 403)
            self.assertEqual((await r1_missing.json())["code"], "USER_TAB_PROTECTED")

            # Missing agent_guarded flag defaults to True and blocks unowned tab 999
            r1_default = await self.client.post("/command", json={
                "action": "CLOSE_TAB",
                "profile": "Profile 14",
                "params": {"tabId": 999},
            })
            self.assertEqual(r1_default.status, 403)
            self.assertEqual((await r1_default.json())["code"], "USER_TAB_PROTECTED")

            # Unowned user tab 999 -> Page.navigate (about:blank park) refused (403 USER_TAB_PROTECTED)
            r2 = await self.client.post("/command", json={
                "action": "CDP_COMMAND",
                "profile": "Profile 14",
                "agent_guarded": True,
                "params": {"tabId": 999, "method": "Page.navigate", "params": {"url": "about:blank"}},
            })
            self.assertEqual(r2.status, 403)
            self.assertEqual((await r2.json())["code"], "USER_TAB_PROTECTED")

            # Missing tabId on guarded Page.navigate -> 403 USER_TAB_PROTECTED
            r2_missing = await self.client.post("/command", json={
                "action": "CDP_COMMAND",
                "profile": "Profile 14",
                "agent_guarded": True,
                "params": {"method": "Page.navigate", "params": {"url": "about:blank"}},
            })
            self.assertEqual(r2_missing.status, 403)
            self.assertEqual((await r2_missing.json())["code"], "USER_TAB_PROTECTED")

            # Explicit agent_guarded=False override allows CLOSE_TAB
            r_override = await self.client.post("/command", json={
                "action": "CLOSE_TAB",
                "profile": "Profile 14",
                "agent_guarded": False,
                "params": {"tabId": 999},
            })
            self.assertEqual(r_override.status, 200)

            # Agent-owned tab 501 -> Page.navigate & CLOSE_TAB allowed!
            r3 = await self.client.post("/command", json={
                "action": "CDP_COMMAND",
                "profile": "Profile 14",
                "agent_guarded": True,
                "params": {"tabId": 501, "method": "Page.navigate", "params": {"url": "about:blank"}},
            })
            self.assertEqual(r3.status, 200)

            r4 = await self.client.post("/command", json={
                "action": "CLOSE_TAB",
                "profile": "Profile 14",
                "agent_guarded": True,
                "params": {"tabId": 501},
            })
            self.assertEqual(r4.status, 200)
            self.assertFalse(srv.is_agent_owned_tab("Profile 14", 501))


class TestDriverTabProtectionAndRotatorSafety(unittest.TestCase):
    def test_aistudio_and_gemini_drivers_skip_user_tabs(self):
        # User has personal AI Studio tab (id=10) & YouTube tab (id=11) open; owned_tabs is empty!
        calls = []

        def fake_ais_api(endpoint, method="GET", payload=None, timeout=30.0):
            calls.append((endpoint, payload))
            if endpoint == "/resources":
                return {"ok": True, "owned_tabs": {"Profile 14": {}}}
            if payload and payload.get("action") == "LIST_TABS":
                return {"ok": True, "tabs": [
                    {"id": 10, "url": "https://aistudio.google.com/prompts/my_personal_prompt"},
                    {"id": 11, "url": "https://www.youtube.com/watch?v=abc"},
                ]}
            if payload and payload.get("action") == "OPEN_TAB":
                return {"ok": True, "tabId": 777}
            return {"ok": True}

        with mock.patch.object(ais, "call_bridge_api", side_effect=fake_ais_api):
            tid, reused = ais.find_or_open_ai_studio_tab({"dir_name": "Profile 14"})
        self.assertEqual(tid, 777)
        self.assertFalse(reused)
        self.assertTrue(any(p and p.get("action") == "OPEN_TAB" for _, p in calls))

        # Gemini driver also skips user's personal Gemini tab (id=20)
        driver = gbd.GeminiBrainDriver(default_profile="Profile 14")

        def fake_raw(endpoint, payload=None, method="POST", timeout=30.0, profile=None):
            if endpoint == "/resources":
                return {"ok": True, "owned_tabs": {"Profile 14": {"888": {"owner": "agent"}}}}
            if payload and payload.get("action") == "LIST_TABS":
                return {"ok": True, "tabs": [
                    {"id": 20, "url": "https://gemini.google.com/app/personal_chat", "active": True},
                    {"id": 21, "url": "https://www.youtube.com/"},
                ]}
            return {"ok": True}

        driver._call_api_raw = fake_raw
        self.assertIsNone(driver.get_open_gemini_tab(profile="Profile 14"))

    def test_rotator_refuses_closing_window_with_user_tabs(self):
        fake_prof = pm.ChromeProfile(
            dir_name="Profile 14", name="Alt1", email="alt1@example.com",
            gaia_name="Alt1", is_ai_premium=True, ai_subscription_tier="pro",
            avatar_path="", is_daily_driver=False, has_bridge_extension=True,
        )
        fake_states = {
            "Profile 14": {
                "profile": fake_prof,
                "connected": True,
                "is_open": True,
                "tabs_count": 2,
                "tabs": [
                    {"id": 101, "url": "https://aistudio.google.com/prompts/new_chat", "title": "AI Studio"},
                    {"id": 202, "url": "https://www.youtube.com/watch?v=xyz", "title": "YouTube"},
                ],
                "shortcut_path": "",
                "shortcut_exists": True,
                "list_error": "",
            }
        }
        closed_tabs = []

        def fake_http(method, path, payload=None, timeout=5.0):
            if path == "/resources":
                return {
                    "ok": True,
                    "active_locks": {},
                    "launched_by_agent": {"Profile 14": {"owner": "rotator"}},
                    "owned_tabs": {"Profile 14": {"101": {"owner": "agent"}}},
                }
            if path == "/command" and payload and payload.get("action") == "CLOSE_TAB":
                closed_tabs.append(payload["params"]["tabId"])
                return {"ok": True}
            return {"ok": True}

        with (
            mock.patch.object(pr, "_resolve_profile", return_value=fake_prof),
            mock.patch.object(pr, "get_live_profile_states", return_value=(True, fake_states)),
            mock.patch.object(pr, "_http_json", side_effect=fake_http),
        ):
            rc, res = pr.close_profile("Profile 14", idle_eviction=True)

        self.assertEqual(rc, 3)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "USER_TAB_PROTECTED")
        self.assertEqual(closed_tabs, [])

    def test_rotator_refuses_closing_window_when_profile_has_active_lease(self):
        fake_prof = pm.ChromeProfile(
            dir_name="Profile 14", name="Alt1", email="alt1@example.com",
            gaia_name="Alt1", is_ai_premium=True, ai_subscription_tier="pro",
            avatar_path="", is_daily_driver=False, has_bridge_extension=True,
        )
        fake_states = {
            "Profile 14": {
                "profile": fake_prof, "connected": True, "is_open": True, "tabs_count": 1,
                "tabs": [{"id": 101, "url": "https://aistudio.google.com/prompts/new_chat", "title": "AI Studio"}],
                "shortcut_path": "", "shortcut_exists": True, "list_error": "",
            }
        }
        def fake_http(method, path, payload=None, timeout=5.0):
            if path == "/resources":
                return {
                    "ok": True,
                    "active_locks": {"Profile 14::aistudio": {"profile": "Profile 14", "surface": "aistudio"}},
                    "launched_by_agent": {"Profile 14": {"owner": "rotator"}},
                    "owned_tabs": {"Profile 14": {"101": {"owner": "agent"}}},
                }
            return {"ok": True}

        with (
            mock.patch.object(pr, "_resolve_profile", return_value=fake_prof),
            mock.patch.object(pr, "get_live_profile_states", return_value=(True, fake_states)),
            mock.patch.object(pr, "_http_json", side_effect=fake_http),
        ):
            rc, res = pr.close_idle_profile("Profile 14")

        self.assertEqual(rc, 3)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "PROFILE_BUSY")

    def test_rotator_refuses_closing_window_when_list_tabs_fails(self):
        fake_prof = pm.ChromeProfile(
            dir_name="Profile 14", name="Alt1", email="alt1@example.com",
            gaia_name="Alt1", is_ai_premium=True, ai_subscription_tier="pro",
            avatar_path="", is_daily_driver=False, has_bridge_extension=True,
        )
        fake_states = {
            "Profile 14": {
                "profile": fake_prof, "connected": True, "is_open": True, "tabs_count": 0,
                "tabs": [], "shortcut_path": "", "shortcut_exists": True,
                "list_error": "WebSocket timeout on LIST_TABS",
            }
        }
        with (
            mock.patch.object(pr, "_resolve_profile", return_value=fake_prof),
            mock.patch.object(pr, "get_live_profile_states", return_value=(True, fake_states)),
        ):
            rc, res = pr.close_idle_profile("Profile 14")

        self.assertEqual(rc, 1)
        self.assertFalse(res["ok"])
        self.assertEqual(res["code"], "TAB_STATE_UNKNOWN")


class TestAIStudioAndGeminiReliabilityAndRecovery(unittest.TestCase):
    def test_js_helpers_parse_cleanly_in_node_and_check_visibility_guards(self):
        # Verify both AI_STUDIO_HELPERS_JS and Gemini HELPER_JS parse cleanly in Node.js
        for label, js_src in (
            ("AI_STUDIO_HELPERS_JS", "const window = {};\n" + ais.AI_STUDIO_HELPERS_JS),
            ("GEMINI_HELPER_JS", "const window = {};\n" + gbd.HELPER_JS),
        ):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
                f.write(js_src)
                tmp_js = f.name
            try:
                proc = subprocess.run(["node", "--check", tmp_js], capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, f"{label} JS syntax error: {proc.stderr}")
            finally:
                Path(tmp_js).unlink(missing_ok=True)

        # Verify visibility & exclusion checks exist in _isStopControlVisible
        self.assertIn("el.offsetParent === null", ais.AI_STUDIO_HELPERS_JS)
        self.assertIn("stop sequence", ais.AI_STUDIO_HELPERS_JS)
        self.assertIn(".right-panel", ais.AI_STUDIO_HELPERS_JS)
        self.assertIn("findSubmitButton", gbd.HELPER_JS)

    def test_aistudio_empty_harvest_timeout_and_error_banner_fast_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            shot_calls = []

            def make_fake_bridge(status_seq):
                idx = {"i": 0}

                def fake_api(endpoint, method="GET", payload=None, timeout=30.0):
                    if not payload:
                        return {"ok": True}
                    act = payload.get("action")
                    code = (payload.get("params") or {}).get("code", "")
                    if act == "EVAL_DOM":
                        if "window.location.href" in code:
                            return {"ok": True, "result": "https://aistudio.google.com/prompts/new_chat"}
                        if "assertActiveModel" in code:
                            return {"ok": True, "result": {"ok": True, "actual": "Gemini 4 Argon"}}
                        if "getGenerationStatus(" in code:
                            i = min(idx["i"], len(status_seq) - 1)
                            idx["i"] += 1
                            return status_seq[i]
                        if "harvestRichContent(" in code:
                            return {"ok": True, "result": {"ok": True, "text": "", "thoughts": ""}}
                        return {"ok": True, "result": {"ok": True}}
                    return {"ok": True, "result": {}}

                return fake_api

            # Case 1: Empty harvest timeout returns ok=False & EMPTY_HARVEST_TIMEOUT (never ok=True!)
            empty_seq = [
                {"ok": True, "result": {"is_generating": False, "answer_turns_count": 0, "text_length": 0, "has_answer": False}},
                {"ok": True, "result": {"is_generating": True, "answer_turns_count": 0, "text_length": 0, "has_answer": False}},
            ]
            with (
                mock.patch.object(ais, "profile_lock_manager", None),
                mock.patch.object(ais, "popup_healer", None),
                mock.patch.object(ais, "ensure_extension_ready", return_value={"dir_name": "Profile 14"}),
                mock.patch.object(ais, "find_or_open_ai_studio_tab", return_value=(123, True)),
                mock.patch.object(ais, "capture_tab_screenshot", side_effect=lambda c, t, p: shot_calls.append(p) or True),
                mock.patch.object(ais, "park_tab_about_blank"),
                mock.patch.object(ais, "call_bridge_api", side_effect=make_fake_bridge(empty_seq)),
                mock.patch.object(ais.time, "sleep", return_value=None),
            ):
                res = ais.ask_ai_studio(
                    prompt="hi",
                    timeout_sec=0.05,
                    poll_interval_sec=0.02,
                    stall_reload_sec=999.0,
                    output_file=str(Path(tmp) / "out.md"),
                )
            self.assertFalse(res["ok"])
            self.assertEqual(res["code"], "EMPTY_HARVEST_TIMEOUT")
            self.assertTrue(any("aistudio_timeout_diag.png" in p for p in shot_calls))

            # Case 2: Error banner fast-fails immediately with AISTUDIO_ERROR_BANNER
            banner_seq = [
                {"ok": True, "result": {"is_generating": False, "answer_turns_count": 0, "text_length": 0, "has_answer": False}},
                {"ok": True, "result": {"is_generating": False, "answer_turns_count": 0, "text_length": 0, "has_answer": False, "error_banner": "Quota exceeded for model", "is_transient_network_error": False}},
            ]
            with (
                mock.patch.object(ais, "profile_lock_manager", None),
                mock.patch.object(ais, "popup_healer", None),
                mock.patch.object(ais, "ensure_extension_ready", return_value={"dir_name": "Profile 14"}),
                mock.patch.object(ais, "find_or_open_ai_studio_tab", return_value=(123, True)),
                mock.patch.object(ais, "capture_tab_screenshot", return_value=True),
                mock.patch.object(ais, "park_tab_about_blank"),
                mock.patch.object(ais, "call_bridge_api", side_effect=make_fake_bridge(banner_seq)),
                mock.patch.object(ais.time, "sleep", return_value=None),
            ):
                res_err = ais.ask_ai_studio(
                    prompt="hi",
                    timeout_sec=300,
                    poll_interval_sec=0.01,
                    output_file=str(Path(tmp) / "out2.md"),
                )
            self.assertFalse(res_err["ok"])
            self.assertEqual(res_err["code"], "AISTUDIO_ERROR_BANNER")
            self.assertIn("Quota exceeded", res_err["error_banner"])

    def test_aistudio_transient_network_and_stall_recovery_succeeds_bounded(self):
        reloads = []
        reruns = []
        heal_calls = []

        status_seq = [
            {"ok": True, "result": {"is_generating": False, "answer_turns_count": 0, "text_length": 0, "has_answer": False}},  # baseline
            {"ok": True, "result": {"is_generating": False, "answer_turns_count": 0, "text_length": 0, "has_answer": False, "error_banner": "ERR_INTERNET_DISCONNECTED", "is_transient_network_error": True}},
            {"ok": True, "result": {"is_generating": False, "answer_turns_count": 1, "text_length": 18, "has_answer": True}},
            {"ok": True, "result": {"is_generating": False, "answer_turns_count": 1, "text_length": 18, "has_answer": True}},
            {"ok": True, "result": {"is_generating": False, "answer_turns_count": 1, "text_length": 18, "has_answer": True}},
        ]
        idx = {"i": 0}

        def fake_api(endpoint, method="GET", payload=None, timeout=30.0):
            if not payload:
                return {"ok": True}
            act = payload.get("action")
            params = payload.get("params") or {}
            code = params.get("code", "")
            if act == "CDP_COMMAND" and params.get("method") == "Page.reload":
                reloads.append(True)
                return {"ok": True}
            if act == "EVAL_DOM":
                if code.startswith("window.__agyStudio.rerunCurrentPrompt("):
                    reruns.append(code)
                    return {"ok": True, "result": {"ok": True, "method": "rerun_btn"}}
                if "window.location.href" in code:
                    return {"ok": True, "result": "https://aistudio.google.com/prompts/new_chat"}
                if "assertActiveModel" in code:
                    return {"ok": True, "result": {"ok": True, "actual": "Gemini 4 Argon"}}
                if "getGenerationStatus(" in code:
                    i = min(idx["i"], len(status_seq) - 1)
                    idx["i"] += 1
                    return status_seq[i]
                if "harvestRichContent(" in code:
                    return {"ok": True, "result": {"ok": True, "text": "Recovered answer!!", "thoughts": ""}}
                return {"ok": True, "result": {"ok": True}}
            return {"ok": True}

        fake_healer = mock.MagicMock()
        fake_healer.dismiss_blocking_popups.side_effect = lambda **kw: heal_calls.append(kw) or {"blocked": False}

        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(ais, "profile_lock_manager", None),
                mock.patch.object(ais, "popup_healer", fake_healer),
                mock.patch.object(ais, "ensure_extension_ready", return_value={"dir_name": "Profile 14"}),
                mock.patch.object(ais, "find_or_open_ai_studio_tab", return_value=(123, True)),
                mock.patch.object(ais, "park_tab_about_blank"),
                mock.patch.object(ais, "call_bridge_api", side_effect=fake_api),
                mock.patch.object(ais.time, "sleep", return_value=None),
            ):
                res = ais.ask_ai_studio(
                    prompt="recover me",
                    timeout_sec=10,
                    poll_interval_sec=0.01,
                    max_recovery_retries=2,
                    output_file=str(Path(tmp) / "recovered.md"),
                )

        self.assertTrue(res["ok"], res)
        self.assertEqual(res["text"], "Recovered answer!!")
        self.assertEqual(reloads, [])
        self.assertEqual(len(reruns), 1)
        self.assertGreaterEqual(len(heal_calls), 2)

    def test_aistudio_retries_one_completed_empty_response_then_fails(self):
        empty = {"is_generating": False, "has_feedback_buttons": True, "text_length": 0}
        statuses = iter([{}, empty, {"is_generating": True}, empty])
        actions = []

        def bridge(endpoint, method="GET", payload=None, timeout=30.0):
            params = (payload or {}).get("params", {})
            code = params.get("code", "")
            actions.append(params.get("method") or code)
            if "window.location.href" in code:
                return {"ok": True, "result": "https://aistudio.google.com/prompts/new_chat"}
            if "assertActiveModel" in code:
                return {"ok": True, "result": {"ok": True, "actual": "Gemini 4 Argon"}}
            if code.startswith("window.__agyStudio.getGenerationStatus("):
                return {"ok": True, "result": next(statuses)}
            return {"ok": True, "result": {"ok": True}}

        with (
            mock.patch.object(ais, "profile_lock_manager", None),
            mock.patch.object(ais, "popup_healer", None),
            mock.patch.object(ais, "ensure_extension_ready", return_value={"dir_name": "Profile 14"}),
            mock.patch.object(ais, "find_or_open_ai_studio_tab", return_value=(123, True)),
            mock.patch.object(ais, "call_bridge_api", side_effect=bridge),
            mock.patch.object(ais.time, "sleep", return_value=None),
        ):
            result = ais.ask_ai_studio(prompt="retry fixture", timeout_sec=10, poll_interval_sec=0.01, keep_tab=True)

        self.assertEqual(result["code"], "EMPTY_MODEL_RESPONSE")
        self.assertEqual(result["recovery_attempts"], 1)
        self.assertIn("Emulation.setFocusEmulationEnabled", actions)
        self.assertNotIn("Page.reload", actions)

    def test_aistudio_reclaims_only_when_a_tab_can_keep_its_window_open(self):
        own_tab = {"id": 123, "windowId": 11}
        for sibling_window, expected_close in ((11, True), (22, False)):
            actions = []

            def bridge(endpoint, method="GET", payload=None, timeout=30.0):
                actions.append(payload)
                return {"ok": True, "tabs": [own_tab, {"id": 456, "windowId": sibling_window}]}

            with mock.patch.object(ais, "call_bridge_api", side_effect=bridge):
                ais.reclaim_finished_tab("Profile 14", 123)

            self.assertEqual(actions[0]["action"], "LIST_TABS")
            operation = actions[1]
            self.assertEqual(operation["action"], "CLOSE_TAB" if expected_close else "CDP_COMMAND")
            self.assertEqual(operation["params"]["tabId"], 123)
            self.assertTrue(operation["agent_guarded"])
            if not expected_close:
                self.assertEqual(operation["params"]["params"]["url"], "about:blank")

    def test_consult_argon_status_banner_format(self):
        banner = ca.format_status_banner({
            "active_agent_profiles_count": 2,
            "max_agent_profiles": 3,
            "active_agent_tabs": 4,
            "max_agent_tabs": 6,
        })
        self.assertEqual(
            banner,
            "Agent Fleet Budget: Profiles [2/3] | Tabs [4/6] (User tabs & windows strictly protected)",
        )


if __name__ == "__main__":
    unittest.main()
