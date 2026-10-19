/* LiveSupport JSX {"code_sha256":"3c1dc7bac7b91f366df446459579180794536ca70176acacee2af87945e4e66b","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"e774ed3dcaf52bf175bb1ead66127d902fc59b7457073a7dec6ceea54b6806f9","schema":1,"source":"app.jsx","source_sha256":"114ca44e61dde36a8b56f58f4f9320e8f889defcbc67e2ce486088a86690a863"} */
(function () {
"use strict";
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* One state owner. Python snapshots remain authoritative after every action. */

const {
  useState,
  useEffect,
  useRef,
  useCallback
} = React;
const {
  Icon,
  Pulse,
  call,
  bridgeReady,
  relativeTime,
  toRoom
} = window;
const DEFAULT_SETTINGS = {
  auto_revive: true,
  auto_danmaku_intimacy: true,
  auto_like: false,
  notify_on_live: true,
  check_minutes: 30,
  autostart: false
};
const EMPTY_SNAPSHOT = {
  rows: [],
  paused: false,
  checking: false,
  error: "",
  account: "",
  safety: {},
  settings: DEFAULT_SETTINGS,
  accountInfo: {
    signed_in: false,
    name: "",
    confirmed: false,
    safety: {}
  }
};
const Sidebar = ({
  page,
  onPage,
  account,
  onLogs,
  onQuit
}) => /*#__PURE__*/React.createElement("aside", {
  className: "side"
}, /*#__PURE__*/React.createElement("div", {
  className: "brand"
}, /*#__PURE__*/React.createElement("div", {
  className: "logo"
}, /*#__PURE__*/React.createElement(Pulse, {
  size: 18
})), /*#__PURE__*/React.createElement("div", {
  className: "brand-text"
}, /*#__PURE__*/React.createElement("span", {
  className: "brand-name"
}, "LiveSupport"))), /*#__PURE__*/React.createElement("nav", {
  className: "nav",
  "aria-label": "\u4E3B\u5BFC\u822A"
}, [["monitor", "monitor", "直播总览"], ["automation", "sliders", "挂机设置"], ["account", "user", "账号"]].map(([key, icon, text]) => /*#__PURE__*/React.createElement("button", {
  type: "button",
  key: key,
  className: "nav-item",
  "aria-current": page === key ? "page" : undefined,
  "aria-label": text,
  title: text,
  onClick: () => onPage(key)
}, /*#__PURE__*/React.createElement(Icon, {
  name: icon
}), /*#__PURE__*/React.createElement("span", null, text)))), /*#__PURE__*/React.createElement("div", {
  className: "nav-spacer"
}), /*#__PURE__*/React.createElement("nav", {
  className: "nav nav-bottom",
  "aria-label": "\u5E94\u7528\u64CD\u4F5C"
}, /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "nav-item",
  onClick: onLogs,
  "aria-label": "\u67E5\u770B\u65E5\u5FD7",
  title: "\u67E5\u770B\u65E5\u5FD7"
}, /*#__PURE__*/React.createElement(Icon, {
  name: "folder"
}), /*#__PURE__*/React.createElement("span", null, "\u67E5\u770B\u65E5\u5FD7")), /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "nav-item",
  onClick: onQuit,
  "aria-label": "\u9000\u51FA\u5E94\u7528",
  title: "\u9000\u51FA\u5E94\u7528"
}, /*#__PURE__*/React.createElement(Icon, {
  name: "power"
}), /*#__PURE__*/React.createElement("span", null, "\u9000\u51FA\u5E94\u7528"))), /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "sidebar-account",
  onClick: () => onPage("account"),
  title: "\u8D26\u53F7\u7BA1\u7406"
}, /*#__PURE__*/React.createElement("span", {
  className: "sidebar-avatar"
}, Array.from(account.name || "?")[0]), /*#__PURE__*/React.createElement("span", {
  className: "sidebar-account-text"
}, /*#__PURE__*/React.createElement("strong", null, account.name || (account.signed_in ? "等待验证" : "尚未登录")))));
function App() {
  const [page, setPage] = useState("monitor");
  const [snap, setSnap] = useState(EMPTY_SNAPSHOT);
  const [selectedId, setSelectedId] = useState(null);
  const [connected, setConnected] = useState(false);
  const [controlBusy, setControlBusy] = useState(false);
  const [busyRoom, setBusyRoom] = useState(null);
  const [pendingSettings, setPendingSettings] = useState(new Set());
  const [dialog, setDialog] = useState(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [medals, setMedals] = useState({
    data: [],
    loading: false,
    error: ""
  });
  const [medalSelection, setMedalSelection] = useState(new Set());
  const [qr, setQr] = useState(null);
  const [menu, setMenu] = useState(null);
  const [images, setImages] = useState({});
  const [toasts, setToasts] = useState([]);
  const latest = useRef(EMPTY_SNAPSHOT);
  const selectionInitialized = useRef(false);
  const alive = useRef(true);
  const handlers = useRef({});
  const roomPending = useRef(new Set());
  const settingsQueue = useRef(Promise.resolve());
  const settingOverrides = useRef({});
  const searchGeneration = useRef(0);
  const dialogGeneration = useRef(0);
  const qrRequest = useRef(0);
  const qrOpen = useRef(false);
  const avatarPending = useRef(new Set());
  const toastTimers = useRef(new Set());
  const userSelected = useRef(null);
  const toast = useCallback((text, tone = "info") => {
    if (!text || !alive.current) return;
    const id = Date.now() + Math.random();
    setToasts(items => [...items.slice(-2), {
      id,
      text,
      tone
    }]);
    const timer = window.setTimeout(() => {
      toastTimers.current.delete(timer);
      if (alive.current) setToasts(items => items.filter(item => item.id !== id));
    }, 4800);
    toastTimers.current.add(timer);
  }, []);
  const receiveSnapshot = useCallback(data => {
    if (!data || !alive.current) return;
    latest.current = {
      ...EMPTY_SNAPSHOT,
      ...data,
      settings: {
        ...DEFAULT_SETTINGS,
        ...data.settings
      },
      accountInfo: {
        ...EMPTY_SNAPSHOT.accountInfo,
        ...data.accountInfo,
        safety: data.safety || data.accountInfo?.safety || {}
      }
    };
    setSnap({
      ...latest.current,
      settings: {
        ...latest.current.settings,
        ...settingOverrides.current
      }
    });
    setConnected(true);
  }, []);
  const refresh = async () => {
    try {
      receiveSnapshot(await call("snapshot"));
    } catch {
      toast("无法更新状态，稍后重试", "error");
    }
  };
  useEffect(() => {
    alive.current = true;
    window.LS = {
      onSnapshot: receiveSnapshot,
      onEvent: event => {
        if (!event || !alive.current) return;
        const payload = event.payload || {};
        if (event.type === "qr_state") {
          if (!qrOpen.current) return;
          setQr(current => {
            if (!current || current.generation !== payload.generation) return current;
            return {
              ...current,
              ...payload
            };
          });
        } else if (event.type === "open_login") handlers.current.openQr?.();else if (event.type === "show_page" || event.type === "navigate") {
          if (["monitor", "automation", "account"].includes(payload.page)) setPage(payload.page);
        } else if (event.type === "add_member") handlers.current.openAdd?.();else if (event.type === "sync_medals") handlers.current.openMedals?.();else if (event.type === "toast") toast(payload.message, payload.tone);else if (event.type === "settings_changed") handlers.current.refresh?.();
      }
    };
    bridgeReady().then(async ready => {
      if (!alive.current) return;
      if (!ready) {
        toast("无法连接后台，重启应用后重试", "error");
        return;
      }
      try {
        await call("ready");
        receiveSnapshot(await call("snapshot"));
      } catch {
        toast("无法读取运行状态，重启应用后重试", "error");
      }
    });
    return () => {
      alive.current = false;
      if (window.LS?.onSnapshot === receiveSnapshot) delete window.LS;
      toastTimers.current.forEach(timer => window.clearTimeout(timer));
    };
  }, [receiveSnapshot, toast]);
  useEffect(() => {
    const rows = snap.rows || [];
    if (!selectionInitialized.current && rows.length) {
      selectionInitialized.current = true;
      setSelectedId(rows[0].room);
    } else if (selectedId !== null && !rows.some(row => row.room === selectedId)) setSelectedId(null);
  }, [snap.rows, selectedId]);
  useEffect(() => {
    if (!connected || !snap.accountInfo?.signed_in) return;
    for (const row of snap.rows || []) {
      if (!row.uid || images[row.uid] || avatarPending.current.has(row.uid)) continue;
      avatarPending.current.add(row.uid);
      call("avatar", row.uid).then(result => {
        if (result?.ok && result.data_uri && alive.current) setImages(items => ({
          ...items,
          [row.uid]: result.data_uri
        }));
      }).catch(() => {});
    }
  }, [snap.rows, connected, images]);
  const rooms = (snap.rows || []).map(row => toRoom(row, snap));
  const selected = rooms.find(room => room.room === selectedId);
  const account = snap.accountInfo || EMPTY_SNAPSHOT.accountInfo;
  const closing = Boolean(snap.closing);
  const invoke = async (method, args = [], success = "") => {
    try {
      const result = await call(method, ...args);
      if (result?.ok === false) {
        toast(result.error || result.message || "操作未完成，稍后重试", "warn");
        return result;
      }
      if (result?.warning) toast(result.warning, "warn");else if (result?.message || success) toast(result.message || success);
      return result || {
        ok: true
      };
    } catch {
      toast("无法完成操作，稍后重试", "error");
      return {
        ok: false
      };
    }
  };
  const control = async (method, success = "") => {
    if (controlBusy || closing) return;
    setControlBusy(true);
    try {
      await invoke(method, [], success);
      await refresh();
    } finally {
      if (alive.current) setControlBusy(false);
    }
  };
  const roomAction = async (kind, roomId) => {
    if (roomPending.current.has(roomId) || closing) return;
    roomPending.current.add(roomId);
    setBusyRoom(roomId);
    try {
      await invoke({
        redo: "redo",
        reconnect: "reconnect",
        wear: "wear_medal"
      }[kind], [roomId]);
      await refresh();
    } finally {
      roomPending.current.delete(roomId);
      if (alive.current) setBusyRoom(roomPending.current.values().next().value ?? null);
    }
  };
  const setSetting = (key, value) => {
    settingOverrides.current[key] = value;
    setPendingSettings(current => new Set(current).add(key));
    setSnap(current => ({
      ...current,
      settings: {
        ...current.settings,
        [key]: value
      }
    }));
    settingsQueue.current = settingsQueue.current.catch(() => {}).then(async () => {
      try {
        await invoke("save_settings", [{
          [key]: value
        }]);
        delete settingOverrides.current[key];
        await refresh();
      } finally {
        if (alive.current) setPendingSettings(current => {
          const next = new Set(current);
          next.delete(key);
          return next;
        });
      }
    });
  };
  const closeQr = () => {
    qrOpen.current = false;
    qrRequest.current += 1;
    setQr(null);
    call("qr_cancel").catch(() => {});
  };
  const openQr = async () => {
    qrOpen.current = true;
    const request = ++qrRequest.current;
    setMenu(null);
    setPage("account");
    setQr({
      state: "starting"
    });
    try {
      const result = await call("qr_start");
      if (!alive.current || !qrOpen.current || request !== qrRequest.current) return;
      setQr(result?.ok ? {
        ...result,
        state: "waiting"
      } : {
        state: "error",
        message: result?.error || "无法生成二维码，稍后重试"
      });
    } catch {
      if (qrOpen.current && request === qrRequest.current) setQr({
        state: "error",
        message: "无法连接登录服务，稍后重试"
      });
    }
  };
  const closeDialog = () => {
    if (dialogBusy) return;
    dialogGeneration.current += 1;
    searchGeneration.current += 1;
    setDialog(null);
  };
  const openAdd = () => {
    dialogGeneration.current += 1;
    searchGeneration.current += 1;
    setMenu(null);
    setDialog("add");
    setQuery("");
    setSearchResult(null);
    setSearching(false);
  };
  const onQuery = value => {
    searchGeneration.current += 1;
    setQuery(value);
    setSearchResult(null);
    setSearching(false);
  };
  const search = async () => {
    const generation = ++searchGeneration.current;
    const term = query.trim();
    if (!term) return;
    setSearching(true);
    try {
      const result = await call("resolve_member", term);
      if (alive.current && generation === searchGeneration.current) setSearchResult(result);
    } catch {
      if (generation === searchGeneration.current) setSearchResult({
        ok: false,
        error: "无法查找主播，检查网络后重试"
      });
    } finally {
      if (generation === searchGeneration.current) setSearching(false);
    }
  };
  const add = async () => {
    if (!searchResult?.ok || dialogBusy) return;
    setDialogBusy(true);
    try {
      const result = await invoke("add_member", [query.trim()]);
      if (result?.ok) {
        setDialog(null);
        toast(`已添加 ${result.member?.name || searchResult.member.name}`);
        await refresh();
      } else setSearchResult(result);
    } finally {
      if (alive.current) setDialogBusy(false);
    }
  };
  const openMedals = async () => {
    const generation = ++dialogGeneration.current;
    setMenu(null);
    setDialog("medals");
    setMedals({
      data: [],
      loading: true,
      error: ""
    });
    setMedalSelection(new Set());
    try {
      const result = await call("medals");
      if (!alive.current || generation !== dialogGeneration.current) return;
      const data = result?.medals || [];
      setMedals({
        data,
        loading: false,
        error: result?.ok ? "" : result?.error || "无法读取粉丝牌"
      });
      setMedalSelection(new Set(data.filter(item => !item.watched).map(item => item.uid)));
    } catch {
      if (generation === dialogGeneration.current) setMedals({
        data: [],
        loading: false,
        error: "无法读取粉丝牌，检查网络后重试"
      });
    }
  };
  const importMedals = async () => {
    if (dialogBusy) return;
    setDialogBusy(true);
    try {
      const result = await invoke("import_medals", [[...medalSelection]]);
      if (result?.ok) {
        setDialog(null);
        toast(`已导入 ${result.count} 位主播`);
        await refresh();
      }
    } finally {
      if (alive.current) setDialogBusy(false);
    }
  };
  const confirmAction = async () => {
    if (dialogBusy) return;
    const kind = dialog?.type;
    setDialogBusy(true);
    try {
      let result;
      if (kind === "remove") result = await invoke("remove_member", [dialog.room.room], `已移除 ${dialog.room.name}`);else if (kind === "logout") {
        closeQr();
        result = await invoke("logout", [], "已退出登录");
      } else if (kind === "safety") result = await invoke("resume_safety");else if (kind === "quit") result = await invoke("quit");
      if (result?.ok) {
        setDialog(null);
        if (kind !== "quit") await refresh();
      }
    } finally {
      if (alive.current) setDialogBusy(false);
    }
  };
  const recover = async () => {
    const route = snap.recovery || {};
    if (route.action === "login") openQr();else if (route.action === "resume") control("toggle_pause");else if (route.action === "safety") {
      if (snap.safety?.kind === "auth" || snap.safety?.kind === "credentials") openQr();else if (snap.safety?.until > Date.now() / 1000) {
        setPage("account");
      } else setDialog({
        type: "safety"
      });
    } else if (route.action === "room") {
      setPage("monitor");
      setSelectedId(route.room);
    } else if (route.action === "logs") invoke("open_logs");else if (route.action === "refresh") control("refresh");else control("check_now");
  };
  handlers.current = {
    openQr,
    openAdd,
    openMedals,
    refresh
  };
  const select = id => {
    userSelected.current = id;
    setSelectedId(id);
  };
  const remove = room => {
    setMenu(null);
    setDialog({
      type: "remove",
      room
    });
  };
  const onContextMenu = (event, id) => {
    event.preventDefault();
    select(id);
    setMenu({
      room: id,
      x: event.clientX,
      y: event.clientY
    });
  };
  const dialogCopy = {
    remove: {
      title: "移除主播？",
      desc: `不再对「${dialog?.room?.name || ""}」执行挂机与每日任务。可随时重新添加。`,
      confirmLabel: "移除主播",
      danger: true
    },
    logout: {
      title: "退出 B 站账号？",
      desc: "将停止当前账号的挂机任务，并清除本机登录凭证。当天进度与发送额度会保留。",
      confirmLabel: "退出登录"
    },
    safety: {
      title: "恢复账号操作？",
      desc: "先在 B 站完成验证并确认限制已解除。恢复后会重新检查账号，当天发送额度不会重置。",
      confirmLabel: "确认并恢复"
    },
    quit: {
      title: "退出 LiveSupport？",
      desc: "将停止所有挂机连接。关闭窗口可继续在托盘运行。",
      confirmLabel: "退出应用"
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "app"
  }, /*#__PURE__*/React.createElement(Sidebar, {
    page: page,
    onPage: setPage,
    account: account,
    onLogs: () => invoke("open_logs"),
    onQuit: () => setDialog({
      type: "quit"
    })
  }), /*#__PURE__*/React.createElement("main", {
    className: "main",
    "aria-busy": !connected
  }, page === "monitor" && /*#__PURE__*/React.createElement(window.Overview, {
    rooms: rooms,
    selectedId: selectedId,
    onSelect: select,
    paused: snap.paused,
    onTogglePause: () => control("toggle_pause"),
    onCheck: () => control("check_now"),
    checking: snap.checking,
    summary: snap.last_check ? relativeTime(snap.last_check) : "",
    onAction: roomAction,
    onOpen: id => invoke("open_room", [id]),
    onAddMember: openAdd,
    onSyncMedals: openMedals,
    onRemove: remove,
    onContextMenu: onContextMenu,
    busyRoom: busyRoom,
    controlBusy: controlBusy,
    error: snap.error || snap.ui_error,
    recovery: snap.recovery,
    onRecovery: recover,
    interval: snap.settings?.check_minutes || 30,
    images: images,
    signedIn: account.signed_in,
    closing: closing,
    bridgeConnected: connected
  }), page === "automation" && /*#__PURE__*/React.createElement(window.SettingsPage, {
    settings: snap.settings || DEFAULT_SETTINGS,
    onSetting: setSetting,
    pendingSettings: pendingSettings,
    notifications: snap.notifications
  }), page === "account" && /*#__PURE__*/React.createElement(window.AccountPage, {
    account: account,
    onScan: openQr,
    onLogout: () => setDialog({
      type: "logout"
    }),
    onResumeSafety: () => setDialog({
      type: "safety"
    }),
    onCheck: () => control("check_now"),
    busy: controlBusy || closing,
    version: snap.version
  })), /*#__PURE__*/React.createElement("div", {
    className: "toasts",
    "aria-live": "polite"
  }, toasts.map(item => /*#__PURE__*/React.createElement("div", {
    key: item.id,
    className: `toast ${item.tone}`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: item.tone === "info" ? "check" : "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, item.text)))), qr && /*#__PURE__*/React.createElement(window.QrModal, {
    qr: qr,
    onClose: closeQr,
    onRetry: openQr
  }), dialog === "add" && /*#__PURE__*/React.createElement(window.AddMemberModal, {
    query: query,
    onQuery: onQuery,
    result: searchResult,
    loading: searching,
    adding: dialogBusy,
    onSearch: search,
    onAdd: add,
    onClose: closeDialog
  }), dialog === "medals" && /*#__PURE__*/React.createElement(window.MedalsModal, {
    data: medals.data,
    loading: medals.loading,
    error: medals.error,
    selected: medalSelection,
    onToggle: uid => setMedalSelection(current => {
      const next = new Set(current);
      if (next.has(uid)) next.delete(uid);else next.add(uid);
      return next;
    }),
    onImport: importMedals,
    importing: dialogBusy,
    onClose: closeDialog,
    onRetry: openMedals
  }), dialog?.type && /*#__PURE__*/React.createElement(window.ConfirmModal, _extends({}, dialogCopy[dialog.type], {
    onConfirm: confirmAction,
    onClose: closeDialog,
    busy: dialogBusy
  })), menu && /*#__PURE__*/React.createElement(window.RoomMenu, {
    menu: menu,
    room: rooms.find(room => room.room === menu.room),
    onClose: () => setMenu(null),
    onOpen: id => invoke("open_room", [id]),
    onAction: roomAction,
    onRemove: remove
  }));
}
ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(App, null));
})();
