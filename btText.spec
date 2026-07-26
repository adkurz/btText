"""PyInstaller definition for the portable btText Windows application."""

from pathlib import Path


project_root = Path(SPECPATH)
data_files = [
    (str(project_root / "assets" / "icon.png"), "assets"),
]
data_files.extend(
    (str(catalog), str(catalog.parent.relative_to(project_root)))
    for catalog in sorted(
        (project_root / "locale").glob("*/LC_MESSAGES/*.mo")
    )
)

analysis = Analysis(
    [str(project_root / "btText.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=data_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="btText",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "icon.ico"),
)

application = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="btText",
)
