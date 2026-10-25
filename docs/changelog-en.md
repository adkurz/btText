# Changelog for btText

## [v1.3.1] 

- changed: Large snippet lists now sort faster by preparing weight and name sort keys once per operation. The existing sort order, selection, and focus are preserved.

- Changed: Large Markdown snippets with many paragraphs are now rendered faster as plain text, while preserving line breaks and indentation.

- Changed: Copying, moving, or deleting multiple snippets now refreshes the category tree and hotstrings once per operation, avoiding repeated full reloads for every snippet.

- Fixed: Invalid or unreadable settings no longer reset the database selection or privacy options. btText now reports the error and stops without overwriting the settings file.

- Fixed: Delayed hotstring expansions are now cancelled if you continue typing or change the target input field, preventing text entered in the meantime or text in another field from being replaced.

- Fixed: The Copy path, Open folder, and Close buttons in the database location dialog are now arranged without overlapping.

- Fixed: Hotstrings now retain the originally typed punctuation mark even when modifier keys are released during a variable prompt. Cancelling the prompt also restores the correct character.

- Fixed: Holding Shift while ending a hotstring with punctuation such as ? no longer changes the paste shortcut or inserts a control character instead of the snippet.

- Fixed: If pasting a snippet or expanding a hotstring fails and the previous clipboard contents cannot be restored immediately, btText now retries restoration automatically. New clipboard contents copied by other applications are preserved.

- Fixed: Databases with missing required columns are now rejected upon opening with an error message specifying the missing columns. This prevents btText from failing to load the main window. A different database can then be selected.

- Fixed: Drag and drop now accepts only active internal category and snippet moves. Text dragged from other applications can no longer trigger unintended moves or errors.

- Fixed: Hotstrings longer than 256 characters are now rejected when saving with a clear error message. This prevents saving triggers that cannot be expanded; your editor input remains available for correction.

- Fixed: Characters entered with Ctrl+Alt, such as backslash (`\`) on a German keyboard, now work as hotstring ending characters, just like characters entered with AltGr.

## [v1.3.0] 2026-10-25

- Added: Text snippets can now optionally be formatted using simple Markdown. When inserted, they are output not only as plain text but also as HTML and RTF, so that the formatting is preserved if supported by the target program. This allows for simple formatting (bold, italics, etc.), links, and citations.

- Changed: Updated to Python 3.15.

- Changed: Dependencies updated.

- Changed: UPX is no longer used to compress the program files in order to achieve faster performance.

- Fixed: Privacy settings for Windows clipboard history and cloud synchronization are now respected even when copying or pasting fails.

- Fixed: Percent signs in database paths no longer cause unexpected issues.

- Fixed: With hotstrings enabled, accents such as ´ were inserted twice instead of combining with the following letter (e.g. to produce é).

- Fixed: A timing issue when pasting snippets could cause newly copied clipboard contents from other applications to be lost and replaced with older contents.

- Fixed: The installer can no longer accidentally update portable versions of btText, which could lead to data loss.

## [v1.2.1] 2026-08-23

- Improved: The installer now ensures that btText is not installed into an existing folder that does not contain btText itself. New installations and updates are still possible without any problems.

- Fixed: Hotstrings now work more reliably during various system events, when switching between windows, and in conjunction with modifier keys (Ctrl, Alt, Shift).

- Fixed: Pasting into other applications now reliably checks whether the window still exists.

- Fixed: Changing the global keyboard shortcut might have caused a misleading error message to appear.

## [v1.2] 2026-08-22

- Added: The **Insert Variable** dialog now shows a preview of the currently selected variable, if possible.

- Added: There is now a setting to play a sound when expanding a hotstring.

- Changed: The installer now uses NSIS, an upgrade is possible without any problems.

- Fixed: If the language is set to the system standard, language-dependent variables, such as date and time, are output in the currently set language of the operating system, even if a suitable btText translation does not yet exist.

## [v1.1] 2026-08-10

- Added: New variable system to automatically fill in certain values, such as date, time or interactively queried values, when inserting snippets. Further information can be found in the user manual.

- Added: The name of the active database is now displayed in the title bar.

- Added: The full path of the active database can now be displayed, copied, and opened in File Explorer.

- Added: Setting to installer to automatically start btText after login.

- Changed: The search now also takes hotstrings into account.

- Fixed: Hotstring expansion for unavailable clipboard formats is now possible.

- Fixed: Hotstring expansions and other temporary paste operations are now reliably prevented from being saved to the Windows clipboard history or synced via the cloud clipboard. Clipboard privacy settings now only apply when snippets are explicitly copied via the context menu or Ctrl+Shift+C.

- Fixed: If the list of snippets is focused after changing a category, the first list entry now receives the focus correctly.

- Fixed: The installer can now close btText for an upgrade.

## [v1.0] 2026-08-02

First Version
