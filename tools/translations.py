"""Create, update, compile, and validate btText translation catalogs."""

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import i18n
import info


MAPPING_FILE = PROJECT_ROOT / "babel.cfg"
LOCALE_DIRECTORY = PROJECT_ROOT / "locale"
TEMPLATE_FILE = LOCALE_DIRECTORY / "{}.pot".format(i18n.DOMAIN)


class TranslationCheckError(Exception):
    """Raised when committed translation artifacts are out of date."""


def _run_babel(arguments: Sequence[str]) -> None:
    """Run Babel through the current Python interpreter."""
    try:
        babel_frontend = importlib.util.find_spec("babel.messages.frontend")
    except ModuleNotFoundError:
        babel_frontend = None
    if babel_frontend is None:
        raise RuntimeError(
            "Babel is not installed. Install the development dependencies with "
            "'python -m pip install -r requirements-dev.txt'."
        )
    command = [
        sys.executable,
        "-m",
        "babel.messages.frontend",
        *arguments,
    ]
    try:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(
            "Babel command failed with exit code {}".format(error.returncode)
        ) from error


def extract(output_file: Path | None = None) -> None:
    """Extract source messages into a deterministic POT template."""
    if output_file is None:
        output_file = TEMPLATE_FILE
    output_file.parent.mkdir(parents=True, exist_ok=True)
    _run_babel(
        (
            "extract",
            "--mapping-file",
            str(MAPPING_FILE),
            "--output-file",
            str(output_file),
            "--keyword",
            "_",
            "--keyword",
            "ngettext:1,2",
            "--keyword",
            "pgettext:1c,2",
            "--add-comments",
            "Translators:",
            "--sort-by-file",
            "--no-wrap",
            "--project",
            info.name,
            "--version",
            info.version,
            "--copyright-holder",
            info.author,
            ".",
        )
    )


def initialize_catalog(language: str) -> None:
    """Create a new PO catalog for ``language`` from the current template."""
    normalized_language = i18n.validate_language(language)
    if normalized_language in (i18n.SYSTEM_LANGUAGE, i18n.DEFAULT_LANGUAGE):
        raise ValueError(
            "A catalog cannot be created for the system setting or source English"
        )
    if not TEMPLATE_FILE.is_file():
        raise FileNotFoundError(
            "The translation template is missing; run 'extract' first"
        )
    catalog_file = (
        LOCALE_DIRECTORY
        / normalized_language
        / "LC_MESSAGES"
        / "{}.po".format(i18n.DOMAIN)
    )
    if catalog_file.exists():
        raise FileExistsError(
            "A catalog for {} already exists".format(normalized_language)
        )
    _run_babel(
        (
            "init",
            "--input-file",
            str(TEMPLATE_FILE),
            "--output-dir",
            str(LOCALE_DIRECTORY),
            "--domain",
            i18n.DOMAIN,
            "--locale",
            normalized_language,
            "--no-wrap",
        )
    )


def update_catalogs() -> None:
    """Merge the current template into all existing PO catalogs."""
    _require_template()
    _run_babel(
        (
            "update",
            "--input-file",
            str(TEMPLATE_FILE),
            "--output-dir",
            str(LOCALE_DIRECTORY),
            "--domain",
            i18n.DOMAIN,
            "--previous",
            "--no-wrap",
        )
    )


def compile_catalogs() -> None:
    """Compile all PO catalogs into runtime MO files."""
    _run_babel(
        (
            "compile",
            "--directory",
            str(LOCALE_DIRECTORY),
            "--domain",
            i18n.DOMAIN,
            "--statistics",
        )
    )


def check_catalogs() -> None:
    """Verify that the template and source catalogs are current and complete."""
    _require_template()
    with tempfile.TemporaryDirectory() as temporary_directory:
        temporary_path = Path(temporary_directory)
        extracted_template = temporary_path / TEMPLATE_FILE.name
        extract(extracted_template)
        if _comparable_template(TEMPLATE_FILE) != _comparable_template(
            extracted_template
        ):
            raise TranslationCheckError(
                "The translation template is out of date; run 'extract'"
            )

        for po_file in _catalog_files():
            _validate_catalog(extracted_template, po_file)
            language = po_file.parents[1].name
            compiled_catalog = temporary_path / language / "{}.mo".format(
                i18n.DOMAIN
            )
            compiled_catalog.parent.mkdir(parents=True, exist_ok=True)
            _run_babel(
                (
                    "compile",
                    "--input-file",
                    str(po_file),
                    "--output-file",
                    str(compiled_catalog),
                    "--statistics",
                )
            )


def _validate_catalog(template_file: Path, catalog_file: Path) -> None:
    """Reject missing, obsolete, fuzzy, empty, or structurally invalid entries."""
    from babel.core import UnknownLocaleError
    from babel.messages.catalog import Catalog
    from babel.messages.pofile import read_po

    with template_file.open("r", encoding="utf-8") as template_stream:
        template = read_po(template_stream)
    with catalog_file.open("r", encoding="utf-8") as catalog_stream:
        catalog = read_po(catalog_stream)

    language = catalog_file.parents[1].name
    try:
        normalized_language = i18n.validate_language(language)
        expected_plural_forms = Catalog(
            locale=normalized_language
        ).plural_forms
    except (UnknownLocaleError, ValueError) as error:
        raise TranslationCheckError(
            "{} has an invalid or unknown language directory: {}".format(
                catalog_file,
                language,
            )
        ) from error
    if normalized_language != language:
        raise TranslationCheckError(
            "{} must use the normalized language directory {}".format(
                catalog_file,
                normalized_language,
            )
        )

    catalog_language = (
        str(catalog.locale)
        if catalog.locale is not None
        else None
    )
    if catalog_language != language:
        raise TranslationCheckError(
            "{} declares language {!r}, expected {!r}".format(
                catalog_file,
                catalog_language,
                language,
            )
        )
    if catalog.plural_forms != expected_plural_forms:
        raise TranslationCheckError(
            "{} has plural forms {!r}, expected {!r} for {}".format(
                catalog_file,
                catalog.plural_forms,
                expected_plural_forms,
                language,
            )
        )

    template_keys = {
        (message.context, message.id)
        for message in template
        if message.id
    }
    messages = {
        (message.context, message.id): message
        for message in catalog
        if message.id
    }
    missing = template_keys - set(messages)
    extra = set(messages) - template_keys
    if missing:
        raise TranslationCheckError(
            "{} is missing {} message(s); run 'update'".format(
                catalog_file,
                len(missing),
            )
        )
    if extra or catalog.obsolete:
        raise TranslationCheckError(
            "{} contains obsolete messages {}; run 'update'".format(
                catalog_file,
                tuple(sorted(map(repr, extra)))[:3],
            )
        )

    incomplete = [
        message
        for message in messages.values()
        if message.fuzzy
        or (
            isinstance(message.string, tuple)
            and not all(message.string)
        )
        or (
            isinstance(message.string, str)
            and not message.string
        )
    ]
    if incomplete:
        details = "\n".join(
            "  - {} ({})".format(
                _message_description(message),
                ", ".join(
                    "{}:{}".format(filename, line_number)
                    for filename, line_number in message.locations
                )
                or "source location unknown",
            )
            for message in incomplete
        )
        raise TranslationCheckError(
            "{} has {} untranslated or fuzzy message(s):\n{}".format(
                catalog_file,
                len(incomplete),
                details,
            )
        )

    errors = [
        error
        for message, message_errors in catalog.check()
        for error in message_errors
    ]
    if errors:
        raise TranslationCheckError(
            "{} has {} formatting error(s): {}".format(
                catalog_file,
                len(errors),
                errors[0],
            )
        )


def _message_description(message) -> str:
    """Return a searchable description of a catalog message."""
    description = repr(message.id)
    if message.context is not None:
        description += " [context: {!r}]".format(message.context)
    return description


def _catalog_files() -> tuple[Path, ...]:
    """Return all PO catalogs in stable language order."""
    return tuple(
        sorted(
            LOCALE_DIRECTORY.glob(
                "*/LC_MESSAGES/{}.po".format(i18n.DOMAIN)
            )
        )
    )


def _comparable_template(template_file: Path) -> str:
    """Read a POT file while ignoring its generated creation timestamp."""
    return "".join(
        line
        for line in template_file.read_text(encoding="utf-8").splitlines(
            keepends=True
        )
        if not line.startswith('"POT-Creation-Date:')
    )


def _require_template() -> None:
    """Require the extracted template for catalog operations."""
    if not TEMPLATE_FILE.is_file():
        raise FileNotFoundError(
            "The translation template is missing; run 'extract' first"
        )


def create_argument_parser() -> argparse.ArgumentParser:
    """Create the command-line parser for translation maintenance."""
    parser = argparse.ArgumentParser(
        description="Maintain btText gettext translation catalogs."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("extract", help="Extract messages into the POT file.")
    init_parser = subparsers.add_parser(
        "init",
        help="Create a PO catalog for a new language.",
    )
    init_parser.add_argument("language", help="Language code such as de or pt_BR.")
    subparsers.add_parser("update", help="Update every existing PO catalog.")
    subparsers.add_parser("compile", help="Compile PO catalogs into MO files.")
    subparsers.add_parser(
        "check",
        help="Check that POT and MO files match their sources.",
    )
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Run the requested translation maintenance command."""
    parser = create_argument_parser()
    options = parser.parse_args(arguments)
    try:
        if options.command == "extract":
            extract()
        elif options.command == "init":
            initialize_catalog(options.language)
        elif options.command == "update":
            update_catalogs()
        elif options.command == "compile":
            compile_catalogs()
        elif options.command == "check":
            check_catalogs()
    except (
        FileExistsError,
        FileNotFoundError,
        RuntimeError,
        TranslationCheckError,
        ValueError,
    ) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    main()
