# [Bug] `design_results` status tallies (`overall_status` / `n_pass` / `n_fail` / `max_dcr`) silently exclude the stiffener checks (ids 20/21): a failing intermediate- or bearing-stiffener check never flips the overall verdict — and the shipped default configuration already contains such a hidden failure alongside a fatigue FAIL (DCR ≈ 1.57) that "Optimized" mode does not iterate away

**Severity:** Medium–High (safety-relevant reporting: the headline verdict of a design run can read "PASS" while a FAIL row exists in the very same `checks` list and in the report's check tables; the two "overall" verdicts in one report disagree)

**Component:** Core — `src/osdagbridge/core/bridge_types/plate_girder/designer.py::DCREngine._structural_checks/overall_status/n_pass/n_warn/n_fail/max_dcr` (lines 2426-2453); category map at 2029-2045

## Environment

- OsdagBridge commit `d74f56d` (branch `task/software-testing`)
- Default configuration: 30 m span, 7.5 m carriageway, 4 girders, E 350A / M40, Design Type = Optimized (all shipped default values)

## Steps to reproduce

Run the default design headlessly (same as the GUI default template + *Design*):

```python
b = PlateGirderBridge(); b.set_input(input_dict); b.design()
dr = dict(b.output_dict)["design_results"]
```

Inspect the tallies against the check list:

```python
fails   = [c for c in dr["checks"] if c["status"] == "FAIL"]
print(dr["overall_status"], dr["n_pass"], dr["n_warn"], dr["n_fail"], dr["max_dcr"])
print([(c["check_id"], c["name"], c["dcr"]) for c in fails])
```

## Expected

- `n_fail` counts every FAIL in `dr["checks"]`; `overall_status` is FAIL if *any* check (girder, stiffener, …) fails; `max_dcr` is the worst DCR across all checks.
- If "Optimized" mode leaves a check failing, that is at minimum surfaced loudly (and ideally the optimizer iterates on it).

## Actual (reference run, all default values)

```
overall_status = FAIL      n_pass = 13   n_warn = 0   n_fail = 1   max_dcr = 1.5726
fails = [(8,  'Fatigue Normal Stress',   1.573),      # counted (structural category 6)
         (20, 'Int.Stiff: Leg ≤ H_limit', 1.479)]      # NOT counted anywhere
```

1. **Stiffener FAILs are invisible to the tallies.** `n_fail` = 1 although two checks failed; `max_dcr` = 1.5726 although the stiffener check reached 1.479. The exclusion is by construction (see root cause): if the fatigue check passed, this bridge would report `overall_status = "PASS"`, `n_fail = 0`, while its own `checks` table contains a FAIL row.
2. **The report contradicts itself.** The executive summary (`core/reports/executive_summary.py:80-110`) scans **all** checks of **every** girder and prints `Fail (Fatigue Normal Stress, Int.Stiff: Leg ≤ H_limit, …)`, while the Design Check chapter's summary rows and `design_results.overall_status` only reflect the 8 structural categories. Two different "overall" verdicts for the same run.
3. **Baseline finding — the default configuration fails its own design checks.** With every input at its shipped default, the run ends `overall_status = FAIL` (fatigue DCR ≈ 1.57, stiffener leg DCR ≈ 1.48). "Optimized" sizing is a single empirical pass (`initial_sizing.py`: D = span/18 rounded to a 10 mm grid; no feedback loop from the DCR results), so the failure stands in the output with no iteration and no user-facing remediation hint.

## Root cause (file:line)

`designer.py:2029-2045` — `DCREngine.CATEGORY_MAP` deliberately maps only check ids 1-14 into the 8 IRC-22 categories, with the comment:

```python
    # 20, 21 — stiffener: excluded from the 8-category aggregation
```

Excluding them from the *category aggregation* is fine — but the same filter is reused for the *verdict tallies*:

```python
# designer.py:2426-2453
def _structural_checks(self) -> List[CheckResult]:
    """Checks belonging to the 8 design categories only (excludes stiffener check_ids 20/21)."""
    return [c for c in self.checks if c.check_id in self.CATEGORY_MAP]

def overall_status(self) -> str:
    structural = self._structural_checks()
    ...
def n_fail(self) -> int:
    return sum(1 for c in self._structural_checks() if c.status == "FAIL")
```

so `overall_status()`, `max_dcr()`, `n_pass()`, `n_warn()`, `n_fail()` (used verbatim in the `design_results` dict, `designer.py:3333-3337`) never see the stiffener checks. The per-girder `checks` list *does* contain them (`designer.py:3338-3352`), which is what makes the mismatch observable.

## Suggested fix

Keep the 8-category aggregation untouched, but compute the verdict tallies over **all** checks:

```python
# designer.py
def _structural_checks(self) -> List[CheckResult]:
    """Checks belonging to the 8 design categories (for category_urs)."""
    return [c for c in self.checks if c.check_id in self.CATEGORY_MAP]

def overall_status(self) -> str:
    checks = self.checks                 # ALL checks, incl. stiffeners 20/21
    if not checks:
        return "NO CHECKS RUN"
    if any(c.status == "FAIL" for c in checks):
        return "FAIL"
    if any(c.status == "WARN" for c in checks):
        return "WARN"
    return "PASS"

def max_dcr(self) -> float:
    return max((c.dcr for c in self.checks), default=0.0)

def n_pass(self) -> int:
    return sum(1 for c in self.checks if c.status == "PASS")
def n_warn(self) -> int:
    return sum(1 for c in self.checks if c.status == "WARN")
def n_fail(self) -> int:
    return sum(1 for c in self.checks if c.status == "FAIL")
```

(If a "structural-only" verdict is also wanted, keep it under a new name, e.g. `structural_status`, and surface both — but the headline `overall_status` must not be able to say PASS while a FAIL row exists.)

For finding 3, the deeper work is an optimizer feedback loop (grow flange area / reduce stress range when the fatigue category exceeds 1.0) or, minimally, a console + GUI warning naming the failing check and the levers that affect it; the one-pass empirical sizing in `initial_sizing.py` cannot resolve a fatigue failure by construction.

**Verification** (currently pinning the behaviour; must be inverted when the fix lands):

- `tests/unit/test_output_consistency.py::TestUtilizationRatios::test_stiffener_failures_excluded_from_overall_status`
- `tests/unit/test_output_consistency.py::TestUtilizationRatios::test_reference_run_fails_fatigue` (pins the default-run FAIL + fatigue DCR > 1)
