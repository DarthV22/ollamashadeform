param(
    [Parameter(Mandatory = $true)][string]$model,
    [string]$apiKey = $env:SHADEFORM_API_KEY
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$headers = @{ 'X-API-KEY' = $apiKey }
$instanceId = $null
$createAttempted = $false
$configPath = Join-Path $PSScriptRoot 'config/config.json'
. (Join-Path $PSScriptRoot 'transport.ps1')

function Save-InstanceState($id, $ipAddress, $active) {
    $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $config | Add-Member -NotePropertyName instance_id -NotePropertyValue $id -Force
    $config | Add-Member -NotePropertyName ip_address -NotePropertyValue $ipAddress -Force
    $config | Add-Member -NotePropertyName active -NotePropertyValue $active -Force
    if ($script:sshUser) {
        $config | Add-Member -NotePropertyName ssh_user -NotePropertyValue $script:sshUser -Force
        $config | Add-Member -NotePropertyName ssh_port -NotePropertyValue $script:sshPort -Force
    }
    $temporary = [IO.Path]::ChangeExtension($configPath, '.tmp')
    $json = $config | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($temporary, $json, (New-Object System.Text.UTF8Encoding))
    Move-Item -LiteralPath $temporary -Destination $configPath -Force
}

try {
    if ([string]::IsNullOrWhiteSpace($apiKey)) { throw 'A Shadeform API key is required.' }
    $existing = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($existing.instance_id) { throw 'An instance is already recorded. Delete it before starting another.' }
    if (!$existing.ssh_key_id -or $existing.ssh_key_id -eq 'YOUR_SHADEFORM_SSH_KEY_ID') { throw 'Set ssh_key_id to a public key registered in Shadeform.' }
    if (!$existing.ssh_private_key -or !(Test-Path -LiteralPath ([Environment]::ExpandEnvironmentVariables($existing.ssh_private_key)) -PathType Leaf)) { throw 'Set ssh_private_key to an existing local SSH private key.' }
    $null = Get-Command ssh -ErrorAction Stop

    $response = Invoke-RestMethod -Uri 'https://api.shadeform.ai/v1/instances/types?gpu_type=A6000&available=true&sort=price' -Headers $headers -Method Get -TimeoutSec 60
    $offers = @(foreach ($type in $response.instance_types) {
        foreach ($availability in $type.availability) {
            if ($availability.available -eq $true -and (!$availability.rental_type -or $availability.rental_type -eq 'on_demand')) {
                [PSCustomObject]@{ Type = $type; Region = $availability.region; Price = [decimal]$type.hourly_price }
            }
        }
    })
    $offer = $offers | Sort-Object Price | Select-Object -First 1
    if (!$offer -or !$offer.Type.shade_instance_type -or !$offer.Region) { throw 'No available on-demand A6000 instances were found.' }
    $instance = $offer.Type
    Write-Host "Instance: $($instance.shade_instance_type) on $($instance.cloud), $($offer.Region)"
    Write-Host "Price: $($offer.Price) cents per hour. Charges continue until deletion."

    $launchScript = "#!/bin/bash`nset -euo pipefail`nsudo docker run -d --restart unless-stopped --gpus all --name ollamashade -p 127.0.0.1:11434:11434 -v ollama:/root/.ollama ollama/ollama:latest`n"
    $body = @{
        cloud = $instance.cloud
        region = $offer.Region
        shade_instance_type = $instance.shade_instance_type
        shade_cloud = $true
        rental_type = 'on_demand'
        name = 'ollamashade'
        ssh_key_id = $existing.ssh_key_id
        launch_configuration = @{
            type = 'script'
            script_configuration = @{
                base64_script = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($launchScript))
            }
        }
    }
    $createAttempted = $true
    $created = Invoke-RestMethod -Uri 'https://api.shadeform.ai/v1/instances/create' -Headers $headers -Method Post -Body ($body | ConvertTo-Json -Depth 10) -ContentType 'application/json' -TimeoutSec 60
    $instanceId = $created.id
    if (!$instanceId) { throw 'Create response did not contain an instance ID. Check the Shadeform dashboard before retrying.' }
    Write-Host "Instance created: $instanceId"
    # Persist the ID before waiting so an interrupted startup remains recoverable.
    Save-InstanceState $instanceId $null $false

    $deadline = (Get-Date).AddMinutes(20)
    do {
        $status = Invoke-RestMethod -Uri "https://api.shadeform.ai/v1/instances/$instanceId/info" -Headers $headers -Method Get -TimeoutSec 60
        Write-Host "Status: $($status.status) - IP: $($status.ip)"
        if ($status.status -in @('error', 'failed', 'deleted', 'deleting', 'terminated')) { throw "Instance entered state: $($status.status)" }
        if ($status.status -eq 'active' -and $status.ip) { break }
        if ((Get-Date) -gt $deadline) { throw 'Timed out waiting for the instance to become active.' }
        Start-Sleep -Seconds 10
    } while ($true)
    $ipAddress = $status.ip
    $script:sshUser = $status.ssh_user
    $script:sshPort = $status.ssh_port
    if (!$script:sshUser -or !$script:sshPort) { throw 'Shadeform did not return SSH connection details.' }
    Save-InstanceState $instanceId $ipAddress $false
    $connection = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json

    # Probe readiness separately: repeatedly restarting a model download can never finish.
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        Write-Host "Checking SSH and Ollama readiness ($($attempt + 1)/60)..."
        try {
            $null = Invoke-OllamaOverSsh -Config $connection -Path 'version'
            $ready = $true
            break
        } catch {
            Write-Host "Not ready yet: $_"
            Start-Sleep -Seconds 5
        }
    }
    if (!$ready) { throw 'Ollama did not become reachable.' }
    Write-Host "Pulling model $model. This can take several minutes..."
    $pull = Invoke-OllamaOverSsh -Config $connection -Path 'pull' -Body @{ model = $model; stream = $false }
    if ($pull.error -or $pull.status -ne 'success') { throw "Model download failed: $($pull.error)" }
    Save-InstanceState $instanceId $ipAddress $true
    @{ instance_id = $instanceId; ip_address = $ipAddress; model = $model; active = $true } | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine("Startup failed: $_")
    if ($instanceId) {
        try {
            $null = Invoke-RestMethod -Uri "https://api.shadeform.ai/v1/instances/$instanceId/delete" -Headers $headers -Method Post -TimeoutSec 60
            Save-InstanceState $null $null $false
            [Console]::Error.WriteLine('The failed instance was deleted.')
        } catch {
            [Console]::Error.WriteLine("Could not complete cleanup. Delete instance $instanceId in the Shadeform dashboard. Error: $_")
        }
    } elseif ($createAttempted) {
        [Console]::Error.WriteLine('If a create request timed out, check the Shadeform dashboard before retrying; it may have succeeded remotely.')
    } else {
        [Console]::Error.WriteLine('No instance was created. Fix the issue above and try again.')
    }
    exit 1
}
