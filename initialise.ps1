param(
    [string]$apiKey,
    [string]$model
)

$headers = @{
    "X-API-KEY" = $apiKey
}


# ============================================================
# Find the cheapest available A6000 instance
# ============================================================

$url = "https://api.shadeform.ai/v1/instances/types?gpu_type=A6000&available=true&sort=price"

$response = Invoke-RestMethod `
    -Uri $url `
    -Headers $headers `
    -Method Get

$instance = $response.instance_types[0]

$gpu = $instance.gpu_type
$price = $instance.hourly_price
$memory = $instance.memory_in_gb
$vcpus = $instance.vcpus
$cloud = $instance.cloud
$region = $instance.availability[0].region
$cloudInstanceType = $instance.cloud_instance_type

Write-Host "GPU: $gpu"
Write-Host "Price: $price per hour"
Write-Host "Memory: $memory GB"
Write-Host "vCPUs: $vcpus"
Write-Host "Cloud: $cloud"
Write-Host "Region: $region"


# ============================================================
# Create Shadeform instance
# ============================================================

$body = @{
    cloud = $cloud
    region = $region
    shade_instance_type = $gpu
    shade_cloud = $true
    name = "ollamashade"
    launch_configuration = @{
        type = "docker"
        docker_configuration = @{
            image = "ollama/ollama:latest"
            envs = @(
                @{
                    name = "OLLAMA_HOST"
                    value = "0.0.0.0"
                }
            )
            port_mappings = @(
                @{
                    container_port = 11434
                    host_port = 11434
                }
            )
        }
    }
}

$createResponse = Invoke-RestMethod `
    -Uri "https://api.shadeform.ai/v1/instances/create" `
    -Headers $headers `
    -Method Post `
    -Body (ConvertTo-Json -InputObject $body -Depth 10) `
    -ContentType "application/json"

$instanceId = $createResponse.id

Write-Host "Instance created: $instanceId"


# ============================================================
# Wait for instance to become active
# ============================================================

do {

    $status = Invoke-RestMethod `
        -Uri "https://api.shadeform.ai/v1/instances/$instanceId/info" `
        -Headers $headers `
        -Method Get

    Write-Host "Status: $($status.status) - IP: $($status.ip)"

    Start-Sleep -Seconds 10

} while ($status.status -ne "active")


$ipAddress = $status.ip

Write-Host "Instance is active."
Write-Host "IP address: $ipAddress"


# ============================================================
# Pull Ollama model
# ============================================================

$maxRetries = 30
$retryCount = 0
$pullSuccess = $false

while ($retryCount -lt $maxRetries -and -not $pullSuccess) {

    try {

        Write-Host "Attempting to pull $model (attempt $($retryCount + 1)/$maxRetries)..."

        Invoke-RestMethod `
            -Uri "http://$($ipAddress):11434/api/pull" `
            -Method Post `
            -Body (ConvertTo-Json @{ model = $model }) `
            -ContentType "application/json" `
            -TimeoutSec 10

        $pullSuccess = $true

        Write-Host "Model pulled successfully!"

    }

    catch {

        $retryCount++

        if ($retryCount -lt $maxRetries) {

            Write-Host "Pull failed, waiting 5 seconds before retry..."
            Start-Sleep -Seconds 5

        }

        else {

            Write-Host "Failed to pull model after $maxRetries attempts"
            Write-Host "Error: $_"

            exit 1
        }
    }
}


# ============================================================
# Return structured information to Python
# ============================================================

$result = @{
    instance_id = $instanceId
    ip_address  = $ipAddress
    model       = $model
    active      = $true
}

$result | ConvertTo-Json -Compress
