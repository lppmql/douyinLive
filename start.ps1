param(
    [ValidateSet("lite", "standard")]
    [string]$Mode = "standard"
)

# Windows 原生日常启动入口。首次部署步骤见 README.md 的 Windows 教程。
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($PSVersionTable.PSVersion.Major -lt 7) {
    throw "请使用 PowerShell 7（pwsh）运行：pwsh -File .\start.ps1 standard"
}
if (-not $IsWindows) {
    throw "start.ps1 仅用于 Windows；macOS/Linux 请执行 ./start.sh"
}

$RootDir = $PSScriptRoot
$BackendDir = Join-Path $RootDir "backend"
$FrontendDir = Join-Path $RootDir "frontend"
$PythonExe = Join-Path $BackendDir ".venv\Scripts\python.exe"
$ViteEntry = Join-Path $FrontendDir "node_modules\vite\bin\vite.js"
$EnvFile = Join-Path $RootDir ".env"
$RuntimeDir = Join-Path $RootDir ".runtime"
$StartPidFile = Join-Path $RuntimeDir "start-windows.pid"

$BackendProcess = $null
$FrontendProcess = $null
$OllamaProcess = $null

function Get-EnvValue {
    param([Parameter(Mandatory)][string]$Name)

    if (-not (Test-Path $EnvFile)) {
        return ""
    }
    $prefix = "$Name="
    $line = Get-Content -LiteralPath $EnvFile |
        Where-Object { $_.StartsWith($prefix, [System.StringComparison]::Ordinal) } |
        Select-Object -Last 1
    if ($null -eq $line) {
        return ""
    }
    $value = $line.Substring($prefix.Length).Trim()
    if ($value.Length -ge 2) {
        $first = $value[0]
        $last = $value[$value.Length - 1]
        if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
            return $value.Substring(1, $value.Length - 2)
        }
    }
    return $value
}

function Require-Command {
    param([Parameter(Mandatory)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "缺少 $Name，请按 README.md 的 Windows 部署教程完成首次安装"
    }
    return $command.Source
}

function Invoke-Native {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$ArgumentList
    )

    & $FilePath @ArgumentList
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath 执行失败，退出码：$LASTEXITCODE"
    }
}

function Test-Http {
    param(
        [Parameter(Mandatory)][string]$Url,
        [switch]$RequireHealthyStatus
    )

    try {
        $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 2
        if ($RequireHealthyStatus) {
            return $response.status -eq "ok"
        }
        return $true
    }
    catch {
        return $false
    }
}

function Wait-Http {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Url,
        [int]$Seconds = 60,
        [System.Diagnostics.Process]$Process,
        [switch]$RequireHealthyStatus
    )

    for ($attempt = 1; $attempt -le $Seconds; $attempt++) {
        if ($null -ne $Process -and $Process.HasExited) {
            throw "$Name 进程已退出，退出码：$($Process.ExitCode)"
        }
        if (Test-Http -Url $Url -RequireHealthyStatus:$RequireHealthyStatus) {
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "$Name 未在 $Seconds 秒内通过健康检查：$Url"
}

function Assert-PortAvailable {
    param([Parameter(Mandatory)][int]$Port)

    $occupied = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners() |
        Where-Object { $_.Port -eq $Port }
    if ($occupied) {
        throw "端口 $Port 已被占用。请先在原启动终端按 Ctrl+C，再重新执行本脚本。"
    }
}

function Stop-OwnedProcess {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process -or $Process.HasExited) {
        return
    }
    try {
        # Ctrl+C 会先广播给同一控制台中的子进程，短暂等待其自行退出。
        Wait-Process -Id $Process.Id -Timeout 3 -ErrorAction Stop
    }
    catch {
        # 仅清理由本脚本 Start-Process 返回的 PID 及其子树，支持 uvicorn --reload。
        $taskkill = Join-Path $env:SystemRoot "System32\taskkill.exe"
        if (Test-Path $taskkill) {
            & $taskkill /PID $Process.Id /T /F *> $null
        }
        if (-not $Process.HasExited) {
            Stop-Process -Id $Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

function New-StartLockFile {
    try {
        $stream = [System.IO.File]::Open(
            $StartPidFile,
            [System.IO.FileMode]::CreateNew,
            [System.IO.FileAccess]::Write,
            [System.IO.FileShare]::None
        )
        try {
            $bytes = [System.Text.Encoding]::UTF8.GetBytes("$PID`n")
            $stream.Write($bytes, 0, $bytes.Length)
        }
        finally {
            $stream.Dispose()
        }
        return $true
    }
    catch [System.IO.IOException] {
        return $false
    }
}

function Acquire-StartLock {
    New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
    if (New-StartLockFile) {
        return
    }

    $existingPid = 0
    try {
        [int]::TryParse((Get-Content -LiteralPath $StartPidFile -Raw).Trim(), [ref]$existingPid) | Out-Null
    }
    catch {
        # 文件可能来自刚完成 CreateNew、尚未写入 PID 的并发启动任务。
        Start-Sleep -Milliseconds 200
        [int]::TryParse((Get-Content -LiteralPath $StartPidFile -Raw).Trim(), [ref]$existingPid) | Out-Null
    }
    if ($existingPid -gt 0 -and (Get-Process -Id $existingPid -ErrorAction SilentlyContinue)) {
        throw "已有 Windows 启动任务正在运行（PID: $existingPid）"
    }

    Remove-Item -LiteralPath $StartPidFile -Force -ErrorAction SilentlyContinue
    if (-not (New-StartLockFile)) {
        throw "另一个 Windows 启动任务正在取得启动锁，请稍后重试"
    }
}

function Release-StartLock {
    try {
        $ownerPid = (Get-Content -LiteralPath $StartPidFile -Raw).Trim()
        if ($ownerPid -eq "$PID") {
            Remove-Item -LiteralPath $StartPidFile -Force
        }
    }
    catch {
        # 锁文件已不存在时无需处理。
    }
}

Write-Host "========================================"
Write-Host "  抖音留资直播分析系统 — Windows 启动"
Write-Host "  模式: $Mode"
Write-Host "========================================"

Acquire-StartLock

try {
    Write-Host "`n  环境快速自检..."
    $DockerExe = Require-Command "docker"
    $NodeExe = Require-Command "node"
    $null = Require-Command "ffmpeg"
    $OllamaExe = Require-Command "ollama"

    if (-not (Test-Path $PythonExe)) {
        throw "后端虚拟环境不存在，请按 README.md 的 Windows 首次部署步骤安装依赖"
    }
    if (-not (Test-Path $ViteEntry)) {
        throw "前端依赖不存在，请在 frontend 目录执行 pnpm install --frozen-lockfile"
    }
    if (-not (Test-Path $EnvFile)) {
        throw "未找到 .env，请先执行 Copy-Item .env.example .env 并填写配置"
    }
    if ((Get-EnvValue "DB_USER") -eq "root") {
        throw "业务后端不能使用 DB_USER=root，请按 .env.example 配置受限账号 douyin_app"
    }

    & $PythonExe -c "import sys; raise SystemExit(sys.version_info[:2] != (3, 12))"
    if ($LASTEXITCODE -ne 0) {
        throw "后端虚拟环境必须使用 Python 3.12"
    }
    $nodeMajor = ((& $NodeExe --version).TrimStart("v").Split("."))[0]
    if ($nodeMajor -ne "22") {
        throw "Node.js 必须是 22.x，当前版本：$(& $NodeExe --version)"
    }

    & $DockerExe info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop 未运行，或当前未切换到 Linux containers"
    }
    Write-Host "  Docker Desktop 已运行"

    Push-Location $BackendDir
    try {
        $ollamaServiceUrl = (& $PythonExe -m scripts.check_local_ai --service-url | Select-Object -Last 1).TrimEnd("/")
        if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($ollamaServiceUrl)) {
            throw "无法读取本地 Ollama 地址"
        }
    }
    finally {
        Pop-Location
    }
    $ollamaTagsUrl = "$ollamaServiceUrl/api/tags"
    if (-not (Test-Http $ollamaTagsUrl)) {
        Write-Host "  正在启动本地 Ollama 服务..."
        $env:OLLAMA_HOST = ([Uri]$ollamaServiceUrl).Authority
        $env:OLLAMA_NO_CLOUD = "1"
        $env:OLLAMA_MAX_LOADED_MODELS = "1"
        $env:OLLAMA_NUM_PARALLEL = "1"
        $OllamaProcess = Start-Process -FilePath $OllamaExe -ArgumentList @("serve") -PassThru -NoNewWindow
        Wait-Http -Name "Ollama" -Url $ollamaTagsUrl -Seconds 30 -Process $OllamaProcess
    }
    Push-Location $BackendDir
    try {
        Invoke-Native -FilePath $PythonExe -ArgumentList @("-m", "scripts.check_local_ai")
    }
    finally {
        Pop-Location
    }
    Write-Host "  本地 Ollama 模型已就绪"

    Assert-PortAvailable 8000
    Assert-PortAvailable 9527

    Write-Host "`n[1/6] 启动 MySQL、Redis 与 Qdrant..."
    Push-Location $RootDir
    try {
        Invoke-Native -FilePath $DockerExe -ArgumentList @("compose", "up", "-d", "mysql", "redis", "qdrant")
    }
    finally {
        Pop-Location
    }

    $mysqlRootPassword = Get-EnvValue "MYSQL_ROOT_PASSWORD"
    if ([string]::IsNullOrWhiteSpace($mysqlRootPassword)) {
        $mysqlRootPassword = Get-EnvValue "DB_PASSWORD"
    }
    $mysqlReady = $false
    for ($attempt = 1; $attempt -le 60; $attempt++) {
        & $DockerExe exec -e "MYSQL_PWD=$mysqlRootPassword" douyin_live_mysql mysqladmin ping -h 127.0.0.1 -uroot --silent *> $null
        if ($LASTEXITCODE -eq 0) {
            $mysqlReady = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $mysqlReady) {
        throw "MySQL 60 秒内未就绪，或 MYSQL_ROOT_PASSWORD 不正确"
    }

    Push-Location $BackendDir
    try {
        Invoke-Native -FilePath $PythonExe -ArgumentList @("-m", "scripts.configure_database_users")
    }
    finally {
        Pop-Location
    }
    Wait-Http -Name "Qdrant" -Url "http://127.0.0.1:6333/healthz" -Seconds 60
    Write-Host "  基础服务已就绪"

    Write-Host "`n[2/6] 准备启动应用..."

    Write-Host "`n[3/6] 启动后端 FastAPI..."
    Push-Location $BackendDir
    try {
        Invoke-Native -FilePath $PythonExe -ArgumentList @("-m", "alembic", "upgrade", "head")
    }
    finally {
        Pop-Location
    }
    $backendArguments = @("-m", "uvicorn", "app.main:app", "--port", "8000")
    if ($env:BACKEND_RELOAD -eq "true") {
        $backendArguments += "--reload"
    }
    $BackendProcess = Start-Process -FilePath $PythonExe -ArgumentList $backendArguments -WorkingDirectory $BackendDir -PassThru -NoNewWindow
    Wait-Http -Name "后端" -Url "http://127.0.0.1:8000/health" -Seconds 60 -Process $BackendProcess -RequireHealthyStatus
    Write-Host "  后端: http://localhost:8000"

    Write-Host "`n[4/6] 采集调度器由后端统一管理..."
    Write-Host "  不启动独立 Worker，避免重复浏览器和重复调度"

    Write-Host "`n[5/6] 启动 FunASR 语音转写服务..."
    $asrAutoStart = Get-EnvValue "ASR_AUTO_START"
    if ($Mode -eq "lite" -or $asrAutoStart -ne "true") {
        Write-Host "  已跳过可选的 FunASR"
    }
    else {
        Push-Location $RootDir
        try {
            Invoke-Native -FilePath $DockerExe -ArgumentList @("compose", "--profile", "funasr", "up", "-d", "funasr")
        }
        finally {
            Pop-Location
        }
        $asrReady = $false
        for ($attempt = 1; $attempt -le 30; $attempt++) {
            try {
                $client = [System.Net.Sockets.TcpClient]::new()
                $connect = $client.ConnectAsync("127.0.0.1", 10096)
                if ($connect.Wait(2000) -and $client.Connected) {
                    $asrReady = $true
                    $client.Dispose()
                    break
                }
                $client.Dispose()
            }
            catch {
                # FunASR 首次加载模型可能需要数分钟，主系统继续启动。
            }
            Start-Sleep -Seconds 1
        }
        if ($asrReady) {
            Write-Host "  FunASR: ws://localhost:10096"
        }
        else {
            Write-Warning "FunASR 30 秒内未就绪，将在 Docker 中继续加载"
        }
    }

    Write-Host "`n[6/6] 启动前端..."
    $FrontendProcess = Start-Process -FilePath $NodeExe -ArgumentList @("node_modules/vite/bin/vite.js", "--mode", "test") -WorkingDirectory $FrontendDir -PassThru -NoNewWindow
    Wait-Http -Name "前端" -Url "http://127.0.0.1:9527" -Seconds 60 -Process $FrontendProcess

    Write-Host "`n========================================"
    Write-Host "  启动完成！"
    Write-Host "  前端: http://localhost:9527"
    Write-Host "  后端: http://localhost:8000"
    Write-Host "  Swagger: http://localhost:8000/docs"
    Write-Host "========================================"
    Write-Host "按 Ctrl+C 停止前端和后端；Docker 数据服务保持运行"

    while ($true) {
        if ($BackendProcess.HasExited) {
            throw "后端进程异常退出，退出码：$($BackendProcess.ExitCode)"
        }
        if ($FrontendProcess.HasExited) {
            throw "前端进程异常退出，退出码：$($FrontendProcess.ExitCode)"
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    Write-Host "`n正在停止 Windows 应用进程..."
    if (Test-Path $PythonExe) {
        Push-Location $BackendDir
        try {
            & $PythonExe -c "from app.services.asr.control import stop_asr_runtime; stop_asr_runtime()" 2>$null
        }
        catch {
            # 清理是尽力而为，不能覆盖原始启动错误。
        }
        finally {
            Pop-Location
        }
    }
    Stop-OwnedProcess $FrontendProcess
    Stop-OwnedProcess $BackendProcess
    Stop-OwnedProcess $OllamaProcess
    Release-StartLock
    Write-Host "已停止"
}
