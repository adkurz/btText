# Changelog for btText

## [v1.1]

### Added

- Added a new variable system to automatically fill in certain values, such as date, time or interactively queried values, when inserting snippets. Further information can be found in the user manual.

- The name of the active database is now displayed in the title bar.

- Added setting to installer to automatically start btText after login.

### Bug fixes

- Fixed hotstring expansion for unavailable clipboard formats.

- Hotstring expansions and other temporary paste operations are now reliably prevented from being saved to the Windows clipboard history or synced via the cloud clipboard. Clipboard privacy settings now only apply when snippets are explicitly copied via the context menu or Ctrl+Shift+C.

- If the list of snippets is focused after changing a category, the first list entry now receives the focus correctly.

- The search now also takes hotstrings into account.

- Fixed bug when installer closes btText for upgrade.

## [v1.0] 2026-08-02

First Version