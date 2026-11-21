"""Generate the "after" (refactored) OsdagBridge design report headlessly.

Adapted from /home/z/my-project/scripts/gen_report.py (baseline generator):
same metadata, same section list, same output layout — only the report engine
differs (this branch: task/latex-report refactor).

Usage:
  /home/z/.venv/bin/python tools/gen_report_after.py <out_dir> <stem>

Reads /home/z/my-project/work/shared/smoke_output.json (input/output dicts
saved by smoke_headless.py).
"""
import sys, os, json, datetime

WORK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # repo root
OUT = sys.argv[1] if len(sys.argv) > 1 else '/home/z/my-project/download/task_a'
STEM = sys.argv[2] if len(sys.argv) > 2 else 'Report_After'
JSON_PATH = sys.argv[3] if len(sys.argv) > 3 else '/home/z/my-project/work/shared/smoke_output.json'

sys.path.insert(0, os.path.join(WORK, 'src'))

from osdagbridge.core.reports.report_generator import (
    ReportMetadata, ReportOptions, ReportRequest,
    build_report_payload, generate_report,
)

with open(JSON_PATH) as f:
    data = json.load(f)

input_dict = dict(data['input'])
output_dict = dict(data['output'])

os.makedirs(OUT, exist_ok=True)

request = ReportRequest(
    metadata=ReportMetadata(
        project_name='OsdagBridge Example - Plate Girder Bridge',
        project_location='Mumbai, Maharashtra, India',
        designer='Test Designer',
        reviewer='Test Reviewer',
        client='Test Client',
        company='FOSSEE, IIT Bombay',
        group_name='FOSSEE, IIT Bombay',
        subtitle='Rev 0',
        job_number='2026-001',
        additional_comments='Generated headlessly for verification.',
        logo_path=None,
        report_date=datetime.date.today().isoformat(),
    ),
    options=ReportOptions(
        sections=[
            'exec_summary', 'project_info', 'input_parameters', 'loads',
            'analysis', 'design_checks', 'drawings', 'quantities',
            'standards', 'design_log_window', 'references',
        ],
        include_figures=False,
        include_toc=True,
        include_pdf=True,
    ),
    output_dir=OUT,
    file_stem=STEM,
)

payload = build_report_payload(request, input_dict, output_dict)
result = generate_report(payload, request)

print('PDF :', result.pdf_path)
print('TEX :', result.tex_path)
if result.pdf_path and os.path.exists(result.pdf_path):
    print('SIZE:', os.path.getsize(result.pdf_path), 'bytes')
    sys.exit(0)
sys.exit(1)
