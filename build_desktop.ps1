param([ValidateSet('onedir','onefile')][string]$Mode='onefile')
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    python tools/build_webui.py --check --stage-assets build/webui-runtime/assets
    if ($LASTEXITCODE -ne 0) { throw 'Web UI preparation failed' }
    python -c "from desktop.widgets import icon_image; icon_image().save('assets/live-support.ico', sizes=[(16,16),(32,32),(48,48),(64,64)])"
    if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed' }
    python -m PyInstaller --noconfirm --clean --windowed "--$Mode" --name LiveSupport --hidden-import pystray._win32 --hidden-import webview.platforms.winforms --hidden-import webview.platforms.edgechromium --hidden-import clr --collect-data webview --collect-binaries webview --collect-all pythonnet --collect-all clr_loader --add-data "build/webui-runtime/assets;desktop/webui/assets" --exclude-module numpy --icon assets/live-support.ico --manifest assets/desktop.manifest --distpath "dist/$Mode" --workpath "build/$Mode" tray_app.py
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
    $exePath = if ($Mode -eq 'onefile') { 'dist/onefile/LiveSupport.exe' } else { 'dist/onedir/LiveSupport/LiveSupport.exe' }
    python tools/build_manifest.py --exe $exePath
    if ($LASTEXITCODE -ne 0) { throw 'Build manifest failed' }
} finally {
    Pop-Location
}
