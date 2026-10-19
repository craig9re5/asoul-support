/* LiveSupport JSX {"code_sha256":"0120f5feaa8dee2b57bb5d664167c45063ed8f5dc3ca7864b4ec0b7c32cd9e2b","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"e774ed3dcaf52bf175bb1ead66127d902fc59b7457073a7dec6ceea54b6806f9","schema":1,"source":"overview.jsx","source_sha256":"2023cafd014eee20753d7817c29f5f47c0e10786e938a54cc9632103fca9e2eb"} */
(function () {
"use strict";
/* Overview and room detail. Labels describe verified state from the engine. */

const {
  Icon,
  relativeTime,
  absoluteTime,
  durationLabel,
  numberLabel
} = window;
const Avatar = ({
  room,
  image
}) => /*#__PURE__*/React.createElement("span", {
  className: "avatar",
  style: {
    background: room.color
  },
  "aria-hidden": "true"
}, image ? /*#__PURE__*/React.createElement("img", {
  src: image,
  alt: ""
}) : room.initial);
const RoomRow = ({
  room,
  selected,
  onSelect,
  onContextMenu,
  image
}) => /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "room",
  role: "option",
  "aria-selected": selected,
  "data-room": room.room,
  onClick: () => onSelect(room.room),
  onDoubleClick: () => window.call("open_room", room.room).catch(() => {}),
  onContextMenu: event => onContextMenu(event, room.room)
}, /*#__PURE__*/React.createElement(Avatar, {
  room: room,
  image: image
}), /*#__PURE__*/React.createElement("span", {
  className: "room-main"
}, /*#__PURE__*/React.createElement("span", {
  className: "room-name"
}, room.live && /*#__PURE__*/React.createElement("i", {
  className: "live-dot",
  title: "\u76F4\u64AD\u4E2D"
}), /*#__PURE__*/React.createElement("span", null, room.name)), room.live && room.title && /*#__PURE__*/React.createElement("span", {
  className: "room-title",
  title: room.title
}, room.title), /*#__PURE__*/React.createElement("span", {
  className: "room-meta"
}, room.healthy && /*#__PURE__*/React.createElement("span", null, "\u5DF2\u8FDE\u63A5 ", durationLabel(room.minutes)), room.healthy && room.gain !== null && /*#__PURE__*/React.createElement("span", {
  className: "sep"
}, "\xB7"), room.gain !== null && /*#__PURE__*/React.createElement("span", null, "\u4ECA\u65E5 +", numberLabel(room.gain)))), room.state !== "未开播" && /*#__PURE__*/React.createElement("span", {
  className: "room-side"
}, /*#__PURE__*/React.createElement("span", {
  className: `pill ${room.tone}`
}, room.state)));
const DetailPanel = ({
  room,
  busy,
  onAction,
  onOpen,
  onRemove,
  image
}) => {
  if (!room) return /*#__PURE__*/React.createElement("aside", {
    className: "detail card",
    "aria-label": "\u76F4\u64AD\u95F4\u8BE6\u60C5"
  }, /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "monitor",
    size: 24
  }), /*#__PURE__*/React.createElement("strong", null, "\u9009\u62E9\u4E00\u4E2A\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("span", null, "\u67E5\u770B\u8FDE\u63A5\u72B6\u6001\u4E0E\u4ECA\u65E5\u4EFB\u52A1")));
  const taskCount = room.tasks.filter(task => task.done).length;
  const reason = room.actions.redo || "";
  const operation = room.operation;
  const pending = busy || operation.pending;
  const knownExperience = !room.tasks_stale && room.next_intimacy > 0;
  const progress = knownExperience ? Math.min(100, Math.max(0, room.intimacy / room.next_intimacy * 100)) : 0;
  const note = room.watch_note || "";
  return /*#__PURE__*/React.createElement("aside", {
    className: "detail card",
    "aria-label": "\u76F4\u64AD\u95F4\u8BE6\u60C5",
    "data-screen-label": `详情 · ${room.name}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-scroll",
    key: room.room
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-heading"
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-identity"
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-name"
  }, room.name), /*#__PURE__*/React.createElement("div", {
    className: "detail-title",
    title: room.title
  }, room.live ? room.title || "直播中" : "等待主播开播")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost icon-button",
    title: "\u66F4\u591A\u64CD\u4F5C",
    "aria-label": "\u66F4\u591A\u64CD\u4F5C",
    onClick: onRemove
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "more",
    size: 17
  }))), /*#__PURE__*/React.createElement("div", {
    className: "state-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: `state-label ${room.tone === "warn" ? "warn" : ""}`
  }, room.state, /*#__PURE__*/React.createElement("span", {
    className: "state-sub",
    title: absoluteTime(room.last_heartbeat)
  }, room.healthy ? `已连接 ${durationLabel(room.minutes)}` : room.live ? "开播后自动建立连接" : "等待主播开播", room.last_heartbeat && room.active ? ` · ${relativeTime(room.last_heartbeat)}同步` : "")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onAction("reconnect", room.room),
    disabled: pending || Boolean(room.actions.reconnect),
    title: room.actions.reconnect || "重新建立看播连接"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "reconnect",
    size: 12,
    className: room.reconnecting ? "spin" : ""
  }), room.reconnecting ? "重连中…" : "重连")), /*#__PURE__*/React.createElement("div", {
    className: "gain-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "gain-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "gain-label"
  }, "\u4ECA\u65E5\u4EB2\u5BC6\u5EA6"), room.medal_name && /*#__PURE__*/React.createElement("span", {
    className: "gain-medal"
  }, room.medal_name, " Lv.", room.medal_level)), /*#__PURE__*/React.createElement("div", {
    className: "gain-value"
  }, room.gain === null ? "—" : `+${numberLabel(room.gain)}`), /*#__PURE__*/React.createElement("div", {
    className: "gain-foot"
  }, /*#__PURE__*/React.createElement("span", null, room.gain === null ? "等待更新" : "已确认到账"), room.day_limit > 0 && /*#__PURE__*/React.createElement("span", null, "\u6BCF\u65E5\u4E0A\u9650 ", numberLabel(room.day_limit))), knownExperience && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "bar thin",
    role: "progressbar",
    "aria-label": "\u7C89\u4E1D\u724C\u5347\u7EA7\u8FDB\u5EA6",
    "aria-valuenow": room.intimacy,
    "aria-valuemin": 0,
    "aria-valuemax": room.next_intimacy
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: `${progress}%`
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "gain-foot"
  }, /*#__PURE__*/React.createElement("span", null, "\u7B49\u7EA7\u7ECF\u9A8C"), /*#__PURE__*/React.createElement("span", {
    className: "tnum"
  }, numberLabel(room.intimacy), " / ", numberLabel(room.next_intimacy))))), (room.connection_warning || room.watch_warning || room.task_error) && /*#__PURE__*/React.createElement("div", {
    className: "notice",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, room.connection_warning || room.watch_warning || room.task_error)), note && /*#__PURE__*/React.createElement("div", {
    className: "notice neutral"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, note)), room.reconnect_message && /*#__PURE__*/React.createElement("div", {
    className: "inline-status",
    role: "status"
  }, room.reconnect_message), /*#__PURE__*/React.createElement("section", {
    className: "block"
  }, /*#__PURE__*/React.createElement("div", {
    className: "block-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "block-title"
  }, "\u4ECA\u65E5\u4EFB\u52A1"), /*#__PURE__*/React.createElement("span", {
    className: "block-note"
  }, room.tasks_stale ? "等待更新" : `${taskCount} 项已完成`)), /*#__PURE__*/React.createElement("div", {
    className: "task-table"
  }, room.tasks.map(task => /*#__PURE__*/React.createElement("div", {
    className: "task",
    key: task.key
  }, /*#__PURE__*/React.createElement("span", {
    className: "task-name"
  }, task.name), /*#__PURE__*/React.createElement("span", {
    className: `task-val ${task.done ? "done" : !task.text ? "pending" : ""}`
  }, task.done && /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 11
  }), task.text || "待更新"))))), /*#__PURE__*/React.createElement("div", {
    className: "detail-secondary-actions"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: () => onAction("wear", room.room),
    disabled: pending || Boolean(room.actions.wear),
    title: room.actions.wear || "佩戴这个主播的粉丝牌"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "medal",
    size: 12
  }), "\u4F69\u6234\u7C89\u4E1D\u724C"), /*#__PURE__*/React.createElement("span", {
    className: "block-note"
  }, "\u4EE5 B \u7AD9\u7ED3\u7B97\u4E3A\u51C6"))), /*#__PURE__*/React.createElement("div", {
    className: "detail-action-area"
  }, operation.message && /*#__PURE__*/React.createElement("p", {
    className: "action-hint",
    role: "status"
  }, operation.message), reason && /*#__PURE__*/React.createElement("p", {
    className: "action-hint"
  }, reason), /*#__PURE__*/React.createElement("div", {
    className: "detail-foot"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: () => onOpen(room.room),
    disabled: Boolean(room.actions.open)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "external",
    size: 13
  }), "\u6253\u5F00\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: () => onAction("redo", room.room),
    disabled: pending || Boolean(reason)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: pending ? "refresh" : "check",
    size: 13,
    className: pending ? "spin" : ""
  }), pending ? "正在处理…" : "补齐任务"))));
};
const Overview = ({
  rooms,
  selectedId,
  onSelect,
  paused,
  onTogglePause,
  onCheck,
  checking,
  summary,
  onAction,
  onOpen,
  onAddMember,
  onSyncMedals,
  onRemove,
  onContextMenu,
  busyRoom,
  controlBusy,
  error,
  recovery,
  onRecovery,
  interval,
  images,
  signedIn,
  closing,
  bridgeConnected
}) => {
  const selected = rooms.find(room => room.room === selectedId);
  const healthy = rooms.filter(room => room.healthy).length;
  const unknown = rooms.filter(room => room.live_status == null).length;
  const status = closing ? "正在退出…" : !bridgeConnected ? "正在连接后台…" : paused ? "已暂停挂机" : !signedIn ? "等待登录" : error ? "需要处理" : healthy ? `${healthy} 个直播间挂机中` : unknown ? "等待检查" : "等待开播";
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "topbar"
  }, /*#__PURE__*/React.createElement("h1", null, "\u76F4\u64AD\u603B\u89C8"), /*#__PURE__*/React.createElement("span", {
    className: "sub"
  }, checking ? "正在检查直播状态…" : summary ? `${summary}检查` : ""), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onAddMember,
    disabled: closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 13
  }), "\u6DFB\u52A0\u4E3B\u64AD"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onCheck,
    disabled: checking || controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13,
    className: checking ? "spin" : ""
  }), checking ? "检查中…" : "立即检查"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: `btn ${paused ? "primary" : ""}`,
    onClick: onTogglePause,
    disabled: controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: paused ? "play" : "pause",
    size: 13
  }), paused ? "恢复挂机" : "暂停挂机")), (error || recovery?.action === "login") && /*#__PURE__*/React.createElement("div", {
    className: "banner",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: recovery?.action === "login" ? "user" : "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, !signedIn ? "登录 B 站，开始自动挂机与每日任务" : error || recovery?.message), recovery?.action && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onRecovery
  }, recovery.label || "查看详情")), /*#__PURE__*/React.createElement("div", {
    className: "workspace"
  }, /*#__PURE__*/React.createElement("section", {
    className: "list card",
    "aria-label": "\u5173\u6CE8\u7684\u76F4\u64AD\u95F4"
  }, /*#__PURE__*/React.createElement("header", {
    className: "list-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "list-title"
  }, "\u5173\u6CE8\u7684\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("span", {
    className: "list-count"
  }, rooms.length), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: onSyncMedals,
    disabled: closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "medal",
    size: 12
  }), "\u540C\u6B65\u7C89\u4E1D\u724C")), /*#__PURE__*/React.createElement("div", {
    className: "rooms",
    role: "listbox",
    "aria-label": "\u76F4\u64AD\u95F4\u5217\u8868"
  }, rooms.length ? rooms.map(room => /*#__PURE__*/React.createElement(RoomRow, {
    key: room.room,
    room: room,
    selected: room.room === selectedId,
    image: images[room.uid],
    onSelect: onSelect,
    onContextMenu: onContextMenu
  })) : /*#__PURE__*/React.createElement("div", {
    className: "empty list-empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "monitor",
    size: 24
  }), /*#__PURE__*/React.createElement("strong", null, "\u8FD8\u6CA1\u6709\u5173\u6CE8\u4E3B\u64AD"), /*#__PURE__*/React.createElement("span", null, "\u6DFB\u52A0\u4E3B\u64AD\u6216\u540C\u6B65\u5DF2\u6709\u7C89\u4E1D\u724C\uFF0C\u5F00\u64AD\u540E\u81EA\u52A8\u5F00\u59CB"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onAddMember
  }, "\u6DFB\u52A0\u4E3B\u64AD")))), /*#__PURE__*/React.createElement(DetailPanel, {
    room: selected,
    busy: busyRoom === selected?.room,
    onAction: onAction,
    onOpen: onOpen,
    onRemove: () => selected && onRemove(selected),
    image: selected && images[selected.uid]
  })), /*#__PURE__*/React.createElement("footer", {
    className: "statusbar"
  }, /*#__PURE__*/React.createElement("span", {
    className: healthy && !closing ? "dot-live" : "dot-paused",
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("strong", null, status), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "low-priority"
  }, "\u6BCF ", interval, " \u5206\u949F\u68C0\u67E5\u4E00\u6B21")));
};
Object.assign(window, {
  Overview,
  Avatar
});
})();
