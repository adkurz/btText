# btText

btText is a lightweight and accessible Windows desktop application for managing and reusing
text snippets. It keeps frequently used text in a searchable SQLite database
and can paste snippets into other Windows applications through the clipboard.
Optional hotstrings and configurable global hotkeys make common snippets
available without leaving the active application.

## Features

- Accessible with screen readers and keyboard navigation.
- Organize snippets in a hierarchical category tree.
- Search, create, edit, move, copy, and delete snippets and categories.
- Assign a weight and an optional hotstring to each snippet.
- Variables: Insert localized, contextual, and interactive values and position the caret after insertion.
- Paste snippet content into active Windows application.
- Preserve and restore the previous clipboard contents after a paste.
- Configure global hotkeys and react to the active keyboard layout.
- Follow the Windows light or dark app mode at startup, or select a fixed
  appearance in the settings.
- Multilingual user interface (english and german).
- Store data in a portable directory or in the per-user Windows application
  data directory.
- Open an existing database or create a new one.
- Run as a portable application or install per user without administrator
  privileges.

## Accessibility

btText is designed to be accessible with screen readers. The user interface
uses native controls with descriptive labels and supports keyboard navigation,
so snippets and categories can be managed without relying on visual input. What is more, dark mode is supported.

## Snippets, weights, and hotstrings

Each snippet has a name, text, category, and optional settings that control
how it is found and used.

The `weight` determines the snippet's priority in search and category lists.
Higher-weight snippets are shown before lower-weight snippets, which makes
frequently used entries easier to find. Weights are deliberately simple: they
are a small ranking choice, not a numerical score or a measurement of text
quality.

A hotstring is a short trigger assigned to a snippet, for example `;addr` for
an address. When the trigger is typed in another Windows application, btText
recognizes it and expands it to the associated snippet text. Hotstrings are
optional and each hotstring must be unique.

## How it works

btText provides a wxPython user interface backed by a SQLite database. It
loads the selected database and settings when it starts, and keeps the
interface synchronized with changes to snippets and categories.

When a user selects a snippet, btText writes its text to the Windows clipboard
and sends the paste keystroke to the active application. The existing
clipboard is captured first and restored after the operation. Hotstrings and
global shortcuts are handled by the Windows-specific modules in
`platform_support/` and coordinated by controllers in `ui/`.

## Installation and use

Prebuilt Windows releases are produced as:

- `btText-<version>-setup-windows.exe`, a per-user x64 installer.
- `btText-<version>-portable-windows.zip`, a portable application.

See [`docs/setup.md`](docs/setup.md) for installation, portable use, database
selection, updates, uninstall behavior, and build options.

The end-user manuals are available in
[English](docs/manual-en.md) and [German](docs/manual-de.md).

## Requirements

- Windows 11 x64. May also work with older versions of Windows, but this has not been tested.
- Python 3.14 or newer when running from source.
- wxPython 4.3.1 or newer and the dependencies in
  [`requirements.txt`](requirements.txt).

Packaged releases include the Python runtime and do not require Python to be
installed separately.

## Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe btText.py
```

For tests, translation tooling, and packaging, install the development
dependencies as well:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Build releases

The Windows build script checks the project, runs the tests, and creates the
portable application. With NSIS installed, it also creates the
installer:

```powershell
.\build.ps1
```

To create only the portable release:

```powershell
.\build.ps1 -PortableOnly
```

### Note to NSIS

It is recommended to build the installer with this [unofficial version of NSIS](https://github.com/negrutiu/nsis) to get X64 installers.
## Project structure

```text
btText.py             Application entry point
core/                 Application data and domain logic
platform_support/     Windows-specific functionality
ui/                   wxPython user interface
tests/                Automated tests
locale/               Translations
tools/                Development tools
docs/                 Project documentation
assets/               Application assets
installer/            Windows installer definition
build.ps1             Windows release build script
```

## Author

Copyright (c) 2026 Adrian Kurz.

## License

btText is released under the MIT License. See [`LICENSE`](LICENSE) for the
complete license text.
