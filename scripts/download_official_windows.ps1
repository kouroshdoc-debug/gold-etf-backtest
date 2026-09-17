param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$outputDirectory = Join-Path $RepoRoot "data\official"
New-Item -ItemType Directory -Force -Path $outputDirectory | Out-Null

$instruments = @(
    @{ Symbol = "عیار"; Slug = "ayar"; InsCode = "34144395039913458" },
    @{ Symbol = "گوهر"; Slug = "gohar"; InsCode = "12390706505809150" },
    @{ Symbol = "کهربا"; Slug = "kahroba"; InsCode = "25559236668122210" }
)

$summary = @()
foreach ($instrument in $instruments) {
    $uri = "https://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceDailyList/$($instrument.InsCode)/0"
    Write-Host "Downloading $($instrument.Symbol) from TSETMC..."
    $payload = Invoke-RestMethod -Uri $uri -Headers @{ "User-Agent" = "gold-etf-backtest/1.0" } -TimeoutSec 90
    $rows = @($payload.closingPriceDaily)
    if ($rows.Count -lt 500) {
        throw "$($instrument.Symbol): history is unexpectedly short ($($rows.Count) rows)."
    }
    $codes = @($rows | Where-Object { $_.insCode } | ForEach-Object { [string]$_.insCode } | Sort-Object -Unique)
    if ($codes.Count -ne 1 -or $codes[0] -ne $instrument.InsCode) {
        throw "$($instrument.Symbol): InsCode validation failed. Found: $($codes -join ', ')"
    }
    $dates = @($rows | ForEach-Object { [int64]$_.dEven } | Sort-Object)
    $destination = Join-Path $outputDirectory "$($instrument.Slug).json"
    $json = $payload | ConvertTo-Json -Depth 8 -Compress
    [System.IO.File]::WriteAllText($destination, $json, [System.Text.UTF8Encoding]::new($false))
    $hash = (Get-FileHash -Path $destination -Algorithm SHA256).Hash.ToLowerInvariant()
    $summary += [pscustomobject]@{
        Symbol = $instrument.Symbol
        InsCode = $instrument.InsCode
        Rows = $rows.Count
        FirstDate = $dates[0]
        LastDate = $dates[-1]
        File = $destination
        SHA256 = $hash
    }
}

$summary | Format-Table -AutoSize
Write-Host "Official snapshots are ready. Review the table, then commit data\official\*.json with GitHub Desktop."
