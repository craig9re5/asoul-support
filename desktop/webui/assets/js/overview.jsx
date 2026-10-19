/* Overview and room detail. Labels describe verified state from the engine. */

const { Icon, relativeTime, absoluteTime, durationLabel, numberLabel } = window;

const Avatar = ({ room, image }) => (
  <span className="avatar" style={{ background: room.color }} aria-hidden="true">
    {image ? <img src={image} alt="" /> : room.initial}
  </span>
);

const RoomRow = ({ room, selected, onSelect, onContextMenu, image }) => (
  <button type="button" className="room" role="option" aria-selected={selected}
    data-room={room.room} onClick={() => onSelect(room.room)}
    onDoubleClick={() => window.call("open_room", room.room).catch(() => {})}
    onContextMenu={(event) => onContextMenu(event, room.room)}>
    <Avatar room={room} image={image} />
    <span className="room-main">
      <span className="room-name">
        {room.live && <i className="live-dot" title="直播中" />}
        <span>{room.name}</span>
      </span>
      {room.live && room.title && <span className="room-title" title={room.title}>{room.title}</span>}
      <span className="room-meta">
        {room.healthy && <span>已连接 {durationLabel(room.minutes)}</span>}
        {room.healthy && room.gain !== null && <span className="sep">·</span>}
        {room.gain !== null && <span>今日 +{numberLabel(room.gain)}</span>}
      </span>
    </span>
    {room.state !== "未开播" && <span className="room-side">
      <span className={`pill ${room.tone}`}>{room.state}</span>
    </span>}
  </button>
);

const DetailPanel = ({ room, busy, onAction, onOpen, onRemove, image }) => {
  if (!room) return (
    <aside className="detail card" aria-label="直播间详情">
      <div className="empty">
        <Icon name="monitor" size={24} />
        <strong>选择一个直播间</strong>
        <span>查看连接状态与今日任务</span>
      </div>
    </aside>
  );
  const taskCount = room.tasks.filter((task) => task.done).length;
  const reason = room.actions.redo || "";
  const operation = room.operation;
  const pending = busy || operation.pending;
  const knownExperience = !room.tasks_stale && room.next_intimacy > 0;
  const progress = knownExperience ? Math.min(100, Math.max(0, room.intimacy / room.next_intimacy * 100)) : 0;
  const note = room.watch_note || "";
  return (
    <aside className="detail card" aria-label="直播间详情" data-screen-label={`详情 · ${room.name}`}>
      <div className="detail-scroll" key={room.room}>
        <div className="detail-heading">
          <div className="detail-identity">
            <div className="detail-name">{room.name}</div>
            <div className="detail-title" title={room.title}>{room.live ? room.title || "直播中" : "等待主播开播"}</div>
          </div>
          <button type="button" className="btn ghost icon-button" title="更多操作"
            aria-label="更多操作" onClick={onRemove}><Icon name="more" size={17} /></button>
        </div>
        <div className="state-row">
          <span className={`state-label ${room.tone === "warn" ? "warn" : ""}`}>
            {room.state}
            <span className="state-sub" title={absoluteTime(room.last_heartbeat)}>
              {room.healthy ? `已连接 ${durationLabel(room.minutes)}`
                : room.live ? "开播后自动建立连接" : "等待主播开播"}
              {room.last_heartbeat && room.active ? ` · ${relativeTime(room.last_heartbeat)}同步` : ""}
            </span>
          </span>
          <button type="button" className="btn sm" onClick={() => onAction("reconnect", room.room)}
            disabled={pending || Boolean(room.actions.reconnect)} title={room.actions.reconnect || "重新建立看播连接"}>
            <Icon name="reconnect" size={12} className={room.reconnecting ? "spin" : ""} />
            {room.reconnecting ? "重连中…" : "重连"}
          </button>
        </div>
        <div className="gain-card">
          <div className="gain-head"><span className="gain-label">今日亲密度</span>
            {room.medal_name && <span className="gain-medal">{room.medal_name} Lv.{room.medal_level}</span>}
          </div>
          <div className="gain-value">{room.gain === null ? "—" : `+${numberLabel(room.gain)}`}</div>
          <div className="gain-foot">
            <span>{room.gain === null ? "等待更新" : "已确认到账"}</span>
            {room.day_limit > 0 && <span>每日上限 {numberLabel(room.day_limit)}</span>}
          </div>
          {knownExperience && <>
            <div className="bar thin" role="progressbar" aria-label="粉丝牌升级进度"
              aria-valuenow={room.intimacy} aria-valuemin={0} aria-valuemax={room.next_intimacy}>
              <i style={{ width: `${progress}%` }} />
            </div>
            <div className="gain-foot"><span>等级经验</span>
              <span className="tnum">{numberLabel(room.intimacy)} / {numberLabel(room.next_intimacy)}</span>
            </div>
          </>}
        </div>
        {(room.connection_warning || room.watch_warning || room.task_error) && <div className="notice" role="status">
          <Icon name="alert" size={14} /><span>{room.connection_warning || room.watch_warning || room.task_error}</span>
        </div>}
        {note && <div className="notice neutral"><Icon name="info" size={14} /><span>{note}</span></div>}
        {room.reconnect_message && <div className="inline-status" role="status">{room.reconnect_message}</div>}
        <section className="block">
          <div className="block-head"><span className="block-title">今日任务</span>
            <span className="block-note">{room.tasks_stale ? "等待更新" : `${taskCount} 项已完成`}</span>
          </div>
          <div className="task-table">
            {room.tasks.map((task) => <div className="task" key={task.key}>
              <span className="task-name">{task.name}</span>
              <span className={`task-val ${task.done ? "done" : !task.text ? "pending" : ""}`}>
                {task.done && <Icon name="check" size={11} />}{task.text || "待更新"}
              </span>
            </div>)}
          </div>
        </section>
        <div className="detail-secondary-actions">
          <button type="button" className="btn ghost sm" onClick={() => onAction("wear", room.room)}
            disabled={pending || Boolean(room.actions.wear)} title={room.actions.wear || "佩戴这个主播的粉丝牌"}>
            <Icon name="medal" size={12} />佩戴粉丝牌
          </button>
          <span className="block-note">以 B 站结算为准</span>
        </div>
      </div>
      <div className="detail-action-area">
        {operation.message && <p className="action-hint" role="status">{operation.message}</p>}
        {reason && <p className="action-hint">{reason}</p>}
        <div className="detail-foot">
          <button type="button" className="btn" onClick={() => onOpen(room.room)} disabled={Boolean(room.actions.open)}>
            <Icon name="external" size={13} />打开直播间
          </button>
          <button type="button" className="btn primary" onClick={() => onAction("redo", room.room)}
            disabled={pending || Boolean(reason)}>
            <Icon name={pending ? "refresh" : "check"} size={13} className={pending ? "spin" : ""} />
            {pending ? "正在处理…" : "补齐任务"}
          </button>
        </div>
      </div>
    </aside>
  );
};

const Overview = ({ rooms, selectedId, onSelect, paused, onTogglePause, onCheck, checking, summary,
  onAction, onOpen, onAddMember, onSyncMedals, onRemove, onContextMenu, busyRoom, controlBusy,
  error, recovery, onRecovery, interval, images, signedIn, closing, bridgeConnected }) => {
  const selected = rooms.find((room) => room.room === selectedId);
  const healthy = rooms.filter((room) => room.healthy).length;
  const unknown = rooms.filter((room) => room.live_status == null).length;
  const status = closing ? "正在退出…" : !bridgeConnected ? "正在连接后台…" : paused ? "已暂停挂机"
    : !signedIn ? "等待登录" : error ? "需要处理" : healthy ? `${healthy} 个直播间挂机中`
    : unknown ? "等待检查" : "等待开播";
  return (<>
    <header className="topbar">
      <h1>直播总览</h1><span className="sub">{checking ? "正在检查直播状态…" : summary ? `${summary}检查` : ""}</span>
      <span className="spacer" />
      <button type="button" className="btn" onClick={onAddMember} disabled={closing}><Icon name="plus" size={13} />添加主播</button>
      <button type="button" className="btn" onClick={onCheck} disabled={checking || controlBusy || closing}>
        <Icon name="refresh" size={13} className={checking ? "spin" : ""} />{checking ? "检查中…" : "立即检查"}
      </button>
      <button type="button" className={`btn ${paused ? "primary" : ""}`} onClick={onTogglePause} disabled={controlBusy || closing}>
        <Icon name={paused ? "play" : "pause"} size={13} />{paused ? "恢复挂机" : "暂停挂机"}
      </button>
    </header>
    {(error || recovery?.action === "login") && <div className="banner" role="status">
      <Icon name={recovery?.action === "login" ? "user" : "alert"} size={14} />
      <span>{!signedIn ? "登录 B 站，开始自动挂机与每日任务" : error || recovery?.message}</span>
      {recovery?.action && <button type="button" className="btn sm" onClick={onRecovery}>{recovery.label || "查看详情"}</button>}
    </div>}
    <div className="workspace">
      <section className="list card" aria-label="关注的直播间">
        <header className="list-head"><span className="list-title">关注的直播间</span><span className="list-count">{rooms.length}</span>
          <span className="spacer" /><button type="button" className="btn ghost sm" onClick={onSyncMedals} disabled={closing}>
            <Icon name="medal" size={12} />同步粉丝牌</button>
        </header>
        <div className="rooms" role="listbox" aria-label="直播间列表">
          {rooms.length ? rooms.map((room) => <RoomRow key={room.room} room={room} selected={room.room === selectedId}
            image={images[room.uid]} onSelect={onSelect} onContextMenu={onContextMenu} />)
            : <div className="empty list-empty"><Icon name="monitor" size={24} /><strong>还没有关注主播</strong>
              <span>添加主播或同步已有粉丝牌，开播后自动开始</span><button type="button" className="btn" onClick={onAddMember}>添加主播</button></div>}
        </div>
      </section>
      <DetailPanel room={selected} busy={busyRoom === selected?.room} onAction={onAction} onOpen={onOpen}
        onRemove={() => selected && onRemove(selected)} image={selected && images[selected.uid]} />
    </div>
    <footer className="statusbar">
      <span className={healthy && !closing ? "dot-live" : "dot-paused"} aria-hidden="true" /><strong>{status}</strong>
      <span className="spacer" /><span className="low-priority">每 {interval} 分钟检查一次</span>
    </footer>
  </>);
};

Object.assign(window, { Overview, Avatar });
