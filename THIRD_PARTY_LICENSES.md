# 桌面依赖

| 组件 | 作用 | 许可文本来源 |
| --- | --- | --- |
| Python | 解释器与标准库 | 构建环境的 LICENSE.txt（包含 Python 相关许可） |
| Tcl/Tk | 兼容桌面窗口（`--tk`） | Python 附带 Tcl/Tk 的 license.terms |
| pywebview | WebView2 窗口与 Python 桥接 | pywebview.dist-info/licenses/LICENSE（BSD） |
| pythonnet / clr_loader | .NET 和 WebView2 加载 | 各发行包自带的 LICENSE（MIT） |
| Microsoft WebView2 SDK | 嵌入式浏览器控件加载 | Web UI THIRD_PARTY_NOTICES；系统 Evergreen Runtime 不打包 |
| React / React DOM | 离线界面 | assets/vendor/THIRD_PARTY_NOTICES.txt（MIT） |
| Babel | 仅构建时编译 JSX | assets/vendor/THIRD_PARTY_NOTICES.txt（MIT）；运行时不加载 |
| bottle / typing_extensions / proxy_tools / cffi / pycparser | WebView 桥接依赖 | 发行包许可和 Web UI THIRD_PARTY_NOTICES |
| Pillow | 图标绘制/图像处理 | pillow.dist-info/licenses/LICENSE |
| pystray | Windows 托盘 | COPYING、COPYING.LGPL；上游仓库 https://github.com/moses-palmer/pystray |
| six | pystray 的兼容依赖 | six.dist-info/LICENSE |
| qrcode | 扫码登录二维码生成 | qrcode.dist-info/licenses/LICENSE（BSD） |
| colorama | qrcode 的 Windows 依赖 | colorama.dist-info/licenses/LICENSE（BSD） |
| PyInstaller | 打包与启动器 | COPYING.txt（包括分发例外） |

`tools/build_manifest.py` 从实际构建环境复制这些文本到发布包的 `third_party_licenses` 目录，并记录安装版本。第三方软件的授权遵循其自身文本；pystray 源码可从上述上游获取。发布桌面包时应随附本文件及许可目录。
