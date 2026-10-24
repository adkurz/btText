"""Regression coverage for unsupported build runtimes."""

import io
from types import SimpleNamespace
import unittest
from unittest import mock

from tools import check_build_runtime


class CheckBuildRuntimeTests(unittest.TestCase):
    def setUp(self):
        runtime = SimpleNamespace(
            implementation=SimpleNamespace(name="cpython"),
            version_info=(3, 15, 0, "final", 0),
        )
        self.runtime = runtime
        self.enterContext(mock.patch.object(check_build_runtime, "sys", runtime))
        self.platform = self.enterContext(mock.patch.object(
            check_build_runtime.sysconfig, "get_platform", return_value="win-amd64"
        ))
        self.configuration = self.enterContext(mock.patch.object(
            check_build_runtime.sysconfig, "get_config_var", return_value=0
        ))

    def test_accepts_python_315_patch_releases_without_importing_wx(self):
        for patch in (0, 1, 10):
            with self.subTest(patch=patch):
                self.runtime.version_info = (3, 15, patch, "final", 0)
                with mock.patch.dict("sys.modules", {"wx": None}):
                    check_build_runtime.check_runtime()

    def test_rejects_other_python_versions(self):
        for version in ((3, 13), (3, 14), (3, 16), (4, 0)):
            with self.subTest(version=version):
                self.runtime.version_info = version
                with self.assertRaisesRegex(RuntimeError, "Recreate .venv"):
                    check_build_runtime.check_runtime()

    def test_rejects_other_implementations(self):
        self.runtime.implementation.name = "pypy"
        with self.assertRaisesRegex(RuntimeError, "CPython 3.15"):
            check_build_runtime.check_runtime()

    def test_rejects_other_platforms_and_architectures(self):
        for platform in ("win32", "win-arm64", "linux-x86_64"):
            with self.subTest(platform=platform):
                self.platform.return_value = platform
                with self.assertRaisesRegex(RuntimeError, "Windows x64"):
                    check_build_runtime.check_runtime()

    def test_rejects_free_threaded_interpreters(self):
        self.configuration.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "standard CPython"):
            check_build_runtime.check_runtime()

    def test_accepts_required_wx_version(self):
        with mock.patch.dict("sys.modules", {"wx": SimpleNamespace(__version__="4.3.2")}):
            check_build_runtime.check_runtime(with_wx=True)

    def test_rejects_other_wx_versions(self):
        for version in ("4.3.1", "4.3.3", "4.3.2a1"):
            with self.subTest(version=version):
                with mock.patch.dict("sys.modules", {"wx": SimpleNamespace(__version__=version)}):
                    with self.assertRaisesRegex(RuntimeError, "wxPython 4.3.2"):
                        check_build_runtime.check_runtime(with_wx=True)

    def test_command_reports_import_failure_without_traceback(self):
        self.runtime.stderr = io.StringIO()
        with mock.patch.dict("sys.modules", {"wx": None}):
            self.assertEqual(check_build_runtime.main(["--with-wx"]), 1)
        self.assertNotIn("Traceback", self.runtime.stderr.getvalue())
        self.assertIn("wx", self.runtime.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
