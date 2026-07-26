import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def get_marked_arguments(
    relative_file,
    function_name="_",
    argument_positions=(0,),
):
    source_file = PROJECT_ROOT / relative_file
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    arguments = set()
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == function_name
            and len(node.args) > max(argument_positions)
        ):
            continue
        values = tuple(
            node.args[position].value
            for position in argument_positions
            if (
                isinstance(node.args[position], ast.Constant)
                and isinstance(node.args[position].value, str)
            )
        )
        if len(values) != len(argument_positions):
            continue
        arguments.add(values[0] if len(values) == 1 else values)
    return arguments


class TranslationMarkersTestCase(unittest.TestCase):
    def test_application_startup_dialog_is_marked(self):
        self.assertLessEqual(
            {"Settings error", "Language error"},
            get_marked_arguments("btText.py"),
        )

    def test_main_window_labels_menus_and_dialogs_are_marked(self):
        expected_messages = {
            "&Categories",
            "&Edit",
            "&Help",
            "&Search...\tF3",
            "&Settings...\tCtrl+,",
            "&Snippets",
            "About",
            "Categories",
            "Clipboard restore error",
            "Error",
            "F3: Search snippets    Enter: Insert selected snippet",
            "Hotkey error",
            "Paste error",
            "Settings error",
            "Snippets in the selected category",
            "The category of the selected snippet no longer exists.",
            "The global hotkey {} is already in use and could not be registered.",
            (
                "The previous clipboard contents could not be restored after "
                "multiple attempts. The clipboard may still contain the "
                "inserted snippet.\n\n{}"
            ),
            (
                "The previous hotkey could not be restored. No global hotkey "
                "is active."
            ),
            (
                "The selected hotkey {} is already in use and the previous "
                "hotkey could not be restored. No global hotkey is active."
            ),
            (
                "The selected hotkey {} is already in use. The previous "
                "hotkey has been restored."
            ),
            "The selected snippet no longer exists.",
            "There is no previous window to insert the snippet into.",
        }

        self.assertLessEqual(
            expected_messages,
            get_marked_arguments("ui/main_frame.py"),
        )

    def test_tray_tooltip_and_commands_are_marked(self):
        self.assertLessEqual(
            {
                "Exit",
                "Show snippets",
                "{app_name} - {app_version}",
            },
            get_marked_arguments("ui/tray_icon.py"),
        )

    def test_category_tree_commands_and_dialogs_are_marked(self):
        self.assertLessEqual(
            {
                "No categories",
                "New top-level category\tCtrl+N",
                "Paste as top-level\tCtrl+Shift+V",
                "Enter the name of the new category",
                "Delete category",
                "A snippet must be pasted into a category.",
                "Category error",
            },
            get_marked_arguments("ui/category_tree.py"),
        )

    def test_snippet_list_uses_plural_aware_messages(self):
        plural_messages = get_marked_arguments(
            "ui/snippet_list.py",
            "ngettext",
            (0, 1),
        )

        self.assertIn(
            ("Copy snippet\tCtrl+C", "Copy snippets\tCtrl+C"),
            plural_messages,
        )
        self.assertIn(
            (
                "Deleted {count} snippet.",
                "Deleted {count} snippets.",
            ),
            plural_messages,
        )
        self.assertIn(
            (
                "Transferred {count} item.",
                "Transferred {count} items.",
            ),
            plural_messages,
        )

    def test_editors_search_and_settings_are_marked(self):
        expected_by_file = {
            "ui/snippet_editor.py": {
                "Add snippet",
                "Edit snippet",
                "&Name",
                "&Category",
                "&Weight",
                "C&ontent",
                "Validation error",
            },
            "ui/search_dialog.py": {
                "Search snippets",
                "&Search",
                "Search &results",
                "&Show snippet",
                "Search error",
            },
            "ui/settings_dialog.py": {
                "Settings",
                "&General",
                "&Keyboard",
                "&Language",
                "Current &hotkey",
                "&Record new shortcut",
                "Language changes take effect after restarting btText.",
                (
                    "Include copied snippet &text in the Windows clipboard "
                    "history"
                ),
                (
                    "Allow copied snippet text to be stored in the Windows "
                    "&cloud"
                ),
                "Recording is not active.",
                "Shortcut recording cancelled.",
                "The settings have been applied.",
            },
            "i18n.py": {
                "System default",
            },
            "ui/validators.py": {
                "The input field must not be empty!",
                "Validation error",
            },
            "error_messages.py": {
                (
                    "The translation catalog for {language} could not be "
                    "loaded. btText will continue in English.\n\n{reason}"
                ),
            },
        }
        for relative_file, expected_messages in expected_by_file.items():
            with self.subTest(relative_file=relative_file):
                self.assertLessEqual(
                    expected_messages,
                    get_marked_arguments(relative_file),
                )

    def test_weight_labels_use_translation_context(self):
        self.assertEqual(
            get_marked_arguments("ui/utils.py", "pgettext", (0, 1)),
            {
                ("snippet weight", "Low"),
                ("snippet weight", "Middle"),
                ("snippet weight", "High"),
            },
        )


if __name__ == "__main__":
    unittest.main()
