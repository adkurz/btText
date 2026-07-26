"""Enforce translation markers at user-visible wxPython text boundaries."""

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKER_NAMES = frozenset({"_", "ngettext", "pgettext"})


@dataclass(frozen=True)
class TextArguments:
    """Describe positional and named user-visible arguments of a call."""

    positions: tuple[int, ...] = ()
    keywords: tuple[str, ...] = ()


# These rules are intentionally about stable APIs rather than current messages.
# Adding a new message to an existing UI call therefore needs no test change.
TEXT_ARGUMENTS_BY_CALL = {
    "AddPage": TextArguments((1,)),
    "AddRoot": TextArguments((0,)),
    "Append": TextArguments((1,)),
    "AppendColumn": TextArguments((0,)),
    "Button": TextArguments((2,), ("label",)),
    "CheckBox": TextArguments((2,), ("label",)),
    "Dialog": TextArguments((1,), ("title",)),
    "MessageBox": TextArguments((0, 1), ("message", "caption")),
    "MessageDialog": TextArguments((1, 2), ("message", "caption")),
    "RadioBox": TextArguments((2, 5), ("label", "choices")),
    "SetLabel": TextArguments((0,)),
    "SetName": TextArguments((0,)),
    "SetStatusText": TextArguments((0,)),
    "StaticText": TextArguments((1,), ("label",)),
    "TextEntryDialog": TextArguments((1, 2), ("message", "caption")),
}


def _call_name(node):
    """Return the final component of a called function or method name."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _unmarked_literals(expression):
    """Return string literals not enclosed by a translation marker."""
    unmarked = []

    def visit(node, inside_marker=False):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value and not inside_marker:
                unmarked.append(node)
            return

        marker_call = (
            isinstance(node, ast.Call)
            and _call_name(node.func) in MARKER_NAMES
        )
        for child in ast.iter_child_nodes(node):
            visit(child, inside_marker or marker_call)

    visit(expression)
    return unmarked


def _scope_nodes(scope):
    """Yield nodes belonging to ``scope`` without entering nested scopes."""
    nested_scope_types = (
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.FunctionDef,
        ast.Lambda,
    )
    pending = list(ast.iter_child_nodes(scope))
    while pending:
        node = pending.pop()
        yield node
        if not isinstance(node, nested_scope_types):
            pending.extend(ast.iter_child_nodes(node))


def _assignments_by_name(scope):
    """Collect simple local assignments that can later feed a UI call."""
    assignments = {}
    for node in _scope_nodes(scope):
        targets_and_value = ()
        if isinstance(node, (ast.Assign, ast.NamedExpr)):
            targets = node.targets if isinstance(node, ast.Assign) else (node.target,)
            targets_and_value = ((target, node.value) for target in targets)
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets_and_value = ((node.target, node.value),)

        for target, value in targets_and_value:
            if isinstance(target, ast.Name):
                assignments.setdefault(target.id, []).append(value)
    return assignments


def _argument_expressions(argument, assignments, resolving=()):
    """Yield an argument and simple local values from which it can originate."""
    yield argument
    if not isinstance(argument, ast.Name) or argument.id in resolving:
        return
    for value in assignments.get(argument.id, ()):
        yield from _argument_expressions(
            value,
            assignments,
            resolving + (argument.id,),
        )


def find_unmarked_ui_strings(source, filename="<unknown>"):
    """Find literal UI arguments that bypass gettext marker functions."""
    tree = ast.parse(source, filename=filename)
    violations = []
    scopes = [tree]
    scopes.extend(
        node
        for node in ast.walk(tree)
        if isinstance(
            node,
            (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef, ast.Lambda),
        )
    )
    for scope in scopes:
        assignments = _assignments_by_name(scope)
        for node in _scope_nodes(scope):
            if not isinstance(node, ast.Call):
                continue
            rule = TEXT_ARGUMENTS_BY_CALL.get(_call_name(node.func))
            if rule is None:
                continue

            arguments = [
                node.args[position]
                for position in rule.positions
                if position < len(node.args)
            ]
            arguments.extend(
                keyword.value
                for keyword in node.keywords
                if keyword.arg in rule.keywords
            )
            for argument in arguments:
                for expression in _argument_expressions(argument, assignments):
                    violations.extend(
                        (literal.lineno, literal.value)
                        for literal in _unmarked_literals(expression)
                    )
    return violations


def production_python_files():
    """Return application Python files covered by the marker audit."""
    excluded_directories = {
        ".git",
        ".venv",
        "__pycache__",
        "build",
        "tests",
        "tools",
    }
    return tuple(
        source_file
        for source_file in sorted(PROJECT_ROOT.rglob("*.py"))
        if not excluded_directories.intersection(
            source_file.relative_to(PROJECT_ROOT).parts
        )
    )


class TranslationMarkersTestCase(unittest.TestCase):
    def test_user_visible_literal_arguments_are_marked(self):
        violations = []
        for source_file in production_python_files():
            relative_file = source_file.relative_to(PROJECT_ROOT)
            violations.extend(
                "{}:{}: {!r}".format(relative_file, line_number, message)
                for line_number, message in find_unmarked_ui_strings(
                    source_file.read_text(encoding="utf-8"),
                    str(relative_file),
                )
            )

        self.assertEqual(
            violations,
            [],
            "User-visible string literals must use _(), ngettext(), or "
            "pgettext():\n{}".format("\n".join(violations)),
        )

    def test_a_raw_ui_string_is_rejected(self):
        source = """
message = "Could not save"
wx.MessageBox(message, _("Save error"))
"""

        self.assertEqual(
            find_unmarked_ui_strings(source),
            [(2, "Could not save")],
        )

    def test_all_supported_markers_are_accepted(self):
        source = """
menu.Append(1, _("Open"))
control.SetLabel(ngettext("item", "items", count))
wx.StaticText(parent, label=pgettext("status", "Ready"))
"""

        self.assertEqual(find_unmarked_ui_strings(source), [])


if __name__ == "__main__":
    unittest.main()
