param(
    [string]$ipAddress,
    [string]$model,
    [string]$prompt
)

$maxRetries = 10
$retryCount = 0
$generateSuccess = $false


while ($retryCount -lt $maxRetries -and -not $generateSuccess) {

    try {

        $response = Invoke-RestMethod `
            -Uri "http://$($ipAddress):11434/api/generate" `
            -Method Post `
            -Body (@{
                model = $model
                prompt = $prompt
                stream = $false
            } | ConvertTo-Json) `
            -ContentType "application/json" `
            -TimeoutSec 60

        $response.response

        $generateSuccess = $true

    }

    catch {

        $retryCount++

        if ($retryCount -lt $maxRetries) {

            Write-Host "Generate request failed. Retrying in 5 seconds..."
            Start-Sleep -Seconds 5

        }

        else {

            Write-Host "Failed to generate response after $maxRetries attempts."
            Write-Host "Error: $_"

            exit 1
        }
    }
}