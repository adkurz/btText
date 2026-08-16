# btText - Installation, Portable Use, and Development

btText is available as a per-user Windows installation and as a portable
archive. Neither packaged version requires Python to be installed.

## Install btText on Windows

1. Run `btText-<version>-setup-windows.exe`.
2. Select the installer language.
3. Optionally enable the desktop shortcut.
4. Complete the installation and start btText.

The installer does not request administrator privileges. It installs the
program for the current user in:

```text
%LOCALAPPDATA%\Programs\btText
```

It also creates a Start menu entry and a standard Windows uninstaller.

On first start, btText asks whether to create a new snippet database or open an
existing one. Settings and the default database of the installed version are
stored separately from the program files:

```text
%APPDATA%\btText\settings.ini
%APPDATA%\btText\data.db
```

## Use the portable version

1. Extract `btText-<version>-portable-windows.zip` to a writable directory.
2. Start `btText.exe` from the extracted `btText` directory.

The portable version stores `settings.ini` and its default `data.db` beside
`btText.exe`. Keep the complete directory together when moving the portable
installation.

Do not run the portable version from a protected directory such as
`C:\Program Files`, because it must be able to write its settings and default
database beside the executable.

## Move from portable to installed

btText does not search for, move, or delete portable data automatically.

There are two supported ways to continue using an existing portable database:

- Start the installed version, choose **Open existing database**, and select
  the portable `data.db`. The database remains in its original location, and
  the installed settings store its absolute path.
- Before the first installed start, copy the portable `data.db` to
  `%APPDATA%\btText\data.db`. btText adopts it as the installed default
  database.

Back up `data.db` before copying or moving it. Do not overwrite an existing
database unless its contents are no longer needed.

## Change the active database

Use the database selection command in btText to choose another existing
database or create a new one. btText validates the selected file before saving
the setting. Restart btText after changing the active database.

A database inside the active data directory is stored as a relative filename.
A database in any other directory is stored as an absolute path.

## Update btText

For an installed version, close btText and run the newer setup executable. The
installer updates the program files in place. User settings and databases under
`%APPDATA%\btText` remain unchanged.

For a portable version:

1. Close btText.
2. Extract the new archive to a new directory.
3. Copy the previous `settings.ini` and `data.db` into the new `btText`
   directory, or continue opening an externally stored database.
4. Start the new executable and verify the data before deleting the old
   directory.

## Uninstall btText

Uninstall btText from Windows **Installed apps** or from its Start menu
uninstaller.

The uninstaller always removes the program files and shortcuts. It then offers
to delete the user data in:

```text
%APPDATA%\btText
```

The removal option is disabled by default. Keeping the data allows a later
installation to reuse the settings and default database.

Select the data-removal option only after backing up `data.db`. It permanently
deletes the complete `%APPDATA%\btText` directory, including the installed
version's settings and default database, and cannot be undone. Databases
selected from other directories are external and are not deleted.

To remove btText without leaving its program-managed files behind:

1. Back up any database that may still be needed.
2. Start the uninstaller.
3. Confirm the optional removal of settings and databases.

To remove the portable version, close btText and delete its extracted
directory. This also deletes a portable `settings.ini` and `data.db` stored in
that directory, so back up the database first.

## Run from source

Running from source is intended for development. It requires 64-bit Python
3.14. Earlier Python versions are not supported. The project targets the
current Python version as soon as its dependencies support it and does not add
compatibility layers for older interpreters.

Create a virtual environment and install the runtime dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe btText.py
```

The source version stores `settings.ini` and its default `data.db` in the
project directory.

For development, translation work, tests, and packaging, install:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Build the Windows releases

The default build requires NSIS and creates both release artifacts:

```powershell
.\build.ps1
```

```text
build\btText-<version>-portable-windows.zip
build\btText-<version>-setup-windows.exe
```

The build script:

1. creates or reuses the project `.venv`;
2. installs the declared build dependencies;
3. validates and compiles translation catalogs;
4. runs the complete test suite;
5. creates the PyInstaller onedir application;
6. verifies that the payload contains no user data;
7. creates the portable ZIP;
8. locates and invokes the NSIS compiler;
9. creates the per-user x64 installer.

The script locates `makensis.exe` on `PATH` or in the standard NSIS
installation directory. Supply a non-standard location explicitly:

```powershell
.\build.ps1 -NsisCompiler "C:\Path\To\NSIS\makensis.exe"
```

Create only the portable artifact without NSIS:

```powershell
.\build.ps1 -PortableOnly
```

Select the Python interpreter used when creating a missing `.venv`:

```powershell
.\build.ps1 -Python "C:\Path\To\python.exe"
```

An existing `.venv` is reused. Recreate it before using `-Python` to switch the
build environment to Python 3.14.
