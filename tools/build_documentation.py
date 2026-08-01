"""Convert project Markdown documentation into standalone HTML files."""

import argparse
import html
import re
from pathlib import Path

import markdown


STYLESHEET = """
:root { color-scheme: light dark; font-family: system-ui, sans-serif; }
body { max-width: 70rem; margin: 0 auto; padding: 1rem 2rem 3rem; line-height: 1.55; }
a { color: LinkText; }
a:focus-visible { outline: 0.2rem solid Highlight; outline-offset: 0.15rem; }
pre { overflow-x: auto; padding: 0.8rem; background: Canvas; border: 1px solid GrayText; }
code { font-family: ui-monospace, monospace; }
table { border-collapse: collapse; }
th, td { padding: 0.35rem 0.6rem; border: 1px solid GrayText; text-align: left; }
""".strip()
LANGUAGE_SUFFIX = re.compile(r"-([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*)$")
HEADING = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


def discover_sources(source_directory: Path) -> tuple[Path, ...]:
    """Return every Markdown document below ``source_directory``."""
    return tuple(sorted(source_directory.rglob("*.md")))


def document_language(source: Path) -> str:
    """Infer a document language from its final filename suffix."""
    match = LANGUAGE_SUFFIX.search(source.stem)
    return match.group(1).replace("_", "-").lower() if match else "en"


def convert_document(source: Path, destination: Path) -> None:
    """Convert one UTF-8 Markdown source to standalone HTML."""
    markdown_text = source.read_text(encoding="utf-8")
    heading = HEADING.search(markdown_text)
    title = heading.group(1) if heading else source.stem
    body = markdown.markdown(
        markdown_text,
        extensions=("toc", "fenced_code", "tables"),
        output_format="html5",
    )
    output = """<!doctype html>
<html lang="{language}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>{stylesheet}</style>
</head>
<body>
{body}
</body>
</html>
""".format(
        language=html.escape(document_language(source), quote=True),
        title=html.escape(title),
        stylesheet=STYLESHEET,
        body=body,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(output, encoding="utf-8", newline="\n")


def build_documentation(source_directory: Path, output_directory: Path) -> tuple[Path, ...]:
    """Convert all Markdown sources while preserving relative paths."""
    sources = discover_sources(source_directory)
    if not sources:
        raise ValueError(f"No Markdown documentation found in {source_directory}")
    outputs = []
    for source in sources:
        destination = output_directory / source.relative_to(source_directory).with_suffix(".html")
        convert_document(source, destination)
        outputs.append(destination)
    return tuple(outputs)


def main() -> int:
    """Parse command-line paths and build all documentation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    arguments = parser.parse_args()
    outputs = build_documentation(
        arguments.source_directory.resolve(), arguments.output_directory.resolve()
    )
    for output in outputs:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
