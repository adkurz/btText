"""Tests for source, portable, and installed application paths."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from platform_support import app_paths


class AppPathsTests(unittest.TestCase):
    """Verify that launch modes select deterministic resource and data paths."""

    def test_source_mode_uses_project_for_application_and_data(self):
        with patch.object(sys, "frozen", False, create=True):
            self.assertEqual(
                app_paths.get_application_mode(),
                app_paths.ApplicationMode.SOURCE,
            )
            self.assertEqual(
                app_paths.get_data_directory(),
                app_paths.PROJECT_ROOT,
            )

    def test_frozen_build_without_marker_is_portable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            executable = root / "btText.exe"
            bundle = root / "_internal"
            bundle.mkdir()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(executable)),
                patch.object(sys, "_MEIPASS", str(bundle), create=True),
            ):
                self.assertEqual(
                    app_paths.get_application_mode(),
                    app_paths.ApplicationMode.PORTABLE,
                )
                self.assertEqual(app_paths.get_data_directory(), root)
                self.assertEqual(
                    app_paths.get_settings_file(),
                    root / "settings.ini",
                )
                self.assertEqual(
                    app_paths.get_database_file(),
                    root / "data.db",
                )

    def test_frozen_build_with_marker_uses_appdata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle = root / "_internal"
            bundle.mkdir()
            (bundle / app_paths.INSTALL_MODE_MARKER).write_text(
                '{"mode": "installed"}',
                encoding="utf-8",
            )
            appdata = root / "AppData" / "Roaming"
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(root / "btText.exe")),
                patch.object(sys, "_MEIPASS", str(bundle), create=True),
                patch.dict(os.environ, {"APPDATA": str(appdata)}),
            ):
                expected = appdata.resolve() / "btText"
                self.assertEqual(
                    app_paths.get_application_mode(),
                    app_paths.ApplicationMode.INSTALLED,
                )
                self.assertEqual(app_paths.get_data_directory(), expected)
                self.assertTrue(expected.is_dir())
                self.assertEqual(
                    app_paths.get_settings_file(),
                    expected / "settings.ini",
                )
                self.assertEqual(
                    app_paths.get_database_file(),
                    expected / "data.db",
                )
                self.assertEqual(
                    app_paths.get_resource_directory(),
                    bundle,
                )

    def test_installed_mode_requires_appdata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            bundle = root / "_internal"
            bundle.mkdir()
            (bundle / app_paths.INSTALL_MODE_MARKER).touch()
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "_MEIPASS", str(bundle), create=True),
                patch.dict(os.environ, {}, clear=True),
            ):
                with self.assertRaisesRegex(RuntimeError, "APPDATA"):
                    app_paths.get_data_directory()


if __name__ == "__main__":
    unittest.main()
