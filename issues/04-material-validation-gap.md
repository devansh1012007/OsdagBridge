# [Bug] `validate_material_inputs()` ignores the `material.cross_bracing.*` / `material.end_diaphragm.*` keys — custom bracing/diaphragm material properties are accepted with **any** value (garbage strings, negatives, 10× out-of-range) on every non-GUI path

**Severity:** Low–Medium (the GUI is protected only because it validates the girder-*template* keys *before* remapping them to member prefixes; the headless API / OSI file-load / future-CLI paths get no material range checking at all, and the unvalidated values are echoed into `output_dict` and the design report as if they were valid)

**Component:** Core — `src/osdagbridge/core/bridge_types/plate_girder/validator.py::validate_material_inputs`; key constants in `src/osdagbridge/core/utils/common.py:76-90`

## Environment

- OsdagBridge commit `d74f56d` (branch `task/software-testing`)
- Any entry point that writes member-prefixed material keys directly: `PlateGirderBridge.set_input()`, `.osi` project files, future CLI/web API

## Steps to reproduce

```python
from osdagbridge.core.bridge_types.plate_girder.validator import BridgeInputValidator

v = BridgeInputValidator()
for key in ("material.cross_bracing.fy", "material.end_diaphragm.fy",
            "material.cross_bracing.poisson", "material.end_diaphragm.e"):
    for bad in (99999.0, -50.0, "garbage"):
        print(key, repr(bad), "->", v.validate_material_inputs(key, {key: bad}))
```

## Expected

The same range rules that protect `material.girder.*` (Fy 100–1200 MPa, Fu 100–1500 MPa, E 100–300 GPa, G 30–120 GPa, ν 0–0.5, density 50–120 kN/m³, thermal 1–30 ×10⁻⁶/°C — `validator.py:85-131`) apply to the other two steel members, because the Material Properties dialog explicitly supports selecting **Cross Bracing** and **End Diaphragm** materials and exports exactly these keys (`material.cross_bracing.fy`, `material.end_diaphragm.fu`, …).

## Actual

Every call returns `None` (= "valid, no correction"):

```
material.cross_bracing.fy 99999.0  -> None
material.cross_bracing.fy -50.0    -> None
material.cross_bracing.fy 'garbage'-> None
material.end_diaphragm.fy 99999.0  -> None
material.cross_bracing.poisson -50.0 -> None
material.end_diaphragm.e 99999.0   -> None
```

Out-of-range, negative, and **non-numeric** values are all accepted verbatim; `set_input()`'s `_coerce` leaves `"garbage"` as a string, and the value is then echoed into `output_dict` (`material.cross_bracing.fy = 'garbage'`) and rendered in the Chapter-2 "Member Properties: Cross Bracing Details" report table.

## Root cause (file:line)

`BridgeInputValidator.validate_material_inputs` (`validator.py:78-168`) is a chain of `if key == KEY_MATERIAL_GIRDER_*` / `elif key == KEY_MATERIAL_DECK_*` branches and falls through to `return None` for every other key. The member-prefixed constants **were defined** —

```python
# core/utils/common.py:76-90
KEY_MATERIAL_CROSS_BRACING_FY  = "material.cross_bracing.fy"
KEY_MATERIAL_CROSS_BRACING_FU  = "material.cross_bracing.fu"
...
KEY_MATERIAL_END_DIAPHRAGM_FY  = "material.end_diaphragm.fy"
...
```

— but no branch in the validator references them (grep: the only consumers of these constants in `src/` are none; only the test-suite imports them). `validate_osi_inputs` (`core/utils/osi_validator.py`) contains no material validation either, so the file-load path does not close the gap.

Why the GUI still works: `MaterialPropertiesDialog._validate_and_save()` / `_on_material_field_edited()` (`desktop/ui/dialogs/material_properties.py:348,370`) validate the **girder-template field keys** (`material.girder.fy`, …) while editing, and only `get_export_fields()` (`material_properties.py:578`) remaps them to the member prefix (`material.cross_bracing.fy`) at export time. The protection is therefore an accident of the dialog's internal key naming; every other writer of these keys bypasses it.

## Suggested fix

Validate by *property suffix* for the three steel members instead of by hard-coded girder keys:

```python
# validator.py — replace the steel branches of validate_material_inputs()
_STEEL_MEMBERS = ("girder", "cross_bracing", "end_diaphragm")
_STEEL_RANGES = {          # property suffix -> (min, max, label, unit)
    "density": (50.0, 120.0, "Weight Density", "kN/m³"),
    "fy":      (100.0, 1200.0, "Yield Strength, Fy", "MPa"),
    "fu":      (100.0, 1500.0, "Ultimate Tensile Strength, Fu", "MPa"),
    "e":       (100.0, 300.0, "Modulus of Elasticity, E", "GPa"),
    "g":       (30.0, 120.0, "Modulus of Rigidity, G", "GPa"),
    "poisson": (0.0, 0.5, "Poisson's Ratio", ""),
    "thermal": (1.0, 30.0, "Thermal Expansion Coefficient", "×10⁻⁶/°C"),
}

prefix, _, prop = key.rpartition(".")            # e.g. 'material.cross_bracing', 'fy'
member = prefix.removeprefix("material.")
if member in _STEEL_MEMBERS and prop in _STEEL_RANGES:
    lo, hi, label, unit = _STEEL_RANGES[prop]
    v = self._to_float(inputs.get(key))
    if v is None: return lo, f"{label} must be a numeric value."
    if v < lo:    return lo, f"{label} must be between {lo} and {hi} {unit}."
    if v > hi:    return hi, f"{label} must be between {lo} and {hi} {unit}."
    return None
# ... deck branches unchanged (single member) ...
```

(This keeps the girder/deck behaviour byte-identical — the girder row of the table is the same ranges — while extending it to the two other steel members the dialog already exports.)

**Verification** (currently pinning the gap; must be inverted when the fix lands):

- `tests/unit/test_input_validation.py::TestMaterialValidation::test_cross_bracing_and_end_diaphragm_keys_are_not_validated`

Related but separate: design-time validation gaps for *geometry* keys are drafted in `03-design-time-validation-gaps.md`; this draft covers only the material member keys.
