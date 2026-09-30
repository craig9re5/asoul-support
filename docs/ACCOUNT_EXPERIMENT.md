# 本机账号验收方法

实验工具调用桌面与命令行共用的 `AppContext`，无需桌面自动化。公开仓库只保存实验方法，不保存个人账号、房间关联、运行时间线或原始报告。

## 查询与看播

```powershell
python tools/account_experiment.py --data-dir "$env:LOCALAPPDATA/LiveSupport"
# 将 room-id 替换为自己已配置的在播房间号。
python tools/account_experiment.py --data-dir "$env:LOCALAPPDATA/LiveSupport" --room room-id --watch-minutes 16 --danmaku-tasks --output build/watch-result.json
```

- 仅查询时无需 `--watch-minutes`。单次看播限制 0–20 分钟，同房间共用挂机租约。
- 默认不执行互动。显式传入 `--danmaku-tasks` 后遵循本机点亮与每日弹幕开关，复用发送预算及巡检；此工具始终不执行直播点赞。
- 每次请求检查主机和路径。报告不输出 Cookie、CSRF 或完整请求 URL，但仍包含任务和房间关联，必须留在本机。
- `success` 表示接口检查通过。收益必须比较服务端任务进度；接口成功、心跳成功和亲密度增长分别核对。
- 任务结算可能延迟。不要因为立即复查未增加而重复发送结果未知的请求。
- 实验结束后，原桌面暂停状态保持。

## 发布前

使用隔离目录做离线检查，不复制真实应用数据。报告、日志、HAR、抓包和截图均不纳入源码或发行包。问题报告只提供脱敏后的错误类型、任务变化和代码位置。
