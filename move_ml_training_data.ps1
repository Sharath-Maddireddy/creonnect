$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$sourceDir = Join-Path $repoRoot "backend\app\tests"
$destinationDir = Join-Path $repoRoot "backend\ml\data"

New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null

$files = @(
    "train.jsonl",
    "training_data.jsonl",
    "val.jsonl"
)

foreach ($file in $files) {
    $sourcePath = Join-Path $sourceDir $file
    $destinationPath = Join-Path $destinationDir $file

    if (Test-Path $sourcePath) {
        Move-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
        Write-Host "Moved $file to backend/ml/data/"
    }
    else {
        Write-Host "Skipped $file; source file not found."
    }
}
