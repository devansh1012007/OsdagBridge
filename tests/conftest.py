"""Shared pytest fixtures for the OsdagBridge plate-girder test-suite.

The fixtures mirror the headless pipeline proven out by
``scripts/smoke_headless.py``:

    BASIC_INPUT_DICT  ->  user geometry values  ->  solve_extend_basic_input_dict()
    ->  material.* keys (Material Properties dialog)  ->  PlateGirderBridge.set_input()
    ->  PlateGirderBridge.design()

Full design runs take ~30 s each, so every fixture that executes ``design()``
is marked ``slow``; select the fast subset with ``-m 'not slow'``.

NOTE ON THE SANDBOX: the real Osdag conda package is not installed here; a
stub at ``/home/z/my-project/stubs/osdag_core`` provides heuristic bracing
sizing.  Cross-bracing / end-diaphragm *capacity* numbers are therefore only
shape-checked (key presence + type), never magnitude-checked.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

# ── make the package importable regardless of invocation directory ──────────
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SRC = os.path.join(_REPO, "src")
for _p in (_SRC, "/home/z/my-project/stubs"):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

# Reference smoke output produced with the *unmodified* baseline code
# (30 m span / 7.5 m carriageway / E350A / M40, 4 girders).
SMOKE_OUTPUT_JSON = "/home/z/my-project/work/shared/smoke_output.json"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: full design-pipeline run (~30 s each); deselect with -m 'not slow'")
    config.addinivalue_line(
        "markers", "gui: test instantiates real Qt widgets (offscreen platform)")
    config.addinivalue_line(
        "markers", "occ: test requires pythonocc-core (CAD solid modelling)")


# ─────────────────────────────────────────────────────────────────────────────
# Input-dict builders (fast — no analysis)
# ─────────────────────────────────────────────────────────────────────────────

def build_basic_input(span=30.0, carriageway_width=7.5, skew=0.0,
                      footpath="None", include_median="No",
                      project_location="Mumbai", girder_grade="E 350A",
                      concrete_grade="M40"):
    """Return an extended basic input dict exactly the way the template page +
    layout solver would leave it (mirrors scripts/smoke_headless.py)."""
    from osdagbridge.core.bridge_types.plate_girder.defaults import (
        BASIC_INPUT_DICT, solve_extend_basic_input_dict)

    d = dict(BASIC_INPUT_DICT)
    d["geometry.span"] = span
    d["geometry.carriageway_width"] = carriageway_width
    d["geometry.skew_angle"] = skew
    d["geometry.footpath"] = footpath
    d["geometry.include_median"] = include_median
    d["project.location"] = project_location
    d["material.girder"] = girder_grade
    d["material.cross_bracing"] = girder_grade
    d["material.end_diaphragm"] = girder_grade
    d["material.deck"] = concrete_grade
    solve_extend_basic_input_dict(d)
    return d


def apply_default_materials(d, steel=None, deck=None):
    """Fill the material.* keys the Material Properties dialog would write.

    ``steel`` / ``deck`` are optional override dicts, e.g.
    ``steel={"fy": 250.0, "fu": 410.0}`` — only overridden keys change.
    """
    steel_full = {"density": 76.4, "fy": 350.0, "fu": 490.0, "e": 200.0,
                  "g": 76.9, "poisson": 0.30, "thermal": 0.000012}
    deck_full = {"fck": 40.0, "fctm": 3.0, "ecm": 33.0,
                 "thermal": 0.00001, "density": 24.5}
    if steel:
        steel_full.update(steel)
    if deck:
        deck_full.update(deck)

    for member in ("girder", "cross_bracing", "end_diaphragm"):
        for prop, value in steel_full.items():
            d[f"material.{member}.{prop}"] = value
    for prop, value in deck_full.items():
        d[f"material.deck.{prop}"] = value
    return d


def make_input(**kwargs) -> dict:
    """One-call helper: basic input + default material properties."""
    return apply_default_materials(build_basic_input(**kwargs))


@pytest.fixture
def make_input_dict():
    """Factory fixture returning fresh input dicts (no design run)."""
    def _factory(**kwargs) -> dict:
        return make_input(**kwargs)
    return _factory


@pytest.fixture
def default_input_dict():
    """Reference input dict: 30 m / 7.5 m / 0° skew / E350A / M40."""
    return make_input()


# ─────────────────────────────────────────────────────────────────────────────
# Reference outputs (fast — loads a JSON produced by the baseline code)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def reference_output():
    """input+output dicts of the baseline 30 m reference design run."""
    if not os.path.exists(SMOKE_OUTPUT_JSON):
        pytest.skip(f"reference smoke output not found: {SMOKE_OUTPUT_JSON}")
    with open(SMOKE_OUTPUT_JSON) as fh:
        return json.load(fh)


# ─────────────────────────────────────────────────────────────────────────────
# Full design runs (slow)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def designed_bridge_default():
    """Session-scoped default design run (30 m / 7.5 m / E350A / M40).

    Reused by every functional output/report test so the ~30 s pipeline
    executes only once per test session.
    """
    from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
        PlateGirderBridge)

    bridge = PlateGirderBridge()
    bridge.set_input(make_input())
    bridge.design()
    return bridge


@pytest.fixture(scope="session")
def custom_material_bridge():
    """Session-scoped design run with fully custom steel + deck materials
    (fy=250 / fu=410 / E=205 / G=79.3 / ν=0.27, deck fck=30 / fctm=2.9 /
    Ecm=32), mirroring the GUI custom-material flow (grades renamed to
    custom_steel_* / custom_concrete_*)."""
    from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import (
        PlateGirderBridge)

    custom_steel = {"fy": 250.0, "fu": 410.0, "e": 205.0, "g": 79.3,
                    "poisson": 0.27, "density": 77.0, "thermal": 0.000012}
    d = make_input(girder_grade="custom_steel_fy250",
                   concrete_grade="custom_concrete_fck30")
    d["material.girder"] = "custom_steel_fy250"
    d["material.cross_bracing"] = "custom_steel_fy250"
    d["material.end_diaphragm"] = "custom_steel_fy250"
    d["material.deck"] = "custom_concrete_fck30"
    for member in ("girder", "cross_bracing", "end_diaphragm"):
        for prop, val in custom_steel.items():
            d[f"material.{member}.{prop}"] = val
    d["material.deck.fck"] = 30.0
    d["material.deck.fctm"] = 2.9
    d["material.deck.ecm"] = 32.0

    bridge = PlateGirderBridge()
    bridge.set_input(d)
    bridge.design()
    return bridge


@pytest.fixture(scope="session")
def default_output(designed_bridge_default):
    """Plain dict snapshot of the default run's output_dict."""
    return dict(designed_bridge_default.output_dict)
