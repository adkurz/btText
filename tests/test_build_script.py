"""Static contracts for portable and installer build outputs."""

import unittest
from pathlib import Path

BUILD_SCRIPT = Path(__file__).resolve().parents[1] / "build.ps1"


class BuildScriptTests(unittest.TestCase):
    """Keep both release variants and their safety checks wired."""

    @classmethod
    def setUpClass(cls):
        cls.script = BUILD_SCRIPT.read_text(encoding="utf-8")

    def test_default_build_creates_portable_archive_and_installer(self):
        self.assertIn(
            '"btText-{0}-portable-windows.zip" -f $Version',
            self.script,
        )
        self.assertIn("installer\\btText.nsi", self.script)

    def test_portable_only_build_does_not_require_nsis(self):
        self.assertIn("[switch]$PortableOnly", self.script)
        self.assertIn("if (-not $PortableOnly)", self.script)

    def test_nsis_is_the_only_installer_builder(self):
        self.assertIn('[string]$NsisCompiler = ""', self.script)
        self.assertIn('"NSIS\\makensis.exe"', self.script)
        self.assertIn('installer\\btText.nsi', self.script)
        self.assertIn('"/INPUTCHARSET"', self.script)
        self.assertIn('"UTF8"', self.script)
        self.assertIn('"/DVERSION=$Version"', self.script)
        self.assertNotIn("InnoCompiler", self.script)
        self.assertNotIn("ISCC", self.script)
        self.assertNotIn("InstallerType", self.script)

    def test_portable_payload_rejects_user_data_and_install_marker(self):
        for forbidden_name in (
            "data.db",
            "settings.ini",
            "settings.ini.tmp",
            "bttext-install-mode.json",
        ):
            self.assertIn(forbidden_name, self.script)

    def test_build_checks_expected_outputs(self):
        self.assertIn(
            '"NSIS did not create exactly one installer."',
            self.script,
        )
        self.assertIn(
            "The btText archive was not created.",
            self.script,
        )

    def test_build_generates_and_checks_all_markdown_documentation(self):
        self.assertIn("tools/build_documentation.py", self.script)
        self.assertIn("BTTEXT_DOCUMENTATION_DIRECTORY", self.script)
        self.assertIn('-Filter "*.md"', self.script)
        self.assertIn("_internal\\docs", self.script)


if __name__ == "__main__":
    unittest.main()
