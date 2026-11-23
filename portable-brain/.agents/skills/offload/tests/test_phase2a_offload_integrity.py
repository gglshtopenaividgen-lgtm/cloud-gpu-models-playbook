import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
MANAGER = ROOT / '.agents/skills/offload/scripts/offload_manager.py'
COMPILER = ROOT / '.agents/skills/full-sync/scripts/offload_context_compiler.py'
spec = importlib.util.spec_from_file_location('offload_compiler_fixture', COMPILER)
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)

manager_spec = importlib.util.spec_from_file_location("offload_manager_fixture", MANAGER)
manager = importlib.util.module_from_spec(manager_spec)
manager_spec.loader.exec_module(manager)


class OffloadIntegrity(unittest.TestCase):
    def test_concurrent_claim_and_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / 'prompt.md'
            prompt.write_text('Isolated test task.', encoding='utf-8')

            def command(action, *args):
                return [sys.executable, str(MANAGER), action, '--project', str(root), *args]

            subprocess.run(command('dispatch', '--title', 'Fixture', '--prompt-file', str(prompt)),
                           capture_output=True, check=True)
            task_path, = (root / 'offload/tasks').glob('TASK-*.json')
            task_id = task_path.stem
            claim = command('worker-claim', '--task-id', task_id)
            with subprocess.Popen(claim, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as first:
                with subprocess.Popen(claim, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as second:
                    first_output, first_error = first.communicate(timeout=15)
                    second_output, second_error = second.communicate(timeout=15)
            self.assertEqual(sorted([first.returncode, second.returncode]), [0, 1],
                             (first_output, first_error, second_output, second_error))
            data = json.loads(task_path.read_text(encoding='utf-8'))
            complete = command('worker-complete', '--task-id', task_id, '--summary', 'Fixture result')
            rejected = subprocess.run([*complete, '--claim-id', 'other'], capture_output=True)
            self.assertEqual(rejected.returncode, 1)
            self.assertEqual(json.loads(task_path.read_text(encoding='utf-8'))['status'], 'IN_PROGRESS')
            subprocess.run([*complete, '--claim-id', data['claim_id']], capture_output=True, check=True)
            self.assertEqual(json.loads(task_path.read_text(encoding='utf-8'))['status'], 'COMPLETED')
            presence = json.loads((root / 'offload/status.json').read_text(encoding='utf-8'))
            self.assertIsNone(presence['worker']['pid'])

    def test_directory_lock_contends_across_processes_and_reaps_dead_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = (
                "import sys, time; from pathlib import Path; "
                "sys.path.insert(0, sys.argv[1]); from offload_manager import offload_lock; "
                "exec('with offload_lock(Path(sys.argv[2])):\\n"
                " Path(sys.argv[3]).touch()\\n time.sleep(60)')"
            )
            ready = root / "child-ready"
            args = [sys.executable, "-B", "-c", entry, str(MANAGER.parent), str(root), str(ready)]
            child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline and child.poll() is None:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), "Child did not acquire the directory lock")
                lock_dir = root / manager._OFFLOAD_LOCK_DIR
                original_owner, = lock_dir.glob("owner.*.json")
                info = json.loads(original_owner.read_text(encoding="utf-8"))
                self.assertEqual(info["pid"], child.pid)
                age = time.time() - manager._OFFLOAD_LOCK_TTL - 1
                os.utime(original_owner, (age, age))
                with self.assertRaises(TimeoutError):
                    with manager.offload_lock(root, timeout=0.15):
                        self.fail("Reaped a live owner")
            finally:
                child.kill()
                child.communicate(timeout=5)

            with manager.offload_lock(root, timeout=2):
                recovered_owner, = lock_dir.glob("owner.*.json")
                self.assertNotEqual(recovered_owner, original_owner)
                manager._drop_lock_owner(original_owner)
                self.assertTrue(recovered_owner.is_file())
                with manager.offload_lock(root):
                    self.assertTrue(recovered_owner.is_file())
            self.assertFalse(lock_dir.exists())

    def test_abandoned_empty_directory_is_recoverable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / manager._OFFLOAD_LOCK_DIR
            lock.mkdir()
            age = time.time() - manager._OFFLOAD_LOCK_TTL - 1
            os.utime(lock, (age, age))
            with manager.offload_lock(root, timeout=1):
                owner, = lock.glob("owner.*.json")
                self.assertTrue(owner.is_file())
            self.assertFalse(lock.exists())

    def test_atomic_replace_retries_sharing_errors_and_removes_failed_temporary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "status.json"
            target.write_text("original", encoding="utf-8")
            replace = os.replace
            errors = iter((PermissionError("sharing violation"), OSError("indexer busy")))

            def replace_after_sharing_errors(source, destination):
                failure = next(errors, None)
                if failure is not None:
                    raise failure
                return replace(source, destination)

            with (
                patch.object(manager.os, "replace", side_effect=replace_after_sharing_errors) as patched,
                patch.object(manager.time, "sleep") as delay,
            ):
                manager.atomic_write_text(target, "replacement")
                self.assertEqual(patched.call_count, 3)
                self.assertEqual([call.args[0] for call in delay.call_args_list], [0.025, 0.05])
            self.assertEqual(target.read_text(encoding="utf-8"), "replacement")

            with (
                patch.object(manager.os, "replace", side_effect=PermissionError("still busy")) as patched,
                patch.object(manager.time, "sleep"),
            ):
                with self.assertRaises(PermissionError):
                    manager.atomic_write_text(target, "uncommitted")
                self.assertEqual(patched.call_count, 6)
            self.assertEqual(target.read_text(encoding="utf-8"), "replacement")
            self.assertEqual(list(root.iterdir()), [target])

    def test_dry_run_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            literal = 'synthetic-passphrase-with-spaces'
            pattern = 'sk-' + 'a' * 24
            (root / '.env.fixture').write_text(f'FIXTURE={literal}', encoding='utf-8')
            (root / 'constraints.md').write_text(f'Markers {literal} and {pattern}', encoding='utf-8')
            (root / 'entry.py').write_text('def entry(): pass', encoding='utf-8')
            with patch.object(compiler, '_git_volatile_tail', return_value=''):
                out, stats = compiler.compile_offload_context(root, dry_run=True)
                self.assertFalse(out.parent.exists())
                self.assertEqual(stats['redaction_count'], 2)
                compiler.compile_offload_context(root)
                before = {path.name: path.read_bytes() for path in out.parent.iterdir()}
                compiler.compile_offload_context(root, dry_run=True)
                after = {path.name: path.read_bytes() for path in out.parent.iterdir()}
            self.assertEqual(before, after)
            result = out.read_text(encoding='utf-8')
            self.assertNotIn(literal, result)
            self.assertNotIn(pattern, result)
            self.assertIn('[REDACTED_API_KEY]', result)
            self.assertIn('[REDACTED_ENV_SECRET]', result)
            self.assertIn('Compilation Metadata', result)


if __name__ == '__main__':
    unittest.main()
