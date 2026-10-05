import unittest

from core.rich_text import ClipboardContent, render_clipboard_content
from core.variables import RenderedSnippet


class RichTextRenderingTestCase(unittest.TestCase):
    def test_blank_markdown_produces_empty_clipboard_representations(self):
        for source in ("", " ", "\t\r\n", "\u00a0"):
            with self.subTest(source=source):
                result = render_clipboard_content(RenderedSnippet(source), True)

                self.assertEqual(result.plain_text, "")
                self.assertEqual(result.html, "")
                self.assertIsNone(result.cursor_offset_from_end)
                self.assertTrue(result.rtf.startswith(b"{\\rtf1"))
                self.assertTrue(result.rtf.endswith(b"}"))
                self.assertNotIn(rb"\par ", result.rtf)

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

    def test_entities_are_decoded_in_text_and_inline_tails(self):
        result = render_clipboard_content(
            RenderedSnippet("A &amp; **B &copy;** &#169; &#x1F600; &amp;amp;"),
            True,
        )

        self.assertEqual(result.plain_text, "A & B \u00a9 \u00a9 \U0001f600 &amp;")
        self.assertEqual(
            result.html,
            "<p>A &amp; <strong>B \u00a9</strong> \u00a9 \U0001f600 &amp;amp;</p>",
        )
        self.assertIn(b"A & ", result.rtf)
        self.assertIn(rb"\b B \u169?", result.rtf)
        self.assertIn(rb"\u-10179?\u-8704? &amp;", result.rtf)
        for value in (result.plain_text, result.html, result.rtf.decode("ascii")):
            self.assertNotIn("wzxhzdk:", value)

    def test_automatic_email_links_are_normalized_before_link_validation(self):
        for source in ("<person@example.com>", "<mailto:person@example.com>"):
            with self.subTest(source=source):
                result = render_clipboard_content(RenderedSnippet(source), True)

                self.assertEqual(result.plain_text, "person@example.com")
                self.assertEqual(
                    result.html,
                    '<p><a href="mailto:person@example.com">person@example.com</a></p>',
                )
                self.assertIn(b'HYPERLINK "mailto:person@example.com"', result.rtf)
                self.assertNotIn(rb"\u2?amp", result.rtf)

    def test_inline_code_preserves_literal_special_characters_and_entities(self):
        result = render_clipboard_content(
            RenderedSnippet("`a < b > c & &amp; &#169; {x}`"),
            True,
        )

        self.assertEqual(result.plain_text, "a < b > c & &amp; &#169; {x}")
        self.assertEqual(
            result.html,
            "<p><code>a &lt; b &gt; c &amp; &amp;amp; &amp;#169; {x}</code></p>",
        )
        self.assertIn(rb"\f1 a < b > c & &amp; &#169; \{x\}", result.rtf)

    def test_code_blocks_preserve_literal_special_characters_and_entities(self):
        result = render_clipboard_content(
            RenderedSnippet("    a < b & &amp;\n    &#169; > c"),
            True,
        )

        self.assertEqual(result.plain_text, "a < b & &amp;\n&#169; > c")
        self.assertIn("a &lt; b &amp; &amp;amp;\n&amp;#169; &gt; c", result.html)
        self.assertIn(rb"a < b & &amp;\line &#169; > c", result.rtf)

    def test_link_attributes_decode_entities_exactly_once(self):
        result = render_clipboard_content(
            RenderedSnippet(
                '[label](https://example.com/?a=1&amp;b=&amp;amp; "A &amp; B")'
            ),
            True,
        )

        self.assertEqual(result.plain_text, "label")
        self.assertIn('href="https://example.com/?a=1&amp;b=&amp;amp;"', result.html)
        self.assertIn('title="A &amp; B"', result.html)
        self.assertIn(b'HYPERLINK "https://example.com/?a=1&b=&amp;"', result.rtf)

    def test_entity_encoded_unsupported_link_is_rejected_after_normalization(self):
        result = render_clipboard_content(
            RenderedSnippet("[label](javascript&#58;alert(1))"),
            True,
        )

        self.assertEqual(result.plain_text, "label")
        self.assertEqual(result.html, "<p><span>label</span></p>")
        self.assertNotIn(b"HYPERLINK", result.rtf)

    def test_url_parameters_and_alternative_text_preserve_entity_like_names(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "[label](https://example.com/?x=1&copy=2&notebook=3&notit;=4) "
                "![A &copy=1 &notebook &notit;](https://example.com/image.png)"
            ),
            True,
        )

        self.assertEqual(result.plain_text, "label A &copy=1 &notebook &notit;")
        self.assertIn(
            'href="https://example.com/?x=1&amp;copy=2&amp;notebook=3&amp;notit;=4"',
            result.html,
        )
        self.assertIn("A &amp;copy=1 &amp;notebook &amp;notit;", result.html)
        self.assertIn(
            b'HYPERLINK "https://example.com/?x=1&copy=2&notebook=3&notit;=4"',
            result.rtf,
        )

    def test_image_alternative_text_decodes_entities_exactly_once(self):
        result = render_clipboard_content(
            RenderedSnippet("![A &amp; B &amp;amp;](https://example.com/image.png)"),
            True,
        )

        self.assertEqual(result.plain_text, "A & B &amp;")
        self.assertEqual(result.html, "<p>A &amp; B &amp;amp;</p>")
        self.assertIn(b"A & B &amp;", result.rtf)

    def test_decoded_entities_remain_text_instead_of_html_or_markdown(self):
        result = render_clipboard_content(
            RenderedSnippet("&lt;script&gt;x&lt;/script&gt; &#42;literal&#42; &unknown;"),
            True,
        )

        self.assertEqual(result.plain_text, "<script>x</script> *literal* &unknown;")
        self.assertEqual(
            result.html,
            "<p>&lt;script&gt;x&lt;/script&gt; *literal* &amp;unknown;</p>",
        )
        self.assertIn(b"<script>x</script> *literal* &unknown;", result.rtf)

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
        self.assertIn(r"\li720\ri0\fi-240 \bullet\tab Nested", rtf)
        self.assertIn(r"\brdrb\brdrs\brdrw10", rtf)

    def test_rtf_preserves_three_nested_list_levels_in_document_order(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "- Level one\n"
                "    - Level two\n"
                "        - Level three"
            ),
            True,
        )

        rtf = result.rtf.decode("ascii")
        levels = (
            r"\li360\ri0\fi-240 \bullet\tab Level one",
            r"\li720\ri0\fi-240 \bullet\tab Level two",
            r"\li1080\ri0\fi-240 \bullet\tab Level three",
        )
        positions = tuple(rtf.index(level) for level in levels)
        self.assertEqual(positions, tuple(sorted(positions)))

    def test_rtf_combines_quote_and_nested_list_indentation(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "> Intro\n>\n"
                "> - Quoted one\n"
                ">     - Quoted two\n>\n"
                "> Outro"
            ),
            True,
        )

        rtf = result.rtf.decode("ascii")
        blocks = (
            r"\li720\ri360\f0\fs22 Intro",
            r"\li1080\ri360\fi-240 \bullet\tab Quoted one",
            r"\li1440\ri360\fi-240 \bullet\tab Quoted two",
            r"\li720\ri360\f0\fs22 Outro",
        )
        positions = tuple(rtf.index(block) for block in blocks)
        self.assertEqual(positions, tuple(sorted(positions)))

    def test_rtf_renders_multiple_list_item_paragraphs_before_nested_list(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "- First paragraph\n\n"
                "    Second paragraph\n\n"
                "    - Nested after paragraphs\n\n"
                "- Last"
            ),
            True,
        )

        rtf = result.rtf.decode("ascii")
        blocks = (
            r"\li360\ri0\fi-240 \bullet\tab First paragraph",
            r"\li360\ri0 Second paragraph",
            r"\li720\ri0\fi-240 \bullet\tab Nested after paragraphs",
            r"\li360\ri0\fi-240 \bullet\tab Last",
        )
        positions = tuple(rtf.index(block) for block in blocks)
        self.assertEqual(positions, tuple(sorted(positions)))
        self.assertNotIn(r"\bullet\tab Second paragraph", rtf)

    def test_rtf_encodes_diverse_unicode_as_utf16_code_units(self):
        result = render_clipboard_content(
            RenderedSnippet(
                "Latin é; combining e\u0301; Hebrew אב; CJK 漢; emoji 🧑‍💻"
            ),
            True,
        )

        rtf = result.rtf.decode("ascii")
        for encoded in (
            r"\u233?",
            r"e\u769?",
            r"\u1488?\u1489?",
            r"\u28450?",
            r"\u-10178?\u-8751?\u8205?\u-10179?\u-9029?",
        ):
            with self.subTest(encoded=encoded):
                self.assertIn(encoded, rtf)
        self.assertEqual(rtf.count("{"), rtf.count("}"))


if __name__ == "__main__":
    unittest.main()
