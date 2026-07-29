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
        self.assertIn('"btText-{0}-setup" -f $Version', self.script)
        self.assertIn("installer\\btText.iss", self.script)

    def test_portable_only_build_does_not_require_inno_setup(self):
        self.assertIn("[switch]$PortableOnly", self.script)
        self.assertIn("if (-not $PortableOnly)", self.script)
        self.assertIn("[string]$InnoCompiler", self.script)

    def test_installer_build_requires_inno_setup_7(self):
        self.assertIn(
            '"Inno Setup 7\\ISCC.exe"',
            self.script,
        )
        self.assertIn(
            "Inno Setup 7 Command-Line Compiler",
            self.script,
        )
        self.assertNotIn("Inno Setup 6", self.script)

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
            "Inno Setup did not create the expected installer.",
            self.script,
        )
        self.assertIn(
            "The btText archive was not created.",
            self.script,
        )


if __name__ == "__main__":
    unittest.main()
