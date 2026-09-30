# 贡献说明

1. Fork 仓库，在独立分支提交改动。
2. 核心代码放在 asoul_support，桌面只负责展示、调度和适配。不得从核心反向导入脚本或 GUI。
3. 保持现有命令和函数签名兼容；业务规则只实现一次。新依赖通过构造函数或作用域传入，不修改模块全局、sys.argv 或请求凭证缓存。
4. 为真实风险增加离线回归测试。Mock HTTP 边界；不要在 CI 或普通单测中调用账号接口。
5. 运行 `python tools/offline_test.py`、`python tools/check_architecture.py`、`python tools/scan_public.py`。Windows 界面改动还需运行 `python tools/desktop_smoke.py`。
6. Python 格式采用 Black，行宽 100。不要机械拆分协议字段、布局颜色或尺寸。
7. PR 描述写明改变的行为、兼容性、验证和限制。不上传数据目录或调试抓包。

协议改动应提供脱敏的输入/响应和本地测试向量。直播点赞的服务端记账验收与离线回归分开记录，接口成功不能代替任务进度验证。
