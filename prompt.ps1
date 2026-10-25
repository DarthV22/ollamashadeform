param(
    [Parameter(Mandatory = $true)][string]$ipAddress,
    [Parameter(Mandatory = $true)][string]$model,
    [string]$prompt = $env:OLLAMASHADE_PROMPT
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
. (Join-Path $PSScriptRoot 'transport.ps1')
try {
    if ([string]::IsNullOrWhiteSpace($prompt)) { throw 'A prompt is required.' }
    $config = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config/config.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $response = Invoke-OllamaOverSsh -Config $config -Path 'generate' -Body @{ model = $model; prompt = $prompt; stream = $false }
    if ($response.error) { throw $response.error }
    if ($null -eq $response.response -or $response.done -ne $true) { throw 'Ollama returned an incomplete response.' }
    $response.response
} catch {
    [Console]::Error.WriteLine("Generation failed: $_")
    exit 1
}
