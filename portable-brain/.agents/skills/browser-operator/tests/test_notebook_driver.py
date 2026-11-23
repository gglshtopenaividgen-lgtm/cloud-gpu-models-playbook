#!/usr/bin/env python3
"""Offline unit tests for argon_bridge/notebook_driver.py."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

ARGON_BRIDGE_DIR = Path(__file__).resolve().parent.parent / "argon_bridge"
sys.path.insert(0, str(ARGON_BRIDGE_DIR))

import notebook_driver as nd  # noqa: E402


class FakeBridgeHarness:
    """In-memory Argon Bridge /command simulator for offline notebook driver tests."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.tab_seq = 100
        self.tab_urls: Dict[int, str] = {}
        self.tab_profiles: Dict[int, str] = {}
        self.dom_source_counts: Dict[str, int] = {}
        self.clone_url = "https://gemini.google.com/notebook/clone-uuid-9999"
        self.share_url = "https://gemini.google.com/notebook/owner-uuid-1111?usp=sharing"
        self.simulate_quota_exhausted = False
        self.uploaded_files: List[str] = []
        self.deleted_urls: List[tuple[str, str]] = []

    def post_fn(self, url: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
        assert url == nd.COMMAND_URL
        action = payload["action"]
        params = payload.get("params", {})
        profile = payload.get("profile") or "Profile 14"
        self.calls.append({"url": url, "action": action, "params": params, "profile": profile})

        if action == "OPEN_TAB":
            self.tab_seq += 1
            tid = self.tab_seq
            opened_url = params["url"]
            if opened_url == nd.CREATE_NOTEBOOK_URL:
                opened_url = "https://gemini.google.com/notebook/owner-uuid-1111"
            self.tab_urls[tid] = opened_url
            self.tab_profiles[tid] = profile
            return {"ok": True, "tabId": tid, "url": opened_url}

        if action == "LIST_TABS":
            tabs = [
                {"id": tid, "url": u, "title": "Notebook"}
                for tid, u in self.tab_urls.items()
                if self.tab_profiles.get(tid) == profile
            ]
            return {"ok": True, "tabs": tabs}

        if action == "CLOSE_TAB":
            tid = int(params["tabId"])
            self.tab_urls.pop(tid, None)
            self.tab_profiles.pop(tid, None)
            return {"ok": True}

        if action == "CDP_COMMAND":
            method = params["method"]
            cparams = params.get("params", {})
            if method == "DOM.enable":
                return {"ok": True, "result": {}}
            if method == "DOM.getDocument":
                return {"ok": True, "result": {"root": {"nodeId": 1}}}
            if method == "DOM.querySelector":
                return {"ok": True, "result": {"nodeId": 42}}
            if method == "DOM.setFileInputFiles":
                self.uploaded_files = list(cparams.get("files", []))
                tid = int(params["tabId"])
                cur_url = self.tab_urls.get(tid, "")
                self.dom_source_counts[cur_url] = len(self.uploaded_files)
                return {"ok": True, "result": {}}
            return {"ok": True, "result": {}}

        if action == "EVAL_DOM":
            tid = int(params["tabId"])
            code = params["code"]
            cur_url = self.tab_urls.get(tid, "")

            if "sourceCount" in code and "window.location.href" in code:
                return {
                    "ok": True,
                    "result": {
                        "href": cur_url,
                        "title": "Test Notebook",
                        "sourceCount": self.dom_source_counts.get(cur_url, 0),
                    },
                }
            if 'aria-label="Add sources"' in code:
                return {"ok": True, "result": {"clicked": True, "selector": 'GEM-SOURCE-LIST-CHIP[aria-label="Add sources"]'}}
            if "clickedUploadOption" in code:
                return {"ok": True, "result": {"ready": True, "hasInput": True}}
            if "Discover web sources" in code or "discoverBtn" in code:
                return {"ok": True, "result": {"ok": True, "submitted": True}}
            if "imported:" in code or "add selected" in code:
                self.dom_source_counts[cur_url] = self.dom_source_counts.get(cur_url, 0) + 2
                return {"ok": True, "result": {"imported": True}}
            if "4 neon" in code and "switched" in code:
                return {"ok": True, "result": {"ok": True, "model": "4 Neon", "thinking": "High", "switched": True}}
            if "Send button missing" in code:
                return {"ok": True, "result": {"ok": True, "sent": True}}
            if "quota_exhausted" in code:
                if self.simulate_quota_exhausted:
                    return {"ok": True, "result": {"quota_exhausted": True, "text": "", "citations": []}}
                return {
                    "ok": True,
                    "result": {
                        "quota_exhausted": False,
                        "text": "Architecture uses Argon Bridge with 2-layer redaction.",
                        "citations": [{"label": "bundle_01_context.md", "href": "https://gemini.google.com/cite/1"}],
                    },
                }
            if "Anyone with" in code or "allow copy" in code:
                return {"ok": True, "result": {"ok": True, "share_url": self.share_url}}
            if "copy notebook" in code:
                self.tab_urls[tid] = self.clone_url
                return {"ok": True, "result": {"ok": True, "clicked": True}}
            if "project-delete-button" in code:
                self.deleted_urls.append((profile, cur_url))
                return {"ok": True, "result": {"ok": True, "deleted": True}}
            return {"ok": True, "result": {"updated": True}}

        return {"ok": False, "error": f"Unknown action {action}"}


class TestPackAndRedaction(unittest.TestCase):
    def test_pack_max_12_bundles_exclusions_and_2_layer_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            proj = Path(tmp)
            # Secret env files (must NEVER be packed, values len >= 8 must be scrubbed)
            (proj / ".env").write_text(
                "CUSTOM_TOKEN=supersecretvalue999\nSHORT_PIN=1234\n",
                encoding="utf-8",
            )
            (proj / ".env.local").write_text(
                'EXPORTED_KEY="another_env_secret_xyz"\n',
                encoding="utf-8",
            )

            # Context files
            (proj / "mistakes.md").write_text(
                "Never leak supersecretvalue999 or sk-proj-AbCdEfGhIjKlMnOpQrSt.\n",
                encoding="utf-8",
            )
            (proj / "ideas.md").write_text(
                "Google key AIzaSyDummyKeyValue1234567890ABCD and Bearer tok_1234567890.\n",
                encoding="utf-8",
            )
            (proj / "constraints.md").write_text(
                'password = "my_plaintext_password" and api_key: "another_env_secret_xyz"\n',
                encoding="utf-8",
            )

            # Ignored dirs & binaries
            (proj / ".git").mkdir()
            (proj / ".git" / "config").write_text("git-secret", encoding="utf-8")
            (proj / "node_modules" / "pkg").mkdir(parents=True)
            (proj / "node_modules" / "pkg" / "index.js").write_text("console.log(1);", encoding="utf-8")
            (proj / ".venv").mkdir()
            (proj / ".venv" / "pyvenv.cfg").write_text("home = /usr", encoding="utf-8")
            (proj / "__pycache__").mkdir()
            (proj / "__pycache__" / "mod.pyc").write_bytes(b"\x00\x01\x02")
            (proj / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00")

            # 24 source files -> must pack into <= 12 bundles total
            src = proj / "src"
            src.mkdir()
            for i in range(24):
                (src / f"mod_{i:02d}.py").write_text(
                    f"def fn_{i}():\n    token = 'supersecretvalue999'\n    return {i}\n",
                    encoding="utf-8",
                )

            res = nd.pack_project(proj, max_bundles=12)
            self.assertTrue(res["ok"])
            self.assertLessEqual(res["bundle_count"], 12)
            self.assertGreaterEqual(res["remaining_slots"], 288)
            self.assertEqual(res["files_packed"], 27)  # 3 context + 24 src
            self.assertGreater(res["redactions"], 0)

            out_dir = proj / "temp_read" / "nb_bundles"
            bundle_files = sorted(out_dir.glob("bundle_*.md"))
            self.assertEqual(len(bundle_files), res["bundle_count"])

            combined = "\n".join(bf.read_text(encoding="utf-8") for bf in bundle_files)
            # Layer 2 exact literal scrubbing
            self.assertNotIn("supersecretvalue999", combined)
            self.assertNotIn("another_env_secret_xyz", combined)
            # Layer 1 regex scrubbing
            self.assertNotIn("sk-proj-AbCdEfGhIjKlMnOpQrSt", combined)
            self.assertNotIn("AIzaSyDummyKeyValue1234567890ABCD", combined)
            self.assertNotIn("tok_1234567890", combined)
            self.assertNotIn("my_plaintext_password", combined)
            # Exclusions
            self.assertNotIn("CUSTOM_TOKEN=", combined)
            self.assertNotIn("node_modules", combined)
            self.assertNotIn("pyvenv.cfg", combined)
            self.assertNotIn("git-secret", combined)
            self.assertNotIn("logo.png", combined)
            # Included context
            self.assertIn("mistakes.md", combined)
            self.assertIn("ideas.md", combined)
            self.assertIn("constraints.md", combined)


class TestNotebookDriverLifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.proj = Path(self.tmp.name)
        (self.proj / "ideas.md").write_text("# Ideas\nUse NotebookLM RAG.\n", encoding="utf-8")
        self.harness = FakeBridgeHarness()
        self.leases: List[tuple[str, str, str]] = []
        self.releases: List[tuple[str, str]] = []
        self.cooldowns: List[tuple[str, str, int, str]] = []

        def fake_acquire(**kwargs):
            prof = kwargs.get("preferred_profile") or "Profile 14"
            self.leases.append((prof, kwargs.get("surface", ""), kwargs.get("bucket", "")))
            return prof, None

        def fake_release(profile, agent_id=None, surface=None):
            self.releases.append((profile, surface or ""))
            return True

        def fake_cooldown(profile, bucket, cooldown_seconds=1800, reason=""):
            self.cooldowns.append((profile, bucket, cooldown_seconds, reason))

        self.driver = nd.NotebookDriver(
            bridge=nd.BridgeClient(post_fn=self.harness.post_fn),
            lease_acquire_fn=fake_acquire,
            lease_release_fn=fake_release,
            cooldown_fn=fake_cooldown,
            popup_dismiss_fn=lambda **kwargs: {"ok": True, "blocked": False, "dismissed_count": 0},
            liveness_check_fn=lambda eval_fn: {"active": False, "reasons": []},
            sleep_fn=lambda _s: None,
            agent_id="test_agent",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_add_sources_discover_query_share_clone_and_cleanup(self):
        # 1. Pack & Create
        pack_res = nd.pack_project(self.proj)
        self.assertEqual(pack_res["bundle_count"], 1)

        created = self.driver.create(title="Test RAG", project_path=self.proj, profile="Profile 14")
        nb = created["notebook"]
        self.assertEqual(nb["notebook_id"], "owner-uuid-1111")
        self.assertEqual(nb["owner_profile"], "Profile 14")
        self.assertEqual(nb["status"], "ACTIVE")
        self.assertEqual(nb["source_count"], 0)
        self.assertEqual(nb["clones"], [])
        self.assertIn(("Profile 14", "notebook", "notebooklm"), self.leases)
        self.assertIn(("Profile 14", "notebook"), self.releases)

        # 2. Add Sources via CDP DOM.setFileInputFiles
        add_res = self.driver.add_sources(
            notebook_id_or_url="owner-uuid-1111",
            bundles_dir=self.proj / "temp_read" / "nb_bundles",
            project_path=self.proj,
        )
        self.assertEqual(add_res["source_count"], 1)
        self.assertEqual(len(self.harness.uploaded_files), 1)
        ledger = nd.load_ledger(nd.get_ledger_path(self.proj))
        self.assertEqual(ledger["notebooks"]["owner-uuid-1111"]["source_count"], 1)

        # 3. Discover Web Sources
        disc_res = self.driver.discover_web("owner-uuid-1111", "Gemini Notebooks API", self.proj)
        self.assertTrue(disc_res["imported"])
        self.assertEqual(disc_res["source_count"], 3)

        # 4. Query with 4 Neon High + Citations
        out_md = self.proj / "temp_read" / "ans.md"
        q_res = self.driver.query("owner-uuid-1111", "Summarize RAG", self.proj, out_file=out_md)
        self.assertEqual(q_res["model"], "4 Neon (High)")
        self.assertTrue(out_md.exists())
        self.assertIn("Citations", out_md.read_text(encoding="utf-8"))

        # 5. Share-Clone with exact source count match
        self.harness.dom_source_counts[self.harness.clone_url] = 3
        clone_res = self.driver.share_clone("owner-uuid-1111", target_profile="Profile 13", project_path=self.proj)
        self.assertEqual(clone_res["clone"]["notebook_id"], "clone-uuid-9999")
        self.assertEqual(clone_res["verified_source_count"], 3)

        ledger = nd.load_ledger(nd.get_ledger_path(self.proj))
        clones = ledger["notebooks"]["owner-uuid-1111"]["clones"]
        self.assertEqual(len(clones), 1)
        self.assertEqual(clones[0]["profile"], "Profile 13")

        # 6. Cleanup across owner + clone via CLI --cleanup-notebooks
        rc = nd.main(["--cleanup-notebooks", "--project", str(self.proj)], driver=self.driver)
        self.assertEqual(rc, 0)
        self.assertIn(("Profile 13", self.harness.clone_url), self.harness.deleted_urls)
        self.assertIn(("Profile 14", "https://gemini.google.com/notebook/owner-uuid-1111"), self.harness.deleted_urls)

        ledger_after = nd.load_ledger(nd.get_ledger_path(self.proj))
        owner_after = ledger_after["notebooks"]["owner-uuid-1111"]
        self.assertEqual(owner_after["status"], "DELETED")
        self.assertEqual(owner_after["clones"][0]["status"], "DELETED")

    def test_share_clone_source_count_mismatch_detection(self):
        self.driver.create(title="Mismatch Test", project_path=self.proj, profile="Profile 14")
        ledger_path = nd.get_ledger_path(self.proj)
        ledger = nd.load_ledger(ledger_path)
        ledger["notebooks"]["owner-uuid-1111"]["source_count"] = 5
        nd.save_ledger(ledger_path, ledger)

        self.harness.dom_source_counts["https://gemini.google.com/notebook/owner-uuid-1111"] = 5
        self.harness.dom_source_counts[self.harness.clone_url] = 2  # Mismatch!

        with self.assertRaises(nd.SourceCountMismatchError) as ctx:
            self.driver.share_clone("owner-uuid-1111", target_profile="Profile 13", project_path=self.proj)
        self.assertIn("owner=5, clone=2", str(ctx.exception))

        # Ledger must NOT record an unverified mismatched clone
        ledger_after = nd.load_ledger(ledger_path)
        self.assertEqual(ledger_after["notebooks"]["owner-uuid-1111"]["clones"], [])

    def test_query_quota_exhaustion_triggers_cooldown_and_failover_guidance(self):
        self.driver.create(title="Quota Test", project_path=self.proj, profile="Profile 14")
        self.harness.simulate_quota_exhausted = True

        with self.assertRaises(nd.QuotaExhaustedError) as ctx:
            self.driver.query("owner-uuid-1111", "Any prompt", self.proj)

        self.assertIn("share-clone", str(ctx.exception))
        self.assertEqual(self.cooldowns[0][0], "Profile 14")
        self.assertEqual(self.cooldowns[0][1], "notebooklm")


if __name__ == "__main__":
    unittest.main()
