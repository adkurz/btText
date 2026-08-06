import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ui.search_dialog import SearchDialog


class SearchDialogResultListTestCase(unittest.TestCase):
    def test_search_focuses_first_result_without_selecting_it(self):
        snippet = SimpleNamespace(
            id=7,
            category_id=3,
            name="Example",
            weight=1,
            content="Example content",
        )
        result_list = SimpleNamespace(
            Freeze=Mock(),
            Thaw=Mock(),
            DeleteAllItems=Mock(),
            Append=Mock(return_value=0),
            SetItemData=Mock(),
            GetItemCount=Mock(return_value=1),
            Focus=Mock(),
            Select=Mock(),
        )
        dialog = SimpleNamespace(
            search_input=SimpleNamespace(GetValue=Mock(return_value="example")),
            result_list=result_list,
            open_button=SimpleNamespace(Enable=Mock()),
            _selected_snippet_id=None,
            _model=SimpleNamespace(
                search_snippets=Mock(return_value=[snippet]),
                get_category_path=Mock(return_value="Category"),
            ),
        )

        SearchDialog._run_search(dialog)

        result_list.Focus.assert_called_once_with(0)
        result_list.Select.assert_not_called()


if __name__ == "__main__":
    unittest.main()
