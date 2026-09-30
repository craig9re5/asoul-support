---
name: asoul-support
description: "LiveSupport B 站直播间心跳、粉丝牌与弹幕任务、实验性直播点赞及视频动态互动。支持 Windows 托盘和命令行。"
---

# LiveSupport 操作入口

读取 README.md、DESKTOP.md 和 LOCAL_CONFIG.md 获取当前使用规则，ARCHITECTURE.md 描述核心逻辑。

- 凭证由用户在本机运行 `setup_local_cookie.py` 输入，不要求用户在聊天中提供原始 Cookie。
- 先用 `scripts/check_auth.py` 验证，再用 `scripts/heartbeat.py --check-only` 查看状态。
- 挂机入口：`scripts/heartbeat.py --until-offline`；动作可分别用 `--no-revive`、`--no-intimacy-danmaku`、`--no-danmaku` 控制。
- 自动签到：`scripts/checkin.py --live-only`；按任务进度与预算补齐，不把接口成功数当成亲密度记账。
- 视频入口：`scripts/videos.py --days 7`；投币仅在用户选择后加 `--coin`，收藏加 `--fav`。
- 动态入口：`scripts/dynamics.py --days 7`。这些命令会产生账号动作，应符合用户本次授权。
- 直播点赞是实验功能，默认关闭；扫码建立同账号会话后显式加 `--live-likes`。不宣称上报接口 code=0 就完成了任务。
- 桌面入口 `tray_app.py --show` 或发布包的 LiveSupport.exe，关闭窗口保留托盘，退出才停止监控。
- 改代码后运行 `tools/offline_test.py` 和 `tools/check_architecture.py`；离线测试不做真实账号动作。

成员来自共享数据目录的 members.json。纯 Python 核心无第三方依赖，桌面依赖另见 requirements-desktop.txt。历史 mobileHeartBeat 收益说明不适用于当前 X25Kn 实现。
