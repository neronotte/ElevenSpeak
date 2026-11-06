import argparse
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[1]
        / ".github"
        / "skills"
        / "eleven-speak"
        / "scripts"
    ),
)

import eleven_say as say


WORKER = """
import json, sys, time
from pathlib import Path
import eleven_say as say
root, name, duration, wait, budget = sys.argv[1:]
root = Path(root)
say.LOCK_PATH = root / 'playback.lock'
def operation(*args):
    (root / (name + '.started')).touch()
    start = time.monotonic()
    time.sleep(float(duration))
    (root / (name + '.json')).write_text(json.dumps([start, time.monotonic()]))
    return 0
say.run_operation = operation
sys.argv = ['eleven_say.py', '--replay', '--lock-timeout', wait,
            '--operation-timeout', budget]
sys.exit(say.main())
"""


class ScriptTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.children = []

    def tearDown(self):
        for child in self.children:
            if child.poll() is None:
                child.kill()
            child.communicate()
        self.directory.cleanup()

    def start_worker(self, name, duration, wait=3, budget=3):
        child = subprocess.Popen(
            [sys.executable, "-c", WORKER, str(self.root), name,
             str(duration), str(wait), str(budget)],
            cwd=Path(say.__file__).parent,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.children.append(child)
        return child

    def await_started(self, name):
        deadline = time.monotonic() + 10
        while not (self.root / f"{name}.started").exists():
            if time.monotonic() > deadline:
                self.fail("Worker did not acquire the lock")
            time.sleep(0.02)

    def result(self, child):
        _, stderr = child.communicate(timeout=10)
        return child.returncode, stderr

    def test_concurrent_invocations_do_not_overlap(self):
        first = self.start_worker("first", 4, budget=6)
        self.await_started("first")
        second = self.start_worker("second", 0.1, wait=8)
        self.assertEqual(self.result(first)[0], 0)
        self.assertEqual(self.result(second)[0], 0)
        first_times = json.loads((self.root / "first.json").read_text())
        second_times = json.loads((self.root / "second.json").read_text())
        self.assertGreaterEqual(second_times[0], first_times[1])

    def test_lock_timeout_never_runs_operation(self):
        first = self.start_worker("first", 4, budget=6)
        self.await_started("first")
        second = self.start_worker("second", 0.1, wait=0.1)
        code, error = self.result(second)
        self.assertEqual(code, 75)
        self.assertIn("turno audio", error)
        self.assertFalse((self.root / "second.started").exists())
        self.assertEqual(self.result(first)[0], 0)

    def test_watchdog_exit_releases_lock(self):
        first = self.start_worker("first", 10, budget=0.6)
        self.await_started("first")
        second = self.start_worker("second", 0.1)
        code, error = self.result(first)
        self.assertEqual(code, 124)
        self.assertIn("processo interrotto", error)
        self.assertEqual(self.result(second)[0], 0)
        self.assertFalse((self.root / "first.json").exists())

    def test_watchdog_is_cancelled_after_success(self):
        with patch.object(say.os, "_exit") as exit_process:
            with say.operation_watchdog(0.05):
                pass
            time.sleep(0.1)
            exit_process.assert_not_called()

    def test_watchdog_is_cancelled_after_exception(self):
        with patch.object(say.os, "_exit") as exit_process:
            with self.assertRaises(ValueError):
                with say.operation_watchdog(0.05):
                    raise ValueError("test")
            time.sleep(0.1)
            exit_process.assert_not_called()

    def test_atomic_cache_preserves_previous_note_on_failure(self):
        destination = self.root / "note.wav"
        destination.write_bytes(b"previous")
        with self.assertRaises(ValueError):
            with say.atomic_cache_file(destination) as temporary:
                temporary.write_bytes(b"incomplete")
                raise ValueError("test")
        self.assertEqual(destination.read_bytes(), b"previous")
        self.assertEqual(list(self.root.glob("*.tmp")), [])
        with say.atomic_cache_file(destination) as temporary:
            temporary.write_bytes(b"complete")
        self.assertEqual(destination.read_bytes(), b"complete")

    def test_cleanup_removes_interrupted_temporary_files(self):
        (self.root / "note-123.tmp").write_bytes(b"incomplete")
        (self.root / "note.wav").write_bytes(b"complete")
        (self.root / "unrelated.txt").write_text("keep")
        with patch.object(say, "CACHE_DIR", self.root):
            say.purge_cache(30)
        self.assertFalse((self.root / "note-123.tmp").exists())
        self.assertTrue((self.root / "note.wav").exists())
        self.assertTrue((self.root / "unrelated.txt").exists())

    def test_invalid_timeouts(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    say.positive_seconds(value)

    def test_off_disables_all_modes_before_input_and_lock(self):
        (self.root / ".off").touch()
        for args in (["message"], ["--replay"], ["--list-voices"], []):
            with self.subTest(args=args), \
                 patch.object(say, "__file__", str(self.root / "eleven_say.py")), \
                 patch.object(sys, "argv", ["eleven_say.py", *args]), \
                 patch.object(say, "load_env_file") as load_env, \
                 patch.object(say, "run_operation") as run, \
                 patch.object(say.portalocker, "Lock") as lock:
                self.assertEqual(say.main(), 0)
                load_env.assert_not_called()
                run.assert_not_called()
                lock.assert_not_called()

    def test_off_created_while_waiting_prevents_operation(self):
        class FakeLock:
            released = False

            def acquire(inner_self):
                (self.root / ".off").touch()

            def release(inner_self):
                inner_self.released = True

        fake_lock = FakeLock()
        with patch.object(say, "__file__", str(self.root / "eleven_say.py")), \
             patch.object(say, "LOCK_PATH", self.root / "playback.lock"), \
             patch.object(sys, "argv", ["eleven_say.py", "--replay"]), \
             patch.object(say, "load_env_file"), \
             patch.object(say.portalocker, "Lock", return_value=fake_lock), \
             patch.object(say, "run_operation") as run:
            self.assertEqual(say.main(), 0)
            run.assert_not_called()
            self.assertTrue(fake_lock.released)

    def test_without_off_operation_runs(self):
        with patch.object(say, "__file__", str(self.root / "eleven_say.py")), \
             patch.object(say, "LOCK_PATH", self.root / "playback.lock"), \
             patch.object(sys, "argv", ["eleven_say.py", "--replay"]), \
             patch.object(say, "load_env_file"), \
             patch.object(say, "run_operation", return_value=0) as run:
            self.assertEqual(say.main(), 0)
            run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
