#!/usr/bin/env python3
"""Integration tests for `worktree_manager.py` using real temporary Git repos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import worktree_manager as wm  # noqa: E402


def _run_cli(args: list[str]) -> tuple[int, dict]:
    """Invoke `worktree_manager.py` via subprocess and parse JSON output."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "worktree_manager.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    raw = proc.stdout.strip() or proc.stderr.strip()
    payload = json.loads(raw) if raw else {}
    return proc.returncode, payload


class WorktreeManagerTest(unittest.TestCase):
    """End-to-end tests against a real temporary Git repository."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.tmp.name).resolve()
        self.repo_dir = self.base_dir / "my-proj"
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        self.git_exe = wm.resolve_git_exe()

        self._git(["init", "-b", "main"], cwd=self.repo_dir)
        self._git(["config", "user.name", "Test Agent"], cwd=self.repo_dir)
        self._git(["config", "user.email", "agent@example.com"], cwd=self.repo_dir)

        (self.repo_dir / "README.md").write_text("# My Project\n", encoding="utf-8")
        (self.repo_dir / ".gitignore").write_text(".env.local\nconfig/*.local.json\n", encoding="utf-8")
        self._git(["add", "README.md", ".gitignore"], cwd=self.repo_dir)
        self._git(["commit", "-m", "chore: initial commit"], cwd=self.repo_dir)

    def tearDown(self) -> None:
        # Unlink any stray junctions before temp cleanup so target dirs stay safe
        worktrees_dir = self.base_dir / ".worktrees"
        if worktrees_dir.exists():
            wm.unlink_ntfs_junctions(worktrees_dir)
        self.tmp.cleanup()

    def _git(self, args: list[str], cwd: Path) -> str:
        proc = subprocess.run(
            [self.git_exe, "-C", str(cwd), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return proc.stdout.strip()

    def test_create_external_sibling_and_worktreeinclude_hydration(self) -> None:
        # Create ignored local configs + an outside secret file that must NOT be copied
        outside_secret = self.base_dir / "secret_outside.txt"
        outside_secret.write_text("DO_NOT_COPY", encoding="utf-8")

        (self.repo_dir / ".env.local").write_text("API_KEY=local-only\n", encoding="utf-8")
        (self.repo_dir / "config").mkdir()
        (self.repo_dir / "config" / "dev.local.json").write_text('{"port": 3000}\n', encoding="utf-8")
        (self.repo_dir / ".worktreeinclude").write_text(
            "\n".join(
                [
                    "# Local config hydration",
                    ".env.local",
                    "config/*.local.json",
                    "../secret_outside.txt",
                    ".git/HEAD",
                    ".git/config",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        rc, data = _run_cli(
            [
                "create",
                "--repo",
                str(self.repo_dir),
                "--worker",
                "Worker Alpha!",
                "--task",
                "Fix Auth/Flow",
            ]
        )
        self.assertEqual(rc, 0, msg=data)
        self.assertTrue(data["ok"])
        self.assertEqual(data["branch"], "agent/worker-alpha/fix-auth-flow")

        wt_path = Path(data["worktree_path"]).resolve()
        expected_worker_root = (self.base_dir / ".worktrees" / "my-proj" / "worker-alpha").resolve()
        self.assertEqual(wt_path.parent, expected_worker_root)
        self.assertFalse(wt_path.is_relative_to(self.repo_dir))
        self.assertTrue((wt_path / ".env.local").is_file())
        self.assertTrue((wt_path / "config" / "dev.local.json").is_file())
        self.assertFalse((wt_path / "secret_outside.txt").exists())
        self.assertFalse((wt_path.parent / "secret_outside.txt").exists())
        self.assertEqual(
            set(data["hydrated_files"]),
            {".env.local", "config/dev.local.json"},
        )

        # Verify core.fileMode false and core.longpaths true on worktree
        self.assertEqual(self._git(["config", "--get", "core.fileMode"], wt_path), "false")
        self.assertEqual(self._git(["config", "--get", "core.longpaths"], wt_path), "true")

        # Verify list & status
        rc_list, list_data = _run_cli(["list", "--repo", str(self.repo_dir)])
        self.assertEqual(rc_list, 0)
        listed_paths = {Path(w["path"]).resolve() for w in list_data["worktrees"]}
        self.assertIn(wt_path, listed_paths)

        rc_status, status_data = _run_cli(["status", "--path", str(wt_path)])
        self.assertEqual(rc_status, 0)
        self.assertTrue(status_data["exists"])
        self.assertFalse(status_data["dirty"])
        self.assertEqual(status_data["branch"], "agent/worker-alpha/fix-auth-flow")

        # Reject --worktrees-root inside repo
        rc_bad, _ = _run_cli(
            [
                "create",
                "--repo",
                str(self.repo_dir),
                "--worker",
                "w2",
                "--task",
                "t2",
                "--worktrees-root",
                str(self.repo_dir / "inside"),
            ]
        )
        self.assertNotEqual(rc_bad, 0)

    @unittest.skipUnless(os.name == "nt", "Windows NTFS junction safety test requires Windows")
    def test_windows_ntfs_junction_safe_teardown(self) -> None:
        rc, data = _run_cli(
            [
                "create",
                "--repo",
                str(self.repo_dir),
                "--worker",
                "win-worker",
                "--task",
                "junction-test",
            ]
        )
        self.assertEqual(rc, 0, msg=data)
        wt_path = Path(data["worktree_path"]).resolve()

        # External shared target directory with sentinel file
        shared_target = self.base_dir / "shared_node_modules"
        shared_target.mkdir()
        sentinel = shared_target / "keep.txt"
        sentinel.write_text("MUST_SURVIVE_TEARDOWN", encoding="utf-8")

        junction_path = wt_path / "node_modules"
        mklink_proc = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(junction_path), str(shared_target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(mklink_proc.returncode, 0, msg=mklink_proc.stderr or mklink_proc.stdout)
        self.assertTrue((junction_path / "keep.txt").is_file())

        # Status should report the NTFS junction
        rc_st, st_data = _run_cli(["status", "--path", str(wt_path)])
        self.assertEqual(rc_st, 0)
        self.assertIn(os.path.abspath(junction_path), [os.path.abspath(p) for p in st_data["junctions"]])

        # Remove worktree cleanly without deleting shared target contents
        rc_rm, rm_data = _run_cli(
            [
                "remove",
                "--repo",
                str(self.repo_dir),
                "--worker",
                "win-worker",
                "--task",
                "junction-test",
            ]
        )
        self.assertEqual(rc_rm, 0, msg=rm_data)
        self.assertFalse(wt_path.exists())
        self.assertTrue(sentinel.is_file(), "Sentinel file in junction target must remain intact!")
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "MUST_SURVIVE_TEARDOWN")

        # Prune cleans empty directories under .worktrees
        rc_prune, prune_data = _run_cli(["prune", "--repo", str(self.repo_dir)])
        self.assertEqual(rc_prune, 0, msg=prune_data)
        self.assertFalse((self.base_dir / ".worktrees" / "my-proj").exists())

    def test_verify_and_ff_only_merge_with_rebase_and_cleanup(self) -> None:
        rc, data = _run_cli(
            [
                "create",
                "--repo",
                str(self.repo_dir),
                "--worker",
                "coder1",
                "--task",
                "feature-x",
            ]
        )
        self.assertEqual(rc, 0, msg=data)
        wt_path = Path(data["worktree_path"]).resolve()
        branch = data["branch"]

        # Independent commit on main to exercise rebase before ff-only merge
        (self.repo_dir / "main_only.txt").write_text("main advance\n", encoding="utf-8")
        self._git(["add", "main_only.txt"], cwd=self.repo_dir)
        self._git(["commit", "-m", "chore: advance main"], cwd=self.repo_dir)

        # Uncommitted change in worktree -> merge must refuse dirty worktree
        feature_file = wt_path / "feature.py"
        feature_file.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        rc_dirty, dirty_data = _run_cli(
            [
                "merge",
                "--repo",
                str(self.repo_dir),
                "--worker",
                "coder1",
                "--task",
                "feature-x",
                "--into",
                "main",
            ]
        )
        self.assertNotEqual(rc_dirty, 0)
        self.assertFalse(dirty_data["ok"])

        # Commit feature in worktree
        self._git(["add", "feature.py"], cwd=wt_path)
        self._git(["commit", "-m", "feat: add greet"], cwd=wt_path)

        # Verify command check (pass & fail)
        verify_cmd = f'"{sys.executable}" -B -c "import feature; assert feature.greet() == \'hello\'"'
        rc_v_ok, v_ok = _run_cli(["verify", "--path", str(wt_path), "--cmd", verify_cmd])
        self.assertEqual(rc_v_ok, 0, msg=v_ok)
        self.assertTrue(v_ok["passed"])

        rc_v_bad, v_bad = _run_cli(
            ["verify", "--path", str(wt_path), "--cmd", f'"{sys.executable}" -c "import sys; sys.exit(2)"']
        )
        self.assertEqual(rc_v_bad, 2)
        self.assertFalse(v_bad["passed"])

        # Merge with verification + automatic cleanup
        rc_merge, merge_data = _run_cli(
            [
                "merge",
                "--repo",
                str(self.repo_dir),
                "--worker",
                "coder1",
                "--task",
                "feature-x",
                "--into",
                "main",
                "--verify-cmd",
                verify_cmd,
            ]
        )
        self.assertEqual(rc_merge, 0, msg=merge_data)
        self.assertTrue(merge_data["ok"])
        self.assertFalse(wt_path.exists())
        self.assertTrue((self.repo_dir / "feature.py").is_file())
        self.assertTrue((self.repo_dir / "main_only.txt").is_file())

        # Branch should be deleted after clean merge
        branches = self._git(["branch", "--list", branch], cwd=self.repo_dir)
        self.assertEqual(branches, "")


if __name__ == "__main__":
    unittest.main()
