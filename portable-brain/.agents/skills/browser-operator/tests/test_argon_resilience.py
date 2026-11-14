#!/usr/bin/env python3
"""
Unit Tests for Browser Operator & Argon Bridge:
- ProfileLockManager (Strict Priority Hierarchy, Dynamic Leasing, Expiry Cleaning)
- Shared Fleet Observability & Zero-Mock Invariant
"""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

# Add argon_bridge directory to path
ARGON_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "argon_bridge"
sys.path.insert(0, str(ARGON_BRIDGE_DIR))

import profile_lock_manager as plm


class TestProfileLockManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_locks_file = Path(self.temp_dir.name) / "test_locks.json"
        self.test_sessions_file = Path(self.temp_dir.name) / "test_sessions.json"
        
        # Save original file references
        self.orig_locks_file = plm.LOCKS_FILE
        self.orig_sessions_file = plm.SESSIONS_FILE
        
        # Point to temp fixtures
        plm.LOCKS_FILE = self.test_locks_file
        plm.SESSIONS_FILE = self.test_sessions_file

    def tearDown(self):
        # Restore originals
        plm.LOCKS_FILE = self.orig_locks_file
        plm.SESSIONS_FILE = self.orig_sessions_file
        self.temp_dir.cleanup()

    def test_priority_order_definition(self):
        """Verifies strict priority hierarchy: Profile 14 (Profile-User1) > Profile 13 (Profile-User2) > failsafes."""
        self.assertEqual(plm.PRIMARY_Profile-User_1, "Profile 14")
        self.assertEqual(plm.PRIMARY_Profile-User_2, "Profile 13")
        self.assertEqual(plm.FLEET_ORDER[0], "Profile 14")
        self.assertEqual(plm.FLEET_ORDER[1], "Profile 13")
        for failsafe in ["Profile 7", "Profile 9", "Profile 16", "Profile 8"]:
            self.assertIn(failsafe, plm.FAILSAFE_ORDER)

    def test_clean_expired_locks(self):
        """Ensures stale locks older than now are purged while active ones remain."""
        now = time.time()
        initial_data = {
            "Profile 14": {
                "agent_id": "stale_agent",
                "expires_at": now - 50.0,
                "task": "expired_task"
            },
            "Profile 13": {
                "agent_id": "active_agent",
                "expires_at": now + 200.0,
                "task": "active_task"
            }
        }
        plm._write_locks(initial_data)

        active = plm.clean_expired_locks()
        self.assertNotIn("Profile 14", active)
        self.assertIn("Profile 13", active)
        self.assertEqual(active["Profile 13"]["agent_id"], "active_agent")

    def test_release_profile_lease(self):
        """Verifies releasing lease by agent removes lock cleanly."""
        now = time.time()
        initial_data = {
            "Profile 13": {
                "agent_id": "agent_alpha",
                "expires_at": now + 100.0,
                "task": "thinking"
            }
        }
        plm._write_locks(initial_data)

        # Releasing by non-holder should fail to remove
        plm.release_profile_lease("Profile 13", agent_id="wrong_agent")
        self.assertIn("Profile 13", plm._read_locks())

        # Releasing by correct holder removes lock
        plm.release_profile_lease("Profile 13", agent_id="agent_alpha")
        self.assertNotIn("Profile 13", plm._read_locks())


if __name__ == "__main__":
    unittest.main()
