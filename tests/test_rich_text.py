import unittest

from core.rich_text import ClipboardContent, render_clipboard_content
from core.variables import RenderedSnippet


class RichTextRenderingTestCase(unittest.TestCase):
    def test_plain_snippet_is_not_interpreted_as_markdown(self):
        result = render_clipboard_content(RenderedSnippet("**literal**", 2), False)

        self.assertEqual(result, ClipboardContent("**literal**", None, 2))

    def test_markdown_produces_html_and_readable_plain_text(self):
        result = render_clipboard_content(
            RenderedSnippet("# Greeting\n\nHello **Ada**.\n\n- First\n- Second"),
            True,
        )

        self.assertEqual(
            result.plain_text,
            "Greeting\n\nHello Ada.\n\n- First\n- Second",
        )
        self.assertEqual(
            result.html,
            "<h1>Greeting</h1><p>Hello <strong>Ada</strong>.</p>"
            "<ul><li>First</li><li>Second</li></ul>",
        )
        self.assertTrue(result.rtf.startswith(b"{\\rtf1"))
        self.assertIn(b"\\b Ada", result.rtf)
        self.assertIn(b"\\bullet\\tab First", result.rtf)

    def test_raw_html_is_escaped_instead_of_being_activated(self):
        result = render_clipboard_content(
            RenderedSnippet("<script>alert('unsafe')</script>"),
            True,
        )

        self.assertEqual(result.plain_text, "<script>alert('unsafe')</script>")
        self.assertNotIn("<script>", result.html)
        self.assertIn("&lt;script&gt;", result.html)

    def test_only_supported_absolute_links_remain_actionable(self):
        for target in (
            "http://example.com/path",
            "https://example.com/path",
            "mailto:person@example.com",
        ):
            with self.subTest(target=target):
                result = render_clipboard_content(
                    RenderedSnippet(f"[safe]({target})"),
                    True,
                )

                self.assertIn(f'href="{target}"', result.html)
                self.assertIn(
                    f'HYPERLINK "{target}"'.encode("ascii"),
                    result.rtf,
                )

    def test_unsupported_links_are_rendered_as_plain_labels(self):
        for target in (
            "javascript:alert(1)",
            "file:///C:/secret.txt",
            "//example.com/path",
            "relative/path",
            "http:missing-host",
            "mailto:",
        ):
            with self.subTest(target=target):
                result = render_clipboard_content(
                    RenderedSnippet(f"[**label**]({target})"),
                    True,
                )

                self.assertEqual(result.plain_text, "label")
                self.assertNotIn("<a", result.html)
                self.assertNotIn("href=", result.html)
                self.assertNotIn(b"HYPERLINK", result.rtf)
                self.assertIn("<strong>label</strong>", result.html)
                self.assertIn(b"\\b label", result.rtf)

    def test_images_are_replaced_with_alternative_text_in_every_format(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "Before ![diagram](https://example.com/tracker.png) after"
            ),
            True,
        )

        self.assertEqual(result.plain_text, "Before diagram after")
        self.assertEqual(result.html, "<p>Before diagram after</p>")
        self.assertIn(b"Before diagram after", result.rtf)
        self.assertNotIn("<img", result.html)
        self.assertNotIn("tracker.png", result.html)
        self.assertNotIn(b"tracker.png", result.rtf)

    def test_image_replacement_preserves_surrounding_inline_markup(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "**Before ![diagram](https://example.com/image.png) after**"
            ),
            True,
        )

        self.assertEqual(
            result.html,
            "<p><strong>Before diagram after</strong></p>",
        )
        self.assertIn(b"\\b Before diagram after", result.rtf)

    def test_markdown_rejects_rendered_cursor_metadata(self):
        with self.assertRaises(ValueError):
            render_clipboard_content(
                RenderedSnippet("**AB** C", cursor_offset_from_end=1),
                True,
            )

    def test_rtf_omits_only_the_final_paragraph_break(self):
        single = render_clipboard_content(
            RenderedSnippet("Hello **world**"),
            True,
        )
        multiple = render_clipboard_content(
            RenderedSnippet("First\n\nSecond"),
            True,
        )

        self.assertEqual(single.html, "<p>Hello <strong>world</strong></p>")
        self.assertEqual(multiple.html, "<p>First</p><p>Second</p>")
        self.assertFalse(single.rtf.decode("ascii").endswith(r"\par }"))
        self.assertFalse(multiple.rtf.decode("ascii").endswith(r"\par }"))
        self.assertIn(r"First\par ", multiple.rtf.decode("ascii"))

    def test_rtf_escapes_markup_unicode_and_links(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "Text {backslash\\ path} \N{GRINNING FACE} and "
                "[a link](https://example.com/a b)"
            ),
            True,
        )

        rtf = result.rtf.decode("ascii")
        self.assertIn(r"\{backslash\\ path\}", rtf)
        self.assertIn(r"\u-10179?\u-8704?", rtf)
        self.assertIn('HYPERLINK "https://example.com/a%20b"', rtf)
        self.assertEqual(rtf.count("{"), rtf.count("}"))

    def test_rtf_formats_headings_code_quotes_and_nested_lists(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "## Heading\n\n> Quote with `code`\n\n"
                "1. First\n    - Nested\n2. Second\n\n---"
            ),
            True,
        )

        rtf = result.rtf.decode("ascii")
        self.assertIn(r"\b\fs32 Heading", rtf)
        self.assertIn(r"\f1 code", rtf)
        self.assertIn(r"\li720", rtf)
        self.assertIn(r"1.\tab First", rtf)
        self.assertIn(r"\li720\fi-240 \bullet\tab Nested", rtf)
        self.assertIn(r"\brdrb\brdrs\brdrw10", rtf)


if __name__ == "__main__":
    unittest.main()
