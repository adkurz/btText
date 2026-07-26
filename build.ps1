param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$VirtualEnvironmentDirectory = Join-Path $ProjectRoot ".venv"
$VirtualEnvironmentPython = Join-Path (
    $VirtualEnvironmentDirectory
) "Scripts\python.exe"
$BuildDirectory = Join-Path $ProjectRoot "build"
$ExpectedBuildDirectory = [IO.Path]::GetFullPath(
    (Join-Path $ProjectRoot "build")
)
$ResolvedBuildDirectory = [IO.Path]::GetFullPath($BuildDirectory)
if ($ResolvedBuildDirectory -ne $ExpectedBuildDirectory) {
    throw "Refusing to use an unexpected build directory."
}

$TemporaryRoot = Join-Path (
    [IO.Path]::GetTempPath()
) ("btText-build-" + [guid]::NewGuid().ToString("N"))
$WorkDirectory = Join-Path $TemporaryRoot "work"
$DistributionDirectory = Join-Path $TemporaryRoot "dist"

Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath $VirtualEnvironmentPython -PathType Leaf)) {
        if (Test-Path -LiteralPath $VirtualEnvironmentDirectory) {
            throw "The .venv directory is incomplete. Remove or repair it."
        }
        Write-Host "Creating project virtual environment..."
        & $Python -m venv $VirtualEnvironmentDirectory
        if ($LASTEXITCODE -ne 0) {
            throw "Virtual environment creation failed: $LASTEXITCODE."
        }
    }

    Write-Host "Installing build dependencies in .venv..."
    & $VirtualEnvironmentPython -m pip install `
        --disable-pip-version-check `
        -r requirements-dev.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE."
    }

    Write-Host "Validating translation sources..."
    & $VirtualEnvironmentPython tools/translations.py check
    if ($LASTEXITCODE -ne 0) {
        throw "Translation validation failed with exit code $LASTEXITCODE."
    }

    Write-Host "Compiling runtime translation catalogs..."
    & $VirtualEnvironmentPython tools/translations.py compile
    if ($LASTEXITCODE -ne 0) {
        throw "Translation compilation failed with exit code $LASTEXITCODE."
    }

    Write-Host "Running tests..."
    & $VirtualEnvironmentPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed with exit code $LASTEXITCODE."
    }

    Write-Host "Creating portable Windows application..."
    New-Item -ItemType Directory -Path $TemporaryRoot | Out-Null
    & $VirtualEnvironmentPython -m PyInstaller `
        --noconfirm `
        --clean `
        --workpath $WorkDirectory `
        --distpath $DistributionDirectory `
        btText.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    $ApplicationDirectory = Join-Path $DistributionDirectory "btText"
    $Executable = Join-Path $ApplicationDirectory "btText.exe"
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "PyInstaller did not create btText.exe."
    }

    $ForbiddenNames = @("data.db", "settings.ini", "settings.ini.tmp")
    $ForbiddenFiles = Get-ChildItem `
        -LiteralPath $ApplicationDirectory `
        -Recurse `
        -File |
        Where-Object { $_.Name -in $ForbiddenNames }
    if ($ForbiddenFiles) {
        $Paths = ($ForbiddenFiles.FullName -join ", ")
        throw "The application bundle contains forbidden user data: $Paths"
    }

    $Version = (
        & $VirtualEnvironmentPython -c "import info; print(info.version)"
    ).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Version) {
        throw "The application version could not be read from info.py."
    }
    if ($Version -notmatch "^[0-9A-Za-z._-]+$") {
        throw "The application version contains unsafe filename characters."
    }

    if (Test-Path -LiteralPath $BuildDirectory) {
        Remove-Item -LiteralPath $BuildDirectory -Recurse -Force
    }
    New-Item -ItemType Directory -Path $BuildDirectory | Out-Null
    $Archive = Join-Path $BuildDirectory (
        "btText-{0}-windows.zip" -f $Version
    )
    Compress-Archive `
        -LiteralPath $ApplicationDirectory `
        -DestinationPath $Archive `
        -CompressionLevel Optimal

    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "The btText archive was not created."
    }

    Write-Host "Build completed successfully:"
    Write-Host $Archive
}
finally {
    Pop-Location
    if (
        (Test-Path -LiteralPath $TemporaryRoot) -and
        ([IO.Path]::GetFullPath($TemporaryRoot)).StartsWith(
            [IO.Path]::GetFullPath([IO.Path]::GetTempPath()),
            [StringComparison]::OrdinalIgnoreCase
        )
    ) {
        Remove-Item -LiteralPath $TemporaryRoot -Recurse -Force
    }
}
