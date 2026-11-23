"""Isolated Phase 2A fixtures for skill reconciliation and Git staging."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


BRAIN_ROOT = Path(__file__).resolve().parents[4]
SCRIPTS = BRAIN_ROOT / ".agents" / "skills" / "full-sync" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import full_sync
from skill_reconciler import SkillReconciler, SyncAction


def make_skill(root, folder, name=None, extra=""):
    skill = root / folder
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {name or folder}\ndescription: Fixture skill.\n{extra}---\n",
        encoding="utf-8",
    )
    return skill


def snapshot(root):
    return {
        path.relative_to(root): None if path.is_dir() else path.read_bytes()
        for path in root.rglob("*")
    }


class SkillSyncTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.brain = self.root / "brain"
        self.project = self.root / "project"
        self.live = self.project / ".agents" / "skills"
        self.universal = self.brain / ".agents" / "skills"
        self.archive = self.brain / "project_skills" / self.project.name

    def test_dry_run_cannot_write_or_invoke_catalog(self):
        target = make_skill(self.live, "local-skill", extra="target_universal_skill: offload\n")
        (target / "scripts").mkdir()
        (target / "scripts" / "example.py").write_text("pass\n", encoding="utf-8")
        make_skill(self.universal, "offload")
        worker = make_skill(self.universal, "auto-skill")
        (worker / "scripts").mkdir()
        (worker / "scripts" / "sync_catalog.py").touch()
        before = snapshot(self.root)
        reconciler = SkillReconciler(self.brain, dry_run=True)

        with (
            patch.object(reconciler, "trigger_catalog_sync") as trigger,
            patch("skill_reconciler.subprocess.run") as run,
        ):
            actions = reconciler.run_all(self.project)
            trigger.assert_not_called()
            run.assert_not_called()
        self.assertEqual(
            {action.action for action in actions},
            {SyncAction.BACKUP_TO_BRAIN, SyncAction.PROMOTE_UNIVERSAL_UPDATE},
        )
        with patch("skill_reconciler.subprocess.run") as run:
            self.assertTrue(reconciler.trigger_catalog_sync())
            run.assert_not_called()
        self.assertEqual(snapshot(self.root), before)

    def test_skips_universal_identity_before_backup_and_hydration(self):
        make_skill(self.universal, "offload")
        make_skill(self.live, "offload")
        make_skill(self.live, "renamed", "offload")
        make_skill(self.archive, "archive-only", "offload")
        make_skill(self.live, "local-skill")
        reconciler = SkillReconciler(self.brain)

        actions = reconciler.reconcile_project_skills(self.project.name, self.project)

        self.assertEqual([(action.skill_name, action.action) for action in actions],
                         [("local-skill", SyncAction.BACKUP_TO_BRAIN)])
        self.assertFalse((self.archive / "offload").exists())
        self.assertFalse((self.archive / "renamed").exists())
        self.assertFalse((self.live / "archive-only").exists())
        self.assertTrue((self.archive / "local-skill" / "SKILL.md").is_file())

    def test_catalog_skips_archived_duplicates_and_candidates(self):
        script = BRAIN_ROOT / ".agents/skills/auto-skill/scripts/sync_catalog.py"
        spec = importlib.util.spec_from_file_location("fixture_sync_catalog", script)
        catalog = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(catalog)
        make_skill(self.universal, "offload")
        make_skill(self.archive, "offload", "other-name")
        make_skill(self.archive, "renamed", "offload")
        make_skill(self.archive, "local-skill")
        make_skill(self.archive.parent / "_universal_candidates", "candidate")

        with (
            patch.object(catalog, "BRAIN_SKILLS_DIR", self.universal),
            patch.object(catalog, "brain_project_skills", self.archive.parent),
        ):
            skills = catalog.scan_skills()

        self.assertEqual([(entry["name"], entry["scope"]) for entry in skills],
                         [("offload", "Universal"), ("local-skill", "Project: project")])


class BrainGitTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.check_output(
            ["git", *args], cwd=self.root, text=True, stderr=subprocess.STDOUT,
        ).strip()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def test_commit_scopes_to_new_managed_changes_and_preserves_existing_index(self):
        with tempfile.TemporaryDirectory() as directory:
            self.root = Path(directory)
            self.git("init")
            self.git("config", "user.name", "Fixture")
            self.git("config", "user.email", "fixture@example.test")
            for name in ("ideas.md", "constraints.md", "untouched.md", "staged.md"):
                self.write(name, "baseline\n")
            self.git("add", "--all")
            self.git("commit", "-m", "Baseline")

            self.write("constraints.md", "pre-existing managed work\n")
            self.write("untouched.md", "local changes\n")
            self.write("staged.md", "already staged\n")
            self.git("add", "--", "staged.md")
            self.write("untracked.md", "untracked local work\n")
            with patch.object(full_sync, "BRAIN_ROOT", self.root):
                before = frozenset(full_sync._managed_git_changes())
                self.write("ideas.md", "new sync output\n")
                self.write("projects/fixture/new context.md", "new archive\n")
                full_sync._commit_brain_git("Managed only", preexisting_changes=before)

            self.assertEqual(set(self.git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()),
                             {"ideas.md", "projects/fixture/new context.md"})
            self.assertEqual(self.git("diff", "--cached", "--name-only"), "staged.md")
            self.assertEqual(set(self.git("diff", "--name-only").splitlines()),
                             {"constraints.md", "untouched.md"})
            self.assertEqual(self.git("ls-files", "--others", "--exclude-standard"), "untracked.md")

    def test_git_failure_propagates(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(full_sync, "BRAIN_ROOT", Path(directory)):
                with self.assertRaises(subprocess.CalledProcessError):
                    full_sync._commit_brain_git()


if __name__ == "__main__":
    unittest.main()
