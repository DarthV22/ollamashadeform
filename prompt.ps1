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
    $null = Invoke-OllamaOverSsh -Config $config -Path 'generate' -Stream -Body @{ model = $model; prompt = $prompt; stream = $true; options = @{ num_ctx = 8192 } }
} catch {
    [Console]::Error.WriteLine("Generation failed: $_")
    exit 1
}
