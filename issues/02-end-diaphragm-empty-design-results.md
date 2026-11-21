# [Bug] End diaphragms are never designed: `end_diaphragm_design_results` is empty for every girder pair because the force extraction reads `Vz_i`, which is 0.0 on the support-line members (transverse shear is reported in `Vy_i`)

**Severity:** High (functional — a full component of the bridge has no design output; report tables are empty and the executive summary omits end-diaphragm utilization)

**Component:** Core — `src/osdagbridge/core/bridge_types/plate_girder/plategirderbridge.py::_design_end_diaphragm_members` (stage 7)

## Environment

- OsdagBridge commit `d74f56d` (branch `task/software-testing`)
- Default configuration: 30 m span, 7.5 m carriageway, 4 girders @ 2.1 m, deck overhang 1.05 m, E 350A / M40, Optimized
- End diaphragms **fully configured** in Additional Inputs → Transverse Member Design (type `Cross Bracing`, X-bracing, top+bottom chords for every pair, both member slots E{n}M1/E{n}M2)

## Steps to reproduce

1. Run the default design (headless below; identical through the GUI):

```python
from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import PlateGirderBridge
b = PlateGirderBridge(); b.set_input(input_dict); b.design()
```

2. Inspect the output:

```python
od = dict(b.output_dict)
od["end_diaphragm_design_results"]     # {'G1-G2': {}, 'G2-G3': {}, 'G3-G4': {}}
od["end_diaphragm_forces_dict"]["pairs"]  # every force is None
```

3. Reproduction script with hard numbers: `scripts/verify_ed_forces.py` in the task branch.

## Expected

Design forces (tension/compression envelopes for diagonal + chord) are extracted from the analysis for every support-line girder pair, Osdag member designs run, and `end_diaphragm_design_results` contains `{pair: {diagonal/chord: {tension/compression: result}}}` — as happens for the intermediate cross bracings.

## Actual

```
end_diaphragm_design_results = {'G1-G2': {}, 'G2-G3': {}, 'G3-G4': {}}
end_diaphragm_forces_dict['pairs'] = {
  'G1-G2': {'diag_tension_kN': None, 'diag_compression_kN': None,
            'chord_tension_kN': None, 'chord_compression_kN': None, ...},
  ... same for every pair ...}
```

No design forces are ever collected, no member designs run, the report's "End Diaphragm Design — Capacity Summary" tables are empty, and the executive summary silently omits end-diaphragm utilization.

## Proof / logs

`scripts/verify_ed_forces.py` dumps, per support-line element, the max |Vz_i| and max |Vy_i| over every load case after a default run:

```
=== PER-ELEMENT support-line transverse members (start+end edges) ===
  elem    2: max|Vz_i| =   0.000 kN   max|Vy_i| = 126.175 kN   (Vz_i gov LC: None)
  elem    3: max|Vz_i| =   0.000 kN   max|Vy_i| =   0.000 kN   (Vz_i gov LC: None)
  elem    4: max|Vz_i| =   0.000 kN   max|Vy_i| = 126.175 kN   (Vz_i gov LC: None)
  elem  216: max|Vz_i| =   0.000 kN   max|Vy_i| =  99.966 kN   (Vz_i gov LC: None)
  elem  217: max|Vz_i| =   0.000 kN   max|Vy_i| =   0.000 kN   (Vz_i gov LC: None)
  elem  218: max|Vz_i| =   0.000 kN   max|Vy_i| =  99.966 kN   (Vz_i gov LC: None)

=== SUPPORT-LINE (start_edge) transverse members — ED stage input ===
  max |Vy_i| = 213.689 kN  (LC ACCIDENTAL_1: 1.0DL + 1.0DW + 0.75LL)
  max |Vz_i| =  19.943 kN  (LC 1.5 EQ (b))     ← only on the outermost members
```

The elements mapped to girder pairs (2/216, 3/217, 4/218 — the interior support-line diaphragm members) have **`Vz_i ≡ 0.000 kN in every load case`**, while their transverse shear (up to **126 kN**, governed by gravity/live combinations) is reported in **`Vy_i`**. (The outermost support members 1/5/215/219 do show non-zero `Vz_i`, but they connect the edge beams and are not mapped to any girder pair.)

## Root cause

`plategirderbridge.py:2728` (`_design_end_diaphragm_members`) reads only the `Vz_i` component from the results dataset:

```python
vz_i = self.result_data["forces"][lc_str][m].get("Vz_i")
if vz_i is None:
    continue
vz_kn = vz_i / 1000.0
f_diag = vz_kn / cos_alpha
f_chord = vz_kn
```

`Vz_i`/`Vy_i` are **local-axis** components of the grillage beam elements (ospgrillage local axes). For the support-line transverse members the local axes are oriented such that the vertical (design) shear is reported in `Vy_i`; `Vz_i` is identically zero there. The tolerance gate then nulls every force:

```python
pair_forces = {
    "diag_tension_kN": round(diag_tens_max, 3) if diag_tens_max > _tol else None,
    ...
}
```

so `jobs` stays empty and `pair_designs[pair]` remains `{}`.

Related (same local-axis trap, one severity lower): the intermediate **cross-bracing** stage (`crossbracingforces.py:326-343 _read_vz`, used by `_design_cross_bracing_members`) also reads only `Vz_i`; on the intermediate transverse lines `Vz_i` is non-zero **only for the transverse-seismic cases** (governing LCs of the default run are all `1.5 EQ (a)/(b)`, diag forces ≈ 4.5-6.0 kN), while the much larger gravity/live transverse shears on those members live in `Vy_i` and are never considered for the bracing design.

## Suggested fix

Read the component that actually carries the transverse shear, with a fallback so both element orientations work. In `_design_end_diaphragm_members` (plategirderbridge.py, around line 2728):

```python
f = self.result_data["forces"][lc_str][m]
# Support-line transverse members report the vertical (design) shear in
# Vy_i (local axes); Vz_i is 0.0 there.  Use the larger-magnitude of the
# two local shears as the diaphragm shear, mirroring the sign convention.
vz_i = f.get("Vz_i")
vy_i = f.get("Vy_i")
cands = [v for v in (vz_i, vy_i) if v is not None]
if not cands:
    continue
shear_n = max(cands, key=abs)          # transverse shear at the i-end
vz_kn = shear_n / 1000.0
f_diag = vz_kn / cos_alpha
f_chord = vz_kn
```

(The same change applies to `CrossBracingForces._read_vz` in `crossbracingforces.py:326` so intermediate bracings are designed for the governing gravity case, not only the seismic cases; the sign/tension-compression convention noted in the module TODO must be re-validated against a hand calculation.)

**Verification after the fix** (already pinned in the test-suite, will start failing = bug fixed):

- `tests/functional/test_additional_inputs.py::TestEndDiaphragmAdditionalInputs::test_ed_design_forces_all_none`
- `tests/functional/test_additional_inputs.py::TestEndDiaphragmAdditionalInputs::test_ed_design_results_empty_despite_configuration`
- `tests/unit/test_output_consistency.py::TestComponentCoverage::test_end_diaphragm_design_results_present`
