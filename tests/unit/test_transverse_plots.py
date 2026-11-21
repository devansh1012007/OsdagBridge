"""
Task III tests — result plotting for Transverse Members.

Builds a synthetic grillage *result-data dictionary* whose geometry is driven
by the completed design in ``/home/z/my-project/work/shared/smoke_output.json``
(span, girder count, girder spacing, overhang, cross-bracing spacing) and
verifies that

* the transverse extraction (End Diaphragms + Intermediate Cross Bracings as
  a single component) returns **non-empty series**, and
* transverse element tags are **disjoint from the longitudinal tags**,
* all required components (Fx, Vy, Vz, Tx=Mx, My, Mz, deflections) are pulled
  for the selected load case with correct unit conversion,
* the graph-engine member-selection API exposes "Transverse Members", and
* the matplotlib / plotly transverse figure builders render from the data.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# Make the in-repo conftest helpers importable even when pytest is invoked
# from a different rootdir.
_HERE = os.path.dirname(os.path.abspath(__file__))
_TESTS_DIR = os.path.dirname(_HERE)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from osdagbridge.core.bridge_types.plate_girder.results_data import (
    END_DIAPHRAGM_LABEL,
    INTERMEDIATE_BRACING_LABEL,
    TRANSVERSE_FORCE_COMPONENTS,
    TRANSVERSE_MEMBERS_LABEL,
    classify_longitudinal_transverse,
    extract_transverse_displacement_series,
    extract_transverse_force_series,
    extract_transverse_member_results,
    get_transverse_member_chains,
    longitudinal_element_tags,
    transverse_element_tags,
)

SMOKE_JSON = "/home/z/my-project/work/shared/smoke_output.json"


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic result-data dictionary (geometry from smoke_output.json)
# ─────────────────────────────────────────────────────────────────────────────

def _smoke_geometry():
    """Read the completed design geometry from smoke_output.json."""
    if not os.path.isfile(SMOKE_JSON):
        pytest.skip(f"smoke_output.json not found at {SMOKE_JSON}")
    with open(SMOKE_JSON) as f:
        smoke = json.load(f)

    inp = smoke["input"]
    out = smoke["output"]

    return {
        "span": float(inp["geometry.span"]),
        "n_girders": int(out["typical_section.no_of_girders"]),
        "girder_spacing": float(out["typical_section.girder_spacing"]),
        "overhang": float(out["deck_design_results"]["deck_overhang"]),
        # cb spacing lives on the cross-bracing geometry the design produced
        "cb_spacing": float(
            out["crossbracing_forces_dict"]["geometry"]["cb_spacing_m"]
        ),
        "loadcase": "girder self weight",
    }


def _build_result_data():
    """
    Build a restructured-output-dictionary look-alike for a straight plate
    girder bridge matching the smoke design:

    * longitudinal lines: edge beams (±overhang) + n girders,
    * intermediate transverse members at every ``cb_spacing`` station,
    * end diaphragms at x = 0 and x = span (start_edge / end_edge elements),
    * forces stored in N / N·mm and displacements in m (ospgrillage units).
    """
    geom = _smoke_geometry()
    span = geom["span"]
    n_girders = geom["n_girders"]
    spacing = geom["girder_spacing"]
    overhang = geom["overhang"]
    cb_spacing = geom["cb_spacing"]

    z_lines = [-(overhang)]                      # edge beam 1
    z_lines += [i * spacing for i in range(n_girders)]
    z_lines.append((n_girders - 1) * spacing + overhang)   # edge beam 2

    x_stations = [0.0, span] + [
        x for x in _frange(cb_spacing, span, cb_spacing) if x < span - 1e-9
    ]
    x_stations = sorted(set(round(x, 6) for x in x_stations))

    # ── nodes ────────────────────────────────────────────────────────────
    nodes: dict = {}
    node_tag = 1
    node_at = {}
    for z in z_lines:
        for x in x_stations:
            nodes[str(node_tag)] = [x, 0.0, z]
            node_at[(round(x, 6), round(z, 6))] = node_tag
            node_tag += 1

    # ── members ──────────────────────────────────────────────────────────
    members: dict = {}
    elem_tag = 1

    def _add_member(n1, n2):
        nonlocal elem_tag
        members[str(elem_tag)] = [n1, n2]
        elem_tag += 1
        return elem_tag - 1

    # Longitudinal elements along every line (girders + edge beams)
    girder_members = {i: [] for i in range(len(z_lines))}
    for li, z in enumerate(z_lines):
        for x0, x1 in zip(x_stations[:-1], x_stations[1:]):
            n1 = node_at[(round(x0, 6), round(z, 6))]
            n2 = node_at[(round(x1, 6), round(z, 6))]
            girder_members[li].append(_add_member(n1, n2))

    # Transverse members between ADJACENT GIRDERS (not edge beams):
    #   x = 0 and x = span → end diaphragms,
    #   intermediate stations → intermediate cross bracings.
    diaphragm_tags = []
    bracing_chains = []
    girder_pairs = [
        (gi, gi + 1) for gi in range(1, n_girders)  # 1-based girder indices
    ]
    for x in x_stations:
        for (g_left, g_right) in girder_pairs:
            z_left = z_lines[g_left]
            z_right = z_lines[g_right]
            n1 = node_at[(round(x, 6), round(z_left, 6))]
            n2 = node_at[(round(x, 6), round(z_right, 6))]
            tag = _add_member(n1, n2)
            if x <= 1e-9 or x >= span - 1e-9:
                diaphragm_tags.append(tag)
            else:
                bracing_chains.append({
                    "members": [tag],
                    "left_girder": f"G{g_left}",
                    "right_girder": f"G{g_right}",
                    "start": {"node": n1, "coords": [x, 0.0, z_left]},
                    "end":   {"node": n2, "coords": [x, 0.0, z_right]},
                    "mid":   {"coords": [x, 0.0, (z_left + z_right) / 2]},
                })

    # Transverse slab overhang pieces (edge beam ↔ outer girder) — present in
    # real models, excluded from both end diaphragms and cross bracings.
    for x in x_stations:
        for edge_z, girder_z, girder_idx in (
            (z_lines[0], z_lines[1], 1),
            (z_lines[-1], z_lines[-2], n_girders),
        ):
            n1 = node_at[(round(x, 6), round(edge_z, 6))]
            n2 = node_at[(round(x, 6), round(girder_z, 6))]
            _add_member(n1, n2)

    # ── girder map (post_process "girders" structure) ────────────────────
    girders = {}
    for gi in range(1, n_girders + 1):
        line = girder_members[gi]
        girders[f"G{gi}"] = {
            "members": line,
            "nodes": sorted(
                n for e in line for n in members[str(e)]
            ),
            "index": gi,
        }

    # ── results for one load case ────────────────────────────────────────
    lc = geom["loadcase"]
    forces: dict = {lc: {}}
    displacements: dict = {lc: {}}

    comp_stems = ["Vx", "Vy", "Vz", "Mx", "My", "Mz"]
    for tag_str in members:
        n1, n2 = members[tag_str]
        row = {}
        for stem in comp_stems:
            # deterministic, non-zero synthetic values (element-dependent)
            base = 1000.0 * ((int(tag_str) % 7) + 1)
            row[f"{stem}_i"] = base * (1 if stem in ("Vz", "Mz") else -1)
            row[f"{stem}_j"] = -row[f"{stem}_i"]
        forces[lc][tag_str] = row

    for n_str, coord in nodes.items():
        # sag profile: maximum at mid-span
        x = coord[0]
        sag = 0.012 * 4 * x * (span - x) / (span * span)
        displacements[lc][n_str] = {"x": 0.0, "y": -sag, "z": 0.0}

    result_data = {
        "nodes": nodes,
        "members": members,
        "loadcases": [lc],
        "girders": girders,
        "crossbracings": bracing_chains,
        "forces": forces,
        "displacements": displacements,
        "force_components": [f"{s}_{e}" for s in comp_stems for e in ("i", "j")],
        "disp_components": ["x", "y", "z"],
    }
    return result_data, geom


def _frange(start, stop, step):
    x = start
    while x < stop - 1e-9:
        yield round(x, 6)
        x += step


@pytest.fixture(scope="module")
def result_data():
    data, _geom = _build_result_data()
    return data


@pytest.fixture(scope="module")
def geom():
    _data, geom = _build_result_data()
    return geom


# ─────────────────────────────────────────────────────────────────────────────
# Classification — transverse vs longitudinal tags
# ─────────────────────────────────────────────────────────────────────────────

class TestOrientationClassification:
    def test_disjoint_and_complete(self, result_data):
        nodes = result_data["nodes"]
        members = result_data["members"]
        longitudinal, transverse = classify_longitudinal_transverse(nodes, members)

        assert longitudinal and transverse
        assert not (longitudinal & transverse)
        assert longitudinal | transverse == {int(t) for t in members}

    def test_longitudinal_tags_follow_girder_map(self, result_data):
        longitudinal = longitudinal_element_tags(result_data)
        expected = set()
        for g in result_data["girders"].values():
            expected.update(g["members"])
        assert expected
        assert expected <= longitudinal

    def test_transverse_tags_disjoint_from_longitudinal(self, result_data):
        transverse = transverse_element_tags(result_data)
        longitudinal = longitudinal_element_tags(result_data)
        assert transverse, "transverse extraction must not be empty"
        assert longitudinal, "longitudinal extraction must not be empty"
        assert not (transverse & longitudinal), (
            "transverse element tags must be disjoint from longitudinal tags"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Unified transverse chains (End Diaphragms + Intermediate Cross Bracings)
# ─────────────────────────────────────────────────────────────────────────────

class TestTransverseChains:
    def test_non_empty_and_sorted(self, result_data, geom):
        chains = get_transverse_member_chains(result_data)
        assert chains, "transverse member chains must not be empty"

        stations = [c["x_station"] for c in chains]
        assert stations == sorted(stations)

        # Expected station count: intermediate bracings at every cb_spacing
        # station + 2 end-diaphragm planes, each with (n_girders - 1) pairs.
        n_pairs = geom["n_girders"] - 1
        intermediate = len({round(x, 3) for x in stations
                            if 1e-9 < x < geom["span"] - 1e-9})
        end_planes = len({round(x, 3) for x in stations
                          if x <= 1e-9 or x >= geom["span"] - 1e-9})
        assert intermediate >= 1
        assert end_planes == 2
        assert len(chains) == (intermediate + end_planes) * n_pairs

    def test_end_diaphragms_and_bracings_unified(self, result_data, geom):
        chains = get_transverse_member_chains(result_data)
        kinds = {c["kind"] for c in chains}
        assert kinds == {END_DIAPHRAGM_LABEL, INTERMEDIATE_BRACING_LABEL}

        diaphragms = [c for c in chains if c["kind"] == END_DIAPHRAGM_LABEL]
        assert all(
            c["x_station"] <= 1e-9 or c["x_station"] >= geom["span"] - 1e-9
            for c in diaphragms
        )
        bracings = [c for c in chains if c["kind"] == INTERMEDIATE_BRACING_LABEL]
        assert all(
            1e-9 < c["x_station"] < geom["span"] - 1e-9 for c in bracings
        )

    def test_single_component_no_diagonal_chord_split(self, result_data):
        """Every chain is a single member — diagonals/chords never separated."""
        chains = get_transverse_member_chains(result_data)
        assert all(len(c["members"]) == 1 for c in chains)

    def test_girder_pairs_labelled(self, result_data, geom):
        chains = get_transverse_member_chains(result_data)
        expected_pairs = {
            f"G{i}-G{i + 1}" for i in range(1, geom["n_girders"])
        }
        for c in chains:
            assert f"{c['left_girder']}-{c['right_girder']}" in expected_pairs
        assert expected_pairs == {
            f"{c['left_girder']}-{c['right_girder']}" for c in chains
        }


# ─────────────────────────────────────────────────────────────────────────────
# Series extraction (forces + deflections) for the selected load case
# ─────────────────────────────────────────────────────────────────────────────

class TestSeriesExtraction:
    def test_force_series_non_empty_all_components(self, result_data, geom):
        lc = geom["loadcase"]
        for plot_key, stem in TRANSVERSE_FORCE_COMPONENTS.items():
            series = extract_transverse_force_series(result_data, lc, stem)
            assert series, f"force series for {plot_key} ({stem}) is empty"
            assert all(e["value_i"] is not None for e in series)
            # i/j stored in opposite senses (local frame equilibrium)
            assert all(
                abs(e["value_i"] + e["value_j"]) < 1e-6 for e in series
            )

    def test_force_series_values_match_members_table(self, result_data, geom):
        lc = geom["loadcase"]
        series = extract_transverse_force_series(result_data, lc, "Vz")
        entry = series[0]
        tag = str(entry["member"])
        expected_i = result_data["forces"][lc][tag]["Vz_i"]
        assert entry["value_i"] == expected_i

    def test_displacement_series_non_empty(self, result_data, geom):
        lc = geom["loadcase"]
        series = extract_transverse_displacement_series(result_data, lc, "dy")
        assert series
        assert all(e["value_start"] is not None for e in series)

    def test_unknown_loadcase_yields_empty(self, result_data):
        assert extract_transverse_force_series(result_data, "nope", "Vz") == []
        assert (
            extract_transverse_displacement_series(result_data, "nope", "dy") == []
        )


class TestExtractTransverseMemberResults:
    def test_full_bundle(self, result_data, geom):
        lc = geom["loadcase"]
        res = extract_transverse_member_results(result_data, lc)
        assert res is not None
        xs, bmd, sfd, defl, all_data = res

        assert len(xs) > 0
        assert len({len(xs), len(bmd), len(sfd), len(defl)}) == 1
        assert xs[0] == pytest.approx(0.0)
        assert xs[-1] == pytest.approx(geom["span"])

        # Every required component is pulled (Fx, Vy, Vz, Tx, My, Mz, defl).
        for key in ("Fx_i", "Vy_i", "Vz_i", "Tx_i", "My_i", "Mz_i"):
            assert key in all_data, f"missing {key}"
            assert len(all_data[key]) == len(xs)
            assert any(abs(v) > 0 for v in all_data[key])
        # Brief naming aliases point at the same arrays
        for key in ("Fx", "Vy", "Vz", "Tx", "My", "Mz"):
            assert all_data[key] is all_data[f"{key}_i"]
        for key in ("dx", "dy", "dz"):
            assert key in all_data

    def test_unit_conversion(self, result_data, geom):
        """N → kN for forces, m → mm for deflections."""
        lc = geom["loadcase"]
        res = extract_transverse_member_results(result_data, lc)
        xs, _bmd, _sfd, _defl, all_data = res

        # Pick the station of xs[1] and compare the governing Vz ordinate.
        station = round(float(xs[1]), 6)
        raw = [
            e["value_i"] for e in extract_transverse_force_series(result_data, lc, "Vz")
            if round(e["x"], 6) == station
        ]
        expected_kn = max(raw, key=abs) / 1000.0
        assert all_data["Vz_i"][1] == pytest.approx(expected_kn)

        # Deflection at the same station, converted m → mm (sign flipped for sag
        # is NOT applied here — extract returns the stored sense).
        disp = extract_transverse_displacement_series(result_data, lc, "dy")
        raw_d = [e["value_start"] for e in disp if round(e["x"], 6) == station]
        expected_mm = max(raw_d, key=abs) * 1000.0
        assert all_data["dy"][1] == pytest.approx(expected_mm)

    def test_empty_data_returns_none(self):
        assert extract_transverse_member_results({}, "lc") is None
        assert extract_transverse_member_results({"crossbracings": []}, "lc") is None


# ─────────────────────────────────────────────────────────────────────────────
# Graph-engine member-selection API
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphEngineTransverse:
    def _engine(self, result_data):
        from types import SimpleNamespace

        from osdagbridge.core.bridge_types.plate_girder.analysis_results import (
            PlateGirderAnalysisResults,
        )
        from osdagbridge.core.bridge_types.plate_girder.graph_engine import (
            GirderGraphEngine,
        )

        bridge = SimpleNamespace(result_data=result_data)
        handler = PlateGirderAnalysisResults(dataset=None, bridge=bridge)
        return GirderGraphEngine(
            figure=None, ax_scheme=None, ax_bmd=None, ax_sfd=None,
            ax_defl=None, result_handler=handler,
        )

    def test_get_member_keys_includes_transverse(self, result_data, geom):
        engine = self._engine(result_data)
        keys = engine.get_member_keys()
        assert TRANSVERSE_MEMBERS_LABEL in keys
        assert keys[-1] == TRANSVERSE_MEMBERS_LABEL
        # engine.get_girder_keys() stays longitudinal-only
        assert TRANSVERSE_MEMBERS_LABEL not in engine.get_girder_keys()

    def test_extract_member_results_routes_through_results_data(
        self, result_data, geom
    ):
        engine = self._engine(result_data)
        res = engine.extract_member_results(
            TRANSVERSE_MEMBERS_LABEL, geom["loadcase"]
        )
        assert res is not None
        xs, bmd, sfd, defl, all_data = res
        assert len(xs) > 0
        assert "Vz_i" in all_data and "Tx_i" in all_data and "dy" in all_data

    def test_extract_reactions_none_for_transverse(self, result_data, geom):
        engine = self._engine(result_data)
        reactions = engine.extract_reactions(geom["loadcase"], TRANSVERSE_MEMBERS_LABEL)
        assert reactions == {"Ra": None, "Rb": None}

    def test_is_transverse_member_key(self, result_data):
        engine = self._engine(result_data)
        assert engine.is_transverse_member_key(TRANSVERSE_MEMBERS_LABEL)
        assert not engine.is_transverse_member_key("G1")


# ─────────────────────────────────────────────────────────────────────────────
# Figure builders (matplotlib Agg + plotly)
# ─────────────────────────────────────────────────────────────────────────────

class TestFigureBuilders:
    def test_matplotlib_transverse_figure(self, result_data, geom):
        import matplotlib
        matplotlib.use("Agg", force=True)
        from osdagbridge.core.bridge_types.plate_girder.plot_generator import (
            build_figure_transverse_members,
        )

        fig, summary = build_figure_transverse_members(
            result_data, geom["loadcase"], "Fz",
            result_data["nodes"], result_data["members"],
            diagram_kind="force",
        )
        assert fig is not None
        assert summary, "per-girder-pair summary must not be empty"
        assert "G1-G2" in summary
        fig.canvas.draw()  # force a full Agg render

    def test_matplotlib_sfd_routes_to_transverse(self, result_data, geom):
        import matplotlib
        matplotlib.use("Agg", force=True)
        from osdagbridge.core.bridge_types.plate_girder.plot_generator import (
            build_figure_sfd,
        )

        fig, summary = build_figure_sfd(
            None, "Fz", result_data["nodes"], result_data["members"],
            selected_girder=TRANSVERSE_MEMBERS_LABEL,
            result_data=result_data, loadcase=geom["loadcase"],
        )
        assert TRANSVERSE_MEMBERS_LABEL in fig.axes[0].get_title()
        assert summary

    def test_plotly_transverse_figure(self, result_data, geom):
        pytest.importorskip("plotly")
        from osdagbridge.core.bridge_types.plate_girder.plots_widget import (
            build_figure_transverse_members as plotly_transverse,
        )

        payload = plotly_transverse(
            result_data, geom["loadcase"], "Fz",
            result_data["nodes"], result_data["members"],
        )
        assert isinstance(payload, str)
        assert TRANSVERSE_MEMBERS_LABEL in payload

    def test_plotly_hover_text_names_the_member(self, result_data, geom):
        """Regression: hover text must use entry['member'] (NameError guard)."""
        pytest.importorskip("plotly")
        import json

        from osdagbridge.core.bridge_types.plate_girder.plots_widget import (
            build_figure_transverse_members as plotly_transverse,
        )

        payload = plotly_transverse(
            result_data, geom["loadcase"], "Mz",
            result_data["nodes"], result_data["members"],
        )
        fig = json.loads(payload)
        texts = [t.get("text") for t in fig["data"] if t.get("text")]
        # plotly serialises per-point hover text as a list of strings
        hover_texts = [
            item
            for entry in texts
            for item in (entry if isinstance(entry, list) else [entry])
        ]
        assert hover_texts, "hover texts must exist"
        joined = "".join(hover_texts)
        assert "End Diaphragm" in joined or "Intermediate Cross Bracing" in joined
        # The element tag is part of the hover text (was a NameError before).
        assert any(
            f"{e['kind']} {e['member']}" in joined
            for e in extract_transverse_force_series(
                result_data, geom["loadcase"], "Mz"
            )
        )

    def test_matplotlib_deflection_routes_to_transverse(self, result_data, geom):
        import matplotlib
        matplotlib.use("Agg", force=True)
        from osdagbridge.core.bridge_types.plate_girder.plot_generator import (
            build_figure_deflection,
        )

        fig, summary = build_figure_deflection(
            None, "Dy", result_data["nodes"], result_data["members"],
            selected_girder=TRANSVERSE_MEMBERS_LABEL,
            result_data=result_data, loadcase=geom["loadcase"],
        )
        assert TRANSVERSE_MEMBERS_LABEL in fig.axes[0].get_title()
        assert summary
        fig.canvas.draw()  # force a full Agg render


# ─────────────────────────────────────────────────────────────────────────────
# Node/member table normalisation (int- vs str-keyed producer conventions)
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizedModelDicts:
    def test_str_keyed_tables_become_int_keyed(self, result_data):
        from osdagbridge.core.bridge_types.plate_girder.results_data import (
            normalized_model_dicts,
        )

        nodes_n, members_n = normalized_model_dicts(
            result_data["nodes"], result_data["members"]
        )
        # restructure_data convention: str keys, int connectivity values
        assert all(isinstance(k, int) for k in nodes_n)
        assert all(isinstance(k, int) for k in members_n)
        for conn in members_n.values():
            assert all(isinstance(n, int) for n in conn)
        # round trip: same coordinates / connectivity
        assert nodes_n[1] == result_data["nodes"]["1"]
        assert members_n[1] == [
            int(n) for n in result_data["members"]["1"]
        ]

    def test_int_keyed_tables_pass_through(self, result_data):
        from osdagbridge.core.bridge_types.plate_girder.results_data import (
            normalized_model_dicts,
        )

        int_nodes = {int(k): v for k, v in result_data["nodes"].items()}
        int_members = {
            int(k): [int(n) for n in v] for k, v in result_data["members"].items()
        }
        nodes_n, members_n = normalized_model_dicts(int_nodes, int_members)
        assert nodes_n == int_nodes
        assert members_n == int_members

    def test_garbage_and_empty_inputs(self):
        from osdagbridge.core.bridge_types.plate_girder.results_data import (
            normalized_model_dicts,
        )

        assert normalized_model_dicts(None, None) == ({}, {})
        assert normalized_model_dicts({}, {}) == ({}, {})
        # non-numeric keys/values survive untouched
        nodes_n, members_n = normalized_model_dicts(
            {"a": [0, 0, 0]}, {"b": ["x", "y"]}
        )
        assert nodes_n == {"a": [0, 0, 0]}
        assert members_n == {"b": ["x", "y"]}
