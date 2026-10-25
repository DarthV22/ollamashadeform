# Shared SSH transport. Ollama listens only on the remote loopback interface.
function Invoke-OllamaOverSsh {
    param(
        [Parameter(Mandatory = $true)]$Config,
        [Parameter(Mandatory = $true)][string]$Path,
        $Body = $null
    )
    if ($Path -notin @('version', 'pull', 'generate')) { throw 'Unsupported Ollama endpoint.' }
    if (!$Config.ssh_user -or !$Config.ssh_port -or !$Config.ip_address) { throw 'SSH connection details are missing. Start a new instance.' }
    if ($Config.ssh_user -notmatch '^[a-zA-Z0-9_-]+$' -or $Config.ip_address -notmatch '^[a-fA-F0-9.:]+$') { throw 'Invalid SSH connection details.' }
    $keyPath = [Environment]::ExpandEnvironmentVariables($Config.ssh_private_key)
    if (!(Test-Path -LiteralPath $keyPath -PathType Leaf)) { throw 'The configured SSH private key does not exist.' }
    $sshArgs = @('-n', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=15', '-o', 'ServerAliveCountMax=3', '-o', 'StrictHostKeyChecking=accept-new', '-i', $keyPath, '-p', [string]$Config.ssh_port, "$($Config.ssh_user)@$($Config.ip_address)")
    $url = "http://127.0.0.1:11434/api/$Path"
    if ($null -eq $Body) {
        $output = & ssh @sshArgs "curl --fail --silent --show-error --max-time 10 $url"
    } else {
        # Base64 transports arbitrary Unicode and quotes without remote shell interpolation.
        $json = $Body | ConvertTo-Json -Depth 10 -Compress
        $payload = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))
        $timeout = if ($Path -eq 'pull') { 3600 } else { 600 }
        $output = & ssh @sshArgs "printf '%s' '$payload' | base64 --decode | curl --fail --silent --show-error --max-time $timeout -H 'Content-Type: application/json' --data-binary @- $url"
    }
    if ($LASTEXITCODE -ne 0) { throw "SSH/Ollama request failed (exit $LASTEXITCODE). Check your SSH key and the instance in Shadeform." }
    $response = ($output -join "`n") | ConvertFrom-Json
    if ($response.error) { throw $response.error }
    return $response
}
