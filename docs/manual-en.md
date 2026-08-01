# btText – User Manual

btText is a Windows application for managing and quickly inserting frequently used texts. These texts are stored as **text snippets** in an SQLite database. Categories, search, keyboard shortcuts, and optional hotstrings help you find the right text quickly.

This manual is intended for end-users of the compiled Windows version. Requirements for running from source code are different and are not described here.

## Contents

[TOC]

## Requirements

- Windows 11 (X64)
- A btText installation file or the portable ZIP archive

The prebuilt packages include the required runtime. Python does not need to be installed.

## Installation

### Installable version

1. Run `btText-<Version>-setup-windows.exe`.
2. Select the language of the installer if desired.
3. Optionally enable the creation of a desktop shortcut.
4. Complete the installation and start btText via the Start menu or the desktop shortcut if created.

The installation applies only to the current Windows user and does not require administrator rights. The program files are typically located under:

```text
%LOCALAPPDATA%\Programs\btText
```

Settings and the default database are stored separately from the program files:

```text
%APPDATA%\btText\settings.ini
%APPDATA%\btText\data.db
```

### Portable Version

1. Extract `btText-<Version>-portable-windows.zip` into its own writable folder.
2. Run `btText.exe` from the extracted btText folder.

The portable version stores `settings.ini` and the default database `data.db` in the same folder where the `btText.exe` file is located. Always move or back up the entire folder when transferring the portable version to another drive.

Do not use a protected folder such as `C:\Program Files`, otherwise btText will not be able to save settings and will not function correctly.

### First Start and Database

Upon the first start, btText asks whether to create a new database or open an existing one.

- **Create new database** opens a file dialog. If no changes are made in this dialog, a database named `data.db` will be saved in the default directory. Installed version: `%APPDATA%\btText\`. Portable version: Next to the `btText.exe` file.
- **Open existing database** opens an existing btText database.
- **Cancel** exits the selection. btText cannot work without a database.

The selected database is remembered for subsequent starts. A file in the active data folder is stored as a relative name; databases in other folders are stored as absolute paths.

After the database selection, btText continues to run in the background. The main window is not automatically displayed upon startup. Instead, you can find btText via its icon in the Windows system tray. This ensures the program is always available without taking up permanent space on the screen or in the taskbar.

### Switching between Portable and Installed Versions

btText does not automatically move or delete portable data. To use a portable database with the installed version, there are two ways:

- Start the installed version, select **Switch Database** (Datenbank wechseln), and open the portable `data.db`. The file remains in its original location.
- Copy the portable `data.db` to `%APPDATA%\btText\data.db` before the first start of the installed version.

Create a backup before copying or moving. Do not overwrite a database whose content is still needed.

## Basic Usage

btText is designed to be a constantly available background program. After starting, it runs in the Windows system tray and waits for you to need a text snippet. You can open the main window using the global keyboard shortcut or by clicking the btText icon in the system tray.

To insert a text snippet into another program:

1. Place the cursor in the target program where the text should appear.
2. Press the global btText keyboard shortcut – default is `Ctrl`+`Shift`+`Alt`+`T` – or click the btText icon in the system tray.
3. Select the desired category in the main window and then select the text snippet.
4. Press `Enter` or select **Insert text snippet** (Textbaustein einfügen) from the context menu.

btText then hides its main window, returns to the previously active program, and inserts the text at the current cursor position. After the process, btText continues to run in the background and remains available via keyboard shortcut and the system tray. The target program must provide a normal text input field. If no valid previous window is found or it cannot be activated, btText will display an error.

## Main Window

The main window consists of two areas:

- **Categories**: In this tree view, you can select categories or subcategories.
- **Text Snippets**: This list displays the text snippets of the currently selected category.

The list shows, among other things, the name, weighting, and a content preview. A higher weighting places a text snippet higher in search and list views. This only influences the sorting order, not the evaluation of the text itself.

The status bar provides information on important standard actions or feedback for certain steps, such as copying a text snippet or a category.

### Managing Categories

Categories can be nested. Open the context menu in the **Categories** area and use:

- **New main category** for a category at the top level;
- **New subcategory** for a subcategory of the selection;
- **Rename** or `F2` to rename the selection;
- **Delete** or `Del` to delete the category, including its subcategories and text snippets.

Deleting a category is an irreversible data change. All text snippets stored in the category are permanently deleted; the same applies to any existing subcategories. Therefore, always check the confirmation dialog carefully.

### Creating and Editing Text Snippets

Select a category in the category tree and select **New Text Snippet** (Neuer Textbaustein) from the context menu of the text snippet list. Then fill out the fields:

- **Name**: Designation of the text snippet; must be unique within a category.
- **Category**: Target category of the text snippet. The currently selected category is pre-filled here.
- **Weighting**: Priority for sorting and search ("low", "medium", "high". Default: "low").
- **Hotstring**: Optional shortcut for automatic expansion.
- **Content**: The text to be inserted.

Click **Save** to apply changes. The name and content must not be empty. A hotstring must not contain spaces and must be unique throughout the entire database.

To edit, select a single text snippet and select **Edit text snippet** (Textbaustein bearbeiten) from the context menu or press `F2`.

### Inserting or Copying Text

Open btText using the global keyboard shortcut or via the icon in the system tray and select a text snippet. You can then:

- Press `Enter` or select **Insert text snippet** (Textbaustein einfügen) from the context menu to insert it into the previously active Windows window;
- Select **Copy text to clipboard** (Text in die Zwischenablage kopieren) or press `Ctrl`+`Shift`+`C` to copy only the content.

When inserting, btText remembers the previously active window, hides its own window, and uses the Windows clipboard. After the process, the previous clipboard content is restored, as far as possible. btText does not terminate but continues to run in the background and remains available via keyboard shortcut and the system tray. The target program must provide a standard text input field. If no valid previous window is available or it cannot be activated, btText displays an error.

### Search

Press `F3` or select **Edit > Search** (Bearbeiten > Suchen). Enter a search term to find text snippets. The results show the name, category, weighting, and a content preview.

Select a result and **Show text snippet** (Textbaustein anzeigen) to navigate to the matching category and select the text snippet.

### Copy, Cut, and Paste

Categories and text snippets can be copied or moved internally:

1. Select one or more categories or text snippets.
2. Select **Copy** (`Ctrl`+`C`) or **Cut** (`Ctrl`+`X`).
3. Select the destination.
4. Select **Paste here** (Hier einfügen) or **Paste into category** (In Kategorie einfügen) (`Ctrl`+`V`).

With `Ctrl`+`Shift`+`V`, you can paste a category at the top level. A text snippet must always be pasted into a category. When copying, the original is preserved; when cutting, it is moved after successful pasting.

In the text snippet list, you can select all visible entries with `Ctrl`+`A`. Multiple selection is possible for copying, cutting, and deleting.

## Menus and Keyboard Shortcuts

Keyboard shortcuts are displayed in the German interface as `Strg` (Ctrl), `Umschalt` (Shift), `Alt`, and `Win`. The designations may vary depending on the selected interface language.

### "File" (Datei) Menu

- **Switch Database** (Datenbank wechseln): Open a different existing database or create a new one for the next start.
- **Close** (Schließen): Hides the main window. btText remains active in the system tray.
- **Exit** (Beenden): Completely closes btText.

### "Edit" (Bearbeiten) Menu

- **Search** (Suchen) (`F3`): Search for text snippets.
- **Settings** (Einstellungen) (`Ctrl`+`,`): Configure language, display, clipboard, hotstrings, and the global keyboard shortcut.

### "Help" (Hilfe) Menu

- **View user manual** (`F1`): Opens this user manual in the default browser.
- **About btText** (Über btText): Shows version, author, and license.

### Context Menus

Open context-dependent commands for categories and text snippets using the right mouse button or the context menu command on the keyboard. These menus include entries such as new, insert, copy, cut, rename, edit, and delete.

## Hotstrings

A hotstring is a shortcut that is automatically replaced by the content of a text snippet. Example:

```text
Hotstring: ;addr
Content:   Musterstraße 12, 12345 Musterstadt
```

When you type `;addr` followed by a space, `Enter`, `Tab`, or a punctuation mark in another Windows program, btText replaces the shortcut with the stored content.

### Setting up Hotstrings

1. Open the text snippet with `F2` or create a new one.
2. Enter a shortcut without spaces in the **Hotstring** field.
3. Save the text snippet.

Hotstrings are reloaded automatically after changes. They are case-sensitive: use the shortcut in the exact casing it was saved.

btText only monitors the keyboard if "Enable hotstrings" is activated in the settings, which is the default. Input is restarted when switching to a different foreground window. You can correct part of the entered shortcut using the Backspace key.

## Settings

### General (Allgemein)

- **Language** (Sprache): Changes the user interface language. The change only takes effect after restarting the program.
- **Save copied text snippet in Windows clipboard history** (Kopierten Textbaustein im Windows-Zwischenablageverlauf speichern): If enabled, a text snippet copied via the context menu entry "Copy text to clipboard" or the shortcut `Ctrl`+`Shift`+`C` will be saved in the Windows clipboard history.

- **Save copied text snippets in the Windows Cloud** (Kopierte Textbausteine in der Windows-Cloud speichern): Allows synchronization of copied text snippets via the Windows cloud clipboard. This only applies to copying via the context menu entry "Copy text to clipboard" or the shortcut `Ctrl`+`Shift`+`C`.

### Hotstrings

- **Enable hotstrings** (Hotstrings aktivieren): Turns automatic monitoring on or off.
- **Retain end character after expansion** (Endezeichen nach der Erweiterung erhalten): Re-outputs the triggering space, `Enter`, `Tab`, or punctuation mark after the inserted text. Deactivate this option if the end character should not be included.
- **Show Windows notification after expansion** (Nach der Erweiterung eine Windows-Benachrichtigung anzeigen): Displays a notification in the Windows system tray after successful expansion.

### Design

- **Appearance** (Darstellung): Sets the color scheme of btText. You can select **System setting** (Systemeinstellung), **Light** (Hell), or **Dark** (Dunkel). The change takes effect after restarting the program.

### Keyboard (Tastatur)

The global keyboard shortcut shows/hides the btText main window. By default, this is:

```text
Ctrl+Shift+Alt+T
```

A global keyboard shortcut must contain at least one modifier key (`Ctrl`, `Shift`, `Alt`, or the Windows key) and exactly one other key. Select **Record new combination** (Neue Tastenkombination aufzeichnen), press the desired combination, and confirm with **Apply** (Übernehmen) or **OK**. `Esc` cancels the recording. If the combination is already used by another program, btText will retain its previous combination.

btText takes changes in the active Windows keyboard layout into account and re-registers the global keyboard shortcut if necessary. Not every combination used by Windows or another program can be used.

## System Tray and Program End

Upon startup, btText runs only in the Windows system tray by default; the main window remains hidden. Click the btText icon or press the global keyboard shortcut to show the main window. The context menu of the icon contains:

- **Show text snippets** (Textbausteine anzeigen): Opens and focuses the main window;
- **Exit** (Beenden): Completely closes btText.

**Close** (Schließen) in the main window menu only hides the window. The program, the global keyboard shortcut, and activated hotstrings remain available in the background. The **Exit** (Beenden) menu entry terminates btText completely and removes the icon from the system tray.

## Data, Backups, and Uninstallation

The most important file is the SQLite database `data.db`. Back it up if necessary while btText is closed. A selected database in another folder is not deleted during uninstallation.

### Uninstalling the Installed Version

Uninstall btText via **Windows > Installed Apps** or the uninstallation command in the Start menu. Program files and shortcuts will be removed. Afterwards, the uninstaller optionally offers to delete the `%APPDATA%\btText` folder containing settings and the default database.

Deleting the data is not activated by default and cannot be undone. If necessary, back up `data.db` before agreeing to the deletion. If the database is stored in a different location, it will not be removed.

### Removing the Portable Version

Close btText and delete the extracted program folder. This also deletes any `settings.ini` and `data.db` contained within. Back up the database beforehand if it is still needed.

## Accessibility

btText uses native Windows controls, labeled areas, and keyboard shortcuts. The most important operations are possible without a mouse:

- `Tab` and `Shift`+`Tab` switch between controls;
- Arrow keys move the selection in the category tree and text snippet list;
- `F2` edits the current selection;
- `Del` deletes the current selection after confirmation;
- `F3` opens the search;
- `Enter` inserts the selected text snippet.

## Troubleshooting

### btText does not start because it is already running

Only one instance of btText can be active per user. Check the system tray and terminate the already running instance or use the `Exit` (Beenden) menu item in the `File` menu of the main window.

### A hotstring is not expanded

Check:

1. if **Enable hotstrings** is turned on in Settings;
2. if the shortcut was entered exactly, including case sensitivity;
3. if a space, `Enter`, `Tab`, or a punctuation mark follows;
4. if a text snippet is actually assigned to the shortcut;
5. if the target program has an active text input field.

### The global keyboard shortcut does not work

Select a different combination in **Settings > Keyboard**. A combination already in use might not be able to be registered. After changing the keyboard layout, Windows may require a brief re-registration.

### The database cannot be opened

Ensure the file exists, is not locked by another process, and has a valid btText database structure. Use **Switch Database** to select a different file. A database from a newer btText version may not be openable in an older version.

### Text is inserted in the wrong window

Select the text snippet in btText only when the desired target program is active, or use the global window shortcut to open btText and then focus the target program specifically. The target program must be able to be activated during the insertion process.
