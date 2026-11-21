"""Functional tests: multi-run & state-persistence (task requirement 2).

Simulates the GUI workflow of running a design, unlocking the inputs,
modifying parameters, and re-running — headlessly this is a new
``set_input(...)`` + ``design()`` on the SAME instance.  Three consecutive
runs are performed on one instance with different parameters each time,
then a fresh instance is used to verify there is no hidden state carried
between runs.
"""

from __future__ import annotations

import pytest

from conftest import make_input

from osdagbridge.core.utils.common import (
    KEY_SPAN, KEY_CARRIAGEWAY_WIDTH, KEY_TS_NO_OF_GIRDERS, KEY_TS_OVERALL_WIDTH,
    KEY_UTIL_FLEXURE, KEY_UTIL_FATIGUE, KEY_SD_SECTION_DESIGNATION,
)


def _run(bridge, input_dict):
    """Unlock-equivalent: fresh set_input + design on the instance."""
    bridge.set_input(input_dict)
    bridge.design()
    return dict(bridge.output_dict)


@pytest.mark.slow
class TestThreeConsecutiveRuns:
    """Run 1: default 30 m / 7.5 m / E350A
       Run 2: span 35 m + custom steel fy=250
       Run 3: carriageway 10.5 m (wider deck, more girders expected)"""

    @pytest.fixture(scope="class")
    def runs(self):
        from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
            PlateGirderBridge)

        bridge = PlateGirderBridge()

        # ── Run 1: reference configuration ───────────────────────────────
        d1 = make_input(span=30.0, carriageway_width=7.5)
        od1 = _run(bridge, d1)

        # ── Run 2: unlock → change span + switch to a custom weaker steel ─
        d2 = make_input(span=35.0, carriageway_width=7.5,
                        girder_grade="custom_steel_fy250")
        d2["material.girder"] = "custom_steel_fy250"
        d2["material.cross_bracing"] = "custom_steel_fy250"
        d2["material.end_diaphragm"] = "custom_steel_fy250"
        for member in ("girder", "cross_bracing", "end_diaphragm"):
            d2[f"material.{member}.fy"] = 250.0
            d2[f"material.{member}.fu"] = 410.0
        od2 = _run(bridge, d2)

        # ── Run 3: unlock → widen carriageway to 10.5 m ──────────────────
        d3 = make_input(span=35.0, carriageway_width=10.5,
                        girder_grade="custom_steel_fy250")
        d3["material.girder"] = "custom_steel_fy250"
        d3["material.cross_bracing"] = "custom_steel_fy250"
        d3["material.end_diaphragm"] = "custom_steel_fy250"
        for member in ("girder", "cross_bracing", "end_diaphragm"):
            d3[f"material.{member}.fy"] = 250.0
            d3[f"material.{member}.fu"] = 410.0
        od3 = _run(bridge, d3)

        return {"bridge": bridge, "outputs": [od1, od2, od3],
                "inputs": [d1, d2, d3]}

    def test_all_three_runs_complete(self, runs):
        """All three consecutive runs on one instance finish with full outputs."""
        assert all(len(od) > 500 for od in runs["outputs"])

    # ── Run 2 verification: changed span + material must be reflected ─────

    def test_run2_span_echo_updated(self, runs):
        """After unlock→span 35 m, both echo keys must read 35 m."""
        od2 = runs["outputs"][1]
        assert od2[KEY_SPAN] == 35.0
        assert od2["design_results"]["span_m"] == 35.0

    def test_run2_no_stale_span_from_run1(self, runs):
        """No key may still show the run-1 span of 30 m."""
        od1, od2 = runs["outputs"][0], runs["outputs"][1]
        assert od1[KEY_SPAN] == 30.0
        assert od2[KEY_SPAN] == 35.0
        assert od2["design_results"]["span_m"] != od1["design_results"]["span_m"]

    def test_run2_custom_material_consumed(self, runs):
        """Run 2's custom steel (fy=250) must be the one the designer used."""
        od2 = runs["outputs"][1]
        assert od2["design_results"]["fy_MPa"] == pytest.approx(250.0)
        assert od2["design_results"]["fu_MPa"] == pytest.approx(410.0)

    def test_run2_results_actually_recomputed(self, runs):
        """Deflections / section / utilization must change with span+fy."""
        od1, od2 = runs["outputs"][0], runs["outputs"][1]
        assert od2["design_results"]["delta_live_mm"] != \
            od1["design_results"]["delta_live_mm"]
        assert od2[KEY_UTIL_FLEXURE] != od1[KEY_UTIL_FLEXURE]
        assert od2[KEY_SD_SECTION_DESIGNATION] != \
            od1[KEY_SD_SECTION_DESIGNATION]

    # ── Run 3 verification: wider carriageway changes layout ──────────────

    def test_run3_carriageway_echo_updated(self, runs):
        """After unlock→carriageway 10.5 m, both echo keys must read 10.5 m."""
        od3 = runs["outputs"][2]
        assert od3[KEY_CARRIAGEWAY_WIDTH] == 10.5
        assert od3["design_results"]["carriageway_width_m"] == 10.5

    def test_run3_layout_changed(self, runs):
        """The wider carriageway must produce a wider overall bridge width."""
        od2, od3 = runs["outputs"][1], runs["outputs"][2]
        assert od3[KEY_TS_OVERALL_WIDTH] > od2[KEY_TS_OVERALL_WIDTH]

    def test_run3_girder_pairs_rebuilt(self, runs):
        """Cross-bracing result keys must match the new girder count."""
        od3 = runs["outputs"][2]
        n = int(od3[KEY_TS_NO_OF_GIRDERS])
        expected = [f"G{i}-G{i+1}" for i in range(1, n)]
        assert sorted(od3["crossbracing_design_results"].keys()) == expected

    def test_no_stale_utilization_values(self, runs):
        """util.* must differ between runs where the config differs, and be
        internally consistent (percent == category DCR × 100) every time.

        NOTE: in a live design_results dict the category_urs keys are INTs
        (JSON serialization in the reference smoke output stringifies them,
        but run_design_check's DCREngine.category_urs() returns Dict[int, dict]).
        """
        seen = []
        for od in runs["outputs"]:
            cats = od["design_results"]["category_urs"]
            assert od[KEY_UTIL_FLEXURE] == pytest.approx(
                cats[1]["max_dcr"] * 100.0, rel=1e-6)
            assert od[KEY_UTIL_FATIGUE] == pytest.approx(
                cats[6]["max_dcr"] * 100.0, rel=1e-6)
            seen.append(od[KEY_UTIL_FLEXURE])
        assert len(set(seen)) == 3, "utilization values look stale across runs"


@pytest.mark.slow
class TestFreshInstanceEquivalence:
    def test_fresh_instance_matches_reused_instance(self):
        """A fresh instance given the same final configuration must produce
        the same headline results as a re-used (unlocked+rerun) instance —
        i.e. no state from earlier runs leaks into the numbers."""
        from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
            PlateGirderBridge)

        def final_config():
            return make_input(span=32.0, carriageway_width=7.5)

        # Reused instance: run an unrelated configuration first…
        bridge = PlateGirderBridge()
        _run(bridge, make_input(span=25.0, carriageway_width=7.5))
        od_reused = _run(bridge, final_config())

        # …then a fresh instance with the final configuration.
        fresh = PlateGirderBridge()
        od_fresh = _run(fresh, final_config())

        for key in (KEY_SPAN, KEY_TS_NO_OF_GIRDERS, KEY_UTIL_FLEXURE,
                    KEY_UTIL_FATIGUE, KEY_SD_SECTION_DESIGNATION):
            assert od_reused[key] == od_fresh[key], (
                f"{key} differs between reused and fresh instance "
                f"({od_reused[key]!r} vs {od_fresh[key]!r}) — stale state")
        assert (od_reused["design_results"]["delta_live_mm"]
                == od_fresh["design_results"]["delta_live_mm"])
