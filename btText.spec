"""PyInstaller definition for the portable btText Windows application."""

from pathlib import Path
import runpy

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)


project_root = Path(SPECPATH)
application_info = runpy.run_path(str(project_root / "info.py"))


def windows_version(version):
    """Convert a dotted application version to a four-part Windows version."""
    try:
        parts = tuple(int(part) for part in version.split("."))
    except ValueError as error:
        raise ValueError(
            f"info.version must contain only numeric dot-separated parts: {version!r}"
        ) from error
    if not 1 <= len(parts) <= 4 or any(not 0 <= part <= 65535 for part in parts):
        raise ValueError(
            "info.version must contain one to four numeric parts between 0 and 65535"
        )
    return parts + (0,) * (4 - len(parts))


application_name = application_info["name"]
application_author = application_info["author"]
application_version = application_info["version"]
numeric_version = windows_version(application_version)
version_resource = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=numeric_version,
        prodvers=numeric_version,
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",
                    [
                        StringStruct("CompanyName", application_author),
                        StringStruct("FileDescription", application_name),
                        StringStruct("FileVersion", application_version),
                        StringStruct("InternalName", application_name),
                        StringStruct("OriginalFilename", f"{application_name}.exe"),
                        StringStruct("ProductName", application_name),
                        StringStruct("ProductVersion", application_version),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
    ],
)

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
    manifest=str(project_root / "btText.manifest"),
    version=version_resource,
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
