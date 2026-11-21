"""Functional tests: custom steel & concrete materials propagate through a
full design run without falling back to defaults (task requirement 1).

The ``custom_material_bridge`` session fixture (conftest.py) mirrors the GUI
custom-material flow: the user opens Material Properties, enters a CUSTOM
steel (fy = 250 MPa, fu = 410 MPa, E = 205 GPa, G = 79.3 GPa, ν = 0.27) and
a CUSTOM deck (fck = 30 MPa, fctm = 2.9 MPa, Ecm = 32 GPa); the GUI renames
the grades to ``custom_steel_*`` / ``custom_concrete_*``.

Assertions check both the input_dict echo AND the values actually consumed
downstream (design_results / material_props), so a silent fallback to DB
defaults would be caught.
"""

from __future__ import annotations

import pytest

from osdagbridge.core.utils.common import (
    KEY_SPAN, KEY_UTIL_FLEXURE,
)

pytestmark = pytest.mark.slow


@pytest.mark.usefixtures("custom_material_bridge")
class TestCustomMaterialPropagation:
    def test_design_completes_with_custom_materials(self, custom_material_bridge):
        """The full 14-stage pipeline must run end-to-end on custom input."""
        assert len(custom_material_bridge.output_dict) > 500

    def test_custom_fy_fu_consumed_by_designer(self, custom_material_bridge):
        """design_results must carry the CUSTOM fy/fu — not the E350 DB row."""
        dr = dict(custom_material_bridge.output_dict)["design_results"]
        assert dr["steel_grade"] == "custom_steel_fy250"
        assert dr["fy_MPa"] == pytest.approx(250.0)
        assert dr["fu_MPa"] == pytest.approx(410.0)

    def test_custom_deck_properties_consumed(self, custom_material_bridge):
        """design_results must carry the CUSTOM deck fck/fctm — not M40."""
        dr = dict(custom_material_bridge.output_dict)["design_results"]
        assert dr["concrete_grade"] == "custom_concrete_fck30"
        assert dr["fck_MPa"] == pytest.approx(30.0)
        assert dr["fctm_MPa"] == pytest.approx(2.9)

    def test_custom_elastic_constants_consumed(self, custom_material_bridge):
        """E / G / ν must come from the custom dialog values (Pa / GPa→MPa)."""
        mp = custom_material_bridge.material_props
        assert mp.steel_prop.Fy == pytest.approx(250.0e6)     # Pa
        assert mp.steel_prop.E == pytest.approx(205.0e9)      # Pa
        assert mp.steel_prop.v == pytest.approx(0.27)
        assert mp.concrete_prop.fck == pytest.approx(30.0)

    def test_output_echoes_custom_values(self, custom_material_bridge):
        """output_dict must echo every custom material.* sub-key unchanged
        for all four members (registration + no default-back)."""
        out = dict(custom_material_bridge.output_dict)
        for member in ("girder", "cross_bracing", "end_diaphragm"):
            assert out[f"material.{member}.fy"] == 250.0
            assert out[f"material.{member}.fu"] == 410.0
            assert out[f"material.{member}.e"] == 205.0
            assert out[f"material.{member}.poisson"] == 0.27
        assert out["material.deck.fck"] == 30.0
        assert out["material.deck.fctm"] == 2.9
        assert out["material.deck.ecm"] == 32.0

    def test_lower_fy_raises_flexure_utilization(
            self, custom_material_bridge, reference_output):
        """Shape check: lowering fy (350→250) must increase the flexure
        utilization ratio of the same 30 m configuration."""
        out = dict(custom_material_bridge.output_dict)
        ref = reference_output["output"]
        assert out[KEY_SPAN] == ref[KEY_SPAN] == 30.0
        assert out[KEY_UTIL_FLEXURE] > ref[KEY_UTIL_FLEXURE]

    def test_custom_material_does_not_default_back(self, custom_material_bridge):
        """Explicit anti-regression: no E350/M40 DB value may reappear."""
        dr = dict(custom_material_bridge.output_dict)["design_results"]
        assert dr["fy_MPa"] != 350.0
        assert dr["fck_MPa"] != 40.0

    def test_custom_run_still_produces_all_component_results(
            self, custom_material_bridge):
        """Custom materials must not break transverse-member/deck design."""
        out = dict(custom_material_bridge.output_dict)
        assert out["crossbracing_design_results"]
        assert out["end_diaphragm_design_results"]
        assert out["deck_design_results"]["ur_top_uls"] >= 0


class TestDbGradePrecedenceDocumented:
    def test_db_grade_wins_over_subkeys_when_grade_name_is_db_grade(self):
        """DOCUMENTED PRECEDENCE (see Testing_Findings.md): when the grade
        name matches a DB grade ('E 350A'), _build_material_props() reads
        fy/fu/E/ν from the SQLite DB and silently IGNORES the
        material.girder.fy / .fu / .e / .poisson sub-keys.  The GUI avoids
        this by renaming custom grades to custom_steel_*, but any headless /
        hand-edited input that keeps a DB grade name while editing sub-keys
        gets the DB values.  This test pins that (surprising) behaviour."""
        from conftest import make_input
        from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
            PlateGirderBridge)

        d = make_input(girder_grade="E 350A")   # DB grade kept
        d["material.girder.fy"] = 250.0         # sub-key edited anyway
        bridge = PlateGirderBridge()
        bridge.set_input(d)
        mp = bridge._build_material_props()
        assert mp.steel_prop.Fy == pytest.approx(350.0e6), (
            "DB lookup no longer takes precedence — update this documenting "
            "test and the findings note")
