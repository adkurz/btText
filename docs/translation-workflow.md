# Translating btText

This guide is for contributors who want to improve an existing btText
translation or add a new language.

btText uses GNU gettext. English text in the Python source is extracted into a
POT template. Each language has a PO file containing the translation. At build
time, the PO file is compiled into an MO file that btText can load.

## 1. Prepare the repository

From the repository root, install the development dependencies:

```powershell
python -m pip install -r requirements-dev.txt
```

This installs Babel, which provides the catalog tools. Verify the setup:

```powershell
python tools/translations.py --help
```

The relevant files have this layout:

```text
locale/
├── bttext.pot
├── de/
│   └── LC_MESSAGES/
│       └── bttext.po
└── <language>/
    └── LC_MESSAGES/
        └── bttext.po
```

- `locale/bttext.pot` is the English message template.
- A `bttext.po` file is the editable translation for one language.
- A `bttext.mo` file is generated for running the application. MO files are
  ignored by Git and must not be committed.

## 2. Choose a workflow

### Improve an existing language

Open the language's PO file, for example:

```text
locale/de/LC_MESSAGES/bttext.po
```

Edit `msgstr` values only. Do not change `msgid`, `msgctxt`, source locations,
or translator comments.

You may use a gettext editor such as Poedit or edit the UTF-8 PO file directly
in a text editor.

If the application has gained new user-visible strings, update the existing
catalog before translating:

```powershell
python tools/translations.py extract
python tools/translations.py update
```

`extract` refreshes the shared `locale/bttext.pot` template from the Python
source. `update` then merges that template into every existing PO file,
including `locale/de/LC_MESSAGES/bttext.po`. Babel adds new entries, updates
source locations and translator comments, and preserves translations whose
message IDs have not changed. Do not copy entries manually from the POT file.

After the merge, search the PO file for empty `msgstr` values and `fuzzy`
flags. Translate or review those entries, then remove any obsolete `#~` entries
that Babel retained at the end of the file.

After editing, continue with [Validate and test](#5-validate-and-test).

### Add a new language

First ensure that the POT template matches the current source:

```powershell
python tools/translations.py extract
```

Create the new PO catalog:

```powershell
python tools/translations.py init <language-code>
```

Examples:

```powershell
python tools/translations.py init nl
python tools/translations.py init fr
python tools/translations.py init pt_BR
```

Use a gettext locale code: a two- or three-letter language code, optionally
followed by a territory or script. Use an underscore in stored catalog names,
for example `pt_BR`.

The command creates:

```text
locale/<language-code>/LC_MESSAGES/bttext.po
```

Translate every entry in that file. Once the catalog is compiled, btText
discovers the language automatically. No application allowlist needs to be
changed.

## 3. Understand a PO entry

A typical entry looks like this:

```po
#. Translators: Settings-dialog button that saves and activates pending
#. changes without closing the dialog. "&" marks the keyboard mnemonic.
#: ui/settings_dialog.py:71
msgid "&Apply"
msgstr "Ü&bernehmen"
```

- `Translators:` explains where the text appears and what it does.
- `#:` identifies the source location.
- `msgid` is the English source text. Do not edit it.
- `msgstr` is the translation to write.

An empty `msgstr` means that the entry is not translated:

```po
msgid "Settings"
msgstr ""
```

Entries marked `fuzzy` are also incomplete. Review the proposed translation and
remove the `fuzzy` flag only after correcting it:

```po
#, fuzzy
msgid "Settings"
msgstr "Einstellungen"
```

## 4. Translation rules

### Translate meaning, not isolated words

Read the translator comment before translating. The same English word may need
a different translation depending on whether it is a button, title, status
message, or error.

Keep terminology consistent throughout one language. Established German terms
include:

- `snippet` → `Textbaustein`
- `snippets` → `Textbausteine`
- `Apply` → `Übernehmen`

### Preserve placeholders exactly

Placeholders are replaced by btText at runtime:

```text
{name}
{count}
{reason}
{}
```

Keep every placeholder unchanged. You may move named placeholders to obtain
natural grammar, but do not translate, rename, add, or remove them.

Correct:

```po
msgid "The category with ID {id} no longer exists."
msgstr "Die Kategorie mit der ID {id} ist nicht mehr vorhanden."
```

Incorrect:

```po
msgstr "Die Kategorie mit der ID {kennung} ist nicht mehr vorhanden."
```

### Translate every plural form

Plural entries contain a singular and plural source:

```po
msgid "Deleted {count} snippet."
msgid_plural "Deleted {count} snippets."
msgstr[0] "{count} Textbaustein gelöscht."
msgstr[1] "{count} Textbausteine gelöscht."
```

Fill every `msgstr[n]` required by the language's `Plural-Forms` header.

### Preserve keyboard shortcuts

Menu labels can contain a tab followed by a shortcut:

```po
msgid "Copy\tCtrl+C"
msgstr "Kopieren\tStrg+C"
```

Keep the tab and the shortcut. Key names may be localized when that is customary
for the target language.

### Choose non-conflicting mnemonics

In wxPython labels, `&` marks the following character as a keyboard mnemonic:

```text
&Apply → Alt+A
Ü&bernehmen → Alt+B
```

If the source contains a mnemonic, the translation must also contain exactly
one mnemonic. Choose a character that occurs naturally in the translated label.

Mnemonics must be unique among controls that are active in the same window.
Check these groups separately:

- main-window headings and menus;
- search-dialog fields and buttons;
- settings tabs, fields, and buttons;
- text-snippet editor fields and buttons.

A mnemonic may be reused in a different dialog because those controls are not
active at the same time.

## 5. Validate and test

Run the catalog check:

```powershell
python tools/translations.py check
```

It rejects:

- a POT template that no longer matches the Python source;
- missing or obsolete PO entries;
- empty or fuzzy translations;
- invalid placeholders or formatting;
- catalogs that Babel cannot compile.

Compile the PO files into local MO files:

```powershell
python tools/translations.py compile
```

Run btText:

```powershell
python btText.py
```

Open **Settings > General**, select the language, choose **Apply** or **OK**, and
restart btText. Check all translated windows, menus, dialogs, status messages,
plural messages, shortcuts, and mnemonics.

Finally, run the tests:

```powershell
python -m unittest discover -s tests -v
```

## 6. Run the local build checks

The repository provides a PowerShell build script:

```powershell
.\build.ps1
```

It performs the required build checks in order:

1. validates POT and PO sources;
2. compiles all runtime MO catalogs;
3. runs the complete test suite.

To use a specific Python executable:

```powershell
.\build.ps1 -Python "C:\Path\To\python.exe"
```

The script must succeed before submitting a translation. Generated MO files
remain ignored and must not be added to Git.

## 7. Update catalogs after source changes

This section applies to developers who add or change user-visible source text.
It is not required when only translating an existing PO file.

Mark source strings with `_`, `ngettext`, or `pgettext` and place a meaningful
`Translators:` comment immediately next to every call. Then run:

```powershell
python tools/translations.py extract
python tools/translations.py update
```

`extract` regenerates `locale/bttext.pot` in source-file order. `update` merges
the new template into every PO file.

After updating:

1. translate all new or changed entries;
2. review and remove fuzzy flags;
3. remove any obsolete entries retained at the end of a PO file;
4. run `.\build.ps1`.
