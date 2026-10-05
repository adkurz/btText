"""Render snippet text into the formats offered on the Windows clipboard."""

from copy import deepcopy
from dataclasses import dataclass
from html import unescape
from html.entities import html5
import re
from xml.etree import ElementTree
from urllib.parse import quote, urlsplit

import markdown
from markdown import util as markdown_util
from markdown.extensions import Extension
from markdown.treeprocessors import Treeprocessor

from core.variables import RenderedSnippet


_ALLOWED_LINK_SCHEMES = frozenset(("http", "https", "mailto"))
_AMP_ENTITY_RE = re.compile(
    re.escape(markdown_util.AMP_SUBSTITUTE)
    + r"([a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);"
)
_ATTRIBUTE_ENTITY_RE = re.compile(r"&([a-zA-Z][a-zA-Z0-9]*|#[0-9]+|#x[0-9a-fA-F]+);")


@dataclass(frozen=True)
class ClipboardContent:
    """Bundle plain text, optional HTML and RTF, and caret metadata."""

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
    # Markdown returns early for blank input without running tree processors.
    # Empty variable values therefore need an ordinary empty document tree.
    if not source.strip():
        return ElementTree.Element("div")

    capture = _TreeCaptureExtension()
    parser = markdown.Markdown(extensions=[capture], output_format="html")
    parser.convert(source)
    if capture.root is None:
        raise RuntimeError("Markdown did not produce a document tree.")
    _normalize_markdown_tree(capture.root, parser)
    return capture.root


def _normalize_markdown_tree(
    root: ElementTree.Element,
    parser: markdown.Markdown,
) -> None:
    """Resolve parser representations into Unicode before format rendering."""
    def stashed_entity(match: re.Match[str]) -> str:
        # Raw HTML processors are disabled, so only entities enter this stash.
        return str(parser.htmlStash.rawHtmlBlocks[int(match.group(1))])

    def normalize_text(value: str) -> str:
        # Decode only parser-generated entities. Decoding the whole string
        # would also reinterpret literal or already decoded entity text.
        value = markdown_util.HTML_PLACEHOLDER_RE.sub(
            lambda match: unescape(stashed_entity(match)), value
        )
        return _AMP_ENTITY_RE.sub(
            lambda match: unescape("&" + match.group(1) + ";"), value
        )

    def attribute_entity(match: re.Match[str]) -> str:
        # Markdown's serializer preserves complete entity references in
        # attributes. Ordinary URL parameters such as &copy=1 stay literal.
        name = match.group(1)
        if name.startswith("#"):
            return unescape(match.group(0))
        return html5.get(name + ";", match.group(0))

    for element in root.iter():
        if element.text:
            # Code is HTML-escaped by Markdown even before serialization.
            element.text = (
                unescape(element.text)
                if element.tag == "code"
                else normalize_text(element.text)
            )
        if element.tail:
            element.tail = normalize_text(element.tail)
        for name, value in element.items():
            value = markdown_util.HTML_PLACEHOLDER_RE.sub(stashed_entity, value)
            value = value.replace(markdown_util.AMP_SUBSTITUTE, "&")
            element.set(name, _ATTRIBUTE_ENTITY_RE.sub(attribute_entity, value))


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


@dataclass(frozen=True)
class _RtfLayout:
    """Carry inherited paragraph indentation through nested RTF blocks."""

    left_indent: int = 0
    right_indent: int = 0

    def indented(self, left: int = 0, right: int = 0) -> "_RtfLayout":
        return _RtfLayout(
            self.left_indent + left,
            self.right_indent + right,
        )

    @property
    def controls(self) -> str:
        return rf"\li{self.left_indent}\ri{self.right_indent}"


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

    def _render_block(
        self,
        element: ElementTree.Element,
        layout: _RtfLayout = _RtfLayout(),
    ) -> str:
        tag = element.tag
        if tag in self._HEADING_SIZES:
            return (
                rf"\pard{layout.controls}\keepn\sb240\sa120\b"
                rf"\fs{self._HEADING_SIZES[tag]} "
                + self._render_inline_contents(element)
                + r"\b0\fs22\par "
            )
        if tag == "p":
            return (
                rf"\pard{layout.controls}\f0\fs22 "
                + self._render_inline_contents(element)
                + r"\par "
            )
        if tag == "blockquote":
            quote_layout = layout.indented(left=720, right=360)
            return "".join(
                self._render_block(child, quote_layout)
                for child in element
            )
        if tag in {"ul", "ol"}:
            return self._render_list(element, layout, depth=0)
        if tag == "pre":
            text = "".join(element.itertext())
            code_layout = layout.indented(left=360)
            return (
                rf"\pard{code_layout.controls}"
                r"\sa120\f1\fs20 "
                + _escape_rtf_text(text, preserve_lines=True)
                + r"\f0\fs22\par "
            )
        if tag == "hr":
            return (
                rf"\pard{layout.controls}"
                r"\brdrb\brdrs\brdrw10\brsp20\par "
            )
        return (
            rf"\pard{layout.controls} "
            + self._render_inline_contents(element)
            + r"\par "
        )

    def _render_list(
        self,
        element: ElementTree.Element,
        layout: _RtfLayout,
        depth: int,
    ) -> str:
        parts: list[str] = []
        ordered = element.tag == "ol"
        item_number = int(element.get("start", "1"))
        for item in element:
            if item.tag != "li":
                continue
            marker = f"{item_number}." if ordered else r"\bullet"
            parts.append(
                self._render_list_item(
                    item,
                    marker,
                    layout,
                    depth,
                )
            )
            item_number += 1
        return "".join(parts)

    def _render_list_item(
        self,
        item: ElementTree.Element,
        marker: str,
        layout: _RtfLayout,
        depth: int,
    ) -> str:
        parts: list[str] = []
        inline_parts = [_escape_rtf_text(item.text or "")]
        marker_pending = True
        item_layout = layout.indented(left=360 * (depth + 1))

        def flush_inline() -> None:
            nonlocal marker_pending
            contents = "".join(inline_parts)
            inline_parts.clear()
            if not contents:
                return
            parts.append(
                self._render_list_paragraph(
                    contents,
                    marker if marker_pending else None,
                    item_layout,
                )
            )
            marker_pending = False

        for child in item:
            if child.tag == "p":
                flush_inline()
                parts.append(
                    self._render_list_paragraph(
                        self._render_inline_contents(child),
                        marker if marker_pending else None,
                        item_layout,
                    )
                )
                marker_pending = False
            elif child.tag in {"ul", "ol"}:
                flush_inline()
                parts.append(
                    self._render_list(
                        child,
                        layout,
                        depth + 1,
                    )
                )
            else:
                inline_parts.append(self._render_inline(child))
            inline_parts.append(_escape_rtf_text(child.tail or ""))
        flush_inline()
        return "".join(parts)

    @staticmethod
    def _render_list_paragraph(
        contents: str,
        marker: str | None,
        layout: _RtfLayout,
    ) -> str:
        if marker is None:
            prefix = rf"\pard{layout.controls} "
        else:
            prefix = (
                rf"\pard{layout.controls}\fi-240 "
                + marker
                + r"\tab "
            )
        return prefix + contents + r"\par "

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
