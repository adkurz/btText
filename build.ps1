param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location $ProjectRoot
try {
    Write-Host "Validating translation sources..."
    & $Python tools/translations.py check
    if ($LASTEXITCODE -ne 0) {
        throw "Translation validation failed with exit code $LASTEXITCODE."
    }

    Write-Host "Compiling runtime translation catalogs..."
    & $Python tools/translations.py compile
    if ($LASTEXITCODE -ne 0) {
        throw "Translation compilation failed with exit code $LASTEXITCODE."
    }

    Write-Host "Running tests..."
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed with exit code $LASTEXITCODE."
    }

    Write-Host "Build checks completed successfully."
}
finally {
    Pop-Location
}
