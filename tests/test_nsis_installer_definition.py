"""Static contracts for the optional NSIS installer definition."""

import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (PROJECT_ROOT / "installer" / "btText.nsi").read_text(encoding="utf-8")


class NsisInstallerDefinitionTests(unittest.TestCase):
    def test_german_messages_are_stored_as_utf8(self):
        source = (PROJECT_ROOT / "installer" / "btText.nsi").read_bytes()
        self.assertIn("Möchten Sie zusätzlich".encode("utf-8"), source)
        self.assertIn("wird noch ausgeführt".encode("utf-8"), source)

    def test_installer_is_per_user_and_uses_build_version(self):
        self.assertIn("RequestExecutionLevel user", SCRIPT)
        self.assertIn("ManifestSupportedOS Win10", SCRIPT)
        self.assertIn(r'InstallDir "$LOCALAPPDATA\Programs\${APP_NAME}"', SCRIPT)
        self.assertIn('!error "VERSION must be supplied by build.ps1"', SCRIPT)

    def test_installer_requires_supported_64_bit_windows(self):
        self.assertIn("${AtLeastWin10}", SCRIPT)
        self.assertIn("${RunningX64}", SCRIPT)
        self.assertIn("UnsupportedWindows", SCRIPT)
        self.assertIn("UnsupportedArchitecture", SCRIPT)

    def test_matches_shortcut_and_launch_choices(self):
        self.assertIn('Section /o "$(DesktopShortcut)"', SCRIPT)
        self.assertIn('Section /o "$(StartupShortcut)"', SCRIPT)
        self.assertNotIn('MUI_FINISHPAGE_RUN_NOTCHECKED', SCRIPT)
        self.assertIn('CreateShortcut "$SMSTARTUP\\${APP_NAME}.lnk"', SCRIPT)
        self.assertIn("SelectSection ${DesktopSection}", SCRIPT)
        self.assertIn("SelectSection ${StartupSection}", SCRIPT)

    def test_existing_shortcuts_control_upgrade_component_defaults(self):
        on_init = SCRIPT.split("Function .onInit", 1)[1].split("FunctionEnd", 1)[0]
        self.assertIn('UnselectSection ${DesktopSection}', on_init)
        self.assertIn('UnselectSection ${StartupSection}', on_init)
        self.assertIn('IfFileExists "$DESKTOP\\${APP_NAME}.lnk"', on_init)
        self.assertIn('SelectSection ${DesktopSection}', on_init)
        self.assertIn('IfFileExists "$SMSTARTUP\\${APP_NAME}.lnk"', on_init)
        self.assertIn('SelectSection ${StartupSection}', on_init)
        self.assertNotIn("0 +2", on_init)
        self.assertIn("desktop_shortcut_exists desktop_shortcut_done", on_init)
        self.assertIn("startup_shortcut_exists startup_shortcut_done", on_init)

    def test_upgrade_removes_inno_installation_without_user_data(self):
        self.assertIn(r'${APP_ID}_is1', SCRIPT)
        self.assertIn('"UninstallString"', SCRIPT)
        self.assertIn('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-', SCRIPT)
        self.assertIn("Call RemovePreviousInstallations", SCRIPT)
        upgrade = SCRIPT.split("Function RemovePreviousInstallations", 1)[1].split(
            "FunctionEnd", 1
        )[0]
        self.assertNotIn("$APPDATA\\btText", upgrade)

    def test_existing_install_is_touched_only_after_user_confirms(self):
        on_init = SCRIPT.split("Function .onInit", 1)[1].split("FunctionEnd", 1)[0]
        main = SCRIPT.split('Section "$(MainSection)"', 1)[1].split(
            "SectionEnd", 1
        )[0]
        self.assertNotIn("RemovePreviousInstallations", on_init)
        self.assertIn("Call WaitForApplication", main)
        self.assertIn("Call RemovePreviousInstallations", main)

    def test_shutdown_protocol_is_used_for_install_and_uninstall(self):
        self.assertIn('Local\\btText.UpdateShutdown', SCRIPT)
        self.assertIn("advapi32::GetUserName", SCRIPT)
        self.assertIn('OpenMutexW', SCRIPT)
        self.assertIn('Call WaitForApplication', SCRIPT)
        self.assertIn('Call un.WaitForApplication', SCRIPT)

    def test_real_uninstall_offers_optional_data_removal(self):
        uninstall = SCRIPT.split('Section "Uninstall"', 1)[1]
        self.assertIn('IfSilent keep_user_data', uninstall)
        self.assertIn('MB_DEFBUTTON2', uninstall)
        self.assertIn('RMDir /r "$APPDATA\\btText"', uninstall)
        self.assertIn("ClearErrors", uninstall)
        self.assertIn("IfErrors 0 keep_user_data", uninstall)
        self.assertIn("RemoveUserDataFailed", uninstall)

    def test_uninstaller_does_not_recursively_delete_shared_directories(self):
        uninstall = SCRIPT.split('Section "Uninstall"', 1)[1]
        self.assertNotIn('RMDir /r "$INSTDIR"', uninstall)
        self.assertNotIn('RMDir /r "$SMPROGRAMS', uninstall)
        self.assertIn('RMDir /r "$INSTDIR\\_internal"', uninstall)
        self.assertIn('Delete "$INSTDIR\\${APP_EXE}"', uninstall)
        self.assertIn('RMDir "$INSTDIR"', uninstall)

    def test_silent_failure_messages_have_defaults_and_error_codes(self):
        self.assertIn('"$(InnoUpgradeFailed)" /SD IDOK', SCRIPT)
        self.assertIn('"$(OldUpgradeFailed)" /SD IDOK', SCRIPT)
        self.assertIn("SetErrorLevel 2", SCRIPT)

    def test_add_remove_programs_metadata_includes_estimated_size(self):
        self.assertIn("SectionGetSize ${MainSection} $0", SCRIPT)
        self.assertIn('"EstimatedSize" $0', SCRIPT)


if __name__ == "__main__":
    unittest.main()
