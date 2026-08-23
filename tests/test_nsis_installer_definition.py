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

    def test_directory_input_has_a_localized_accessible_label(self):
        self.assertNotIn("!insertmacro MUI_PAGE_DIRECTORY", SCRIPT)
        self.assertIn("Page custom ShowDirectoryPage LeaveDirectoryPage", SCRIPT)
        self.assertIn(
            'LangString InstallLocationLabel ${LANG_ENGLISH} "&Install location:"',
            SCRIPT,
        )
        self.assertIn(
            'LangString InstallLocationLabel ${LANG_GERMAN} "&Installationsordner:"',
            SCRIPT,
        )
        page = SCRIPT.split("Function ShowDirectoryPage", 1)[1].split(
            "FunctionEnd", 1
        )[0]
        self.assertLess(
            page.index('${NSD_CreateLabel} 0 30u 100% 12u "$(InstallLocationLabel)"'),
            page.index("${NSD_CreateDirRequest}"),
        )
        self.assertIn('${NSD_CreateDirRequest} 0 44u 78% 13u "$INSTDIR"', page)
        self.assertIn("${NSD_SetFocus} $DirectoryInput", page)

    def test_directory_page_normalizes_a_nonexistent_install_directory(self):
        leave = SCRIPT.split("Function LeaveDirectoryPage", 1)[1].split(
            "FunctionEnd", 1
        )[0]
        normalize = SCRIPT.split("Function NormalizeInstallDirectory", 1)[1].split(
            "FunctionEnd", 1
        )[0]
        self.assertIn("${NSD_GetText} $DirectoryInput $0", leave)
        self.assertIn("Call NormalizeInstallDirectory", leave)
        self.assertIn("StrCpy $INSTDIR $0", leave)
        self.assertNotIn("GetFullPathName", leave)
        self.assertIn("kernel32::GetFullPathNameW", normalize)
        self.assertIn("StrCpy $0 $1", normalize)

    def test_nonempty_directory_requires_a_complete_bttext_installation(self):
        leave = SCRIPT.split("Function LeaveDirectoryPage", 1)[1].split(
            "FunctionEnd", 1
        )[0]
        validation = SCRIPT.split("Function ValidateInstallDirectory", 1)[1].split(
            "FunctionEnd", 1
        )[0]
        main = SCRIPT.split('Section "$(MainSection)"', 1)[1].split(
            "SectionEnd", 1
        )[0]
        self.assertIn("Call ValidateInstallDirectory", leave)
        self.assertIn('FindFirst $1 $2 "$INSTDIR\\*"', validation)
        self.assertIn("IfErrors directory_validation_done", validation)
        self.assertIn('StrCmp $2 "." directory_find_next', validation)
        self.assertIn('StrCmp $2 ".." directory_find_next', validation)
        self.assertIn("FindNext $1 $2", validation)
        self.assertIn("FindClose $1", validation)
        self.assertNotIn('IfFileExists "$INSTDIR\\*.*"', validation)
        self.assertIn(
            'IfFileExists "$INSTDIR\\_internal\\${INSTALL_MARKER}"',
            validation,
        )
        self.assertIn('IfFileExists "$INSTDIR\\${APP_EXE}"', validation)
        self.assertIn('IfFileExists "$INSTDIR\\uninstall.exe"', validation)
        self.assertIn("InstallLocationNotOwned", leave)
        self.assertIn("Abort", leave)
        self.assertIn("Call RequireSafeInstallDirectory", main)
        require = SCRIPT.split("Function RequireSafeInstallDirectory", 1)[1].split(
            "FunctionEnd", 1
        )[0]
        self.assertIn('/SD IDOK', require)
        self.assertIn("SetErrorLevel 2", require)
        self.assertIn("Call NormalizeInstallDirectory", require)
        self.assertNotIn("GetFullPathName $INSTDIR", require)
        self.assertLess(
            main.index("Call RequireSafeInstallDirectory"),
            main.index('File /r "${SOURCE_DIR}\\*"'),
        )

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
        self.assertNotIn('RMDir /r "$INSTDIR\\_internal"', uninstall)
        self.assertIn('!include "${UNINSTALL_INCLUDE}"', uninstall)
        self.assertIn(
            'Delete "$INSTDIR\\_internal\\${INSTALL_MARKER}"',
            uninstall,
        )
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
