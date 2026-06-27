# Place kaggle.json / access_token and download competition data
$ErrorActionPreference = "Stop"
$comp = "pokemon-tcg-ai-battle-challenge-strategy"
$kdir = "$env:USERPROFILE\.kaggle"
$dataDir = Join-Path $PSScriptRoot "data"

# Auth check: need either kaggle.json or access_token
$hasJson  = Test-Path "$kdir\kaggle.json"
$hasToken = Test-Path "$kdir\access_token"
if (-not ($hasJson -or $hasToken)) {
    # try to grab kaggle.json from Downloads automatically
    $dl = "$env:USERPROFILE\Downloads\kaggle.json"
    if (Test-Path $dl) {
        if (-not (Test-Path $kdir)) { New-Item -ItemType Directory -Path $kdir | Out-Null }
        Move-Item $dl "$kdir\kaggle.json" -Force
        Write-Host "Moved kaggle.json to $kdir" -ForegroundColor Green
    } else {
        Write-Host "No Kaggle credentials found. Put kaggle.json or access_token in $kdir" -ForegroundColor Yellow
        exit 1
    }
}

if (-not (Test-Path $dataDir)) { New-Item -ItemType Directory -Path $dataDir | Out-Null }
Write-Host "Downloading competition data..." -ForegroundColor Cyan
python -m kaggle competitions download -c $comp -p $dataDir

$zip = Join-Path $dataDir "$comp.zip"
if (Test-Path $zip) {
    Expand-Archive -Path $zip -DestinationPath $dataDir -Force
    Write-Host "Extracted to $dataDir" -ForegroundColor Green
    Get-ChildItem $dataDir -Name
}
