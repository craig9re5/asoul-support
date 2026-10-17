import io
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
try:
    from PIL import Image
except ImportError:
    Image = None

from desktop.avatars import load_avatar, avatar_url, round_avatar, MAX_BYTES
from desktop.presentation import phase_label, gain_label
from desktop.storage import initialize
from desktop.engine import Engine
from asoul_support.runtime import task_day


class WorkbenchTests(unittest.TestCase):
    def test_running_label_uses_session_duration_and_only_running_state(self):
        row = {"active": True, "phase": "挂机中", "started": 100}
        self.assertEqual(phase_label(row, 100 + 42 * 60), "挂机中·42分钟")
        self.assertEqual(phase_label({**row, "phase": "账号保护暂停"}, 300), "账号保护暂停")
        self.assertEqual(gain_label({"intimacy_gain": None}), "今日亲密度：待更新")
        self.assertEqual(gain_label({"intimacy_gain": 0}), "今日亲密度 +0")

    def test_gain_requires_current_confirmed_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [{"uid": 1, "room": 2, "name": "test"}])
            engine = Engine(root, job=Mock())
            now = time.time()
            engine.account_checked_at = now
            engine.statuses = {"2": {"live_status": 1, "face": "https://i0.hdslb.com/bfs/face/test.jpg"}}
            engine.status_times = {"2": now}
            engine.medals = {1: {"today_intimacy": 9, "level": 9}}
            engine.tasks = {"2": {"day": task_day(), "updated": now}}
            row = engine.snapshot()["rows"][0]
            self.assertEqual(row["intimacy_gain"], 9)
            self.assertIn("hdslb.com", row["avatar_url"])
            engine.tasks["2"]["day"] = "2000-01-01"
            self.assertIsNone(engine.snapshot()["rows"][0]["intimacy_gain"])
            engine.tasks["2"]["day"] = task_day()
            engine.medals[1].pop("today_intimacy")
            self.assertIsNone(engine.snapshot()["rows"][0]["intimacy_gain"])

    @unittest.skipUnless(Image, "desktop Pillow dependency")
    def test_avatar_uses_public_profile_without_cookie_and_daily_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = Image.new("RGB", (60,30), "green")
            body = io.BytesIO()
            image.save(body, "PNG")
            profile = b'{"data":{"info":{"face":"https://i0.hdslb.com/bfs/face/synthetic.png"}}}'
            with patch("desktop.avatars._read", side_effect=[profile, body.getvalue()]) as read:
                actual = load_avatar(root, 123)
            self.assertEqual(actual.size, (128,128))
            self.assertIn("Master/info?uid=123", read.call_args_list[0].args[0])
            with patch("desktop.avatars._read", side_effect=AssertionError("cache should avoid IO")):
                self.assertEqual(load_avatar(root, 123).size, (128,128))
            circle = round_avatar(actual, 40)
            self.assertEqual(circle.getpixel((0,0))[3], 0)
            self.assertEqual(circle.getpixel((20,20))[3], 255)

    @unittest.skipUnless(Image, "desktop Pillow dependency")
    def test_avatar_rejects_external_targets_and_bad_images(self):
        self.assertEqual(avatar_url("https://example.com/x"), "")
        self.assertEqual(avatar_url("https://user:password@i0.hdslb.com/x"), "")
        self.assertEqual(avatar_url("//i0.hdslb.com/bfs/face/x.png"), "https://i0.hdslb.com/bfs/face/x.png")
        with tempfile.TemporaryDirectory() as folder, patch("desktop.avatars._read", return_value=b"not an image"):
            with self.assertRaises(OSError):
                load_avatar(Path(folder), 123, "https://i0.hdslb.com/bfs/face/x.png")

    def test_avatar_transport_has_no_credentials_and_bounds_reads(self):
        from desktop.avatars import _read
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"12345"
        opener = Mock()
        opener.open.return_value = response
        with patch("desktop.avatars.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ValueError):
                _read("https://i0.hdslb.com/bfs/face/test.png", 4)
        request = opener.open.call_args.args[0]
        self.assertFalse(request.has_header("Cookie"))
        response.read.assert_called_once_with(5)

    def test_measure_cache_avoids_repeated_font_fallback(self):
        # Emoji fall back through the font stack and measure ~5ms each; the list
        # re-elides every row per refresh, so widths must be memoised per font spec.
        from desktop import room_list

        room_list._MEASURE_CACHE.clear()
        font = Mock()
        font.actual.return_value = {"family": "test", "size": 9}
        font.measure.return_value = 42
        self.assertEqual(room_list.measure(font, "💬2/5"), 42)
        self.assertEqual(room_list.measure(font, "💬2/5"), 42)
        self.assertEqual(font.measure.call_count, 1)
        self.assertEqual(room_list.measure(font, "other"), 42)
        self.assertEqual(font.measure.call_count, 2)

    def test_font_for_reuses_one_object_per_spec(self):
        from desktop import room_list

        room_list._FONT_CACHE.clear()
        widget = Mock()
        widget.cget.return_value = ("Microsoft YaHei UI", 9)
        with patch("desktop.room_list.tkfont.Font") as factory:
            factory.side_effect = lambda **_: Mock()
            first = room_list.font_for(widget)
            second = room_list.font_for(widget)
        self.assertIs(first, second)
        self.assertEqual(factory.call_count, 1)

    def test_detail_clears_when_selection_is_empty(self):
        """A stale detail panel kept the old room's buttons live after deselect."""
        from desktop import workbench as wb_module

        widgets = {}
        wb = object.__new__(wb_module.Workbench)
        wb.ui = SimpleNamespace(px=lambda v: v, rows_cache={}, room_actions={})
        for name in ("detail_title", "detail_live_title", "detail_phase", "detail_medal",
                     "detail_gain", "detail_exp", "detail_heartbeat", "detail_warning",
                     "open_button", "redo_button", "reconnect_button", "action_hint"):
            widgets[name] = Mock()
            setattr(wb, name, widgets[name])
        wb.task_labels = [("弹幕", Mock()), ("观看", Mock())]
        wb.experience_fraction = 0.5
        wb._draw_experience = Mock()
        wb._render_menu = Mock()

        wb._render_no_selection()

        self.assertEqual(widgets["detail_title"].configure.call_args.kwargs["text"], "未选择直播间")
        for name in ("open_button", "redo_button", "reconnect_button"):
            self.assertEqual(widgets[name].configure.call_args.kwargs["state"], "disabled")
        widgets["detail_warning"].pack_forget.assert_called_once_with()
        widgets["action_hint"].pack_forget.assert_called_once_with()
        self.assertEqual(wb.experience_fraction, 0)
