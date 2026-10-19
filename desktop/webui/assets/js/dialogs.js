/* LiveSupport JSX {"code_sha256":"b97a8be855aa1b9f6fc3673717cbfe574de46e7d21da5d0b75142265f429af09","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"e774ed3dcaf52bf175bb1ead66127d902fc59b7457073a7dec6ceea54b6806f9","schema":1,"source":"dialogs.jsx","source_sha256":"9dcaf81b3d0f1ed2608d51d134d63cbd8407a1388efdd9411b666e9ce158e7de"} */
(function () {
"use strict";
/* Dialogs keep focus inside the active view and restore it on close. */

const {
  Icon
} = window;
const {
  useEffect,
  useRef
} = React;
function Modal({
  title,
  desc,
  children,
  actions,
  onClose,
  wide
}) {
  const element = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const node = element.current;
    const items = () => [...node.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex="0"]')];
    (node.querySelector("[autofocus]") || items()[0] || node).focus();
    const keydown = event => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
      }
      if (event.key !== "Tab") return;
      const controls = items();
      if (!controls.length) {
        event.preventDefault();
        return;
      }
      const first = controls[0],
        last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    node.addEventListener("keydown", keydown);
    return () => {
      node.removeEventListener("keydown", keydown);
      previous?.focus?.();
    };
  }, []);
  return /*#__PURE__*/React.createElement("div", {
    className: "scrim",
    onMouseDown: event => event.target === event.currentTarget && onClose()
  }, /*#__PURE__*/React.createElement("section", {
    className: `modal ${wide ? "wide" : ""}`,
    role: "dialog",
    "aria-modal": "true",
    "aria-label": title,
    ref: element,
    tabIndex: -1
  }, /*#__PURE__*/React.createElement("h3", null, title), desc && /*#__PURE__*/React.createElement("p", null, desc), children, actions && /*#__PURE__*/React.createElement("div", {
    className: "modal-actions"
  }, actions)));
}
const QrModal = ({
  qr,
  onClose,
  onRetry
}) => {
  const messages = {
    starting: "正在生成二维码…",
    waiting: "等待扫码",
    scanned: "已扫码，在手机上确认登录",
    confirmed: "登录已确认",
    expired: "二维码已过期，刷新后重新扫描",
    error: qr.message || "无法连接登录服务，稍后重试"
  };
  return /*#__PURE__*/React.createElement(Modal, {
    title: qr.state === "confirmed" ? "已登录" : "扫码登录 B 站",
    desc: qr.state === "confirmed" ? qr.account : "使用 B 站 App 扫码，并在手机上确认",
    onClose: onClose,
    actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn",
      onClick: onClose
    }, qr.state === "confirmed" ? "完成" : "取消"), qr.state !== "confirmed" && /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn primary",
      onClick: onRetry,
      disabled: qr.state === "starting"
    }, "\u5237\u65B0\u4E8C\u7EF4\u7801"))
  }, /*#__PURE__*/React.createElement("div", {
    className: `qr-wrap ${qr.state === "expired" ? "expired" : ""}`
  }, qr.data_uri ? /*#__PURE__*/React.createElement("img", {
    src: qr.data_uri,
    alt: "B \u7AD9\u767B\u5F55\u4E8C\u7EF4\u7801"
  }) : /*#__PURE__*/React.createElement("span", {
    className: "qr-placeholder"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: qr.state === "error" ? "alert" : "refresh",
    size: 24,
    className: qr.state === "starting" ? "spin" : ""
  }))), /*#__PURE__*/React.createElement("div", {
    className: "qr-hint",
    role: "status"
  }, messages[qr.state]));
};
const AddMemberModal = ({
  query,
  onQuery,
  result,
  loading,
  adding,
  onSearch,
  onAdd,
  onClose
}) => /*#__PURE__*/React.createElement(Modal, {
  title: "\u6DFB\u52A0\u4E3B\u64AD",
  desc: "\u901A\u8FC7\u76F4\u64AD\u95F4\u53F7\u3001UID \u6216\u76F4\u64AD\u95F4\u94FE\u63A5\u67E5\u627E",
  onClose: onClose,
  actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onClose
  }, "\u53D6\u6D88"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: onAdd,
    disabled: !result?.ok || loading || adding
  }, adding ? "正在添加…" : "添加主播"))
}, /*#__PURE__*/React.createElement("form", {
  className: "field-row",
  onSubmit: event => {
    event.preventDefault();
    if (!loading && query.trim()) onSearch();
  }
}, /*#__PURE__*/React.createElement("input", {
  className: "input",
  value: query,
  onChange: event => onQuery(event.target.value),
  "aria-label": "\u76F4\u64AD\u95F4\u53F7\u3001UID \u6216\u94FE\u63A5",
  placeholder: "\u76F4\u64AD\u95F4\u53F7\u3001UID \u6216\u94FE\u63A5",
  autoFocus: true,
  disabled: adding
}), /*#__PURE__*/React.createElement("button", {
  type: "submit",
  className: "btn",
  disabled: loading || adding || !query.trim()
}, loading ? "查找中…" : "查找")), result?.ok && /*#__PURE__*/React.createElement("div", {
  className: "member-preview"
}, /*#__PURE__*/React.createElement("span", {
  className: "account-avatar"
}, Array.from(result.member.name || "?")[0]), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
  className: "account-name"
}, result.member.name), /*#__PURE__*/React.createElement("div", {
  className: "account-meta"
}, "\u76F4\u64AD\u95F4 ", result.member.room, " \xB7 UID ", result.member.uid))), result && !result.ok && /*#__PURE__*/React.createElement("div", {
  className: "field-error",
  role: "alert"
}, result.error));
const MedalsModal = ({
  data,
  selected,
  onToggle,
  onImport,
  onClose,
  loading,
  importing,
  error,
  onRetry
}) => /*#__PURE__*/React.createElement(Modal, {
  title: "\u540C\u6B65\u7C89\u4E1D\u724C",
  desc: "\u9009\u62E9\u8981\u5173\u6CE8\u7684\u4E3B\u64AD\uFF0C\u5DF2\u5173\u6CE8\u7684\u4E3B\u64AD\u4F1A\u81EA\u52A8\u8DF3\u8FC7",
  wide: true,
  onClose: onClose,
  actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onClose
  }, "\u53D6\u6D88"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: onImport,
    disabled: loading || importing || selected.size === 0 || Boolean(error)
  }, importing ? "正在导入…" : selected.size ? `导入 ${selected.size} 位主播` : "导入主播"))
}, /*#__PURE__*/React.createElement("div", {
  className: "medal-list"
}, loading ? /*#__PURE__*/React.createElement("div", {
  className: "field-note"
}, "\u6B63\u5728\u8BFB\u53D6\u7C89\u4E1D\u724C\u2026") : error ? /*#__PURE__*/React.createElement("div", {
  className: "field-note"
}, /*#__PURE__*/React.createElement("p", null, error), /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "btn sm",
  onClick: onRetry
}, "\u91CD\u8BD5")) : !data.length ? /*#__PURE__*/React.createElement("div", {
  className: "field-note"
}, "\u6682\u65E0\u53EF\u540C\u6B65\u7684\u7C89\u4E1D\u724C") : data.map(medal => /*#__PURE__*/React.createElement("label", {
  key: medal.uid,
  className: `medal-row ${medal.watched ? "watched" : ""}`
}, /*#__PURE__*/React.createElement("input", {
  type: "checkbox",
  checked: selected.has(medal.uid),
  disabled: medal.watched || importing,
  onChange: () => onToggle(medal.uid)
}), /*#__PURE__*/React.createElement("span", {
  className: "account-avatar small"
}, Array.from(medal.name || medal.medal_name || "?")[0]), /*#__PURE__*/React.createElement("span", {
  className: "medal-main"
}, /*#__PURE__*/React.createElement("span", {
  className: "account-name"
}, medal.name || medal.medal_name), /*#__PURE__*/React.createElement("span", {
  className: "account-meta"
}, medal.medal_name, " Lv.", medal.level, medal.watched ? " · 已关注" : ""))))));
const ConfirmModal = ({
  title,
  desc,
  confirmLabel,
  danger,
  onConfirm,
  onClose,
  busy
}) => /*#__PURE__*/React.createElement(Modal, {
  title: title,
  desc: desc,
  onClose: onClose,
  actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onClose,
    disabled: busy
  }, "\u53D6\u6D88"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: `btn ${danger ? "danger" : "primary"}`,
    onClick: onConfirm,
    disabled: busy
  }, busy ? "正在处理…" : confirmLabel))
});
const RoomMenu = ({
  menu,
  room,
  onClose,
  onOpen,
  onAction,
  onRemove
}) => {
  const ref = useRef(null);
  useEffect(() => {
    const close = event => {
      if (!ref.current?.contains(event.target)) onClose();
    };
    const key = event => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", key);
    };
  }, [onClose]);
  if (!room) return null;
  const invoke = fn => {
    onClose();
    fn();
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "room-menu",
    role: "menu",
    ref: ref,
    style: {
      left: Math.min(menu.x, window.innerWidth - 200),
      top: Math.min(menu.y, window.innerHeight - 200)
    }
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    onClick: () => invoke(() => onOpen(room.room))
  }, "\u6253\u5F00\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    disabled: Boolean(room.actions.reconnect) || room.operation.pending,
    title: room.actions.reconnect,
    onClick: () => invoke(() => onAction("reconnect", room.room))
  }, "\u91CD\u65B0\u8FDE\u63A5"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    disabled: Boolean(room.actions.redo) || room.operation.pending,
    title: room.actions.redo,
    onClick: () => invoke(() => onAction("redo", room.room))
  }, "\u8865\u9F50\u4EFB\u52A1"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    disabled: Boolean(room.actions.wear) || room.operation.pending,
    title: room.actions.wear,
    onClick: () => invoke(() => onAction("wear", room.room))
  }, "\u4F69\u6234\u7C89\u4E1D\u724C"), /*#__PURE__*/React.createElement("div", {
    className: "menu-divider"
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    className: "destructive-text",
    onClick: () => invoke(() => onRemove(room))
  }, "\u79FB\u9664\u4E3B\u64AD"));
};
Object.assign(window, {
  Modal,
  QrModal,
  AddMemberModal,
  MedalsModal,
  ConfirmModal,
  RoomMenu
});
})();
