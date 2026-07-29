"""Static contract tests for the per-user Inno Setup definition."""

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SCRIPT = PROJECT_ROOT / "installer" / "btText.iss"
INSTALL_MODE_MARKER = (
    PROJECT_ROOT / "installer" / "bttext-install-mode.json"
)


class InstallerDefinitionTests(unittest.TestCase):
    """Keep installer location and user-data behavior explicit."""

    @classmethod
    def setUpClass(cls):
        cls.script = INSTALLER_SCRIPT.read_text(encoding="utf-8")

    def test_installer_is_per_user_and_non_elevated(self):
        self.assertIn("PrivilegesRequired=lowest", self.script)
        self.assertIn("SetupArchitecture=x64", self.script)
        self.assertIn(
            r"DefaultDirName={localappdata}\Programs\{#MyAppName}",
            self.script,
        )

    def test_installer_adds_shortcuts_and_uninstall_metadata(self):
        self.assertIn("AppId=btText.AdrianKurz", self.script)
        self.assertIn(r'Name: "{group}\{#MyAppName}"', self.script)
        self.assertIn(r'Name: "{autodesktop}\{#MyAppName}"', self.script)
        self.assertIn("UninstallDisplayIcon=", self.script)

    def test_installer_marks_only_its_payload_as_installed(self):
        self.assertTrue(INSTALL_MODE_MARKER.is_file())
        self.assertEqual(
            INSTALL_MODE_MARKER.read_text(encoding="utf-8").strip(),
            '{"mode": "installed"}',
        )
        self.assertIn(
            r'DestDir: "{app}\_internal"',
            self.script,
        )

    def test_installer_does_not_manage_user_data(self):
        directives = "\n".join(
            line
            for line in self.script.splitlines()
            if line and not line.lstrip().startswith(";")
        ).lower()
        self.assertNotIn("userappdata", directives)
        self.assertNotIn("data.db", directives)
        self.assertNotIn("settings.ini", directives)


if __name__ == "__main__":
    unittest.main()
