"""Design tokens and Qt stylesheet generation.

DaVinci Resolve's Fusion UIManager is Qt-based, so the framework gets a modern
appearance by generating a real ``StyleSheet`` (QSS) block per widget. That
means themes are not cosmetic sugar: they drive the actual Qt painting,
including hover/pressed/focus/disabled states.

    from ResolveScript.ui import theme, Button

    Button("Render", variant="primary", theme=theme.dark)

A :class:`Theme` bundles colours, a spacing scale, corner radii and a type
scale. ``theme.dark`` and ``theme.light`` are ready-made; both are frozen, so
derive a variant with :meth:`Theme.replace` instead of mutating in place::

    midnight = theme.dark.replace(name="midnight", colors={**theme.dark.colors, "bg": "#0b0d10"})
"""

from __future__ import annotations

import contextlib
import platform
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

__all__ = [
    "Color",
    "Font",
    "Theme",
    "theme",
    "dark_theme",
    "light_theme",
    "default_font_family",
]


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class Color:
    """An sRGB colour with an alpha channel, stored as 0-255 components."""

    r: int
    g: int
    b: int
    a: int = 255

    def __post_init__(self) -> None:
        for name in ("r", "g", "b", "a"):
            object.__setattr__(self, name, int(_clamp(getattr(self, name), 0, 255)))

    # -- construction ----------------------------------------------------
    @classmethod
    def from_hex(cls, value: str) -> Color:
        """Parse ``#rgb``, ``#rrggbb`` or ``#rrggbbaa`` (a leading ``#`` optional)."""
        text = value.strip().lstrip("#")
        if len(text) == 3:
            text = "".join(ch * 2 for ch in text)
        if len(text) == 4:
            text = "".join(ch * 2 for ch in text)
        if len(text) not in (6, 8):
            raise ValueError(f"not a hex colour: {value!r}")
        try:
            parts = [int(text[i : i + 2], 16) for i in range(0, len(text), 2)]
        except ValueError as exc:
            raise ValueError(f"not a hex colour: {value!r}") from exc
        if len(parts) == 3:
            parts.append(255)
        return cls(*parts)

    @classmethod
    def rgb(cls, r: int, g: int, b: int) -> Color:
        return cls(r, g, b, 255)

    @classmethod
    def rgba(cls, r: int, g: int, b: int, a: float) -> Color:
        return cls(r, g, b, int(_clamp(round(a * 255), 0, 255)))

    # -- accessors -------------------------------------------------------
    @property
    def hex(self) -> str:
        """``#rrggbb``, or ``#rrggbbaa`` when translucent."""
        base = f"#{self.r:02x}{self.g:02x}{self.b:02x}"
        return base if self.a == 255 else f"{base}{self.a:02x}"

    def to_css(self) -> str:
        """A CSS colour usable in a Qt stylesheet."""
        return f"rgba({self.r}, {self.g}, {self.b}, {self.a / 255:.3f})"

    def to_fusion(self) -> list[float]:
        """Normalised RGBA floats, as Resolve's own colour properties expect."""
        return [self.r / 255, self.g / 255, self.b / 255, self.a / 255]

    def with_alpha(self, alpha: float) -> Color:
        return Color(self.r, self.g, self.b, int(_clamp(round(alpha * 255), 0, 255)))

    # -- manipulation ----------------------------------------------------
    def mix(self, other: Color, amount: float) -> Color:
        """Blend towards ``other``; ``amount=0`` keeps ``self``, ``1`` gives ``other``."""
        t = _clamp(amount, 0.0, 1.0)
        return Color(
            round(self.r + (other.r - self.r) * t),
            round(self.g + (other.g - self.g) * t),
            round(self.b + (other.b - self.b) * t),
            round(self.a + (other.a - self.a) * t),
        )

    def lighten(self, amount: float = 0.1) -> Color:
        return self.mix(Color(255, 255, 255), amount)

    def darken(self, amount: float = 0.1) -> Color:
        return self.mix(Color(0, 0, 0), amount)

    def __str__(self) -> str:
        return self.hex


@dataclass(frozen=True)
class Font:
    """A Qt font description, mapping 1:1 onto Fusion's ``Font`` property."""

    family: str = "Segoe UI"
    point_size: int = 11
    bold: bool = False
    italic: bool = False

    def to_dict(self) -> dict[str, Any]:
        """The property dict Fusion expects."""
        return {
            "Family": self.family,
            "PointSize": self.point_size,
            "Bold": self.bold,
            "Italic": self.italic,
        }

    def scaled(self, delta: int) -> Font:
        return replace(self, point_size=max(6, self.point_size + delta))


def default_font_family() -> str:
    """Best available UI font for the current platform."""
    system = platform.system()
    if system == "Windows":
        return "Segoe UI"
    if system == "Darwin":
        return "SF Pro Text"
    return "DejaVu Sans"


# ---------------------------------------------------------------------------
# Small vector assets
#
# QSS cannot reference inline SVG, so the few glyphs a modern control set needs
# (dropdown chevron, check mark, scrollbar arrows) are written to a cache
# directory once and referenced by path.
# ---------------------------------------------------------------------------

_SVG_CACHE: dict[str, Path | None] = {}
_SVG_DIR: Path | None = None
_SVG_DIR_FAILED = False

_CHEVRON_DOWN = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6">'
    '<path d="M1 1l4 4 4-4" fill="none" stroke="{color}" stroke-width="1.6"'
    ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_CHECK = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
    '<path d="M2.5 6.2l2.4 2.4 4.6-5" fill="none" stroke="{color}" stroke-width="2"'
    ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_CARET_RIGHT = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="6" height="10" viewBox="0 0 6 10">'
    '<path d="M1 1l4 4-4 4" fill="none" stroke="{color}" stroke-width="1.4"'
    ' stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def _asset_dir() -> Path | None:
    """The cache directory for SVG glyphs, or ``None`` if it is not writable."""
    global _SVG_DIR, _SVG_DIR_FAILED
    if _SVG_DIR is not None or _SVG_DIR_FAILED:
        return _SVG_DIR
    base = Path(tempfile.gettempdir()) / "resolvescript-ui-assets"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        _SVG_DIR_FAILED = True
        return None
    _SVG_DIR = base
    return base


def _asset(name: str, template: str, color: Color) -> Path | None:
    """Materialise an SVG once and return its path."""
    key = f"{name}-{color.hex}"
    if key in _SVG_CACHE:
        return _SVG_CACHE[key]
    directory = _asset_dir()
    if directory is None:
        _SVG_CACHE[key] = None
        return None
    path = directory / f"{key}.svg"
    if not path.exists():
        try:
            path.write_text(template.format(color=color.hex), encoding="utf-8")
        except OSError:
            _SVG_CACHE[key] = None
            return None
    _SVG_CACHE[key] = path
    return path


_SPACE_SCALE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32, "none": 0}
_RADIUS_SCALE = {"none": 0, "sm": 4, "md": 6, "lg": 10, "pill": 999}


@dataclass(frozen=True)
class Theme:
    """A complete set of design tokens plus the QSS they generate."""

    name: str
    mode: str
    colors: Mapping[str, Color]
    space: Mapping[str, int] = field(default_factory=lambda: dict(_SPACE_SCALE))
    radii: Mapping[str, int] = field(default_factory=lambda: dict(_RADIUS_SCALE))
    fonts: Mapping[str, Font] = field(default_factory=dict)
    font_family: str = field(default_factory=default_font_family)

    # -- construction ----------------------------------------------------
    def replace(self, **changes: Any) -> Theme:
        """Return a copy with ``changes`` applied."""
        return replace(self, **changes)

    def with_colors(self, **overrides: Color) -> Theme:
        """Return a copy with individual colour tokens replaced."""
        return replace(self, colors={**self.colors, **overrides})

    # -- token lookups ---------------------------------------------------
    def color(self, token: str) -> Color:
        try:
            return self.colors[token]
        except KeyError:
            raise KeyError(
                f"unknown colour token {token!r}; available: {sorted(self.colors)}"
            ) from None

    def gap(self, token: str | int) -> int:
        """Resolve a spacing token (or pass a raw int) to pixels."""
        if isinstance(token, int):
            return token
        try:
            return self.space[token]
        except KeyError:
            raise KeyError(f"unknown space token {token!r}") from None

    def radius(self, token: str | int) -> int:
        if isinstance(token, int):
            return token
        try:
            return self.radii[token]
        except KeyError:
            raise KeyError(f"unknown radius token {token!r}") from None

    def font(self, token: str) -> Font:
        try:
            return self.fonts[token]
        except KeyError:
            return Font(family=self.font_family, **_FONT_SIZES.get(token, {}))

    # -- stylesheets -----------------------------------------------------
    def stylesheet(self, kind: str, variant: str | None = None) -> str:
        """The QSS for a widget kind, e.g. ``stylesheet("button", "primary")``."""
        builder = _QSS.get(kind, _QSS["label"])
        return builder(self, variant)

    def window_stylesheet(self) -> str:
        return _WINDOW_QSS(self)

    def palette(self) -> dict[str, list[float]]:
        """Colour tokens as normalised RGBA, for the handful of properties that
        take colours rather than a stylesheet (e.g. ``BackgroundColor``)."""
        return {name: colour.to_fusion() for name, colour in self.colors.items()}

    def __repr__(self) -> str:
        return f"<Theme {self.name!r} mode={self.mode!r}>"


_FONT_SIZES = {
    "xs": {"point_size": 9},
    "sm": {"point_size": 10},
    "md": {"point_size": 11},
    "lg": {"point_size": 13},
    "xl": {"point_size": 16, "bold": True},
    "title": {"point_size": 20, "bold": True},
}


def _dark() -> Theme:
    colours = {
        "bg": Color.from_hex("#16181c"),
        "surface": Color.from_hex("#1e2126"),
        "surface_alt": Color.from_hex("#262a31"),
        "surface_hover": Color.from_hex("#2e323a"),
        "border": Color.from_hex("#32363e"),
        "border_strong": Color.from_hex("#434852"),
        "text": Color.from_hex("#e7e9ee"),
        "text_muted": Color.from_hex("#9aa1ad"),
        "text_subtle": Color.from_hex("#6b7280"),
        "accent": Color.from_hex("#3b7ddd"),
        "accent_hover": Color.from_hex("#4f8ce8"),
        "accent_active": Color.from_hex("#2f6bc7"),
        "on_accent": Color.from_hex("#ffffff"),
        "danger": Color.from_hex("#e05c5c"),
        "danger_hover": Color.from_hex("#e97070"),
        "success": Color.from_hex("#3fb27f"),
        "warning": Color.from_hex("#dfa038"),
    }
    return Theme(
        name="dark",
        mode="dark",
        colors=colours,
        fonts={
            token: Font(family=default_font_family(), **spec) for token, spec in _FONT_SIZES.items()
        },
    )


def _light() -> Theme:
    colours = {
        "bg": Color.from_hex("#f2f4f7"),
        "surface": Color.from_hex("#ffffff"),
        "surface_alt": Color.from_hex("#eceef2"),
        "surface_hover": Color.from_hex("#e2e5eb"),
        "border": Color.from_hex("#d7dae1"),
        "border_strong": Color.from_hex("#bcc1cb"),
        "text": Color.from_hex("#1b1e24"),
        "text_muted": Color.from_hex("#5b6371"),
        "text_subtle": Color.from_hex("#8b93a0"),
        "accent": Color.from_hex("#2f6fe0"),
        "accent_hover": Color.from_hex("#4280ee"),
        "accent_active": Color.from_hex("#2559bd"),
        "on_accent": Color.from_hex("#ffffff"),
        "danger": Color.from_hex("#d64545"),
        "danger_hover": Color.from_hex("#e05c5c"),
        "success": Color.from_hex("#2f9e6d"),
        "warning": Color.from_hex("#c8891f"),
    }
    return Theme(
        name="light",
        mode="light",
        colors=colours,
        fonts={
            token: Font(family=default_font_family(), **spec) for token, spec in _FONT_SIZES.items()
        },
    )


# ---------------------------------------------------------------------------
# QSS templates
# ---------------------------------------------------------------------------


def _WINDOW_QSS(t: Theme) -> str:
    return f"QWidget {{ background-color: {t.color('bg').hex}; color: {t.color('text').hex}; }}"


def _button_qss(t: Theme, variant: str | None) -> str:
    accent = t.color("accent")
    if variant == "primary":
        base, hover, active, fg = (
            accent.hex,
            t.color("accent_hover").hex,
            t.color("accent_active").hex,
            t.color("on_accent").hex,
        )
    elif variant == "danger":
        base, hover, active, fg = (
            t.color("danger").hex,
            t.color("danger_hover").hex,
            t.color("danger").darken(0.12).hex,
            t.color("on_accent").hex,
        )
    elif variant == "success":
        base = t.color("success").hex
        hover = t.color("success").lighten(0.1).hex
        active = t.color("success").darken(0.1).hex
        fg = t.color("on_accent").hex
    elif variant == "ghost":
        return (
            "QPushButton {{ background: transparent; border: 1px solid transparent;"
            " color: {fg}; border-radius: {r}px; padding: 6px 12px; }}"
            "QPushButton:hover {{ background-color: {hover}; }}"
            "QPushButton:pressed {{ background-color: {pressed}; }}"
            "QPushButton:disabled {{ color: {subtle}; }}"
        ).format(
            fg=t.color("text").hex,
            r=t.radius("md"),
            hover=t.color("surface_hover").hex,
            pressed=t.color("surface_alt").hex,
            subtle=t.color("text_subtle").hex,
        )
    else:
        base, hover, active, fg = (
            t.color("surface_alt").hex,
            t.color("surface_hover").hex,
            t.color("surface_alt").darken(0.08).hex,
            t.color("text").hex,
        )

    radius = t.radius("md")
    return (
        "QPushButton {{ background-color: {base}; color: {fg};"
        " border: 1px solid {border}; border-radius: {r}px; padding: 6px 14px; }}"
        "QPushButton:hover {{ background-color: {hover}; border-color: {strong}; }}"
        "QPushButton:pressed {{ background-color: {active}; }}"
        "QPushButton:checked {{ background-color: {active}; border-color: {strong}; }}"
        "QPushButton:focus {{ border-color: {accent}; }}"
        "QPushButton:disabled {{ background-color: {disabled}; color: {subtle};"
        " border-color: {border_dim}; }}"
    ).format(
        base=base,
        fg=fg,
        border=t.color("border").hex,
        border_dim=t.color("border").with_alpha(0.5).hex,
        strong=t.color("border_strong").hex,
        hover=hover,
        active=active,
        accent=t.color("accent").hex,
        r=radius,
        disabled=t.color("surface").hex,
        subtle=t.color("text_subtle").hex,
    )


def _label_qss(t: Theme, variant: str | None) -> str:
    colour = {
        "muted": t.color("text_muted"),
        "subtle": t.color("text_subtle"),
        "accent": t.color("accent"),
        "danger": t.color("danger"),
        "success": t.color("success"),
        "warning": t.color("warning"),
        "title": t.color("text"),
        "heading": t.color("text"),
    }.get(variant or "", t.color("text"))
    size = {"title": 20, "heading": 13}.get(variant or "", 0)
    weight = "font-weight: bold; " if variant in ("title", "heading") else ""
    point = f"font-size: {size}px; " if size else ""
    return f"QLabel {{ background: transparent; color: {colour.hex}; {weight}{point}}}"


def _input_qss(t: Theme, variant: str | None) -> str:
    r = t.radius("md")
    return (
        "QLineEdit, QTextEdit, QSpinBox, QPlainTextEdit {{"
        " background-color: {bg}; color: {fg};"
        " border: 1px solid {border}; border-radius: {r}px; padding: 5px 9px;"
        " selection-background-color: {accent}; selection-color: {on_accent}; }}"
        "QLineEdit:focus, QTextEdit:focus, QSpinBox:focus {{"
        " border-color: {accent}; background-color: {surface}; }}"
        "QLineEdit:disabled, QTextEdit:disabled, QSpinBox:disabled {{"
        " color: {subtle}; background-color: {dim}; }}"
        "QLineEdit[readOnly='true'] {{ background-color: {dim}; color: {muted}; }}"
    ).format(
        bg=t.color("surface_alt").hex,
        surface=t.color("surface").hex,
        fg=t.color("text").hex,
        muted=t.color("text_muted").hex,
        subtle=t.color("text_subtle").hex,
        dim=t.color("surface").hex,
        border=t.color("border").hex,
        accent=t.color("accent").hex,
        on_accent=t.color("on_accent").hex,
        r=r,
    )


def _combo_qss(t: Theme, variant: str | None) -> str:
    r = t.radius("md")
    arrow = _asset("chevron-down", _CHEVRON_DOWN, t.color("text_muted"))
    arrow_rule = f"image: url({arrow});" if arrow else "image: none;"
    return (
        "QComboBox {{ background-color: {alt}; color: {fg};"
        " border: 1px solid {border}; border-radius: {r}px; padding: 5px 9px; }}"
        "QComboBox:hover {{ border-color: {strong}; }}"
        "QComboBox:focus {{ border-color: {accent}; }}"
        "QComboBox:disabled {{ color: {subtle}; }}"
        "QComboBox::drop-down {{ border: none; width: 22px; }}"
        "QComboBox::down-arrow {{ {arrow} width: 10px; height: 6px; }}"
        "QComboBox QAbstractItemView {{ background-color: {surface}; color: {fg};"
        " border: 1px solid {border}; border-radius: {r}px; padding: 4px;"
        " selection-background-color: {accent}; selection-color: {on_accent}; }}"
    ).format(
        alt=t.color("surface_alt").hex,
        surface=t.color("surface").hex,
        fg=t.color("text").hex,
        subtle=t.color("text_subtle").hex,
        border=t.color("border").hex,
        strong=t.color("border_strong").hex,
        accent=t.color("accent").hex,
        on_accent=t.color("on_accent").hex,
        arrow=arrow_rule,
        r=r,
    )


def _checkbox_qss(t: Theme, variant: str | None) -> str:
    check = _asset("check", _CHECK, t.color("on_accent"))
    check_rule = f"image: url({check});" if check else "image: none;"
    return (
        "QCheckBox {{ background: transparent; color: {fg}; spacing: 8px; }}"
        "QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px;"
        " border: 1px solid {strong}; background-color: {alt}; }}"
        "QCheckBox::indicator:hover {{ border-color: {accent}; }}"
        "QCheckBox::indicator:checked {{ background-color: {accent};"
        " border-color: {accent}; {check} }}"
        "QCheckBox:disabled {{ color: {subtle}; }}"
    ).format(
        fg=t.color("text").hex,
        subtle=t.color("text_subtle").hex,
        strong=t.color("border_strong").hex,
        alt=t.color("surface_alt").hex,
        accent=t.color("accent").hex,
        check=check_rule,
    )


def _slider_qss(t: Theme, variant: str | None) -> str:
    return (
        "QSlider::groove:horizontal {{ height: 4px; border-radius: 2px;"
        " background: {border}; }}"
        "QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}"
        "QSlider::handle:horizontal {{ background: {fg}; width: 14px; margin: -5px 0;"
        " border-radius: 7px; }}"
        "QSlider::handle:horizontal:hover {{ background: {accent}; }}"
        "QSlider::groove:vertical {{ width: 4px; border-radius: 2px; background: {border}; }}"
        "QSlider::add-page:vertical {{ background: {accent}; border-radius: 2px; }}"
        "QSlider::handle:vertical {{ background: {fg}; height: 14px; margin: 0 -5px;"
        " border-radius: 7px; }}"
        "QSlider:disabled {{ opacity: 0.5; }}"
    ).format(
        border=t.color("border").hex,
        accent=t.color("accent").hex,
        fg=t.color("text").hex,
    )


def _tabs_qss(t: Theme, variant: str | None) -> str:
    return (
        "QTabBar::tab {{ background: transparent; color: {muted}; padding: 7px 14px;"
        " border-bottom: 2px solid transparent; margin-right: 2px; }}"
        "QTabBar::tab:hover {{ color: {fg}; }}"
        "QTabBar::tab:selected {{ color: {fg}; border-bottom: 2px solid {accent}; }}"
    ).format(
        fg=t.color("text").hex,
        muted=t.color("text_muted").hex,
        accent=t.color("accent").hex,
    )


def _tree_qss(t: Theme, variant: str | None) -> str:
    r = t.radius("md")
    return (
        "QTreeWidget, QTreeView, QTableWidget, QListWidget {{"
        " background-color: {surface}; color: {fg}; alternate-background-color: {alt};"
        " border: 1px solid {border}; border-radius: {r}px; }}"
        "QTreeWidget::item, QListWidget::item {{ padding: 4px 6px; border-radius: 4px; }}"
        "QTreeWidget::item:hover, QListWidget::item:hover {{ background-color: {hover}; }}"
        "QTreeWidget::item:selected, QListWidget::item:selected {{"
        " background-color: {accent}; color: {on_accent}; }}"
        "QHeaderView::section {{ background-color: {alt}; color: {muted};"
        " border: none; border-bottom: 1px solid {border}; padding: 6px 8px; }}"
    ).format(
        surface=t.color("surface").hex,
        alt=t.color("surface_alt").hex,
        hover=t.color("surface_hover").hex,
        fg=t.color("text").hex,
        muted=t.color("text_muted").hex,
        border=t.color("border").hex,
        accent=t.color("accent").hex,
        on_accent=t.color("on_accent").hex,
        r=r,
    )


def _scrollbar_qss(t: Theme, variant: str | None) -> str:
    return (
        "QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}"
        "QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}"
        "QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{"
        " background: {strong}; border-radius: 5px; min-height: 28px; min-width: 28px; }}"
        "QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{"
        " background: {muted}; }}"
        "QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}"
        "QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}"
    ).format(
        strong=t.color("border_strong").hex,
        muted=t.color("text_muted").hex,
    )


def _card_qss(t: Theme, variant: str | None) -> str:
    r = t.radius("lg")
    return (
        "QWidget {{ background-color: {surface}; border: 1px solid {border};"
        " border-radius: {r}px; }}"
    ).format(surface=t.color("surface").hex, border=t.color("border").hex, r=r)


def _container_qss(t: Theme, variant: str | None) -> str:
    return "QWidget { background: transparent; }"


def _spin_qss(t: Theme, variant: str | None) -> str:
    return _input_qss(t, variant) + (
        "QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; background: {alt};"
        " border: none; }}"
    ).format(alt=t.color("surface_hover").hex)


def _color_qss(t: Theme, variant: str | None) -> str:
    return (
        "QWidget {{ background: transparent; }}"
        "QPushButton {{ border: 1px solid {border}; border-radius: {r}px; }}"
    ).format(border=t.color("border_strong").hex, r=t.radius("md"))


def _progress_qss(t: Theme, variant: str | None) -> str:
    return (
        "QProgressBar {{ background-color: {border}; border: none; border-radius: 3px;"
        " height: 6px; text-align: center; color: {muted}; }}"
        "QProgressBar::chunk {{ background-color: {accent}; border-radius: 3px; }}"
    ).format(
        border=t.color("border").hex,
        muted=t.color("text_muted").hex,
        accent=t.color("accent").hex,
    )


def _tooltip_qss(t: Theme, variant: str | None) -> str:
    return (
        "QToolTip {{ background-color: {surface}; color: {fg}; border: 1px solid {border};"
        " border-radius: 4px; padding: 4px 6px; }}"
    ).format(
        surface=t.color("surface_hover").hex,
        fg=t.color("text").hex,
        border=t.color("border_strong").hex,
    )


_QSS: dict[str, Any] = {
    "button": _button_qss,
    "label": _label_qss,
    "text_field": _input_qss,
    "text_area": _input_qss,
    "number": _spin_qss,
    "combo": _combo_qss,
    "check": _checkbox_qss,
    "radio": _checkbox_qss,
    "switch": _checkbox_qss,
    "slider": _slider_qss,
    "tabs": _tabs_qss,
    "tree": _tree_qss,
    "table": _tree_qss,
    "list": _tree_qss,
    "scroll": _scrollbar_qss,
    "card": _card_qss,
    "divider": _container_qss,
    "color": _color_qss,
    "progress": _progress_qss,
    "row": _container_qss,
    "column": _container_qss,
    "stack": _container_qss,
    "scroll_area": _container_qss,
    "window": _container_qss,
    "spacer": _container_qss,
    "tooltip": _tooltip_qss,
    "raw": _container_qss,
}


dark_theme: Theme = _dark()
light_theme: Theme = _light()

#: The active theme. Flip with :func:`use_theme` or pass ``theme=`` per widget.
theme: Theme = dark_theme


@contextlib.contextmanager
def use_theme(replacement: Theme):
    """Temporarily make ``replacement`` the active theme.

    Anything that resolves its theme lazily — :func:`active`, and therefore
    every renderer — sees the swap; anything that captured the previous value
    keeps it.
    """
    global theme
    previous = theme
    theme = replacement
    try:
        yield replacement
    finally:
        theme = previous


def active() -> Theme:
    """The theme currently in force.

    A function rather than a constant, so that a renderer holding no explicit
    theme still follows :func:`use_theme`.
    """
    return theme
