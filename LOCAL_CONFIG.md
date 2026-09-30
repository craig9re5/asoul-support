# 本地配置与脚本管理器

Windows 默认目录为 `%LOCALAPPDATA%\LiveSupport`；Linux 为 `~/.config/asoul-support`。`ASOUL_APP_DATA` 可指定独立目录，桌面、命令行和管理器必须使用同一目录才能共享租约和发送节奏。

| 文件 | 用途 |
| --- | --- |
| credentials.json | 登录凭证与可选浏览器点赞上下文，不提交 Git |
| members.json | 当前关注列表，GUI 或手动编辑 |
| settings.json | 三个独立动作开关、巡检、提醒、暂停 |
| logs/activity.jsonl | 会话、心跳、任务和异常事件 |
| state/tasks | 每日任务预算 |
| state/房间号.json、status.json | 桌面状态，需结合时间戳与存活进程判断 |
| locks | 系统文件锁与弹幕发送时间 |

成员记录示例（UID 与房间号不同）：

```json
[{"name":"小松绿Viridis","uid":1891335475,"room":1727071052}]
```

名字不能重复或含逗号，UID 和房间号需为正整数，房间不能重复。没有成员文件时使用 `asoul_support/members.py` 的首次初始化名单；已有 JSON 优先。

本机输入凭证：`python setup_local_cookie.py`。浏览器点赞上下文输入：`python setup_live_like_cookie.py`。输入工具不回显 Cookie；更换登录凭证会清除旧账号的设备/点赞上下文。不要把浏览器原始请求、HAR 或 credentials.json 放入 issue。

脚本管理器：

```powershell
python manage_asoul_heartbeat.py --check-only
python manage_asoul_heartbeat.py
python run_scheduled_manager.py
```

可在自己的任务计划中定期运行 `run_scheduled_manager.py`。桌面持续监控也能完成该职责；同数据目录的房间租约会避免重复挂机。迁移旧计划任务时，按自己的任务名称显式配置安装参数。数据备份与凭证迁移在本地进行，不上传到 GitHub。
