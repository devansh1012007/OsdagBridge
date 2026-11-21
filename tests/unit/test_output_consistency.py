"""Output-dictionary self-consistency tests (fast — uses the recorded
baseline reference run instead of re-running the ~30 s pipeline).

Verified against the reference produced by scripts/smoke_headless.py
(30 m span / 7.5 m carriageway / 4 girders / E350A / M40, unmodified code).

Component coverage required by the task:
girders + stiffeners + cross bracings + end diaphragms + concrete deck.
"""

from __future__ import annotations

import math

import pytest

from osdagbridge.core.utils.common import (
    KEY_SPAN, KEY_CARRIAGEWAY_WIDTH, KEY_SKEW_ANGLE,
    KEY_UTIL_FLEXURE, KEY_UTIL_SHEAR, KEY_UTIL_INTERACTION, KEY_UTIL_LTB,
    KEY_UTIL_LONG_TRANS_SHEAR, KEY_UTIL_FATIGUE, KEY_UTIL_STRESS_LIMITATION,
    KEY_UTIL_DEFLECTION_CRACK,
    KEY_TS_NO_OF_GIRDERS, KEY_GIRDER, KEY_DECK_CONCRETE_GRADE_BASIC,
    KEY_MATERIAL_GIRDER_FY, KEY_MATERIAL_DECK_FCK,
)

ALL_UTIL_KEYS = [KEY_UTIL_FLEXURE, KEY_UTIL_SHEAR, KEY_UTIL_INTERACTION,
                 KEY_UTIL_LTB, KEY_UTIL_LONG_TRANS_SHEAR, KEY_UTIL_FATIGUE,
                 KEY_UTIL_STRESS_LIMITATION, KEY_UTIL_DEFLECTION_CRACK]


@pytest.fixture()
def inp(reference_output):
    return reference_output["input"]


@pytest.fixture()
def out(reference_output):
    return reference_output["output"]


class TestInputEcho:
    def test_geometry_echoes_match_entered_values(self, inp, out):
        """output_dict echoes of the basic geometry must equal what was set."""
        assert out[KEY_SPAN] == inp[KEY_SPAN] == 30.0
        assert out[KEY_CARRIAGEWAY_WIDTH] == inp[KEY_CARRIAGEWAY_WIDTH] == 7.5
        assert out[KEY_SKEW_ANGLE] == inp[KEY_SKEW_ANGLE] == 0.0

    def test_material_echoes_match_entered_values(self, inp, out):
        """Custom material sub-keys survive the pipeline unmodified."""
        for member in ("girder", "cross_bracing", "end_diaphragm"):
            for prop, expected in (("fy", 350.0), ("fu", 490.0), ("e", 200.0),
                                   ("g", 76.9), ("poisson", 0.30)):
                assert out[f"material.{member}.{prop}"] == expected, (
                    f"material.{member}.{prop} drifted from user input")
        assert out["material.deck.fck"] == 40.0
        assert out["material.deck.fctm"] == 3.0
        assert out["material.deck.ecm"] == 33.0

    def test_design_results_use_selected_material(self, out):
        """design_results must carry the selected grade's properties."""
        dr = out["design_results"]
        assert dr["steel_grade"] == "E 350A"
        assert dr["fy_MPa"] == 350.0
        assert dr["fu_MPa"] == 490.0
        assert dr["concrete_grade"] == "M40"
        assert dr["fck_MPa"] == 40.0


class TestUtilizationRatios:
    def test_all_eight_utilisation_keys_present_and_numeric(self, out):
        """A utilization percentage must exist for every IRC 22 category."""
        for key in ALL_UTIL_KEYS:
            assert key in out, f"missing utilization key {key}"
            val = out[key]
            assert isinstance(val, (int, float)) and math.isfinite(val), (
                f"{key} = {val!r} is not a finite number")
            assert val >= 0.0

    def test_util_percentages_match_category_dcr(self, out):
        """util.<cat> (in %) must equal category_urs max_dcr × 100."""
        dr = out["design_results"]
        cat = dr["category_urs"]
        mapping = {
            1: KEY_UTIL_FLEXURE, 2: KEY_UTIL_SHEAR, 3: KEY_UTIL_INTERACTION,
            4: KEY_UTIL_LTB, 5: KEY_UTIL_LONG_TRANS_SHEAR, 6: KEY_UTIL_FATIGUE,
            7: KEY_UTIL_STRESS_LIMITATION, 8: KEY_UTIL_DEFLECTION_CRACK,
        }
        for cat_id, util_key in mapping.items():
            expected = cat[str(cat_id)]["max_dcr"] * 100.0
            assert out[util_key] == pytest.approx(expected, rel=1e-6), (
                f"{util_key} inconsistent with design_results.category_urs")

    def test_overall_status_consistent_with_categories(self, out):
        """overall_status is FAIL iff any of the 8 categories reports FAIL."""
        dr = out["design_results"]
        any_fail = any(c.get("status") == "FAIL"
                       for c in dr["category_urs"].values())
        assert (dr["overall_status"] == "FAIL") == any_fail

    def test_max_dcr_equals_worst_category(self, out):
        """max_dcr must equal the worst of the 8 category max_dcr values."""
        dr = out["design_results"]
        worst = max(c["max_dcr"] for c in dr["category_urs"].values())
        assert dr["max_dcr"] == pytest.approx(worst, rel=1e-9)

    def test_reference_run_fails_fatigue(self, out):
        """BASELINE FINDING (issues/06): the shipped default 30 m reference
        configuration ends with overall_status = FAIL driven by the fatigue
        check (DCR ≈ 1.57). Pins current behaviour; if the optimizer gains a
        fatigue loop, update this test."""
        dr = out["design_results"]
        assert dr["overall_status"] == "FAIL"
        assert dr["category_urs"]["6"]["label"].startswith("Fatigue")
        assert dr["category_urs"]["6"]["max_dcr"] > 1.0

    def test_stiffener_failures_excluded_from_overall_status(self, out):
        """BASELINE FINDING (issues/06): check_id 20/21 (stiffeners) are
        excluded from overall_status / n_pass / n_fail. In the reference run
        the intermediate-stiffener leg check FAILS (DCR ≈ 1.48) yet is absent
        from the tallies and would not flip the overall status."""
        dr = out["design_results"]
        checks = dr["checks"]
        all_fail = [c for c in checks if c["status"] == "FAIL"]
        assert len(all_fail) >= 2, "expected fatigue + stiffener failures"
        stiffener_fails = [c for c in all_fail if c["check_id"] in (20, 21)]
        assert stiffener_fails, "expected an intermediate-stiffener failure"
        # Tallies only cover the structural (8-category) checks:
        structural = [c for c in checks if c["check_id"] not in (20, 21)]
        assert dr["n_pass"] + dr["n_warn"] + dr["n_fail"] == len(structural)
        assert dr["n_fail"] == sum(1 for c in structural if c["status"] == "FAIL")
        # ...while the displayed checks list has more entries incl. failures:
        assert len(checks) > dr["n_pass"] + dr["n_warn"] + dr["n_fail"]


class TestComponentCoverage:
    def test_girder_design_results_complete(self, out):
        """Girder results: section, demands, capacities, per-girder demands."""
        dr = out["design_results"]
        for key in ("section_designation", "Mu_kNm", "Vu_kN", "Md_kNm",
                    "Vd_kN", "Mb_kNm", "controlling_girder",
                    "governing_combination", "overall_status", "max_dcr"):
            assert key in dr, f"design_results missing {key}"
        per_girder = dr["per_girder"]
        assert len(per_girder) >= int(out[KEY_TS_NO_OF_GIRDERS])
        for g, gd in per_girder.items():
            assert "demand" in gd and "Mu_kNm" in gd["demand"]

    def test_cross_bracing_design_results_present(self, out):
        """Cross bracings: results exist for every consecutive girder pair,
        diagonal + chord × tension + compression (stub Osdag: shape only)."""
        cb = out["crossbracing_design_results"]
        n_girders = int(out[KEY_TS_NO_OF_GIRDERS])
        expected_pairs = [f"G{i}-G{i+1}" for i in range(1, n_girders)]
        assert sorted(cb.keys()) == expected_pairs
        for pair in expected_pairs:
            for member in ("diagonal", "chord"):
                assert member in cb[pair]
                for force_type in ("tension", "compression"):
                    assert force_type in cb[pair][member]
        # Shape-only assertions — capacities come from the sandbox stub.
        g12 = cb["G1-G2"]["diagonal"]["tension"]
        assert isinstance(g12, (dict, type(None)))

    def test_end_diaphragm_design_results_present(self, out):
        """End diaphragms: pair keys exist for every consecutive girder pair —
        but every pair dict is EMPTY (BUG, see issues/02-end-diaphragm-empty).

        The ED force extraction reads Vz_i from the support-line transverse
        grillage members; for those members Vz_i is 0.0 in every load case
        (the transverse shear is reported in Vy_i), so no design forces are
        ever collected and no Osdag member designs are run.  Current
        behaviour is pinned here; the functional test
        test_additional_inputs.py::TestEndDiaphragmAdditionalInputs proves
        the defect survives even when the user fully configures the EDs.
        """
        ed = out["end_diaphragm_design_results"]
        n_girders = int(out[KEY_TS_NO_OF_GIRDERS])
        expected_pairs = [f"G{i}-G{i+1}" for i in range(1, n_girders)]
        assert sorted(ed.keys()) == expected_pairs
        # Documented defect: no design results for any pair.
        assert all(pair_data == {} for pair_data in ed.values()), (
            "ED design results are no longer empty — the force-extraction "
            "defect may be fixed; update this test and issues/02")
        # The envelope force dict mirrors the emptiness (all forces None).
        edf = out["end_diaphragm_forces_dict"]["pairs"]
        for pair in expected_pairs:
            assert all(v is None for v in edf[pair].values()), pair

    def test_deck_design_results_present(self, out):
        """Concrete deck: IRC 22 utilization ratios for top/bottom, ULS/SLS
        and crack checks are all present and numeric."""
        deck = out["deck_design_results"]
        for key in ("ur_top_uls", "ur_bot_uls", "ur_top_sls_c", "ur_bot_sls_c",
                    "ur_top_sls_s", "ur_bot_sls_s", "ur_top_crack", "ur_bot_crack"):
            assert key in deck, f"deck_design_results missing {key}"
            assert isinstance(deck[key], (int, float))

    def test_stiffener_results_present(self, out):
        """Stiffeners: intermediate + bearing geometry & check values."""
        dr = out["design_results"]
        for key in ("is_tq_mm", "is_H_mm", "is_c_mm", "is_Iys_min_mm4",
                    "is_Iys_prov_mm4", "bs_tq_mm", "bs_H_mm", "bs_R_kN"):
            assert key in dr, f"stiffener result {key} missing"
        # Stiffener detail keys are also echoed per girder member:
        stiff_keys = [k for k in out if k.startswith(
            "member_properties.stiffener_details.")]
        assert stiff_keys, "no member_properties.stiffener_details.* echoes"

    def test_shear_connector_results_present(self, out):
        """Shear connectors: stud forces and provided/governing spacing."""
        dr = out["design_results"]
        for key in ("Qu_kN", "Qr_kN", "VL_N_per_mm", "stud_spacing_uls_mm",
                    "stud_spacing_governing_mm", "stud_spacing_provided_mm",
                    "stud_detailing_ok"):
            assert key in dr, f"shear connector result {key} missing"
        assert isinstance(dr["stud_detailing_ok"], bool)

    def test_deflection_outputs_present(self, out):
        """Per-girder deflections are written as KEY_SD_DEFL_*.<girder>."""
        defl = [k for k in out if k.startswith("steeldesign.deflection.")]
        assert any(k.endswith(".G1") for k in defl)


class TestInternalDictionaryInspection:
    def test_design_results_girder_count_is_grillage_grid_lines(self, out):
        """BUG (issues/07-edge-beams-designed-as-girders): design_results
        ['n_girders'] reports the grillage longitudinal grid-line count
        (2 edge beams + 4 structural girders = 6), not the user's girder
        count (designer.py:401 reads geom.n_l), and per_girder labels the
        overhang edge beams G1/G6 while the user's four girders surface as
        G2..G5 (labels shifted by one).
        Root cause: the analysis handler that feeds run_design_check is
        built without edge_dist (plategirderbridge.py:2296 _run_dcr_checks,
        and likewise :3265/:3765; only compute_load_effects_cache :3291 and
        analyser.py:2861 pass it), so build_girders() (analysis_results.py:
        456-460) never enters its EB1/EB2 naming branch and the EB filters
        downstream (designer.py:2816/3203, executive_summary.py:84) are
        dead code.  Current behaviour pinned here; see the issue draft for
        the fix."""
        assert int(out[KEY_TS_NO_OF_GIRDERS]) == 4
        assert out["design_results"]["n_girders"] == 6
        assert set(out["design_results"]["per_girder"]) == {
            "G1", "G2", "G3", "G4", "G5", "G6"}

    def test_edge_beam_filter_is_dead_code(self, out):
        """issues/07 consequence: the reference run's 4-girder bridge shows
        per_girder rows G1..G6 where G1/G6 are the overhang edge beams
        (outermost symmetric pair, Mu = 2160 kNm vs 2219 kNm interior) —
        the EB1/EB2 skip logic in executive_summary.py / designer.py can
        never fire because no girder is ever *named* EB*."""
        per_girder = out["design_results"]["per_girder"]
        named_eb = [g for g in per_girder if str(g).startswith("EB")]
        assert named_eb == [], "EB naming active — issues/07 may be fixed"
