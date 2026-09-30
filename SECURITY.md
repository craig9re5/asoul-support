# 安全与问题报告

登录凭证只存于本机数据目录。源码、发行包和 CI 不包含任何默认登录凭证。Windows 安装脚本会收紧数据目录权限；源码运行时请使用自己的用户目录。

2026.09.30.7 起，Windows 使用当前用户范围的 DPAPI 保存登录会话；credentials.json 是密文信封。已有明文自动原子迁移，保护失败时保留原文件并停止使用，不写明文临时文件或备份。DPAPI 不能防止以同一 Windows 用户身份运行的恶意程序读取会话，也不能保护已经泄漏的历史副本。

macOS/Linux 使用可选 keyring 的系统 Keychain/Secret Service，拒绝明文和未知后端；没有可用凭据库时拒绝保存。退出登录移除保存的会话和会话别名；UID 对应的每日预算与异常暂停状态保留，避免重新登录绕过保护。

详见 [账号异常保护和升级验收](docs/ACCOUNT_SAFETY.md)。凭证文件即使加密也不应上传；日志脱敏是辅助措施，分享前仍需检查。

请勿公开 credentials.json、SESSDATA、bili_jct、浏览器 Cookie、原始 Fetch/cURL、HAR 或完整个人日志。报告接口问题时提供脱敏后的响应码、任务进度与时间，保留参数名称，移除参数中的凭证值。

如发现凭证泄漏，请先从 B 站退出对应会话/更新登录态，再清理副本。公开问题使用 GitHub Issues；敏感细节请使用仓库开启的 Private vulnerability reporting（如果未开启，请先只提交无敏感内容的问题请求私下报告渠道）。不要把 Cookie 附到报告。

`tools/scan_public.py` 检查待发布文件及 Git 历史中的常见凭证模式、历史运行时文件名、个人路径和提交元数据。可使用 `--private-credentials` 显式指定本机凭证文件，增加精确值比对；凭证只在内存中解密，不打印或另存。报告只含位置和类型。该检查不代替人工检查，无法保证识别所有格式的秘密。

公开历史及产物清理、旧克隆的处理方式与缓存边界见 [docs/PUBLICATION_CLEANUP.md](docs/PUBLICATION_CLEANUP.md)。
