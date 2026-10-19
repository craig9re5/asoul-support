/* LiveSupport JSX {"code_sha256":"b7c58f780963a313a8d4f82aac92ef106b1e7ee0668e2b4d4d0fa53f3b13a2ba","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"e774ed3dcaf52bf175bb1ead66127d902fc59b7457073a7dec6ceea54b6806f9","schema":1,"source":"settings.jsx","source_sha256":"336878c84dc9f9167170c725ef0afeecde6822d3a96bd5a225b83be7cfefa0a8"} */
(function () {
"use strict";
/* Settings use the same vocabulary as the overview; changes apply through Python. */

const {
  Icon,
  relativeTime,
  absoluteTime
} = window;
const Switch = ({
  checked,
  onChange,
  label,
  disabled
}) => /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "switch",
  role: "switch",
  "aria-checked": Boolean(checked),
  "aria-label": label,
  disabled: disabled,
  onClick: () => onChange(!checked)
});
const SettingRow = ({
  name,
  desc,
  children
}) => /*#__PURE__*/React.createElement("div", {
  className: "setting"
}, /*#__PURE__*/React.createElement("div", {
  className: "setting-text"
}, /*#__PURE__*/React.createElement("div", {
  className: "setting-name"
}, name), desc && /*#__PURE__*/React.createElement("div", {
  className: "setting-desc"
}, desc)), children);
const SettingsPage = ({
  settings,
  onSetting,
  pendingSettings,
  notifications
}) => {
  const disabled = key => pendingSettings.has(key);
  const intervals = [...new Set([5, 10, 15, 30, 60, settings.check_minutes || 30])].sort((a, b) => a - b);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "topbar"
  }, /*#__PURE__*/React.createElement("h1", null, "\u6302\u673A\u8BBE\u7F6E"), /*#__PURE__*/React.createElement("span", {
    className: "sub"
  }, "\u66F4\u6539\u540E\u81EA\u52A8\u4FDD\u5B58")), /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u6302\u673A\u8BBE\u7F6E"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u6BCF\u65E5\u4EFB\u52A1", /*#__PURE__*/React.createElement("small", null, "\u5F00\u64AD\u540E\uFF0C\u6309 B \u7AD9\u7684\u4EFB\u52A1\u8FDB\u5EA6\u81EA\u52A8\u5B8C\u6210")), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    desc: "\u7C89\u4E1D\u724C\u7184\u706D\u65F6\u53D1\u9001\u5F39\u5E55\uFF0C\u70B9\u4EAE\u540E\u505C\u6B62"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    checked: settings.auto_revive,
    disabled: disabled("auto_revive"),
    onChange: value => onSetting("auto_revive", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    desc: "\u53EA\u8865\u9F50\u5269\u4F59\u5F39\u5E55\uFF0C\u5B8C\u6210\u540E\u505C\u6B62"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    checked: settings.auto_danmaku_intimacy,
    disabled: disabled("auto_danmaku_intimacy"),
    onChange: value => onSetting("auto_danmaku_intimacy", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: /*#__PURE__*/React.createElement(React.Fragment, null, "\u76F4\u64AD\u70B9\u8D5E ", /*#__PURE__*/React.createElement("span", {
      className: "experimental-label"
    }, "\u5B9E\u9A8C\u6027")),
    desc: "\u81EA\u52A8\u70B9\u8D5E\u5E76\u68C0\u67E5\u4EFB\u52A1\u8FDB\u5EA6\uFF0C\u9ED8\u8BA4\u5173\u95ED"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u76F4\u64AD\u70B9\u8D5E",
    checked: settings.auto_like,
    disabled: disabled("auto_like"),
    onChange: value => onSetting("auto_like", value)
  }))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u63D0\u9192\u4E0E\u542F\u52A8"), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F00\u64AD\u901A\u77E5",
    desc: "\u5173\u6CE8\u7684\u4E3B\u64AD\u5F00\u64AD\u65F6\uFF0C\u901A\u8FC7\u7CFB\u7EDF\u901A\u77E5\u63D0\u9192"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u64AD\u901A\u77E5",
    checked: settings.notify_on_live,
    disabled: disabled("notify_on_live"),
    onChange: value => onSetting("notify_on_live", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F00\u673A\u542F\u52A8",
    desc: "\u767B\u5F55 Windows \u540E\u5728\u6258\u76D8\u8FD0\u884C\uFF0C\u4E0D\u6253\u5F00\u4E3B\u7A97\u53E3"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u673A\u542F\u52A8",
    checked: settings.autostart,
    disabled: disabled("autostart"),
    onChange: value => onSetting("autostart", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F00\u64AD\u68C0\u67E5\u95F4\u9694",
    desc: "\u95F4\u9694\u8D8A\u77ED\uFF0C\u53D1\u73B0\u4E3B\u64AD\u5F00\u64AD\u8D8A\u53CA\u65F6"
  }, /*#__PURE__*/React.createElement("select", {
    className: "select",
    value: settings.check_minutes || 30,
    disabled: disabled("check_minutes"),
    onChange: event => onSetting("check_minutes", Number(event.target.value)),
    "aria-label": "\u5F00\u64AD\u68C0\u67E5\u95F4\u9694"
  }, intervals.map(value => /*#__PURE__*/React.createElement("option", {
    key: value,
    value: value
  }, value, " \u5206\u949F"))))), notifications?.experimental && /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u624B\u673A\u6BCF\u65E5\u603B\u7ED3 ", /*#__PURE__*/React.createElement("span", {
    className: "experimental-label"
  }, "\u6682\u672A\u5F00\u653E")), /*#__PURE__*/React.createElement("div", {
    className: "setting"
  }, /*#__PURE__*/React.createElement("div", {
    className: "setting-text"
  }, /*#__PURE__*/React.createElement("div", {
    className: "setting-desc"
  }, "\u5C1A\u5728\u9A8C\u8BC1\u4E2D\uFF0C\u5F53\u524D\u4E0D\u4F1A\u53D1\u9001\u624B\u673A\u901A\u77E5")), /*#__PURE__*/React.createElement(Switch, {
    label: "\u624B\u673A\u6BCF\u65E5\u603B\u7ED3",
    checked: false,
    disabled: true
  }))), /*#__PURE__*/React.createElement("p", {
    className: "settings-note"
  }, "\u66F4\u6539\u6BCF\u65E5\u4EFB\u52A1\u540E\uFF0C\u4F1A\u6309\u65B0\u8BBE\u7F6E\u91CD\u65B0\u5EFA\u7ACB\u8FDE\u63A5\u3002\u5F53\u5929\u7684\u5DF2\u5B8C\u6210\u8FDB\u5EA6\u4E0E\u53D1\u9001\u989D\u5EA6\u4F1A\u4FDD\u7559\u3002"))));
};
const AccountPage = ({
  account,
  onScan,
  onLogout,
  onResumeSafety,
  onCheck,
  busy,
  version
}) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const action = !account.signed_in || needsLogin ? onScan : cooldown ? null : hold.blocked ? onResumeSafety : onCheck;
  const actionLabel = !account.signed_in || needsLogin ? "扫码登录" : cooldown ? "等待自动恢复" : hold.blocked ? "确认并恢复" : "检查状态";
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("header", {
    className: "topbar"
  }, /*#__PURE__*/React.createElement("h1", null, "\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", {
    className: "sub"
  }, "\u767B\u5F55\u4E0E\u8D26\u53F7\u4FDD\u62A4")), /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u8D26\u53F7"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "B \u7AD9\u8D26\u53F7"), /*#__PURE__*/React.createElement("div", {
    className: "setting"
  }, /*#__PURE__*/React.createElement("span", {
    className: "account-avatar"
  }, Array.from(account.name || "?")[0]), /*#__PURE__*/React.createElement("div", {
    className: "setting-text"
  }, /*#__PURE__*/React.createElement("div", {
    className: "account-name"
  }, account.name || (account.signed_in ? "登录状态待确认" : "尚未登录")), /*#__PURE__*/React.createElement("div", {
    className: "account-meta",
    title: absoluteTime(account.checked_at)
  }, account.signed_in ? account.confirmed ? `${relativeTime(account.checked_at)}验证` : "检查状态以验证登录" : "扫码后开始自动挂机与每日任务")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: onScan,
    disabled: busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "qr",
    size: 13
  }), account.signed_in ? "切换账号" : "扫码登录")), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u767B\u5F55\u51ED\u8BC1",
    desc: "\u52A0\u5BC6\u4FDD\u5B58\u5728\u672C\u673A\uFF0C\u4E0D\u4F1A\u5728\u754C\u9762\u4E2D\u663E\u793A"
  }, account.signed_in ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onLogout,
    disabled: busy
  }, "\u9000\u51FA\u767B\u5F55") : /*#__PURE__*/React.createElement("span", {
    className: "block-note"
  }, "\u672A\u4FDD\u5B58"))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u8D26\u53F7\u4FDD\u62A4"), /*#__PURE__*/React.createElement(SettingRow, {
    name: hold.blocked ? "操作已暂停" : account.signed_in ? "未触发保护" : "等待登录",
    desc: hold.blocked ? hold.reason || "账号出现异常，已暂停互动操作" : "遇到账号异常或请求结果不确定时，自动暂停互动"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: action || undefined,
    disabled: !action || busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: needsLogin ? "qr" : "shield",
    size: 13
  }), actionLabel)), cooldown && /*#__PURE__*/React.createElement("p", {
    className: "settings-note inside"
  }, "\u6700\u65E9\u6062\u590D\u65F6\u95F4\uFF1A", absoluteTime(hold.until), "\u3002\u51B7\u5374\u7ED3\u675F\u540E\u4F1A\u81EA\u52A8\u68C0\u67E5\u3002")), /*#__PURE__*/React.createElement("p", {
    className: "settings-note"
  }, "LiveSupport ", version || "", " \xB7 \u5173\u95ED\u7A97\u53E3\u540E\u7EE7\u7EED\u5728\u6258\u76D8\u8FD0\u884C"))));
};
Object.assign(window, {
  SettingsPage,
  AccountPage,
  Switch,
  SettingRow
});
})();
