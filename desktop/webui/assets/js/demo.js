/* Development preview only. Never imported by production index.html or frozen builds. */
(function () {
  const now = Date.now() / 1000;
  const task = (title, current, total) => ({ title, sub_title: `${current} / ${total}`, is_done: current >= total });
  const rows = [
    { name: "嘉然今天吃什么", room: 22637261, uid: 101, title: "今天也要开开心心地直播", live_status: 1,
      active: true, heartbeat_healthy: true, started: now - 2520, last_heartbeat: now - 12, beats: 41,
      medal_name: "小草莓", medal_level: 9, is_lighted: 1, intimacy_gain: 15, day_limit: 1500,
      intimacy: 1280, next_intimacy: 3000,
      tasks: [task("发送弹幕", 5, 5), task("直播点赞", 8, 10), task("观看直播", 30, 30)] },
    { name: "贝拉kira", room: 22625025, uid: 102, title: "周末一起打游戏", live_status: 1,
      active: true, heartbeat_healthy: true, started: now - 480, last_heartbeat: now - 29, beats: 7,
      medal_name: "贝极星", medal_level: 7, is_lighted: 1, intimacy_gain: 5, day_limit: 1500,
      intimacy: 640, next_intimacy: 2000,
      tasks: [task("发送弹幕", 5, 5), task("直播点赞", 3, 10), task("观看直播", 12, 30)] },
    { name: "向晚大魔王", room: 22632424, uid: 103, title: "", live_status: 0,
      active: false, heartbeat_healthy: false, tasks_stale: true, medal_name: "顶碗人", medal_level: 6,
      intimacy_gain: null, tasks: [] },
    { name: "乃琳Queen", room: 22637255, uid: 104, title: "新一周，一起慢慢来", live_status: 1,
      active: true, heartbeat_healthy: true, started: now - 1380, last_heartbeat: now - 10, beats: 22,
      medal_name: "奶淇琳", medal_level: 8, is_lighted: 1, intimacy_gain: 12, day_limit: 1500,
      intimacy: 980, next_intimacy: 2400,
      watch_note: "多个直播间同时挂机时，收益会依次结算。当前连接正常，继续等待即可。",
      tasks: [task("发送弹幕", 4, 5), task("直播点赞", 10, 10), task("观看直播", 24, 30)] }
  ];
  const state = {
    rows, paused: false, checking: false, last_check: now - 120, version: "2026.10.18.3",
    account: "示例账号", account_confirmed: true, account_checked_at: now - 120,
    safety: { blocked: false }, error: "", running: true,
    settings: { auto_revive: true, auto_danmaku_intimacy: true, auto_like: false, notify_on_live: true, check_minutes: 30, autostart: false },
    accountInfo: { signed_in: true, name: "示例账号", confirmed: true, checked_at: now - 120, safety: { blocked: false } },
    notifications: { available: false, experimental: true }
  };
  let qrGeneration = 0;
  function publish() {
    state.updated = Date.now() / 1000;
    for (const row of rows) {
      row.actions = { open: "", redo: state.paused ? "恢复挂机后可补齐任务" : row.live_status !== 1 ? "主播开播后可补齐任务" : "",
        reconnect: state.paused ? "恢复挂机后可重连" : row.live_status !== 1 ? "当前无需重连" : "", wear: row.medal_name ? "" : "还没有粉丝牌" };
      if (!row.operation) row.operation = {};
    }
    window.LS?.onSnapshot(JSON.parse(JSON.stringify(state)));
  }
  function action(id, kind) {
    const row = rows.find((item) => item.room === id);
    row.operation = { pending: true, kind, message: kind === "redo" ? "正在核对任务进度…" : "正在重新建立连接…" };
    publish();
    return new Promise((resolve) => window.setTimeout(() => {
      row.operation = { pending: false, kind, message: kind === "redo" ? "今日任务已完成" : "连接已恢复" };
      if (kind === "redo") row.tasks = [task("发送弹幕", 5, 5), task("直播点赞", 10, 10), task("观看直播", 30, 30)];
      row.last_heartbeat = Date.now() / 1000;
      publish(); resolve({ ok: true, message: row.operation.message });
    }, 700));
  }
  window.pywebview = { api: {
    ready() { publish(); return { ok: true }; },
    snapshot() { return JSON.parse(JSON.stringify(state)); },
    avatar() { return { ok: false }; },
    toggle_pause() { state.paused = !state.paused; publish(); return { ok: true, message: state.paused ? "已暂停挂机" : "已恢复挂机" }; },
    check_now() { state.checking = true; publish(); window.setTimeout(() => { state.checking = false; state.last_check = Date.now() / 1000; publish(); }, 650); return { ok: true }; },
    save_settings(changes) { Object.assign(state.settings, changes); publish(); return { ok: true }; },
    redo(id) { return action(id, "redo"); }, reconnect(id) { return action(id, "reconnect"); },
    wear_medal() { return { ok: true, message: "已佩戴粉丝牌" }; },
    open_room() { return { ok: true, message: "预览模式不会打开外部直播间" }; },
    open_logs() { return { ok: true, message: "桌面版会打开本机日志目录" }; },
    resolve_member(query) { return query.trim() ? { ok: true, member: { name: "示例主播", room: 123456, uid: 105 } } : { ok: false, error: "输入直播间号或链接后查找" }; },
    add_member() { rows.push({ name: "示例主播", room: 123456, uid: 105, live_status: 0, active: false, tasks_stale: true, tasks: [] }); publish(); return { ok: true, member: rows[rows.length - 1] }; },
    medals() { return { ok: true, medals: [{ name: "示例主播", medal_name: "同行者", uid: 105, level: 7, watched: false }] }; },
    import_medals() { return { ok: true, count: 1 }; },
    remove_member(id) { const index = rows.findIndex((item) => item.room === id); if (index >= 0) rows.splice(index, 1); publish(); return { ok: true }; },
    qr_start() { qrGeneration += 1; return { ok: false, generation: qrGeneration, error: "当前为界面预览。桌面版会显示可扫描的登录二维码。" }; },
    qr_cancel() { qrGeneration += 1; return { ok: true }; },
    logout() { state.account = ""; state.accountInfo = { signed_in: false, name: "", confirmed: false, safety: {} }; state.paused = true;
      state.recovery = { action: "login", label: "扫码登录" }; publish(); return { ok: true }; },
    resume_safety() { state.safety = { blocked: false }; publish(); return { ok: true }; },
    refresh() { publish(); return { ok: true }; },
    quit() { return { ok: false, error: "这是浏览器预览，关闭标签页即可" }; }
  } };
})();
