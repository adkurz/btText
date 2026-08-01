param(
    [string]$Python = "python",
    [switch]$PortableOnly,
    [string]$InnoCompiler = ""
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

function Resolve-InnoCompiler {
    param([string]$RequestedCompiler)

    if ($RequestedCompiler) {
        if (-not (Test-Path -LiteralPath $RequestedCompiler -PathType Leaf)) {
            throw "The specified Inno Setup compiler does not exist: $RequestedCompiler"
        }
        return [IO.Path]::GetFullPath($RequestedCompiler)
    }

    $Command = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
    if ($Command) {
        return $Command.Source
    }

    $Candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $Candidates += Join-Path (
            ${env:ProgramFiles(x86)}
        ) "Inno Setup 7\ISCC.exe"
    }
    if ($env:ProgramFiles) {
        $Candidates += Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"
    }
    foreach ($Candidate in $Candidates) {
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) {
            return $Candidate
        }
    }

    throw (
        "Inno Setup 7 was not found. Install it, pass -InnoCompiler, " +
        "or use -PortableOnly."
    )
}

function Assert-InnoSetup7 {
    param([string]$Compiler)

    $PreviousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $VersionOutput = (& $Compiler /? 2>&1 | Out-String)
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    if ($VersionOutput -notmatch "Inno Setup 7 Command-Line Compiler") {
        throw (
            "The selected compiler is not Inno Setup 7: $Compiler"
        )
    }
}

$ResolvedInnoCompiler = $null
if (-not $PortableOnly) {
    $ResolvedInnoCompiler = Resolve-InnoCompiler $InnoCompiler
    Assert-InnoSetup7 $ResolvedInnoCompiler
}

$TemporaryRoot = Join-Path (
    [IO.Path]::GetTempPath()
) ("btText-build-" + [guid]::NewGuid().ToString("N"))
$WorkDirectory = Join-Path $TemporaryRoot "work"
$DistributionDirectory = Join-Path $TemporaryRoot "dist"
$DocumentationDirectory = Join-Path $TemporaryRoot "documentation"

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

    Write-Host "Building HTML documentation..."
    & $VirtualEnvironmentPython tools/build_documentation.py `
        (Join-Path $ProjectRoot "docs") `
        $DocumentationDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Documentation build failed with exit code $LASTEXITCODE."
    }

    Write-Host "Running tests..."
    & $VirtualEnvironmentPython -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) {
        throw "Tests failed with exit code $LASTEXITCODE."
    }

    Write-Host "Creating portable Windows application..."
    New-Item -ItemType Directory -Path $TemporaryRoot -Force | Out-Null
    $env:BTTEXT_DOCUMENTATION_DIRECTORY = $DocumentationDirectory
    & $VirtualEnvironmentPython -m PyInstaller `
        --noconfirm `
        --clean `
        --workpath $WorkDirectory `
        --distpath $DistributionDirectory `
        btText.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
    Remove-Item Env:BTTEXT_DOCUMENTATION_DIRECTORY -ErrorAction SilentlyContinue

    $ApplicationDirectory = Join-Path $DistributionDirectory "btText"
    $Executable = Join-Path $ApplicationDirectory "btText.exe"
    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw "PyInstaller did not create btText.exe."
    }

    $SourceDocuments = Get-ChildItem `
        -LiteralPath (Join-Path $ProjectRoot "docs") `
        -Filter "*.md" `
        -Recurse `
        -File
    $DocumentationSourceRoot = [IO.Path]::GetFullPath(
        (Join-Path $ProjectRoot "docs")
    ).TrimEnd("\", "/")
    foreach ($SourceDocument in $SourceDocuments) {
        $RelativeDocument = $SourceDocument.FullName.Substring(
            $DocumentationSourceRoot.Length
        ).TrimStart("\", "/")
        $RelativeHtml = [IO.Path]::ChangeExtension($RelativeDocument, ".html")
        $BundledDocument = Join-Path $ApplicationDirectory (
            "_internal\docs\{0}" -f $RelativeHtml
        )
        if (-not (Test-Path -LiteralPath $BundledDocument -PathType Leaf)) {
            throw "The application bundle is missing documentation: $BundledDocument"
        }
    }

    $ApplicationCatalogs = Get-ChildItem `
        -LiteralPath (Join-Path $ProjectRoot "locale") `
        -Filter "bttext.mo" `
        -Recurse `
        -File
    foreach ($Catalog in $ApplicationCatalogs) {
        $Language = $Catalog.Directory.Parent.Name
        $WxCatalog = Join-Path $ApplicationDirectory (
            "_internal\wx\locale\{0}\LC_MESSAGES\wxstd.mo" -f $Language
        )
        if (-not (Test-Path -LiteralPath $WxCatalog -PathType Leaf)) {
            throw "The application bundle is missing the wxWidgets catalog: $WxCatalog"
        }
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
    $InstallModeMarker = Join-Path (
        $ApplicationDirectory
    ) "_internal\bttext-install-mode.json"
    if (Test-Path -LiteralPath $InstallModeMarker) {
        throw "The portable application contains the installed-mode marker."
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
        "btText-{0}-portable-windows.zip" -f $Version
    )
    Compress-Archive `
        -LiteralPath $ApplicationDirectory `
        -DestinationPath $Archive `
        -CompressionLevel Optimal

    if (-not (Test-Path -LiteralPath $Archive -PathType Leaf)) {
        throw "The btText archive was not created."
    }

    $Installer = $null
    if (-not $PortableOnly) {
        Write-Host "Creating per-user Windows installer..."
        & $ResolvedInnoCompiler `
            "/DMyAppVersion=$Version" `
            "/DMySourceDir=$ApplicationDirectory" `
            "/DMyOutputDir=$BuildDirectory" `
            (Join-Path $ProjectRoot "installer\btText.iss")
        if ($LASTEXITCODE -ne 0) {
            throw "Inno Setup failed with exit code $LASTEXITCODE."
        }
        $Installers = @(
            Get-ChildItem -LiteralPath $BuildDirectory `
                -Filter "*.exe" `
                -File
        )
        if ($Installers.Count -ne 1) {
            throw "Inno Setup did not create exactly one installer."
        }
        $Installer = $Installers[0].FullName
    }

    Write-Host "Build completed successfully:"
    Write-Host $Archive
    if ($Installer) {
        Write-Host $Installer
    }
}
finally {
    Remove-Item Env:BTTEXT_DOCUMENTATION_DIRECTORY -ErrorAction SilentlyContinue
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
