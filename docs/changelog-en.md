# Changelog for btText

## [Unreleased] 

- Added: The **Insert Variable** dialog now shows a preview of the currently selected variable, if possible.

## [v1.1] 10.08.2026

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
