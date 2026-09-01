# Repository Guidelines

## Project Structure & Module Organization

`btText.py` is the application entry point. Domain logic and persistence live in `core/`; wxPython windows, dialogs, controls, and controllers live in `ui/`; Windows integrations such as keyboard hooks, clipboard handling, shortcuts, sounds, and paths live in `platform_support/`. Automated tests are in `tests/` and follow the source module names. User documentation is in `docs/`, translation sources in `locale/`, development utilities in `tools/`, application resources in `assets/`, and the NSIS definition in `installer/`.

Keep platform-independent behavior out of `ui/` and `platform_support/` where practical. Preserve the existing controller boundaries for focus-sensitive UI workflows.

## Build, Test, and Development Commands

Run these commands from PowerShell at the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe btText.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe tools\translations.py check
.\build.ps1 -PortableOnly
```

The build script validates translations, builds documentation, runs all tests, and packages the application. Use `.\build.ps1` when NSIS is available to create both portable and installer artifacts.

After changing user-visible strings, run `tools\translations.py extract`, `update`, `check`, and `compile` in that order.

## Coding Style & Naming Conventions

Use four-space indentation and conventional Python naming: `snake_case` for functions and modules, `PascalCase` for classes, and `UPPER_CASE` for constants. Add type hints where they clarify service and controller contracts. Keep development-facing text, comments, documentation, and commit messages in English. No formatter is enforced; match nearby code and keep changes focused.

## Testing Guidelines

Tests use Python's `unittest` framework. Name files `test_<module>.py` and test methods `test_<behavior>`. Add regression tests for every behavioral fix, especially clipboard ownership, keyboard handling, focus restoration, settings persistence, and installer safety. Automated success does not replace native Windows checks: manually exercise relevant keyboard layouts, NVDA behavior, focus transitions, clipboard restoration, and installer lifecycle.

## Commit & Pull Request Guidelines

History favors short, imperative subjects such as `Update README` or `Validate transfer kinds and reject unsupported operations`. Keep each commit cohesive. Pull requests should describe the user-visible effect, implementation scope, tests run, and remaining native smoke tests. Link relevant issues and include screenshots only for visual UI changes.

## Configuration & Safety

Do not commit `settings.ini`, databases, logs, build output, or other user data. New settings pages should use a matching `settings.ini` section; do not add migration behavior unless explicitly required. Preserve localized errors, keyboard navigation, screen-reader accessibility, focus behavior, drag-and-drop semantics, and clipboard data owned by other applications.
