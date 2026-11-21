"""Functional tests: PDF design-report generation (task requirement 3).

Exercises the same path as the GUI "Generate Report" button:
    PlateGirderBridge.generate_design_report(request, cad_generator)
        → build_report_payload(request, input_dict, output_dict)
        → generate_report(payload, request)  → Report_Before.pdf/.tex

LaTeX is compiled through the sandbox pdflatex→tectonic shim on PATH.
The known longtable caption defect (issues/01) is pinned with an xfail so
the suite stays green both before and after the parallel fix lands.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.slow


PDFLATEX_ON_PATH = any(
    os.access(os.path.join(p, "pdflatex"), os.X_OK)
    for p in os.environ.get("PATH", "").split(os.pathsep)
)


def _make_request(tmp_path, stem="Report_Test"):
    from osdagbridge.core.reports.report_generator import (
        ReportRequest, ReportMetadata, ReportOptions)

    return ReportRequest(
        metadata=ReportMetadata(
            project_name="OsdagBridge QA Test Bridge",
            project_location="Mumbai",
            designer="Task D QA",
            client="FOSSEE",
            company="IIT Bombay",
            job_number="QA-2026-004",
            report_date="2026-01-15"),
        options=ReportOptions(
            sections=["loads", "analysis", "design_checks", "drawings"],
            include_figures=True, include_toc=True, include_pdf=True),
        output_dir=str(tmp_path), file_stem=stem)


@pytest.fixture(scope="module")
def report_result(tmp_path_factory, designed_bridge_default):
    """Generate the report once from the session-scoped default design."""
    tmp = tmp_path_factory.mktemp("report")
    request = _make_request(tmp)
    result = designed_bridge_default.generate_design_report(
        request, cad_generator={})
    return result, tmp


class TestReportGeneration:
    def test_report_payload_builds(self, designed_bridge_default):
        """build_report_payload must fill metadata, inputs, output_dict,
        and pull the design log from the singleton logger."""
        from osdagbridge.core.reports.report_generator import build_report_payload

        request = _make_request("/tmp")
        payload = build_report_payload(
            request, dict(designed_bridge_default.input_dict),
            dict(designed_bridge_default.output_dict))
        assert payload.metadata.project_name.startswith("OsdagBridge QA")
        assert payload.inputs["geometry.span"] == 30.0
        assert payload.output_dict["design_results"]["fy_MPa"] == 350.0
        assert payload.log_entries, "design log entries missing from payload"

    @pytest.mark.skipif(not PDFLATEX_ON_PATH, reason=(
        "no pdflatex on PATH (sandbox shim at /home/z/my-project/bin)"))
    def test_report_pdf_is_produced(self, report_result):
        """The report pipeline must emit a non-trivial PDF + the .tex source."""
        result, tmp = report_result
        assert result.pdf_path and os.path.exists(result.pdf_path)
        assert os.path.getsize(result.pdf_path) > 10_000, "PDF suspiciously small"
        assert os.path.exists(result.tex_path)

    def test_tex_contains_all_chapters(self, report_result):
        """The .tex source must include every chapter skeleton."""
        result, _ = report_result
        tex = open(result.tex_path, encoding="utf-8").read()
        for fragment in ("\\chapter{Project Information}",
                         "\\chapter{Input Parameters}",
                         "Loads", "Analysis Results", "Design Checks",
                         "\\end{document}"):
            assert fragment in tex, f"chapter fragment {fragment!r} missing"

    def test_tex_echoes_design_values(self, report_result):
        """Spot-check that report tables carry real numbers, not blanks."""
        result, _ = report_result
        tex = open(result.tex_path, encoding="utf-8").read()
        assert "30.0" in tex            # span
        assert "7.5" in tex             # carriageway
        assert "E 350A" in tex          # steel grade
        assert "1670" in tex            # girder depth (final section)

    @pytest.mark.xfail(reason=(
        "Known upstream defect (issues/01): 46 longtable captions are not "
        "terminated with \\\\ before \\\\hline → ~281 'Misplaced \\noalign / "
        "\\omit / Extra alignment tab' LaTeX errors per compile; "
        "a parallel task is fixing chap2/3/4/5.py"),
        strict=False)
    def test_longtable_captions_are_terminated(self, report_result):
        """Every \\caption{...} inside a longtable must end its row with \\\\
        before \\hline, otherwise pdflatex aborts the table alignment."""
        result, _ = report_result
        tex = open(result.tex_path, encoding="utf-8").read().splitlines()
        in_longtable = False
        bad = []
        for i, line in enumerate(tex):
            if "\\begin{longtable}" in line:
                in_longtable = True
            if in_longtable and line.strip().startswith("\\caption{"):
                nxt = tex[i + 1].strip() if i + 1 < len(tex) else ""
                if not nxt.startswith("\\\\"):
                    bad.append((i + 1, line.strip()[:60]))
            if "\\end{longtable}" in line:
                in_longtable = False
        assert not bad, f"{len(bad)} unterminated caption rows: {bad[:5]}"


@pytest.mark.slow
class TestReportFromCustomRun:
    def test_custom_material_report_shows_custom_values(
            self, tmp_path, custom_material_bridge):
        """A report generated after a custom-material run must echo the
        custom values (no stale E350 defaults).

        report_utils._tex() escapes '_' to '\\_\\allowbreak{}', so the
        plain string 'custom_steel_fy250' never appears verbatim in the
        .tex — unescape before asserting."""
        request = _make_request(tmp_path, stem="Report_Custom")
        result = custom_material_bridge.generate_design_report(
            request, cad_generator={})
        assert result.tex_path and os.path.exists(result.tex_path)
        tex = open(result.tex_path, encoding="utf-8").read()
        plain = (tex
                 .replace(r"\allowbreak{}", "")
                 .replace(r"\_", "_"))
        assert "custom_steel_fy250" in plain, (
            "custom steel grade missing from the report input tables")
        assert "custom_concrete_fck30" in plain
        assert "250.0" in tex
