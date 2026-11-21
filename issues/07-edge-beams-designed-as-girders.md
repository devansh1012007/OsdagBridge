# [Bug] Overhang edge beams are designed and labelled as main girders: `design_results["n_girders"]` = 6 for a 4-girder bridge, `per_girder` labels the user's girders G2..G5 (shifted by one), and every EB1/EB2 skip-filter downstream is dead code

**Severity:** Medium (wrong component identity in all result tables/reports: the report's Design Check chapter lists 6 girder rows for a 4-girder bridge and "G2" means different girders in different tables of the same PDF; the controlling-girder `max()` selection includes the two overhang edge beams)

**Component:** Core — `src/osdagbridge/core/bridge_types/plate_girder/plategirderbridge.py:2296` (`_run_dcr_checks`), `analysis_results.py:453-460` (`build_girders` naming), `designer.py:401` (`n_girders = geom.n_l`)

## Environment

- OsdagBridge commit `d74f56d` (branch `task/software-testing`)
- Default configuration: 30 m span, 7.5 m carriageway, **4 girders** @ 2.1 m, deck overhang 1.05 m, E 350A / M40

## Steps to reproduce

```python
b = PlateGirderBridge(); b.set_input(input_dict); b.design()
dr = dict(b.output_dict)["design_results"]
print(input_dict["typical_section.no_of_girders"])   # 4
print(dr["n_girders"])                               # 6  ← grid lines, not girders
print(sorted(dr["per_girder"]))                      # ['G1','G2','G3','G4','G5','G6']
```

## Expected

- `design_results["n_girders"]` = the user's structural girder count (4).
- The per-girder results are keyed by the *user's* girder labels G1..G4; the two grillage edge lines carrying the deck overhang are either excluded or named `EB1`/`EB2` (the naming branch that already exists in `build_girders`, and which the designer/executive-summary filters expect — see below).

## Actual (reference run)

```
input typical_section.no_of_girders = 4
design_results.n_girders            = 6
design_results.per_girder           = {G1..G6}     # G1/G6 = overhang edge beams,
                                                   # user's girders appear as G2..G5
```

Consequences observed on the default run:

- The report's per-girder tables (Chapter 5 "Girder Design Summary", per-girder demands/deflections) show **6 rows** for a 4-girder bridge; the executive summary's dynamic girder table (`get_girder_entries(input_dict)`, populated by `defaults.py` from the user's count) shows **4 columns** labelled G1..G4 — in the same PDF, "G2" denotes the *second user girder* in one table and the *first user girder* in another.
- The controlling-girder selection (`designer.py:3363`, `max(per_girder_results, key=max_dcr)`) includes the edge beams. On the reference run their Mu is slightly lower (≈ 2160 kNm vs ≈ 2219 kNm interior) so they do not govern — but nothing excludes them.
- Every EB filter is **dead code** because no girder is ever *named* `EB*`:

  ```
  designer.py:2816   girders = {k: v for k, v in girders.items() if k not in ("EB1", "EB2")}
  designer.py:2916   if g_name in ("EB1", "EB2"): continue
  designer.py:3203   if g_name.startswith("EB"): continue
  executive_summary.py:84   if str(g).startswith("EB"): continue
  ```

## Root cause (file:line)

Two independent defects:

1. **The analysis handler that feeds the design check is built without `edge_dist`.** `PlateGirderAnalysisResults.build_girders()` names the first/last longitudinal grid line `EB1`/`EB2` **only when `edge_dist > 0`** (`analysis_results.py:453-460`):

   ```python
   name = f"G{i}"
   if self.edge_dist > 0:
       if i == 1:    name = "EB1"
       elif i == num_pairs: name = "EB2"
   ```

   but the handler constructed for the design check omits it (`plategirderbridge.py:2296`):

   ```python
   def _run_dcr_checks(self, dataset) -> None:
       results = PlateGirderAnalysisResults(dataset=dataset, bridge=self.grillage_model)   # ← no edge_dist
   ```

   The same omission exists at `plategirderbridge.py:3265` (graph-engine handler) and `:3765` (`get_available_loadcases`); only `compute_load_effects_cache` (`:3291`, uses `self.get_edge_dist()`) and `analyser.py:2861` pass it. With `edge_dist = 0` all six grid lines are named `G1..G6`, the EB filters never match, and the user's girder labels shift by one.

2. **`design_results["n_girders"]` counts grillage grid lines.** `BridgeConfig` is built from the grillage geometry (`designer.py:401`):

   ```python
   n_girders = geom.n_l        # 2 edge beams + 4 structural girders = 6
   ```

   and echoed verbatim into the structured results (`designer.py:3394`). The comment at `designer.py:410-413` even shows the author knew: "_girder_count() excludes the overhang edge beams that geom.n_l counts" — it is used for `beam_type`, but not for `n_girders`.

## Suggested fix

Pass the overhang distance everywhere the handler is constructed, and report the structural count:

```python
# plategirderbridge.py:2296 (_run_dcr_checks) — likewise :3265 and :3765
def _run_dcr_checks(self, dataset) -> None:
    results = PlateGirderAnalysisResults(
        dataset=dataset,
        bridge=self.grillage_model,
        edge_dist=self.get_edge_dist(),      # deck overhang; 0.0 when none
    )
```

```python
# designer.py:401
n_girders = bridge._girder_count()   # user's structural girders (excl. edge beams)
```

With `edge_dist` supplied, `build_girders()` names the overhang lines `EB1`/`EB2`, the existing filters at `designer.py:2816/2916/3203` and `executive_summary.py:84` start doing what they were written to do, `per_girder` keys revert to the user's G1..G4, and `n_girders` matches the input. (After the change, verify the per-girder deflection echoes `steeldesign.deflection.*` and the GUI girder selector still line up — they are keyed off the same labels.)

**Verification** (currently pinning the behaviour; must be inverted when the fix lands):

- `tests/unit/test_output_consistency.py::TestInternalDictionaryInspection::test_design_results_girder_count_is_grillage_grid_lines`
- `tests/unit/test_output_consistency.py::TestInternalDictionaryInspection::test_edge_beam_filter_is_dead_code`
