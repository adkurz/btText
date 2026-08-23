# Changelog for btText

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
