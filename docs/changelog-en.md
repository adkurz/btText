# Changelog for btText

## [Unreleased]

### Added

- The name of the active database is now displayed in the title bar.

- Added a new variable system to automatically fill in certain values, such as date, time or interactively queried values, when inserting text modules. Further information can be found in the user manual.

## Bug fixes

- Fixed hotstring extension for unavailable clipboard formats.

- Hotstring extensions and other temporary paste operations are now reliably prevented from being saved to the Windows clipboard history or synced via the cloud clipboard. Clipboard privacy settings now only apply when snippets are explicitly copied via the context menu or Ctrl+Shift+C.

## [v1.0] 2026-08-02

First Version