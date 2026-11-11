# Load temporary sandbox credentials into this PowerShell session.
$envPath = Join-Path $PSScriptRoot '../config/sandbox.env'
Get-Content -LiteralPath $envPath | ForEach-Object {
    if ($_ -match '^(AWS_[A-Z_]+)=(.*)$') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2].Trim().Trim('"').Trim("'"), 'Process')
    }
}
$env:AWS_PAGER = ''
Write-Host 'AWS sandbox environment loaded for this session.'
