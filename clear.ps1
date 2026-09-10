param(
    [string]$apiKey,
    [string]$instanceId
)

$headers = @{
    "X-API-KEY" = $apiKey
}

if ([string]::IsNullOrWhiteSpace($instanceId)) {

    Write-Host "No instance ID was provided."
    exit 1
}

Write-Host "Deleting instance: $instanceId"

$response = Invoke-RestMethod `
    -Uri "https://api.shadeform.ai/v1/instances/$instanceId/delete" `
    -Headers $headers `
    -Method Post

Write-Host "Instance deleted successfully."

$result = @{
    deleted = $true
    instance_id = $instanceId
}

$result | ConvertTo-Json -Compress