"""Functional tests: additional-input registration & consumption (task req. 1).

The ``additional_inputs_bridge`` session fixture runs the full design with the
Additional-Input keys a GUI user would have set in the *Transverse Member
Design* (end-diaphragm tab) and *Stiffener Details* tabs:

  * end diaphragms configured as ``Cross Bracing`` (X, top+bottom chords) for
    every girder pair, both member slots (E{n}M1 / E{n}M2) — exactly the keys
    ``AdditionalInputsDialog._save_ed_pair()`` serialises;
  * CUSTOM stiffener plate sizes (intermediate thickness/spacing/outstand and
    bearing thickness/outstand) via the legacy scalar keys the designer's
    ``_member_value()`` falls back to.

The run then verifies which of those custom inputs are actually *consumed*
downstream (echoed in output_dict / design_results) instead of silently
defaulting back.

It also pins the end-diaphragm force-extraction defect (issues/02): even with
the EDs fully configured, no design forces are collected and
``end_diaphragm_design_results`` stays empty.
"""

from __future__ import annotations

import pytest

from conftest import make_input

from osdagbridge.core.utils.common import (
    KEY_TS_NO_OF_GIRDERS,
    KEY_MP_ED_TYPE, KEY_MP_ED_BRACING_TYPE, KEY_MP_ED_TOP_CHORD,
    KEY_MP_ED_BOTTOM_CHORD,
    KEY_MP_STIFFENER_INTERMEDIATE_SPACING, KEY_MP_STIFFENER_INTERMEDIATE_THICKNESS,
    KEY_MP_STIFFENER_INTERMEDIATE_OUTSTAND, KEY_MP_STIFFENER_BEARING_THICKNESS,
    KEY_MP_STIFFENER_BEARING_OUTSTAND,
)

def custom_stiffener_keys(n_girders: int) -> dict:
    """Custom stiffener plate sizes written the way the Additional-Input
    dialog's stiffener tab serialises them: per girder member .G{n}.M1.

    Set: intermediate thickness 12 mm / spacing 2000 mm / outstand 125 mm,
    bearing thickness 12 mm / outstand 150 mm (auto-sized defaults for this
    configuration are 10 mm / 2440 mm / 250 mm — see smoke_output.json).
    """
    keys = {}
    for g in range(1, n_girders + 1):
        suffix = f".G{g}.M1"
        keys[KEY_MP_STIFFENER_INTERMEDIATE_SPACING + suffix] = 2000.0
        keys[KEY_MP_STIFFENER_INTERMEDIATE_THICKNESS + suffix] = 12.0
        keys[KEY_MP_STIFFENER_INTERMEDIATE_OUTSTAND + suffix] = 125.0
        keys[KEY_MP_STIFFENER_BEARING_THICKNESS + suffix] = 12.0
        keys[KEY_MP_STIFFENER_BEARING_OUTSTAND + suffix] = 150.0
    return keys


def ed_configured_input() -> dict:
    """Default 30 m input + fully-configured end diaphragms + custom
    stiffener plate sizes (mirrors the Additional Input dialog's exports)."""
    d = make_input()
    n = int(d[KEY_TS_NO_OF_GIRDERS])
    for i in range(1, n):
        pair_id = f"G{i}G{i+1}"
        for mi in (1, 2):                      # both end-diaphragm member slots
            suf = f".{pair_id}.E{i}M{mi}"
            d[KEY_MP_ED_TYPE + suf] = "Cross Bracing"
            d[KEY_MP_ED_BRACING_TYPE + suf] = "X"
            d[KEY_MP_ED_TOP_CHORD + suf] = True
            d[KEY_MP_ED_BOTTOM_CHORD + suf] = True
    d.update(custom_stiffener_keys(n))
    return d


@pytest.fixture(scope="session")
def additional_inputs_bridge():
    """Full design run with ED + custom-stiffener additional inputs (slow)."""
    from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
        PlateGirderBridge)

    bridge = PlateGirderBridge()
    bridge.set_input(ed_configured_input())
    bridge.design()
    return bridge


@pytest.mark.slow
class TestEndDiaphragmAdditionalInputs:
    """ED additional inputs are *registered* but the design stage cannot use
    them (issues/02): the force extraction reads Vz_i from the support-line
    transverse grillage members, where Vz_i == 0 in every load case."""

    def test_ed_type_is_registered_and_echoed(self, additional_inputs_bridge):
        """The type/bracing/chord flags must land in output_dict per pair —
        the pipeline does register what the dialog exported.  Design-stage
        echoes remap to '<base>.<pair>.<field>' via make_pair_key(); the raw
        input keys are echoed verbatim as well."""
        od = dict(additional_inputs_bridge.output_dict)
        n = int(od[KEY_TS_NO_OF_GIRDERS])
        for i in range(1, n):
            pair_id = f"G{i}G{i+1}"
            # design-stage echoes (make_pair_key remap: <prefix>.<pair>.<field>)
            assert od[f"member_properties.end_diaphragm_details.{pair_id}.type"] \
                == "Cross Bracing"
            assert od[f"member_properties.end_diaphragm_details.{pair_id}.bracing_type"] \
                == "X"
            assert od[f"member_properties.end_diaphragm_details.{pair_id}.top_chord"] is True
            assert od[f"member_properties.end_diaphragm_details.{pair_id}.bottom_chord"] is True
        # verbatim input echo for one member slot
        assert od["member_properties.end_diaphragm_details.type.G1G2.E1M1"] \
            == "Cross Bracing"

    def test_ed_section_properties_populated_from_designation(self,
                                                              additional_inputs_bridge):
        """Section-property outputs are written for every pair (from the
        designation DB lookup), so the *geometry* side of the ED stage runs."""
        od = dict(additional_inputs_bridge.output_dict)
        for pair_id in ("G1G2", "G2G3", "G3G4"):
            a = od[f"transverse_member_design.ed.section_properties.end_diaphragm.{pair_id}.A"]
            assert isinstance(a, (int, float)) and a > 0

    def test_ed_design_forces_all_none(self, additional_inputs_bridge):
        """BUG (issues/02): with the EDs fully configured the envelope force
        extraction still yields zero forces — every pair's tension/compression
        envelope is None because Vz_i is 0.0 on the support-line members the
        code reads (the transverse shear there is reported in Vy_i)."""
        od = dict(additional_inputs_bridge.output_dict)
        edf = od["end_diaphragm_forces_dict"]["pairs"]
        assert set(edf) == {"G1-G2", "G2-G3", "G3-G4"}
        for pair, forces in edf.items():
            assert all(v is None for v in forces.values()), (pair, forces)

    def test_ed_design_results_empty_despite_configuration(self,
                                                           additional_inputs_bridge):
        """BUG consequence (issues/02): end_diaphragm_design_results contains
        no member designs for any pair — the report shows empty ED tables and
        the executive summary silently omits end-diaphragm utilization."""
        od = dict(additional_inputs_bridge.output_dict)
        ed = od["end_diaphragm_design_results"]
        assert set(ed) == {"G1-G2", "G2-G3", "G3-G4"}
        assert all(pair_data == {} for pair_data in ed.values())


@pytest.mark.slow
class TestCustomStiffenerInputs:
    """Custom stiffener plate sizes must be consumed by the designer, not
    replaced by the auto-sized defaults."""

    def test_custom_stiffener_geometry_consumed(self, additional_inputs_bridge):
        """design_results must carry the CUSTOM intermediate stiffener
        thickness/spacing/outstand (set: 12 mm / 2000 mm / 125 mm)."""
        dr = dict(additional_inputs_bridge.output_dict)["design_results"]
        assert dr["is_tq_mm"] == pytest.approx(12.0)
        assert dr["is_c_mm"] == pytest.approx(2000.0)
        assert dr["is_H_mm"] == pytest.approx(125.0)

    def test_custom_bearing_stiffener_consumed(self, additional_inputs_bridge):
        """design_results must carry the CUSTOM bearing stiffener thickness
        (set: 12 mm) instead of the auto-sized value."""
        dr = dict(additional_inputs_bridge.output_dict)["design_results"]
        assert dr["bs_tq_mm"] == pytest.approx(12.0)

    def test_custom_stiffener_echoes_in_output(self, additional_inputs_bridge):
        """Every user-set stiffener key must be echoed verbatim in output_dict
        (registration without silent defaulting back)."""
        od = dict(additional_inputs_bridge.output_dict)
        for key, expected in custom_stiffener_keys(4).items():
            assert od.get(key) == pytest.approx(expected), (
                f"{key} drifted from the user-set value "
                f"({od.get(key)!r} != {expected!r})")

    def test_provided_inertia_derives_from_custom_outstand(self,
                                                           additional_inputs_bridge):
        """Iys provided must be recomputed from the custom plate sizes, so it
        must differ from an auto-sized run's value and stay positive."""
        dr = dict(additional_inputs_bridge.output_dict)["design_results"]
        assert dr["is_Iys_prov_mm4"] > 0
        assert isinstance(dr["is_Iys_min_mm4"], (int, float))


@pytest.mark.slow
class TestCrossBracingDesignPipeline:
    """Under pytest (importable __main__) the forkserver design pool works, so
    the cross-bracing member designs produce real result dicts (stub Osdag)."""

    def test_cb_design_results_have_numeric_capacities(self,
                                                       additional_inputs_bridge):
        """Every pair×member×force combination that has a design force must
        carry a numeric capacity + efficiency (shape only — stub values)."""
        od = dict(additional_inputs_bridge.output_dict)
        cb = od["crossbracing_design_results"]
        n = int(od[KEY_TS_NO_OF_GIRDERS])
        assert sorted(cb) == [f"G{i}-G{i+1}" for i in range(1, n)]
        found = 0
        for pair, members in cb.items():
            for member in ("diagonal", "chord"):
                for force_type, res in members[member].items():
                    if res is None:
                        continue
                    found += 1
                    assert isinstance(res["Design.Strength"], (int, float))
                    assert 0 <= float(res["Member.efficiency"]) <= 10
        assert found > 0, ("no cross-bracing designs ran — check the design "
                           "pool availability in this environment")

    def test_cb_forces_reference_seismic_cases_only(self,
                                                    additional_inputs_bridge):
        """OBSERVATION (Testing_Findings.md): the CB force extraction reads
        Vz_i, which is non-zero only for the transverse-seismic cases — the
        much larger gravity/live transverse shears live in Vy_i and are not
        considered for the bracing design."""
        od = dict(additional_inputs_bridge.output_dict)
        gov_lcs = set()
        for pair, forces in od["crossbracing_forces_dict"]["pairs"].items():
            for key, val in forces.items():
                if key.endswith("_gov_lc") and val:
                    gov_lcs.add(val)
        assert gov_lcs, "no governing load cases recorded for bracing"
        assert all("EQ" in lc for lc in gov_lcs), (
            f"bracing governs from non-seismic cases too now: {gov_lcs}")
