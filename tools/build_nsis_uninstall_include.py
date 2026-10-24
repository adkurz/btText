"""Generate exact NSIS cleanup instructions from the release payload."""

import argparse
import os
from pathlib import Path
import stat


RESERVED_FILES = {"data.db", "settings.ini", "settings.ini.tmp", "uninstall.exe"}
INSTALL_MARKER = "_internal/bttext-install-mode.json"


def _literal(value: str) -> str:
    """Quote a relative filename without enabling NSIS expansion or globs."""
    if any(character in value for character in '*?"\'`\r\n'):
        raise ValueError(f"Unsupported payload filename: {value!r}")
    return value.replace("$", "$$").replace("/", "\\")


def build_include(source: Path, output: Path) -> None:
    """List payload files explicitly; remove directories only when empty."""
    source = source.absolute()
    files: set[str] = set()
    directories: set[str] = set()
    for directory, names, filenames in os.walk(source, followlinks=False):
        current = Path(directory)
        for entry in [current, *(current / name for name in names + filenames)]:
            attributes = entry.lstat()
            if stat.S_ISLNK(attributes.st_mode) or (
                getattr(attributes, "st_file_attributes", 0) & 0x400
            ):
                raise ValueError(f"Linked payload paths are not supported: {entry}")
        for name in names:
            relative = (current / name).relative_to(source).as_posix()
            _literal(relative)
            directories.add(relative)
        for name in filenames:
            relative = (current / name).relative_to(source).as_posix()
            _literal(relative)
            if name.lower() in RESERVED_FILES or relative.lower() == INSTALL_MARKER:
                raise ValueError(f"Unexpected user data or installer file: {relative}")
            files.add(relative)
    if "btText.exe" not in files:
        raise ValueError("The release payload is missing btText.exe")
    files.update({INSTALL_MARKER, "uninstall.exe"})
    directories.add("_internal")

    lines = [
        "; Generated from the release payload. Never use recursive deletion.",
        '!include "LogicLib.nsh"',
        '!include "FileFunc.nsh"',
        "!macro RemoveApplicationFiles ROOT",
        "  Push $0",
        "  Push $1",
        "  Push $2",
        '  StrCpy $1 "${ROOT}"',
        "  cleanup_check_ancestor:",
        "  System::Call 'kernel32::GetFileAttributesW(w r1) i.r0'",
        "  IntOp $0 $0 & 0x410",
        "  ${If} $0 <> 0x10",
        "    Goto cleanup_done",
        "  ${EndIf}",
        '  ${GetParent} "$1" $2',
        '  StrCmp $2 "" cleanup_root_safe',
        "  StrCmp $2 $1 cleanup_root_safe",
        "  StrCpy $1 $2",
        "  Goto cleanup_check_ancestor",
        "  cleanup_root_safe:",
    ]

    def emit_directory(relative: str, indent: str) -> None:
        for filename in sorted(files):
            if filename.rpartition("/")[0] == relative:
                lines.append(f'{indent}Delete "${{ROOT}}\\{_literal(filename)}"')
        children = sorted(
            folder for folder in directories if folder.rpartition("/")[0] == relative
        )
        for child in children:
            path = "${ROOT}\\" + _literal(child)
            lines.extend([
                f"{indent}System::Call 'kernel32::GetFileAttributesW(w \"{path}\") i.r0'",
                f"{indent}IntOp $0 $0 & 0x410",
                f"{indent}${{If}} $0 = 0x10",
            ])
            emit_directory(child, indent + "  ")
            lines.extend([f'{indent}  RMDir "{path}"', f"{indent}${{EndIf}}"])

    emit_directory("", "  ")
    lines.extend([
        '  RMDir "${ROOT}"',
        "  cleanup_done:",
        "  Pop $2",
        "  Pop $1",
        "  Pop $0",
        "!macroend",
        "",
    ])
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    build_include(arguments.source, arguments.output)


if __name__ == "__main__":
    main()
