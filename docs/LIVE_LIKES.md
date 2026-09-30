# 直播点赞实现与验收

## 调用链

桌面自动任务与手动补齐 → `AppContext` → `DailyTaskRunner` → `like_live_room` → `report_live_likes`。

1. 认证接口确认当前账号 UID。
2. 复用扫码保存的匹配账号会话和 User-Agent。
3. 读取 `GetActivatedMedalInfo` 中点赞任务的当前进度、总额度和每轮次数。
4. 用 WBI 签名查询参数及空 POST body 调用 `likeReportV3`。
5. 延迟查询任务进度；接口 `code=0` 不单独作为记账成功依据。

## 研究依据

- [qydysky/biliApi](https://github.com/qydysky/biliApi/blob/main/main.go) 的 `LikeReport` 使用 POST 表单，包含点击数、房间、账号 UID、主播 UID、CSRF 和 visit_id，并附带 Cookie、Origin 与 Referer。
- [rongyuio/bilibili](https://github.com/rongyuio/bilibili/blob/master/live.go) 的 `ReportLiveLike` 从 Cookie 提取 CSRF，使用表单且不自动重试写请求。
- 本项目实现采用网页请求形式。不同客户端的请求构造可用作对照，不能证明同一账号的任务一定会记账，也不能据此认定每个 Cookie 字段均必需。

扫码白名单包含登录、账号校验及服务器设备字段；只保存 SESSDATA/bili_jct 的旧会话可能缺少后续请求上下文。程序不会从浏览器读取会话，不生成设备身份替代值。

## 本机验收方法

选择已配置、在播且任务未满的单个房间，记录任务基线，单次上报最多 30 次点击，随后独立查询任务进度。任务已满前后的相同读数不能证明写请求有效；任务结算延迟也不能作为立即重发的理由。

写请求超时、无效响应或 HTTP 5xx 会记录未知结果并暂停进一步写请求，只读核对后仍需用户确认恢复。明确拒绝按账号保护规则处理。见 [ACCOUNT_SAFETY.md](ACCOUNT_SAFETY.md)。

直播点赞仍为实验能力、默认关闭。公开文档只保存方法和实现边界，个人实验原始请求、报告、房间关联和账号设置不公开。不同账号及未来接口变化需要各自验证。
