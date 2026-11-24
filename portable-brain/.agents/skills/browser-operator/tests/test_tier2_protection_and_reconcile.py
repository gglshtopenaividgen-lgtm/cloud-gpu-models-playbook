import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "argon_bridge"))
import server


class ReconcileOwnershipTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        resources = mock.patch.object(server, "RESOURCES_FILE", Path(directory.name) / "resources.json")
        clients = mock.patch.object(server, "CONNECTED_CLIENTS", {})
        self.lease_data = {}
        leases = mock.patch.object(server.profile_lock_manager, "clean_expired_locks", return_value=self.lease_data)
        for fixture in (resources, clients, leases):
            fixture.start()
            self.addCleanup(fixture.stop)

    async def test_disconnected_stale_ownership_frees_capacity_only_after_grace(self):
        now = time.time()
        self.lease_data["Profile 13::aistudio"] = {"profile": "Profile 13"}
        server._save_resources({
            "owned_tabs": {
                "Profile 21": {"21": {"created_at": now - 60, "last_seen": now - 16}},
                "Profile 13": {"13": {"created_at": now - 60}},
            },
            "launched_by_agent": {
                "Profile 21": {"launched_at": now - 20},
                "Profile 16": {"launched_at": now},
            },
        })
        self.assertEqual(server.get_resources_snapshot()["active_agent_profiles_count"], 3)
        result = await server.reconcile_agent_tabs()
        self.assertEqual(result["active_agent_profiles"], ["Profile 13", "Profile 16"])
        self.assertIn("13", result["owned_tabs"]["Profile 13"])
        result = await server.reconcile_agent_tabs(disconnected_grace_sec=0)
        self.assertEqual(result["active_agent_profiles"], ["Profile 13"])

    async def test_zero_tab_inventory_clears_old_tabs_and_launch_record_if_unleased(self):
        profile = "Profile 14"
        server.CONNECTED_CLIENTS["client"] = {
            "ws": SimpleNamespace(closed=False), "dir_name": profile, "connected_at": time.time(),
        }
        server.register_agent_launched_profile(profile)
        server.register_agent_tab(profile, 14)
        self.lease_data[f"{profile}::gemini_web"] = {"profile": profile}
        with mock.patch.object(server, "send_extension_command", return_value={"ok": True, "tabs": []}):
            self.assertEqual((await server.reconcile_agent_tabs())["active_agent_tabs"], 1)
            self.lease_data.clear()
            result = await server.reconcile_agent_tabs()
        self.assertEqual(result["active_agent_profiles"], [])
        self.assertEqual(result["owned_tabs"], {})
        self.assertEqual(result["launched_by_agent"], {})
