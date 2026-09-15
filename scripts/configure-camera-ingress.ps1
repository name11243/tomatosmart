# Run with administrator rights on the PC receiving the ESP32-P4 uploads.
$ErrorActionPreference = 'Stop'
$cameraRuleName = 'TomatoSmart-Camera-500'
$cameraRule = Get-NetFirewallRule -Name $cameraRuleName -ErrorAction SilentlyContinue
if ($cameraRule) {
    $cameraRule | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Any
    $cameraRule | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort 500
    $cameraRule | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress LocalSubnet
} else {
    New-NetFirewallRule -Name $cameraRuleName -DisplayName 'TomatoSmart ESP32-P4 photo upload (TCP 500)' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 500 -RemoteAddress LocalSubnet -Profile Any | Out-Null
}
Get-NetFirewallRule -Name $cameraRuleName | Select-Object Name, Enabled, Direction, Action
