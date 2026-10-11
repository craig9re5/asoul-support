from desktop.health import check_progress, recovery_delay, number
from desktop.snapshot import project_snapshot
from asoul_support.application import AppContext
import logging
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from desktop.storage import load_config, read_json, write_json, read_status
from desktop.windows import Job
from asoul_support.runtime import update_json, append_event


def command(*args):
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / "tray_app.py"), *args]


class Engine:

    def __init__(self, root, *, job=None):
        self.root = root
        self.application = AppContext(root)
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.job = job if job is not None else Job()
        self.workers = {}
        self.worker_health = {}
        self.worker_retries = {}
        self.manual_reconnects = {}
        self.started_at = time.time()
        self.last_tick = 0
        self.last_status_publish = 0
        self.publish_error = ""
        self.state_errors = {}
        self.probe = None
        self.probe_path = None
        self.probe_started = 0
        self.next_check = 0
        self.last_check = 0
        self.error = ""
        self.account = ""
        self.account_checked_at = 0
        self.safety = {"blocked": False}
        self.statuses = {}
        self.status_times = {}
        self.status_errors = {}
        self.task_errors = {}
        status = read_status(root)
        self.medals = status.get("medals", {})
        self.tasks = status.get("tasks", {})
        self.known_live = set()
        self.notify_callback = None
        try:
            self.config, self.members = load_config(root)
        except ValueError as exc:
            self.config, self.members = ({"check_minutes": 30}, [])
            self.error = f"配置错误：{exc}"
        self.paused = bool(self.config.get("paused", False))
        self.credentials_signature = self._credentials_signature()
        self.thread = threading.Thread(target=self.run, name="monitor", daemon=True)

    def start(self):
        self.thread.start()

    def _credentials_signature(self):
        path = self.root / "credentials.json"
        if not path.exists():
            return ""
        try:
            value = json.dumps(read_json(path, {}), sort_keys=True).encode("utf-8")
        except (RuntimeError, ValueError):
            value = path.read_bytes()
        return hashlib.sha256(value).hexdigest()

    def reload_settings(self):
        """Apply settings before another worker can continue with an old policy."""
        with self.lock:
            try:
                config, members = load_config(self.root)
                signature = self._credentials_signature()
            except (OSError, ValueError):
                self.stop_children("invalid_config")
                raise
            policy_changed = any(
                (
                    config.get(k) != self.config.get(k)
                    for k in ("auto_revive", "auto_danmaku_intimacy", "auto_like")
                )
            )
            credentials_changed = signature != self.credentials_signature
            changed = config != self.config or members != self.members or credentials_changed
            if policy_changed or credentials_changed:
                self.stop_children("settings_changed")
                self.manual_reconnects.clear()
            if credentials_changed:
                self.account = ""
                self.account_checked_at = 0
                self.medals, self.tasks, self.statuses = ({}, {}, {})
                self.status_times, self.status_errors, self.task_errors = ({}, {}, {})
            keep = {m["room"] for m in members}
            self.manual_reconnects = {room: request for room, request in self.manual_reconnects.items() if room in keep}
            self.worker_retries = {room: retry for room, retry in self.worker_retries.items() if room in keep}
            for room in list(self.workers):
                if room not in keep:
                    proc = self.workers.pop(room)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                    self._record_interruption(room, "member_removed")
            self.config, self.members = (config, members)
            self.credentials_signature = signature
            paused = bool(config.get("paused", False))
            if paused and (not self.paused):
                self.stop_children("paused")
            self.paused = paused
            if changed:
                self.next_check = 0
            return changed

    def spawn(self, *args):
        env = {**os.environ, "ASOUL_APP_DATA": str(self.root), "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(
            command(*args),
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env,
            cwd=str(Path(sys.executable).parent),
        )
        self.job.add(proc)
        return proc

    def stop_children(self, reason="stopped"):
        rooms = list(self.workers)
        processes = list(self.workers.values()) + ([self.probe] if self.probe else [])
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        for room in rooms:
            try:
                self._record_interruption(room, reason)
            except (OSError, ValueError, TimeoutError):
                logging.exception("Cannot record worker interruption")
        self.workers.clear()
        self.worker_health.clear()
        self.probe = None

    def _record_interruption(self, room, reason, expected_pid=None):
        try:
            state = read_json(self.root / "state" / f"{room}.json", {})
        except (OSError, ValueError):
            logging.warning("Cannot read interrupted room state room=%s", room)
            return
        if not isinstance(state, dict) or (expected_pid is not None and state.get("pid") != expected_pid):
            return
        session_id = state.get("session_id")
        if session_id and (not state.get("result")):
            append_event(
                self.root / "logs" / "activity.jsonl",
                {
                    "type": "watch_interrupted",
                    "session_id": session_id,
                    "account_key": state.get("account_key"),
                    "room": room,
                    "member": state.get("name", str(room)),
                    "stopped_reason": reason,
                    "minutes": max(0, int((time.time() - number(state.get("started"), time.time())) / 60)),
                    "beats_ok": state.get("beats", 0),
                    "success": False,
                },
            )

    def set_paused(self, paused):
        with self.lock:
            update_json(
                self.root / "settings.json",
                lambda settings: {**settings, "paused": bool(paused)},
                {},
            )
            self.paused = bool(paused)
            if paused:
                self.stop_children("paused")
                self.error = ""
            else:
                self.next_check = 0
            self.persist()

    def check_now(self):
        with self.lock:
            self.next_check = 0
            self.force_probe = True

    def reconnect_room(self, room):
        """Replace only the selected worker, after a fresh live-status probe."""
        with self.lock:
            if not any(member["room"] == room for member in self.members):
                return False, "该直播间已不在关注列表中。"
            self.safety = self.application.safety_status()
            if self.safety.get("blocked"):
                return False, "账号保护暂停中，请先处理账号异常。"
            if self.paused:
                return False, "挂机已暂停，请先点击恢复挂机。"
            previous = self.manual_reconnects.get(room, {})
            now = time.time()
            if previous.get("cooldown_until", 0) > now:
                return False, "重连请求已提交，请稍后再试。"
            proc = self.workers.get(room)
            if proc:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                self._record_interruption(room, "manual_reconnect", expected_pid=proc.pid)
                self.workers.pop(room, None)
                self.worker_health.pop(room, None)
            self.worker_retries.pop(room, None)
            self.manual_reconnects[room] = {"state": "checking", "requested_at": now,
                                           "cooldown_until": now + 60, "skip_actions": True}
            self.next_check = 0
            self.force_probe = True
            append_event(self.root / "logs/activity.jsonl", {"type": "manual_reconnect", "room": room})
            self.persist()
            return True, "已请求重连，正在确认直播状态；只恢复看播连接。"

    def resume_safety(self, confirmed=False):
        with self.lock:
            ok, message = self.application.resume_safety(confirmed)
            self.safety = self.application.safety_status()
            if ok:
                self.error = ""
                self.next_check = 0
            self.persist()
            return ok, message

    def close(self):
        self.stopping.set()
        with self.lock:
            self.stop_children("exited")
            self.job.close()
            self.persist(exited=True)
        if self.thread.is_alive():
            self.thread.join(timeout=5)

    def _read_room_state(self, room):
        try:
            value = read_json(self.root / "state" / f"{room}.json", {})
            if not isinstance(value, dict):
                raise ValueError("Room state must be an object")
        except (OSError, ValueError) as exc:
            error = type(exc).__name__
            if self.state_errors.get(room) != error:
                logging.warning("Room state unreadable room=%s error=%s", room, error)
            self.state_errors[room] = error
            return {"state_error": "房间状态无法读取，等待重新发布"}
        self.state_errors.pop(room, None)
        health = self.worker_health.get(room)
        if health and value.get("pid") != health["pid"]:
            return {"state_error": "等待当前进程发布状态", "started": self.started_at}
        return value

    def snapshot(self, *, blocking=True):
        if not self.lock.acquire(blocking=blocking):
            return None
        try:
            states = {m["room"]: self._read_room_state(m["room"]) for m in self.members}
            result = project_snapshot(self, states, time.time())
            if self.publish_error:
                result["error"] = "运行快照发布失败：" + self.publish_error
            return result
        finally:
            self.lock.release()

    def persist(self, exited=False):
        write_json(self.root / "status.json", {**self.snapshot(), "exited": exited})
        self.last_status_publish = time.time()

    def cycle(self):
        """A publish failure must not disable scheduling or erase its diagnostics."""
        try:
            self.tick()
            self.last_tick = time.time()
        except Exception as exc:
            logging.exception("Monitor cycle failed")
            self.error = f"配置或运行错误：{type(exc).__name__}"
            self.next_check = time.time() + 60
        try:
            # Recovery clears the previous publication error only after an actual write.
            snapshot = self.snapshot()
            snapshot["error"] = self.error
            write_json(self.root / "status.json", {**snapshot, "exited": False})
            self.last_status_publish = time.time()
            self.publish_error = ""
        except Exception as exc:
            error = type(exc).__name__
            if error != self.publish_error:
                logging.exception("Status publication failed")
            self.publish_error = error
        try:
            write_json(self.root / "monitor-health.json", {
                "pid": os.getpid(), "started": self.started_at, "updated": time.time(),
                "last_tick": self.last_tick, "last_status_publish": self.last_status_publish,
                "publish_error": self.publish_error,
            })
        except OSError:
            logging.warning("Cannot publish monitor health")

    def _watch_workers(self, now):
        clock = time.monotonic()
        for room, proc in list(self.workers.items()):
            if proc.poll() is not None:
                self._record_interruption(room, "worker_exited")
                del self.workers[room]
                self.worker_health.pop(room, None)
                self.next_check = min(self.next_check, now + 300)
                continue
            state = self._read_room_state(room)
            record = self.worker_health.setdefault(room, {
                "pid": proc.pid, "started": clock, "progress": clock,
            })
            if "signature" in record:
                record.setdefault("beat_signature", record["signature"][0])
            record.setdefault("beat_progress", record.get("progress", record["started"]))
            if not check_progress(state, record, clock):
                if state.get("pid") == proc.pid and number(state.get("beats")) >= 5:
                    self.worker_retries.pop(room, None)
                continue
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            del self.workers[room]
            self.worker_health.pop(room, None)
            attempt = self.worker_retries.get(room, {}).get("attempt", 0) + 1
            delay = recovery_delay(attempt)
            self.worker_retries[room] = {"attempt": attempt, "until": clock + delay}
            self._record_interruption(room, "worker_timeout", expected_pid=proc.pid)
            append_event(self.root / "logs/activity.jsonl", {
                "type": "worker_recovery", "room": room, "attempt": attempt,
                "delay": delay, "reason": "progress_timeout",
            })
            self.next_check = min(self.next_check, now + delay)
        for room, retry in self.worker_retries.items():
            if room not in self.workers and self.probe is None:
                self.next_check = min(self.next_check, now + max(0, retry["until"] - clock))

    def tick(self):
        self.reload_settings()
        now = time.time()
        self.safety = self.application.safety_status()
        if self.safety["blocked"]:
            if self.safety.get("kind") in ("auth", "credentials"):
                self.account = ""
                self.account_checked_at = 0
            # IO guards block new writes immediately; let a bounded read finish.
            grace = (
                self.safety.get("kind") == "uncertain" and now - self.safety.get("since", 0) < 20
            )
            if (self.workers or self.probe) and not grace:
                self.stop_children("account_safety")
            self.error = self.safety["reason"]
            self.next_check = self.safety.get("until") or now + 300
            self.force_probe = False
            return
        self._watch_workers(now)
        if self.probe:
            if self.probe.poll() is None and now - self.probe_started > 180:
                self.probe.kill()
                self.probe.wait()
                self.error = "网络检查超时，稍后重试。"
            if self.probe.poll() is not None:
                result = read_json(self.probe_path, {})
                self.probe_path.unlink(missing_ok=True)
                self.probe = None
                self.last_check = now
                self._apply_probe(result, now)
        if (
            not self.probe
            and now >= self.next_check
            and (not self.paused or getattr(self, "force_probe", False))
        ):
            self.force_probe = False
            self.probe_path = self.root / "state" / f"probe-{uuid.uuid4().hex}.json"
            try:
                self.probe = self.spawn("--probe", str(self.probe_path))
            except OSError:
                for request in self.manual_reconnects.values():
                    if request.get("state") == "checking":
                        request.update(state="failed", message="无法启动直播检查，请检查程序安装后重试。")
                raise
            self.probe_started = now
            self.next_check = now + self.config["check_minutes"] * 60

    def run(self):
        while not self.stopping.is_set():
            with self.lock:
                self.cycle()
            self.stopping.wait(1)

    def _apply_probe(self, result, now):
        self.error = result.get("error") or result.get("warning", "")
        if "statuses" not in result:
            for request in self.manual_reconnects.values():
                if request["state"] == "checking":
                    request.update(state="failed", message="重连检查失败，请检查网络后再试。")
            for retry in self.worker_retries.values():
                retry["until"] = max(retry["until"], time.monotonic() + 300)
            self.error = self.error or "检查进程未返回结果，请查看日志。"
            self.status_errors = {str(m["room"]): self.error for m in self.members}
            if result.get("auth_invalid"):
                self.account = ""
                self.account_checked_at = 0
                self.stop_children("auth_invalid")
            self.next_check = now + 300
            return
        self.account = result.get("account", "")
        self.account_checked_at = now
        observed = result.get("observed", now)
        received = {str(k): v for k, v in result["statuses"].items()}
        self.status_errors = {}
        for member in self.members:
            key = str(member["room"])
            if received.get(key, {}).get("live_status") in (0, 1, 2):
                self.status_times[key] = observed
                self.statuses[key] = received[key]
            else:
                self.status_errors[key] = "直播状态查询失败"
        if "medals" in result and isinstance(result["medals"], dict):
            self.medals = result["medals"]
        if "tasks" in result and isinstance(result["tasks"], dict):
            self.tasks.update(result["tasks"])
        self.task_errors = result.get("task_errors", {})
        for member in self.members:
            key = str(member["room"])
            status = received.get(key)
            request = self.manual_reconnects.get(member["room"], {})
            manual = request.get("state") == "checking"
            if manual and observed < request["requested_at"]:
                self.next_check = 0
                continue
            if manual and (not status or status.get("live_status") not in (0, 1, 2)):
                request.update(state="failed", message="直播状态无法确认，请检查网络后重试。")
            if status and status.get("live_status") in (0, 2):
                if request:
                    request.update(state="offline", message="房间已下播，无需重连。", skip_actions=False)
                self.worker_retries.pop(member["room"], None)
            elif not status or status.get("live_status") not in (0, 1, 2):
                retry = self.worker_retries.get(member["room"])
                if retry:
                    retry["until"] = max(retry["until"], time.monotonic() + 300)
            if status and status.get("live_status") == 1:
                if member["room"] not in self.known_live:
                    self.known_live.add(member["room"])
                    if self.config.get("notify_on_live", True) and callable(self.notify_callback):
                        try:
                            self.notify_callback(member["name"], status.get("title", ""))
                        except Exception:
                            logging.exception("Desktop notification failed")
            elif status and status.get("live_status") in (0, 2):
                self.known_live.discard(member["room"])
            if (
                not self.paused
                and not self.safety.get("blocked")
                and status
                and (status.get("live_status") == 1)
                and (member["room"] not in self.workers)
                and time.monotonic() >= self.worker_retries.get(member["room"], {}).get("until", 0)
            ):
                args = ["--worker", key]
                skip_actions = request.get("skip_actions", False)
                if skip_actions:
                    args.append("--watch-only")
                try:
                    proc = self.spawn(*args)
                except OSError:
                    if request:
                        request.update(state="failed", message="无法启动看播连接，请检查程序安装后重试。")
                    self.worker_retries[member["room"]] = {"attempt": 1, "until": time.monotonic() + 60}
                    logging.exception("Cannot start room worker room=%s", member["room"])
                    continue
                self.workers[member["room"]] = proc
                self.worker_health[member["room"]] = {
                    "pid": proc.pid, "started": time.monotonic(), "progress": time.monotonic(),
                }
                if skip_actions:
                    request.update(state="starting", message="已启动新连接，等待成功心跳。")
