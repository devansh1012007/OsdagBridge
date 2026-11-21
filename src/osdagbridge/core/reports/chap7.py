# =============================================================================
# Chapter 7: Material Take-off & Quantity Summary
# =============================================================================
# The BOQ table is rendered through the centralized style system (repeated
# column headers via \endfirsthead / \endhead) and the material quantities
# are additionally summarized as auto-generated matplotlib bar charts
# (structural steel tonnage by component; concrete volume vs reinforcement
# steel weight) that are embedded as LaTeX figures.
# =============================================================================

from osdagbridge.core.reports.styles import (
    longtable, figure_block, ROW_END, TABLE_VSPACE,
)


def _num(inputs, key):
    """Best-effort float from a BOQ string value ('N.A.' -> None)."""
    try:
        v = inputs.get(key)
        if v is None or v == "" or str(v).strip().upper() in ("N.A.", "NA", "-"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _boq_rows(inputs):
    """One BOQ row per material item (7 columns, incl. units in headers)."""
    def _item(sn, desc, vol_formula, qty, vol_total, wt_single, wt_total):
        return (
            f"{sn} & {desc} & {vol_formula} & {qty} & {vol_total} & "
            f"{wt_single} & {wt_total} " + ROW_END + r"\hline" + "\n"
        )

    def _g(key, default="N.A."):
        v = inputs.get(key, default)
        return str(v) if v not in (None, "") else default

    rows = [
        _item("1", "Structural Steel (IS 2062) for Girders",
              _g("steel_girders_vol_formula"), _g("steel_girders_qty"),
              _g("steel_girders_vol_total"), _g("steel_girders_wt_single"),
              _g("steel_girders_wt_total")),
        _item("2(a)", "Cross Bracing -- Top Chord",
              _g("bracing_top_vol_formula"), _g("bracing_top_qty"),
              _g("bracing_top_vol_total"), _g("bracing_top_wt_single"),
              _g("bracing_top_wt_total")),
        _item("2(b)", "Cross Bracing -- Bottom Chord",
              _g("bracing_bot_vol_formula"), _g("bracing_bot_qty"),
              _g("bracing_bot_vol_total"), _g("bracing_bot_wt_single"),
              _g("bracing_bot_wt_total")),
        _item("2(c)", "Cross Bracing -- Diagonal",
              _g("bracing_diag_vol_formula"), _g("bracing_diag_qty"),
              _g("bracing_diag_vol_total"), _g("bracing_diag_wt_single"),
              _g("bracing_diag_wt_total")),
        _item("3", "Concrete for Deck Slab",
              _g("concrete_deck_vol_formula"), _g("concrete_deck_qty"),
              _g("concrete_deck_vol_total"), _g("concrete_deck_wt_single"),
              _g("concrete_deck_wt_total")),
        _item("4", "Reinforcement Steel",
              _g("rebar_deck_vol_formula"), _g("rebar_deck_qty"),
              _g("rebar_deck_vol_total"), _g("rebar_deck_wt_single"),
              _g("rebar_deck_wt_total")),
        _item("5", "Shear Stud Connectors",
              _g("shear_studs_vol_formula"), _g("shear_studs_qty"),
              _g("shear_studs_vol_total"), _g("shear_studs_wt_single"),
              _g("shear_studs_wt_total")),
        _item("6", "Crash Barrier",
              _g("crash_barrier_vol_formula"), _g("crash_barrier_qty"),
              _g("crash_barrier_vol_total"), _g("crash_barrier_wt_single"),
              _g("crash_barrier_wt_total")),
    ]
    return "".join(rows)


def ch7_quantities(input_dict, fig_paths=None):
    """Chapter 7 — BOQ table + embedded material-quantity bar charts.

    ``fig_paths`` maps chart keys ('qty_steel', 'qty_concrete') to image
    paths prepared by osdagbridge.core.reports.charts.quantity_charts(); a
    missing chart simply omits that figure (never fails the report).
    """
    fig_paths = fig_paths or {}

    # Volume-formula cells hold one unbreakable inline math expression, so
    # col 3 is sized for "$0.032102\text{ m}^2 \times 30.00\text{ m}$".
    boq_table = longtable(
        col_spec="|C{1.0cm}|L{3.2cm}|C{2.55cm}|C{1.95cm}|C{1.8cm}|C{1.8cm}|C{1.8cm}|",
        caption="Bill of Materials (Steel, Concrete, and Reinforcement Quantities)",
        header=(r"\textbf{S.N.} & \textbf{Item Description} & "
                r"\textbf{Volume (m\textsuperscript{3})} & \textbf{Quantity} & "
                r"\textbf{Total Volume (m\textsuperscript{3})} & "
                r"\textbf{Weight (MT)} & \textbf{Total Weight (MT)}"),
        body=_boq_rows(input_dict),
        ncols=7,
        colsep="3pt",
    )

    # ── Quantity summary charts (matplotlib, generated at report time) ─────
    chart_figs = []
    steel_fig = figure_block(
        fig_paths.get('qty_steel'),
        caption="Structural steel tonnage by component (plate girders, "
                "cross bracing, end diaphragms, shear stud connectors).",
        width=r"0.9\textwidth", label="fig:qty-steel")
    if steel_fig:
        chart_figs.append(steel_fig)

    conc_fig = figure_block(
        fig_paths.get('qty_concrete'),
        caption="Concrete deck volume (m\\textsuperscript{3}) vs "
                "reinforcement steel weight (MT).",
        width=r"0.8\textwidth", label="fig:qty-concrete")
    if conc_fig:
        chart_figs.append(conc_fig)

    missing = [k for k in ('qty_steel', 'qty_concrete') if not fig_paths.get(k)]

    notes = []
    if missing:
        notes.append(
            r"\noindent\textit{Note: quantity summary chart"
            + ("s" if len(missing) > 1 else "")
            + " could not be generated for this run (missing BOQ data).}"
        )
    notes.append(
        r"\noindent\textit{Note: Quantities are computed from the final "
        r"optimized geometry; ``N.A.'' entries indicate items whose section "
        r"properties were not available for this design run.}"
    )

    return (
        "\\chapter{Material Take-off \\& Quantity Summary}\n"
        "\\label{ch:material-takeoff}\n"
        "\n"
        "This chapter summarizes the bill of materials for the finalized "
        "design, followed by graphical summaries of the structural steel "
        "tonnage and the principal concrete / reinforcement quantities.\n"
        "\n"
        + boq_table + "\n"
        + TABLE_VSPACE + "\n"
        + "".join(chart_figs)
        + "\n".join(notes) + "\n"
    )
