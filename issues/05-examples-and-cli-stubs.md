# [Bug] The shipped CLI is a non-functional stub and `examples/plate_girder/*.yaml` are placeholders, while the README documents `osdagbridge analyze project.yaml --solver native`

**Severity:** Medium (documented functionality does not exist; the stub exits 0 and silently ignores all arguments, so scripted/CI use fails silently; two of the three example files cannot be loaded by anything in the codebase)

**Component:** CLI — `src/osdagbridge/cli/__main__.py`, `src/osdagbridge/cli/commands.py`; docs — `README.md` ("Usage → Command-Line Interface"); examples — `examples/plate_girder/`

## Environment

- OsdagBridge commit `d74f56d` (branch `task/software-testing`)
- Installed per `pyproject.toml`: entry points `osdagbridge-cli = "osdagbridge.cli.__main__:main"` and `osdagbridge = "osdagbridge.desktop.__main__:main"`

## Steps to reproduce

```bash
$ osdagbridge-cli analyze project.yaml --solver native     # README-documented workflow
osdagbridge CLI (stub)
$ echo $?
0

$ python -m osdagbridge.cli report project.yaml report.pdf  # README-documented workflow
osdagbridge CLI (stub)

$ cat examples/plate_girder/verification_case_01.yaml
# Verification case 01 (DDCL) - placeholder
$ cat examples/plate_girder/verification_case_02.yaml
# Verification case 02 (DDCL) - placeholder
$ cat examples/plate_girder/example_basic.yaml
# Example plate girder input (placeholder)
project:
  name: example_basic
  span_m: 30.0
```

## Expected (per README.md "Usage")

```bash
osdagbridge analyze project.yaml --solver native
osdagbridge report project.yaml report.pdf
```

i.e. an argument-parsing CLI that loads a project file, runs the shared-core analysis/design pipeline and writes results/a report; example files that the software (or at least the documented loader) can open.

## Actual

1. **The CLI never parses arguments and never runs anything.** `cli/__main__.py::main()` is:

   ```python
   def main():
       print("osdagbridge CLI (stub)")
   ```

   and `cli/commands.py` is:

   ```python
   def analyze_cmd(path):
       print("analyze", path)
   ```

   All arguments are ignored and the process exits **0** — an invalid command, a missing file, or a typo'd flag all "succeed" silently. (Verified live: `python -m osdagbridge.cli analyze foo.yaml --solver native` → `osdagbridge CLI (stub)`, rc=0.)

2. **The command name in the README does not even point at the CLI.** `pyproject.toml` binds the *unprefixed* `osdagbridge` command to the **desktop GUI** (`osdagbridge.desktop.__main__:main`), whose `main()` builds a `QApplication` and shows `CustomWindow` — it never inspects `sys.argv`. Following the README literally (`osdagbridge analyze …`) launches the GUI (or crashes headless) instead of analysing anything. The actual CLI lives under the differently-named `osdagbridge-cli`.

3. **No YAML project loader exists.** The only `yaml` reference in `src/osdagbridge` is in `desktop/ui/template_page.py`; nothing reads `examples/plate_girder/*.yaml`. Moreover the one non-empty example (`example_basic.yaml`) uses a nested `project: {name, span_m}` layout that matches no schema in the codebase — `PlateGirderBridge.set_input()` consumes a **flat dict with dotted keys** (`geometry.span`, `material.girder.fy`, `typical_section.no_of_girders`, …), so even a hand-written loader could not map it without a schema definition. `verification_case_01.yaml` and `verification_case_02.yaml` contain a single comment line and nothing else.

## Root cause (file:line)

- `src/osdagbridge/cli/__main__.py:1-6` — `main()` is a print stub (no `argparse`/`click`, no subcommands).
- `src/osdagbridge/cli/commands.py:1-3` — `analyze_cmd()` is a print stub.
- `pyproject.toml:84-86` — entry-point names: `osdagbridge` → desktop GUI, `osdagbridge-cli` → CLI stub (README documents the former as the CLI).
- `examples/plate_girder/*.yaml` — placeholder content committed as examples.

## Suggested fix

Implement the two documented subcommands on top of the existing headless pipeline (the same one the test-suite and `scripts/smoke_headless.py` use), and make the examples loadable:

```python
# src/osdagbridge/cli/__main__.py
import argparse, sys

def main(argv=None):
    p = argparse.ArgumentParser(prog="osdagbridge",
                                description="OsdagBridge - steel bridge analysis & design")
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("analyze", help="run the analysis/design pipeline")
    pa.add_argument("project", help="project .yaml (flat dotted-key input dict)")
    pa.add_argument("--solver", choices=("native", "opensees", "ospgrillage"),
                    default="ospgrillage")
    pa.add_argument("--out", default=None, help="write output_dict JSON here")

    pr = sub.add_parser("report", help="run design + generate the PDF report")
    pr.add_argument("project")
    pr.add_argument("report", help="output PDF path")

    args = p.parse_args(argv)
    if args.command == "analyze":
        from osdagbridge.cli.commands import analyze_cmd
        return analyze_cmd(args.project, solver=args.solver, out=args.out)
    from osdagbridge.cli.commands import report_cmd
    return report_cmd(args.project, args.report)
```

```python
# src/osdagbridge/cli/commands.py
import yaml
from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import PlateGirderBridge

def _load_bridge(path):
    with open(path) as fh:
        d = yaml.safe_load(fh)                 # flat dotted-key dict (see examples)
    b = PlateGirderBridge()
    b.set_input(d)
    return b

def analyze_cmd(path, solver="ospgrillage", out=None):
    b = _load_bridge(path)
    b.design()
    if out:
        import json
        with open(out, "w") as fh:
            json.dump(dict(b.output_dict), fh, default=str, indent=1)
    return 0

def report_cmd(path, report_pdf):
    ...
```

Plus:

- resolve the entry-point/README mismatch — either rename the GUI entry (e.g. `osdagbridge-gui`) so `osdagbridge` can be the CLI, or change the README to `osdagbridge-cli analyze …`;
- replace the three placeholder YAMLs with real flat-schema inputs (mirroring `BASIC_INPUT_DICT` + the `material.*` keys used by `scripts/smoke_headless.py`) so `osdagbridge-cli analyze examples/plate_girder/example_basic.yaml` works out of the box;
- until then, exit non-zero (`return 2`) instead of printing "(stub)" and returning 0, so CI/scripts fail loudly.

**Verification:** `tests/integration/test_cli_plate_girder.py` currently contains only `test_cli_placeholder` — it should grow a subprocess test asserting `osdagbridge-cli analyze examples/plate_girder/example_basic.yaml` produces a JSON/PDF and a non-zero exit for a bad path.
