# =============================================================================
# Chapter 3: Loads and Load Combinations
# Extracted from report_generator.py — DO NOT add business logic here.
#
# All tables are assembled through the centralized style system
# (osdagbridge.core.reports.styles) so captioning, header repetition
# (\endfirsthead / \endhead) and cell padding come from a single source.
#
# The Live Loads (LL) block is split into three distinct tables:
#   3.3  Vehicle Live Loads          — one row per vehicle class selected in
#                                      the UI loading tab (impact factor per
#                                      class, IRC 6 references)
#   3.4  Vehicle Live Load Parameters — bridge-level dynamic parameters
#                                      (design lanes, braking load,
#                                      centrifugal forces) with unit columns
#   3.5  Footway / Footpath Loads    — footpath live-load definition,
#                                      clearly separated from vehicle loads
# =============================================================================

from osdagbridge.core.utils.common import (
    KEY_CB_LOAD,
    KEY_CARRIAGEWAY_WIDTH,
    KEY_LL_CUSTOM_VEHICLES,
    KEY_LL_FOOTPATH_PRESSURE_MODE,
    KEY_LL_FOOTPATH_PRESSURE_VALUE,
    KEY_LL_IRC_70R_BOGIE,
    KEY_LL_IRC_70R_TRACKED,
    KEY_LL_IRC_70R_WHEELED,
    KEY_LL_IRC_AA_TRACKED,
    KEY_LL_IRC_AA_WHEELED,
    KEY_LL_IRC_CLASS_A,
    KEY_LL_IRC_CLASS_FATIGUE,
    KEY_LL_IRC_CLASS_SV,
    KEY_MATERIAL_DECK_DENSITY,
    KEY_MATERIAL_GIRDER_DENSITY,
    KEY_PL_SELF_WEIGHT_FACTOR,
    KEY_RL_LOAD_VALUE,
    KEY_SL_DAMPING,
    KEY_SL_DEAD_LOAD_MODE,
    KEY_SL_DEAD_LOAD_VALUE,
    KEY_SL_HORIZONTAL_COEFF,
    KEY_SL_IMPORTANCE_FACTOR,
    KEY_SL_LIVE_LOAD_MODE,
    KEY_SL_LIVE_LOAD_VALUE,
    KEY_SL_SEISMIC_ZONE,
    KEY_SL_SOIL_TYPE,
    KEY_SL_SPECTRAL_COEFF,
    KEY_SL_TIME_PERIOD,
    KEY_SL_VERTICAL_COEFF,
    KEY_SL_ZONE_FACTOR,
    KEY_SPAN,
    KEY_TL_BRIDGE_TEMP_MAX,
    KEY_TL_BRIDGE_TEMP_MIN,
    KEY_TL_HIGHEST_MAX_TEMP,
    KEY_TL_LOWEST_MIN_TEMP,
    KEY_TL_TEMP_FALL,
    KEY_TL_TEMP_RISE,
    KEY_TS_FOOTPATH_WIDTH,
    KEY_WC_LD_LANE_TABLE_COUNT,
    KEY_WC_MATERIAL,
    KEY_WC_THICKNESS,
    KEY_WL_AVG_EXPOSED_HEIGHT,
    KEY_WL_BASIC_WIND_SPEED,
    KEY_WL_HOURLY_MEAN_WIND,
    KEY_WL_HOURLY_WIND_PRESSURE,
    KEY_WL_LONGITUDINAL_WIND_FORCE,
    KEY_WL_TERRAIN_TYPE,
    KEY_WL_TRANSVERSE_WIND_FORCE,
    KEY_WL_VERTICAL_WIND_FORCE
)

from osdagbridge.core.reports.report_utils import _tex, _render_value
from osdagbridge.core.reports.styles import longtable, ROW_END, HEADER_END


# ---------------------------------------------------------------------------
# Live-load helpers (vehicle selection mirrors the UI loading tab)
# ---------------------------------------------------------------------------

def _selected_vehicles(input_dict):
    """(class name, IRC 6 clause) for every vehicle selected in the UI
    loading tab of additional inputs, plus user-defined custom vehicles."""
    vehicles = []
    if input_dict.get(KEY_LL_IRC_CLASS_A):
        vehicles.append(("Class A", "Cl. 204.1"))
    if input_dict.get(KEY_LL_IRC_70R_WHEELED):
        vehicles.append(("Class 70R (Wheeled)", "Cl. 204.1"))
    if input_dict.get(KEY_LL_IRC_70R_TRACKED):
        vehicles.append(("Class 70R (Tracked)", "Cl. 204.1"))
    if input_dict.get(KEY_LL_IRC_AA_WHEELED):
        vehicles.append(("Class AA (Wheeled)", "Cl. 204.2"))
    if input_dict.get(KEY_LL_IRC_AA_TRACKED):
        vehicles.append(("Class AA (Tracked)", "Cl. 204.2"))
    if input_dict.get(KEY_LL_IRC_CLASS_SV):
        vehicles.append(("Class SV (Special Vehicle)", "Cl. 204.5"))
    if input_dict.get(KEY_LL_IRC_70R_BOGIE):
        vehicles.append(("Class 70R (Bogie)", "Cl. 204.1"))
    if input_dict.get(KEY_LL_IRC_CLASS_FATIGUE):
        vehicles.append(("Class Fatigue", "Cl. 204.6"))

    custom = input_dict.get(KEY_LL_CUSTOM_VEHICLES)
    if custom and isinstance(custom, list):
        for c in custom:
            if isinstance(c, dict) and c.get('name'):
                vehicles.append((str(c['name']), "User-defined"))
            elif isinstance(c, str):
                vehicles.append((c, "User-defined"))
    return vehicles


def _impact_factors(input_dict, span_m):
    """Impact factors (1 + IM) by vehicle family, per IRC 6 Cl. 208.2/208.3."""
    from osdagbridge.core.utils.codes.irc6_2017 import IRC6_2017
    im_a = im_heavy = None
    if span_m is not None:
        try:
            if input_dict.get(KEY_LL_IRC_CLASS_A):
                im_a = 1.0 + IRC6_2017.cl_208_2_impact_factor(span_m)
            is_wheeled_heavy = (
                input_dict.get(KEY_LL_IRC_70R_WHEELED)
                or input_dict.get(KEY_LL_IRC_AA_WHEELED)
                or input_dict.get(KEY_LL_IRC_70R_BOGIE)
            )
            is_tracked_heavy = (
                input_dict.get(KEY_LL_IRC_70R_TRACKED)
                or input_dict.get(KEY_LL_IRC_AA_TRACKED)
            )
            if is_wheeled_heavy or is_tracked_heavy:
                im_heavy = 1.0 + IRC6_2017.cl_208_3_impact_factor(span_m)
        except Exception:
            pass
    return im_a, im_heavy


def _design_lanes(input_dict):
    """Number of traffic lanes for design — the UI lane-table count when
    populated, else derived from the carriageway width per IRC 6 Table 6."""
    lanes = input_dict.get(KEY_WC_LD_LANE_TABLE_COUNT)
    if lanes not in (None, ""):
        try:
            return int(lanes)
        except (TypeError, ValueError):
            pass
    cw = input_dict.get(KEY_CARRIAGEWAY_WIDTH)
    if cw not in (None, ""):
        try:
            from osdagbridge.core.utils.codes.irc6_2017 import IRC6_2017
            return int(IRC6_2017.table_6(float(cw)))
        except Exception:
            pass
    return None


def _braking_force(input_dict, lanes):
    """(kN, tonnes) braking force per IRC 6 Cl. 211.2.

    cl_211_2_braking_force returns the force in N (20% of the Class A
    wheel loads of the first two lanes + 5% of Class 70R for the rest).
    """
    if lanes in (None, ""):
        return None, None
    try:
        from osdagbridge.core.utils.codes.irc6_2017 import IRC6_2017
        force_n = IRC6_2017.cl_211_2_braking_force(int(lanes))
        return force_n / 1000.0, force_n / 9810.0
    except Exception:
        return None, None


def _row(param, value, unit, ref):
    """One table row with a dedicated unit column (all cells pre-escaped)."""
    return (param + r" & " + value + r" & " + unit + r" & " + ref
            + " " + ROW_END + r"\hline" + "\n")


def ch3_loads(input_dict):
    from osdagbridge.core.utils.codes.irc6_2017 import IRC6_2017

    span = input_dict.get(KEY_SPAN)
    try:
        span_m = float(span) if span not in (None, "") else None
    except (TypeError, ValueError):
        span_m = None

    vehicles = _selected_vehicles(input_dict)
    im_a, im_heavy = _impact_factors(input_dict, span_m)
    lanes = _design_lanes(input_dict)
    braking_kN, braking_t = _braking_force(input_dict, lanes)

    # ── Table 3.3 — Vehicle Live Loads (one row per selected vehicle) ──────
    if vehicles:
        v_rows = []
        for i, (name, ref) in enumerate(vehicles, start=1):
            if name.startswith("Class A") and not name.startswith("Class AA"):
                im = f"{im_a:.3f}" if im_a is not None else "N/A"
            elif name.startswith(("Class AA", "Class 70R", "Class SV")):
                im = f"{im_heavy:.3f}" if im_heavy is not None else "N/A"
            else:
                im = "N/A"
            v_rows.append(
                f"{i} & {_tex(name)} & {ref} & {im} " + HEADER_END
                + r"\hline" + "\n"
            )
        vehicle_ll_table = longtable(
            col_spec="|C{1.0cm}|L{5.2cm}|C{2.6cm}|C{3.6cm}|",
            caption="Vehicle Live Loads (LL) — as selected in the loading tab",
            header=(r"\textbf{S.N.} & \textbf{Vehicle Class} & "
                    r"\textbf{IRC 6 Ref.} & "
                    r"\textbf{Impact Factor (1 + IM)}"),
            body="".join(v_rows),
            ncols=4,
        )
        vehicle_note = (r"\noindent\textit{Note: Vehicle classes reflect the "
                        r"selection made in the \emph{Loading} tab of the "
                        r"additional inputs. Impact factors are computed from "
                        r"the span per IRC 6 Cl. 208.2 (Class A/B) and "
                        r"Cl. 208.3 (Class AA / 70R).}" + "\n")
    else:
        vehicle_ll_table = longtable(
            col_spec="|C{1.0cm}|L{5.2cm}|C{2.6cm}|C{3.6cm}|",
            caption="Vehicle Live Loads (LL) — as selected in the loading tab",
            header=(r"\textbf{S.N.} & \textbf{Vehicle Class} & "
                    r"\textbf{IRC 6 Ref.} & "
                    r"\textbf{Impact Factor (1 + IM)}"),
            body=r"1 & \emph{None selected} & --- & --- \\" + "\n" + r"\hline",
            ncols=4,
        )
        vehicle_note = (r"\noindent\textit{Note: No vehicle live load class is "
                        r"selected in the loading tab.}" + "\n")

    # ── Table 3.4 — Vehicle live-load parameters (units + references) ──────
    lanes_str = str(lanes) if lanes is not None else "N/A"
    br_kN_str = f"{braking_kN:.2f}" if braking_kN is not None else "N/A"
    br_t_str = f"{braking_t:.2f}" if braking_t is not None else "N/A"
    llp_rows = "".join([
        _row(r"\textnormal{Number of Design Lanes}", _tex(lanes_str), "---",
             r"IRC 6 Table 6"),
        _row(r"\textnormal{Impact Factor, Class A / B (1 + IM)}",
             f"{im_a:.3f}" if im_a is not None else "N/A", "---",
             r"IRC 6 Cl. 208.2 (span-based)"),
        _row(r"\textnormal{Impact Factor, Class AA / 70R (1 + IM)}",
             f"{im_heavy:.3f}" if im_heavy is not None else "N/A", "---",
             r"IRC 6 Cl. 208.3 (span-based)"),
        _row(r"\textnormal{Braking Load}", br_kN_str, "kN",
             r"IRC 6 Cl. 211.2"),
        _row(r"\textnormal{Braking Load (equivalent)}", br_t_str, "tonnes",
             r"IRC 6 Cl. 211.2"),
        _row(r"\textnormal{Braking Load Application Height}", "1.20", "m",
             r"IRC 6 Cl. 211.3"),
        _row(r"\textnormal{Centrifugal Force}",
             r"Not applicable (straight bridge)", "---",
             r"IRC 6 Cl. 211.4"),
    ])
    ll_params_table = longtable(
        col_spec="|L{6.0cm}|C{3.3cm}|C{1.8cm}|L{3.5cm}|",
        caption="Vehicle Live Load Parameters (dynamic effects)",
        header=(r"\textbf{Parameter} & \textbf{Value} & \textbf{Unit} & "
                r"\textbf{Reference}"),
        body=llp_rows,
        ncols=4,
    )

    # ── Table 3.5 — Footway / footpath live loads (distinct table) ─────────
    n_footpaths = input_dict.get("typical_section.no_of_footpaths")
    try:
        n_fp = int(float(n_footpaths)) if n_footpaths not in (None, "") else 0
    except (TypeError, ValueError):
        n_fp = 0
    footpath_provided = (
        n_fp > 0
        or str(input_dict.get("geometry.footpath", "")).strip().lower()
        not in ("", "none", "no", "false", "0")
    )

    fp_mode = str(input_dict.get(KEY_LL_FOOTPATH_PRESSURE_MODE, "") or "").strip()
    fp_value = input_dict.get(KEY_LL_FOOTPATH_PRESSURE_VALUE)
    try:
        fp_code = f"{IRC6_2017.cl_206_1_footway_load():.3f}"
    except Exception:
        fp_code = "N/A"

    if str(fp_mode).lower() in ("as per irc 6", "as per irc6", "automatic"):
        fp_load_str, fp_load_ref = fp_code, r"IRC 6 Cl. 206.1"
    elif fp_value not in (None, ""):
        try:
            fp_load_str, fp_load_ref = f"{float(fp_value):.3f}", r"User-defined"
        except (TypeError, ValueError):
            fp_load_str, fp_load_ref = _tex(str(fp_value)), r"User-defined"
    else:
        fp_load_str, fp_load_ref = fp_code, r"IRC 6 Cl. 206.1"

    fw_rows = "".join([
        _row(r"\textnormal{Footpath Provided}",
             _tex("Yes" if footpath_provided else "No"), "---",
             r"Project geometry input"),
        _row(r"\textnormal{Number of Footways}", _tex(str(n_fp)), "---",
             r"Typical section"),
        _row(r"\textnormal{Footpath Width}",
             _render_value(input_dict, KEY_TS_FOOTPATH_WIDTH), "m",
             r"IRC 5 Cl. 104.3.6 (min. 1.5 m)"),
        _row(r"\textnormal{Footway Live Load Intensity}", fp_load_str,
             r"kN/m\textsuperscript{2}", fp_load_ref),
        _row(r"\textnormal{Footway Load Mode}", _tex(fp_mode or "N/A"), "---",
             r"Loading tab input"),
    ])
    footway_table = longtable(
        col_spec="|L{6.0cm}|C{3.3cm}|C{1.8cm}|L{3.5cm}|",
        caption="Footway / Footpath Live Loads",
        header=(r"\textbf{Parameter} & \textbf{Value} & \textbf{Unit} & "
                r"\textbf{Reference}"),
        body=fw_rows,
        ncols=4,
    )
    if not footpath_provided:
        footway_note = (r"\noindent\textit{Note: No footway/footpath is "
                        r"provided for this bridge — footway live load is not "
                        r"applied in the design. The code intensity above is "
                        r"shown for reference only (IRC 6 Cl. 206.1).}" + "\n")
    else:
        footway_note = (r"\noindent\textit{Note: Footway live load is applied "
                        r"on the footpath area, considered as not coacting "
                        r"with the main carriageway live load (IRC 6 "
                        r"Cl. 206.1).}" + "\n")

    # ── Dead-load / surfacing tables ─────────────────────────────────────────
    dl_rows = "".join([
        r"\textnormal{Steel Self-Weight Applied} & "
        + _render_value(input_dict, KEY_MATERIAL_GIRDER_DENSITY,
                        ' kN/m\\textsuperscript{3}') + " " + ROW_END
        + r"\hline" + "\n",
        r"\textnormal{Concrete Deck Weight} & "
        + _render_value(input_dict, KEY_MATERIAL_DECK_DENSITY,
                        ' kN/m\\textsuperscript{3}') + " " + ROW_END
        + r"\hline" + "\n",
        r"\textnormal{Self-Weight Factor} & "
        + _render_value(input_dict, KEY_PL_SELF_WEIGHT_FACTOR) + " " + ROW_END
        + r"\hline" + "\n",
    ])
    dead_load_table = longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Dead Load -- Self Weight",
        header=r"\textbf{parameter} & \textbf{value}",
        body=dl_rows, ncols=2)

    dw_rows = "".join([
        r"\textnormal{Wearing Course Load} & "
        + _render_value(input_dict, KEY_WC_MATERIAL) + " x "
        + _render_value(input_dict, KEY_WC_THICKNESS) + " " + ROW_END
        + r"\hline" + "\n",
        r"\textnormal{Additional SIDL (Crash Barrier)} & "
        + _render_value(input_dict, KEY_CB_LOAD) + " " + ROW_END
        + r"\hline" + "\n",
        r"\textnormal{Railing Load} & "
        + _render_value(input_dict, KEY_RL_LOAD_VALUE)
        + r" kN/m\sdstar{} " + ROW_END + r"\hline" + "\n",
    ])
    surfacing_table = longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Dead Load for Surfacing (DW)",
        header=r"\textbf{parameter} & \textbf{value}",
        body=dw_rows, ncols=2)

    # ── Wind load table ──────────────────────────────────────────────────────
    # Vz / Pz — prefer stored computed values; fall back to IRC6 Table 12
    vz_val = input_dict.get(KEY_WL_HOURLY_MEAN_WIND)
    pz_val = input_dict.get(KEY_WL_HOURLY_WIND_PRESSURE)
    if not vz_val or not pz_val:
        try:
            _vb = input_dict.get(KEY_WL_BASIC_WIND_SPEED) or input_dict.get('wind_speed')
            _h = input_dict.get(KEY_WL_AVG_EXPOSED_HEIGHT)
            _ter = {
                "Plain Terrain": "plain",
                "Terrain with Obstructions": "obstructed",
            }.get(str(input_dict.get(KEY_WL_TERRAIN_TYPE, "")).strip(), "plain")
            _res = IRC6_2017.table_12(float(_h), _ter, float(_vb))
            if not vz_val:
                vz_val = _res.get("Vz")
            if not pz_val:
                pz_val = _res.get("Pz")
        except Exception:
            pass
    vz_str = f"{float(vz_val):.2f}" if vz_val not in (None, "") else "N/A"
    pz_str = f"{float(pz_val):.2f}" if pz_val not in (None, "") else "N/A"

    def _wrow(param, value):
        return (r"\textnormal{" + param + r"} & " + value + " " + ROW_END
                + r"\hline" + "\n")

    wl_rows = "".join([
        _wrow("Basic Wind Speed, Vb",
              (_render_value(input_dict, 'wind_speed') or "N/A")
              + r" \small{[from Project Location]}"),
        _wrow("Terrain Type", _render_value(input_dict, KEY_WL_TERRAIN_TYPE)),
        _wrow("Average Exposed Height, H",
              _render_value(input_dict, KEY_WL_AVG_EXPOSED_HEIGHT)),
        _wrow("Hourly Mean Wind Speed, Vz", vz_str),
        _wrow("Hourly Wind Pressure, Pz", pz_str),
        _wrow("Transverse Wind Force",
              _render_value(input_dict, KEY_WL_TRANSVERSE_WIND_FORCE)),
        _wrow("Longitudinal Wind Force",
              _render_value(input_dict, KEY_WL_LONGITUDINAL_WIND_FORCE)),
        _wrow("Vertical Wind Force",
              _render_value(input_dict, KEY_WL_VERTICAL_WIND_FORCE)),
    ])
    wind_table = longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Wind Load (WL) --- per IRC 6",
        header=r"\textbf{parameter} & \textbf{value}",
        body=wl_rows, ncols=2)

    # ── Seismic table (unchanged computation, new chrome) ───────────────────
    sl_zone_factor = input_dict.get(KEY_SL_ZONE_FACTOR)
    sl_spectral = input_dict.get(KEY_SL_SPECTRAL_COEFF)
    sl_ah = input_dict.get(KEY_SL_HORIZONTAL_COEFF)
    sl_av = input_dict.get(KEY_SL_VERTICAL_COEFF)
    if not sl_ah or not sl_zone_factor:
        try:
            _zone = input_dict.get(KEY_SL_SEISMIC_ZONE) or input_dict.get('seismic_zone')
            _zmap = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V"}
            _z = str(_zone).strip().upper()
            if _z.isdigit():
                _z = _zmap.get(_z)
            _smap = {"Type I – Rocky or Hard": 1, "Type II – Medium Soil": 2,
                     "Type III – Soft Soil": 3}
            _st = _smap.get(str(input_dict.get(KEY_SL_SOIL_TYPE, "")), 1)
            _tp = input_dict.get(KEY_SL_TIME_PERIOD)
            _damp = input_dict.get(KEY_SL_DAMPING) or "5"
            _dl_v = input_dict.get(KEY_SL_DEAD_LOAD_VALUE)
            _ll_v = input_dict.get(KEY_SL_LIVE_LOAD_VALUE)
            _dead = float(_dl_v) if str(input_dict.get(KEY_SL_DEAD_LOAD_MODE, "")) == "Custom" and _dl_v else 0.0
            _live = float(_ll_v) if str(input_dict.get(KEY_SL_LIVE_LOAD_MODE, "")) == "Custom" and _ll_v else 0.0
            _res = IRC6_2017.cl_218_5_1(zone=f"Zone {_z}", soil_type=_st,
                                        dead_load_kN=_dead, live_load_kN=_live,
                                        period_T=float(_tp) if _tp else None,
                                        damping_percent=float(_damp))
            if not sl_zone_factor:
                sl_zone_factor = _res.get("Z")
            if not sl_spectral:
                sl_spectral = _res.get("Sa_g_adjusted")
            if not sl_ah:
                sl_ah = _res.get("Ah")
            if not sl_av:
                sl_av = round(_res.get("Ah", 0) * 2 / 3, 4)
        except Exception:
            pass

    def _srow(param, value):
        return (r"\textnormal{" + param + r"} & " + (value or "N/A") + " "
                + ROW_END + r"\hline" + "\n")

    el_rows = "".join([
        _srow("Seismic Zone", _render_value(input_dict, 'seismic_zone')
              + r" \small{[from Project Location]}"),
        _srow("Zone Factor, Z", _render_value(input_dict, KEY_SL_ZONE_FACTOR)),
        _srow("Importance Factor, I", _render_value(input_dict, KEY_SL_IMPORTANCE_FACTOR)),
        _srow("Type of Soil", _render_value(input_dict, KEY_SL_SOIL_TYPE)),
        _srow("Sa/g", _render_value(input_dict, KEY_SL_SPECTRAL_COEFF)),
        _srow("Horizontal Seismic Coefficient, Ah", _render_value(input_dict, KEY_SL_HORIZONTAL_COEFF)),
        _srow("Vertical Seismic Coefficient, Av", _render_value(input_dict, KEY_SL_VERTICAL_COEFF)),
        _srow("Horizontal Seismic Force (longitudinal)", "N/A"),
        _srow("Horizontal Seismic Force (transverse)", "N/A"),
    ])
    seismic_table = longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Earthquake Load (EL) --- per IRC 6",
        header=r"\textbf{parameter} & \textbf{value}",
        body=el_rows, ncols=2)

    # ── Temperature table ────────────────────────────────────────────────────
    tl_rows = "".join([
        _srow("Maximum Shade Temperature",
              _render_value(input_dict, 'shade_temp_max') + r" $^\circ$C"),
        _srow("Minimum Shade Temperature",
              _render_value(input_dict, 'shade_temp_min') + r" $^\circ$C"),
        _srow("Effective Bridge Temp. Range",
              _render_value(input_dict, KEY_TL_BRIDGE_TEMP_MIN) + " to "
              + _render_value(input_dict, KEY_TL_BRIDGE_TEMP_MAX)
              + r" $^\circ$C"),
        _srow("Temperature Rise / Fall for Design",
              "+" + _render_value(input_dict, KEY_TL_TEMP_RISE)
              + r" $^\circ$C / \textminus{}"
              + _render_value(input_dict, KEY_TL_TEMP_FALL) + r" $^\circ$C"),
    ])
    temp_table = longtable(
        col_spec="|L{5.5cm}|p{9.7cm}|",
        caption="Temperature Load (TL) --- per IRC 6",
        header=r"\textbf{parameter} & \textbf{value}",
        body=tl_rows, ncols=2)

    # ── Load combinations (dynamically generated from IRC 6) ────────────────
    _LOAD_LABEL_MAP = {
        'dead_load': 'DL',
        'surfacing': 'SIDL',
        'live_load': 'LL',
        'wind_load': 'WL',
        'thermal_load': 'TL',
        'vehicle_collision': 'VC',
        'barge_impact': 'BI',
        'floating_bodies': 'FB',
        'seismic': 'EQ',
    }

    def _fmt_factors(factors):
        parts = []
        for load, val in factors.items():
            label = _LOAD_LABEL_MAP.get(load, load.upper())
            if isinstance(val, dict):
                add = val.get('adding')
                rel = val.get('relieving')
                add_s = f"{add:.2f}" if add is not None else '--'
                rel_s = f"{rel:.2f}" if rel is not None else '--'
                parts.append(f"{label}({add_s}/{rel_s})")
            else:
                if val is None:
                    continue
                parts.append(f"{label}({val:.2f})")
        return ' + '.join(parts)

    uls_combos = IRC6_2017.uls_load_combinations()
    sls_combos = IRC6_2017.sls_load_combinations()
    lc_rows = []
    for i, combo in enumerate(uls_combos, start=1):
        lc_rows.append(
            f"ULS-{i:02d} & " + _tex(_fmt_factors(combo['factors']))
            + " " + ROW_END + r"\hline" + "\n"
        )
    for i, combo in enumerate(sls_combos, start=1):
        lc_rows.append(
            f"SLS-{i:02d} & " + _tex(_fmt_factors(combo['factors']))
            + " " + ROW_END + r"\hline" + "\n"
        )
    combos_table = longtable(
        col_spec="|C{3.9cm}|p{11.3cm}|",
        caption="Load Combinations",
        header=r"\textbf{Combination ID} & \textbf{Load Cases}",
        body="".join(lc_rows), ncols=2)

    return r"""
\chapter{Loads and Load Combinations}

This section summarizes all loads applied to the bridge and the load combinations considered for analysis and design. Vehicle live loads and footway live loads are reported separately, followed by the environmental actions (wind, seismic, temperature).

""" + dead_load_table + r"""
""" + surfacing_table + r"""
""" + vehicle_ll_table + r"""
""" + vehicle_note + r"""
""" + ll_params_table + r"""
\noindent\textit{Note: Braking load is applied longitudinally at 1.2 m above the road surface (IRC 6 Cl. 211.3). Centrifugal forces apply only to bridges on horizontal curves (IRC 6 Cl. 211.4).}
""" + footway_table + r"""
""" + footway_note + r"""
""" + wind_table + r"""
""" + seismic_table + r"""
""" + temp_table + r"""
""" + combos_table + r"""

\noindent\textit{Note: All IRC 6 load combinations are auto-generated by OsdagBridge. User-defined custom combinations, if any, are appended.}
"""
