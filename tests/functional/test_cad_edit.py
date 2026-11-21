"""
Task I functional tests — Interactive 2D CAD parameter editing.

Covers
------
* The pure registry / validation helpers of
  ``osdagbridge.desktop.ui.docks.cad_param_editor`` (no Qt required):
  editable whitelist, locked-parameter rejection, range validation reusing
  the central ``BridgeInputValidator`` rules, and unit conversion.
* The offscreen behaviour of the real CAD widgets: the painted dimension
  labels register hit zones, double-click opens the temporary QLineEdit
  pre-filled with the current value, Enter/focus-out commits
  ``parameter_edit_requested(key, text)`` while Escape cancels, and locked
  (derived) labels only emit ``locked_parameter_clicked``.

The template page itself (``CustomWindow``) cannot be imported here — it
pulls in the OCC-dependent ``cad_3d`` module — so the owner-side slot
(``CustomWindow._on_cad_parameter_edit``) is validated by static review
plus these widget/pure-function tests.
"""

from __future__ import annotations

import copy
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
    CARRIAGEWAY_WIDTH_MAX_LIMIT,
    KEY_CARRIAGEWAY_WIDTH,
    KEY_INCLUDE_MEDIAN,
    KEY_MP_CB_SPACING,
    KEY_SPAN,
    KEY_SPAN as _KEY_SPAN,  # re-exported for parametrization ids
    KEY_TS_DECK_OVERHANG,
    KEY_TS_DECK_THICKNESS,
    KEY_TS_GIRDER_SPACING,
    KEY_TS_NO_OF_GIRDERS,
    KEY_TS_OVERALL_WIDTH,
    SPAN_MAX,
    SPAN_MIN,
)
from osdagbridge.desktop.ui.docks.cad_param_editor import (  # noqa: E402
    CAD_EDITABLE_PARAMS,
    CAD_LOCKED_PARAMS,
    CAD_PARAM_REGISTRY,
    cad_param_label,
    cad_param_to_input_value,
    format_cad_param_value,
    is_cad_param_editable,
    is_cad_param_locked,
    validate_cad_param_value,
)

assert _KEY_SPAN == KEY_SPAN  # sanity for the alias above


# ─────────────────────────────────────────────────────────────────────────────
# Pure registry tests — editable whitelist / locked parameters
# ─────────────────────────────────────────────────────────────────────────────

class TestEditableWhitelist:
    def test_editable_set_is_exactly_the_spec_four(self):
        assert set(CAD_EDITABLE_PARAMS) == {
            KEY_SPAN,
            KEY_CARRIAGEWAY_WIDTH,
            KEY_TS_GIRDER_SPACING,
            KEY_TS_DECK_THICKNESS,
        }

    def test_locked_set_is_exactly_the_spec_three(self):
        assert set(CAD_LOCKED_PARAMS) == {
            KEY_TS_DECK_OVERHANG,
            KEY_TS_OVERALL_WIDTH,
            KEY_MP_CB_SPACING,
        }

    def test_registry_covers_all_seven_cad_dimensions(self):
        assert len(CAD_PARAM_REGISTRY) == 7
        assert set(CAD_PARAM_REGISTRY) == set(CAD_EDITABLE_PARAMS) | set(CAD_LOCKED_PARAMS)

    def test_editable_and_locked_are_disjoint(self):
        assert not (set(CAD_EDITABLE_PARAMS) & set(CAD_LOCKED_PARAMS))

    def test_is_cad_param_editable(self):
        for key in CAD_EDITABLE_PARAMS:
            assert is_cad_param_editable(key), key
        for key in CAD_LOCKED_PARAMS:
            assert not is_cad_param_editable(key), key

    def test_is_cad_param_locked(self):
        for key in CAD_LOCKED_PARAMS:
            assert is_cad_param_locked(key), key
        for key in CAD_EDITABLE_PARAMS:
            assert not is_cad_param_locked(key), key

    def test_unknown_keys_are_never_editable(self):
        assert not is_cad_param_editable("not.a.real.key")
        assert not is_cad_param_locked("not.a.real.key")

    def test_labels_are_human_readable(self):
        expected = {
            KEY_SPAN: "Span Length",
            KEY_CARRIAGEWAY_WIDTH: "Carriageway Width",
            KEY_TS_GIRDER_SPACING: "Girder Spacing",
            KEY_TS_DECK_THICKNESS: "Deck Thickness",
            KEY_TS_DECK_OVERHANG: "Overhang",
            KEY_TS_OVERALL_WIDTH: "Overall Bridge Width",
            KEY_MP_CB_SPACING: "Bracing Spacing",
        }
        for key, label in expected.items():
            assert cad_param_label(key) == label, key
        assert cad_param_label("not.a.real.key") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Pure validation tests — range rules reused from the central validator
# ─────────────────────────────────────────────────────────────────────────────

def _base_inputs() -> dict:
    """A solved basic input dict (as the main window passes to the CAD)."""
    from osdagbridge.core.bridge_types.plate_girder.defaults import (
        BASIC_INPUT_DICT,
        solve_extend_basic_input_dict,
    )

    d = copy.deepcopy(BASIC_INPUT_DICT)
    d[KEY_SPAN] = 30.0
    d[KEY_CARRIAGEWAY_WIDTH] = 7.5
    solve_extend_basic_input_dict(d)
    return d


class TestRangeValidation:
    @pytest.mark.parametrize("value", [20.0, 30.0, 45.0])
    def test_span_in_range_accepted(self, value):
        ok, v, msg = validate_cad_param_value(KEY_SPAN, str(value))
        assert ok, msg
        assert v == value

    @pytest.mark.parametrize("value", [SPAN_MIN - 0.5, SPAN_MAX + 1.0, 1e6])
    def test_span_out_of_range_rejected(self, value):
        ok, v, msg = validate_cad_param_value(KEY_SPAN, str(value))
        assert not ok
        assert v is None
        assert "Span" in msg

    @pytest.mark.parametrize("value", [5.5, 7.5, 10.0])
    def test_carriageway_in_range_accepted(self, value):
        ok, v, msg = validate_cad_param_value(KEY_CARRIAGEWAY_WIDTH, str(value))
        assert ok, msg
        assert v == value

    @pytest.mark.parametrize("value", [2.0, CARRIAGEWAY_WIDTH_MAX_LIMIT + 1.0])
    def test_carriageway_out_of_range_rejected(self, value):
        ok, _v, msg = validate_cad_param_value(KEY_CARRIAGEWAY_WIDTH, str(value))
        assert not ok
        assert msg

    @pytest.mark.parametrize("value", [120, 200, 350])
    def test_deck_thickness_in_range_accepted(self, value):
        ok, v, msg = validate_cad_param_value(KEY_TS_DECK_THICKNESS, str(value))
        assert ok, msg
        assert v == value

    @pytest.mark.parametrize("value", [50, 600])
    def test_deck_thickness_out_of_range_rejected(self, value):
        ok, _v, msg = validate_cad_param_value(KEY_TS_DECK_THICKNESS, str(value))
        assert not ok
        assert msg

    def test_girder_spacing_accepted(self):
        ok, v, msg = validate_cad_param_value(KEY_TS_GIRDER_SPACING, "2.1")
        assert ok, msg
        assert v == 2.1

    def test_girder_spacing_below_minimum_rejected(self):
        ok, _v, msg = validate_cad_param_value(KEY_TS_GIRDER_SPACING, "0.2")
        assert not ok
        assert msg

    def test_girder_spacing_limited_by_overall_width(self):
        # The cross-field rule: spacing ≤ overall_width / 2 when known.
        inputs = _base_inputs()
        overall = 8.4
        inputs[KEY_TS_OVERALL_WIDTH] = overall
        ok, _v, msg = validate_cad_param_value(
            KEY_TS_GIRDER_SPACING, str(overall / 2 + 1.0), inputs
        )
        assert not ok
        assert msg

    def test_non_numeric_rejected(self):
        for key in CAD_EDITABLE_PARAMS:
            ok, v, msg = validate_cad_param_value(key, "twelve")
            assert not ok, key
            assert v is None
            assert "numeric" in msg.lower()

    @pytest.mark.parametrize("bad", ["", "   ", "nan", "inf"])
    def test_empty_and_junk_rejected(self, bad):
        ok, _v, _msg = validate_cad_param_value(KEY_SPAN, bad)
        assert not ok

    def test_comma_decimal_separator_accepted(self):
        ok, v, msg = validate_cad_param_value(KEY_SPAN, "25,5")
        assert ok, msg
        assert v == 25.5


class TestLockedRejection:
    @pytest.mark.parametrize("key", list(CAD_LOCKED_PARAMS))
    def test_locked_parameters_rejected_with_derived_message(self, key):
        ok, v, msg = validate_cad_param_value(key, "3.5")
        assert not ok
        assert v is None
        assert "derived" in msg.lower()

    @pytest.mark.parametrize("key", list(CAD_LOCKED_PARAMS))
    def test_locked_parameters_rejected_even_with_valid_looking_text(self, key):
        ok, _v, _msg = validate_cad_param_value(key, "30")
        assert not ok

    def test_unknown_key_rejected(self):
        ok, _v, msg = validate_cad_param_value("not.a.real.key", "30")
        assert not ok
        assert "not a recognised CAD parameter" in msg


class TestCrossFieldRules:
    def test_carriageway_with_median_uses_median_minimum(self):
        from osdagbridge.core.utils.common import CARRIAGEWAY_WIDTH_MIN_WITH_MEDIAN

        inputs = _base_inputs()
        inputs[KEY_INCLUDE_MEDIAN] = "Yes"
        # A width below the with-median minimum must be rejected.
        ok, _v, msg = validate_cad_param_value(
            KEY_CARRIAGEWAY_WIDTH, str(CARRIAGEWAY_WIDTH_MIN_WITH_MEDIAN - 2.0), inputs
        )
        assert not ok
        assert msg

    def test_validation_reuses_shared_validator_rules(self):
        """The CAD editor must accept exactly what the input dock accepts."""
        from osdagbridge.core.bridge_types.plate_girder.validator import BridgeInputValidator

        validator = BridgeInputValidator()
        ok, v, msg = validate_cad_param_value(
            KEY_SPAN, "33", _base_inputs(), validator
        )
        assert ok, msg
        assert v == 33.0


# ─────────────────────────────────────────────────────────────────────────────
# Pure value helpers — CAD (mm) ↔ input-dict (m / mm) conversion
# ─────────────────────────────────────────────────────────────────────────────

class TestValueHelpers:
    def test_cad_param_to_input_value_converts_mm_to_metres(self):
        assert cad_param_to_input_value(
            KEY_SPAN, {"span_length": 30000}
        ) == pytest.approx(30.0)
        assert cad_param_to_input_value(
            KEY_CARRIAGEWAY_WIDTH, {"carriageway_width": 7500}
        ) == pytest.approx(7.5)
        assert cad_param_to_input_value(
            KEY_TS_GIRDER_SPACING, {"girder_spacing": 2100}
        ) == pytest.approx(2.1)

    def test_deck_thickness_stays_in_mm(self):
        assert cad_param_to_input_value(
            KEY_TS_DECK_THICKNESS, {"deck_thickness": 200}
        ) == pytest.approx(200.0)

    def test_missing_or_invalid_cad_state_returns_none(self):
        assert cad_param_to_input_value(KEY_SPAN, {}) is None
        assert cad_param_to_input_value(KEY_SPAN, {"span_length": None}) is None
        assert cad_param_to_input_value(KEY_SPAN, {"span_length": "abc"}) is None
        # Overall width has no direct CAD parameter
        assert cad_param_to_input_value(KEY_TS_OVERALL_WIDTH, {"span_length": 1}) is None
        assert cad_param_to_input_value("not.a.real.key", {}) is None

    def test_format_cad_param_value_decimals(self):
        assert format_cad_param_value(KEY_SPAN, 30.0) == "30.0"
        assert format_cad_param_value(KEY_CARRIAGEWAY_WIDTH, 7.5) == "7.50"
        assert format_cad_param_value(KEY_TS_GIRDER_SPACING, 2.1) == "2.10"
        assert format_cad_param_value(KEY_TS_DECK_THICKNESS, 200) == "200"
        assert format_cad_param_value(KEY_TS_DECK_THICKNESS, 212.568) == "213"

    def test_format_rejects_garbage(self):
        assert format_cad_param_value(KEY_SPAN, "abc") == ""
        assert format_cad_param_value("not.a.real.key", 1.0) == ""


# ─────────────────────────────────────────────────────────────────────────────
# Offscreen widget tests — double-click editing on the real CAD canvas
# ─────────────────────────────────────────────────────────────────────────────

def _qt():
    widgets = qt_modules_available()
    if widgets is None:
        pytest.skip("PySide6 is not importable in this environment")
    app = widgets.QApplication.instance() or widgets.QApplication([])
    assert app is not None
    return widgets


def _dbl_click(widget, rect):
    """Synthesize a left-button double-click at the centre of *rect*."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    c = rect.center()
    return QMouseEvent(
        QEvent.MouseButtonDblClick, QPointF(c), QPointF(c),
        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
    )


def _rendered_zones(widget) -> dict:
    """Force an offscreen render and return {key: first hit rect}."""
    widget.show()
    _qt()  # ensure an app exists (also used by the caller)
    widget.grab()
    zones: dict = {}
    for rect, key in getattr(widget, "_dim_label_zones", []):
        zones.setdefault(key, rect)
    return zones


class TestTopViewEditing:
    def _widget(self):
        _qt()
        from osdagbridge.desktop.ui.docks.cad_top_view import TopViewCADWidget

        w = TopViewCADWidget()
        w.resize(1400, 900)
        w._set_cad_editing_enabled(True)
        return w

    def test_dimension_labels_register_hit_zones(self):
        w = self._widget()
        zones = _rendered_zones(w)
        assert KEY_SPAN in zones, zones.keys()
        assert KEY_MP_CB_SPACING in zones, zones.keys()
        assert KEY_TS_GIRDER_SPACING in zones, zones.keys()

    def test_double_click_opens_prefilled_editor(self):
        w = self._widget()
        zones = _rendered_zones(w)

        emitted: list = []
        w.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_SPAN]))

        editor = w._active_editor
        assert editor is not None
        # Pre-filled with the current span in input-dict units (metres).
        assert editor.text() == format_cad_param_value(
            KEY_SPAN, cad_param_to_input_value(KEY_SPAN, w.params)
        )
        # No signal until the edit is committed.
        assert emitted == []

    def test_commit_emits_parameter_edit_requested(self):
        w = self._widget()
        zones = _rendered_zones(w)

        emitted: list = []
        w.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_SPAN]))
        editor = w._active_editor
        editor.setText("32.5")
        editor._commit()          # same path as Enter / focus-out

        assert emitted == [(KEY_SPAN, "32.5")]
        assert w._active_editor is None

    def test_unchanged_text_does_not_emit(self):
        w = self._widget()
        zones = _rendered_zones(w)

        emitted: list = []
        w.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_SPAN]))
        editor = w._active_editor
        editor._commit()          # text unchanged

        assert emitted == []
        assert w._active_editor is None

    def test_empty_text_does_not_emit(self):
        w = self._widget()
        zones = _rendered_zones(w)

        emitted: list = []
        w.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_SPAN]))
        editor = w._active_editor
        editor.setText("")
        editor._commit()

        assert emitted == []

    def test_escape_cancels_without_emitting(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QKeyEvent
        from PySide6.QtCore import QEvent

        w = self._widget()
        zones = _rendered_zones(w)

        emitted: list = []
        w.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_SPAN]))
        editor = w._active_editor
        editor.setText("40")
        editor.keyPressEvent(QKeyEvent(
            QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier
        ))

        assert emitted == []
        assert w._active_editor is None

    def test_locked_label_emits_locked_signal_only(self):
        w = self._widget()
        zones = _rendered_zones(w)

        edits: list = []
        locks: list = []
        w.parameter_edit_requested.connect(lambda k, t: edits.append((k, t)))
        w.locked_parameter_clicked.connect(lambda k: locks.append(k))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_MP_CB_SPACING]))

        assert locks == [KEY_MP_CB_SPACING]
        assert edits == []
        assert w._active_editor is None

    def test_double_click_off_label_is_inert(self):
        w = self._widget()
        _rendered_zones(w)

        emitted: list = []
        w.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QMouseEvent
        from PySide6.QtCore import QEvent, Qt

        w.mouseDoubleClickEvent(QMouseEvent(
            QEvent.MouseButtonDblClick, QPointF(5, 5), QPointF(5, 5),
            Qt.LeftButton, Qt.LeftButton, Qt.NoModifier,
        ))
        assert emitted == []
        assert w._active_editor is None

    def test_editing_disabled_leaves_widget_read_only(self):
        _qt()
        from osdagbridge.desktop.ui.docks.cad_top_view import TopViewCADWidget

        w = TopViewCADWidget()
        w.resize(1400, 900)
        assert w.cad_editing_enabled is False   # default: read-only

        zones = _rendered_zones(w)
        assert zones, "labels are painted even when editing is disabled"

        edits: list = []
        locks: list = []
        w.parameter_edit_requested.connect(lambda k, t: edits.append((k, t)))
        w.locked_parameter_clicked.connect(lambda k: locks.append(k))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_SPAN]))
        assert edits == [] and locks == []
        assert w._active_editor is None


class TestCrossSectionEditing:
    def _widget(self):
        _qt()
        from osdagbridge.desktop.ui.docks.cad_cross_section import CrossSectionCADWidget

        w = CrossSectionCADWidget()
        w.resize(1400, 900)
        w._set_cad_editing_enabled(True)
        return w

    def test_dimension_labels_register_hit_zones(self):
        w = self._widget()
        zones = _rendered_zones(w)
        assert KEY_CARRIAGEWAY_WIDTH in zones, zones.keys()
        assert KEY_TS_GIRDER_SPACING in zones, zones.keys()
        assert KEY_TS_DECK_THICKNESS in zones, zones.keys()
        assert KEY_TS_OVERALL_WIDTH in zones, zones.keys()
        assert KEY_TS_DECK_OVERHANG in zones, zones.keys()

    def test_carriageway_double_click_edit_round_trip(self):
        w = self._widget()
        zones = _rendered_zones(w)

        emitted: list = []
        w.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_CARRIAGEWAY_WIDTH]))
        editor = w._active_editor
        assert editor is not None
        editor.setText("9.0")
        editor._commit()

        assert emitted == [(KEY_CARRIAGEWAY_WIDTH, "9.0")]

    def test_locked_overall_width_not_editable(self):
        w = self._widget()
        zones = _rendered_zones(w)

        locks: list = []
        edits: list = []
        w.locked_parameter_clicked.connect(lambda k: locks.append(k))
        w.parameter_edit_requested.connect(lambda k, t: edits.append((k, t)))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_TS_OVERALL_WIDTH]))
        assert locks == [KEY_TS_OVERALL_WIDTH]
        assert edits == [] and w._active_editor is None

    def test_locked_overhang_not_editable(self):
        w = self._widget()
        zones = _rendered_zones(w)

        locks: list = []
        w.locked_parameter_clicked.connect(lambda k: locks.append(k))

        w.mouseDoubleClickEvent(_dbl_click(w, zones[KEY_TS_DECK_OVERHANG]))
        assert locks == [KEY_TS_DECK_OVERHANG]
        assert w._active_editor is None


class TestDualViewAggregation:
    """The template page listens on BridgeDualCADWidget — child signals re-emit."""

    def _dual(self):
        _qt()
        from osdagbridge.desktop.ui.docks.cad_dual_view import BridgeDualCADWidget

        dual = BridgeDualCADWidget()
        dual.resize(1400, 900)
        return dual

    def test_children_have_editing_enabled(self):
        dual = self._dual()
        assert dual.cross_section_widget.cad_editing_enabled is True
        assert dual.top_view_widget.cad_editing_enabled is True

    def test_child_edit_reaches_dual_signal(self):
        dual = self._dual()
        top = dual.top_view_widget

        zones = _rendered_zones(top)
        assert KEY_SPAN in zones

        emitted: list = []
        dual.parameter_edit_requested.connect(lambda k, t: emitted.append((k, t)))

        top.mouseDoubleClickEvent(_dbl_click(top, zones[KEY_SPAN]))
        editor = top._active_editor
        assert editor is not None
        editor.setText("28")
        editor._commit()

        assert emitted == [(KEY_SPAN, "28")]

    def test_child_locked_click_reaches_dual_signal(self):
        dual = self._dual()
        top = dual.top_view_widget

        zones = _rendered_zones(top)
        assert KEY_MP_CB_SPACING in zones

        locks: list = []
        dual.locked_parameter_clicked.connect(lambda k: locks.append(k))

        top.mouseDoubleClickEvent(_dbl_click(top, zones[KEY_MP_CB_SPACING]))
        assert locks == [KEY_MP_CB_SPACING]

    def test_update_from_osdag_inputs_drives_the_cad_state(self):
        """The redraw trigger used by the template page after a committed edit."""
        dual = self._dual()
        inputs = _base_inputs()
        inputs[KEY_TS_GIRDER_SPACING] = 2.3
        inputs[KEY_TS_NO_OF_GIRDERS] = 4

        dual.update_from_osdag_inputs(inputs)

        assert dual.top_view_widget.params["span_length"] == pytest.approx(
            inputs[KEY_SPAN] * 1000
        )
        assert dual.cross_section_widget.params["girder_spacing"] == pytest.approx(2300)
