# A-SOUL Support 功能与实现逻辑详解

> 历史实现说明。2026-09-30 已调整存储、桌面调度和统计：所有本机入口共用 LiveSupport 数据目录；重启以任务进度补齐，开关独立生效，跨日重置；会话 ID 用于日志配对。下文旧路径、PID 锁、仅开播执行任务及已知问题列表不代表当前代码。当前使用规则以 [DESKTOP.md](DESKTOP.md) 与 [LOCAL_CONFIG.md](LOCAL_CONFIG.md) 为准。

> 本文档面向想读懂/改造这个项目的人。读完你应该能回答：它到底能干什么、每个功能靠什么协议实现、代码是怎么串起来的。
>
> 项目版本：v4.1.1 ｜ 语言：纯 Python 3.9+ ｜ 外部依赖：无

---

## 一、总览：它是什么

这是一个 **B 站直播间/UP 主自动应援工具**。核心目标是两件事：

1. **维持粉丝牌不掉**（靠直播间弹幕 + 心跳）
2. **刷高粉丝亲密度**（靠直播间心跳挂机）

外加两个"顺手做掉"的互动功能：**视频三连**和**动态点赞**。

设计上有一个很明确的取向：**零外部依赖**。不用 Node.js、不用 Docker、不用第三方签名服务，只用 Python 标准库 `hashlib` / `hmac` / `urllib`。这是 v4.0 之后的重要决定——早期版本需要跑一个 Node 签名服务，部署很痛。

---

## 二、能干的四件事

| 功能 | 需要开播？ | 命令入口 | 作用 |
|------|-----------|---------|------|
| 💓 心跳挂机涨亲密度 | ✅ 必须 | `heartbeat.py` | 模拟移动端/Web 端心跳，按分钟结算亲密度 |
| 🏅 粉丝牌点亮 | ✅ 必须 | `checkin.py --live-only` | 发 10 条弹幕点亮牌子，牌子保持 3 天可见 |
| 🪙 视频点赞/投币/收藏 | ❌ | `videos.py` | 给 UP 主新视频批量三连（投币默认关） |
| 💬 动态点赞 | ❌ | `dynamics.py` | 给 UP 主新动态点赞（默认不开启） |

**关键背景知识（决定了所有设计）：**

- **亲密度**只有三种来源：看直播（每分钟少量）、**投币（1 币 = 10 亲密度）**、送礼。
- **粉丝牌点亮**（发 10 条弹幕）**不涨亲密度**，它只是让牌子"亮起来"保持可见。
- 这两件事经常被混为一谈，所以项目里它们是**两条独立的代码路径**。

---

## 三、代码结构

```
asoul-support/
├── manage_asoul_heartbeat.py   # 进程管理器：查开播 → 起/停挂机子进程（带锁）
├── setup_local_cookie.py       # 交互式录入 Cookie（getpass 不回显）
├── scripts/
│   ├── members.py              # ★ 唯一的成员配置表（改动只需改这里）
│   ├── credentials.py          # ★ Cookie 路径的唯一真相来源
│   ├── check_auth.py           # 登录态校验（nav 接口）
│   ├── heartbeat.py            # 核心：开播检测 + X25Kn 心跳挂机
│   ├── checkin.py              # 粉丝牌点亮（10 条弹幕）
│   ├── videos.py               # 视频三连（含 WBI 签名）
│   ├── dynamics.py             # 动态点赞
│   └── daily_summary.py        # 读日志生成 24 小时挂机日报
├── assets/                     # logo 等图片
├── tests/                      # 测试
└── logs/                       # 运行时日志（gitignore）
```

**两个"单一真相来源"文件**是理解整个项目的钥匙：

- `members.py` —— 所有脚本都 `from members import MEMBERS`，改监控对象只改一处。
- `credentials.py` —— 所有脚本都 `from credentials import cookie_path()`，Cookie 路径只在一处定义。

---

## 四、核心：X25Kn 心跳协议（最难的部分）

这是项目技术含量最高的地方，也是 v4.1 的重大升级点。

### 4.1 为什么是 X25Kn

B 站历史上换过好几代心跳协议：

| 协议 | 状态 | 说明 |
|------|------|------|
| `mobileHeartBeat` | ❌ 已废弃 | v4 用的，B 站后端已**停止为其结算亲密度** |
| `User/userOnlineHeart` | ⚠️ 保留 | 只维持在线，不涨亲密度（代码里的 legacy fallback）|
| **`X25Kn` E/X** | ✅ 现行 | v4.1 起采用，需要 HMAC 链式签名 |

`X25Kn` 是 B 站 Web 端现行协议，有两个端点：

- **E（Enter）**：`live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/E`
- **X（心跳）**：`live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/X`

### 4.2 链式签名的逻辑

这是整个脚本最精巧的设计。流程是 **先 E 后 X，每次响应递推下一次的秘密**：

```
① 发 E 请求
   ↓
② 拿到 {secret_key, secret_rule, timestamp(ets), heartbeat_interval}
   ↓
③ 等待 heartbeat_interval 秒
   ↓
④ 用 secret_key + secret_rule 对 payload 做 HMAC 签名 → 发 X 请求
   ↓
⑤ X 响应又返回新的 secret_key / secret_rule / ets
   ↓
⑥ 回到 ③，用新秘密签下一次
```

**签名算法**（`_x25kn_sign`）：

`secret_rule` 是一个索引数组，每个索引映射到一个哈希算法：

```python
_X25KN_HMAC_FUNCS = ["md5", "sha1", "sha256", "sha224", "sha512", "sha384"]
```

签名过程是**链式的**——不是逐层哈希，而是把上一轮结果当作下一轮的输入：

```python
result = payload_json
key_bytes = secret_key.encode("utf-8")
for r in rules:
    mac = hmac.new(key_bytes, result.encode("utf-8"), getattr(hashlib, _X25KN_HMAC_FUNCS[r]))
    result = mac.hexdigest()   # 上一轮 hexdigest 成为下一轮输入
return result
```

签名覆盖的 payload 是这 10 个字段（用 `separators=(",", ":")` 压缩成无空格 JSON，顺序敏感）：

```python
{
  "platform": "web", "parent_id": ..., "area_id": ...,
  "seq_id": seq, "room_id": ..., "buvid": ...,
  "uuid": ..., "ets": ..., "time": heartbeat_interval, "ts": ...,
}
```

### 4.3 三个容易踩的坑，代码里都处理了

**① 时间漂移** —— 这是 v4.1.1 修的核心问题。

服务端要求严格按 `heartbeat_interval` 发心跳，发早了报 `time check failed`。如果直接 `sleep(60)`，网络往返时间会逐次累积漂移。解法是记录**上一次响应到达的时刻**，只补足剩余时间：

```python
def _wait_for_heartbeat_window(last_response_at, interval):
    wait_seconds = interval - (time.monotonic() - last_response_at)
    if wait_seconds > 0:
        time.sleep(wait_seconds)
```

用 `time.monotonic()` 而非 `time.time()`，避免系统时间调整导致跳变。而且每次响应后**用服务端下发的 `heartbeat_interval` 覆盖本地值**（带 5~300 秒的合理性校验），完全跟随服务端节奏。

**② 失败链恢复** —— 这是 v4.1.1 修的另一件事。

X 请求失败后，如果继续用旧的 `secret_key` / `ets` 硬发，会连续失败（时间戳已过期）。`_restart_chain()` 的做法是**重新走一次 E** 重建整条链，重置 `seq=0`：

```python
def _do_x_beat():
    ...
    if result:
        # 递推新秘密
        protocol_seq = next_seq
        secret_key = result.get("secret_key", secret_key)
        ...
    else:
        _restart_chain()   # 失败 → 重发 E
```

连续失败 10 次则整体退出，避免无限空转。

**③ 设备指纹（LIVE_BUVID）** —— 拿不到会导致亲密度不结算。

优先复用 `.cookies.json` 里已有的 `LIVE_BUVID`（浏览器真实指纹）；没有就走 SPI 接口 `x/frontend/finger/spi` 抓一个 `b_3` 当替代，**并写回缓存**（`os.chmod 0600`）。都失败才退到随机字符串。

---

## 五、四个功能模块的实现逻辑

### 5.1 开播检测

两个 API 双保险：

1. **批量接口**：`room/v1/Room/get_status_info_by_uids` —— 一次 POST 提交所有 `uids[]`，效率高。
2. **兜底单查**：`room/v1/Room/get_info?room_id=` —— 批量接口漏了的房间逐个补查，并带回 `area_id` / `parent_area_id`（X25Kn 签名要用）。

判据统一是 `live_status == 1`。

### 5.2 心跳挂机 `watch_room()`

这是 `heartbeat.py` 的主循环，两种模式：

**限时模式**（默认 25 分钟）：
```python
total_beats = (duration_min * 60) // heartbeat_interval
for i in range(total_beats):
    _do_x_beat()
```
先算总次数再循环，轮次确定。

**长期挂机模式**（`--until-offline`，实际部署用的）：

```python
while True:
    _do_x_beat()
    # 每轮都查一次直播状态
    status = _get_single_room_status(...)
    if status and status.get("live_status") != 1:
        return {..., "stopped_reason": "offline"}   # 下播即退出
    if consecutive_fail >= 10:
        return {..., "stopped_reason": "error"}     # 连续失败熔断
```

每轮心跳后查一次开播状态，**下播立即退出**。这个模式还会：
- 启动时通过 `_notify()` 发 Discord 通知（需环境变量 `ASOUL_DISCORD_TARGET`）
- 自动调 `light_up_medal()` 发 10 条弹幕点牌子（可用 `--no-danmaku` 关掉）

### 5.3 亲密度增量记录

挂机**前后各拉一次粉丝牌面板**，做差值：

```python
before_intimacy = medals.get(uid, {}).get("today_intimacy")
refreshed = get_my_medals(...)
after_intimacy = refreshed.get(uid, {}).get("today_intimacy")
result["intimacy_delta"] = after_intimacy - before_intimacy
```

字段名要特别注意——B 站面板里叫 `today_feed`，代码做了兼容：

```python
"today_intimacy": info.get("today_feed", info.get("today_intimacy", 0))
```

这个增量是**验证协议是否真的生效**的唯一手段，也是 v4.1.1 新增的能力。

### 5.4 粉丝牌点亮与日常弹幕亲密度任务 (`checkin.py` / `heartbeat.py`)

逻辑链：**取牌子状态 → 佩戴 → [阶段1: 10条点亮复活] → [阶段2: 5条亲密度任务]**。

B 站现行规则中，“熄灭后的点亮任务”与“每日弹幕亲密度任务”是两个独立的状态：
- **阶段 1（点亮/复活）**：若牌子处于熄灭状态（`is_lighted == False`），发送 **10 条弹幕**完成复活点亮；若已点亮则跳过。
- **阶段 2（日常亲密度）**：牌子就绪后，继续发送 **5 条弹幕**完成当天的发弹幕亲密度任务（上限 +5 亲密度）。
- **总计**：熄灭时按 `10 + 5 = 15` 条执行；已点亮时仅执行 5 条日常亲密度弹幕。

- 接口进度感知：读取 `GetActivatedMedalInfo`，实时检测 `is_lighted` 与 `sendDanmu` 任务进度（`current/limit`），避免重复刷屏。
- 佩戴：`fansMedal/wear`，先戴上牌子，弹幕才带牌。
- 弹幕：`msg/send`，发送间隔 3 秒（`--danmaku-delay`），采用扩充的不重样弹幕词库防止风控。

### 5.5 视频三连 `videos.py` + WBI 签名

这是唯一需要 **WBI 签名**的模块，因为 B 站 Space API 有反爬。

WBI 的逻辑：

1. 从 `nav` 接口拿 `img_key` / `sub_key`（从图片 URL 里切出来）。
2. 用一张 64 元素的**重排表** `MIXIN_KEY_ENC_TAB` 把两个 key 拼成一个 32 位 `mixin_key`：
   ```python
   orig = img_key + sub_key
   return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]
   ```
3. 参数加时间戳 `wts`，过滤掉 `!'()*` 这些特殊字符，排序后 urlencode，拼上 `mixin_key` 取 MD5 得到 `w_rid`。

`mixin_key` 有模块级缓存（`_wbi_mixin_key_cache`），避免每次请求都调 nav。

三个动作各自处理了"重复操作"的返回码，把它们视为**成功**而不是失败：

| 动作 | 接口 | 已完成错误码 |
|------|------|-------------|
| 点赞 | `archive/like` | 65006 |
| 投币 | `coin/add` | 34005 |
| 收藏 | `v3/fav/resource/deal` | 11201 |

收藏还得先查默认收藏夹 ID（`fav/folder/created/list-all`，拿第一个）。

### 5.6 动态点赞 `dynamics.py`

比 videos 简单，**不需要 WBI**（用的是 polymer web-dynamic 接口）。

一个细节：它额外维护了一个 `CookieJar`，先访问一次 `bilibili.com` 拿到 `buvid3` 等反爬 cookie，再和自己的 `SESSDATA` 拼在一起发请求：

```python
combined = f"{jar_cookies}; {auth_cookies}" if jar_cookies else auth_cookies
```

点赞接口在 `api.vc.bilibili.com/dynamic_like/v1/dynamic_like/thumb`，`65006` 和 `500` 都当"已点过"处理。

---

## 六、进程管理与调度

这是"能不能长期无人值守稳定跑"的关键，项目给了两条路。

### 6.1 进程管理器 `manage_asoul_heartbeat.py`

**为什么需要它**：定时任务每 30 分钟跑一次，如果每次都不管不顾地起新进程，会同时开一堆挂机进程互相打架。所以需要**锁**。

流程：

```
① 检查 .cookies.json 存在
② 跑 check_auth.py 校验登录态
③ 查开播状态
④ 对每个成员：
     - 锁文件 locks/<room>.lock 存在？
       - 有 → 读 PID，安全探测进程是否活着
         - 活着 → 跳过
         - 死了/空/非法 → 删锁（清理僵尸）
     - 在播 且 无有效锁 → 起子进程 heartbeat.py --until-offline --members <name>
                         → 把子进程 PID 写进锁文件
```

**PID 存活探测**统一走 `process_lock.is_process_running()`：Windows 用 `OpenProcess` 和 `GetExitCodeProcess` 查询；Unix 才用 `os.kill(pid, 0)`。Windows 上不能用 `os.kill(pid, 0)` 做探测，因为它可能直接结束进程。

**Windows 适配细节**：子进程用 `CREATE_NO_WINDOW` 避免弹黑框，环境变量注入 `PYTHONIOENCODING=utf-8` 避免中文乱码，stdout/stderr 重定向到 `%TEMP%\asoul-support\heartbeat_<name>_<ts>.log`。

### 6.2 两种调度方式的权衡

| 方式 | 周期 | 特点 |
|------|------|------|
| 简单 cron | 每 30 分钟 | 直接跑 `heartbeat.py`，轻量，无锁 |
| 进程管理器 | 每 5 分钟 | 有锁 + 自动清理僵尸 + 通知，长期稳定 |

`heartbeat.py` 自身在 `--until-offline` 下**也会写锁**（写自己的 PID），所以两条路径共享同一套锁语义。

### 6.3 运行日志

统一写到 `%TEMP%\asoul-support\`（Windows）/ `/tmp/asoul-support/`：

- `asoul_activity.jsonl` —— 结构化事件流，每行一个 JSON，带 `ts` 时间戳。
- `heartbeat_<name>_<ts>.log` —— 子进程原始输出。
- `locks/` —— 锁文件目录。

事件类型：

| type | 触发时机 |
|------|---------|
| `check` | 每次开播检测（含在播名单和标题）|
| `watch_start` / `watch_end` | 挂机起止（end 含亲密度前后值和增量）|
| `x25kn_x_success` | 每次心跳成功（含 seq 和 interval）|
| `x25kn_e_error` / `x25kn_x_error` | 心跳失败（含错误码）|
| `watch_exception` | 挂机抛异常 |
| `auth_error` | 登录态失效 |

`daily_summary.py` 就是消费这个日志的——读 24 小时记录，把 `watch_start` 和匹配的 `watch_end` 配对（找同成员、时间在后的最近一条），算出总挂机时长，输出一份日报。

> ⚠️ 注意：`daily_summary.py` 里的 `_LOG_FILE` 写的是 `Path.home() / ".openclaw" / "logs"`，和 `heartbeat.py` 实际写的 `%TEMP%/asoul-support/` **不一致**，目前读不到数据。

---

## 七、执行链路全貌

```
                    ┌─────────────────────────────┐
                    │  Windows 计划任务 / cron     │
                    │  每 5~30 分钟一次            │
                    └──────────────┬──────────────┘
                                   ↓
                  ┌────────────────────────────────┐
                  │ manage_asoul_heartbeat.py      │
                  │ ① check_auth  ② 查开播 ③ 查锁  │
                  └──────────────┬─────────────────┘
                                 ↓ 在播 且 无有效锁
                  ┌────────────────────────────────┐
                  │ Popen: heartbeat.py --until-offline │
                  │        （写子进程 PID 到 lock）  │
                  └──────────────┬─────────────────┘
                                 ↓
       ┌─────────────────────────────────────────────────┐
       │ watch_room()                                    │
       │  enter_room → 取 area_id → 取 LIVE_BUVID        │
       │  → E 拿 secret_key → while: 等窗口 → X 心跳     │
       │     → 递推 secret → 查开播 → 下播则退出          │
       └──────────────┬──────────────────────────────────┘
                      ↓
       ┌─────────────────────────────────────────────────┐
       │ %TEMP%/asoul-support/asoul_activity.jsonl       │
       └──────────────┬──────────────────────────────────┘
                      ↓
              daily_summary.py → 24 小时日报
```

---

## 八、安全设计

- **Cookie 不明文进命令行**：`setup_local_cookie.py` 用 `getpass` 不回显输入。
- **文件权限 600**：`os.chmod(cookies_path, 0o600)`（Windows 上是 no-op，但语义保留）。
- **默认最小动作**：投币、收藏、动态点赞全部**默认关闭**，需显式 `--coin` / `--fav`。
- **仓库忽略凭证**：`.gitignore` 含 `.cookies.json`。
- **校验前置**：挂机前先跑 `check_login()`，避免用失效 Cookie 空转一晚上。

---

## 九、已知问题与改进方向

按优先级排列（详细分析见代码审查结论）：

| 级别 | 问题 | 影响 |
|------|------|------|
| 🔴 P0 | `setup_local_cookie.py` 写仓库根，`credentials.cookie_path()` 读 `%LOCALAPPDATA%`，**写入/读取路径不一致** | 脚本读不到 Cookie，直接起不来 |
| 🟠 P1 | `daily_summary.py` 日志路径与实际不一致 | 日报永远为空 |
| 🟠 P1 | `heartbeat.py` 的 `_DANMAKU_MSGS` 仅 14 条，`checkin.py` 用同一池子循环复用 | 文案重复，且删几条就会静默点不亮 |
| 🟡 P2 | `check_live_status` 在 `heartbeat.py` / `checkin.py` 重复实现且**签名不同** | 改一处漏一处 |
| 🟡 P2 | 多处 `except Exception: pass` 静默吞异常 | 故障难排查 |
| 🟡 P2 | `format_output` 里 `all_ok` 算了不用；`_get_single_room_status` 是无意义透传包装 | 死代码 |

---

## 十、快速上手（本机）

```bash
# 1. 存 Cookie（交互式，不回显）
python setup_local_cookie.py

# 2. 只检测谁在播
python scripts/heartbeat.py --check-only

# 3. 挂机到下播（会同时点牌子）
python scripts/heartbeat.py --until-offline

# 4. 用进程管理器（推荐长期用）
python manage_asoul_heartbeat.py

# 5. 视频/动态（不需要开播）
python scripts/videos.py --days 7
python scripts/dynamics.py --days 7
```

**改监控对象**：编辑 `scripts/members.py` 的 `MEMBERS`，填 `name` / `uid`（主播 UID）/ `room`（直播间号）——**两者不能互换**。一次只配一位最稳。
