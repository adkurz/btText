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
        self.assertIn("DirExistsWarning=no", self.script)
        self.assertIn(
            r"DefaultDirName={localappdata}\Programs\{#MyAppName}",
            self.script,
        )

    def test_installer_requires_version_from_build_script(self):
        self.assertIn(
            "#error MyAppVersion must be supplied by build.ps1",
            self.script,
        )
        self.assertNotIn('#define MyAppVersion "', self.script)

    def test_installer_requests_graceful_update_shutdown_with_force_fallback(self):
        self.assertIn("CloseApplications=force", self.script)
        self.assertIn(
            "UpdateShutdownEventName = 'Local\\btText.UpdateShutdown'",
            self.script,
        )
        self.assertIn("procedure SignalRunningApplicationToExit;", self.script)
        self.assertIn("function NextButtonClick(CurPageID: Integer)", self.script)
        self.assertIn("function PrepareToInstall(var NeedsRestart: Boolean)", self.script)

    def test_installer_adds_shortcuts_and_uninstall_metadata(self):
        self.assertIn("AppId=btText.AdrianKurz", self.script)
        self.assertIn(r'Name: "{group}\{#MyAppName}"', self.script)
        self.assertIn(r'Name: "{autodesktop}\{#MyAppName}"', self.script)
        self.assertIn("UninstallDisplayIcon=", self.script)

    def test_installer_offers_per_user_startup_shortcut(self):
        self.assertIn(
            'Name: "autostart"; Description: "{cm:AutoStartProgram,{#MyAppName}}";',
            self.script,
        )
        self.assertIn(
            r'Name: "{userstartup}\{#MyAppName}"; '
            r'Filename: "{app}\{#MyAppExeName}";',
            self.script,
        )
        self.assertIn("Tasks: autostart", self.script)
        self.assertNotIn("uninsneveruninstall", self.script.lower())

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
        self.assertNotIn("[UninstallDelete]", self.script)
        self.assertIn("procedure CurUninstallStepChanged(", self.script)
        self.assertIn("CurUninstallStep = usUninstall", self.script)
        self.assertIn(
            "CurUninstallStep = usPostUninstall",
            self.script,
        )
        self.assertIn("SuppressibleMsgBox(", self.script)
        self.assertIn("IDNO", self.script)
        self.assertIn("DelTree(", self.script)
        self.assertIn(
            "External databases will not be deleted.",
            self.script,
        )
        self.assertIn(
            "Externe Datenbanken werden nicht gelöscht.",
            self.script,
        )
        self.assertIn("RemoveUserDataFailed", self.script)

    def test_uninstaller_waits_for_the_running_application(self):
        self.assertIn("function InitializeUninstall: Boolean;", self.script)
        self.assertIn(
            "ExpandConstant('{#MyAppName}-{username}')",
            self.script,
        )
        self.assertIn("while CheckForMutexes(MutexName) do", self.script)
        self.assertIn("MB_RETRYCANCEL", self.script)
        self.assertIn("IDRETRY", self.script)
        self.assertIn("ApplicationStillRunning", self.script)
        self.assertIn("klicken Sie anschließend auf Wiederholen", self.script)


if __name__ == "__main__":
    unittest.main()
