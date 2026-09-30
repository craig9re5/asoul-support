# LiveSupport / A-SOUL Support

可配置的 B 站直播应援工具，包含 Windows 托盘程序和 Python 命令行。桌面自动任务、手动补齐与脚本使用同一套业务实现。

基于 [XiaoYiWeio/asoul-support](https://github.com/XiaoYiWeio/asoul-support) 重构，保留原有命令和作者归属。公开 Git 历史整合为经过清理的源码基线；来源、许可和图片说明见 [NOTICE.md](NOTICE.md)。

## 功能与边界

| 功能 | 实现与确认方式 |
| --- | --- |
| 开播检测与心跳 | X25Kn E/X 链式签名，遵循服务端间隔；记录成功心跳和亲密度前后值 |
| 粉丝牌点亮与弹幕任务 | 独立开关；读取任务进度、有限重试、跨进程发送间隔、每 10 分钟巡检、跨日重新确认 |
| 直播点赞 | **实验性，默认关闭**；复用扫码会话；接口 code=0 后仍复查任务进度 |
| 视频互动 | 按日期分页查询；点赞默认开启，投币和收藏需显式参数 |
| 动态点赞 | 按日期查询并点赞；查询失败、分页不完整和接口失败返回失败 |
| Windows 桌面 | 自定义主播、同步勋章、状态与任务明细、暂停、提醒、自启动、手动补齐 |

每日任务以 B 站返回的任务进度为准。接口成功不保证记账，项目不承诺固定亲密度收益。当前重构经过离线测试；账号行为与平台规则可能变化。

## Windows 桌面

在设置中配置登录凭证和动作开关。数据保存在 `%LOCALAPPDATA%\LiveSupport`，不保存在源码目录。完整安装与开机启动说明见 [DESKTOP.md](DESKTOP.md)。

推荐在设置中点击「扫码登录」，用 B 站 App 扫码确认即可。[扫码登录说明](docs/QR_LOGIN.md)。

从源码运行（桌面环境需 Python 3.10+）：

```powershell
python -m pip install -r requirements-desktop.txt
python tray_app.py --show
```

## 命令行

核心仅使用标准库，支持 Python 3.9+。首次运行 `setup_local_cookie.py`，凭证输入不回显。

Windows 凭证由当前用户的 DPAPI 加密；macOS/Linux 保存登录需要安装 `asoul-support[secure-store]` 并启用系统凭据库。没有可用的安全存储时拒绝保存，不回退到明文。账号异常保护与恢复说明见 [docs/ACCOUNT_SAFETY.md](docs/ACCOUNT_SAFETY.md)。

```powershell
git clone https://github.com/craig9re5/asoul-support.git
cd asoul-support
python setup_local_cookie.py
python scripts/check_auth.py
python scripts/heartbeat.py --check-only
python scripts/heartbeat.py --until-offline
python scripts/checkin.py --live-only
python scripts/videos.py --days 7
python scripts/dynamics.py --days 7
python scripts/daily_summary.py
```

`--count` 是签到本轮尝试上限，仍按任务缺额发送并受每日预算约束。视频 `--coin`、`--fav` 是显式选择的额外动作。成员配置与旧管理器用法见 [LOCAL_CONFIG.md](LOCAL_CONFIG.md)。原命令参数仍可用 `--help` 查看。

可选安装核心包，使用 `asoul-heartbeat`、`asoul-checkin`、`asoul-videos`、`asoul-dynamics`、`asoul-summary`：

```powershell
python -m pip install .
asoul-heartbeat --help
```

## 开发与构建

```powershell
python tools/offline_test.py
python tools/check_architecture.py
python tools/scan_public.py
# Windows：真实控件测试，无账号请求
python tools/desktop_smoke.py
powershell -ExecutionPolicy Bypass -File build_desktop.ps1
```

输出为 `dist/onefile/LiveSupport.exe`，附带构建版本、源码哈希和程序哈希。发布流程见 [docs/RELEASING.md](docs/RELEASING.md)。GitHub 的账号操作工作流仅手动触发，需自行配置 Secrets。

## 阅读顺序

- [架构与调用关系](ARCHITECTURE.md)
- [审计及分阶段计划](docs/REFACTOR_PLAN.md)
- [重构结果与验证](docs/REFACTOR_RESULTS.md)
- [贡献说明](CONTRIBUTING.md)、[安全报告与凭证处理](SECURITY.md)

代码使用 [MIT License](LICENSE)。上游品牌图片的许可范围另见 [NOTICE.md](NOTICE.md)。
