# =============================================================================
# OsdagBridge — Report Chart Generation (matplotlib, Agg backend)
# =============================================================================
# Programmatically generates the summary visualizations embedded in the
# LaTeX report:
#
#   • Utilization-Ratio (UR = Demand / Capacity) bar charts for ALL primary
#     elements — steel plate girders, concrete deck slab, cross bracing and
#     end diaphragms (Section 5.5, "Overall Design Check Summary").
#     Every chart carries a red-dashed reference line at UR = 1.0 that
#     visually separates passing (UR ≤ 1.0) from failing (UR > 1.0) checks.
#
#   • Material-quantity bar charts for Chapter 7 (BOQ / material take-off):
#     structural steel tonnage by component and concrete volume vs
#     reinforcement steel weight.
#
# All visual styling is imported from styles.py (chart theme = single source
# of truth).  Charts are auto-saved as PNG assets into the caller-provided
# directory (the report temp dir) and returned as paths for LaTeX embedding.
#
# Every public function is defensive: missing/partial data degrades to a
# skipped chart (returns None) — report generation never crashes.
# =============================================================================

import logging
import math
import os

import matplotlib
matplotlib.use("Agg")           # headless — no display required
import matplotlib.pyplot as plt   # noqa: E402

from osdagbridge.core.reports import styles   # noqa: E402
from osdagbridge.core.reports.report_utils import get_girder_entries  # noqa: E402

logger = logging.getLogger(__name__)

_UR_LIMIT = styles.CHART["ur_limit"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _to_float(v):
    try:
        if v is None or v == "":
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Code-based fallback helpers (used ONLY when the Osdag member-design engine
# produced no results for the cross-bracing members — e.g. headless runs where
# osdag_core is unavailable).  Section properties are read from the same
# Osdag section database the designer uses, and capacities follow
# IS 800:2007: tension = gross yielding (Cl. 6.2.1), compression = buckling
# class c (Cl. 7.1.2, Table 10).  These values are clearly labelled as
# code-based checks wherever they are reported.
# ---------------------------------------------------------------------------

_IS800_GAMMA_M0 = 1.10          # Table 5 (partial safety factors)
_IS800_CLASS_C_ALPHA = 0.49     # Table 10 — imperfection factor, buckling class c
_STEEL_E_MPA = 2.0e5            # modulus of elasticity, MPa

# Osdag section database shipped with the package
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                        "data", "ResourceFiles", "Intg_osdag.sqlite")

_angle_props_cache = {}


def _osdag_angle_props(designation):
    """(area_cm2, rz_cm, rv_cm, mass_kg_per_m) for an angle designation from
    the bundled Osdag section database; None when not found."""
    des = str(designation or "").strip()
    if not des:
        return None
    if des in _angle_props_cache:
        return _angle_props_cache[des]
    props = None
    try:
        import re
        import sqlite3
        if os.path.exists(_DB_PATH):
            con = sqlite3.connect(_DB_PATH)
            try:
                cur = con.cursor()
                # Normalize: drop unit prefixes ('IS') and unicode glyphs so
                # 'IS 100 x 100 x 10' matches the DB's '100 x 100 x 10'.
                des_norm = (des.replace("∠", "").replace("ⅹ", "x")
                            .replace("×", "x").strip())
                cur.execute(
                    'SELECT Area, rz, rvmin, Mass FROM Angles '
                    'WHERE Designation = ?', (des_norm,))
                row = cur.fetchone()
                if not row:
                    # Same number-based fuzzy match the designer uses
                    # (plategirderbridge._query_crossbracing_section).
                    nums = re.findall(r"\d+(?:\.\d+)?", des_norm)
                    if nums:
                        cur.execute(
                            'SELECT Area, rz, rvmin, Mass FROM Angles '
                            'WHERE Designation LIKE ? ORDER BY LENGTH(Designation)',
                            ("%" + "%".join(nums) + "%",))
                        row = cur.fetchone()
                if row:
                    props = tuple(_to_float(x) for x in row)
            finally:
                con.close()
    except Exception as exc:
        logger.debug("Osdag section DB lookup failed for %r: %s", designation, exc)
    _angle_props_cache[des] = props
    return props


def _section_multiplier(section_type):
    """Area/mass multiplier of the section type ('Double Angle' -> 2)."""
    st = str(section_type or "").strip().lower()
    if st.startswith("double"):
        return 2.0
    return 1.0


def _first_key_value(source, prefix):
    """First non-empty value among keys starting with *prefix* (the bracing
    input keys carry a member-id suffix that varies: '.G1G2.B1M1', ...)."""
    best_key = None
    for k in source:
        if str(k).startswith(prefix):
            v = source[k]
            if v not in (None, ""):
                if best_key is None or k < best_key:
                    best_key = k
    return source[best_key] if best_key else None


def _is800_tension_capacity_kN(area_mm2, fy_mpa):
    """Gross-section yielding capacity, IS 800:2007 Cl. 6.2.1 (kN)."""
    if not area_mm2 or not fy_mpa:
        return None
    return area_mm2 * fy_mpa / _IS800_GAMMA_M0 / 1000.0


def _is800_compression_capacity_kN(area_mm2, fy_mpa, kl_mm, r_min_mm):
    """Axial buckling capacity, IS 800:2007 Cl. 7.1.2, buckling class c (kN)."""
    if not area_mm2 or not fy_mpa or not kl_mm or not r_min_mm or r_min_mm <= 0:
        return None
    slenderness = kl_mm / r_min_mm
    lam = slenderness / math.pi * math.sqrt(fy_mpa / _STEEL_E_MPA)
    phi = 0.5 * (1.0 + _IS800_CLASS_C_ALPHA * (lam - 0.2) + lam * lam)
    chi = 1.0 / (phi + math.sqrt(max(phi * phi - lam * lam, 0.0)))
    chi = min(chi, 1.0)
    f_cd = chi * fy_mpa / _IS800_GAMMA_M0
    return area_mm2 * f_cd / 1000.0


def _cb_code_checks(output_dict, input_dict):
    """Cross-bracing code-based IS 800 axial checks.

    Used only for members whose Osdag design result is missing.  Demands come
    from crossbracing_forces_dict; sections from the UI loading-tab inputs
    (designation + section type) resolved against the Osdag section database.
    Returns a list of dicts: {pair, member, force_type, demand_kN,
    capacity_kN, ur}.
    """
    od = output_dict or {}
    inputs = input_dict or {}
    forces = (od.get("crossbracing_forces_dict", {}) or {})
    pairs = forces.get("pairs", {}) or {}
    geom = forces.get("geometry", {}) or {}
    if not pairs:
        return []

    fy = _to_float(inputs.get("material.cross_bracing.fy")) or 350.0
    L_diag_mm = _to_float(geom.get("diagonal_length_m"))
    L_chord_mm = _to_float(geom.get("horiz_proj_m"))
    L_diag_mm = L_diag_mm * 1000.0 if L_diag_mm else None
    L_chord_mm = L_chord_mm * 1000.0 if L_chord_mm else None

    out = []
    for pair in sorted(pairs.keys()):
        pair_id = str(pair).replace("-", "")
        pfx = "member_properties.cross_bracing_details."
        # diagonal (bracing) section
        diag_des = _first_key_value(inputs, f"{pfx}bracing_section_designation.{pair_id}.")
        diag_type = _first_key_value(inputs, f"{pfx}bracing_section_type.{pair_id}.")
        # chords (top preferred, bottom fallback — same designation in practice)
        chord_des = (_first_key_value(inputs, f"{pfx}top_chord_section_designation.{pair_id}.")
                     or _first_key_value(inputs, f"{pfx}bottom_chord_section_designation.{pair_id}."))
        chord_type = (_first_key_value(inputs, f"{pfx}top_chord_section_type.{pair_id}.")
                      or _first_key_value(inputs, f"{pfx}bottom_chord_section_type.{pair_id}."))

        for member, des, stype, L_mm in (
            ("Diag.", diag_des, diag_type, L_diag_mm),
            ("Chord", chord_des, chord_type, L_chord_mm),
        ):
            props = _osdag_angle_props(des)
            if not props or not L_mm:
                continue
            area_cm2, _rz_cm, rv_cm, _mass = props
            area_mm2 = area_cm2 * 100.0 * _section_multiplier(stype)
            r_min_mm = rv_cm * 10.0     # single-angle r_min — conservative for built-ups
            mem_key = "diag" if member == "Diag." else "chord"
            for ftype, key in (("T", "tension"), ("C", "compression")):
                demand = _to_float(pairs[pair].get(f"{mem_key}_{key}_kN"))
                if demand is None:
                    continue
                if ftype == "T":
                    cap = _is800_tension_capacity_kN(area_mm2, fy)
                else:
                    cap = _is800_compression_capacity_kN(area_mm2, fy, L_mm, r_min_mm)
                if cap and cap > 0:
                    out.append({"pair": pair, "member": member, "force_type": key,
                                "demand_kN": demand, "capacity_kN": cap,
                                "ur": demand / cap})
    return out


def _cb_code_urs(output_dict, input_dict):
    """[(label, ur)] view of :func:`_cb_code_checks` (chart input)."""
    return [(f"{c['pair']} {c['member']} ({c['force_type'][0].upper()})",
             c["ur"])
            for c in _cb_code_checks(output_dict, input_dict)]


def _cb_code_tonnage(input_dict, output_dict):
    """Cross-bracing structural steel tonnage (MT) from the UI section
    selection, when the designer did not persist bracing weights.  Each
    X-braced panel = 2 diagonals + top chord + bottom chord; one panel per
    girder pair per bracing location."""
    inputs = input_dict or {}
    od = output_dict or {}
    forces = (od.get("crossbracing_forces_dict", {}) or {})
    geom = forces.get("geometry", {}) or {}
    pairs = forces.get("pairs", {}) or {}
    diag_len = _to_float(geom.get("diagonal_length_m"))
    chord_len = _to_float(geom.get("horiz_proj_m"))
    if not diag_len or not chord_len:
        return None

    n_panels = _to_float(inputs.get("member_properties.cross_bracing_details.no_of_cross_bracings"))
    if n_panels is None:
        span = _to_float(inputs.get("bridge_details.span")) or _to_float(inputs.get("span"))
        spacing = _to_float(geom.get("cb_spacing_m"))
        if span and spacing:
            n_panels = max(1.0, round(span / spacing) - 1)
    if not n_panels:
        return None

    pfx = "member_properties.cross_bracing_details."
    # girder pairs that actually carry a bracing designation
    pair_ids = set()
    for k in inputs:
        if str(k).startswith(f"{pfx}bracing_section_designation.") and inputs[k] not in (None, ""):
            parts = str(k).split(".")
            if len(parts) >= 5:
                pair_ids.add(parts[3])
    if not pair_ids:
        pair_ids = {str(p).replace("-", "") for p in pairs.keys()}
    if not pair_ids:
        return None

    total_kg = 0.0
    found = False
    for pair_id in sorted(pair_ids):
        # member mass (kg/m) — double angle counts both legs
        for prefix, length_m in (
            (f"{pfx}bracing_section_designation.{pair_id}.", 2.0 * diag_len),
            (f"{pfx}top_chord_section_designation.{pair_id}.", chord_len),
            (f"{pfx}bottom_chord_section_designation.{pair_id}.", chord_len),
        ):
            des = _first_key_value(inputs, prefix)
            stype_prefix = prefix.replace("_designation.", "_type.")
            stype = _first_key_value(inputs, stype_prefix)
            props = _osdag_angle_props(des)
            if not props or not props[3]:
                continue
            found = True
            total_kg += props[3] * _section_multiplier(stype) * length_m * n_panels
    if not found:
        return None
    return total_kg / 1000.0


def _save(fig, out_dir, name):
    """Save a figure as PNG into *out_dir*; return the absolute path."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name + ".png")
    fig.savefig(path, dpi=styles.CHART["dpi"], bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    return path


def _threshold_line(ax, vertical=False):
    """Red-dashed UR = 1.0 reference line (pass/fail boundary)."""
    kw = dict(color=styles.CHART["threshold_color"],
              linestyle=styles.CHART["threshold_ls"],
              linewidth=styles.CHART["threshold_lw"])
    if vertical:
        ax.axvline(_UR_LIMIT, **kw)
    else:
        ax.axhline(_UR_LIMIT, **kw)


def _girder_labels(input_dict, output_dict):
    """G1..Gn labels from the backend keys, falling back to per_girder keys."""
    labels = [lbl for lbl, _ in get_girder_entries(input_dict or {})]
    if not labels:
        pg = ((output_dict or {}).get("design_results", {}) or {}).get("per_girder", {}) or {}
        labels = [g for g in sorted(pg.keys()) if not str(g).startswith("EB")]
    return labels


_CAT_SHORT = {
    "Strength – Flexure": "Flexure",
    "Strength - Flexure": "Flexure",
    "Strength – Shear": "Shear",
    "Strength - Shear": "Shear",
    "Interaction": "Interaction",
    "Lateral Torsional Buckling": "LTB",
    "Resistance to Longitudinal Shear": "Longit. Shear",
    "Fatigue": "Fatigue",
    "SLS Stress Limitation": "Stress (SLS)",
    "Deflection Check": "Deflection",
}


def _short_cat(label):
    return _CAT_SHORT.get(str(label).strip(), str(label).strip()[:16])


# ---------------------------------------------------------------------------
# 1. Steel plate girders — grouped UR bars (category x girder)
# ---------------------------------------------------------------------------

def girder_ur_chart(output_dict, input_dict, out_dir):
    """Grouped bar chart of per-girder utilization ratios by check category."""
    per_girder = ((output_dict or {}).get("design_results", {}) or {}).get("per_girder", {}) or {}
    labels = _girder_labels(input_dict, output_dict)
    if not per_girder or not labels:
        return None

    # category order -> {category label: {girder: ur}}
    cats = {}
    order = []
    for g in labels:
        gd = per_girder.get(g) or {}
        cat_urs = gd.get("category_urs") or {}
        for _key, cat in cat_urs.items():
            name = _short_cat(cat.get("label", _key))
            ur = _to_float(cat.get("max_dcr"))
            if ur is None:
                continue
            if name not in cats:
                cats[name] = {}
                order.append(name)
            cats[name][g] = ur
    if not cats:
        # fallback: flat util.* percentages (stored as %, e.g. 19.51 -> 0.195)
        flat = {
            "Flexure": "util.flexure", "Shear": "util.shear",
            "LTB": "util.ltb", "Interaction": "util.interaction",
            "Fatigue": "util.fatigue",
            "Longit. Shear": "util.long_trans_shear",
            "Stress (SLS)": "util.stress_limitation",
            "Deflection": "util.deflection_crack",
        }
        for name, key in flat.items():
            v = _to_float((output_dict or {}).get(key))
            if v is not None:
                cats[name] = {labels[0]: v / 100.0}
                order.append(name)
    if not cats:
        return None

    colors = styles.CHART["bar_colors"]
    n_g = len(labels)
    x = list(range(len(order)))
    width = 0.8 / max(1, n_g)

    styles.chart_rc()
    fig, ax = plt.subplots(figsize=(9.4, 4.6))
    for gi, g in enumerate(labels):
        vals = [cats[c].get(g, 0.0) for c in order]
        offs = [xi - 0.4 + width * (gi + 0.5) for xi in x]
        bars = ax.bar(offs, vals, width=width * 0.92, label=str(g),
                      color=colors[gi % len(colors)], edgecolor="white",
                      linewidth=0.4, zorder=3)
        for bar, v in zip(bars, vals):
            if v > _UR_LIMIT:
                ax.annotate(f"{v:.2f}", (bar.get_x() + bar.get_width() / 2, v),
                            xytext=(0, 2), textcoords="offset points",
                            ha="center", va="bottom", fontsize=7.5,
                            color=styles.CHART["fail_color"], fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(order, rotation=20, ha="right")
    ax.set_ylabel("Utilization Ratio (UR)")
    ax.set_title("Steel Plate Girders — Utilization Ratios by Design Check")
    ax.legend(ncol=min(n_g, 6), frameon=False, loc="upper left")
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)
    ymax = max([_UR_LIMIT] + [v for c in order for v in cats[c].values()])
    ax.set_ylim(0, ymax * 1.18 + 0.05)
    _threshold_line(ax)
    ax.annotate("UR = 1.0 (pass/fail threshold)", xy=(0.995, _UR_LIMIT),
                xycoords=("axes fraction", "data"), xytext=(0, 3),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=8, style="italic",
                color=styles.CHART["threshold_color"])
    return _save(fig, out_dir, "ur_girders")


# ---------------------------------------------------------------------------
# 2. Concrete deck slab — UR bars
# ---------------------------------------------------------------------------

_DECK_UR_LABELS = [
    ("ur_bot_uls", "Flexure — Bottom (ULS)"),
    ("ur_top_uls", "Flexure — Top (ULS)"),
    ("ur_oh_uls", "Flexure — Overhang (ULS)"),
    ("ur_bot_sls_s", "Rebar Stress — Bottom (SLS)"),
    ("ur_top_sls_s", "Rebar Stress — Top (SLS)"),
    ("ur_oh_sls_s", "Rebar Stress — Overhang (SLS)"),
    ("ur_bot_crack", "Crack Width — Bottom"),
    ("ur_top_crack", "Crack Width — Top"),
    ("ur_oh_crack", "Crack Width — Overhang"),
    ("ur_bot_shear", "One-Way Shear"),
    ("ur_bot_punch", "Punching Shear"),
    ("ur_composite_trans_shear", "Longitudinal Shear (composite)"),
    ("ur_composite_crack", "Crack Width (composite)"),
    ("ur_composite_conc_stress", "Concrete Stress (composite)"),
    ("ur_composite_rebar_stress", "Rebar Stress (composite)"),
]


def deck_ur_chart(output_dict, out_dir):
    """Horizontal bar chart of the concrete deck slab utilization ratios."""
    deck = (output_dict or {}).get("deck_design_results", {}) or {}
    pairs = []
    for key, label in _DECK_UR_LABELS:
        v = _to_float(deck.get(key))
        if v is not None:
            pairs.append((label, v))
    if not pairs:
        return None
    pairs.sort(key=lambda t: t[1])
    labels = [p[0] for p in pairs]
    vals = [p[1] for p in pairs]

    styles.chart_rc()
    fig, ax = plt.subplots(figsize=(8.6, max(3.2, 0.42 * len(vals) + 1.2)))
    colors = [styles.CHART["fail_color"] if v > _UR_LIMIT
              else styles.CHART["bar_colors"][0] for v in vals]
    bars = ax.barh(labels, vals, color=colors, edgecolor="white",
                   linewidth=0.4, zorder=3)
    for bar, v in zip(bars, vals):
        ax.annotate(f"{v:.2f}", (v, bar.get_y() + bar.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=8)
    ax.set_xlabel("Utilization Ratio (UR)")
    ax.set_title("Concrete Deck Slab — Utilization Ratios")
    ax.grid(axis="x", zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(vals + [_UR_LIMIT]) * 1.15 + 0.02)
    _threshold_line(ax, vertical=True)
    ax.annotate("UR = 1.0", xy=(_UR_LIMIT, 1.0), xycoords=("data", "axes fraction"),
                xytext=(4, 0), textcoords="offset points", ha="left",
                va="top", fontsize=8, style="italic",
                color=styles.CHART["threshold_color"])
    return _save(fig, out_dir, "ur_deck")


# ---------------------------------------------------------------------------
# 3. Cross bracing & end diaphragms — UR bars
# ---------------------------------------------------------------------------

def _transverse_urs(design_results):
    """[(label, ur)] from a crossbracing/end-diaphragm results dump."""
    out = []
    if not isinstance(design_results, dict):
        return out
    try:
        from osdagbridge.core.bridge_types.plate_girder.results_data import (
            _extract_osdag_summary)
    except Exception:
        return out
    for pair, members in sorted(design_results.items()):
        if not isinstance(members, dict):
            continue
        for member, force_types in members.items():
            if not isinstance(force_types, dict):
                continue
            mlabel = "Diag." if "diag" in str(member).lower() else "Chord"
            for ftype, raw in force_types.items():
                try:
                    ur = _extract_osdag_summary(raw or {}).get("efficiency")
                except Exception:
                    continue
                v = _to_float(ur)
                if v is not None:
                    tag = "T" if "tension" in str(ftype).lower() else "C"
                    out.append((f"{pair} {mlabel} ({tag})", v))
    return out


def transverse_ur_chart(output_dict, input_dict, out_dir):
    """Bar chart of cross-bracing and end-diaphragm utilization ratios.

    URs come from the Osdag member designs when available; otherwise the
    cross-bracing bars fall back to a code-based IS 800 axial check (clearly
    noted under the figure).  End-diaphragm bars require member forces which
    the headless designer does not always produce — they are omitted with an
    explanatory note in that case.
    """
    cb = _transverse_urs((output_dict or {}).get("crossbracing_design_results", {}))
    ed = _transverse_urs((output_dict or {}).get("end_diaphragm_design_results", {}))
    code_based = False
    if not cb:
        cb = _cb_code_urs(output_dict, input_dict)
        code_based = bool(cb)
    if not cb and not ed:
        return None
    data = cb + ed
    labels = [d[0] for d in data]
    vals = [d[1] for d in data]

    styles.chart_rc()
    fig, ax = plt.subplots(figsize=(8.6, max(3.0, 0.4 * len(vals) + 1.2)))
    colors = [styles.CHART["bar_colors"][1]] * len(cb) + \
             [styles.CHART["bar_colors"][2]] * len(ed)
    colors = [styles.CHART["fail_color"] if v > _UR_LIMIT else c
              for c, v in zip(colors, vals)]
    bars = ax.barh(labels, vals, color=colors, edgecolor="white",
                   linewidth=0.4, zorder=3)
    for bar, v in zip(bars, vals):
        ax.annotate(f"{v:.2f}", (v, bar.get_y() + bar.get_height() / 2),
                    xytext=(3, 0), textcoords="offset points",
                    va="center", ha="left", fontsize=8)
    ax.set_xlabel("Utilization Ratio (UR)")
    ax.set_title("Cross Bracing & End Diaphragms — Utilization Ratios")
    if cb and ed:
        from matplotlib.patches import Patch
        ax.legend(handles=[
            Patch(facecolor=styles.CHART["bar_colors"][1], label="Cross bracing"),
            Patch(facecolor=styles.CHART["bar_colors"][2], label="End diaphragm"),
        ], frameon=False, loc="lower right")
    elif code_based:
        ax.annotate("cross-bracing URs from IS 800 code-based axial check\n"
                    "(Osdag member-design results not available for this run)",
                    xy=(0.02, 0.96), xycoords="axes fraction", ha="left",
                    va="top", fontsize=7.5, style="italic", color="#555555")
    ax.grid(axis="x", zorder=0)
    ax.set_axisbelow(True)
    ax.set_xlim(0, max(vals + [_UR_LIMIT]) * 1.15 + 0.02)
    _threshold_line(ax, vertical=True)
    return _save(fig, out_dir, "ur_transverse")


# ---------------------------------------------------------------------------
# 4. Overall UR by primary element
# ---------------------------------------------------------------------------

def overall_ur_chart(output_dict, input_dict, out_dir):
    """Single bar per primary element: governing (maximum) utilization ratio."""
    od = output_dict or {}
    per_girder = (od.get("design_results", {}) or {}).get("per_girder", {}) or {}
    labels = _girder_labels(input_dict, od)
    girder_ur = None
    for g in labels or list(per_girder.keys()):
        gd = per_girder.get(g) or {}
        v = _to_float(gd.get("max_dcr"))
        if v is not None and (girder_ur is None or v > girder_ur):
            girder_ur = v

    deck = od.get("deck_design_results", {}) or {}
    deck_ur = None
    for k, v in deck.items():
        if str(k).startswith("ur_"):
            f = _to_float(v)
            if f is not None and (deck_ur is None or f > deck_ur):
                deck_ur = f

    cb_ur = ed_ur = None
    cb_from_code = False
    for lst, which in ((_transverse_urs(od.get("crossbracing_design_results", {})), "cb"),
                       (_transverse_urs(od.get("end_diaphragm_design_results", {})), "ed")):
        best = None
        for _lbl, v in lst:
            if best is None or v > best:
                best = v
        if which == "cb":
            cb_ur = best
        else:
            ed_ur = best
    if cb_ur is None:
        code_urs = _cb_code_urs(od, input_dict)
        if code_urs:
            cb_ur = max(v for _l, v in code_urs)
            cb_from_code = True

    series = [
        ("Steel Plate\nGirders", girder_ur),
        ("Concrete\nDeck Slab", deck_ur),
        ("Cross\nBracing", cb_ur),
        ("End\nDiaphragms", ed_ur),
    ]
    series = [(l, v) for l, v in series if v is not None]
    if not series:
        return None
    labels = [s[0] for s in series]
    vals = [s[1] for s in series]

    styles.chart_rc()
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    colors = [styles.CHART["fail_color"] if v > _UR_LIMIT
              else styles.CHART["bar_colors"][0] for v in vals]
    bars = ax.bar(labels, vals, color=colors, width=0.55,
                  edgecolor="white", linewidth=0.4, zorder=3)
    for bar, v in zip(bars, vals):
        ax.annotate(f"{v:.2f}", (bar.get_x() + bar.get_width() / 2, v),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("Governing Utilization Ratio (max UR)")
    ax.set_title("Overall Utilization Ratio by Primary Element")
    if cb_from_code:
        ax.annotate("cross bracing: IS 800 code-based check (Osdag member\n"
                    "design results not available for this run)",
                    xy=(0.02, 0.96), xycoords="axes fraction", ha="left",
                    va="top", fontsize=7.5, style="italic", color="#555555")
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(0, max(vals + [_UR_LIMIT]) * 1.2 + 0.05)
    _threshold_line(ax)
    ax.annotate("UR = 1.0 (pass/fail threshold)", xy=(0.99, _UR_LIMIT),
                xycoords=("axes fraction", "data"), xytext=(0, 3),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=8, style="italic",
                color=styles.CHART["threshold_color"])
    return _save(fig, out_dir, "ur_overall")


# ---------------------------------------------------------------------------
# Public aggregator for Chapter 5 (Section 5.5)
# ---------------------------------------------------------------------------

def ur_charts(output_dict, input_dict, out_dir):
    """Generate all UR charts.

    Returns (paths, notes): *paths* maps a figure key to the saved PNG path;
    *notes* lists human-readable reasons for any skipped chart so the report
    can state them instead of failing.
    """
    paths, notes = {}, []
    try:
        p = girder_ur_chart(output_dict, input_dict, out_dir)
        if p:
            paths["ur_girders"] = p
        else:
            notes.append("Per-girder utilization data not available — "
                         "girder UR chart omitted.")
    except Exception as exc:
        logger.warning("girder_ur_chart failed: %s", exc)
        notes.append("Girder UR chart could not be generated.")
    try:
        p = deck_ur_chart(output_dict, out_dir)
        if p:
            paths["ur_deck"] = p
        else:
            notes.append("Deck slab utilization data not available — "
                         "deck UR chart omitted.")
    except Exception as exc:
        logger.warning("deck_ur_chart failed: %s", exc)
        notes.append("Deck slab UR chart could not be generated.")
    try:
        p = transverse_ur_chart(output_dict, input_dict, out_dir)
        if p:
            paths["ur_transverse"] = p
        else:
            notes.append("Cross bracing / end diaphragm member utilization "
                         "results not available for this run — transverse "
                         "member UR chart omitted.")
    except Exception as exc:
        logger.warning("transverse_ur_chart failed: %s", exc)
        notes.append("Transverse member UR chart could not be generated.")
    try:
        p = overall_ur_chart(output_dict, input_dict, out_dir)
        if p:
            paths["ur_overall"] = p
        else:
            notes.append("No utilization data at all — overall UR chart omitted.")
    except Exception as exc:
        logger.warning("overall_ur_chart failed: %s", exc)
        notes.append("Overall UR chart could not be generated.")
    return paths, notes


# ---------------------------------------------------------------------------
# 5. Material quantity charts (Chapter 7 — BOQ / material take-off)
# ---------------------------------------------------------------------------

def _ed_steel_tonnage(output_dict, input_dict=None):
    """End-diaphragm structural steel tonnage (MT), computed from the designed
    member section mass (kg/m, persisted per girder-pair / member-entry by the
    designer) and the bracing geometry.  Each member entry is one X-braced
    panel: 2 diagonals + top chord + bottom chord.  When the UI section type
    is a double angle, the single-angle database mass is doubled.  Returns
    None when the section mass or geometry is missing."""
    od = output_dict or {}
    inputs = input_dict or {}
    ed_geom = ((od.get("end_diaphragm_forces_dict", {}) or {}).get("geometry", {}) or {})
    cb_geom = ((od.get("crossbracing_forces_dict", {}) or {}).get("geometry", {}) or {})
    geom = ed_geom or cb_geom
    diag_len = _to_float(geom.get("diagonal_length_m"))
    chord_len = _to_float(geom.get("horiz_proj_m"))
    if not diag_len or not chord_len:
        return None

    # X-bracing panel: 2 diagonals + top chord + bottom chord
    length_m = 2.0 * diag_len + 2.0 * chord_len

    # Mass keys look like
    # member_properties.end_diaphragm_details.section_properties.mass.<PAIR>.<MEM>
    # (pair spelled without the dash, e.g. G1G2, one entry per bracing member).
    mass_prefix = "member_properties.end_diaphragm_details.section_properties.mass."
    type_prefix = "member_properties.end_diaphragm_details.bracing_section."
    n_prefix_parts = len(mass_prefix.rstrip(".").split("."))
    total_kg = 0.0
    found = False
    for k, v in od.items():
        parts = str(k).split(".")
        if (str(k).startswith(mass_prefix)
                and len(parts) == n_prefix_parts + 2):
            m = _to_float(v)
            if m is not None and m > 0:
                found = True
                stype = _first_key_value(
                    inputs, type_prefix + parts[-2] + ".")
                total_kg += m * _section_multiplier(stype) * length_m
    if not found:
        return None
    return total_kg / 1000.0


def steel_tonnage_chart(inputs, output_dict, out_dir):
    """Structural steel tonnage bar chart (girders, cross bracing, end
    diaphragms, shear studs)."""
    inputs = inputs or {}
    output_dict = output_dict or {}

    def _qty(key):
        return _to_float(inputs.get(key))

    cb_t = None
    cb_parts = [_qty("bracing_top_wt_total"), _qty("bracing_bot_wt_total"),
                _qty("bracing_diag_wt_total")]
    if any(p is not None for p in cb_parts):
        cb_t = sum(p for p in cb_parts if p is not None)
    if cb_t is None:
        # fallback: compute from the selected bracing sections + geometry
        cb_t = _cb_code_tonnage(inputs, output_dict)

    ed_t = _ed_steel_tonnage(output_dict, inputs)

    series = [
        ("Plate\nGirders", _qty("steel_girders_wt_total")),
        ("Cross\nBracing", cb_t),
        ("End\nDiaphragms", ed_t),
        ("Shear Stud\nConnectors", _qty("shear_studs_wt_total")),
    ]
    notes = []
    if cb_t is None:
        notes.append("cross bracing")
    if ed_t is None:
        notes.append("end diaphragm")
    series = [(l, v) for l, v in series if v is not None]
    if not series:
        return None, notes

    labels = [s[0] for s in series]
    vals = [s[1] for s in series]

    styles.chart_rc()
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    colors = styles.CHART["bar_colors"][1] if len(vals) == 1 else None
    bars = ax.bar(labels, vals, color=colors or [
        styles.CHART["bar_colors"][i % len(styles.CHART["bar_colors"])]
        for i in range(len(vals))], width=0.55, edgecolor="white",
        linewidth=0.4, zorder=3)
    for bar, v in zip(bars, vals):
        ax.annotate(f"{v:.2f} MT", (bar.get_x() + bar.get_width() / 2, v),
                    xytext=(0, 3), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax.set_ylabel("Structural Steel Tonnage (MT)")
    ax.set_title("Structural Steel Tonnage by Component")
    ax.grid(axis="y", zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(0, max(vals) * 1.22 + 0.01)
    return _save(fig, out_dir, "qty_steel"), notes


def concrete_rebar_chart(inputs, out_dir):
    """Concrete deck volume (m³) vs reinforcement steel weight (MT)."""
    inputs = inputs or {}
    conc = _to_float(inputs.get("concrete_deck_vol_total"))
    rebar = _to_float(inputs.get("rebar_deck_wt_total"))
    if conc is None and rebar is None:
        return None
    labels, vals, units = [], [], []
    if conc is not None:
        labels.append("Concrete Deck\n(volume)")
        vals.append(conc)
        units.append("m³")
    if rebar is not None:
        labels.append("Reinforcement Steel\n(weight)")
        vals.append(rebar)
        units.append("MT")
    if len(vals) < 2:
        # single metric available — plain bar chart with its own unit
        styles.chart_rc()
        fig, ax = plt.subplots(figsize=(5.6, 3.8))
        bars = ax.bar(labels, vals, color=styles.CHART["bar_colors"][0],
                      width=0.45, zorder=3)
        for bar, v, u in zip(bars, vals, units):
            ax.annotate(f"{v:.2f} {u}", (bar.get_x() + bar.get_width() / 2, v),
                        xytext=(0, 3), textcoords="offset points",
                        ha="center", va="bottom", fontsize=9, fontweight="bold")
        ax.set_title("Material Quantity — " + units[0])
        ax.grid(axis="y", zorder=0)
        ax.set_axisbelow(True)
        ax.set_ylim(0, max(vals) * 1.25)
        return _save(fig, out_dir, "qty_concrete")

    styles.chart_rc()
    fig, ax1 = plt.subplots(figsize=(6.4, 4.0))
    x = [0, 1]
    b1 = ax1.bar([x[0]], [vals[0]], width=0.42, color=styles.CHART["bar_colors"][0],
                 edgecolor="white", zorder=3, label=labels[0])
    ax1.set_ylabel("Concrete Volume (m$^3$)", color=styles.CHART["bar_colors"][0])
    ax1.tick_params(axis="y", labelcolor=styles.CHART["bar_colors"][0])
    ax2 = ax1.twinx()
    b2 = ax2.bar([x[1]], [vals[1]], width=0.42, color=styles.CHART["bar_colors"][2],
                 edgecolor="white", zorder=3, label=labels[1])
    ax2.set_ylabel("Reinforcement Steel (MT)", color=styles.CHART["bar_colors"][2])
    ax2.tick_params(axis="y", labelcolor=styles.CHART["bar_colors"][2])
    ax1.set_xticks(x)
    ax1.set_xticklabels(labels)
    for bar, v, u in zip(list(b1) + list(b2), vals, units):
        ax_ = ax1 if bar in b1 else ax2
        ax_.annotate(f"{v:.2f} {u}", (bar.get_x() + bar.get_width() / 2, v),
                     xytext=(0, 3), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9, fontweight="bold")
    ax1.set_title("Concrete Deck Volume vs Reinforcement Steel Weight")
    ax1.grid(axis="y", zorder=0)
    ax1.set_axisbelow(True)
    ax1.set_ylim(0, vals[0] * 1.25)
    ax2.set_ylim(0, vals[1] * 1.25)
    return _save(fig, out_dir, "qty_concrete")


# ---------------------------------------------------------------------------
# Public aggregator for Chapter 7
# ---------------------------------------------------------------------------

def quantity_charts(inputs, output_dict, out_dir):
    """Generate the BOQ material-quantity charts.

    Returns (paths, notes) like :func:`ur_charts`.
    """
    paths, notes = {}, []
    try:
        p, skip = steel_tonnage_chart(inputs, output_dict, out_dir)
        if p:
            paths["qty_steel"] = p
        if skip:
            notes.append("Quantity data not computed for: " + ", ".join(skip) +
                         " — corresponding bars omitted.")
        elif not p:
            notes.append("Material quantity data not available — steel "
                         "tonnage chart omitted.")
    except Exception as exc:
        logger.warning("steel_tonnage_chart failed: %s", exc)
        notes.append("Steel tonnage chart could not be generated.")
    try:
        p = concrete_rebar_chart(inputs, out_dir)
        if p:
            paths["qty_concrete"] = p
        else:
            notes.append("Concrete / reinforcement quantity data not "
                         "available — chart omitted.")
    except Exception as exc:
        logger.warning("concrete_rebar_chart failed: %s", exc)
        notes.append("Concrete vs reinforcement chart could not be generated.")
    return paths, notes
