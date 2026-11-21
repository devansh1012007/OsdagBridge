"""Rigorous input & customization validation tests (fast — no design run).

Covers BridgeInputValidator.validate_basic_inputs / validate_material_inputs
(the same rules the InputDock and Material Properties dialog enforce live)
plus the load-time OSI validator, plus the design-time gate
PlateGirderBridge._validate_inputs.

Where the *actual* behaviour deviates from the documented/GUI-clamped
behaviour, the test pins the current behaviour and references the issue
draft under download/task_d/issues/ (see module-level constants below).
"""

from __future__ import annotations

import pytest

from osdagbridge.core.bridge_types.plate_girder.validator import BridgeInputValidator
from osdagbridge.core.utils.common import (
    KEY_SPAN, KEY_CARRIAGEWAY_WIDTH, KEY_SKEW_ANGLE, KEY_INCLUDE_MEDIAN,
    KEY_TS_NO_OF_GIRDERS,
    KEY_MATERIAL_GIRDER_FY, KEY_MATERIAL_GIRDER_FU, KEY_MATERIAL_GIRDER_E,
    KEY_MATERIAL_GIRDER_G, KEY_MATERIAL_GIRDER_POISSON,
    KEY_MATERIAL_GIRDER_DENSITY, KEY_MATERIAL_GIRDER_THERMAL,
    KEY_MATERIAL_CROSS_BRACING_FY, KEY_MATERIAL_END_DIAPHRAGM_FY,
    KEY_MATERIAL_DECK_FCK, KEY_MATERIAL_DECK_FCTM, KEY_MATERIAL_DECK_ECM,
    KEY_MATERIAL_DECK_DENSITY, KEY_MATERIAL_DECK_THERMAL,
    SPAN_MIN, SPAN_MAX, CARRIAGEWAY_WIDTH_MIN, CARRIAGEWAY_WIDTH_MAX_LIMIT,
    SKEW_ANGLE_MIN, SKEW_ANGLE_MAX,
)


@pytest.fixture
def validator():
    return BridgeInputValidator()


# ────────────────────────── Span (20–45 m software scope) ───────────────────

class TestSpanValidation:
    def test_span_19_is_clamped_to_min(self, validator):
        """span = 19 m (1 m below SPAN_MIN) must be rejected + clamped to 20 m."""
        res = validator.validate_basic_inputs(
            KEY_SPAN, {KEY_SPAN: 19.0})
        assert res is not None
        corrected, msg = res
        assert corrected == SPAN_MIN == 20.0
        assert "20" in msg

    def test_span_46_is_clamped_to_max(self, validator):
        """span = 46 m (1 m above SPAN_MAX) must be rejected + clamped to 45 m."""
        res = validator.validate_basic_inputs(
            KEY_SPAN, {KEY_SPAN: 46.0})
        assert res is not None
        corrected, msg = res
        assert corrected == SPAN_MAX == 45.0
        assert "45" in msg

    @pytest.mark.parametrize("span", [20.0, 30.0, 45.0])
    def test_span_in_range_is_valid(self, validator, span):
        """Boundary and mid-range spans pass without correction."""
        assert validator.validate_basic_inputs(KEY_SPAN, {KEY_SPAN: span}) is None

    def test_span_non_numeric_string_clamped_to_min(self, validator):
        """'abc' → non-numeric message + clamp to SPAN_MIN (GUI autofill)."""
        res = validator.validate_basic_inputs(KEY_SPAN, {KEY_SPAN: "abc"})
        assert res is not None
        corrected, msg = res
        assert corrected == SPAN_MIN
        assert "numeric" in msg

    def test_span_none_clamped_to_min(self, validator):
        """Cleared field (None) → clamp to SPAN_MIN."""
        res = validator.validate_basic_inputs(KEY_SPAN, {KEY_SPAN: None})
        assert res is not None and res[0] == SPAN_MIN

    def test_span_numeric_string_is_coerced(self, validator):
        """'30.5' typed in the QLineEdit is accepted as a valid span."""
        assert validator.validate_basic_inputs(
            KEY_SPAN, {KEY_SPAN: "30.5"}) is None


# ───────────────────── Carriageway width (IRC 5 Cl. 104.3.1) ────────────────

class TestCarriagewayValidation:
    def test_carriageway_zero_clamped_to_single_lane_min(self, validator):
        """cw = 0 must be clamped to 4.25 m (1-lane minimum)."""
        res = validator.validate_basic_inputs(
            KEY_CARRIAGEWAY_WIDTH, {KEY_CARRIAGEWAY_WIDTH: 0.0,
                                    KEY_INCLUDE_MEDIAN: "No"})
        assert res is not None
        corrected, msg = res
        assert corrected == CARRIAGEWAY_WIDTH_MIN == 4.25
        assert "104.3.1" in msg

    def test_carriageway_negative_clamped(self, validator):
        """Negative widths are clamped the same way as zero."""
        res = validator.validate_basic_inputs(
            KEY_CARRIAGEWAY_WIDTH, {KEY_CARRIAGEWAY_WIDTH: -5.0,
                                    KEY_INCLUDE_MEDIAN: "No"})
        assert res is not None and res[0] == CARRIAGEWAY_WIDTH_MIN

    def test_carriageway_with_median_requires_7_5(self, validator):
        """With a median, each carriageway must be ≥ 7.5 m (2 lanes)."""
        res = validator.validate_basic_inputs(
            KEY_CARRIAGEWAY_WIDTH, {KEY_CARRIAGEWAY_WIDTH: 5.0,
                                    KEY_INCLUDE_MEDIAN: "Yes"})
        assert res is not None and res[0] == 7.5

    def test_carriageway_above_software_limit_clamped(self, validator):
        """cw > 23.6 m hits the software cap."""
        res = validator.validate_basic_inputs(
            KEY_CARRIAGEWAY_WIDTH, {KEY_CARRIAGEWAY_WIDTH: 30.0,
                                    KEY_INCLUDE_MEDIAN: "No"})
        assert res is not None and res[0] == CARRIAGEWAY_WIDTH_MAX_LIMIT == 23.6

    def test_carriageway_valid_value_passes(self, validator):
        """cw = 7.5 m without median is inside IRC 5 limits — no correction."""
        assert validator.validate_basic_inputs(
            KEY_CARRIAGEWAY_WIDTH, {KEY_CARRIAGEWAY_WIDTH: 7.5,
                                    KEY_INCLUDE_MEDIAN: "No"}) is None


# ───────────────────────────── Skew angle (±15°) ────────────────────────────

class TestSkewValidation:
    @pytest.mark.parametrize("skew,expected", [(-20.0, -15.0), (20.0, 15.0)])
    def test_skew_out_of_range_clamped(self, validator, skew, expected):
        """Skew beyond ±15° (IRC 24 Cl. 504.8) is clamped to the nearer bound."""
        res = validator.validate_basic_inputs(KEY_SKEW_ANGLE, {KEY_SKEW_ANGLE: skew})
        assert res is not None and res[0] == expected

    @pytest.mark.parametrize("skew", [-15.0, 0.0, 15.0])
    def test_skew_in_range_valid(self, validator, skew):
        """Both skew bounds and 0° pass without correction."""
        assert validator.validate_basic_inputs(
            KEY_SKEW_ANGLE, {KEY_SKEW_ANGLE: skew}) is None

    def test_skew_non_numeric_clamped(self, validator):
        """'x' typed into the skew field → numeric message + clamp to -15°."""
        res = validator.validate_basic_inputs(KEY_SKEW_ANGLE, {KEY_SKEW_ANGLE: "x"})
        assert res is not None and res[0] == SKEW_ANGLE_MIN


# ─────────────────────── Custom material property ranges ────────────────────

class TestMaterialValidation:
    """The Material Properties dialog (steel + deck tabs) validates each field
    against these ranges via validate_material_inputs()."""

    def test_girder_fy_below_min_clamped(self, validator):
        """Custom fy = 50 MPa (below the 100 MPa floor) is clamped to 100."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_GIRDER_FY, {KEY_MATERIAL_GIRDER_FY: 50.0})
        assert res is not None and res[0] == 100.0

    def test_girder_fy_above_max_clamped(self, validator):
        """Custom fy = 2000 MPa (above the 1200 MPa cap) is clamped to 1200."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_GIRDER_FY, {KEY_MATERIAL_GIRDER_FY: 2000.0})
        assert res is not None and res[0] == 1200.0

    def test_girder_fu_bounds(self, validator):
        """Custom fu = 5 MPa is clamped to the 100 MPa lower bound."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_GIRDER_FU, {KEY_MATERIAL_GIRDER_FU: 5.0})
        assert res is not None and res[0] == 100.0

    def test_girder_e_bounds_gpa(self, validator):
        """Custom E = 500 GPa (cap 300 GPa) is clamped."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_GIRDER_E, {KEY_MATERIAL_GIRDER_E: 500.0})
        assert res is not None and res[0] == 300.0

    def test_girder_g_bounds_gpa(self, validator):
        """Custom G = 10 GPa (floor 30 GPa) is clamped."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_GIRDER_G, {KEY_MATERIAL_GIRDER_G: 10.0})
        assert res is not None and res[0] == 30.0

    def test_girder_poisson_bounds(self, validator):
        """ν = 0.9 (physical max 0.5) is clamped to 0.5."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_GIRDER_POISSON, {KEY_MATERIAL_GIRDER_POISSON: 0.9})
        assert res is not None and res[0] == 0.5

    def test_girder_density_bounds(self, validator):
        """Steel density 10 kN/m³ (floor 50) is clamped."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_GIRDER_DENSITY, {KEY_MATERIAL_GIRDER_DENSITY: 10.0})
        assert res is not None and res[0] == 50.0

    def test_deck_fck_bounds(self, validator):
        """Deck fck = 5 MPa (floor 10 MPa) is clamped."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_DECK_FCK, {KEY_MATERIAL_DECK_FCK: 5.0})
        assert res is not None and res[0] == 10.0

    def test_deck_fctm_ecm_bounds(self, validator):
        """Deck fctm = 0.1 MPa (floor 0.5) and Ecm = 100 GPa (cap 50) clamp."""
        res = validator.validate_material_inputs(
            KEY_MATERIAL_DECK_FCTM, {KEY_MATERIAL_DECK_FCTM: 0.1})
        assert res is not None and res[0] == 0.5
        res = validator.validate_material_inputs(
            KEY_MATERIAL_DECK_ECM, {KEY_MATERIAL_DECK_ECM: 100.0})
        assert res is not None and res[0] == 50.0

    def test_valid_custom_material_passes(self, validator):
        """A realistic custom steel (fy=250, fu=410, e=205 …) passes untouched."""
        valid = {KEY_MATERIAL_GIRDER_FY: 250.0, KEY_MATERIAL_GIRDER_FU: 410.0,
                 KEY_MATERIAL_GIRDER_E: 205.0, KEY_MATERIAL_GIRDER_G: 79.3,
                 KEY_MATERIAL_GIRDER_POISSON: 0.3,
                 KEY_MATERIAL_GIRDER_DENSITY: 77.0}
        for key, val in valid.items():
            assert validator.validate_material_inputs(key, {key: val}) is None

    def test_cross_bracing_and_end_diaphragm_keys_are_not_validated(self, validator):
        """DOCUMENTED GAP (see issues/04-material-validation-gap.md):

        validate_material_inputs() only knows the girder/deck key constants.
        The material.cross_bracing.* / material.end_diaphragm.* keys that the
        export path (and any headless/API/OSI consumer) writes are accepted
        with ANY value — including garbage — and never range-checked.
        Current behaviour: None (no correction) for out-of-range values.
        """
        for key in (KEY_MATERIAL_CROSS_BRACING_FY, KEY_MATERIAL_END_DIAPHRAGM_FY):
            res = validator.validate_material_inputs(key, {key: 99_999.0})
            assert res is None, (
                f"{key} unexpectedly validated; update this test and the "
                "related issue draft if validation was added")


# ───────────────────── Design-time gate (defense in depth) ──────────────────

class TestDesignTimeValidation:
    """PlateGirderBridge._validate_inputs() is the ONLY check the headless /
    programmatic path enforces before the full pipeline runs."""

    def test_design_gate_does_not_enforce_span_scope(self, make_input_dict):
        """ISSUE (see issues/03-design-time-validation-gaps.md): spans of
        19 m / 46 m / 0.5 m / 100 m all pass _validate_inputs() — the 20–45 m
        software scope is only enforced by the GUI field validator and the
        OSI load-time validator, never by the pipeline itself."""
        from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
            PlateGirderBridge)

        for span in (19.0, 46.0, 0.5, 100.0):
            d = make_input_dict(span=span)
            bridge = PlateGirderBridge()
            bridge.set_input(d)
            bridge._validate_inputs()  # must NOT raise today (documents gap)
            assert float(bridge.input_dict[KEY_SPAN]) == span

    def test_design_gate_rejects_missing_layout_keys(self, make_input_dict):
        """Missing girder count / spacing are hard errors at design time."""
        from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
            PlateGirderBridge)

        d = make_input_dict()
        del d[KEY_TS_NO_OF_GIRDERS]
        bridge = PlateGirderBridge()
        bridge.set_input(d)
        with pytest.raises(ValueError, match="Missing required input"):
            bridge._validate_inputs()

    def test_design_gate_rejects_single_girder(self, make_input_dict):
        """A single-girder layout must be rejected before any analysis runs."""
        from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
            PlateGirderBridge)

        d = make_input_dict()
        d[KEY_TS_NO_OF_GIRDERS] = 1
        bridge = PlateGirderBridge()
        bridge.set_input(d)
        with pytest.raises(ValueError, match="Minimum 2 girders"):
            bridge._validate_inputs()

    def test_design_gate_non_numeric_span_raises_cryptic_valueerror(
            self, make_input_dict):
        """ISSUE (issues/03): a non-numeric span that bypassed the GUI (e.g.
        hand-edited save file) surfaces as a raw
        'could not convert string to float' ValueError with no field context."""
        from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
            PlateGirderBridge)

        d = make_input_dict()
        d[KEY_SPAN] = "abc"
        bridge = PlateGirderBridge()
        bridge.set_input(d)
        with pytest.raises(ValueError, match="could not convert string to float"):
            bridge._validate_inputs()

    def test_layout_solver_rejects_zero_carriageway(self, make_input_dict):
        """carriageway = 0 is not rejected by the entry validator chain in the
        headless flow; it reaches the layout solver which raises a (clear but
        late) spacing error."""
        with pytest.raises(ValueError, match="below the minimum"):
            make_input_dict(carriageway_width=0.0)


# ───────────────────────── OSI load-time validation ─────────────────────────

class TestOsiValidator:
    def test_osi_span_out_of_scope_is_flagged(self):
        """OSI load: span 19 m is flagged and corrected to 20 m."""
        from osdagbridge.core.utils.osi_validator import validate_osi_inputs

        res = validate_osi_inputs({"geometry": {"span": 19.0}})
        assert not res.is_valid
        assert any("Span" in e for e in res.errors)
        assert res.corrected_values.get(KEY_SPAN) == 20.0

    def test_osi_carriageway_zero_is_flagged(self):
        """OSI load: carriageway 0 is flagged invalid."""
        from osdagbridge.core.utils.osi_validator import validate_osi_inputs

        res = validate_osi_inputs({
            "geometry.span": 30.0,
            "geometry.carriageway_width": 0.0,
        })
        assert not res.is_valid

    def test_osi_valid_inputs_pass(self):
        """OSI load: a valid geometry triple loads without errors."""
        from osdagbridge.core.utils.osi_validator import validate_osi_inputs

        res = validate_osi_inputs({
            "geometry.span": 30.0,
            "geometry.carriageway_width": 7.5,
            "geometry.skew_angle": 0.0,
        })
        assert res.is_valid, res.errors

    def test_osi_missing_optional_inputs_pass(self):
        """Untouched additional fields must never block a file load."""
        from osdagbridge.core.utils.osi_validator import validate_osi_inputs

        res = validate_osi_inputs({"geometry.span": 30.0})
        assert res.is_valid

    def test_osi_bad_design_mode_flagged(self):
        """OSI load: an unknown design_mode string is rejected."""
        from osdagbridge.core.utils.osi_validator import validate_osi_inputs

        res = validate_osi_inputs({"geometry.design_mode": "Turbo"})
        assert not res.is_valid
