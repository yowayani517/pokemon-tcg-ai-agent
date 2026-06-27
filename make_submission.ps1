# Build submission.tar.gz (main.py and deck.csv at top level)
$ErrorActionPreference = "Stop"
$agentDir = Join-Path $PSScriptRoot "agent"
$out = Join-Path $PSScriptRoot "submission.tar.gz"
if (-not (Test-Path (Join-Path $agentDir "main.py")))  { throw "main.py not found" }
if (-not (Test-Path (Join-Path $agentDir "deck.csv"))) { throw "deck.csv not found" }
# Pack from inside agent/ so main.py and deck.csv sit at the archive top level (not nested)
tar -czvf $out -C $agentDir main.py deck.csv
Write-Host "Created: $out" -ForegroundColor Green
tar -tzf $out
