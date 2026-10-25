param(
    # Optional full path to a Python 3.10+ interpreter.
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$venvPath = Join-Path $PSScriptRoot '.venv'
$venvPython = Join-Path $venvPath 'Scripts/python.exe'
$versionCheck = 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'

try {
    if (!(Test-Path -LiteralPath $venvPython -PathType Leaf)) {
        if (Test-Path -LiteralPath $venvPath) {
            throw 'The .venv folder is incomplete. Rename or remove it, then run setup again.'
        }

        $pythonArguments = @()
        if (!$Python) {
            foreach ($candidate in @('py', 'python')) {
                if (!(Get-Command $candidate -ErrorAction SilentlyContinue)) { continue }
                $candidateArguments = if ($candidate -eq 'py') { @('-3') } else { @() }
                try {
                    & $candidate @candidateArguments -c $versionCheck 2>$null
                    if ($LASTEXITCODE -eq 0) {
                        $Python = $candidate
                        $pythonArguments = $candidateArguments
                        break
                    }
                } catch { }
            }
        }
        if (!$Python) {
            throw 'Install Python 3.10 or later, then rerun setup. You can also use: .\setup.ps1 -Python C:\path\to\python.exe'
        }
        & $Python @pythonArguments -c $versionCheck
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.10 or later is required.' }

        Write-Host 'Creating .venv...'
        & $Python @pythonArguments -m venv $venvPath
        if ($LASTEXITCODE -ne 0) { throw 'Could not create .venv. Check your Python installation.' }
    }

    & $venvPython -c $versionCheck
    if ($LASTEXITCODE -ne 0) { throw 'The existing .venv needs Python 3.10 or later. Recreate it with a supported Python installation.' }

    $configPath = Join-Path $PSScriptRoot 'config/config.json'
    if (!(Test-Path -LiteralPath $configPath)) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'config/config.example.json') -Destination $configPath
        Write-Host 'Created config/config.json. Edit it with your Shadeform API key and SSH settings.'
    } else {
        $config = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($config -isnot [PSCustomObject]) { throw 'config/config.json must contain a JSON object.' }
        $defaults = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'config/config.example.json') -Raw -Encoding UTF8 | ConvertFrom-Json
        $added = @()
        foreach ($property in $defaults.PSObject.Properties) {
            if ($config.PSObject.Properties.Name -notcontains $property.Name) {
                $config | Add-Member -NotePropertyName $property.Name -NotePropertyValue $property.Value
                $added += $property.Name
            }
        }
        if ($added.Count -gt 0) {
            $temporary = [IO.Path]::ChangeExtension($configPath, '.tmp')
            [IO.File]::WriteAllText($temporary, ($config | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding))
            Move-Item -LiteralPath $temporary -Destination $configPath -Force
            Write-Host "Added missing configuration fields: $($added -join ', '). Review config/config.json before starting AI."
        }
    }

    Write-Host 'Setup complete. No third-party Python packages are required.'
    Write-Host 'Run: .\run.ps1'
} catch {
    [Console]::Error.WriteLine("Setup failed: $_")
    exit 1
}
