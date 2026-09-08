"""Render snippet text into the formats offered on the Windows clipboard."""

from copy import deepcopy
from dataclasses import dataclass
from xml.etree import ElementTree
import uuid

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from core.variables import RenderedSnippet


@dataclass(frozen=True)
class ClipboardContent:
    """Represent one clipboard item with plain text and optional HTML."""

    plain_text: str
    html: str | None = None
    cursor_offset_from_end: int | None = None


class _CaptureTreeprocessor(Treeprocessor):
    """Retain the normalized Markdown tree before it is serialized."""

    def __init__(self, extension: "_TreeCaptureExtension") -> None:
        super().__init__()
        self._extension = extension

    def run(self, root: ElementTree.Element) -> None:
        self._extension.root = deepcopy(root)


class _TreeCaptureExtension(Extension):
    """Disable raw HTML and expose a copy of the parsed element tree."""

    def __init__(self) -> None:
        super().__init__()
        self.root: ElementTree.Element | None = None

    def extendMarkdown(self, md: markdown.Markdown) -> None:
        # Snippets are formatting instructions, not arbitrary executable HTML.
        # Without these processors, angle brackets are emitted as escaped text.
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")
        md.treeprocessors.register(
            _CaptureTreeprocessor(self),
            "bttext_capture_tree",
            15,
        )


def render_clipboard_content(
    rendered: RenderedSnippet,
    markdown_enabled: bool,
) -> ClipboardContent:
    """Create the clipboard representations for one resolved snippet."""
    if not markdown_enabled:
        return ClipboardContent(
            rendered.text,
            cursor_offset_from_end=rendered.cursor_offset_from_end,
        )

    marker = None
    source = rendered.text
    if rendered.cursor_offset_from_end is not None:
        marker = f"\ue000{uuid.uuid4().hex}\ue001"
        position = len(source) - rendered.cursor_offset_from_end
        source = source[:position] + marker + source[position:]

    root = _parse_markdown_tree(rendered.text)
    plain_text = _render_plain_text(root)
    cursor_offset = None
    if marker is not None:
        marked_plain_text = _render_plain_text(_parse_markdown_tree(source))
        marker_position = marked_plain_text.find(marker)
        if marker_position < 0:
            raise RuntimeError("Markdown discarded the cursor position.")
        cursor_offset = len(plain_text) - marker_position

    html = "".join(
        ElementTree.tostring(child, encoding="unicode", method="html")
        for child in root
    )
    return ClipboardContent(plain_text, html, cursor_offset)


def _parse_markdown_tree(source: str) -> ElementTree.Element:
    """Parse source and return a detached, normalized element tree."""
    capture = _TreeCaptureExtension()
    parser = markdown.Markdown(extensions=[capture], output_format="html")
    parser.convert(source)
    if capture.root is None:
        raise RuntimeError("Markdown did not produce a document tree.")
    return capture.root


def _render_plain_text(root: ElementTree.Element) -> str:
    """Render the supported Markdown element tree as readable plain text."""
    parts: list[str] = []

    def append_text(value: str | None, *, preserve_lines: bool = False) -> None:
        if value:
            parts.append(value if preserve_lines else value.replace("\n", " "))

    def end_block(lines: int = 2) -> None:
        current = "".join(parts)
        missing = lines - (len(current) - len(current.rstrip("\n")))
        if missing > 0:
            parts.append("\n" * missing)

    def visit(element: ElementTree.Element, list_depth: int = 0) -> None:
        tag = element.tag
        if tag == "br":
            parts.append("\n")
        elif tag == "hr":
            parts.append("---")
            end_block()
        elif tag == "img":
            append_text(element.get("alt"))
        elif tag in ("ul", "ol"):
            ordered = tag == "ol"
            item_number = int(element.get("start", "1"))
            for child in element:
                if child.tag != "li":
                    visit(child, list_depth + 1)
                    continue
                parts.append("  " * list_depth)
                parts.append(f"{item_number}. " if ordered else "- ")
                visit(child, list_depth + 1)
                end_block(1)
                item_number += 1
            end_block()
        elif tag == "pre":
            append_text("".join(element.itertext()), preserve_lines=True)
            end_block()
        else:
            append_text(element.text)
            for child in element:
                visit(child, list_depth)
                append_text(child.tail)
            if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}:
                end_block()

    for child in root:
        visit(child)
        append_text(child.tail)
    return "".join(parts).strip("\n")
