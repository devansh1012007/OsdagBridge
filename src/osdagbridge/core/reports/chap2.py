# Chapter 2: Input Parameters — exact LaTeX template match
#
# All tables are assembled through the centralized style system
# (osdagbridge.core.reports.styles): captions are correctly terminated and
# every table repeats its column headers across page breaks via
# \endfirsthead / \endhead.


from osdagbridge.core.utils.common import (
    KEY_CARRIAGEWAY_WIDTH,
    KEY_CB_LOAD,
    KEY_CB_TYPE,
    KEY_CROSS_BRACING,
    KEY_DECK_CONCRETE_GRADE_BASIC,
    KEY_DESIGN_MODE,
    KEY_DO_GAMMA_C_BASIC,
    KEY_DO_GAMMA_FLT,
    KEY_DO_GAMMA_M0,
    KEY_DO_GAMMA_M1,
    KEY_DO_GAMMA_MF,
    KEY_DO_GAMMA_S,
    KEY_DO_GAMMA_V,
    KEY_END_DIAPHRAGM,
    KEY_FOOTPATH,
    KEY_GIRDER,
    KEY_INCLUDE_MEDIAN,
    KEY_MD_TYPE,
    KEY_MP_CB_BRACING_SECTION_DESIGNATION,
    KEY_MP_CB_MEMBER_ID,
    KEY_MP_CB_SELECT_GIRDERS,
    KEY_MP_CB_SPACING,
    KEY_MP_CB_TYPE,
    KEY_MP_ED_BRACING_SECTION_DESIGNATION,
    KEY_MP_ED_MEMBER_ID,
    KEY_MP_ED_SELECT_GIRDERS,
    KEY_MP_ED_TYPE,
    KEY_MP_GD_MEMBER_ID,
    KEY_MP_GD_SELECT_GIRDER,
    KEY_MP_GIRDER_BOTTOM_FLANGE_THICKNESS,
    KEY_MP_GIRDER_BOTTOM_FLANGE_WIDTH,
    KEY_MP_GIRDER_DEPTH,
    KEY_MP_GIRDER_SYMMETRY,
    KEY_MP_GIRDER_TOP_FLANGE_THICKNESS,
    KEY_MP_GIRDER_TOP_FLANGE_WIDTH,
    KEY_MP_GIRDER_TORSIONAL_RESTRAINT,
    KEY_MP_GIRDER_TYPE,
    KEY_MP_GIRDER_WARPING_RESTRAINT,
    KEY_MP_GIRDER_WEB_THICKNESS,
    KEY_MP_GIRDER_WEB_TYPE,
    KEY_MP_STIFFENER_BEARING_THICKNESS,
    KEY_MP_STIFFENER_INTERMEDIATE,
    KEY_MP_STIFFENER_INTERMEDIATE_SPACING,
    KEY_MP_STIFFENER_INTERMEDIATE_THICKNESS,
    KEY_MP_STIFFENER_LONGITUDINAL,
    KEY_MP_STIFFENER_NO_BEARING_STIFFENERS,
    KEY_MP_STIFFENER_SPACING,
    KEY_RL_LOAD_VALUE,
    KEY_RL_TYPE,
    KEY_SD_SHEAR_DIAMETER,
    KEY_SD_SHEAR_HEIGHT,
    KEY_SD_SHEAR_STUDS_PER_SECTION,
    KEY_SD_SHEAR_ULTIMATE_STRENGTH,
    KEY_SD_SHEAR_YIELD_STRENGTH,
    KEY_SKEW_ANGLE,
    KEY_SPAN,
    KEY_STRUCTURE_TYPE,
    KEY_TS_DECK_OVERHANG,
    KEY_TS_DECK_THICKNESS,
    KEY_TS_FOOTPATH_WIDTH,
    KEY_TS_GIRDER_SPACING,
    KEY_TS_NO_OF_GIRDERS,
    KEY_TS_OVERALL_WIDTH,
    KEY_WC_LD_LANE_TABLE_COUNT,
    KEY_WC_MATERIAL,
    KEY_WC_THICKNESS
)

from osdagbridge.core.reports.report_utils import _render_value, get_girder_entries, _tex
from osdagbridge.core.reports.styles import longtable, ROW_END


def ch2_input_parameters(m, input_dict, output_dict=None):
    girder_entries = get_girder_entries(input_dict)
    n_girders = len(girder_entries)

    # Median row only shown when the user included a median
    median_row = ""
    if str(input_dict.get(KEY_INCLUDE_MEDIAN, "")).strip().lower() in ("yes", "true", "1"):
        median_row = (r"\textnormal{Median Type} & "
                      + _render_value(input_dict, KEY_MD_TYPE)
                      + " " + ROW_END + r"\hline" + "\n")

    def _kv_row(param, value):
        return (r"\textnormal{" + param + r"} & " + value + " " + ROW_END
                + r"\hline" + "\n")

    location_rows = "".join([
        _kv_row("Project Location", _tex(m.project_location)),
        _kv_row("Latitude / Longitude",
                (_render_value(input_dict, 'latitude') + ', '
                 + _render_value(input_dict, 'longitude'))),
        _kv_row("Seismic Zone (IRC 6)", _render_value(input_dict, 'seismic_zone')),
        _kv_row("Basic Wind Speed (IRC 6)",
                _render_value(input_dict, 'wind_speed', ' m/s')),
        _kv_row("Shade Temp. Max / Min (IRC 6)",
                (_render_value(input_dict, 'shade_temp_max', '') + r" $^\circ$C / "
                 + _render_value(input_dict, 'shade_temp_min', '') + r" $^\circ$C")),
    ])
    location_table = longtable(
        col_spec="|L{5.5cm}|L{8.5cm}|",
        caption="Project Location",
        header=r"\textbf{parameter} & \textbf{value}",
        body=location_rows, ncols=2, vspace_before="",
        label="subsec:project-location")

    geometry_rows = "".join([
        _kv_row("Type of Structure", _render_value(input_dict, KEY_STRUCTURE_TYPE)),
        _kv_row("Span (m)", _render_value(input_dict, KEY_SPAN, ' m')),
        _kv_row("Carriageway Width (m)", _render_value(input_dict, KEY_CARRIAGEWAY_WIDTH, ' m')),
        _kv_row("Include Median", _render_value(input_dict, KEY_INCLUDE_MEDIAN)),
        _kv_row("Footpath", _render_value(input_dict, KEY_FOOTPATH)),
        _kv_row("Skew Angle (degrees)",
                (_render_value(input_dict, KEY_SKEW_ANGLE, '°')
                 + r" (IRC 24 Cl. 504.8 limit: $\pm$15°)")),
    ])
    geometry_table = longtable(
        col_spec="|L{5.5cm}|L{8.5cm}|",
        caption="Bridge Geometry",
        header=r"\textbf{parameter} & \textbf{value}",
        body=geometry_rows, ncols=2, label="subsec:bridge-geometry")

    material_rows = "".join([
        _kv_row("Girder Steel Grade (IS 2062)", _render_value(input_dict, KEY_GIRDER)),
        _kv_row("Cross Bracing Steel Grade", _render_value(input_dict, KEY_CROSS_BRACING)),
        _kv_row("End Diaphragm Steel Grade", _render_value(input_dict, KEY_END_DIAPHRAGM)),
        _kv_row("Concrete Deck Grade (IRC 22)", _render_value(input_dict, KEY_DECK_CONCRETE_GRADE_BASIC)),
    ])
    material_table = longtable(
        col_spec="|L{5.5cm}|L{8.5cm}|",
        caption="Material Selection",
        header=r"\textbf{parameter} & \textbf{value}",
        body=material_rows, ncols=2, label="subsec:material")

    ts_rows = "".join([
        _kv_row("Overall Bridge Width (m)", _render_value(input_dict, KEY_TS_OVERALL_WIDTH)),
        _kv_row("No. of Girders", _render_value(input_dict, KEY_TS_NO_OF_GIRDERS)),
        _kv_row("Girder Spacing (m)", _render_value(input_dict, KEY_TS_GIRDER_SPACING, ' m')),
        _kv_row("Deck Overhang Width (m)", _render_value(input_dict, KEY_TS_DECK_OVERHANG, ' m')),
        _kv_row("Deck Thickness (mm)", _render_value(input_dict, KEY_TS_DECK_THICKNESS, ' mm')),
        _kv_row("Footpath Width (m)",
                (_render_value(input_dict, KEY_TS_FOOTPATH_WIDTH)
                 + r" (IRC 5 Cl. 104.3.6 min: 1.5 m)")),
        _kv_row("No. of Traffic Lanes",
                (_render_value(input_dict, KEY_WC_LD_LANE_TABLE_COUNT)
                 + r" (per IRC 5 Cl. 104.3.1)")),
    ])
    typical_section_table = longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Typical Section Details",
        header=r"\textbf{parameter} & \textbf{value}",
        body=ts_rows, ncols=2)

    comp_rows = "".join([
        _kv_row("Crash Barrier Type", _render_value(input_dict, KEY_CB_TYPE)),
        _kv_row("Crash Barrier Load (kN/m)", _render_value(input_dict, KEY_CB_LOAD)),
        median_row,
        _kv_row("Railing Type", _render_value(input_dict, KEY_RL_TYPE)),
        _kv_row("Railing Load (kN/m)", _render_value(input_dict, KEY_RL_LOAD_VALUE)),
        _kv_row("Wearing Course Material", _render_value(input_dict, KEY_WC_MATERIAL)),
        _kv_row("Wearing Course Thickness (mm)", _render_value(input_dict, KEY_WC_THICKNESS, ' mm')),
    ])
    components_table = longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Components Details",
        header=r"\textbf{parameter} & \textbf{value}",
        body=comp_rows, ncols=2)

    return r"""
\chapter{Input Parameters}

\setlength{\abovecaptionskip}{2pt}
\setlength{\belowcaptionskip}{2pt}

This section documents all inputs provided to OsdagBridge. User-provided inputs are clearly distinguished from software-assumed defaults. Where the user did not supply a value, the software has applied the IRC/IS code default or an empirical guideline; these are annotated with an asterisk (\sdstar{}).

\section{Basic Inputs (User-Defined)}
\label{sec:basic-inputs}

\noindent\textit{Note: These inputs are mandatory and were provided by the user.}

""" + location_table + r"""
""" + geometry_table + r"""
""" + material_table + r"""

\newpage
\section{Additional Inputs}
\label{sec:additional-inputs}

Where the user has modified additional inputs, those values are reported here. Where no modification was made, the software default is shown.

""" + typical_section_table + r"""
""" + components_table + r"""

""" + _girder_tables(input_dict, n_girders) + r"""

""" + _bracing_tables(input_dict, n_girders) + r"""

""" + _shear_connector_table(input_dict, output_dict) + r"""

""" + _safety_factors_table(input_dict)


def _girder_tables(input_dict, n_girders):
    # Fetch backend-populated labels via exact suffix pattern (defaults.py)
    # KEY_MP_GD_SELECT_GIRDER.G{i}    = 'G{i}'
    # KEY_MP_GD_MEMBER_ID.G{i}.M1     = 'G{i}M1'
    # All other girder/stiffener keys: {BASE_KEY}.G{i}.M1
    n = n_girders if n_girders >= 1 else 1
    girder_entries = get_girder_entries(input_dict)
    if not girder_entries:
        girder_entries = [(f"Girder {i}", f"M1") for i in range(1, n + 1)]

    entries_for_table = [
        (lbl, mid, i)
        for i, (lbl, mid) in enumerate(
            girder_entries,
            start=1,
        )
    ]

    # Helper: one girder-dimension row
    def _dim_row(g_lbl, i):
        return (g_lbl + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_DEPTH}.G{i}.M1", ' mm'))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_WEB_THICKNESS}.G{i}.M1", ' mm'))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_TOP_FLANGE_WIDTH}.G{i}.M1", ' mm'))
                + ', '
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_TOP_FLANGE_THICKNESS}.G{i}.M1", ' mm'))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_BOTTOM_FLANGE_WIDTH}.G{i}.M1", ' mm'))
                + ', '
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_BOTTOM_FLANGE_THICKNESS}.G{i}.M1", ' mm'))
                + " " + ROW_END
                + r"\hline" + "\n")

    # Helper: one general-info row
    def _gen_row(g_lbl, m_id, i):
        return (g_lbl + r""" & """ + m_id + r""" & """
                + (_render_value(input_dict, KEY_DESIGN_MODE))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_TYPE}.G{i}.M1"))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_SYMMETRY}.G{i}.M1"))
                + " " + ROW_END
                + r"\hline" + "\n")

    # Helper: one restraint/stiffener row
    def _rst_row(g_lbl, i):
        return (g_lbl + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_TORSIONAL_RESTRAINT}.G{i}.M1"))
                + ', '
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_WARPING_RESTRAINT}.G{i}.M1"))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_GIRDER_WEB_TYPE}.G{i}.M1"))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_STIFFENER_INTERMEDIATE}.G{i}.M1"))
                + '; Spacing: '
                + (_render_value(input_dict, f"{KEY_MP_STIFFENER_INTERMEDIATE_SPACING}.G{i}.M1", ' mm'))
                + '; Thickness: '
                + (_render_value(input_dict, f"{KEY_MP_STIFFENER_INTERMEDIATE_THICKNESS}.G{i}.M1", ' mm'))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_STIFFENER_LONGITUDINAL}.G{i}.M1"))
                + r""" & No.: """
                + (_render_value(input_dict, f"{KEY_MP_STIFFENER_NO_BEARING_STIFFENERS}.G{i}.M1"))
                + '; Spacing: '
                + (_render_value(input_dict, f"{KEY_MP_STIFFENER_SPACING}.G{i}.M1", ' mm'))
                + '; Thickness: '
                + (_render_value(input_dict, f"{KEY_MP_STIFFENER_BEARING_THICKNESS}.G{i}.M1", ' mm'))
                + " " + ROW_END
                + r"\hline" + "\n")

    gen_rows = "".join([_gen_row(g_lbl, m_id, i) for g_lbl, m_id, i in entries_for_table])
    dim_rows = "".join([_dim_row(g_lbl, i) for g_lbl, _, i in entries_for_table])
    rst_rows = "".join([_rst_row(g_lbl, i) for g_lbl, _, i in entries_for_table])

    # Column widths sized for the 15.92 cm text width budget (styles.py):
    # "Member" (bold 12pt) is 1.74 cm wide, so col 2 needs >= 1.8 cm.
    gen_table = longtable(
        col_spec="|L{2.0cm}|L{1.8cm}|p{3.5cm}|p{3.5cm}|p{3.5cm}|",
        caption="Girder General Information",
        header=(r"\textbf{Girder} & \textbf{Member ID} & \textbf{Design Mode} & "
                r"\textbf{Girder Type} & \textbf{Girder Symmetry}"),
        body=gen_rows, ncols=5, vspace_before=r"\newpage" + "\n" + r"\vspace{0.4em}")

    dim_table = longtable(
        col_spec="|L{1.7cm}|L{2.2cm}|L{1.7cm}|p{4.4cm}|p{4.4cm}|",
        caption="Girder Section Dimensions",
        header=(r"\textbf{Girder} & \textbf{Total Depth, D (mm)} & "
                r"\textbf{Web, $t_w$ (mm)} & "
                r"\textbf{Top Flange (b\textsubscript{tf}, t\textsubscript{tf}) mm} & "
                r"\textbf{Bottom Flange (b\textsubscript{bf}, t\textsubscript{bf}) mm}"),
        body=dim_rows, ncols=5, vspace_before=r"\vspace{0.6em}")

    # Column widths sized for the 15.92 cm budget: "Philosophy" needs 2.3 cm,
    # "Longitudinal" 2.64 cm, "Stiffener" 1.76 cm, "Intermediate" 2.68 cm.
    rst_table = longtable(
        col_spec="|L{1.4cm}|p{2.2cm}|p{2.35cm}|p{3.0cm}|p{2.75cm}|p{2.0cm}|",
        caption="Girder Restraint and Stiffener Details",
        header=(r"\textbf{Girder} & \textbf{Torsional / Warping Restraint} & "
                r"\textbf{Web Philosophy} & \textbf{Intermediate Stiffeners} & "
                r"\textbf{Longitudinal Stiffeners} & \textbf{Bearing Stiffener}"),
        body=rst_rows, ncols=6, vspace_before=r"\vspace{0.6em}")

    return gen_table + "\n" + dim_table + "\n" + rst_table + "\n"


def _bracing_tables(input_dict, n_girders):
    n = n_girders if n_girders >= 2 else 2
    panels = [
        (
            _render_value(input_dict, f"{KEY_MP_CB_SELECT_GIRDERS}.G{i}G{i+1}.B{i}M1"),
            _render_value(input_dict, f"{KEY_MP_CB_MEMBER_ID}.G{i}G{i+1}.B{i}M1"),
            _render_value(input_dict, f"{KEY_MP_ED_SELECT_GIRDERS}.G{i}G{i+1}.E{i}M1"),
            _render_value(input_dict, f"{KEY_MP_ED_MEMBER_ID}.G{i}G{i+1}.E{i}M1"),
            i
        )
        for i in range(1, n)
    ]

    # Helper: one cross-bracing row (all locations share same bracing config)
    def _cb_row(location, member_ids, i):
        return (location + r""" & """ + member_ids + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_CB_TYPE}.G{i}G{i+1}.B{i}M1"))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_CB_BRACING_SECTION_DESIGNATION}.G{i}G{i+1}.B{i}M1"))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_CB_SPACING}.G{i}G{i+1}.B{i}M1", ' m'))
                + " " + ROW_END
                + r"\hline" + "\n")

    # Helper: one end-diaphragm row (all locations share same config)
    def _ed_row(location, member_ids, i):
        return (location + r""" & """ + member_ids + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_ED_TYPE}.G{i}G{i+1}.E{i}M1"))
                + r""" & """
                + (_render_value(input_dict, f"{KEY_MP_ED_BRACING_SECTION_DESIGNATION}.G{i}G{i+1}.E{i}M1"))
                + " " + ROW_END
                + r"\hline" + "\n")

    cb_rows = "".join([_cb_row(cb_loc, cb_ids, i) for cb_loc, cb_ids, _, _, i in panels])
    ed_rows = "".join([_ed_row(ed_loc, ed_ids, i) for _, _, ed_loc, ed_ids, i in panels])

    cb_table = longtable(
        col_spec="|L{2.2cm}|L{2.2cm}|L{3.0cm}|L{2.5cm}|C{1.8cm}|",
        caption="Member Properties: Cross Bracing Details",
        header=(r"\textbf{Location} & \textbf{Member IDs} & "
                r"\textbf{Type of Bracing} & \textbf{Bracing Section} & "
                r"\textbf{Spacing (m)}"),
        body=cb_rows, ncols=5, vspace_before=r"\newpage" + "\n" + r"\vspace{0.4em}",
        colsep="4pt")

    ed_table = longtable(
        col_spec="|L{2.2cm}|L{2.2cm}|L{3.0cm}|L{2.5cm}|",
        caption="Member Properties: End Diaphragm Details",
        header=(r"\textbf{Location} & \textbf{Member IDs} & "
                r"\textbf{Type of Bracing} & \textbf{Bracing Section}"),
        body=ed_rows, ncols=4, vspace_before=r"\vspace{0.4em}",
        colsep="4pt")

    return cb_table + "\n" + ed_table + "\n"


def _shear_connector_table(input_dict, output_dict=None):
    # Stud computed properties live in output_dict (populated by store_design_results)
    od = output_dict or {}

    def _row(param, value):
        return (r"\textnormal{" + param + r"} & " + value + " " + ROW_END
                + r"\hline" + "\n")

    rows = "".join([
        _row("Stud Diameter (mm)", _render_value(od, KEY_SD_SHEAR_DIAMETER, ' mm')),
        _row("Stud Height (mm)", _render_value(od, KEY_SD_SHEAR_HEIGHT, ' mm')),
        _row("Stud $f_y$ (MPa)", _render_value(od, KEY_SD_SHEAR_YIELD_STRENGTH, ' MPa')),
        _row("Stud $f_u$ (MPa)", _render_value(od, KEY_SD_SHEAR_ULTIMATE_STRENGTH, ' MPa')),
        _row("No. of Studs per Section", _render_value(od, KEY_SD_SHEAR_STUDS_PER_SECTION)),
    ])
    return longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Shear Connector Details",
        header=r"\textbf{parameter} & \textbf{value}",
        body=rows, ncols=2,
        vspace_before=r"\vspace{2.2em}",
        label="subsec:shear-connectors")


def _safety_factors_table(input_dict):
    def _row(param, value):
        return (r"\textnormal{" + param + r"} & " + value + " " + ROW_END
                + r"\hline" + "\n")

    rows = "".join([
        _row(r"$\gamma_{M0}$ (Yielding / Buckling)", _render_value(input_dict, KEY_DO_GAMMA_M0)),
        _row(r"$\gamma_{M1}$ (Ultimate Stress)", _render_value(input_dict, KEY_DO_GAMMA_M1)),
        _row(r"$\gamma_C$ (Concrete, Basic)", _render_value(input_dict, KEY_DO_GAMMA_C_BASIC)),
        _row(r"$\gamma_s$ (Reinforcement)", _render_value(input_dict, KEY_DO_GAMMA_S)),
        _row(r"$\gamma_v$ (Shear Connectors)", _render_value(input_dict, KEY_DO_GAMMA_V)),
        _row(r"$\gamma_{flt}$ (Fatigue Load)", _render_value(input_dict, KEY_DO_GAMMA_FLT)),
        _row(r"$\gamma_{Mft}$ (Fatigue Strength)", _render_value(input_dict, KEY_DO_GAMMA_MF)),
    ])
    return (
        r"\label{subsec:safety-factors}" + "\n"
        + r"\noindent\textit{Note: All values are per IRC 22 Table 1 unless user-modified.}"
        + "\n\n"
        + longtable(
            col_spec="|L{5.5cm}|p{9.7cm}|",
            caption="Partial Safety Factors",
            header=r"\textbf{parameter} & \textbf{value}",
            body=rows, ncols=2,
            vspace_before=r"\vspace{2.2em}")
    )
