import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from danmaku_pacing import send_paced  # noqa: E402


class DanmakuPacingTests(unittest.TestCase):
    def test_interval_persists_across_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "pace.lock"
            first = send_paced(time.time, lock_path=lock_path, min_interval=0.2)
            second = send_paced(time.time, lock_path=lock_path, min_interval=0.2)
            self.assertGreaterEqual(second - first, 0.18)

    def test_two_processes_share_one_send_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "pace.lock"
            gate_path = Path(directory) / "go"
            program = (
                "import sys,time; from pathlib import Path; "
                "sys.path.insert(0,sys.argv[1]); "
                "from danmaku_pacing import send_paced; "
                "gate=Path(sys.argv[3]); "
                "\nwhile not gate.exists(): time.sleep(.01)\n"
                "print(send_paced(time.time,lock_path=Path(sys.argv[2]),"
                "min_interval=.4))"
            )
            args = [sys.executable, "-c", program, str(SCRIPTS_DIR), str(lock_path), str(gate_path)]
            processes = [
                subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                for _ in range(2)
            ]
            try:
                time.sleep(0.2)
                gate_path.touch()
                outputs = [process.communicate(timeout=10) for process in processes]
                for process, (_, stderr) in zip(processes, outputs):
                    self.assertEqual(process.returncode, 0, stderr)
                timestamps = sorted(float(stdout.strip()) for stdout, _ in outputs)
                self.assertGreaterEqual(timestamps[1] - timestamps[0], 0.35)
            finally:
                for process in processes:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()


if __name__ == "__main__":
    unittest.main()
