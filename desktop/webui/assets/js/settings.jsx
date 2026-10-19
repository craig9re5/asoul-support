/* Settings use the same vocabulary as the overview; changes apply through Python. */

const { Icon, relativeTime, absoluteTime } = window;

const Switch = ({ checked, onChange, label, disabled }) => (
  <button type="button" className="switch" role="switch" aria-checked={Boolean(checked)}
    aria-label={label} disabled={disabled} onClick={() => onChange(!checked)} />
);

const SettingRow = ({ name, desc, children }) => (
  <div className="setting"><div className="setting-text"><div className="setting-name">{name}</div>
    {desc && <div className="setting-desc">{desc}</div>}</div>{children}</div>
);

const SettingsPage = ({ settings, onSetting, pendingSettings, notifications }) => {
  const disabled = (key) => pendingSettings.has(key);
  const intervals = [...new Set([5, 10, 15, 30, 60, settings.check_minutes || 30])].sort((a, b) => a - b);
  return (<>
    <header className="topbar"><h1>挂机设置</h1><span className="sub">更改后自动保存</span></header>
    <div className="settings" data-screen-label="挂机设置"><div className="settings-inner">
      <section className="group card">
        <header className="group-head">每日任务<small>开播后，按 B 站的任务进度自动完成</small></header>
        <SettingRow name="点亮粉丝牌" desc="粉丝牌熄灭时发送弹幕，点亮后停止">
          <Switch label="点亮粉丝牌" checked={settings.auto_revive} disabled={disabled("auto_revive")}
            onChange={(value) => onSetting("auto_revive", value)} />
        </SettingRow>
        <SettingRow name="完成弹幕任务" desc="只补齐剩余弹幕，完成后停止">
          <Switch label="完成弹幕任务" checked={settings.auto_danmaku_intimacy} disabled={disabled("auto_danmaku_intimacy")}
            onChange={(value) => onSetting("auto_danmaku_intimacy", value)} />
        </SettingRow>
        <SettingRow name={<>直播点赞 <span className="experimental-label">实验性</span></>} desc="自动点赞并检查任务进度，默认关闭">
          <Switch label="直播点赞" checked={settings.auto_like} disabled={disabled("auto_like")}
            onChange={(value) => onSetting("auto_like", value)} />
        </SettingRow>
      </section>
      <section className="group card">
        <header className="group-head">提醒与启动</header>
        <SettingRow name="开播通知" desc="关注的主播开播时，通过系统通知提醒">
          <Switch label="开播通知" checked={settings.notify_on_live} disabled={disabled("notify_on_live")}
            onChange={(value) => onSetting("notify_on_live", value)} />
        </SettingRow>
        <SettingRow name="开机启动" desc="登录 Windows 后在托盘运行，不打开主窗口">
          <Switch label="开机启动" checked={settings.autostart} disabled={disabled("autostart")}
            onChange={(value) => onSetting("autostart", value)} />
        </SettingRow>
        <SettingRow name="开播检查间隔" desc="间隔越短，发现主播开播越及时">
          <select className="select" value={settings.check_minutes || 30} disabled={disabled("check_minutes")}
            onChange={(event) => onSetting("check_minutes", Number(event.target.value))} aria-label="开播检查间隔">
            {intervals.map((value) => <option key={value} value={value}>{value} 分钟</option>)}
          </select>
        </SettingRow>
      </section>
      {notifications?.experimental && <section className="group card">
        <header className="group-head">手机每日总结 <span className="experimental-label">暂未开放</span></header>
        <div className="setting"><div className="setting-text">
          <div className="setting-desc">尚在验证中，当前不会发送手机通知</div>
        </div><Switch label="手机每日总结" checked={false} disabled /></div>
      </section>}
      <p className="settings-note">更改每日任务后，会按新设置重新建立连接。当天的已完成进度与发送额度会保留。</p>
    </div></div>
  </>);
};

const AccountPage = ({ account, onScan, onLogout, onResumeSafety, onCheck, busy, version }) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const action = !account.signed_in || needsLogin ? onScan : cooldown ? null : hold.blocked ? onResumeSafety : onCheck;
  const actionLabel = !account.signed_in || needsLogin ? "扫码登录" : cooldown ? "等待自动恢复" : hold.blocked ? "确认并恢复" : "检查状态";
  return (<>
    <header className="topbar"><h1>账号</h1><span className="sub">登录与账号保护</span></header>
    <div className="settings" data-screen-label="账号"><div className="settings-inner">
      <section className="group card">
        <header className="group-head">B 站账号</header>
        <div className="setting">
          <span className="account-avatar">{Array.from(account.name || "?")[0]}</span>
          <div className="setting-text">
            <div className="account-name">{account.name || (account.signed_in ? "登录状态待确认" : "尚未登录")}</div>
            <div className="account-meta" title={absoluteTime(account.checked_at)}>
              {account.signed_in ? account.confirmed ? `${relativeTime(account.checked_at)}验证` : "检查状态以验证登录" : "扫码后开始自动挂机与每日任务"}
            </div>
          </div>
          <button type="button" className="btn primary" onClick={onScan} disabled={busy}><Icon name="qr" size={13} />
            {account.signed_in ? "切换账号" : "扫码登录"}</button>
        </div>
        <SettingRow name="登录凭证" desc="加密保存在本机，不会在界面中显示">
          {account.signed_in ? <button type="button" className="btn sm" onClick={onLogout} disabled={busy}>退出登录</button>
            : <span className="block-note">未保存</span>}
        </SettingRow>
      </section>
      <section className="group card">
        <header className="group-head">账号保护</header>
        <SettingRow name={hold.blocked ? "操作已暂停" : account.signed_in ? "未触发保护" : "等待登录"}
          desc={hold.blocked ? hold.reason || "账号出现异常，已暂停互动操作" : "遇到账号异常或请求结果不确定时，自动暂停互动"}>
          <button type="button" className="btn sm" onClick={action || undefined} disabled={!action || busy}>
            <Icon name={needsLogin ? "qr" : "shield"} size={13} />{actionLabel}
          </button>
        </SettingRow>
        {cooldown && <p className="settings-note inside">最早恢复时间：{absoluteTime(hold.until)}。冷却结束后会自动检查。</p>}
      </section>
      <p className="settings-note">LiveSupport {version || ""} · 关闭窗口后继续在托盘运行</p>
    </div></div>
  </>);
};

Object.assign(window, { SettingsPage, AccountPage, Switch, SettingRow });
