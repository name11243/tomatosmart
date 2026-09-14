#requires -Version 7.0
param(
    [Parameter(Mandatory=$true)][string]$HardwareSource,
    [string]$EmqxRoot = 'C:\emqx\emqx-5.2.0'
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$firmware = Get-Content -LiteralPath $HardwareSource -Raw
function Firmware-Default([string]$Key) {
    $match = [regex]::Match($firmware, '_config\.get\("' + [regex]::Escape($Key) + '",\s*"([^"\r\n]*)"\)')
    if (-not $match.Success) { throw "Cannot find firmware default for $Key" }
    return $match.Groups[1].Value
}
$hardwareUser = Firmware-Default 'mqtt_user'
$hardwarePassword = Firmware-Default 'mqtt_password'
$hardwareBroker = Firmware-Default 'mqtt_server'
$envPath = Join-Path $projectRoot '.env'
if (-not (Test-Path -LiteralPath $envPath)) { throw 'Create local .env from .env.example first.' }
$envText = Get-Content -LiteralPath $envPath -Raw
$secretMatch = [regex]::Match($envText, '(?m)^TOMATO_MQTT_PASSWORD=([^\r\n]+)')
$platformPassword = if ($secretMatch.Success) { $secretMatch.Groups[1].Value } else { [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant() }
if (-not $secretMatch.Success) {
    [IO.File]::AppendAllText($envPath, "`nTOMATO_MQTT_PASSWORD=$platformPassword`n", [Text.UTF8Encoding]::new($false))
}
$backupDir = Join-Path $projectRoot 'data/emqx-backups'
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$clusterConfig = Join-Path $EmqxRoot 'data/configs/cluster.hocon'
if (Test-Path -LiteralPath $clusterConfig) {
    Copy-Item -LiteralPath $clusterConfig -Destination (Join-Path $backupDir ('cluster-' + (Get-Date -Format yyyyMMdd-HHmmss) + '.hocon'))
}
$setupUser = 'tomatosmart_setup_' + [guid]::NewGuid().ToString('N').Substring(0,12)
$setupPassword = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(24))
$ctl = Join-Path $EmqxRoot 'bin/emqx_ctl.cmd'
$setupCreated = $false
$headers = @{}
function Emqx-Api([string]$Method, [string]$Path, [object]$Body = $null) {
    $request = @{ Method=$Method; Uri="http://127.0.0.1:18083/api/v5$Path"; Headers=$headers; NoProxy=$true; TimeoutSec=15 }
    if ($null -ne $Body) {
        $request.ContentType = 'application/json; charset=utf-8'
        $request.Body = ConvertTo-Json -InputObject $Body -Depth 20 -Compress
    }
    try { Invoke-RestMethod @request }
    catch { throw "EMQX $Method $Path failed: $($_.Exception.Message)" }
}
Push-Location $EmqxRoot
try {
    $setupOutput = & $ctl admins add $setupUser $setupPassword 'TomatoSmartSetup' 2>&1
    if ($LASTEXITCODE -ne 0 -or ($setupOutput -join "`n") -match 'Usage:|Error|error') { throw ('Failed to create temporary EMQX setup account: ' + ($setupOutput -join "`n").Replace($setupPassword,'[REDACTED]')) }
    $setupCreated = $true
    $login = Emqx-Api 'POST' '/login' @{username=$setupUser;password=$setupPassword}
    $headers.Authorization = 'Bearer ' + $login.token
    $authId = 'password_based:built_in_database'
    $authPath = '/authentication/' + [uri]::EscapeDataString($authId)
    $authenticators = Emqx-Api 'GET' '/authentication'
    $authConfig = @{mechanism='password_based';backend='built_in_database';enable=$true;user_id_type='username';password_hash_algorithm=@{name='sha256';salt_position='suffix'}}
    if ($authenticators.id -contains $authId) {
        # Preserve the existing hash algorithm so other users remain valid.
        $existing = $authenticators | Where-Object id -eq $authId
        if ($existing.user_id_type -ne 'username') { throw 'Existing password authentication uses client IDs; review before changing it.' }
        if (-not $existing.enable) { $existing.enable=$true; Emqx-Api 'PUT' $authPath $existing | Out-Null }
    } else { Emqx-Api 'POST' '/authentication' $authConfig | Out-Null }
    Emqx-Api 'PUT' "$authPath/position/front" | Out-Null
    $users = (Emqx-Api 'GET' "$authPath/users?limit=1000").data
    foreach ($account in @(@{user_id=$hardwareUser;password=$hardwarePassword;is_superuser=$false}, @{user_id='tomatosmart-platform';password=$platformPassword;is_superuser=$false})) {
        if ($users.user_id -contains $account.user_id) {
            Emqx-Api 'PUT' ($authPath + '/users/' + [uri]::EscapeDataString($account.user_id)) @{password=$account.password;is_superuser=$false} | Out-Null
        } else { Emqx-Api 'POST' "$authPath/users" $account | Out-Null }
    }
    $sources = (Emqx-Api 'GET' '/authorization/sources').sources
    if ($sources.type -notcontains 'built_in_database') {
        Emqx-Api 'POST' '/authorization/sources' @{type='built_in_database';enable=$true} | Out-Null
    } elseif (-not ($sources | Where-Object type -eq 'built_in_database').enable) {
        Emqx-Api 'PUT' '/authorization/sources/built_in_database' @{type='built_in_database';enable=$true} | Out-Null
    }
    Emqx-Api 'POST' '/authorization/sources/built_in_database/move' @{position='front'} | Out-Null
    $root = 'tomato_hnsw0001'
    $upstream = @('telemetry','state','availability','result')
    $hardwareRules = @(@{permission='allow';action='subscribe';topic="$root/set";qos=@('0')})
    $platformRules = @(@{permission='allow';action='publish';topic="$root/set";qos=@('0');retain='false'})
    foreach ($topic in $upstream) {
        $retention = if ($topic -in @('state','availability')) { 'all' } else { 'false' }
        $hardwareRules += @{permission='allow';action='publish';topic="$root/$topic";qos=@('0');retain=$retention}
        $platformRules += @{permission='allow';action='subscribe';topic="$root/$topic";qos=@('0')}
    }
    $hardwareRules += @{permission='deny';action='all';topic='#'}
    $platformRules += @{permission='deny';action='all';topic='#'}
    $aclUsers = @(@{username=$hardwareUser;rules=$hardwareRules}, @{username='tomatosmart-platform';rules=$platformRules})
    Emqx-Api 'POST' '/authorization/sources/built_in_database/rules/users' $aclUsers | Out-Null
    Emqx-Api 'DELETE' '/authorization/cache' | Out-Null
    $ruleName = 'TomatoSmart-MQTT-1883'
    if (Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue) {
        Set-NetFirewallRule -Name $ruleName -Enabled True -Direction Inbound -Action Allow -Profile Any | Out-Null
    } else {
        New-NetFirewallRule -Name $ruleName -DisplayName 'TomatoSmart local EMQX MQTT 1883' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 1883 -RemoteAddress LocalSubnet -Profile Any | Out-Null
    }
    [pscustomobject]@{broker='127.0.0.1:1883';hardware_broker=$hardwareBroker;hardware_user=$hardwareUser;platform_user='tomatosmart-platform';authentication='password_based:built_in_database';root=$root;qos=0;firewall_rule=$ruleName;firmware_sha256=(Get-FileHash -Algorithm SHA256 -LiteralPath $HardwareSource).Hash} | ConvertTo-Json
} finally {
    if ($setupCreated) {
        $cleanupOutput = & $ctl admins del $setupUser 2>&1
        if ($LASTEXITCODE -ne 0) { Write-Warning "Remove temporary dashboard account: $setupUser" }
    }
    Pop-Location
}
