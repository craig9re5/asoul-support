import json
import os
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import heartbeat  # noqa: E402
from process_lock import is_process_running  # noqa: E402


class X25KnTests(unittest.TestCase):
    def test_signing_vector(self):
        payload = (
            '{"platform":"web","parent_id":9,"area_id":371,"seq_id":1,'
            '"room_id":22632424,"buvid":"TEST-BUVID",'
            '"uuid":"00000000-0000-4000-8000-000000000000",'
            '"ets":1700000000,"time":60,"ts":1700000060000}'
        )

        result = heartbeat._x25kn_sign(
            payload,
            [2, 5, 1, 4],
            "seacasdgyijfhofiuxoannn",
        )

        self.assertEqual(
            result,
            "09159f943eb73570f2f6395b35291397f666444492e0c4e0197fcc7f509f850b"
            "37a06aade2a8d2657e367e400aacc0817d5fc0ca900a1bf33e9b6beb6d8eb91d",
        )

    @patch("heartbeat._now_ms", return_value=1700000060000)
    @patch("heartbeat._x25kn_post")
    def test_x_request_uses_server_interval_and_ruid(self, post, _now):
        post.return_value = {
            "code": 0,
            "data": {
                "timestamp": 1700000060,
                "heartbeat_interval": 60,
                "secret_key": "next-key",
                "secret_rule": [2, 5, 1, 4],
            },
        }

        result = heartbeat.x25kn_heartbeat(
            room_id=22632424,
            parent_id=9,
            area_id=371,
            up_id=672353429,
            seq=1,
            buvid="TEST-BUVID",
            uuid_str="00000000-0000-4000-8000-000000000000",
            ets=1700000000,
            secret_key="seacasdgyijfhofiuxoannn",
            secret_rule=[2, 5, 1, 4],
            heartbeat_interval=60,
            sessdata="secret",
            bili_jct="csrf",
        )

        self.assertEqual(result["secret_key"], "next-key")
        form = post.call_args.args[1]
        self.assertEqual(form["ruid"], 672353429)
        self.assertEqual(form["time"], 60)
        self.assertEqual(json.loads(form["id"]), [9, 371, 1, 22632424])

    @patch("heartbeat.time.sleep")
    @patch("heartbeat.time.monotonic", return_value=112.5)
    def test_wait_subtracts_work_already_spent(self, _monotonic, sleep):
        waited = heartbeat._wait_for_heartbeat_window(100.0, 60)

        self.assertEqual(waited, 47.5)
        sleep.assert_called_once_with(47.5)


class LiveLikeTests(unittest.TestCase):
    @patch("urllib.request.OpenerDirector.open")
    def test_live_like_post_has_no_form_body(self, urlopen):
        urlopen.return_value.__enter__.return_value.read.return_value = b'{"code":0}'
        response = heartbeat._post_empty_json(
            "https://example.test/likeReportV3", {"Cookie": "test"}
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(response["code"], 0)
        self.assertEqual(request.get_method(), "POST")
        self.assertIsNone(request.data)
        self.assertFalse(request.has_header("Content-type"))

    @patch("heartbeat.get_mixin_key", return_value="test-mixin-key")
    @patch("heartbeat._post_empty_json", return_value={"code": 0, "message": "0"})
    def test_live_like_reports_room_viewer_and_anchor(self, post, _mixin):
        headers = {
            "Cookie": "test-browser-session",
            "Referer": "https://live.bilibili.com/1727071052",
        }
        result = heartbeat.report_live_likes(
            1727071052, 1891335475, 12345, "session", "csrf", headers=headers
        )

        self.assertTrue(result["success"])
        url, sent_headers = post.call_args.args
        self.assertIn("/likeReportV3?", url)
        params = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        self.assertEqual(
            {
                k: params[k]
                for k in ("click_time", "room_id", "uid", "anchor_id", "web_location", "csrf")
            },
            {
                "click_time": "30",
                "room_id": "1727071052",
                "uid": "12345",
                "anchor_id": "1891335475",
                "web_location": "444.8",
                "csrf": "csrf",
            },
        )
        self.assertIn("wts", params)
        self.assertEqual(len(params["w_rid"]), 32)
        self.assertIs(sent_headers, headers)

    @patch("heartbeat.load_cookies")
    def test_like_headers_require_matching_browser_account(self, load):
        load.return_value = {
            "SESSDATA": "session",
            "bili_jct": "csrf",
            "live_like_cookie": "SESSDATA=session; bili_jct=csrf; DedeUserID=12345; buvid3=device",
            "live_like_user_agent": "Browser UA",
        }
        headers = heartbeat._live_like_headers(1727071052, 12345, "session", "csrf")
        self.assertEqual(headers["User-Agent"], "Browser UA")
        self.assertIn("buvid3=device", headers["Cookie"])
        self.assertIsNone(heartbeat._live_like_headers(1727071052, 99999, "session", "csrf"))

    @patch("heartbeat._get_json")
    def test_like_progress_uses_task_rounds(self, get_json):
        get_json.return_value = {
            "code": 0,
            "data": {
                "task_info": [
                    {
                        "jump_type": "like",
                        "title": "点赞30次",
                        "sub_title": "每日上限 1/5",
                        "is_done": False,
                    }
                ]
            },
        }
        result = heartbeat.get_live_like_progress(
            1727071052, 1891335475, {"Cookie": "test"}, "csrf"
        )
        self.assertEqual((result["current"], result["limit"], result["per_round"]), (1, 5, 30))
        self.assertIn("/GetActivatedMedalInfo?", get_json.call_args.args[0])

    @patch("heartbeat.time.sleep")
    @patch("heartbeat.report_live_likes")
    @patch("heartbeat.get_live_like_progress")
    @patch("heartbeat._live_like_headers", return_value={"Cookie": "test"})
    @patch("heartbeat.get_viewer_uid", return_value=12345)
    def test_live_like_stops_after_api_error(self, _uid, _headers, progress, report, sleep):
        progress.side_effect = [
            {"current": 0, "limit": 5, "per_round": 30, "done": False},
            {"current": 1, "limit": 5, "per_round": 30, "done": False},
        ]
        report.side_effect = [
            {"success": True, "code": 0, "message": "0"},
            {"success": False, "code": -111, "message": "csrf error"},
        ]

        result = heartbeat.like_live_room(1727071052, 1891335475, "session", "csrf")

        self.assertFalse(result["success"])
        self.assertEqual(result["reported"], 30)
        self.assertEqual(report.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in sleep.call_args_list],
            [heartbeat.LIVE_LIKE_PROGRESS_DELAY, heartbeat.LIVE_LIKE_DELAY],
        )

    @patch("heartbeat.time.sleep")
    @patch("heartbeat.report_live_likes", return_value={"success": True, "code": 0})
    @patch("heartbeat.get_live_like_progress")
    @patch("heartbeat._live_like_headers", return_value={"Cookie": "test"})
    @patch("heartbeat.get_viewer_uid", return_value=12345)
    def test_live_like_sends_only_remaining_round(self, _uid, _headers, progress, report, _sleep):
        progress.side_effect = [
            {"current": 4, "limit": 5, "per_round": 30, "done": False},
            {"current": 5, "limit": 5, "per_round": 30, "done": True},
        ]
        result = heartbeat.like_live_room(1727071052, 1891335475, "session", "csrf")
        self.assertTrue(result["success"])
        self.assertEqual(result["progress"], "5/5")
        self.assertEqual(result["reported"], 30)
        report.assert_called_once()

    @patch("heartbeat.time.sleep")
    @patch("heartbeat.report_live_likes", return_value={"success": True, "code": 0})
    @patch("heartbeat.get_live_like_progress")
    @patch("heartbeat._live_like_headers", return_value={"Cookie": "test"})
    @patch("heartbeat.get_viewer_uid", return_value=12345)
    def test_live_like_stops_when_task_does_not_advance(
        self, _uid, _headers, progress, report, _sleep
    ):
        progress.return_value = {"current": 0, "limit": 5, "per_round": 30, "done": False}
        result = heartbeat.like_live_room(1727071052, 1891335475, "session", "csrf")
        self.assertFalse(result["success"])
        self.assertEqual(result["reported"], 30)
        report.assert_called_once()


class ProcessLockTests(unittest.TestCase):
    def test_liveness_check_keeps_current_process_running(self):
        self.assertTrue(is_process_running(os.getpid()))
        self.assertFalse(is_process_running(0))


class DanmakuTaskTests(unittest.TestCase):
    def setUp(self):
        auth = patch.object(heartbeat, "get_viewer_uid", return_value=123)
        auth.start()
        self.addCleanup(auth.stop)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        for name, path in (("_TASK_STATE_DIR", "state/tasks"), ("_LOCK_DIR", "locks")):
            setting = patch.object(heartbeat, name, Path(folder.name) / path)
            setting.start()
            self.addCleanup(setting.stop)
        log_patch = patch("heartbeat._log")
        log_patch.start()
        self.addCleanup(log_patch.stop)

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_unlit_medal_waits_for_light_confirmation(self, get_club_info, send_danmaku, _sleep):
        get_club_info.return_value = {
            "is_lighted": False,
            "task_info": [
                {"jump_type": "sendDanmu", "sub_title": "每日上限 0/5", "is_done": False}
            ],
        }
        res = heartbeat.send_medal_danmaku_tasks(1727071052, 1891335475, "session", "csrf")
        self.assertEqual(res["light_sent"], 10)
        self.assertEqual(res["intimacy_sent"], 0)
        self.assertEqual(res["total_sent"], 10)
        self.assertEqual(send_danmaku.call_count, 10)

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_unlit_medal_sends_intimacy_after_lit(self, get_club_info, send_danmaku, _sleep):
        get_club_info.side_effect = [
            {
                "is_lighted": False,
                "task_info": [
                    {"jump_type": "sendDanmu", "sub_title": "每日上限 0/5", "is_done": False}
                ],
            },
            {
                "is_lighted": True,
                "task_info": [
                    {"jump_type": "sendDanmu", "sub_title": "每日上限 0/5", "is_done": False}
                ],
            },
            {
                "is_lighted": True,
                "task_info": [
                    {"jump_type": "sendDanmu", "sub_title": "每日上限 5/5", "is_done": True}
                ],
            },
        ]
        res = heartbeat.send_medal_danmaku_tasks(1727071052, 1891335475, "session", "csrf")
        self.assertEqual(res["total_sent"], 15)
        self.assertTrue(res["done"])
        self.assertEqual(send_danmaku.call_count, 15)

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_already_lit_medal_sends_only_5(self, get_club_info, send_danmaku, _sleep):
        get_club_info.return_value = {
            "is_lighted": True,
            "task_info": [
                {"jump_type": "sendDanmu", "sub_title": "每日上限 0/5", "is_done": False}
            ],
        }
        res = heartbeat.send_medal_danmaku_tasks(1727071052, 1891335475, "session", "csrf")
        self.assertEqual(res["light_sent"], 0)
        self.assertEqual(res["intimacy_sent"], 5)
        self.assertEqual(res["total_sent"], 5)
        self.assertEqual(send_danmaku.call_count, 5)

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_already_lit_and_danmu_done_sends_0(self, get_club_info, send_danmaku, _sleep):
        get_club_info.return_value = {
            "is_lighted": True,
            "task_info": [{"jump_type": "sendDanmu", "sub_title": "每日上限 5/5", "is_done": True}],
        }
        res = heartbeat.send_medal_danmaku_tasks(1727071052, 1891335475, "session", "csrf")
        self.assertEqual(res["light_sent"], 0)
        self.assertEqual(res["intimacy_sent"], 0)
        self.assertEqual(res["total_sent"], 0)
        self.assertEqual(send_danmaku.call_count, 0)

    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_partial_progress_sends_only_remaining_three(self, get_club_info, send_danmaku):
        get_club_info.side_effect = [
            {
                "is_lighted": True,
                "task_info": [
                    {"jump_type": "sendDanmu", "sub_title": "每日上限 2/5", "is_done": False}
                ],
            },
            {
                "is_lighted": True,
                "task_info": [
                    {"jump_type": "sendDanmu", "sub_title": "每日上限 5/5", "is_done": True}
                ],
            },
        ]
        result = heartbeat.send_medal_danmaku_tasks(1727071052, 1891335475, "session", "csrf")
        self.assertEqual(result["intimacy_sent"], 3)
        self.assertEqual(result["attempted"], 3)
        self.assertTrue(result["done"])
        self.assertEqual(send_danmaku.call_count, 3)

    @patch("heartbeat.send_paced", return_value={"code": -509, "message": "发言过于频繁"})
    def test_send_failure_records_api_reason(self, _paced):
        self.assertFalse(heartbeat._send_danmaku(1727071052, "测试", "session", "csrf"))
        heartbeat._log.assert_called_once()
        event = heartbeat._log.call_args.args[0]
        self.assertEqual((event["code"], event["message"]), (-509, "发言过于频繁"))

    @patch("heartbeat._send_danmaku", side_effect=[False, True, False, True, True])
    def test_batch_retries_failures_until_target(self, send_danmaku):
        sent, used, attempts = heartbeat.send_danmaku_batch(
            1727071052, 3, "session", "csrf", max_attempts=5
        )
        self.assertEqual((sent, attempts), (3, 5))
        self.assertEqual(len(used), 3)
        self.assertEqual(send_danmaku.call_count, 5)

    @patch("heartbeat._send_danmaku", return_value=False)
    def test_batch_respects_attempt_cap(self, send_danmaku):
        sent, _, attempts = heartbeat.send_danmaku_batch(
            1727071052, 3, "session", "csrf", max_attempts=4
        )
        self.assertEqual((sent, attempts), (0, 4))
        self.assertEqual(send_danmaku.call_count, 4)

    @patch("heartbeat._send_danmaku")
    @patch("heartbeat.get_fans_club_task_info", return_value={})
    def test_unknown_task_status_does_not_send(self, _get_club_info, send_danmaku):
        result = heartbeat.send_medal_danmaku_tasks(1727071052, 1891335475, "session", "csrf")
        self.assertEqual(result["attempted"], 0)
        send_danmaku.assert_not_called()

    @patch("heartbeat.DANMAKU_RECHECK_INTERVAL", 0)
    @patch("heartbeat._notify")
    @patch("heartbeat._log")
    @patch("heartbeat._wait_for_heartbeat_window")
    @patch("heartbeat.send_medal_danmaku_tasks", return_value={"attempted": 1})
    @patch(
        "heartbeat._get_single_room_status", side_effect=[{"live_status": 1}, {"live_status": 0}]
    )
    @patch(
        "heartbeat.x25kn_heartbeat",
        return_value={
            "secret_key": "key",
            "secret_rule": [2, 5, 1, 4],
            "timestamp": 1700000000,
            "heartbeat_interval": 60,
        },
    )
    @patch(
        "heartbeat.x25kn_enter_room",
        return_value={
            "secret_key": "key",
            "secret_rule": [2, 5, 1, 4],
            "timestamp": 1700000000,
            "heartbeat_interval": 60,
        },
    )
    @patch("heartbeat._ensure_live_buvid", return_value="device")
    @patch("heartbeat._get_room_info", return_value={"area_id": 1, "parent_area_id": 2})
    @patch("heartbeat.enter_room", return_value=True)
    def test_watch_loop_rechecks_danmaku_after_heartbeat(
        self, _enter, _room, _buvid, _e, _x, _status, send_tasks, _wait, _log, _notify
    ):
        result = heartbeat.watch_room(
            {"name": "test", "room": 1727071052, "uid": 1891335475},
            "session",
            "csrf",
            until_offline=True,
        )
        self.assertEqual(result["stopped_reason"], "offline")
        self.assertEqual(send_tasks.call_count, 2)

    @patch("heartbeat.DANMAKU_RECHECK_INTERVAL", 0)
    @patch("heartbeat._notify")
    @patch("heartbeat._log")
    @patch("heartbeat._wait_for_heartbeat_window")
    @patch("heartbeat.send_medal_danmaku_tasks", return_value={"attempted": 5, "done": True})
    @patch(
        "heartbeat._get_single_room_status", side_effect=[{"live_status": 1}, {"live_status": 0}]
    )
    @patch(
        "heartbeat.x25kn_heartbeat",
        return_value={
            "secret_key": "key",
            "secret_rule": [2, 5, 1, 4],
            "timestamp": 1700000000,
            "heartbeat_interval": 60,
        },
    )
    @patch(
        "heartbeat.x25kn_enter_room",
        return_value={
            "secret_key": "key",
            "secret_rule": [2, 5, 1, 4],
            "timestamp": 1700000000,
            "heartbeat_interval": 60,
        },
    )
    @patch("heartbeat._ensure_live_buvid", return_value="device")
    @patch("heartbeat._get_room_info", return_value={"area_id": 1, "parent_area_id": 2})
    @patch("heartbeat.enter_room", return_value=True)
    def test_watch_loop_stops_rechecking_once_danmaku_done(
        self, _enter, _room, _buvid, _e, _x, _status, send_tasks, _wait, _log, _notify
    ):
        result = heartbeat.watch_room(
            {"name": "test", "room": 1727071052, "uid": 1891335475},
            "session",
            "csrf",
            until_offline=True,
        )
        self.assertEqual(result["stopped_reason"], "offline")
        self.assertEqual(send_tasks.call_count, 1)

    @patch("heartbeat.time.sleep")
    @patch("heartbeat._send_danmaku", return_value=True)
    @patch("heartbeat.get_fans_club_task_info")
    def test_unlit_medal_proceeds_even_if_progress_is_initially_none(
        self, get_club_info, send_danmaku, _sleep
    ):
        get_club_info.side_effect = [
            {"is_lighted": False, "task_info": []},
            {
                "is_lighted": True,
                "task_info": [
                    {"jump_type": "sendDanmu", "sub_title": "每日上限 5/5", "is_done": True}
                ],
            },
            {
                "is_lighted": True,
                "task_info": [
                    {"jump_type": "sendDanmu", "sub_title": "每日上限 5/5", "is_done": True}
                ],
            },
        ]
        res = heartbeat.send_medal_danmaku_tasks(1727071052, 1891335475, "session", "csrf")
        self.assertEqual(res["light_sent"], 10)
        self.assertTrue(res["done"])
        self.assertEqual(send_danmaku.call_count, 10)

    def test_danmaku_task_progress_fallback_on_is_done(self):
        info = {"task_info": [{"jump_type": "sendDanmu", "sub_title": "已完成", "is_done": True}]}
        res = heartbeat._danmaku_task_progress(info)
        self.assertIsNotNone(res)
        self.assertTrue(res["done"])

    def test_pacing_lock_timeout_is_at_least_30s(self):
        import danmaku_pacing

        self.assertGreaterEqual(danmaku_pacing.LOCK_WAIT_TIMEOUT, 30.0)

    def test_check_limits_allow_full_revival(self):
        self.assertGreaterEqual(heartbeat.DANMAKU_ATTEMPTS_PER_CHECK, 15)
        self.assertGreaterEqual(heartbeat.DANMAKU_WORK_BUDGET, 90)


if __name__ == "__main__":
    unittest.main()
