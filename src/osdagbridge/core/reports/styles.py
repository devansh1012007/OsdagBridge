# =============================================================================
# OsdagBridge — Centralized Report Style System (single source of truth)
# =============================================================================
# Every document-level formatting rule used by the report generator lives in
# this module:
#
#   • Colour palette            (brand green, pass/fail colours, chart palette)
#   • Page geometry             (margins, header/footer clearance)
#   • Global spacing            (line spread, caption skips, table pre/post)
#   • Table style               (column separators, row padding, rule widths,
#                                array stretch, page-break needspace threshold)
#   • Header / footer themes    (fancyhdr styles, foot rules, SD-note handling)
#   • Longtable machinery       (caption + \\endfirsthead / \\endhead builders
#                                that repeat column headers on every page)
#   • Small-table builder       (table[H] + tabular for single-page tables)
#   • Figure embedding          (numbered LaTeX figures for generated charts)
#   • Chart theme               (matplotlib rcParams, colours, threshold line)
#
# ALL chapter generator files (chap1..chap9, executive_summary) must import
# their formatting rules from here — no scattered hardcoded values.
#
# The LaTeX emitted by the builders is plain string assembly (no PyLaTeX
# dependency) so it stays drop-in compatible with the existing generators.
# =============================================================================

from osdagbridge.core.reports.report_utils import _tex

# ---------------------------------------------------------------------------
# 1. COLOUR PALETTE
# ---------------------------------------------------------------------------
OSDAG_GREEN = "91B014"      # Osdag brand green — header/footer rules, accents
FAIL_RED = "B00020"         # failing checks / UR threshold line
PASS_BLACK = "1A1A1A"       # passing check text
TABLE_RULE_GRAY = "4D4D4D"  # optional inner rules

# matplotlib-friendly equivalents (used by charts.py)
CHART_PALETTE = [
    "#5B8C5A",   # muted green   (primary series)
    "#2F5D77",   # steel blue    (secondary series)
    "#C39A3B",   # ochre         (tertiary series)
    "#7A5C92",   # plum          (quaternary series)
    "#A64C4C",   # brick         (quinary series)
    "#4C7A8C",   # teal
    "#8C7A4C",   # bronze
    "#5A5A8C",   # indigo
]
CHART_FAIL_COLOR = "#C0392B"      # bars / line above UR = 1.0
CHART_THRESHOLD_COLOR = "#C0392B" # reference line at UR = 1.0
CHART_GRID_COLOR = "#D5D8DC"
CHART_TEXT_COLOR = "#1B2631"

# ---------------------------------------------------------------------------
# 2. PAGE GEOMETRY  (prevents body text / table rows bleeding into the
#    header and footer boxes — requirement 2)
# ---------------------------------------------------------------------------
# headheight=18pt keeps fancyhdr happy at 12pt (it needs >= 17.5pt for the
# two-line header rule + headrule), footskip=42pt clears the 3-line footer.
GEOMETRY_OPTIONS = (
    "a4paper, margin=1in, headheight=18pt, headsep=12pt, footskip=42pt"
)
LINE_SPREAD = "1.15"

# ---------------------------------------------------------------------------
# 3. TABLE STYLE  (cell padding, row heights, rules — requirements 1, 2, 6)
# ---------------------------------------------------------------------------
# Cell padding is sized so that the fixed-width p/L/C column specifications
# used across the chapters fit within \textwidth (a4paper, 1in margins →
# 15.92 cm):  colspec_sum + 2·tabcolsep·ncols + rules ≤ 15.92 cm.
TABCOLSEP = "4pt"          # horizontal cell padding
ARRAYSTRETCH = "1.12"      # row height multiplier
ARRAYRULEWIDTH = "0.5pt"   # table rule thickness
EXTRAROWHEIGHT = "0.6pt"   # extra height added to every row
LT_PRE = "2pt"             # vertical space above a longtable
LT_POST = "8pt"            # vertical space below a longtable

ROW_PAD = "6pt"                                # extra padding after a body row
ROW_END = "\\\\[6pt]\n"                        # body-row terminator + padding
HEADER_END = "\\\\[4pt]\n"                     # header-row terminator
TABLE_VSPACE = r"\vspace{1em}"                 # glue between caption block and table

# A table (or float) may only start when at least this many lines of space
# remain on the page — otherwise it breaks to the next page first.
NEEDSPACE_TABLES = r"6\baselineskip"

# Caption appearance (caption package)
CAPTION_SETUP = (
    "labelfont=bf, justification=raggedright, singlelinecheck=false, "
    "format=plain, skip=6pt"
)


# ---------------------------------------------------------------------------
# 4. TABLE BUILDERS
# ---------------------------------------------------------------------------

def _normalize_header(header: str) -> str:
    """Strip a trailing row terminator (``\\\\[6pt]`` or ``\\\\``) from a
    single-line header row so the builder can append its own canonical one."""
    h = (header or "").rstrip()
    for suffix in (r"\\[6pt]", r"\\[8pt]", r"\\"):
        if h.endswith(suffix):
            return h[: -len(suffix)].rstrip()
    return h


def _count_cols(header: str) -> int:
    """Best-effort column count from a header row (top-level & separators)."""
    depth = 0
    cols = 1
    escaped = False
    for ch in header:
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == "&" and depth == 0:
            cols += 1
    return max(1, cols)


def lt_head_block(caption, header, ncols=None, label=None, continued=True):
    r"""Emit the canonical opening block of a ``longtable`` environment.

    Fixes both longtable requirements at once:
      * the caption row is terminated with ``\\\\`` (a bare ``\\caption{}``
        followed by ``\hline`` triggers *Misplaced \\noalign / \\omit*);
      * the column header row is repeated on every page via
        ``\endfirsthead`` / ``\endhead``.

    Parameters
    ----------
    caption : str     plain-text caption (escaped here — no LaTeX needed)
    header  : str     column header row(s). A single line may be passed with
                      or without its trailing ``\\\\[6pt]``; a multi-line
                      block is used verbatim (each row pre-terminated).
    ncols   : int     number of columns (counted from ``header`` if omitted)
    label   : str     optional ``\label{...}``
    continued : bool  prepend a "(continued)" note on follow-up pages
    """
    if ncols is None:
        ncols = _count_cols(header.splitlines()[-1] if header else "")
    if "\n" in (header or ""):
        head_rows = header.strip("\n")
    else:
        head_rows = _normalize_header(header) + " " + HEADER_END.rstrip("\n")

    label_tex = (r"\label{" + label + "}") if label else ""
    cap = r"\caption{\textbf{" + _tex(caption) + "}}" + label_tex + r"\\"

    cont = ""
    if continued:
        cont = (
            r"\multicolumn{" + str(ncols) + r"}{l}"
            r"{\small\itshape \tablename~\thetable{} (continued)}" + r"\\" + "\n"
        )

    return (
        cap + "\n"
        r"\hline" "\n"
        + head_rows + "\n"
        r"\hline" "\n"
        r"\endfirsthead" "\n"
        + cont +
        r"\hline" "\n"
        + head_rows + "\n"
        r"\hline" "\n"
        r"\endhead" "\n"
    )


def longtable(col_spec, caption, header, body, ncols=None, label=None,
              continued=True, vspace_before=None, colsep=None,
              lt_left=None, lt_right=None):
    r"""Assemble a *complete* longtable environment with repeated headers.

    ``body`` must contain the fully-terminated data rows (including the
    closing ``\hline`` of each row block).  Use :data:`ROW_END` for the
    canonical row terminator so cell padding stays centralized.
    """
    if ncols is None:
        ncols = _count_cols(header.splitlines()[-1] if header else "")

    pre = ""
    if vspace_before is None:
        pre = TABLE_VSPACE + "\n"
    elif vspace_before:
        pre = vspace_before + "\n"

    scoped = bool(colsep or lt_left or lt_right)
    scope = ""
    if scoped:
        scope = "\\begingroup\n"
    if colsep:
        scope += "\\setlength{\\tabcolsep}{" + colsep + "}\n"
    if lt_left:
        scope += "\\setlength\\LTleft{" + lt_left + "}\n"
    if lt_right:
        scope += "\\setlength\\LTright{" + lt_right + "}\n"
    post = "\\endgroup\n" if scoped else ""

    return (
        pre
        + scope
        + "\\begin{longtable}{" + col_spec + "}\n"
        + lt_head_block(caption, header, ncols=ncols, label=label,
                        continued=continued)
        + (body or "").strip("\n") + "\n"
        + "\\end{longtable}\n"
        + post
    )


def simple_table(col_spec, caption, header, body, label=None,
                 vspace_after=None, colsep=None):
    """Small single-page table: ``table[H]`` float + ``tabular``.

    Used where a table will never split across pages; formatting (padding,
    rules) still flows from the global style constants installed by
    :func:`preamble_tex`.
    """
    label_tex = (r"\label{" + label + "}") if label else ""
    post = vspace_after if vspace_after is not None else r"\vspace{0.4cm}"
    scope = end = ""
    if colsep:
        scope = "\\begingroup\n\\setlength{\\tabcolsep}{" + colsep + "}\n"
        end = "\\endgroup\n"
    return (
        scope
        + "\\begin{table}[H]\n"
        + "\\caption{\\textbf{" + _tex(caption) + "}}" + label_tex + "\n"
        + "\\begin{tabular}{" + col_spec + "}\n"
        + "\\hline\n"
        + _normalize_header(header) + " " + HEADER_END.rstrip("\n") + "\n"
        + "\\hline\n"
        + (body or "").strip("\n") + "\n"
        + "\\end{tabular}\n"
        + post + "\n"
        + "\\end{table}\n"
        + end
    )


def plain_table(col_spec, header, body, colsep=None, noindent=True):
    """Un-numbered, un-floated ``tabular`` (no caption, no table number).

    For front-matter tables (executive summary, chapter 1) that must not
    consume a table number.  Row terminators, header padding and rules still
    come from the centralized constants (:data:`HEADER_END`, :data:`ROW_END`).
    Like every other builder, each body row must carry its own ``\\hline``.
    """
    scope = end = ""
    if colsep:
        scope = "\\begingroup\n\\setlength{\\tabcolsep}{" + colsep + "}\n"
        end = "\\endgroup\n"
    pre = r"\noindent" + "\n" if noindent else ""
    return (
        scope
        + pre
        + "\\begin{tabular}{" + col_spec + "}\n"
        + "\\hline\n"
        + _normalize_header(header) + " " + HEADER_END.rstrip("\n") + "\n"
        + "\\hline\n"
        + (body or "").strip("\n") + "\n"
        + "\\end{tabular}\n"
        + end
    )


def figure_block(path, caption, width=r"0.95\textwidth", label=None):
    """Numbered LaTeX figure for a generated chart (or any image)."""
    if not path:
        return ""
    p = str(path).replace("\\", "/")
    label_tex = (r"\label{" + label + "}") if label else ""
    return (
        "\\begin{figure}[H]\n"
        "\\centering\n"
        "\\includegraphics[width=" + width + "]{" + p + "}\n"
        "\\caption{" + caption + "}\n"
        + label_tex +
        "\\end{figure}\n"
    )


def figure_or_placeholder(path, caption, width=r"0.85\textwidth", label=None):
    """Numbered figure when the image exists, framed placeholder otherwise."""
    if path:
        return figure_block(path, caption, width=width, label=label)
    label_tex = (r"\label{" + label + "}") if label else ""
    return (
        "\\begin{figure}[H]\n"
        "\\centering\n"
        "\\fbox{\\parbox{0.97\\textwidth}{\\centering\n"
        "\\textit{[ PLACEHOLDER: " + caption + r" ]}}\n"
        "}\n"
        "\\caption{" + caption + "}\n"
        + label_tex +
        "\\end{figure}\n"
    )


def includegraphics_or_placeholder(path, title, width=r"\linewidth"):
    """Just the graphic body (or a framed placeholder box) — no environment.

    Used by callers that compose their own layout (e.g. side-by-side
    minipages in the drawings chapter).
    """
    if path:
        p = str(path).replace("\\", "/")
        return "\\includegraphics[width=" + width + "]{" + p + "}"
    return ("\\fbox{\\parbox{0.95\\linewidth}{\\centering\\textit{[ "
            + title + r" ]}}}")


# ---------------------------------------------------------------------------
# 5. PREAMBLE, HEADER & FOOTER THEMES
# ---------------------------------------------------------------------------

def _fancypagestyles_tex(pn, jn, rd, rv):
    """Header/footer theme (fancyhdr) shared by all page styles."""
    return r"""
\fancypagestyle{main}{
  \fancyhf{}
  \fancyhead[L]{""" + pn + r""" $|$ """ + jn + r"""}
  \fancyhead[R]{""" + rd + r""" $|$ """ + rv + r"""}
  \fancyfoot[L]{Osdag $|$ FOSSEE $|$ Indian Institute of Technology Bombay}
  \fancyfoot[R]{Page \thepage\ of \pageref{LastPage}}
  \renewcommand{\headrule}{\color{osdagGreen}\hrule width\headwidth height 1pt \vspace{2pt}}
  \renewcommand{\footrule}{%
    \ifbool{hasSDonPage}{%
      \hbox to \headwidth{\hfil\textcolor{black}{\footnotesize\textit{* Software default value}}\hfil}%
      \vspace{2pt}%
    }{}%
    \color{osdagGreen}\hrule width\headwidth height 1pt \vspace{3pt}%
  }
}
\fancypagestyle{plain}{
  \fancyhf{}
  \fancyhead[L]{""" + pn + r""" $|$ """ + jn + r"""}
  \fancyhead[R]{""" + rd + r""" $|$ """ + rv + r"""}
  \fancyfoot[L]{Osdag $|$ FOSSEE $|$ Indian Institute of Technology Bombay}
  \fancyfoot[R]{Page \thepage\ of \pageref{LastPage}}
  \renewcommand{\headrule}{\color{osdagGreen}\hrule width\headwidth height 1pt \vspace{2pt}}
  \renewcommand{\footrule}{%
    \ifbool{hasSDonPage}{%
      \hbox to \headwidth{\hfil\textcolor{black}{\footnotesize\textit{* Software default value}}\hfil}%
      \vspace{2pt}%
    }{}%
    \color{osdagGreen}\hrule width\headwidth height 1pt \vspace{3pt}%
  }
}
\fancypagestyle{firstpage}{
  \fancyhf{}
  \renewcommand{\headrulewidth}{0pt}
  \fancyfoot[L]{Osdag $|$ FOSSEE $|$ Indian Institute of Technology Bombay}
  \fancyfoot[R]{Page \thepage\ of \pageref{LastPage}}
  \renewcommand{\footrule}{\color{osdagGreen}\hrule width\headwidth height 1pt \vspace{3pt}}
}
\pagestyle{main}
"""


def preamble_tex(project_name, job_number, report_date, report_version="Rev 0"):
    """Full document preamble — every global setting comes from the constants
    declared at the top of this module."""
    pn = _tex(project_name)
    jn = _tex(job_number)
    rd = _tex(report_date)
    rv = _tex(report_version)
    return r"""\documentclass[12pt,a4paper]{report}

% Packages
\usepackage[""" + GEOMETRY_OPTIONS + r"""]{geometry}
\usepackage{graphicx}
\usepackage{amsmath}
\usepackage{amssymb}
\usepackage{booktabs}
\usepackage{array}
\usepackage{tabularx}
\usepackage{float}
\usepackage{fancyhdr}
\usepackage[hidelinks]{hyperref}
\usepackage{xcolor}
\usepackage{setspace}
\usepackage{enumitem}
\usepackage{caption}
\usepackage{subcaption}
\usepackage{multirow}
\usepackage{colortbl}
\usepackage{longtable}
\usepackage{titlesec}
\usepackage{titletoc}
\usepackage{lastpage}
\usepackage{makecell}
\usepackage{etoolbox}
\usepackage{needspace}

\captionsetup{""" + CAPTION_SETUP + r"""}
\numberwithin{table}{chapter}
\numberwithin{figure}{chapter}

% ---- Table layout and spacing (styles.py: table style constants) -----------
\setlength{\LTleft}{\fill}
\setlength{\LTright}{\fill}
\setlength{\tabcolsep}{""" + TABCOLSEP + r"""}
\renewcommand{\arraystretch}{""" + ARRAYSTRETCH + r"""}
\setlength{\LTpre}{""" + LT_PRE + r"""}
\setlength{\LTpost}{""" + LT_POST + r"""}
\setlength{\arrayrulewidth}{""" + ARRAYRULEWIDTH + r"""}
\setlength{\extrarowheight}{""" + EXTRAROWHEIGHT + r"""}

% ---- Page-bottom safety net (styles.py: layout constants) ------------------
% Never let a float or longtable start when fewer than NEEDSPACE_TABLES
% lines remain — pushes it (and its caption) to the next page instead of
% crowding the footer box. Section headings get the same protection so a
% heading is never orphaned directly above the footer rule.
\BeforeBeginEnvironment{table}{\needspace{""" + NEEDSPACE_TABLES + r"""}}
\BeforeBeginEnvironment{longtable}{\needspace{""" + NEEDSPACE_TABLES + r"""}}
\BeforeBeginEnvironment{figure}{\needspace{4\baselineskip}}
\titlespacing*{\section}{0pt}{3.2ex plus 1ex minus .2ex}{1.6ex plus .2ex}
\titlespacing*{\subsection}{0pt}{2.6ex plus .8ex minus .2ex}{1.2ex plus .2ex}

% ---- Colours (styles.py: palette) ------------------------------------------
\definecolor{osdagGreen}{HTML}{""" + OSDAG_GREEN + r"""}
\definecolor{osdagFail}{HTML}{""" + FAIL_RED + r"""}

""" + _fancypagestyles_tex(pn, jn, rd, rv) + r"""
% Give TeX stretch room on hard-to-break prose lines (code clause refs,
% long inline math) so justified paragraphs do not spill into the margin.
\setlength{\emergencystretch}{3em}
\setstretch{""" + LINE_SPREAD + r"""}

% Custom Commands
\newcommand{\placeholder}[1]{\textit{\textless #1\textgreater}}
\newcommand{\todo}[1]{\colorbox{yellow}{TODO: #1}}
\newcolumntype{L}[1]{>{\raggedright\arraybackslash}p{#1}}
\newcolumntype{C}[1]{>{\centering\arraybackslash}p{#1}}
\newcolumntype{R}[1]{>{\raggedleft\arraybackslash}p{#1}}

% Software-default asterisk
\newcommand{\sdstar}{\textsuperscript{*}}
\newbool{hasSDonPage}
\boolfalse{hasSDonPage}
\newcommand{\markSD}{\global\booltrue{hasSDonPage}}
\renewcommand{\sdstar}{\textsuperscript{*}\markSD{}}
\AddToHook{shipout/before}{\global\boolfalse{hasSDonPage}}

\title{\Large\textbf{OsdagBridge} \\ \normalsize Open Source Software for Steel Girder Bridge Design \\ \vspace{2cm} \large Design Report}
\author{}
\date{}

\begin{document}
"""


# ---------------------------------------------------------------------------
# 6. CHART THEME (consumed by charts.py — matplotlib)
# ---------------------------------------------------------------------------
CHART = {
    "dpi": 200,
    "figsize": (8.6, 4.4),
    "figsize_wide": (8.6, 4.0),
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans"],
    "font.size": 9.5,
    "axes.titlesize": 10.5,
    "axes.labelsize": 10.0,
    "axes.edgecolor": CHART_TEXT_COLOR,
    "axes.linewidth": 0.8,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8.5,
    "grid.color": CHART_GRID_COLOR,
    "grid.linewidth": 0.6,
    "text.color": CHART_TEXT_COLOR,
    "axes.labelcolor": CHART_TEXT_COLOR,
    "xtick.color": CHART_TEXT_COLOR,
    "ytick.color": CHART_TEXT_COLOR,
    "bar_colors": CHART_PALETTE,
    "fail_color": CHART_FAIL_COLOR,
    "threshold_color": CHART_THRESHOLD_COLOR,
    "threshold_ls": "--",
    "threshold_lw": 1.4,
    "ur_limit": 1.0,
}


def chart_rc():
    """Apply the centralized matplotlib style to the current pyplot context."""
    import matplotlib.pyplot as plt
    rc = {k: v for k, v in CHART.items()
          if k in ("font.family", "font.sans-serif", "font.size",
                   "axes.titlesize", "axes.labelsize", "axes.edgecolor",
                   "axes.linewidth", "xtick.labelsize", "ytick.labelsize",
                   "legend.fontsize", "grid.color", "grid.linewidth",
                   "text.color", "axes.labelcolor", "xtick.color",
                   "ytick.color")}
    plt.rcParams.update(rc)
