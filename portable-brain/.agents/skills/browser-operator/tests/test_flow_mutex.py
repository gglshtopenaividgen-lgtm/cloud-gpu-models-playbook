import json
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "argon_bridge"))
import profile_lock_manager as leases


class FlowMutexTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name, path in {
            "FLOW_STATE_FILE": root / "flow_state.json",
            "LOCKS_LOCK_FILE": root / "bridge.lock",
            "LOCKS_FILE": root / "leases.json",
            "FLOW_REGISTRY_FILE": root / "registry.json",
        }.items():
            previous = getattr(leases, name)
            setattr(leases, name, path)
            self.addCleanup(setattr, leases, name, previous)
            if name == "FLOW_REGISTRY_FILE":
                path.write_bytes(previous.read_bytes())

        self.resources = {
            "ok": True, "active_agent_profiles": [], "active_agent_tabs": 0,
            "max_agent_profiles": 3, "max_agent_tabs": 6,
        }
        self.addCleanup(setattr, leases, "_get_bridge_resources_json", leases._get_bridge_resources_json)
        leases._get_bridge_resources_json = lambda: self.resources

    def test_parallel_managers_and_generation_fencing(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            profiles = [f"Profile {n}" for n in (14, 14, 18, 21)]
            tokens = list(executor.map(leases.acquire_flow_lock, "abcd", profiles))
        self.assertEqual(sum(token is not None for token in tokens), 3)
        self.assertIsNone(leases.acquire_flow_lock("new-owner", "Profile 16"))
        owner, profile, token = next((a, p, t) for a, p, t in zip("abcd", profiles, tokens) if t)
        self.assertFalse(leases.release_flow_lock("another-owner", profile, token))
        self.assertFalse(leases.release_flow_lock(owner, profile, "stale-token"))
        self.assertTrue(leases.renew_flow_lock(owner, profile, token))
        self.assertTrue(leases.release_flow_lock(owner, profile, token))
        next_token = leases.acquire_flow_lock(owner, profile)
        self.assertNotEqual(next_token, token)
        self.assertFalse(leases.release_flow_lock(owner, profile, token))

    def test_live_legacy_lock_blocks_until_expiration(self):
        leases.FLOW_STATE_FILE.write_text(json.dumps({"flow_global": {
            "agent_id": "owner", "token": "legacy", "expires_at": time.time() + 60,
        }}), encoding="utf-8")
        self.assertIsNone(leases.acquire_flow_lock("owner", "Profile 14"))
        state = json.loads(leases.FLOW_STATE_FILE.read_text(encoding="utf-8"))
        state["flow_global"]["expires_at"] = time.time() - 1
        leases.FLOW_STATE_FILE.write_text(json.dumps(state), encoding="utf-8")
        token = leases.acquire_flow_lock("owner", "Profile 14")
        self.assertTrue(token)
        self.assertFalse(leases.renew_flow_lock("owner", "Profile 14", "legacy"))
        self.assertFalse(leases.release_flow_lock("owner", "Profile 14", "legacy"))
        self.assertNotIn("flow_global", json.loads(leases.FLOW_STATE_FILE.read_text(encoding="utf-8")))

    def test_shared_profile_and_tab_capacity_denials(self):
        self.resources["active_agent_profiles"] = ["Profile 1", "Profile 2", "Profile 3"]
        self.assertIsNone(leases.acquire_flow_lock("owner", "Profile 14"))
        self.resources["active_agent_profiles"] = ["Profile 1", "Profile 14"]
        self.resources["active_agent_tabs"] = 5
        self.assertTrue(leases.acquire_flow_lock("owner", "Profile 14"))
        self.assertIsNone(leases.acquire_flow_lock("owner", "Profile 18"))
        self.resources["active_agent_tabs"] = 4
        self.resources["pending_tabs"] = 1
        self.assertIsNone(leases.acquire_flow_lock("owner", "Profile 18"))

    def test_video_cooldown_is_per_profile_and_daily_last(self):
        registry = json.loads(leases.FLOW_REGISTRY_FILE.read_text(encoding="utf-8"))
        registry["profiles"]["Profile 21"]["enabled"] = False
        registry["profiles"]["Profile 13"] = {"enabled": True, "role": "family_member", "priority": 0}
        leases.FLOW_REGISTRY_FILE.write_text(json.dumps(registry), encoding="utf-8")
        profiles = [SimpleNamespace(dir_name=f"Profile {number}", is_daily_driver=number in (7, 8, 9, 16),
                                    has_bridge_extension=True, cooldown_until=0)
                    for number in (8, 7, 21, 13, 14, 18, 16, 9)]
        manager = leases.profile_manager
        previous = manager.get_ai_premium_profiles
        self.addCleanup(setattr, manager, "get_ai_premium_profiles", previous)
        manager.get_ai_premium_profiles = lambda: profiles

        self.assertEqual(leases.pick_flow_profile("video"), "Profile 14")
        self.assertEqual(leases.pick_flow_profile("image", open_profiles={"Profile 18", "Profile 16"}), "Profile 18")
        leases.mark_flow_video_depleted("Profile 14")
        self.assertEqual(leases.pick_flow_profile("video"), "Profile 18")
        self.assertEqual(leases.pick_flow_profile("image", open_profiles=set()), "Profile 14")
        leases.mark_flow_video_depleted("Profile 18")
        for number in (16, 8):
            expected = f"Profile {number}"
            self.assertEqual(leases.pick_flow_profile("video"), expected)
            leases.mark_flow_video_depleted(expected)
        self.assertIsNone(leases.pick_flow_profile("video"))
        for number in (7, 9, 13, 21):
            self.assertIsNone(leases.acquire_flow_lock("owner", f"Profile {number}"))


if __name__ == "__main__":
    unittest.main()
