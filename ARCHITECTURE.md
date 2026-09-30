# 架构与调用关系

## 分层与入口

```text
scripts/*.py（兼容命令）                 desktop.view / dialogs
      ↓                                    ↓
asoul_support.cli                  desktop.engine / worker / dispatch
      ↓                                    ↓
stateless heartbeat gateway ←──── asoul_support.application.AppContext
      ↓
services：daily_tasks / danmaku / likes / watch / content
      ↓
API 适配：heartbeat / videos / dynamics / api.medals
      ↓
http / runtime / credentials / members / context / danmaku_pacing
```

`asoul_support` 不导入 `scripts` 或 `desktop`。旧 `import heartbeat` 等名称映射到核心模块，以保留既有函数与测试替换点；旧脚本没有第二套业务实现。业务服务显式接收 gateway，避免反向导入调用者。gateway 中旧路径常量仅作兼容默认值，实际桌面操作由 `AppContext` 的作用域覆盖。

## 运行依赖和状态归属

| 状态 | 唯一所有者 | 生命周期 |
| --- | --- | --- |
| 数据目录、事件监听、通知回调 | RuntimeContext / AppContext | 一次应用操作；ContextVar 在 finally 恢复，隔离线程和嵌套调用 |
| 心跳密钥、规则、时间戳、序号 | HeartbeatChain | 一次直播会话；失败重建 E 链 |
| 弹幕阶段状态、消息池、发送次数 | MedalDanmakuTask | 一次任务检查 |
| 每日尝试额度与任务完成状态 | DailyTaskRunner + state/tasks JSON | 认证 UID、房间、北京时间日期；会话替换保留额度 |
| 账号异常暂停、底层请求预算 | safety + http | 同一数据目录内跨进程共享；写请求未知结果不重放 |
| 登录会话密文、账号请求头 | secret_store + session_headers | Windows 用户 DPAPI 或系统凭据库；原子迁移、账号匹配 |
| 监控子进程、巡检时间、缓存 | desktop.Engine | 桌面实例；Windows Job 管理其子进程 |
| 控件及主线程回调 | TrayUI / dialogs / Dispatcher | GUI 实例；3 个后台 IO 线程，回调在 Tk 主线程执行 |
| 公共设备 Cookie | RuntimeContext 的 SessionProvider | 应用作用域内按线程隔离；不保存登录凭证到全局缓存 |

`EVENT_CONTEXT` 仅存日志会话字段，不控制动作策略。动作开关是显式参数。桌面 worker 不修改 `sys.argv`、`MEMBERS`、`_log` 或路径变量。

## 主要流程

1. **检测**：登录验证 → 查询开播与勋章/任务 → 写探测结果。查询缺失或失效表示未知，不等于未开播。
2. **监控**：Engine 应用最新设置 → 启动每房间 worker → AppContext 传递策略 → CLI 的共享会话协调器取得 OS 房间租约 → HeartbeatChain 按服务端间隔发 X。
3. **每日任务**：房间任务锁 → 保留尝试额度 → 读取服务端状态 → 必要时点亮 → 发送剩余弹幕 → 再读状态；点赞单独执行并验证任务轮次。每 10 分钟检查未完成项，跨日重置。
4. **手动补齐/签到**：桌面手动动作、CLI 点赞和签到所有模式调用同一个 DailyTaskRunner，复用预算、锁、阶段与完成判定。
5. **显示**：snapshot 接收内存状态及读取后的房间记录，投影为行；view 更新摘要与表格；布局、控件、对话框与调度分开。
6. **内容**：查询并验证日期范围的分页 → 筛选 → 执行选择的互动 → 汇总；查询错误不能伪装成空列表。

## 并发、存储与失败

配置读改写由 `update_json` 的 OS 文件锁串行化，并用独立临时文件原子替换。成员导入和删除也走这个边界。发送弹幕在同一个数据目录内共享 6 秒间隔；不同机器/数据目录无法共享锁。

任务预算先写入再发送；进程中断会保留预约额度，避免反复重启绕过上限。数据目录相同的不同启动方式共用房间租约。UI 设置变更使 Engine 停止旧策略的 worker，再用新设置重启。

HTTP 层返回 `error_kind`；查询要求成功时用 ApiError 中止，不返回部分列表。已有兼容查询入口仍允许 None/空状态表示未知；所有消费者必须区分它与正常离线。CLI 可执行入口把预期错误转为非零退出码。错误报告不回显请求 Cookie。

## 兼容与验证

旧命令和函数保留，`main(argv=None)` 增加显式参数，原无参数调用仍可用。不再支持外部模块靠修改全局变量配置桌面；应构造 AppContext(root)。

结构门禁检查核心反向依赖、静态导入循环和桌面模块/argv 修改；离线测试覆盖协议向量、时间窗口、跨日、重启、预算、锁、未知状态、配置并发和桌面一致性。UI 声明中的颜色、尺寸与协议规定的字段作为有意义的常量保留。

`docs/history` 仅保留上游来源材料，不作为当前行为依据。实验性点赞及平台收益仍需独立的账号验收，个人实测过程不公开。
