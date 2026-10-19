/* Transport and presentation adapters. Business decisions stay in Python. */

function call(method, ...args) {
  const api = window.pywebview?.api;
  if (typeof api?.[method] !== "function") return Promise.reject(new Error("bridge-unavailable"));
  return Promise.resolve(api[method](...args));
}

function bridgeReady() {
  if (window.pywebview?.api) return Promise.resolve(true);
  return new Promise((resolve) => {
    let attempts = 0;
    const timer = window.setInterval(() => {
      if (window.pywebview?.api || ++attempts >= 200) {
        window.clearInterval(timer);
        resolve(Boolean(window.pywebview?.api));
      }
    }, 50);
  });
}

function relativeTime(timestamp) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "尚未更新";
  const delta = Math.max(0, Date.now() / 1000 - timestamp);
  if (delta < 60) return "刚刚";
  if (delta < 3600) return `${Math.floor(delta / 60)} 分钟前`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} 小时前`;
  return new Date(timestamp * 1000).toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

function absoluteTime(timestamp) {
  return timestamp > 0 ? new Date(timestamp * 1000).toLocaleString("zh-CN", { hour12: false }) : "尚未更新";
}

function durationLabel(minutes) {
  if (minutes < 1) return "不到 1 分钟";
  const hours = Math.floor(minutes / 60);
  const remainder = Math.floor(minutes % 60);
  return hours ? `${hours} 小时${remainder ? ` ${remainder} 分钟` : ""}` : `${remainder} 分钟`;
}

function numberLabel(value) {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("zh-CN") : "—";
}

function taskPair(row, words) {
  if (row.tasks_stale) return null;
  const task = (Array.isArray(row.tasks) ? row.tasks : []).find((item) =>
    words.some((word) => String(item.title || "").includes(word))
  );
  if (!task) return null;
  const match = String(task.sub_title || "").match(/(\d+)\s*\/\s*(\d+)/);
  return { current: match ? Number(match[1]) : null, total: match ? Number(match[2]) : null,
    done: Boolean(task.is_done), text: match ? `${match[1]} / ${match[2]}` : task.is_done ? "已完成" : "未完成" };
}

function colorFor(room) {
  const colors = ["#3d7a6c", "#6a5f8f", "#8a7b62", "#7a6270", "#4f6f8a", "#7d6a4f"];
  let hash = 0;
  for (const letter of String(room)) hash = (hash * 31 + letter.charCodeAt(0)) % 997;
  return colors[hash % colors.length];
}

function toRoom(row, snap) {
  const paused = Boolean(snap.paused);
  const protectedAccount = Boolean(snap.safety?.blocked);
  const live = row.live_status === 1;
  const healthy = Boolean(row.heartbeat_healthy && !paused && !protectedAccount);
  const tasks = [
    { key: "danmaku", name: "弹幕", ...taskPair(row, ["弹幕"]) },
    { key: "like", name: "点赞", ...taskPair(row, ["点赞"]) },
    { key: "watch", name: "观看", ...taskPair(row, ["观看", "看播"]) }
  ];
  const lightKnown = Boolean(row.medal_name && !row.tasks_stale);
  tasks.push({ key: "light", name: "粉丝牌", done: lightKnown && row.is_lighted === 1,
    text: lightKnown ? row.is_lighted === 1 ? "已点亮" : "未点亮" : "待更新" });
  let state = "未开播", tone = "muted";
  if (paused) state = "已暂停";
  else if (protectedAccount) { state = "保护暂停"; tone = "warn"; }
  else if (row.reconnecting) state = "正在重连";
  else if (row.heartbeat_stale || row.connection_warning) { state = "连接异常"; tone = "warn"; }
  else if (row.status_error) { state = "查询失败"; tone = "warn"; }
  else if (row.watch_warning) { state = "收益待确认"; tone = "warn"; }
  else if (healthy) { state = "挂机中"; tone = "live"; }
  else if (row.active) state = "正在连接";
  else if (live) state = "等待连接";
  else if (row.live_status == null) state = "等待检查";
  const fallback = "状态尚未确认，更新后可操作";
  return {
    ...row, live, healthy, state, tone, tasks,
    gain: !row.tasks_stale && Number.isFinite(row.intimacy_gain) ? row.intimacy_gain : null,
    minutes: row.started ? Math.max(0, Math.floor((Date.now() / 1000 - row.started) / 60)) : 0,
    initial: Array.from(String(row.name || "?").trim())[0],
    color: colorFor(row.room),
    actions: row.actions || { open: "", redo: fallback, reconnect: fallback, wear: fallback },
    operation: row.operation || {},
    paused, protectedAccount
  };
}

Object.assign(window, { call, bridgeReady, relativeTime, absoluteTime, durationLabel, numberLabel, toRoom, colorFor });
