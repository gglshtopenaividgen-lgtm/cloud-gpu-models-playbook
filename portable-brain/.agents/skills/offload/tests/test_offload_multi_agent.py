import concurrent.futures
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MANAGER = ROOT / ".agents/skills/offload/scripts/offload_manager.py"

_spec = importlib.util.spec_from_file_location("offload_manager_v3", MANAGER)
om = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(om)


def _run_cli(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(MANAGER), *args, "--project", str(root)]
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=20)


class OffloadV3MultiAgentTests(unittest.TestCase):
    def test_auto_id_concurrent_joins_and_stale_reuse(self):
        """3 concurrent worker joins + main-1 + collab-1 get unique IDs without clobbering heartbeats."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _run_cli(root, "init")

            def _join(role: str, host: str):
                res = _run_cli(root, "join", "--role", role, "--host", host, "--json")
                return json.loads(res.stdout)

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                futs = [
                    pool.submit(_join, "worker", "cli"),
                    pool.submit(_join, "worker", "cli"),
                    pool.submit(_join, "worker", "cli"),
                    pool.submit(_join, "main", "antigravity"),
                    pool.submit(_join, "collaborator", "codex"),
                ]
                results = [f.result() for f in futs]

            worker_ids = sorted(r["agent_id"] for r in results if r["role"] == "worker")
            main_ids = [r["agent_id"] for r in results if r["role"] == "main"]
            collab_ids = [r["agent_id"] for r in results if r["role"] == "collaborator"]

            self.assertEqual(worker_ids, ["worker-1", "worker-2", "worker-3"])
            self.assertEqual(main_ids, ["main-1"])
            self.assertEqual(collab_ids, ["collab-1"])

            status = json.loads((root / "offload/status.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(status["agents"].keys()),
                {"worker-1", "worker-2", "worker-3", "main-1", "collab-1"},
            )
            for aid in ("worker-1", "worker-2", "worker-3", "main-1", "collab-1"):
                self.assertEqual(status["agents"][aid]["state"], "ONLINE")

            # Leave worker-2 -> next worker join reuses lowest offline slot (worker-2)
            _run_cli(root, "leave", "--agent-id", "worker-2")
            status_after_leave = json.loads((root / "offload/status.json").read_text(encoding="utf-8"))
            self.assertEqual(status_after_leave["agents"]["worker-2"]["state"], "OFFLINE")
            self.assertIsNone(status_after_leave["agents"]["worker-2"]["pid"])

            reused = _join("worker", "cli")
            self.assertEqual(reused["agent_id"], "worker-2")

            # Stale listening worker (>45s) slot reuse via allocate_agent_id
            stale_status = {
                "agents": {
                    "worker-1": {
                        "agent_id": "worker-1",
                        "role": "worker",
                        "pid": 99991,
                        "state": "ONLINE_LISTENING",
                        "last_seen_epoch": time.time() - 60.0,
                    },
                    "worker-2": {
                        "agent_id": "worker-2",
                        "role": "worker",
                        "pid": 99992,
                        "state": "ONLINE_LISTENING",
                        "last_seen_epoch": time.time() - 5.0,
                    },
                }
            }
            self.assertEqual(om.allocate_agent_id(stale_status, "worker", pid=77777), "worker-1")

    def test_targeted_dispatch_routing_and_skipping(self):
        """worker-1 skips worker-2 & role:collaborator tasks and claims `any`; worker-2 & collab-1 claim theirs."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            p1 = root / "p1.md"
            p1.write_text("Task for worker-2 only", encoding="utf-8")
            p2 = root / "p2.md"
            p2.write_text("Task for collaborator role", encoding="utf-8")
            p3 = root / "p3.md"
            p3.write_text("Task for any worker", encoding="utf-8")

            _run_cli(root, "dispatch", "--title", "ForW2", "--prompt-file", str(p1), "--from", "main-1", "--to", "worker-2")
            time.sleep(0.05)
            _run_cli(root, "dispatch", "--title", "ForCollab", "--prompt-file", str(p2), "--from", "main-1", "--to", "role:collaborator")
            time.sleep(0.05)
            _run_cli(root, "dispatch", "--title", "ForAny", "--prompt-file", str(p3), "--from", "main-1", "--to", "any")

            # worker-1 runs worker-listen --once -> must skip ForW2 and ForCollab, claim ForAny!
            r_w1 = _run_cli(root, "worker-listen", "--role", "worker", "--agent-id", "worker-1", "--once")
            self.assertIn("[WorkerListen] Joined as worker-1 (role=worker)", r_w1.stdout)
            w1_dossier = r_w1.stdout.split("# OFFLOAD TASK DOSSIER:")[-1]
            self.assertIn("**Title**: ForAny", w1_dossier)
            self.assertNotIn("ForW2", w1_dossier)

            # worker-2 runs worker-listen --once -> claims ForW2
            r_w2 = _run_cli(root, "worker-listen", "--role", "worker", "--agent-id", "worker-2", "--once")
            self.assertIn("**Title**: ForW2", r_w2.stdout.split("# OFFLOAD TASK DOSSIER:")[-1])

            # collab-1 runs worker-listen --once -> claims ForCollab
            r_c1 = _run_cli(root, "worker-listen", "--role", "collaborator", "--agent-id", "collab-1", "--once")
            self.assertIn("[WorkerListen] Joined as collab-1 (role=collaborator)", r_c1.stdout)
            self.assertIn("**Title**: ForCollab", r_c1.stdout.split("# OFFLOAD TASK DOSSIER:")[-1])

            tasks = [json.loads(p.read_text(encoding="utf-8")) for p in (root / "offload/tasks").glob("TASK-*.json")]
            by_title = {t["title"]: t for t in tasks}
            self.assertEqual(by_title["ForAny"]["claimed_by"], "worker-1")
            self.assertEqual(by_title["ForW2"]["claimed_by"], "worker-2")
            self.assertEqual(by_title["ForCollab"]["claimed_by"], "collab-1")
            self.assertEqual(by_title["ForW2"]["from_agent"], "main-1")
            self.assertEqual(by_title["ForW2"]["target_agent"], "worker-2")

    def test_concurrent_atomic_claiming_across_workers(self):
        """3 concurrent worker-listen processes racing for 1 pending task result in exactly 1 claim."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pf = root / "race.md"
            pf.write_text("Race task", encoding="utf-8")
            _run_cli(root, "dispatch", "--title", "RaceTask", "--prompt-file", str(pf), "--to", "any")

            procs = [
                subprocess.Popen(
                    [sys.executable, str(MANAGER), "worker-listen", "--project", str(root), "--role", "worker", "--once"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(3)
            ]
            outputs = [p.communicate(timeout=20)[0] for p in procs]
            claimed_count = sum(1 for out in outputs if "[TASK_CLAIMED:" in out)
            self.assertEqual(claimed_count, 1, outputs)

    def test_peer_post_and_inbox_filtering(self):
        """post/inbox filter accurately by all, exact agent_id, and role:<role>."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _run_cli(root, "join", "--role", "main", "--agent-id", "main-1")
            _run_cli(root, "join", "--role", "collaborator", "--agent-id", "collab-1", "--host", "codex")
            _run_cli(root, "join", "--role", "worker", "--agent-id", "worker-1", "--host", "cli")
            _run_cli(root, "join", "--role", "worker", "--agent-id", "worker-2", "--host", "cli")

            _run_cli(root, "post", "--from", "main-1", "--to", "all", "--message", "Broadcast update")
            _run_cli(root, "post", "--from", "collab-1", "--to", "worker-2", "--message", "Only for W2", "--file", "src/a.py")
            _run_cli(root, "post", "--from", "main-1", "--to", "role:collaborator", "--message", "Collab review needed")
            _run_cli(root, "post", "--from", "main-1", "--to", "role:worker", "--message", "Workers sync")

            w1_msgs = json.loads(_run_cli(root, "inbox", "--for", "worker-1", "--json").stdout)
            w2_msgs = json.loads(_run_cli(root, "inbox", "--for", "worker-2", "--json").stdout)
            c1_msgs = json.loads(_run_cli(root, "inbox", "--for", "collab-1", "--json").stdout)

            self.assertEqual([m["message"] for m in w1_msgs], ["Broadcast update", "Workers sync"])
            self.assertEqual([m["message"] for m in w2_msgs], ["Broadcast update", "Only for W2", "Workers sync"])
            self.assertEqual(Path(w2_msgs[1]["file"]).as_posix(), "src/a.py")
            self.assertEqual([m["message"] for m in c1_msgs], ["Broadcast update", "Collab review needed"])

            board_md = (root / "offload/BOARD.md").read_text(encoding="utf-8")
            self.assertIn("Recent Peer Messages", board_md)
            self.assertIn("Only for W2", board_md)

    def test_worker_complete_preserves_other_live_workers(self):
        """Completing worker-1's task does not clobber worker-2's live ONLINE_LISTENING state."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pf = root / "task.md"
            pf.write_text("Complete me", encoding="utf-8")
            _run_cli(root, "dispatch", "--title", "KeepPeersAlive", "--prompt-file", str(pf), "--to", "worker-1")

            # Claim task as worker-1
            task_json, = (root / "offload/tasks").glob("TASK-*.json")
            tid = task_json.stem
            _run_cli(root, "worker-claim", "--task-id", tid, "--agent-id", "worker-1")
            claim_id = json.loads(task_json.read_text(encoding="utf-8"))["claim_id"]

            # Inject live worker-2 ONLINE_LISTENING in status.json
            status_path = root / "offload/status.json"
            st = json.loads(status_path.read_text(encoding="utf-8"))
            st["agents"]["worker-2"] = {
                "agent_id": "worker-2",
                "role": "worker",
                "host": "cli",
                "pid": 54321,
                "state": "ONLINE_LISTENING",
                "last_seen": om._now_iso(),
                "last_seen_epoch": time.time(),
                "current_tasks": [],
                "note": "worker-2 listening",
            }
            status_path.write_text(json.dumps(st, indent=2), encoding="utf-8")

            # Complete worker-1's task
            _run_cli(root, "worker-complete", "--task-id", tid, "--claim-id", claim_id, "--summary", "Done cleanly")

            st_after = json.loads(status_path.read_text(encoding="utf-8"))
            self.assertEqual(st_after["agents"]["worker-1"]["state"], "OFFLINE")
            self.assertIsNone(st_after["agents"]["worker-1"]["pid"])
            self.assertEqual(st_after["agents"]["worker-2"]["state"], "ONLINE_LISTENING")
            self.assertEqual(st_after["agents"]["worker-2"]["pid"], 54321)
            # Legacy mirror reflects live worker-2!
            self.assertEqual(st_after["worker"]["state"], "ONLINE_LISTENING")
            self.assertEqual(st_after["worker"]["pid"], 54321)

    def test_wsl_windows_path_normalization(self):
        """Windows C:\\... <-> WSL /mnt/c/... path normalization works cleanly in both directions."""
        self.assertEqual(
            str(om._to_host_path("./", target_os="nt")),
            r"./",
        )
        self.assertEqual(
            om._to_host_path(r"./", target_os="posix").as_posix(),
            "./",
        )
        self.assertEqual(
            om._to_wsl_path(r"./.agents\skills\offload\SKILL.md"),
            "./.agents/skills/offload/SKILL.md",
        )
        self.assertEqual(
            om._to_display_path("./"),
            r"./",
        )


if __name__ == "__main__":
    unittest.main()
