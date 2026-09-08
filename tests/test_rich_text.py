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

    def test_raw_html_is_escaped_instead_of_being_activated(self):
        result = render_clipboard_content(
            RenderedSnippet("<script>alert('unsafe')</script>"),
            True,
        )

        self.assertEqual(result.plain_text, "<script>alert('unsafe')</script>")
        self.assertNotIn("<script>", result.html)
        self.assertIn("&lt;script&gt;", result.html)

    def test_cursor_offset_is_mapped_to_rendered_plain_text(self):
        result = render_clipboard_content(
            RenderedSnippet("**AB** C", cursor_offset_from_end=1),
            True,
        )

        self.assertEqual(result.plain_text, "AB C")
        self.assertEqual(result.cursor_offset_from_end, 1)
        self.assertNotIn("\ue000", result.html)


if __name__ == "__main__":
    unittest.main()
