/* Dialogs keep focus inside the active view and restore it on close. */

const { Icon } = window;
const { useEffect, useRef } = React;

function Modal({ title, desc, children, actions, onClose, wide }) {
  const element = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const node = element.current;
    const items = () => [...node.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex="0"]')];
    (node.querySelector("[autofocus]") || items()[0] || node).focus();
    const keydown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const controls = items();
      if (!controls.length) { event.preventDefault(); return; }
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    };
    node.addEventListener("keydown", keydown);
    return () => { node.removeEventListener("keydown", keydown); previous?.focus?.(); };
  }, []);
  return (
    <div className="scrim" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true"
        aria-label={title} ref={element} tabIndex={-1}>
        <h3>{title}</h3>{desc && <p>{desc}</p>}{children}
        {actions && <div className="modal-actions">{actions}</div>}
      </section>
    </div>
  );
}

const QrModal = ({ qr, onClose, onRetry }) => {
  const messages = {
    starting: "正在生成二维码…", waiting: "等待扫码", scanned: "已扫码，在手机上确认登录",
    confirmed: "登录已确认", expired: "二维码已过期，刷新后重新扫描", error: qr.message || "无法连接登录服务，稍后重试"
  };
  return (
    <Modal title={qr.state === "confirmed" ? "已登录" : "扫码登录 B 站"}
      desc={qr.state === "confirmed" ? qr.account : "使用 B 站 App 扫码，并在手机上确认"} onClose={onClose}
      actions={<>
        <button type="button" className="btn" onClick={onClose}>{qr.state === "confirmed" ? "完成" : "取消"}</button>
        {qr.state !== "confirmed" && <button type="button" className="btn primary" onClick={onRetry} disabled={qr.state === "starting"}>
          刷新二维码</button>}
      </>}>
      <div className={`qr-wrap ${qr.state === "expired" ? "expired" : ""}`}>
        {qr.data_uri ? <img src={qr.data_uri} alt="B 站登录二维码" />
          : <span className="qr-placeholder"><Icon name={qr.state === "error" ? "alert" : "refresh"} size={24}
            className={qr.state === "starting" ? "spin" : ""} /></span>}
      </div>
      <div className="qr-hint" role="status">{messages[qr.state]}</div>
    </Modal>
  );
};

const AddMemberModal = ({ query, onQuery, result, loading, adding, onSearch, onAdd, onClose }) => (
  <Modal title="添加主播" desc="通过直播间号、UID 或直播间链接查找" onClose={onClose}
    actions={<>
      <button type="button" className="btn" onClick={onClose}>取消</button>
      <button type="button" className="btn primary" onClick={onAdd} disabled={!result?.ok || loading || adding}>
        {adding ? "正在添加…" : "添加主播"}</button>
    </>}>
    <form className="field-row" onSubmit={(event) => { event.preventDefault(); if (!loading && query.trim()) onSearch(); }}>
      <input className="input" value={query} onChange={(event) => onQuery(event.target.value)}
        aria-label="直播间号、UID 或链接" placeholder="直播间号、UID 或链接" autoFocus disabled={adding} />
      <button type="submit" className="btn" disabled={loading || adding || !query.trim()}>{loading ? "查找中…" : "查找"}</button>
    </form>
    {result?.ok && <div className="member-preview"><span className="account-avatar">{Array.from(result.member.name || "?")[0]}</span>
      <div><div className="account-name">{result.member.name}</div>
        <div className="account-meta">直播间 {result.member.room} · UID {result.member.uid}</div></div></div>}
    {result && !result.ok && <div className="field-error" role="alert">{result.error}</div>}
  </Modal>
);

const MedalsModal = ({ data, selected, onToggle, onImport, onClose, loading, importing, error, onRetry }) => (
  <Modal title="同步粉丝牌" desc="选择要关注的主播，已关注的主播会自动跳过" wide onClose={onClose}
    actions={<>
      <button type="button" className="btn" onClick={onClose}>取消</button>
      <button type="button" className="btn primary" onClick={onImport} disabled={loading || importing || selected.size === 0 || Boolean(error)}>
        {importing ? "正在导入…" : selected.size ? `导入 ${selected.size} 位主播` : "导入主播"}</button>
    </>}>
    <div className="medal-list">
      {loading ? <div className="field-note">正在读取粉丝牌…</div>
        : error ? <div className="field-note"><p>{error}</p><button type="button" className="btn sm" onClick={onRetry}>重试</button></div>
        : !data.length ? <div className="field-note">暂无可同步的粉丝牌</div>
        : data.map((medal) => <label key={medal.uid} className={`medal-row ${medal.watched ? "watched" : ""}`}>
          <input type="checkbox" checked={selected.has(medal.uid)} disabled={medal.watched || importing}
            onChange={() => onToggle(medal.uid)} />
          <span className="account-avatar small">{Array.from(medal.name || medal.medal_name || "?")[0]}</span>
          <span className="medal-main"><span className="account-name">{medal.name || medal.medal_name}</span>
            <span className="account-meta">{medal.medal_name} Lv.{medal.level}{medal.watched ? " · 已关注" : ""}</span></span>
        </label>)}
    </div>
  </Modal>
);

const ConfirmModal = ({ title, desc, confirmLabel, danger, onConfirm, onClose, busy }) => (
  <Modal title={title} desc={desc} onClose={onClose} actions={<>
    <button type="button" className="btn" onClick={onClose} disabled={busy}>取消</button>
    <button type="button" className={`btn ${danger ? "danger" : "primary"}`} onClick={onConfirm} disabled={busy}>
      {busy ? "正在处理…" : confirmLabel}</button>
  </>} />
);

const RoomMenu = ({ menu, room, onClose, onOpen, onAction, onRemove }) => {
  const ref = useRef(null);
  useEffect(() => {
    const close = (event) => { if (!ref.current?.contains(event.target)) onClose(); };
    const key = (event) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", key); };
  }, [onClose]);
  if (!room) return null;
  const invoke = (fn) => { onClose(); fn(); };
  return <div className="room-menu" role="menu" ref={ref}
    style={{ left: Math.min(menu.x, window.innerWidth - 200), top: Math.min(menu.y, window.innerHeight - 200) }}>
    <button type="button" role="menuitem" onClick={() => invoke(() => onOpen(room.room))}>打开直播间</button>
    <button type="button" role="menuitem" disabled={Boolean(room.actions.reconnect) || room.operation.pending}
      title={room.actions.reconnect} onClick={() => invoke(() => onAction("reconnect", room.room))}>重新连接</button>
    <button type="button" role="menuitem" disabled={Boolean(room.actions.redo) || room.operation.pending}
      title={room.actions.redo} onClick={() => invoke(() => onAction("redo", room.room))}>补齐任务</button>
    <button type="button" role="menuitem" disabled={Boolean(room.actions.wear) || room.operation.pending}
      title={room.actions.wear} onClick={() => invoke(() => onAction("wear", room.room))}>佩戴粉丝牌</button>
    <div className="menu-divider" />
    <button type="button" role="menuitem" className="destructive-text" onClick={() => invoke(() => onRemove(room))}>移除主播</button>
  </div>;
};

Object.assign(window, { Modal, QrModal, AddMemberModal, MedalsModal, ConfirmModal, RoomMenu });
