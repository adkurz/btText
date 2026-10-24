"""Validate the supported Windows build runtime before installing or packaging."""

import argparse
import sys
import sysconfig


def check_runtime(*, with_wx: bool = False) -> None:
    """Reject interpreters and wx builds outside the supported release baseline."""
    if (
        sys.implementation.name != "cpython"
        or sys.version_info[:2] != (3, 15)
        or sysconfig.get_platform() != "win-amd64"
        or sysconfig.get_config_var("Py_GIL_DISABLED")
    ):
        raise RuntimeError(
            "btText builds require standard CPython 3.15 for Windows x64. "
            "Recreate .venv with a supported interpreter; use -Python to select it."
        )

    if with_wx:
        import wx

        if wx.__version__ != "4.3.2":
            raise RuntimeError(
                "btText builds require wxPython 4.3.2. "
                "Install requirements-dev.txt in .venv."
            )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-wx", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        check_runtime(with_wx=arguments.with_wx)
    except (RuntimeError, ImportError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
