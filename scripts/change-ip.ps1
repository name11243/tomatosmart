#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$NewIP,
    [string]$ProjectRoot,
    [switch]$Preview,
    [switch]$SkipRestart
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
$utf8 = New-Object System.Text.UTF8Encoding($false, $true)
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Assert-IPv4([string]$Value) {
    if ($Value -notmatch '^(0|[1-9][0-9]{0,2})(\.(0|[1-9][0-9]{0,2})){3}$') {
        throw '请输入完整的 IPv4 地址，例如 192.168.31.217；不要填写 http:// 或端口。'
    }
    $parts = @($Value.Split('.') | ForEach-Object { [int]$_ })
    if (@($parts | Where-Object { $_ -gt 255 }).Count -or $parts[0] -eq 0 -or $parts[0] -ge 224) {
        throw 'IP 地址不合法，请填写电脑使用的 IPv4 单播地址。'
    }
}

function Read-Config([string]$Path) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    $hasBom = $bytes.Length -ge 3 -and $bytes[0] -eq 239 -and $bytes[1] -eq 187 -and $bytes[2] -eq 191
    $text = $utf8.GetString($bytes).TrimStart([char]0xfeff)
    [pscustomobject]@{ Path = $Path; Bytes = $bytes; Text = $text; Bom = $hasBom }
}

function Find-Scalar([string]$Text, [string]$Section, [string]$Key) {
    # Only edit one scalar in the expected block; never replace IPs throughout the file.
    $roots = [regex]::Matches($Text, '(?m)^' + [regex]::Escape($Section) + '[ \t]*:')
    if ($roots.Count -ne 1) { throw "配置必须包含唯一的 ${Section}: 配置块。" }
    $rest = $Text.Substring($roots[0].Index)
    $header = [regex]::Match($rest, '^[^\r\n]*\r?\n')
    if (-not $header.Success -or $header.Value.Trim() -notmatch ('^' + $Section + ':\s*(#.*)?$')) {
        throw "${Section}: 必须使用当前项目的 YAML 分行格式。"
    }
    $start = $roots[0].Index + $header.Length
    $tail = $Text.Substring($start)
    $next = [regex]::Match($tail, '(?m)^[^ \t#\r\n]')
    $block = if ($next.Success) { $tail.Substring(0, $next.Index) } else { $tail }
    $fields = [regex]::Matches($block, '(?m)^[ \t]+' + [regex]::Escape($Key) + ':[ \t]*(?<value>[^\r\n]*)')
    if ($fields.Count -ne 1) { throw "${Section}.${Key} 缺失或重复，原配置未修改。" }
    $field = $fields[0].Groups['value']
    $scalar = [regex]::Match($field.Value, '^(?<value>"[^"\r\n]*"|''(?:[^'']|'''')*''|[^#"''\r\n]*?)(?<suffix>[ \t]*(?:#.*)?)$')
    if (-not $scalar.Success) { throw "无法读取 ${Section}.${Key}，请保留标准 YAML 单行值。" }
    $value = $scalar.Groups['value'].Value.Trim()
    if ($value.StartsWith('"')) { $value = $value.Substring(1, $value.Length - 2) }
    elseif ($value.StartsWith("'")) { $value = $value.Substring(1, $value.Length - 2).Replace("''", "'") }
    if (-not $value -or $value.Contains('\')) { throw "${Section}.${Key} 为空或使用了不支持的转义格式。" }
    [pscustomobject]@{ Value = $value; Index = $start + $field.Index; Length = $field.Length; Suffix = $scalar.Groups['suffix'].Value }
}

function Changed-Bytes($Config, $Field, [string]$Value) {
    $text = $Config.Text.Remove($Field.Index, $Field.Length).Insert($Field.Index, $Value + $Field.Suffix)
    $bytes = $utf8.GetBytes($text)
    if ($Config.Bom) { $bytes = [byte[]](@(239,187,191) + $bytes) }
    return ,$bytes
}

function Same-Bytes([byte[]]$Left, [byte[]]$Right) {
    [Convert]::ToBase64String($Left) -ceq [Convert]::ToBase64String($Right)
}

function Replace-File([string]$Path, [byte[]]$Bytes) {
    $temp = Join-Path (Split-Path -Parent $Path) ('.ip-update-' + [guid]::NewGuid().ToString('N') + '.tmp')
    $previous = $temp + '.previous'
    try {
        [IO.File]::WriteAllBytes($temp, $Bytes)
        # Windows PowerShell 5.1 coerces a null backup path to an invalid empty string.
        [IO.File]::Replace($temp, $Path, $previous)
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
        if (Test-Path -LiteralPath $previous) { Remove-Item -LiteralPath $previous -Force -ErrorAction SilentlyContinue }
    }
}

function Run-Docker([string]$Arguments, [int]$TimeoutSeconds = 15) {
    $docker = Get-Command docker.exe -ErrorAction SilentlyContinue
    if (-not $docker) { throw '没有找到 Docker Desktop。' }
    $info = New-Object Diagnostics.ProcessStartInfo
    $info.FileName = $docker.Source
    $info.Arguments = $Arguments
    $info.WorkingDirectory = $ProjectRoot
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $process = New-Object Diagnostics.Process
    $process.StartInfo = $info
    try {
        $null = $process.Start()
        $output = $process.StandardOutput.ReadToEndAsync()
        $errors = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            throw 'Docker 操作超时，已保存的配置仍然保留。'
        }
        if ($process.ExitCode -ne 0) { throw 'Docker 操作未完成，请查看 Docker Desktop 中的服务状态。' }
        $output.GetAwaiter().GetResult()
    } finally { $process.Dispose() }
}

try {
    if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
    $mqtt = Read-Config (Join-Path $ProjectRoot 'backend/config/mqtt.yaml')
    $camera = Read-Config (Join-Path $ProjectRoot 'backend/config/camera.yaml')
    $hostField = Find-Scalar $mqtt.Text 'mqtt' 'host'
    $urlField = Find-Scalar $camera.Text 'camera' 'url'
    Write-Host '番茄系统 · 一键修改服务器 IP' -ForegroundColor Cyan
    Write-Host ('当前 MQTT 地址：' + $hostField.Value)
    if (-not $NewIP) { $NewIP = Read-Host '请输入电脑的新 IPv4 地址（直接回车取消）' }
    if (-not $NewIP.Trim()) { Write-Host '已取消，配置未修改。'; exit 0 }
    $NewIP = $NewIP.Trim()
    Assert-IPv4 $NewIP
    $uri = $null
    if (-not [Uri]::TryCreate($urlField.Value, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -notin @('http','https') -or $uri.UserInfo -or $uri.Fragment -or
        $uri.HostNameType -ne [UriHostNameType]::IPv4) {
        throw '摄像头原地址必须为不含用户名、密码和片段的 HTTP/HTTPS IPv4 地址。'
    }
    # Replace just the host, preserving the camera's port, path and query verbatim.
    $newUrl = [regex]::Replace($urlField.Value, '^(https?://)[0-9.]+', '${1}' + $NewIP, [Text.RegularExpressions.RegexOptions]::IgnoreCase)
    $changes = @(
        [pscustomobject]@{ Config = $mqtt; After = (Changed-Bytes $mqtt $hostField $NewIP); Name = 'mqtt.yaml' },
        [pscustomobject]@{ Config = $camera; After = (Changed-Bytes $camera $urlField ("'" + $newUrl.Replace("'", "''") + "'")); Name = 'camera.yaml' }
    )
    # Keep exact bytes when the values already match (including YAML quote style).
    if ($hostField.Value -eq $NewIP) { $changes[0].After = $mqtt.Bytes }
    if ($urlField.Value -ceq $newUrl) { $changes[1].After = $camera.Bytes }
    Write-Host ('新 MQTT 主机：' + $NewIP + '（端口和主题保留原值）')
    Write-Host ('新摄像头地址：' + $newUrl)
    Write-Host ('网页入口：http://' + $NewIP + ':5176/')
    Write-Host ('EMQX 管理：http://' + $NewIP + ':18083/')
    if ($Preview) { Write-Host '仅预览，没有写入配置或重启服务。'; exit 0 }
    $pending = @($changes | Where-Object { -not (Same-Bytes $_.Config.Bytes $_.After) })
    if ($pending.Count) {
        $backup = Join-Path $ProjectRoot ('data/ip-backups/' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0,8))
        $null = New-Item -ItemType Directory -Path $backup -Force
        foreach ($item in $changes) { [IO.File]::WriteAllBytes((Join-Path $backup $item.Name), $item.Config.Bytes) }
        $manifest = @{ changed_at = (Get-Date).ToString('o'); old_mqtt_host = $hostField.Value; new_ip = $NewIP; files = @('mqtt.yaml','camera.yaml') }
        [IO.File]::WriteAllText((Join-Path $backup 'change.json'), ($manifest | ConvertTo-Json), $utf8)
        $written = @()
        try {
            foreach ($item in $pending) {
                if (-not (Same-Bytes ([IO.File]::ReadAllBytes($item.Config.Path)) $item.Config.Bytes)) {
                    throw '运行期间配置被其他程序修改，请重新运行脚本。'
                }
                Replace-File $item.Config.Path $item.After
                $written += $item
            }
        } catch {
            foreach ($item in $written) {
                if (Same-Bytes ([IO.File]::ReadAllBytes($item.Config.Path)) $item.After) {
                    Replace-File $item.Config.Path $item.Config.Bytes
                }
            }
            Write-Host ('修改未完成；原配置备份：' + $backup) -ForegroundColor Yellow
            throw
        }
        Write-Host ('配置已保存。原配置备份：' + $backup) -ForegroundColor Green
    } else { Write-Host '配置已经是这个 IP，无需重复修改。' -ForegroundColor Green }
    Write-Host 'EMQX 节点名、监听、匿名连接和主题权限保持原样。'
    if ($SkipRestart) { Write-Host '已按参数跳过后端重启。'; exit 0 }
    try {
        $running = Run-Docker 'compose ps --status running --services'
        if ('api' -notin @($running -split '\r?\n')) { throw '当前 API 容器未运行，下次启动会读取已保存的新 IP。' }
        Write-Host '正在重启后端，让 MQTT 连接读取新地址……'
        $null = Run-Docker 'compose restart --no-deps api' 45
        # Verify the active container sees the same bind-mounted YAML, without login or secrets.
        $verify = 'compose exec -T api python -c "import sys,yaml; from pathlib import Path; m=yaml.safe_load(Path(''backend/config/mqtt.yaml'').read_text()); c=yaml.safe_load(Path(''backend/config/camera.yaml'').read_text()); from urllib.parse import urlsplit; assert m[''mqtt''][''host'']==sys.argv[1]; assert urlsplit(c[''camera''][''url'']).hostname==sys.argv[1]" ' + $NewIP
        $null = Run-Docker $verify
        Write-Host '完成：后端已重启并读取新 IP，请刷新网页。设备在线状态以实际连接为准。' -ForegroundColor Green
    } catch {
        Write-Host ('配置已保存，但后端尚未完成应用：' + $_.Exception.Message) -ForegroundColor Yellow
        Write-Host '下次后端启动时会读取新配置；也可以恢复服务后用同一 IP 再运行此脚本。'
        exit 2
    }
} catch {
    Write-Host ('操作失败：' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
