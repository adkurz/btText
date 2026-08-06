import unittest
from types import MethodType, SimpleNamespace
from unittest.mock import Mock, patch

from ui.search_dialog import SearchDialog


class SearchDialogResultListTestCase(unittest.TestCase):
    def test_search_selects_and_focuses_first_result(self):
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
            GetItemData=Mock(return_value=7),
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
        dialog._select_result = MethodType(SearchDialog._select_result, dialog)

        SearchDialog._run_search(dialog)

        result_list.Select.assert_called_once_with(0)
        result_list.Focus.assert_called_once_with(0)
        self.assertEqual(dialog._selected_snippet_id, 7)
        dialog.open_button.Enable.assert_called_with(True)

    def test_deselect_schedules_one_selection_check(self):
        result_list = SimpleNamespace(
            GetItemCount=Mock(return_value=1),
        )
        dialog = SimpleNamespace(
            _updating_results=False,
            _selection_check_pending=False,
            result_list=result_list,
            _ensure_result_selected=Mock(),
        )
        event = SimpleNamespace(GetIndex=Mock(return_value=0))

        with patch("ui.search_dialog.wx.CallAfter") as call_after:
            SearchDialog._on_result_deselected(dialog, event)
            SearchDialog._on_result_deselected(dialog, event)

        call_after.assert_called_once_with(dialog._ensure_result_selected, 0)

    def test_selection_check_keeps_new_arrow_key_selection(self):
        result_list = SimpleNamespace(
            GetItemCount=Mock(return_value=2),
            GetFirstSelected=Mock(return_value=1),
        )
        dialog = SimpleNamespace(
            _updating_results=False,
            _selection_check_pending=True,
            result_list=result_list,
            _select_result=Mock(),
        )

        SearchDialog._ensure_result_selected(dialog, 0)

        dialog._select_result.assert_not_called()
        self.assertFalse(dialog._selection_check_pending)

    def test_selection_check_restores_missing_selection(self):
        result_list = SimpleNamespace(
            GetItemCount=Mock(return_value=1),
            GetFirstSelected=Mock(return_value=-1),
        )
        dialog = SimpleNamespace(
            _updating_results=False,
            _selection_check_pending=True,
            result_list=result_list,
            _select_result=Mock(),
        )

        SearchDialog._ensure_result_selected(dialog, 0)

        dialog._select_result.assert_called_once_with(0)
        self.assertFalse(dialog._selection_check_pending)


if __name__ == "__main__":
    unittest.main()
