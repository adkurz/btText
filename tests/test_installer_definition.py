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

    def test_user_data_removal_is_optional_and_defaults_to_keep(self):
        self.assertIn("[UninstallDelete]", self.script)
        self.assertIn(
            r'Type: filesandordirs; Name: "{userappdata}\btText"',
            self.script,
        )
        self.assertIn("Check: ShouldRemoveUserData", self.script)
        self.assertIn("SuppressibleMsgBox(", self.script)
        self.assertIn("IDNO", self.script)
        self.assertIn(
            "External databases will not be deleted.",
            self.script,
        )
        self.assertIn(
            "Externe Datenbanken werden nicht gelöscht.",
            self.script,
        )


if __name__ == "__main__":
    unittest.main()
