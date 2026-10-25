param(
    [Parameter(Mandatory = $true)][string]$instanceId,
    [string]$apiKey = $env:SHADEFORM_API_KEY
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
try {
    if ([string]::IsNullOrWhiteSpace($instanceId)) { throw 'No instance ID was provided.' }
    if ([string]::IsNullOrWhiteSpace($apiKey)) { throw 'A Shadeform API key is required.' }
    $headers = @{ 'X-API-KEY' = $apiKey }
    $null = Invoke-RestMethod -Uri "https://api.shadeform.ai/v1/instances/$instanceId/delete" -Headers $headers -Method Post -TimeoutSec 60
    @{ deleted = $true; instance_id = $instanceId } | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine("Deletion failed; local instance details have been retained. Error: $_")
    exit 1
}
