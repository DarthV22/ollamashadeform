param([string]$scenario, [string]$target)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$env:SHADEFORM_API_KEY = 'test-key'
function Log($text) { Add-Content -LiteralPath (Join-Path $PSScriptRoot 'events.txt') -Value $text }
function Start-Sleep { param($Seconds) }
function Invoke-RestMethod {
    param($Uri, $Headers, $Method, $TimeoutSec, $Body, $ContentType)
    if ($Uri -like '*instances/types*') {
        if ($scenario -eq 'no-capacity') { return @{ instance_types = @() } }
        return @{ instance_types = @(@{
            cloud = 'test-cloud'; gpu_type = 'A6000'; shade_instance_type = 'correct-type'; hourly_price = 100
            availability = @(
                @{ available = $false; region = 'unavailable' },
                @{ available = $true; region = 'spot-only'; rental_type = 'spot' },
                @{ available = $true; region = 'available-region'; rental_type = 'on_demand' }
            )
        }) }
    }
    if ($Uri -like '*instances/create') {
        $data = $Body | ConvertFrom-Json
        Log "create:$($data.shade_instance_type):$($data.region)"
        $launch = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($data.launch_configuration.script_configuration.base64_script))
        if ($launch -notlike '*127.0.0.1:11434:11434*') { throw 'Ollama exposed publicly' }
        Log 'private-binding'
        return @{ id = 'new-instance' }
    }
    if ($Uri -like '*/info') { return @{ status = 'active'; ip = '192.0.2.1'; ssh_user = 'shadeform'; ssh_port = 2222 } }
    if ($Uri -like '*/delete') {
        Log 'delete'
        if ($scenario -in @('cleanup-failure', 'delete-failure')) { throw 'simulated delete error' }
        return @{}
    }
    throw "Unexpected network request: $Uri"
}
function ssh {
    $global:LASTEXITCODE = 0
    $command = $args[-1]
    if ($command -like '*api/version*') { return '{"version":"test"}' }
    if ($command -like '*api/pull*') {
        if ($scenario -in @('pull-failure', 'cleanup-failure')) { return '{"error":"bad model"}' }
        return '{"status":"success"}'
    }
    if ($command -like '*api/generate*') {
        $payload = $command.Split("'")[3]
        $body = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($payload)) | ConvertFrom-Json
        if ($body.prompt -ne 'Say "hello"; café $HOME') { throw 'Prompt was corrupted' }
        Log 'unicode-payload'
        return '{"response":"Hello","done":true}'
    }
    throw 'Unexpected SSH command'
}
if ($target -eq 'clear.ps1') {
    & (Join-Path $PSScriptRoot $target) 'test-instance'
} elseif ($target -eq 'prompt.ps1') {
    $path = Join-Path $PSScriptRoot 'config/config.json'
    $config = Get-Content $path -Raw | ConvertFrom-Json
    $config | Add-Member -NotePropertyName ssh_user -NotePropertyValue 'shadeform'
    $config | Add-Member -NotePropertyName ssh_port -NotePropertyValue 2222
    $config.ip_address = '192.0.2.1'
    $config | ConvertTo-Json | Set-Content -Encoding utf8 $path
    & (Join-Path $PSScriptRoot $target) '192.0.2.1' 'test-model' 'Say "hello"; café $HOME'
} else {
    & (Join-Path $PSScriptRoot $target) 'test-model'
}
exit $LASTEXITCODE
