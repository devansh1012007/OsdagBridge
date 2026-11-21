"""
Interactive 2D-CAD parameter editing (Task I)
=============================================

Central registry + pure validation helpers for double-click editing of
bridge dimension labels directly on the 2D CAD canvas (template page).

Design
------
* The CAD widgets (``CrossSectionCADWidget`` / ``TopViewCADWidget``) only
  *report* edit attempts: they know nothing about the input dictionaries.
  They emit ``parameter_edit_requested(key, text)`` and the template page
  performs the validation / dictionary update / CAD redraw.
* All editable-parameter knowledge lives in THIS module as a registry keyed
  by the central ``KEY_*`` constants from
  ``osdagbridge.core.utils.common`` — no hardcoded parameter strings.
* Range validation reuses ``BridgeInputValidator`` (the same rules the main
  input dock enforces) so the CAD editor can never accept a value the main
  UI would reject.

Editable (write-enabled) parameters
    Carriageway Width, Girder Spacing, Deck Thickness, Span Length.

Locked (read-only via CAD clicks) parameters — derived values, locking
prevents geometric inconsistencies:
    Overhang, Overall Bridge Width, Bracing Spacing.
"""

from osdagbridge.core.utils.common import (
    KEY_SPAN,
    KEY_CARRIAGEWAY_WIDTH,
    KEY_TS_GIRDER_SPACING,
    KEY_TS_DECK_THICKNESS,
    KEY_TS_DECK_OVERHANG,
    KEY_TS_OVERALL_WIDTH,
    KEY_MP_CB_SPACING,
    SPAN_MIN,
    SPAN_MAX,
    CARRIAGEWAY_WIDTH_MIN,
    CARRIAGEWAY_WIDTH_MIN_WITH_MEDIAN,
    CARRIAGEWAY_WIDTH_MAX_LIMIT,
    KEY_INCLUDE_MEDIAN,
    KEY_TS_NO_OF_GIRDERS,
)

# ─────────────────────────────────────────────────────────────────────────────
# Registry — CAD label ↔ input-dictionary key mapping
# ─────────────────────────────────────────────────────────────────────────────

# unit of the value as typed by the user AND as stored in the input dict
# ("m" for metric lengths the UI shows in metres, "mm" for thicknesses).
# ``cad_param`` is the corresponding key inside the CAD widget ``params``
# dict (always millimetres there).
CAD_EDITABLE_PARAMS = {
    KEY_SPAN: {
        "label": "Span Length",
        "cad_param": "span_length",
        "unit": "m",
        "decimals": 1,
    },
    KEY_CARRIAGEWAY_WIDTH: {
        "label": "Carriageway Width",
        "cad_param": "carriageway_width",
        "unit": "m",
        "decimals": 2,
    },
    KEY_TS_GIRDER_SPACING: {
        "label": "Girder Spacing",
        "cad_param": "girder_spacing",
        "unit": "m",
        "decimals": 2,
    },
    KEY_TS_DECK_THICKNESS: {
        "label": "Deck Thickness",
        "cad_param": "deck_thickness",
        "unit": "mm",
        "decimals": 0,
    },
}

# Derived values — displayed on the CAD but never editable from it.
CAD_LOCKED_PARAMS = {
    KEY_TS_DECK_OVERHANG: {
        "label": "Overhang",
        "cad_param": "deck_overhang",
        "unit": "m",
        "decimals": 2,
    },
    KEY_TS_OVERALL_WIDTH: {
        "label": "Overall Bridge Width",
        "cad_param": None,          # computed from geometry, no direct CAD param
        "unit": "m",
        "decimals": 2,
    },
    KEY_MP_CB_SPACING: {
        "label": "Bracing Spacing",
        "cad_param": "cross_bracing_spacing",
        "unit": "m",
        "decimals": 2,
    },
}

# Every CAD dimension label that participates in double-click editing.
CAD_PARAM_REGISTRY = {**CAD_EDITABLE_PARAMS, **CAD_LOCKED_PARAMS}


def is_cad_param_editable(key: str) -> bool:
    """True when *key* may be edited by double-clicking its CAD label."""
    return key in CAD_EDITABLE_PARAMS


def is_cad_param_locked(key: str) -> bool:
    """True when *key* is a known CAD dimension that must stay read-only."""
    return key in CAD_LOCKED_PARAMS


def cad_param_label(key: str) -> str:
    """Human-readable label for a CAD parameter key ("" when unknown)."""
    entry = CAD_PARAM_REGISTRY.get(key)
    return entry["label"] if entry else ""


# ─────────────────────────────────────────────────────────────────────────────
# Pure value helpers
# ─────────────────────────────────────────────────────────────────────────────

def cad_param_to_input_value(key: str, cad_params: dict):
    """
    Current input-dictionary value for *key*, read from a CAD widget's
    ``params`` dict (which always stores millimetres).

    Returns None when the CAD state does not carry the parameter.
    """
    entry = CAD_PARAM_REGISTRY.get(key)
    if entry is None:
        return None
    cad_name = entry.get("cad_param")
    if cad_name is None:
        return None
    raw = cad_params.get(cad_name)
    if raw is None:
        return None
    try:
        raw = float(raw)
    except (TypeError, ValueError):
        return None
    if entry["unit"] == "m":
        return raw / 1000.0
    return raw


def format_cad_param_value(key: str, value) -> str:
    """
    Format an input-dict value (metres or mm per the registry) exactly the
    way the CAD dimension label shows it — this is the text pre-filled into
    the inline editor.
    """
    entry = CAD_PARAM_REGISTRY.get(key)
    if entry is None:
        return ""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{value:.{entry['decimals']}f}"


def _parse_numeric(text: str):
    """Parse user-typed text into a float (accepts a comma decimal separator)."""
    try:
        return float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Validation — reuses the central UI validator rules
# ─────────────────────────────────────────────────────────────────────────────

def validate_cad_param_value(key, text, input_dict=None, validator=None):
    """
    Validate a value typed into a CAD label editor.

    Parameters
    ----------
    key : str
        Central KEY_* constant of the parameter being edited.
    text : str
        Raw editor text.
    input_dict : dict, optional
        Current basic/additional input dictionary (used for cross-field
        rules such as the IRC 5 carriageway-width / median check).
    validator : BridgeInputValidator, optional
        Reuses the provided instance; a fresh one is created when omitted.

    Returns
    -------
    tuple[bool, float | None, str]
        ``(ok, value_in_input_units, message)`` — ``value`` is None and
        ``message`` explains the problem when ``ok`` is False.
    """
    label = cad_param_label(key) or str(key)

    if key not in CAD_PARAM_REGISTRY:
        return False, None, f"'{label}' is not a recognised CAD parameter."

    if is_cad_param_locked(key):
        return (
            False, None,
            f"'{label}' is a derived value and cannot be edited from the "
            f"CAD view. Edit the primary inputs instead.",
        )

    value = _parse_numeric(text)
    if value is None:
        return False, None, f"The value for '{label}' must be numeric."

    entry = CAD_EDITABLE_PARAMS[key]

    # ── Reuse the shared UI validator wherever a rule exists ──────────────
    if validator is None:
        from osdagbridge.core.bridge_types.plate_girder.validator import (
            BridgeInputValidator,
        )
        validator = BridgeInputValidator()

    probe = dict(input_dict or {})
    probe[key] = value

    if key == KEY_SPAN:
        result = validator.validate_basic_inputs(KEY_SPAN, probe)
    elif key == KEY_CARRIAGEWAY_WIDTH:
        result = validator.validate_basic_inputs(KEY_CARRIAGEWAY_WIDTH, probe)
    else:
        result = validator.validate_additional_inputs(key, probe)

    if result is not None:
        _corrected, message = result
        return False, None, message

    # ── Standalone sanity bounds (constant-driven, no magic numbers) ──────
    if key == KEY_SPAN and not (SPAN_MIN <= value <= SPAN_MAX):
        return (
            False, None,
            f"{label} must be between {SPAN_MIN:g} m and {SPAN_MAX:g} m.",
        )
    if key == KEY_CARRIAGEWAY_WIDTH:
        median = (input_dict or {}).get(KEY_INCLUDE_MEDIAN)
        cw_min = (
            CARRIAGEWAY_WIDTH_MIN_WITH_MEDIAN
            if median in ("Yes", True)
            else CARRIAGEWAY_WIDTH_MIN
        )
        if not (cw_min <= value <= CARRIAGEWAY_WIDTH_MAX_LIMIT):
            return (
                False, None,
                f"{label} must be between {cw_min:g} m and "
                f"{CARRIAGEWAY_WIDTH_MAX_LIMIT:g} m.",
            )
    if key == KEY_TS_DECK_THICKNESS and not (100.0 <= value <= 500.0):
        return False, None, f"{label} must be between 100 mm and 500 mm."

    # Girder spacing upper bound is overall-width dependent; the shared
    # validator already enforced it whenever the overall width is known.
    if key == KEY_TS_GIRDER_SPACING and value < 0.5:
        return False, None, f"{label} must be at least 0.5 m."

    return True, value, ""


# ─────────────────────────────────────────────────────────────────────────────
# Qt inline editor + mixin (imported only by the CAD widgets)
# ─────────────────────────────────────────────────────────────────────────────

def _qt_mixin():
    """
    Build and return the ``CadLabelEditMixin`` class (lazy so importing this
    module stays Qt-free for pure-logic tests).
    """
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QDoubleValidator
    from PySide6.QtWidgets import QLineEdit

    class _CadLabelEditor(QLineEdit):
        """Temporary inline editor shown on top of a CAD dimension label."""

        def __init__(self, parent, param_key, on_commit, on_cancel):
            super().__init__(parent)
            self._param_key = param_key
            self._on_commit = on_commit
            self._on_cancel = on_cancel
            self._finished = False
            self.setFrame(True)
            self.setAlignment(Qt.AlignCenter)
            self.setStyleSheet(
                "QLineEdit {"
                " background: #FFFFFF;"
                " border: 2px solid #90AF13;"
                " border-radius: 3px;"
                " padding: 1px 4px;"
                " font-size: 9pt;"
                " color: #000000;"
                "}"
            )
            # numeric input only (loose bounds; semantic checks happen on commit)
            self.setValidator(QDoubleValidator(-1e9, 1e9, 4))
            self.editingFinished.connect(self._commit)

        def keyPressEvent(self, event):
            if event.key() == Qt.Key_Escape:
                self._cancel()
                return
            super().keyPressEvent(event)

        def _commit(self):
            if self._finished:
                return
            self._finished = True
            self._on_commit(self._param_key, self.text().strip())

        def _cancel(self):
            if self._finished:
                return
            self._finished = True
            self._on_cancel(self._param_key)

    class CadLabelEditMixin:
        """
        Double-click label editing for the QPainter-based CAD widgets.

        The host widget must:
          * declare ``parameter_edit_requested = Signal(str, str)`` and
            ``locked_parameter_clicked = Signal(str)`` (Qt signals cannot
            live in a plain mixin),
          * call :meth:`_init_cad_editing` in its ``__init__``,
          * register its dimension labels while painting via
            :meth:`_register_dim_label`,
          * forward ``mouseMoveEvent`` positions to
            :meth:`_update_cad_edit_cursor` for hover feedback.

        The mixin is deliberately inert unless ``cad_editing_enabled`` is
        switched on by the owning view (the template-page dual CAD view).
        """

        #: px padding added around a label's text rect for hit testing
        LABEL_HIT_PADDING = 5

        # ── lifecycle ────────────────────────────────────────────────────
        def _init_cad_editing(self, enabled: bool = False):
            self.cad_editing_enabled = bool(enabled)
            self._dim_label_zones = []      # [(QRectF, key), ...]
            self._active_editor = None

        def _set_cad_editing_enabled(self, enabled: bool):
            self.cad_editing_enabled = bool(enabled)
            if not self.cad_editing_enabled:
                self._cancel_active_editor()

        # ── registration (called from paintEvent draw helpers) ───────────
        def _register_dim_label(self, rect, param_key):
            """Remember a painted dimension-label rect for click editing."""
            if param_key is None or rect is None:
                return
            padded = rect.adjusted(
                -self.LABEL_HIT_PADDING, -self.LABEL_HIT_PADDING,
                self.LABEL_HIT_PADDING, self.LABEL_HIT_PADDING,
            )
            self._dim_label_zones.append((padded, param_key))

        # ── hover feedback ───────────────────────────────────────────────
        def _update_cad_edit_cursor(self, pos):
            from PySide6.QtGui import QCursor
            if not getattr(self, "cad_editing_enabled", False):
                return
            key, _rect = self._dim_label_at(pos)
            if key is not None and is_cad_param_editable(key):
                self.setCursor(QCursor(Qt.PointingHandCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))

        def _dim_label_at(self, pos):
            """Return the (key, rect) of the dimension label under *pos*."""
            for rect, key in getattr(self, "_dim_label_zones", []):
                if rect.contains(pos):
                    return key, rect
            return None, None

        # ── event handling ───────────────────────────────────────────────
        def mouseDoubleClickEvent(self, event):
            if not getattr(self, "cad_editing_enabled", False):
                super().mouseDoubleClickEvent(event)
                return
            pos = event.position() if hasattr(event, "position") else event.pos()
            key, rect = self._dim_label_at(pos)
            if key is None or rect is None:
                super().mouseDoubleClickEvent(event)
                return
            if is_cad_param_locked(key):
                self.locked_parameter_clicked.emit(key)
                return
            if not is_cad_param_editable(key):
                return
            self._begin_label_edit(key, rect)

        # ── editing ──────────────────────────────────────────────────────
        def _begin_label_edit(self, key, rect):
            self._cancel_active_editor()

            current = cad_param_to_input_value(key, self.params)
            if current is None:
                return
            text = format_cad_param_value(key, current)

            editor = _CadLabelEditor(
                self, key,
                on_commit=self._commit_label_edit,
                on_cancel=self._cancel_label_edit,
            )
            editor.setText(text)
            geo = rect.toAlignedRect().adjusted(-2, -2, 2, 2)
            editor.setGeometry(geo)
            self._active_editor = editor
            editor.show()
            editor.setFocus()
            editor.selectAll()

        def _commit_label_edit(self, key, text):
            editor, self._active_editor = self._active_editor, None
            original = cad_param_to_input_value(key, self.params)
            if editor is not None:
                editor.hide()
                editor.deleteLater()
            self.update()
            if text == "" or text is None:
                return
            if original is not None:
                try:
                    if abs(float(_parse_numeric(text) or 0.0) - float(original)) < 1e-9:
                        return
                except (TypeError, ValueError):
                    pass
            # Validation / dictionary push / redraw happens in the owner.
            self.parameter_edit_requested.emit(key, text)

        def _cancel_label_edit(self, _key=None):
            self._cancel_active_editor()

        def _cancel_active_editor(self):
            editor, self._active_editor = getattr(self, "_active_editor", None), None
            if editor is not None:
                try:
                    editor.hide()
                    editor.deleteLater()
                except RuntimeError:
                    pass
                self.update()

    return CadLabelEditMixin


def get_cad_label_edit_mixin():
    """Public accessor for the lazily-built :class:`CadLabelEditMixin`."""
    return _qt_mixin()
