"""Exercise generated cleanup and real NSIS directory validation in isolation."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import uuid

from tools.build_nsis_uninstall_include import build_include


ROOT = Path(__file__).resolve().parents[1]


def find_compiler():
    compiler = shutil.which("makensis.exe")
    if compiler:
        return compiler
    for variable in ("ProgramFiles", "ProgramFiles(x86)"):
        if os.environ.get(variable):
            candidate = Path(os.environ[variable]) / "NSIS" / "makensis.exe"
            if candidate.is_file():
                return str(candidate)
    return None


class CleanupIncludeTests(unittest.TestCase):
    def test_rejects_user_data_and_installer_files_in_payload(self):
        for filename in ("data.db", "settings.ini", "settings.ini.tmp", "uninstall.exe",
                         "_internal/bttext-install-mode.json"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                payload = root / "payload"
                payload.mkdir()
                (payload / "btText.exe").write_bytes(b"application")
                unsafe = payload / filename
                unsafe.parent.mkdir(parents=True, exist_ok=True)
                unsafe.write_bytes(b"must not be packaged")
                with self.assertRaises(ValueError):
                    build_include(payload, root / "cleanup.nsh")

    def test_rejects_missing_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "missing btText.exe"):
                build_include(Path(temporary), Path(temporary) / "cleanup.nsh")


@unittest.skipUnless(os.name == "nt" and find_compiler(), "NSIS on Windows is required")
class NativeNsisCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="btText-nsis-test-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        payload = cls.root / "payload"
        (payload / "_internal/nested").mkdir(parents=True)
        for filename in ("btText.exe", "_internal/runtime.dll", "_internal/nested/$literal.dll"):
            (payload / filename).write_bytes(b"program")
        include = cls.root / "cleanup.nsh"
        build_include(payload, include)
        script = (ROOT / "installer/btText.nsi").read_text(encoding="utf-8")

        def function(name):
            return "Function " + name + script.split(
                "Function " + name, 1
            )[1].split("FunctionEnd", 1)[0] + "FunctionEnd\n"

        cls.registry_key = "Software\\btText-Installer-Test-" + uuid.uuid4().hex
        import winreg

        def remove_test_key():
            try:
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, cls.registry_key, winreg.KEY_WOW64_32KEY)
            except FileNotFoundError:
                pass

        cls.addClassCleanup(remove_test_key)
        cls.runner = cls.root / "cleanup-test.exe"
        harness = cls.root / "test.nsi"
        harness.write_text(
            'Unicode true\nRequestExecutionLevel user\nSilentInstall silent\n'
            f'OutFile "{cls.runner}"\n'
            '!define APP_EXE "btText.exe"\n'
            '!define INSTALL_MARKER "bttext-install-mode.json"\n'
            f'!define NSIS_UNINSTALL_KEY "{cls.registry_key}"\n'
            'LangString OldUpgradeFailed 1033 "Upgrade refused ($0)"\n'
            'LangString InnoUpgradeFailed 1033 "Inno upgrade failed ($0)"\n'
            'Var PreviousUninstaller\nVar PreviousInstallDir\n'
            f'!include "{include}"\n'
            # Isolate real application registrations, shortcuts, and Inno Setup.
            '!macro RemoveApplicationShortcuts\n!macroend\n'
            'Function ReadInnoUninstaller\nStrCpy $PreviousUninstaller ""\nFunctionEnd\n'
            + function("ValidateInstallDirectory")
            + function("NormalizeInstallDirectory")
            + function("RemovePreviousInstallations")
            + '\nSection\n${GetParameters} $0\nClearErrors\n'
            '${GetOptions} $0 "/validate" $1\nIfErrors try_upgrade\n'
            'Call ValidateInstallDirectory\nPop $0\n'
            '${If} $0 = 0\nSetErrorLevel 2\n${EndIf}\nGoto done\n'
            'try_upgrade:\nClearErrors\n'
            '${GetOptions} $0 "/upgrade" $1\nIfErrors cleanup\n'
            'SetRegView 32\n'
            'WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "UninstallString" '
            "'\"$INSTDIR\\uninstall.exe\"'\n"
            'WriteRegStr HKCU "${NSIS_UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"\n'
            'Call RemovePreviousInstallations\n'
            'DeleteRegKey HKCU "${NSIS_UNINSTALL_KEY}"\nGoto done\n'
            'cleanup:\nSetOutPath "$TEMP"\n'
            '!insertmacro RemoveApplicationFiles "$INSTDIR"\n'
            'done:\nSectionEnd\n',
            encoding="utf-8",
        )
        compilation = subprocess.run(
            [find_compiler(), "/INPUTCHARSET", "UTF8", str(harness)],
            capture_output=True, text=True, timeout=30,
        )
        if compilation.returncode:
            raise AssertionError(compilation.stdout + compilation.stderr)
        cls.legacy_uninstaller = cls.root / "legacy-uninstaller.exe"
        legacy_script = cls.root / "legacy.nsi"
        legacy_script.write_text(
            'Unicode true\nRequestExecutionLevel user\nSilentInstall silent\n'
            f'OutFile "{cls.legacy_uninstaller}"\nSection\n'
            'FileOpen $0 "$EXEDIR\\legacy-ran.txt" w\n'
            'FileWrite $0 "Unsafe legacy uninstaller was executed"\nFileClose $0\nSectionEnd\n',
            encoding="utf-8",
        )
        compilation = subprocess.run(
            [find_compiler(), "/INPUTCHARSET", "UTF8", str(legacy_script)],
            capture_output=True, text=True, timeout=30,
        )
        if compilation.returncode:
            raise AssertionError(compilation.stdout + compilation.stderr)

    def setUp(self):
        self.fixture = tempfile.TemporaryDirectory(dir=self.root, prefix="fixture with spaces-")
        self.addCleanup(self.fixture.cleanup)
        self.install = Path(self.fixture.name) / "btText"

    def write(self, filename, content=b"preserve"):
        target = self.install / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def run_installer(self, *, validate=False, upgrade=False):
        command = [str(self.runner), "/S"]
        if validate:
            command.append("/validate")
        if upgrade:
            command.append("/upgrade")
        # NSIS requires /D= last and unquoted, even when its path has spaces.
        # Passing it in an argument list would let subprocess quote the switch.
        command_line = subprocess.list2cmdline(command) + f" /D={self.install}"
        return subprocess.run(command_line, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW).returncode

    def test_rejects_portable_and_partially_marked_directories(self):
        self.write("btText.exe")
        self.write("data.db")
        self.write("settings.ini")
        self.assertEqual(self.run_installer(validate=True), 2)
        self.write("_internal/bttext-install-mode.json")
        self.assertEqual(self.run_installer(validate=True), 2)
        self.assertEqual((self.install / "data.db").read_bytes(), b"preserve")
        self.assertEqual((self.install / "settings.ini").read_bytes(), b"preserve")

    def test_accepts_empty_new_and_installed_directories(self):
        self.assertEqual(self.run_installer(validate=True), 0)
        self.install.mkdir()
        self.assertEqual(self.run_installer(validate=True), 0)
        self.write("btText.exe")
        self.write("uninstall.exe")
        self.write("_internal/bttext-install-mode.json")
        self.assertEqual(self.run_installer(validate=True), 0)

    def test_cleanup_preserves_user_files_at_every_depth(self):
        program_files = ("btText.exe", "uninstall.exe", "_internal/bttext-install-mode.json",
                         "_internal/runtime.dll", "_internal/nested/$literal.dll")
        user_files = ("data.db", "settings.ini", "notes.txt", "_internal/custom.db",
                      "_internal/nested/keep.txt", "logs/btText.log")
        for filename in program_files + user_files:
            self.write(filename)
        self.assertEqual(self.run_installer(), 0)
        for filename in program_files:
            self.assertFalse((self.install / filename).exists(), filename)
        for filename in user_files:
            self.assertEqual((self.install / filename).read_bytes(), b"preserve", filename)

    def test_cleanup_removes_empty_program_directories(self):
        for filename in ("btText.exe", "uninstall.exe", "_internal/bttext-install-mode.json",
                         "_internal/runtime.dll", "_internal/nested/$literal.dll"):
            self.write(filename)
        self.assertEqual(self.run_installer(), 0)
        self.assertFalse(self.install.exists())

    def test_upgrade_skips_legacy_uninstaller_and_preserves_user_files(self):
        self.write("btText.exe")
        self.write("_internal/bttext-install-mode.json")
        for filename in ("data.db", "settings.ini", "_internal/custom.db"):
            self.write(filename)
        shutil.copyfile(self.legacy_uninstaller, self.install / "uninstall.exe")
        self.assertEqual(self.run_installer(upgrade=True), 0)
        self.assertFalse((self.install / "legacy-ran.txt").exists())
        self.assertFalse((self.install / "btText.exe").exists())
        for filename in ("data.db", "settings.ini", "_internal/custom.db"):
            self.assertEqual((self.install / filename).read_bytes(), b"preserve")

    def test_upgrade_refuses_a_registered_portable_folder_before_cleanup(self):
        self.write("btText.exe")
        self.write("data.db")
        shutil.copyfile(self.legacy_uninstaller, self.install / "uninstall.exe")
        self.assertEqual(self.run_installer(upgrade=True), 2)
        self.assertFalse((self.install / "legacy-ran.txt").exists())
        self.assertEqual((self.install / "btText.exe").read_bytes(), b"preserve")
        self.assertEqual((self.install / "data.db").read_bytes(), b"preserve")

    def test_cleanup_preserves_junction_targets(self):
        self.write("btText.exe")
        outside = Path(self.fixture.name) / "outside"
        outside.mkdir()
        protected = outside / "runtime.dll"
        protected.write_bytes(b"external")
        junction = self.install / "_internal"
        # These paths are generated by TemporaryDirectory, not shell input.
        creation = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(junction), str(outside)],
            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(creation.returncode, 0, creation.stderr)
        try:
            with self.assertRaisesRegex(ValueError, "Linked payload paths"):
                build_include(self.install, Path(self.fixture.name) / "unsafe.nsh")
            self.assertEqual(self.run_installer(), 0)
            self.assertEqual(protected.read_bytes(), b"external")
        finally:
            junction.rmdir()


if __name__ == "__main__":
    unittest.main()
