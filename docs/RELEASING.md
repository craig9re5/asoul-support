# 发布流程

## 源码检查

```powershell
python tools/offline_test.py
python tools/check_architecture.py
python tools/scan_public.py
# 可选本机精确比对：凭证只在内存中解密，不输出内容。
python tools/scan_public.py --private-credentials "$env:LOCALAPPDATA/LiveSupport/credentials.json"
python tools/desktop_smoke.py
```

更新 runtime.APP_VERSION、pyproject.toml、package.json 与 CHANGELOG。检查待提交文件，确认没有账号数据、HAR、日志、安装备份或个人配置。

## 桌面构建

```powershell
python -m pip install -r requirements-desktop.txt
powershell -ExecutionPolicy Bypass -File build_desktop.ps1 -Mode onefile
```

构建脚本生成 EXE 和 build-info.json。把 `ASOUL_APP_DATA` 设置为独立临时目录，运行 EXE 的 `--diagnostic` 并确认 diagnostic.json 的版本、frozen 和 ok。这项诊断不进行账号请求。

桌面压缩包包含 LiveSupport.exe、build-info.json、Install-Desktop.ps1、README/DESKTOP、LICENSE、NOTICE、THIRD_PARTY_LICENSES 和依赖许可证。不得打包 `%LOCALAPPDATA%\LiveSupport`、源码 build/dist 全目录或上游品牌美术图。

## GitHub

主分支推送触发离线 CI；手动 desktop-build 工作流提供桌面构建产物。公开历史整合后先提供源码，不恢复旧二进制产物。新的 EXE 在白名单打包、元数据与敏感信息检查、冻结诊断通过后，才以新标签发布压缩包与 SHA256SUMS。避免在新发行说明中附上旧个人实验或完整运行日志。

发布前还要检查 Actions 产物/日志及提交作者地址；只扫描源码不等于已经审核了 EXE。历史改写后的克隆处理见 [PUBLICATION_CLEANUP.md](PUBLICATION_CLEANUP.md)。

发布不自动配置 Secrets、运行账号任务或启用本机账号动作。`.github/workflows/daily.yml` 为手动触发的可选账号工作流，需要用户自行配置 SESSDATA/BILI_JCT。
