$ErrorActionPreference = 'Stop'
$venvPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'

if (!(Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    [Console]::Error.WriteLine('Run .\setup.ps1 first to create the project virtual environment.')
    exit 1
}

& $venvPython (Join-Path $PSScriptRoot 'app.py')
exit $LASTEXITCODE
