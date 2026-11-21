from osdagbridge.core.reports.report_utils import _tex
from osdagbridge.core.reports.styles import plain_table, ROW_END


def ch1_project_info(m):
    rows = "".join([
        r"\textbf{Project Name} & " + _tex(m.project_name) + " " + ROW_END + r"\hline" + "\n",
        r"\textbf{Project Location} & " + _tex(m.project_location) + " " + ROW_END + r"\hline" + "\n",
        r"\textbf{Designer} & " + _tex(m.designer) + " " + ROW_END + r"\hline" + "\n",
        r"\textbf{Reviewer} & " + _tex(m.reviewer) + " " + ROW_END + r"\hline" + "\n",
        r"\textbf{Organization} & " + _tex(m.company) + " " + ROW_END + r"\hline" + "\n",
        r"\textbf{Client} & " + _tex(m.client) + " " + ROW_END + r"\hline" + "\n",
        r"\textbf{Software Version} & OsdagBridge " + ROW_END + r"\hline" + "\n",
    ])
    team_table = plain_table(
        col_spec="|L{5.5cm}|L{8.5cm}|",
        header=r"\textbf{Item} & \textbf{Details}",
        body=rows)

    return r"""
\chapter{Project Information}

This section records all project metadata as entered by the designer.

\section{Project and Design Team Details}
\label{sec:project-details}

""" + team_table + r"""


\section{Applicable Codes and Standards}
\label{sec:codes}

\begin{itemize}
\item Indian Roads Congress (IRC) 5: General Features of Design
\item Indian Roads Congress (IRC) 6: Loads and Load Combinations
\item Indian Roads Congress (IRC) 22: Composite Construction (Limit State Design)
\item Indian Roads Congress (IRC) 24: Steel Road Bridges (Limit State Method)
\item Indian Roads Congress (IRC) 112: Concrete Road Bridges (deck design)
\item Indian Roads Congress Special Publication (IRC SP) 114: Seismic Design of Road Bridges
\item Indian Standard (IS) 800: General Construction in Steel
\item Indian Standard (IS) 2062: Hot Rolled Structural Steel Specification
\item Indian Standard (IS) 6006: Steel Bearings
\end{itemize}
"""
