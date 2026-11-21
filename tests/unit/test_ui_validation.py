"""
Task II tests — Additional Inputs dialog: validation & state management.

Covers
------
* ``find_empty_custom_fields`` / ``empty_custom_field_messages`` — the pure
  pre-save validation functions (no Qt required).
* ``collect_custom_field_states`` against the *real* AdditionalInputs dialog
  built offscreen (all five tabs, real widget object names / KEY constants).
* The Save-halt behaviour of ``AdditionalInputs._save_inputs`` (modal message
  boxes are stubbed) and the ``is_modified`` / unsaved-changes state machine.
"""

from __future__ import annotations

import os
import sys

import pytest

# Make the in-repo conftest helpers importable even when pytest is invoked
# from a different rootdir.
_HERE = os.path.dirname(os.path.abspath(__file__))
_TESTS_DIR = os.path.dirname(_HERE)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from conftest import qt_modules_available  # noqa: E402

from osdagbridge.core.utils.common import (  # noqa: E402
    KEY_CB_TYPE,
    KEY_CB_WIDTH,
    KEY_RL_LOAD_MODE,
    KEY_RL_LOAD_VALUE,
)
from osdagbridge.desktop.ui.dialogs.additional_input.custom_field_validation import (  # noqa: E402
    CUSTOM_CHOICE,
    empty_custom_field_messages,
    find_empty_custom_fields,
    collect_custom_field_states,
    strip_rich_text,
)

# Real object names of a representative pattern-1 field
# (<field>.mode QComboBox + <field>.value QLineEdit).
_GUST_FACTOR_MODE = "loading.wind_load.gust_factor.mode"
_GUST_FACTOR_VALUE = "loading.wind_load.gust_factor.value"


def _solved_input_dict() -> dict:
    """A complete, solver-extended input dict (as the main window passes in)."""
    import copy

    from osdagbridge.core.bridge_types.plate_girder.defaults import (
        BASIC_INPUT_DICT,
        solve_extend_basic_input_dict,
    )
    from osdagbridge.core.utils.common import (
        KEY_CARRIAGEWAY_WIDTH,
        KEY_SKEW_ANGLE,
        KEY_SPAN,
    )

    d = copy.deepcopy(BASIC_INPUT_DICT)
    d[KEY_SPAN] = 30.0
    d[KEY_CARRIAGEWAY_WIDTH] = 7.5
    d[KEY_SKEW_ANGLE] = 0.0
    solve_extend_basic_input_dict(d)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Pure-function tests (no Qt)
# ─────────────────────────────────────────────────────────────────────────────

class TestFindEmptyCustomFieldsPure:
    def test_flags_custom_with_empty_value(self):
        states = [{"name": "Gust Factor", "mode": "Custom", "value": ""}]
        assert find_empty_custom_fields(states) == ["Gust Factor"]

    def test_ignores_non_custom_modes(self):
        states = [
            {"name": "Gust Factor", "mode": "As per IRC 6", "value": ""},
            {"name": "Camber", "mode": "Default", "value": ""},
        ]
        assert find_empty_custom_fields(states) == []

    def test_ignores_filled_custom_value(self):
        states = [{"name": "Gust Factor", "mode": "Custom", "value": " 1.3 "}]
        assert find_empty_custom_fields(states) == []

    def test_skips_disabled_or_hidden_value_fields(self):
        states = [
            {"name": "A", "mode": "Custom", "value": "", "enabled": False},
            {"name": "B", "mode": "Custom", "value": "", "visible": False},
        ]
        assert find_empty_custom_fields(states) == []

    def test_whitespace_only_value_counts_as_empty(self):
        states = [{"name": "Camber", "mode": "Custom", "value": "   \t "}]
        assert find_empty_custom_fields(states) == ["Camber"]

    def test_handles_none_and_garbage_input(self):
        assert find_empty_custom_fields(None) == []
        assert find_empty_custom_fields([]) == []
        assert find_empty_custom_fields(["not-a-dict", None, 42]) == []

    def test_multiple_offenders_keep_order(self):
        states = [
            {"name": "First", "mode": "Custom", "value": ""},
            {"name": "Second", "mode": "Custom", "value": "5"},
            {"name": "Third", "mode": "Custom", "value": ""},
        ]
        assert find_empty_custom_fields(states) == ["First", "Third"]

    def test_mode_matching_is_stripped_and_exact(self):
        # "Custom " (trailing space) matches; "customized" must not.
        states = [
            {"name": "Trailing", "mode": " Custom ", "value": ""},
            {"name": "Wrong", "mode": "customized", "value": ""},
        ]
        assert find_empty_custom_fields(states) == ["Trailing"]


class TestEmptyCustomFieldMessages:
    def test_exact_spec_message(self):
        messages = empty_custom_field_messages(["Gust Factor"])
        assert messages == [
            "Error: The custom value for 'Gust Factor' cannot be empty."
        ]

    def test_one_message_per_field(self):
        names = ["Gust Factor", "Camber"]
        messages = empty_custom_field_messages(names)
        assert len(messages) == 2
        assert all(m.startswith("Error: The custom value for '") for m in messages)
        assert messages[1].endswith("'Camber' cannot be empty.")

    def test_empty_input(self):
        assert empty_custom_field_messages([]) == []
        assert empty_custom_field_messages(None) == []


class TestStripRichText:
    def test_removes_html_markup_and_colon(self):
        assert strip_rich_text("<b>Gust</b> factor (k<sub>x</sub>):") == "Gust factor (kx)"

    def test_plain_text_passthrough(self):
        assert strip_rich_text("Camber") == "Camber"


# ─────────────────────────────────────────────────────────────────────────────
# Offscreen tests against the REAL dialog
# ─────────────────────────────────────────────────────────────────────────────

def _make_dialog():
    """Build the real AdditionalInputs dialog offscreen (or skip the test)."""
    widgets = qt_modules_available()
    if widgets is None:
        pytest.skip("PySide6 is not importable in this environment")
    from osdagbridge.desktop.ui.dialogs.additional_input.additional_inputs import (
        AdditionalInputs,
    )
    app = widgets.QApplication.instance() or widgets.QApplication([])
    assert app is not None
    return AdditionalInputs(), widgets


class TestCollectCustomFieldStatesRealDialog:
    def test_pattern1_custom_with_empty_value_is_collected(self):
        dlg, widgets = _make_dialog()
        combo = dlg.findChild(widgets.QComboBox, _GUST_FACTOR_MODE)
        value = dlg.findChild(widgets.QLineEdit, _GUST_FACTOR_VALUE)
        assert combo is not None and value is not None

        combo.setCurrentText(CUSTOM_CHOICE)
        value.clear()

        names = find_empty_custom_fields(collect_custom_field_states(dlg))
        # The display name comes from the label widget, so match by content.
        assert any("gust" in n.lower() for n in names), names

    def test_pattern1_custom_with_value_is_not_flagged(self):
        dlg, widgets = _make_dialog()
        combo = dlg.findChild(widgets.QComboBox, _GUST_FACTOR_MODE)
        value = dlg.findChild(widgets.QLineEdit, _GUST_FACTOR_VALUE)
        combo.setCurrentText(CUSTOM_CHOICE)
        value.setText("1.35")

        names = find_empty_custom_fields(collect_custom_field_states(dlg))
        assert not any("gust" in n.lower() for n in names), names

    def test_pattern2_crash_barrier_type_custom(self):
        dlg, widgets = _make_dialog()
        combo = dlg.findChild(widgets.QComboBox, KEY_CB_TYPE)
        assert combo is not None
        assert CUSTOM_CHOICE in [combo.itemText(i) for i in range(combo.count())]

        combo.setCurrentText(CUSTOM_CHOICE)
        width = dlg.findChild(widgets.QLineEdit, KEY_CB_WIDTH)
        assert width is not None
        width.clear()

        names = find_empty_custom_fields(collect_custom_field_states(dlg))
        assert any("width" in n.lower() for n in names), names

    def test_disabled_tab_fields_are_skipped(self):
        dlg, widgets = _make_dialog()
        combo = dlg.findChild(widgets.QComboBox, _GUST_FACTOR_MODE)
        value = dlg.findChild(widgets.QLineEdit, _GUST_FACTOR_VALUE)
        combo.setCurrentText(CUSTOM_CHOICE)
        value.clear()

        # Find the tab page that hosts the field and disable it.
        tabs = dlg.findChild(widgets.QTabWidget)
        assert tabs is not None
        host_page = None
        for i in range(tabs.count()):
            page = tabs.widget(i)
            if page.isAncestorOf(combo):
                host_page = i
                break
        assert host_page is not None
        tabs.setTabEnabled(host_page, False)
        try:
            names = find_empty_custom_fields(collect_custom_field_states(dlg))
            assert not any("gust" in n.lower() for n in names), names
        finally:
            tabs.setTabEnabled(host_page, True)


class TestSaveValidationAndState:
    """Save-halt + unsaved-changes state machine on the real dialog."""

    def test_validate_before_save_reports_empty_custom(self):
        dlg, widgets = _make_dialog()
        combo = dlg.findChild(widgets.QComboBox, _GUST_FACTOR_MODE)
        value = dlg.findChild(widgets.QLineEdit, _GUST_FACTOR_VALUE)
        combo.setCurrentText(CUSTOM_CHOICE)
        value.clear()

        errors = dlg._validate_before_save()
        assert any("cannot be empty" in e for e in errors), errors
        assert any("gust" in e.lower() for e in errors), errors

    def test_validate_before_save_clean_when_filled(self):
        dlg, widgets = _make_dialog()
        assert dlg._validate_before_save() == []

    def test_save_inputs_halts_and_commits_nothing(self, monkeypatch):
        dlg, widgets = _make_dialog()

        shown: list[dict] = []

        class _StubBox:
            def __init__(self, title="Message", text="", informativeText="",
                         buttons=("OK",), dialogType=None):
                shown.append({"title": title, "text": text})

            def exec(self):
                return "OK"

        import osdagbridge.desktop.ui.dialogs.additional_input.additional_inputs as ai_mod
        monkeypatch.setattr(ai_mod, "CustomMessageBox", _StubBox)

        combo = dlg.findChild(widgets.QComboBox, _GUST_FACTOR_MODE)
        value = dlg.findChild(widgets.QLineEdit, _GUST_FACTOR_VALUE)
        combo.setCurrentText(CUSTOM_CHOICE)
        value.clear()

        marker = ("marker.should.not.persist",)
        dlg.working_input_dict[marker[0]] = "x"

        dlg._save_inputs()

        # Save halted: error dialog shown, nothing committed, still modified.
        assert shown and "cannot be empty" in shown[0]["text"], shown
        assert marker[0] not in dlg.default_input_dict
        # The flag is only cleared by a *successful* save — a halted save
        # must leave the dialog marked as having unsaved changes.
        assert dlg.is_modified is True

    def test_is_modified_flag_lifecycle(self):
        dlg, widgets = _make_dialog()
        assert dlg.is_modified is False

        # Simulate a user edit through the soft-validation slot.
        dlg._on_field_editing("2.5", KEY_RL_LOAD_VALUE)
        assert dlg.is_modified is True

        # set_input_dictionary re-syncs from the main window → resets the flag.
        dlg.set_input_dictionary(_solved_input_dict())
        assert dlg.is_modified is False

    def test_confirm_discard_unsaved_changes(self, monkeypatch):
        dlg, widgets = _make_dialog()

        responses = iter(["Discard", "Cancel"])

        class _StubBox:
            def __init__(self, *args, **kwargs):
                pass

            def exec(self):
                return next(responses)

        import osdagbridge.desktop.ui.dialogs.additional_input.additional_inputs as ai_mod
        monkeypatch.setattr(ai_mod, "CustomMessageBox", _StubBox)

        # No edits → closes without any prompt.
        assert dlg._confirm_discard_unsaved_changes() is True

        dlg.is_modified = True
        assert dlg._confirm_discard_unsaved_changes() is True   # Discard
        assert dlg.is_modified is False

        dlg.is_modified = True
        assert dlg._confirm_discard_unsaved_changes() is False  # Cancel
