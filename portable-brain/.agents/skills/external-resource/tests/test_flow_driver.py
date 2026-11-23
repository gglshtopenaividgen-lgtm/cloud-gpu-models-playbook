#!/usr/bin/env python3
"""test_flow_driver.py - Unit test suite for flow_driver.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

TEST_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = TEST_DIR.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import flow_driver


class TestFlowDriver(unittest.TestCase):
    """Test suite for manifest parsing, dry-run simulation, and safety invariants."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_manifest_json(self):
        sample = [
            {"id": "hero_01", "prompt": "Pixel knight in armor", "style": "16-bit", "negative": "blurry"},
            {"id": "boss_01", "prompt": "Dark dragon with fiery eyes", "style": "dark fantasy", "negative": ""},
        ]
        parsed = flow_driver.parse_manifest(json.dumps(sample))
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "hero_01")
        self.assertEqual(parsed[1]["id"], "boss_01")

    def test_parse_manifest_delimited_pipe(self):
        sample = """
        # Comment line
        asset_01 | Magic sword glowing blue | fantasy RPG | low quality
        asset_02 | Wooden shield with iron rim | medieval | photorealistic
        """
        parsed = flow_driver.parse_manifest(sample)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "asset_01")
        self.assertEqual(parsed[0]["prompt"], "Magic sword glowing blue")
        self.assertEqual(parsed[0]["style"], "fantasy RPG")
        self.assertEqual(parsed[0]["negative"], "low quality")

    def test_parse_manifest_delimited_blocks(self):
        sample = """
        === ID: char_rogue ===
        prompt: Stealth assassin in shadow cloak
        style: cyberpunk
        negative: daylight, bright colors
        aspect: 1:1

        === ID: char_wizard ===
        prompt: Mystic archmage channeling lightning
        style: fantasy
        aspect: 3:4
        """
        parsed = flow_driver.parse_manifest(sample)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "char_rogue")
        self.assertEqual(parsed[0]["prompt"], "Stealth assassin in shadow cloak")
        self.assertEqual(parsed[0]["aspect"], "1:1")
        self.assertEqual(parsed[1]["id"], "char_wizard")

    def test_dry_run_execution(self):
        manifest_file = self.temp_path / "test_manifest.txt"
        manifest_file.write_text("item_01 | Golden chalice | fantasy | broken", encoding="utf-8")

        res = flow_driver.execute_flow_batch(
            manifest_path=manifest_file,
            preset="game",
            modality="image",
            concurrency=4,
            dry_run=True,
        )

        self.assertTrue(res.get("ok"))
        self.assertTrue(res.get("dry_run"))
        self.assertEqual(res.get("preset"), "game")
        self.assertEqual(res.get("items_count"), 1)
        self.assertIn("target_profile", res)

    def test_invalid_preset(self):
        manifest_file = self.temp_path / "test_manifest.txt"
        manifest_file.write_text("item_01 | Prompt", encoding="utf-8")

        res = flow_driver.execute_flow_batch(
            manifest_path=manifest_file,
            preset="non_existent_preset",
            dry_run=True,
        )
        self.assertFalse(res.get("ok"))
        self.assertIn("Invalid preset", res.get("error", ""))

    def test_missing_manifest(self):
        res = flow_driver.execute_flow_batch(
            manifest_path=self.temp_path / "does_not_exist.txt",
            preset="game",
            dry_run=True,
        )
        self.assertFalse(res.get("ok"))
        self.assertIn("Manifest file not found", res.get("error", ""))

    def test_run_status(self):
        with patch.object(flow_driver, "send_bridge_request") as mock_bridge:
            mock_bridge.return_value = {
                "ok": True,
                "active_agent_tabs": 1,
                "active_agent_profiles": ["Profile 13"],
            }
            res = flow_driver.run_status()
            self.assertTrue(res.get("ok"))
            self.assertEqual(res.get("version"), flow_driver.VERSION)
            self.assertIn("profiles", res)

    def test_cleanup_invariant_on_error(self):
        """Ensures tab is closed and lock released even when batch fails mid-execution."""
        manifest_file = self.temp_path / "test_manifest.txt"
        manifest_file.write_text("item_01 | Test prompt", encoding="utf-8")

        mock_lock_mgr = MagicMock()
        mock_lock_mgr.acquire_flow_lock.return_value = "token_abc123"

        with patch.object(flow_driver, "profile_lock_manager", mock_lock_mgr), \
             patch.object(flow_driver, "send_bridge_request") as mock_bridge, \
             patch.object(flow_driver, "post_message_to_runner") as mock_post:

            # 1. OPEN_TAB succeeds and returns tabId=999
            mock_bridge.side_effect = [
                {"ok": True, "tabId": 999},  # OPEN_TAB
                {"ok": True},                # CLOSE_TAB
            ]
            # 2. postMessage fails on ingest
            mock_post.return_value = {"ok": False, "error": "Simulated runner crash"}

            res = flow_driver.execute_flow_batch(
                manifest_path=manifest_file,
                preset="game",
                profile="Profile 13",
                dry_run=False,
            )

            self.assertFalse(res.get("ok"))
            self.assertIn("Manifest ingestion failed", res.get("error", ""))

            # Verify CLOSE_TAB was strictly called
            close_calls = [
                call for call in mock_bridge.call_args_list
                if call[0][0] == "/command" and call[1].get("payload", {}).get("action") == "CLOSE_TAB"
            ]
            self.assertEqual(len(close_calls), 1)
            self.assertEqual(close_calls[0][1]["payload"]["params"]["tabId"], 999)

            # Verify release_flow_lock was strictly called
            mock_lock_mgr.release_flow_lock.assert_called_once_with(
                agent_id="worker-2",
                profile="Profile 13",
                token="token_abc123",
            )


if __name__ == "__main__":
    unittest.main()
