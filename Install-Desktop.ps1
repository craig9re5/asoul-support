param(
    [string]$ExePath = (Join-Path $PSScriptRoot 'dist\onefile\LiveSupport.exe'),
    [string]$LegacyRoot = $PSScriptRoot,
    [string]$LegacyTaskName = '',
    [switch]$Activate
)
$ErrorActionPreference = 'Stop'
$installDir = Join-Path $env:LOCALAPPDATA 'Programs\LiveSupport'
$dataDir = Join-Path $env:LOCALAPPDATA 'LiveSupport'
$installedExe = Join-Path $installDir 'LiveSupport.exe'
$sourceExe = (Resolve-Path -LiteralPath $ExePath).Path
$env:ASOUL_APP_DATA = $dataDir
New-Item -ItemType Directory -Path $installDir,$dataDir -Force | Out-Null
$account = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $dataDir /inheritance:r /grant:r "${account}:(OI)(CI)(F)" '*S-1-5-18:(OI)(CI)(F)' '*S-1-5-32-544:(OI)(CI)(F)' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Cannot protect application data directory' }

$running = @(Get-CimInstance Win32_Process -Filter "Name='LiveSupport.exe'" | Where-Object { $_.ExecutablePath -eq $installedExe })
if ((Test-Path -LiteralPath $installedExe) -and $running) {
    Start-Process -FilePath $installedExe -ArgumentList '--command exit' -WindowStyle Hidden -Wait
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        $running = @(Get-CimInstance Win32_Process -Filter "Name='LiveSupport.exe'" | Where-Object { $_.ExecutablePath -eq $installedExe })
        if (-not $running) { break }
        Start-Sleep -Milliseconds 500
    }
    if ($running) { throw 'Existing LiveSupport process has not exited; installation stopped' }
}
if (Test-Path -LiteralPath $installedExe) {
    $backupExe = Join-Path $installDir ('LiveSupport.previous-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '.exe')
    Copy-Item -LiteralPath $installedExe -Destination $backupExe
}
Copy-Item -LiteralPath $sourceExe -Destination $installedExe -Force
$obsoleteExtension = Join-Path $installDir 'browser-extension'
if (Test-Path -LiteralPath $obsoleteExtension) {
    $resolvedExtension = (Resolve-Path -LiteralPath $obsoleteExtension).Path
    $expectedExtension = [System.IO.Path]::GetFullPath((Join-Path $installDir 'browser-extension'))
    if ($resolvedExtension -ine $expectedExtension) { throw 'Unexpected extension cleanup path' }
    Remove-Item -LiteralPath $resolvedExtension -Recurse -Force
}
$diagnostic = Start-Process -FilePath $installedExe -ArgumentList '--diagnostic' -WindowStyle Hidden -Wait -PassThru
if ($diagnostic.ExitCode -ne 0) { throw 'Installed EXE diagnostic failed' }

$legacyCookie = Join-Path (Split-Path $LegacyRoot -Parent) '.asoul-support-data\.cookies.json'
$migrationArgs = @('--protect-credentials')
if (Test-Path -LiteralPath $legacyCookie) {
    $migrationArgs += @('--legacy-credentials', ('"' + (Resolve-Path -LiteralPath $legacyCookie).Path + '"'))
}
$migration = Start-Process -FilePath $installedExe -ArgumentList $migrationArgs -WindowStyle Hidden -Wait -PassThru
if ($migration.ExitCode -ne 0) { throw 'Protected credential migration failed' }
$settingsFile = Join-Path $dataDir 'settings.json'
$settings = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
$settings.paused = -not [bool]$Activate
$settings | ConvertTo-Json | Set-Content -LiteralPath $settingsFile -Encoding utf8

if ($Activate) {
    try {
    # Only take over the known legacy task and its verified heartbeat workers.
    $legacyTask = if ($LegacyTaskName) { Get-ScheduledTask -TaskName $LegacyTaskName -ErrorAction SilentlyContinue } else { $null }
    if ($legacyTask) {
        if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'legacy-task.xml'))) {
            Export-ScheduledTask -TaskName $legacyTask.TaskName | Set-Content -LiteralPath (Join-Path $dataDir 'legacy-task.xml') -Encoding utf8
        }
        Disable-ScheduledTask -TaskName $legacyTask.TaskName | Out-Null
        Stop-ScheduledTask -TaskName $legacyTask.TaskName -ErrorAction SilentlyContinue
    }
    $members = Get-Content -LiteralPath (Join-Path $dataDir 'members.json') -Raw | ConvertFrom-Json
    foreach ($member in $members) {
        $legacyLock = Join-Path $env:TEMP ('asoul-support\locks\' + $member.room + '.lock')
        if (Test-Path -LiteralPath $legacyLock) {
            $workerId = 0
            if ([int]::TryParse((Get-Content -LiteralPath $legacyLock -Raw).Trim(), [ref]$workerId)) {
                $worker = Get-CimInstance Win32_Process -Filter "ProcessId=$workerId" -ErrorAction SilentlyContinue
                if ($worker -and $worker.CommandLine -match 'scripts[\\/]heartbeat\.py' -and $worker.CommandLine -match '--until-offline') {
                    Stop-Process -Id $workerId -ErrorAction Stop
                }
            }
        }
    }
    $action = New-ScheduledTaskAction -Execute $installedExe -WorkingDirectory $installDir
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $account
    $trigger.Delay = 'PT20S'
    $principal = New-ScheduledTaskPrincipal -UserId $account -LogonType Interactive -RunLevel Limited
    $taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName 'LiveSupport-Desktop' -Action $action -Trigger $trigger -Principal $principal -Settings $taskSettings -Description 'LiveSupport tray app; starts after Windows login.' -Force | Out-Null
    Start-ScheduledTask -TaskName 'LiveSupport-Desktop'
    } catch {
        if ($legacyTask) {
            Enable-ScheduledTask -TaskName $legacyTask.TaskName | Out-Null
            Start-ScheduledTask -TaskName $legacyTask.TaskName
        }
        throw
    }
}
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\LiveSupport.lnk'))
$shortcut.TargetPath = $installedExe
$shortcut.WorkingDirectory = $installDir
$shortcut.IconLocation = $installedExe + ',0'
$shortcut.Save()
Write-Output "Installed: $installedExe"
Write-Output "Data: $dataDir"
Write-Output "Auto-start active: $Activate"
