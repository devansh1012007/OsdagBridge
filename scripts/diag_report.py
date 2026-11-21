"""Diagnose the LaTeX report compile failure (baseline finding).

Runs the reference 30 m design headlessly, generates the report with the
baseline code (stem Report_Before), then compiles the emitted .tex with the
sandbox pdflatex->tectonic shim, capturing every LaTeX error with its line
number, and dumps tex context for each offending line.

Usage:  PATH=/path/to/pdflatex-shim:$PATH python scripts/diag_report.py
(repo root is derived from this file's location; set OSDAG_STUBS to point at
an osdag_core stub/conda install if the real Osdag package is not installed).
"""
import os, re, shutil, subprocess, sys, tempfile

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.environ.get('OSDAG_STUBS', '/home/z/my-project/stubs'))
sys.path.insert(0, os.path.join(_REPO, 'src'))
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
os.environ['MPLBACKEND'] = 'Agg'
os.environ['PATH'] = '/home/z/my-project/bin:' + os.environ['PATH']

OUT = '/tmp/task_d_diag'
os.makedirs(OUT, exist_ok=True)

from osdagbridge.core.bridge_types.plate_girder.defaults import (
    BASIC_INPUT_DICT, solve_extend_basic_input_dict)
from osdagbridge.core.bridge_types.plate_girder.plategirderbridge import PlateGirderBridge
from osdagbridge.core.reports.report_generator import (
    ReportRequest, ReportMetadata, ReportOptions)

# ---- build the default input (mirror smoke_headless.py) ----
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
print('[1] design done')

request = ReportRequest(
    metadata=ReportMetadata(
        project_name='OsdagBridge QA Test Bridge', project_location='Mumbai',
        designer='Task D QA', client='FOSSEE', company='IIT Bombay',
        job_number='QA-2026-004', report_date='2026-01-15'),
    options=ReportOptions(
        sections=['loads', 'analysis', 'design_checks', 'drawings'],
        include_figures=True, include_toc=True, include_pdf=True),
    output_dir=OUT, file_stem='Report_Before')

result = b.generate_design_report(request, cad_generator={})
print('[2] report result:', result)
print('    tex:', result.tex_path, 'pdf:', result.pdf_path)
if result.pdf_path and os.path.exists(result.pdf_path):
    print('    pdf size:', os.path.getsize(result.pdf_path))

tex_path = result.tex_path or os.path.join(OUT, 'Report_Before.tex')

# ---- compile the tex separately, capturing the full error log ----
work = tempfile.mkdtemp(prefix='texdiag_')
shutil.copy(tex_path, work)
proc = subprocess.run(['pdflatex', '-interaction=nonstopmode', 'Report_Before.tex'],
                      cwd=work, capture_output=True, text=True)
log = proc.stdout + proc.stderr
with open(os.path.join(OUT, 'compile_log.txt'), 'w') as fh:
    fh.write(log)
print('[3] compile rc =', proc.returncode, ' log saved')

# ---- parse errors of the shape  l.NNN <message> ----
errors = []
for line in log.splitlines():
    m = re.match(r'^(\d+):\s+(.*)$', line)
    if m:
        errors.append((int(m.group(1)), m.group(2)))
print('[4] LaTeX diagnostics with line numbers:', len(errors))

from collections import Counter
kinds = Counter(msg.split(':')[0].strip() for _, msg in errors)
print('    by kind:', dict(kinds))
lns = sorted({ln for ln, _ in errors})
print('    offending tex lines:', lns[:60])

# ---- show tex context for every offending line ----
tex_lines = open(tex_path, encoding='utf-8').read().splitlines()
with open(os.path.join(OUT, 'error_context.txt'), 'w') as fh:
    for ln in lns:
        ctx = tex_lines[ln-3:ln+2]
        fh.write(f'--- tex line {ln} ---\n')
        for j, cl in enumerate(ctx, start=max(1, ln-2)):
            fh.write(f'{j:5d}: {cl}\n')
        fh.write('\n')
print('[5] context written to', os.path.join(OUT, 'error_context.txt'))
print('tex total lines:', len(tex_lines))
