# start.ps1 - Launch the song request board for a live gig:
#   1. Load DJ_KEY / PUBLIC_URL from .env
#   2. Start the FastAPI app (uvicorn) in its own window
#   3. Start an ngrok tunnel to that app in its own window
#   4. Print the guest URL and the DJ URL (with key) to copy/paste

# Resolve paths relative to this script's own location (not the caller's
# current directory), so this works no matter where it's invoked from.
$envPath = Join-Path $PSScriptRoot ".env"

if (-not (Test-Path $envPath)) {
    Write-Error "Missing .env file at $envPath`nCopy .env.example to .env and fill in DJ_KEY and PUBLIC_URL before running this script."
    exit 1
}

# Parse the .env file ourselves (KEY=VALUE per line) instead of relying on
# a PowerShell dotenv module, since one may not be installed.
Get-Content $envPath | ForEach-Object {
    $line = $_.Trim()

    # Skip blank lines and comments.
    if ($line -eq "" -or $line.StartsWith("#")) {
        return
    }

    $parts = $line -split "=", 2
    if ($parts.Count -ne 2) {
        return
    }

    $key = $parts[0].Trim()
    $value = $parts[1].Trim()

    # Strip a single matching pair of surrounding quotes, if present.
    if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
        ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
    }

    # Set it on the current process's environment so it is inherited by
    # child processes started below (uvicorn, ngrok).
    Set-Item -Path "Env:$key" -Value $value
}

# Make sure the values we actually need came through.
if ([string]::IsNullOrWhiteSpace($env:DJ_KEY)) {
    Write-Error "DJ_KEY is missing or empty after loading .env. Check $envPath."
    exit 1
}
if ([string]::IsNullOrWhiteSpace($env:PUBLIC_URL)) {
    Write-Error "PUBLIC_URL is missing or empty after loading .env. Check $envPath."
    exit 1
}

$pythonExe = Join-Path $PSScriptRoot ".venv312\Scripts\python.exe"

# Start-Process opens a separate console window for a console executable
# by default, which is exactly what we want here (one window for the app,
# one for the tunnel), so no extra window-handling flags are needed.
# The child process inherits this script's environment, including the
# DJ_KEY / PUBLIC_URL we just set above.
Start-Process -FilePath $pythonExe `
    -ArgumentList "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8000" `
    -WorkingDirectory $PSScriptRoot

Start-Process -FilePath "ngrok" `
    -ArgumentList "http", "8000", "--url", $env:PUBLIC_URL

$guestUrl = $env:PUBLIC_URL
$djUrl = "$($env:PUBLIC_URL)/dj?key=$($env:DJ_KEY)"

Write-Host ""
Write-Host "Guest URL (share with the crowd):"
Write-Host "  $guestUrl"
Write-Host ""
Write-Host "DJ URL (keep private):"
Write-Host "  $djUrl"
Write-Host ""
