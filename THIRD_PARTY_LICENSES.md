# 桌面依赖

| 组件 | 作用 | 许可文本来源 |
| --- | --- | --- |
| Python | 解释器与标准库 | 构建环境的 LICENSE.txt（包含 Python 相关许可） |
| Tcl/Tk | 桌面窗口 | Python 附带 Tcl/Tk 的 license.terms |
| Pillow | 图标绘制/图像处理 | pillow.dist-info/licenses/LICENSE |
| pystray | Windows 托盘 | COPYING、COPYING.LGPL；上游仓库 https://github.com/moses-palmer/pystray |
| six | pystray 的兼容依赖 | six.dist-info/LICENSE |
| qrcode | 扫码登录二维码生成 | qrcode.dist-info/licenses/LICENSE（BSD） |
| colorama | qrcode 的 Windows 依赖 | colorama.dist-info/licenses/LICENSE（BSD） |
| PyInstaller | 打包与启动器 | COPYING.txt（包括分发例外） |

`tools/build_manifest.py` 从实际构建环境复制这些文本到发布包的 `third_party_licenses` 目录，并记录安装版本。第三方软件的授权遵循其自身文本；pystray 源码可从上述上游获取。发布桌面包时应随附本文件及许可目录。
