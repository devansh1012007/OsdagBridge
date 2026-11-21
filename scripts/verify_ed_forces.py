"""Verify the end-diaphragm force-extraction defect with hard numbers.

After a default 30 m design run, dumps for (a) the support-line transverse
members used by the ED stage and (b) the intermediate cross-bracing members:
the max |Vz_i| and max |Vy_i| across every load case, to prove which force
component actually carries the transverse shear.

Usage:  python scripts/verify_ed_forces.py   (repo root is derived from this
file's location; set OSDAG_STUBS to point at an osdag_core stub/conda install
if the real Osdag package is not installed).
"""
import os, sys

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get('OSDAG_STUBS', '/home/z/my-project/stubs'))
sys.path.insert(0, os.path.join(_REPO, 'src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MPLBACKEND'] = 'Agg'

from osdagbridge.core.bridge_types.plate_girder.defaults import (
    BASIC_INPUT_DICT, solve_extend_basic_input_dict)
from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import PlateGirderBridge

d = dict(BASIC_INPUT_DICT)
d['geometry.span'] = 30.0
d['geometry.carriageway_width'] = 7.5
d['geometry.skew_angle'] = 0.0
d['project.location'] = 'Mumbai'
solve_extend_basic_input_dict(d)
STEEL = {'fy': 350.0, 'fu': 490.0, 'e': 200.0, 'g': 76.9, 'poisson': 0.30}
for member in ('girder', 'cross_bracing', 'end_diaphragm'):
    d[f'material.{member}.density'] = 76.4
    for k, v in STEEL.items():
        d[f'material.{member}.{k}'] = v
    d[f'material.{member}.thermal'] = 0.000012
d['material.deck.fck'] = 40.0; d['material.deck.fctm'] = 3.0
d['material.deck.ecm'] = 33.0; d['material.deck.thermal'] = 0.00001
d['material.deck.density'] = 24.5

b = PlateGirderBridge()
b.set_input(d)
b.design()

rd = b.result_data
model = b.grillage_model.model

# --- replicate the ED stage's pair_to_elements mapping exactly ---
start_elements = [str(e) for e in model.get_element(member="start_edge", options="elements")]
end_elements = [str(e) for e in model.get_element(member="end_edge", options="elements")]
all_edge_elements = start_elements + end_elements

girders = rd.get("girders", {})
girder_node_sets = {g: set(gd.get("nodes", [])) for g, gd in girders.items()}
print("result_data['girders'] keys:", list(girders))
print("girder indexes:", {g: gd.get("index") for g, gd in girders.items()})

def _find_girder(node):
    for g, ns in girder_node_sets.items():
        if node in ns:
            return g
    return None

pair_to_elements = {}
for m in all_edge_elements:
    if m not in rd.get("members", {}):
        continue
    n1, n2 = rd["members"][m]
    g1, g2 = _find_girder(n1), _find_girder(n2)
    if g1 and g2 and g1 != g2:
        idx1, idx2 = girders[g1].get("index", 0), girders[g2].get("index", 0)
        pair = f"{g1}-{g2}" if idx1 <= idx2 else f"{g2}-{g1}"
        pair_to_elements.setdefault(pair, []).append(m)
print("pair_to_elements:", pair_to_elements)
edge_in_members = [m for m in all_edge_elements if m in rd.get("members", {})]
print(f"edge elements: {len(all_edge_elements)}, present in result_data['members']: {len(edge_in_members)}")
missed = [m for m in all_edge_elements if m not in rd.get("members", {})]
print("edge elements MISSING from result_data['members']:", missed)
# what do the missing ones connect?
for m in missed[:6]:
    print(f"  elem {m}: forces records?",
          [lc for lc in list(rd['forces'])[:3] if m in rd['forces'][lc]])

try:
    inter = [str(e) for e in model.get_element(member="cross_bracing", options="elements")]
except Exception as exc:
    inter = []
    print("(no cross_bracing member group:", exc, ")")

def component_stats(elements, label):
    print(f"\n=== {label} ({len(elements)} elements) ===")
    forces = rd["forces"]
    agg = {}
    for lc, members in forces.items():
        for m in elements:
            f = members.get(m)
            if not f:
                continue
            for comp in ("Vz_i", "Vy_i", "Vz_j", "Vy_j", "Vy"):
                v = f.get(comp)
                if v is None:
                    continue
                cur = agg.setdefault(comp, [0.0, None])
                if abs(v) > abs(cur[0]):
                    cur[0] = v
                    cur[1] = lc
    for comp in sorted(agg):
        v, lc = agg[comp]
        print(f"  max |{comp}| = {abs(v)/1000.0:10.3f} kN   (LC {lc})")
    if not agg:
        print("  (no force records)")


def per_element_stats(elements, label):
    print(f"\n=== PER-ELEMENT {label} ===")
    forces = rd["forces"]
    for m in elements:
        row = {"Vz_i": (0.0, None), "Vy_i": (0.0, None)}
        for lc, members in forces.items():
            f = members.get(m)
            if not f:
                continue
            for comp in row:
                v = f.get(comp)
                if v is not None and abs(v) > abs(row[comp][0]):
                    row[comp] = (v, lc)
        print(f"  elem {m:>4}: max|Vz_i| = {abs(row['Vz_i'][0])/1000.0:8.3f} kN"
              f"   max|Vy_i| = {abs(row['Vy_i'][0])/1000.0:8.3f} kN"
              f"   (Vz_i gov LC: {row['Vz_i'][1]})")


per_element_stats(start_elements + end_elements,
                  "support-line transverse members (start+end edges)")
mapped = sorted({m for elems in pair_to_elements.values() for m in elems})
per_element_stats(mapped, "MAPPED elements actually used by the ED stage")

component_stats(start_elements, "SUPPORT-LINE (start_edge) transverse members — ED stage input")
component_stats(end_elements, "SUPPORT-LINE (end_edge) transverse members — ED stage input")
component_stats(inter, "INTERMEDIATE cross-bracing members — CB stage input")

print("\n=== end_diaphragm_forces_dict (as stored in output_dict) ===")
edf = dict(b.output_dict).get("end_diaphragm_forces_dict")
print(edf)

print("\n=== crossbracing_forces_dict (pairs, governing LCs) ===")
cbf = dict(b.output_dict).get("crossbracing_forces_dict")
for pair, forces in (cbf or {}).get("pairs", {}).items():
    print(f"  {pair}: " + ", ".join(
        f"{k}={v}" for k, v in forces.items() if k.endswith("gov_lc") or k.endswith("kN")))
