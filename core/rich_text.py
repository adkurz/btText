"""Render snippet text into the formats offered on the Windows clipboard."""

from copy import deepcopy
from dataclasses import dataclass
from xml.etree import ElementTree
from urllib.parse import quote, urlsplit

import markdown
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from core.variables import RenderedSnippet


_ALLOWED_LINK_SCHEMES = frozenset(("http", "https", "mailto"))


@dataclass(frozen=True)
class ClipboardContent:
    """Represent one clipboard item with plain text and optional HTML."""

    plain_text: str
    html: str | None = None
    cursor_offset_from_end: int | None = None
    rtf: bytes | None = None


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
        md.treeprocessors.deregister("prettify")
        md.treeprocessors.register(
            _CaptureTreeprocessor(self),
            "bttext_capture_tree",
            -1,
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

    if rendered.cursor_offset_from_end is not None:
        raise ValueError("Markdown content must not contain a cursor instruction.")

    root = _parse_markdown_tree(rendered.text)
    _sanitize_links(root)
    _replace_images_with_alt_text(root)
    plain_text = _render_plain_text(root)
    html = "".join(
        ElementTree.tostring(child, encoding="unicode", method="html")
        for child in root
    )
    return ClipboardContent(
        plain_text=plain_text,
        html=html,
        rtf=_render_rtf(root),
    )


def _parse_markdown_tree(source: str) -> ElementTree.Element:
    """Parse source and return a detached, normalized element tree."""
    capture = _TreeCaptureExtension()
    parser = markdown.Markdown(extensions=[capture], output_format="html")
    parser.convert(source)
    if capture.root is None:
        raise RuntimeError("Markdown did not produce a document tree.")
    return capture.root


def _sanitize_links(root: ElementTree.Element) -> None:
    """Keep only explicitly supported absolute Markdown link targets."""
    for element in root.iter("a"):
        href = element.get("href", "").strip()
        if _is_allowed_link_target(href):
            element.set("href", href)
        else:
            # Preserve the label and inline formatting without leaving an
            # actionable link in either HTML or RTF.
            element.tag = "span"
            element.attrib.clear()


def _is_allowed_link_target(href: str) -> bool:
    """Return whether a link has a supported scheme and usable destination."""
    try:
        target = urlsplit(href)
    except ValueError:
        return False
    scheme = target.scheme.lower()
    if scheme not in _ALLOWED_LINK_SCHEMES:
        return False
    if scheme == "mailto":
        return bool(target.path)
    return bool(target.netloc)


def _replace_images_with_alt_text(parent: ElementTree.Element) -> None:
    """Replace every image with its alternative text in document order."""
    previous: ElementTree.Element | None = None
    for child in list(parent):
        if child.tag == "img":
            replacement = child.get("alt", "") + (child.tail or "")
            if previous is None:
                parent.text = (parent.text or "") + replacement
            else:
                previous.tail = (previous.tail or "") + replacement
            parent.remove(child)
            continue
        _replace_images_with_alt_text(child)
        previous = child


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


def _escape_rtf_text(value: str, *, preserve_lines: bool = False) -> str:
    """Return text represented entirely by ASCII-safe RTF instructions."""
    result: list[str] = []
    for character in value:
        if character == "\\":
            result.append(r"\\")
        elif character == "{":
            result.append(r"\{")
        elif character == "}":
            result.append(r"\}")
        elif character == "\t":
            result.append(r"\tab ")
        elif character in "\r\n":
            result.append(r"\line " if preserve_lines else " ")
        elif 0x20 <= ord(character) <= 0x7E:
            result.append(character)
        else:
            encoded = character.encode("utf-16-le")
            for index in range(0, len(encoded), 2):
                code_unit = int.from_bytes(encoded[index : index + 2], "little")
                signed_value = code_unit if code_unit < 0x8000 else code_unit - 0x10000
                result.append(f"\\u{signed_value}?")
    return "".join(result)


class _RtfRenderer:
    """Render btText's deliberately limited Markdown element vocabulary."""

    _HEADING_SIZES = {
        "h1": 36,
        "h2": 32,
        "h3": 28,
        "h4": 26,
        "h5": 24,
        "h6": 22,
    }

    def render(self, root: ElementTree.Element) -> bytes:
        """Return a complete RTF document suitable for clipboard transfer."""
        body = "".join(self._render_block(child) for child in root)
        if body.endswith(r"\par "):
            body = body[: -len(r"\par ")]
        document = (
            r"{\rtf1\ansi\ansicpg1252\deff0\uc1"
            r"{\fonttbl{\f0\fswiss Arial;}{\f1\fmodern Courier New;}}"
            r"{\colortbl;\red0\green0\blue255;}"
            r"\viewkind4\pard\f0\fs22 "
            + body
            + "}"
        )
        return document.encode("ascii")

    def _render_block(self, element: ElementTree.Element, depth: int = 0) -> str:
        tag = element.tag
        if tag in self._HEADING_SIZES:
            return (
                rf"\pard\keepn\sb240\sa120\b\fs{self._HEADING_SIZES[tag]} "
                + self._render_inline_contents(element)
                + r"\b0\fs22\par "
            )
        if tag == "p":
            return (
                r"\pard\f0\fs22 "
                + self._render_inline_contents(element)
                + r"\par "
            )
        if tag == "blockquote":
            parts = []
            for child in element:
                if child.tag == "p":
                    parts.append(
                        r"\pard\li720\ri360 "
                        + self._render_inline_contents(child)
                        + r"\par "
                    )
                else:
                    parts.append(self._render_block(child, depth))
            return "".join(parts)
        if tag in {"ul", "ol"}:
            return self._render_list(element, depth)
        if tag == "pre":
            text = "".join(element.itertext())
            return (
                r"\pard\li360\sa120\f1\fs20 "
                + _escape_rtf_text(text, preserve_lines=True)
                + r"\f0\fs22\par "
            )
        if tag == "hr":
            return r"\pard\brdrb\brdrs\brdrw10\brsp20\par "
        return (
            r"\pard " + self._render_inline_contents(element) + r"\par "
        )

    def _render_list(self, element: ElementTree.Element, depth: int) -> str:
        parts: list[str] = []
        ordered = element.tag == "ol"
        item_number = int(element.get("start", "1"))
        left_indent = 360 * (depth + 1)
        first_line_indent = -240
        for item in element:
            if item.tag != "li":
                continue
            marker = f"{item_number}." if ordered else r"\bullet"
            parts.append(
                rf"\pard\li{left_indent}\fi{first_line_indent} "
                + marker
                + r"\tab "
                + self._render_list_item_contents(item, depth)
                + r"\par "
            )
            item_number += 1
        return "".join(parts)

    def _render_list_item_contents(
        self,
        item: ElementTree.Element,
        depth: int,
    ) -> str:
        parts = [_escape_rtf_text(item.text or "")]
        nested_lists: list[ElementTree.Element] = []
        for child in item:
            if child.tag in {"ul", "ol"}:
                nested_lists.append(child)
            elif child.tag == "p":
                parts.append(self._render_inline_contents(child))
            else:
                parts.append(self._render_inline(child))
            parts.append(_escape_rtf_text(child.tail or ""))
        for nested in nested_lists:
            parts.append(r"\par " + self._render_list(nested, depth + 1))
        return "".join(parts)

    def _render_inline_contents(self, element: ElementTree.Element) -> str:
        parts = [_escape_rtf_text(element.text or "")]
        for child in element:
            parts.append(self._render_inline(child))
            parts.append(_escape_rtf_text(child.tail or ""))
        return "".join(parts)

    def _render_inline(self, element: ElementTree.Element) -> str:
        tag = element.tag
        contents = self._render_inline_contents(element)
        if tag in {"strong", "b"}:
            return r"{\b " + contents + "}"
        if tag in {"em", "i"}:
            return r"{\i " + contents + "}"
        if tag in {"del", "s"}:
            return r"{\strike " + contents + "}"
        if tag == "code":
            return r"{\f1 " + contents + "}"
        if tag == "br":
            return r"\line "
        if tag == "a":
            href = quote(
                element.get("href", ""),
                safe="/:#?&=@%+;,-._~",
            )
            instruction = _escape_rtf_text(f'HYPERLINK "{href}"')
            return (
                r"{\field{\*\fldinst "
                + instruction
                + r"}{\fldrslt{\ul\cf1 "
                + contents
                + r"}}}"
            )
        return contents


def _render_rtf(root: ElementTree.Element) -> bytes:
    """Render one normalized Markdown tree as a complete RTF document."""
    return _RtfRenderer().render(root)
