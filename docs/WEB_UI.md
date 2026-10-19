# Web 桌面

默认 Windows 桌面使用 pywebview 6.2.1 / WebView2，界面为 React 18.3.1 + CSS。业务仍由 `desktop.Engine` 和 `AppContext` 运行。`--tk` 可以选择原有 Tk 兼容界面；未检测到 WebView2 Runtime 时自动回退。

## 运行

从源码运行需要 Windows、CPython 3.11–3.15 和 Microsoft Edge WebView2 Evergreen Runtime。系统运行时由 Microsoft 单独安装与更新，本项目不捆绑 Chromium 或修改系统浏览器。

```powershell
python -m pip install -r requirements-desktop.txt
python tray_app.py --show
```

源码内已提交编译后的 JavaScript；直接运行不需要 Node。正常界面入口为 `desktop/webui/assets/index.html`，只加载随程序携带的本地资源。

关闭窗口后保留托盘运行；「退出应用」和托盘「退出」会停止挂机、取消扫码并等待已接受操作结束。第二次启动、开机启动及 `--command pause/resume/check/show/exit` 使用同一份数据目录和 IPC。

## 界面开发

- 页面：`desktop/webui/assets/js/*.jsx`。
- 设计变量与组件样式：`desktop/webui/assets/style.css`。
- 渲染数据适配：`js/bridge.jsx`；操作条件由 Python 桥接补充到快照。
- Python 桥接：`desktop/webui/api.py`；窗口、托盘与生命周期：`window.py`。

更改 JSX 后使用 Node 22+ 和已固定版本的本地 Babel 编译器：

```powershell
python tools/build_webui.py
```

编译工具给每个文件独立作用域，记录源文件、编译器、工具链与输出哈希。提交 JSX 时同时提交生成的 JS。只校验已编译输出不需要 Node：

```powershell
python tools/build_webui.py --check
```

`tools/vendor_web_assets.py --check` 校验第三方库的固定 SHA-256；正常运行和构建不下载依赖。`--download` 是显式修复命令，只恢复已固定的版本。Git 对 vendor JavaScript 禁用换行转换，保持与上游字节一致。

`preview.html` 和 `js/demo.js` 仅用于浏览器中查看合成数据界面，不访问真实账号，也不打入 EXE。可用项目的 `webui-preview` 预览配置打开 `http://localhost:4313/preview.html`。它复用生产组件，生产 `index.html` 不导入演示桥接。

## 构建

```powershell
powershell -NoProfile -File build_desktop.ps1 -Mode onefile
```

构建先校验已编译资源，按 `index.html` 的本地引用清单复制生产文件，再用 PyInstaller 收集 WebView2 SDK DLL、Python.NET 和兼容 Tk 资源。Babel、JSX、演示页面不会进入运行时资产目录。输出为 `dist/onefile/LiveSupport.exe`；Node 不参与常规打包。

`build-info.json` 包含 Python 版本、源码提交、源码状态、EXE 哈希、运行时前端资源哈希和依赖版本。许可证随 `third_party_licenses` 一起分发。

## 验证

改业务与桥接边界时运行离线回归，样式和文案修改只验证相应界面。真实窗口诊断使用独立临时目录、合成凭证和禁止网络的适配器：

```powershell
python tray_app.py --web-diagnostic build/webui-native-check.json --diagnostic-screenshot build/webui-native.png
```

冻结程序同样支持：

```powershell
dist\onefile\LiveSupport.exe --web-diagnostic build/webui-frozen-check.json --diagnostic-screenshot build/webui-frozen.png
```

诊断实际验证导航、设置持久化、账号显示、登录二维码与取消、离线操作禁用、IPC 暂停/恢复、关闭到托盘、退出与 IO 回收。二维码采用合成会话，不会验证真实账号登录；真实账号与平台收益仍按既有验收规则处理。

## 边界

渲染进程只持有公开状态与本机生成的二维码图片，不接收 Cookie、SESSDATA、扫码密钥或加密凭证。JS API 的内部对象均为私有字段，避免 pywebview 递归暴露 Engine 或原生窗口。写入操作使用参数检查、房间级防重和独立控制通道；网络请求及业务预算仍由原有服务负责。

Web UI 的 `accountInfo` 与 `account` 字符串分开，快照读取不反复解密凭证；引擎忙时使用最近快照并标记 `engine_busy`。当前的手机每日总结仍处于验证阶段，界面保持关闭。
