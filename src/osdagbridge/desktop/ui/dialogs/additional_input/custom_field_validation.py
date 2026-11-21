"""
Custom-field validation for the Additional Inputs dialog (Task II)
===================================================================

Pre-Save validation of "Custom" parameter selections.

The Additional Inputs dialog offers a *Custom* choice on many parameters.
Three UI patterns exist (all discovered from ``common_ui_builder.py`` /
``ui_fields_additional_input.py`` — no hardcoded parameter strings, every
field is referenced through its central ``KEY_*`` constant from
``osdagbridge.core.utils.common``):

1. ``TYPE_MODE_LINE`` — a ``<field_id>.mode`` QComboBox paired with a
   ``<field_id>.value`` QLineEdit (wind/seismic coefficients, footpath
   pressure, camber …).  Selecting *Custom* shows and enables the line edit.
2. Type combos with a ``Custom`` item whose related value line-edits are
   enabled by the tab's ``on_*_type_changed`` handler (Crash Barrier /
   Median / Railing geometry, Railing load, Wearing Course density).
   The pairing is declared in :data:`CUSTOM_TYPE_VALUE_FIELDS`.
3. ``TYPE_ADAPTIVE`` widgets driven by the design-mode controller — in
   *Custom* design mode the active sub-widget is a QLineEdit.

:func:`find_empty_custom_fields` is a **pure** function over plain state
records so it can be unit-tested without Qt.  :func:`collect_custom_field_states`
walks a live dialog (offscreen-friendly) and produces those records; the
Additional Inputs Save button runs both before committing anything.
"""

from __future__ import annotations

import re

from osdagbridge.core.utils.common import (
    KEY_CB_TYPE, KEY_CB_DENSITY, KEY_CB_WIDTH, KEY_CB_HEIGHT, KEY_CB_AREA, KEY_CB_LOAD,
    KEY_MD_TYPE, KEY_MD_DENSITY, KEY_MD_WIDTH, KEY_MD_HEIGHT, KEY_MD_AREA, KEY_MD_LOAD,
    KEY_RL_TYPE, KEY_RL_WIDTH, KEY_RL_HEIGHT,
    KEY_RL_LOAD_MODE, KEY_RL_LOAD_VALUE,
    KEY_WC_MATERIAL, KEY_WC_DENSITY,
    KEY_DESIGN_MODE,
)

# The "Custom" choice text used by every mode/type combo in the dialog.
CUSTOM_CHOICE = "Custom"

# Design-mode value that switches TYPE_ADAPTIVE widgets to their line-edit
# sub-widget (see AdditionalInputs.design_mode_trigger).
CUSTOM_DESIGN_MODE = CUSTOM_CHOICE

#: Suffix of the mode combo objectName for TYPE_MODE_LINE fields.
MODE_SUFFIX = ".mode"
#: Suffix of the value line-edit objectName for TYPE_MODE_LINE fields.
VALUE_SUFFIX = ".value"

# ─────────────────────────────────────────────────────────────────────────────
# Pattern-2 registry — type combos offering a "Custom" choice and the value
# fields that become editable when it is selected (KEY_ constants only).
# ─────────────────────────────────────────────────────────────────────────────
CUSTOM_TYPE_VALUE_FIELDS = {
    # Crash Barrier: Density/Area hidden for non-RCC; Width/Height/Load are the
    # user-supplied geometry when Type == Custom (on_crash_barrier_type_changed).
    KEY_CB_TYPE: (KEY_CB_DENSITY, KEY_CB_WIDTH, KEY_CB_HEIGHT, KEY_CB_AREA, KEY_CB_LOAD),
    # Median (on_median_type_changed).
    KEY_MD_TYPE: (KEY_MD_DENSITY, KEY_MD_WIDTH, KEY_MD_HEIGHT, KEY_MD_AREA, KEY_MD_LOAD),
    # Railing geometry (compute_railing_values → Custom branch).
    KEY_RL_TYPE: (KEY_RL_WIDTH, KEY_RL_HEIGHT),
    # Railing load value paired with its own mode combo
    # (on_railing_load_mode_changed).
    KEY_RL_LOAD_MODE: (KEY_RL_LOAD_VALUE,),
    # Wearing course density (on_wearing_material_changed).
    KEY_WC_MATERIAL: (KEY_WC_DENSITY,),
}

_RICH_TEXT_RE = re.compile(r"<[^>]+>")


def strip_rich_text(text: str) -> str:
    """Remove HTML sub/superscript markup and trailing colons from a label."""
    return _RICH_TEXT_RE.sub("", str(text or "")).strip().rstrip(":").strip()


# ─────────────────────────────────────────────────────────────────────────────
# Pure validation
# ─────────────────────────────────────────────────────────────────────────────

def find_empty_custom_fields(field_states) -> list[str]:
    """
    Return the display names of parameters whose mode selector is *Custom*
    while their value line-edit is empty.

    Parameters
    ----------
    field_states : iterable of dict
        One record per candidate parameter, each with the keys:

        ``name``     — human-readable parameter name (str)
        ``mode``     — current mode/type selection text (str)
        ``value``    — current value-line-edit text (str)
        ``enabled``  — whether the value field is editable (bool)
        ``visible``  — whether the value field is shown to the user (bool)

        Records may omit ``enabled``/``visible`` (default True) so minimal
        pure-data tests can be written as
        ``[{"name": "X", "mode": "Custom", "value": ""}]``.

    Returns
    -------
    list[str]
        Names of every parameter with ``mode == "Custom"``, an empty value,
        and a visible + enabled value field — i.e. the fields whose empty
        custom values must halt the Save.
    """
    offending: list[str] = []
    for state in field_states or []:
        if not isinstance(state, dict):
            continue
        if str(state.get("mode", "")).strip() != CUSTOM_CHOICE:
            continue
        if str(state.get("value", "") or "").strip() != "":
            continue
        if not state.get("enabled", True):
            continue
        if not state.get("visible", True):
            continue
        name = str(state.get("name", "") or "").strip()
        if name:
            offending.append(name)
    return offending


def empty_custom_field_messages(names) -> list[str]:
    """
    Format the standard error message for each offending parameter name.

    Message text is fixed by specification:
    ``Error: The custom value for '[Parameter Name]' cannot be empty.``
    """
    return [
        f"Error: The custom value for '{str(name)}' cannot be empty."
        for name in names or []
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Qt state collection (offscreen-friendly)
# ─────────────────────────────────────────────────────────────────────────────

def _enclosing_tab_disabled(widget) -> bool:
    """
    True when *widget* sits on a QTabWidget page that is currently disabled.

    Nested sub-tabs are handled by walking the full ancestor chain; a field
    is only reachable when *every* enclosing tab is enabled.
    """
    node = widget.parentWidget()
    while node is not None:
        tab_widget = None
        if _is_tab_widget(node):
            tab_widget = node
        if tab_widget is not None:
            for i in range(tab_widget.count()):
                page = tab_widget.widget(i)
                if page is not None and (page is widget or page.isAncestorOf(widget)):
                    if not tab_widget.isTabEnabled(i):
                        return True
                    break
        node = node.parentWidget()
    return False


def _is_tab_widget(obj) -> bool:
    """isinstance check that tolerates QTabWidget being unavailable."""
    try:
        from PySide6.QtWidgets import QTabWidget
        return isinstance(obj, QTabWidget)
    except Exception:
        return False


def _shown_in_tab(widget, root=None) -> bool:
    """
    True when *widget* is not explicitly hidden, ignoring QTabWidget page
    switching (fields on non-current tab pages must still be validated —
    the Save checks ALL active tabs, not just the visible one).
    """
    node = widget
    while node is not None and node is not root:
        if node.isHidden():
            parent = node.parentWidget()
            grand = parent.parentWidget() if parent is not None else None
            # A QTabWidget hides its non-current pages via the internal
            # stack; that must not count as "hidden".
            if not (grand is not None and _is_tab_widget(grand)):
                return False
        node = node.parentWidget()
    return True


def _field_display_name(root, field_id: str) -> str:
    """
    Human-readable name for *field_id*: the schema label widget
    (``<field_id>_label``) when present, otherwise a tidied key tail.
    """
    try:
        from PySide6.QtWidgets import QLabel
        label = root.findChild(QLabel, field_id + "_label")
        if label is not None:
            text = strip_rich_text(label.text())
            if text:
                return text
    except Exception:
        pass
    tail = field_id.rsplit(".", 1)[-1] if "." in field_id else field_id
    return tail.replace("_", " ").strip().title() or field_id


def collect_custom_field_states(root) -> list[dict]:
    """
    Walk a dialog (or any widget tree) and build state records for every
    parameter that offers a *Custom* choice.

    Recognises the three UI patterns described in the module docstring.
    Fields on disabled tabs (and fields disabled because the whole dialog is
    locked, or hidden by a type handler) are reported as not
    enabled/visible so :func:`find_empty_custom_fields` skips them.

    Parameters
    ----------
    root : QWidget
        The Additional Inputs dialog (or a tab page of it).

    Returns
    -------
    list[dict]
        State records consumable by :func:`find_empty_custom_fields`.
    """
    states: list[dict] = []

    try:
        from PySide6.QtWidgets import QComboBox, QLineEdit
        from osdagbridge.desktop.ui.dialogs.additional_input.ui_builder.common_ui_builder import (
            AdaptiveWidget,
        )
    except Exception:
        return states

    # ── Pattern 1: '<id>.mode' combo + '<id>.value' line edit ────────────
    for combo in root.findChildren(QComboBox):
        name = combo.objectName() or ""
        if not name.endswith(MODE_SUFFIX):
            continue
        base_id = name[: -len(MODE_SUFFIX)]
        value_edit = root.findChild(QLineEdit, base_id + VALUE_SUFFIX)
        if value_edit is None:
            continue
        states.append({
            "name": _field_display_name(root, base_id),
            "mode": combo.currentText(),
            "value": value_edit.text(),
            "enabled": combo.isEnabled() and value_edit.isEnabled(),
            "visible": _shown_in_tab(value_edit, root)
                       and not _enclosing_tab_disabled(combo),
        })

    # ── Pattern 2: type combos with a Custom choice + registered values ──
    for type_key, value_keys in CUSTOM_TYPE_VALUE_FIELDS.items():
        combo = root.findChild(QComboBox, type_key)
        if combo is None:
            continue
        if CUSTOM_CHOICE not in [combo.itemText(i) for i in range(combo.count())]:
            continue
        for value_key in value_keys:
            value_edit = root.findChild(QLineEdit, value_key)
            if value_edit is None:
                continue
            states.append({
                "name": _field_display_name(root, value_key),
                "mode": combo.currentText(),
                "value": value_edit.text(),
                "enabled": combo.isEnabled() and value_edit.isEnabled(),
                "visible": _shown_in_tab(value_edit, root)
                           and not _enclosing_tab_disabled(combo),
            })

    # ── Pattern 3: AdaptiveWidgets in Custom design mode ─────────────────
    for adaptive in root.findChildren(AdaptiveWidget):
        controller_id = getattr(adaptive, "_controller_id", "")
        if controller_id != KEY_DESIGN_MODE:
            continue
        active = adaptive.currentWidget()
        if not isinstance(active, QLineEdit):
            continue
        states.append({
            "name": _field_display_name(root, getattr(adaptive, "_field_id", "")),
            "mode": CUSTOM_DESIGN_MODE,
            "value": active.text(),
            "enabled": adaptive.isEnabled() and active.isEnabled(),
            "visible": _shown_in_tab(active, root)
                       and not _enclosing_tab_disabled(adaptive),
        })

    return states
