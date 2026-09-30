# LiveSupport 托盘版

Windows 登录后自动出现在系统托盘。双击 EXE 或托盘图标查看状态；关闭状态窗口会保留后台运行。

界面按 Windows 系统 DPI 同步缩放窗口、表格行高、列宽和控件间距，支持高分辨率显示。改变系统缩放比例后请退出并重新打开程序。当前采用 System DPI 模式；不同缩放比例的多显示器之间移动窗口时，由 Windows 处理兼容缩放，并非逐显示器原生重绘。

- **双击表格行**：立即在默认浏览器打开对应直播间。
- **表格行右键菜单**：
  - 🌐 **打开直播间**：浏览器直达。
  - 💬 **补齐弹幕任务**：检测任务差额并按需补发，受间隔、尝试预算和账号异常暂停约束。
  - 👍 **补做点赞任务**：实验性；上报后检查任务进度，失败会显示原因。
  - 🔄 **重新执行全部任务**：一键重做开播弹幕与点赞。
  - 🏅 **佩戴该粉丝牌**：一键切换为主佩戴粉丝牌。
  - ❌ **移除该主播**：从监控关注列表中移除。
- **任务明细浮层 (Tooltip)**：鼠标悬停在任务列时，弹出详尽任务清单（弹幕、点赞、看播时长、粉丝灯牌完成状态，以及距离下级所需经验和点亮剩余天数）。
- **➕ 添加主播**：弹窗输入房间号、短号、UID 或直播间链接，自动调用官方 API 解析主播昵称、真实房号及粉丝牌并确认添加。
- **📥 同步粉丝牌**：自动调用粉丝牌接口，一键列出所有拥有牌子但尚未加入监控的主播，支持勾选批量导入。
- **⚙️ 系统设置**：
  - 开播自动化策略开关：自动复活点亮 (10条弹幕)、自动刷满亲密度 (5条弹幕)、自动点赞。
  - 系统提醒与启动：开播 Windows 气泡提醒 (Toast)、开机自动启动 (写入注册表当前用户 Run 项)。
  - 巡检间隔设置与 B 站登录凭证管理。
- **暂停挂机 / 恢复挂机 / 立即检查**：灵活控制全局运行状态。
- **退出**：结束全部本程序进程。

参数保存在 `%LOCALAPPDATA%\LiveSupport\settings.json`：`check_minutes`、`auto_revive`、`auto_danmaku_intimacy`、`auto_like`、`notify_on_live`、`autostart`、`paused`。凭证保存在 `credentials.json`，成员保存在 `members.json`，运行状态在 `status.json`。

## 运行与恢复规则

- 桌面版、命令行版、凭证设置脚本与日报共用上述目录。`ASOUL_APP_DATA` 可指定另一套独立数据；Linux 默认使用 `~/.config/asoul-support`。
- 三个动作开关独立控制。保存策略或凭证后，停止旧 worker，再查询开播并启动新 worker；外部编辑配置会在下一次监控循环应用。暂停状态下不自动恢复挂机。
- 重启后重新查询服务端任务进度，只补缺额。旧 `actions.json` 和 `--skip-actions` 不再关闭任务巡检。显式的 `auto_*` 设置优先于旧 `danmaku` / `live_likes` 开关。
- 每 10 分钟复查未完成任务；北京时间跨日后重新确认完成标记和当天预算。弹幕发送尝试按认证 UID、房间、日期累计，最多 35 次，重启或重新扫码不会重置当天预算；手动补齐同样受限。
- 同一个房间的挂机进程共用操作系统文件锁，手动任务与自动任务也串行执行。多个房间仍共用至少 6 秒的弹幕发送间隔。
- `logs/activity.jsonl` 中每轮挂机有独立 `session_id`。主动停止会记录中断原因；日报按会话配对，历史无 ID 的结束记录仅使用一次。
- 直播查询失败、未查询和状态过期都不算“未开播”。过期的任务进度会显示“进度待更新”，心跳超时单独提示。
- `status.json` 是快照；程序化读取请使用 `desktop.storage.read_status(root)`，它检查快照年龄、进程存活及退出标记。跨日或计数回退时，不报告负的亲密度增量。

查看日报：`python scripts/daily_summary.py --hours 24`。没有运行记录时会提示无法判断，不会断言无人开播。旧日志可用 `--log-file <路径>` 显式读取。

## 构建与安装

```powershell
python -m pip install -r requirements-desktop.txt
.\build_desktop.ps1 -Mode onedir
.\build_desktop.ps1 -Mode onefile
.\Install-Desktop.ps1 -Activate
```

单文件产物为 `dist\onefile\LiveSupport.exe`，安装后放在 `%LOCALAPPDATA%\Programs\LiveSupport\LiveSupport.exe`。运行不需要另外安装 Python。安装器默认从源码旁的 `.asoul-support-data` 导入现有凭证，仅在新位置没有凭证时导入。

发布压缩包中也可直接运行 EXE；使用安装脚本时可指定 `-ExePath .\LiveSupport.exe`。安装器保留旧 EXE 的备份；默认暂停新安装，`-Activate` 会启动后台监控并配置登录任务。迁移已有计划任务时显式指定 `-LegacyTaskName '你的旧任务名'`，安装器不会猜测其他任务名称。

当前整合源码版本为 `2026.09.30.8`，旧桌面发布包已撤回，新二进制包需要单独审核。已有本机安装不自动变更。桌面后台和手动任务都调用共享 AppContext；GUI 结果在主线程更新。构建版本和源码/程序哈希见 build-info.json。使用设置中的「扫码登录」，见 `docs/QR_LOGIN.md`。浏览器扩展抓取及文件/粘贴导入入口已移除；已有本机凭证自动迁移到 Windows 用户 DPAPI。

账号异常时，表格与页脚显示“账号保护暂停”、原因及冷却时间。托盘菜单“处理账号保护暂停”用于查看或确认恢复；登录失效会打开扫码入口。普通“恢复挂机”不能绕过保护。详见 [ACCOUNT_SAFETY.md](docs/ACCOUNT_SAFETY.md)。

测试命令 `LiveSupport.exe --diagnostic` 验证冻结后的 Tk、图标和进程管理；`--probe <输出文件>` 仅验证登录并查询开播。`--command pause/resume/check/show/exit` 可控制已运行实例。诊断或测试可用 `ASOUL_APP_DATA` 指定隔离的数据目录。
