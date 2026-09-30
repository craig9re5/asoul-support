import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop.storage import initialize, load_config, read_json, write_json
from desktop.engine import Engine
from desktop.windows import Job, Mutex


class ConfigTests(unittest.TestCase):
    def test_duplicate_room_is_rejected_before_monitoring(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(
                root, [{"name": "A", "uid": 1, "room": 2}, {"name": "B", "uid": 3, "room": 2}]
            )
            with self.assertRaisesRegex(ValueError, "重复"):
                load_config(root)

    def test_invalid_interval_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [])
            write_json(root / "settings.json", {"check_minutes": 0})
            with self.assertRaises(ValueError):
                load_config(root)

    def test_snapshot_includes_medals_and_intimacy(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [{"name": "测试主播", "uid": 12345, "room": 67890}])
            write_json(
                root / "status.json",
                {
                    "medals": {
                        "12345": {
                            "medal_name": "测试牌",
                            "level": 10,
                            "today_intimacy": 50,
                            "day_limit": 1500,
                            "is_lighted": 1,
                        }
                    }
                },
            )
            engine = Engine(root, job=Mock())
            snap = engine.snapshot()
            self.assertEqual(len(snap["rows"]), 1)
            row = snap["rows"][0]
            self.assertEqual(row["medal_name"], "测试牌")
            self.assertEqual(row["medal_level"], 10)
            self.assertEqual(row["today_intimacy"], 50)
            self.assertEqual(row["day_limit"], 1500)
            self.assertEqual(row["is_lighted"], 1)

    def test_format_task_mini_badge(self):
        from desktop.ui import format_task_mini_badge

        # 1. Unlit medal
        self.assertEqual(format_task_mini_badge([], is_lighted=0), "⚪待复活(0/10)")
        # 2. Empty tasks
        self.assertEqual(format_task_mini_badge([], is_lighted=1), "—")
        # 3. Partial tasks
        sample_tasks = [
            {"title": "发弹幕", "sub_title": "每日上限 2/5", "is_done": False},
            {"title": "点赞30次", "sub_title": "每日上限 0/5", "is_done": False},
            {"title": "观看直播满15分钟", "sub_title": "每日上限 3/5", "is_done": False},
            {"title": "投喂粉丝灯牌", "sub_title": "每日上限 1/1", "is_done": True},
        ]
        self.assertEqual(format_task_mini_badge(sample_tasks, is_lighted=1), "💬2/5 👍0/5 ⏱3/5 🏮✓")
        # 4. All completed
        done_tasks = [
            {"title": "发弹幕", "sub_title": "每日上限 5/5", "is_done": True},
            {"title": "点赞30次", "sub_title": "每日上限 5/5", "is_done": True},
            {"title": "观看直播满15分钟", "sub_title": "每日上限 5/5", "is_done": True},
            {"title": "投喂粉丝灯牌", "sub_title": "每日上限 1/1", "is_done": True},
        ]
        self.assertEqual(format_task_mini_badge(done_tasks, is_lighted=1), "✅ 全部完成")
        # 5. Anchor without fans medal
        self.assertEqual(format_task_mini_badge([], is_lighted=0, has_medal=False), "无勋章")

    @unittest.skipUnless(os.name == "nt", "Windows registry")
    def test_autostart_toggle(self):
        from desktop.windows import is_autostart_enabled, set_autostart

        app_test_name = "LiveSupport_TestUnit"
        try:
            self.assertFalse(is_autostart_enabled(app_test_name))
            set_autostart(True, app_test_name)
            self.assertTrue(is_autostart_enabled(app_test_name))
            set_autostart(False, app_test_name)
            self.assertFalse(is_autostart_enabled(app_test_name))
        finally:
            set_autostart(False, app_test_name)


@unittest.skipUnless(os.name == "nt", "Windows process ownership")
class ProcessTests(unittest.TestCase):
    def sleeper(self):
        return subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

    def test_job_exit_kills_owned_child_only(self):
        job = Job()
        owned, unrelated = self.sleeper(), self.sleeper()
        try:
            job.add(owned)
            job.close()
            owned.wait(timeout=5)
            self.assertIsNone(unrelated.poll())
        finally:
            for proc in (owned, unrelated):
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
            job.close()

    def test_pause_stops_all_owned_processes_and_persists(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [])
            engine = Engine(root)
            worker, probe = self.sleeper(), self.sleeper()
            engine.job.add(worker)
            engine.job.add(probe)
            engine.workers[123] = worker
            engine.probe = probe
            try:
                engine.set_paused(True)
                self.assertIsNotNone(worker.poll())
                self.assertIsNotNone(probe.poll())
                self.assertTrue(read_json(root / "settings.json")["paused"])
                engine.set_paused(False)
                self.assertEqual(engine.next_check, 0)
                self.assertFalse(read_json(root / "settings.json")["paused"])
            finally:
                engine.stop_children()
                engine.job.close()

    def test_second_instance_cannot_acquire_mutex(self):
        first = Mutex(f"test-{os.getpid()}")
        second = Mutex(f"test-{os.getpid()}")
        try:
            self.assertTrue(first.acquired)
            self.assertFalse(second.acquired)
        finally:
            second.close()
            first.close()


if __name__ == "__main__":
    unittest.main()
