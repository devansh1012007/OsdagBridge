# [Bug] Design-time validation does not enforce the documented input ranges: spans of 19 m / 46 m / 0.5 m / 100 m run through the whole pipeline, and non-numeric values surface as raw `ValueError`s with no field context

**Severity:** Medium (robustness / silent wrong results — out-of-scope inputs produce a full "design" instead of being rejected)

**Component:** Core — `src/osdagbridge/core/bridge_types/plate_girder/plategirderbridge.py::_validate_inputs` (design() stage 1)

## Environment

- OsdagBridge commit `d74f56d` (branch `task/software-testing`)
- Headless API path (`PlateGirderBridge.set_input()` + `design()`), which is also the path used by any future CLI/web/API consumer and by hand-edited `.osi` files that pass the load-time validator

## Steps to reproduce

```python
from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import PlateGirderBridge

for span in (19.0, 46.0, 0.5, 100.0):        # documented scope: 20–45 m
    b = PlateGirderBridge()
    b.set_input({**default_input_dict, "geometry.span": span})
    b._validate_inputs()                      # ← does NOT raise
    print(span, "accepted")

b = PlateGirderBridge()
b.set_input({**default_input_dict, "geometry.span": "abc"})
b._validate_inputs()
# ValueError: could not convert string to float: 'abc'
```

(The full pipeline also runs to completion for 19 m / 46 m / 0.5 m / 100 m — verified live.)

## Expected

`design()` stage 1 rejects inputs outside the software scope with a clear, field-labelled message — the same rules the GUI enforces live:

- Span: 20–45 m (`SPAN_MIN`/`SPAN_MAX`, `core/utils/common.py:325-326`, "software limitation")
- Carriageway width: IRC 5 Cl. 104.3.1 minimum (4.25 m single-lane / 7.5 m with median) and 23.6 m cap
- Skew angle: ±15° (IRC 24 Cl. 504.8)
- Non-numeric values → "Span must be a numeric value." style message naming the field

## Actual

`_validate_inputs` (plategirderbridge.py:599-620) checks only:

```python
missing = [k for k in required_keys if k not in inp or inp[k] is None or str(inp[k]).strip() == ""]
span = float(inp[KEY_SPAN])          # ← raises bare "could not convert string to float" for "abc"
if span <= 0: ...
n_girders = int(inp[KEY_TS_NO_OF_GIRDERS]);  if n_girders < 2: ...
spacing = float(inp[KEY_TS_GIRDER_SPACING]); if spacing <= 0: ...
```

- **No span-range check** (19 m, 46 m, 0.5 m, 100 m all pass; the 20–45 m scope is enforced *only* by the GUI field validator and by `osi_validator` on file load).
- **No carriageway / skew / material checks at all** at design time.
- **Non-numeric span** bypassing the GUI (hand-edited `.osi`, API call) crashes with the raw, field-less `ValueError: could not convert string to float: 'abc'` from the `float()` above instead of a validation message. (Note `set_input()`'s `_coerce` leaves non-numeric strings untouched by design.)
- Carriageway `0.0` is likewise not caught at the gate; it reaches the layout solver, which raises a late and unrelated-looking spacing error (`ValueError: ... below the minimum`).

## Root cause

`plategirderbridge.py:599-620` — `_validate_inputs` re-implements a *much* weaker subset of the rules that already exist in `BridgeInputValidator.validate_basic_inputs` (`core/bridge_types/plate_girder/validator.py:18-70`) and `validate_osi_inputs` (`core/utils/osi_validator.py`). The GUI and the file-load path call those validators; the design pipeline itself never does, so any other entry point (API/CLI/hand-edited input) silently loses the protection.

## Suggested fix

Run the shared validator inside the design gate and raise field-labelled errors:

```python
def _validate_inputs(self):
    """Perform strict validation on essential input dictionary keys."""
    from osdagbridge.core.bridge_types.plate_girder.validator import BridgeInputValidator
    from osdagbridge.core.utils.common import (
        KEY_SPAN, KEY_TS_OVERALL_WIDTH, KEY_TS_NO_OF_GIRDERS, KEY_TS_GIRDER_SPACING)

    inp = self.input_dict
    required = [KEY_SPAN, KEY_TS_OVERALL_WIDTH, KEY_TS_NO_OF_GIRDERS, KEY_TS_GIRDER_SPACING]
    missing = [k for k in required if k not in inp or inp[k] is None or str(inp[k]).strip() == ""]
    if missing:
        raise ValueError(f"Missing required input parameters: {', '.join(missing)}")

    # Re-use the GUI/load-time rules so every entry point is protected.
    v = BridgeInputValidator()
    for key in (KEY_SPAN, KEY_CARRIAGEWAY_WIDTH, KEY_SKEW_ANGLE):
        result = v.validate_basic_inputs(key, inp)
        if result is not None:                      # (corrected_value, message)
            corrected, message = result
            raise ValueError(f"Invalid input '{key}' = {inp.get(key)!r}: {message} "
                             f"(suggested value: {corrected})")

    if float(inp[KEY_SPAN]) <= 0:
        raise ValueError(f"Span must be strictly positive, got {inp[KEY_SPAN]}.")
    if int(inp[KEY_TS_NO_OF_GIRDERS]) < 2:
        raise ValueError(f"Minimum 2 girders required, got {inp[KEY_TS_NO_OF_GIRDERS]}.")
    if float(inp[KEY_TS_GIRDER_SPACING]) <= 0:
        raise ValueError(f"Girder spacing must be positive, got {inp[KEY_TS_GIRDER_SPACING]}.")
```

**Verification** (currently pinning the gap; the two "documents gap" tests must be inverted when the fix lands):

- `tests/unit/test_input_validation.py::TestDesignTimeValidation::test_design_gate_does_not_enforce_span_scope`
- `tests/unit/test_input_validation.py::TestDesignTimeValidation::test_design_gate_non_numeric_span_raises_cryptic_valueerror`
- `tests/unit/test_input_validation.py::TestOsiValidator` (the load-time rules that should be shared)
