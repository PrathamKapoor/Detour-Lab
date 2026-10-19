"""Shared layout primitives for the review packet (Gate 6).

Fonts, styles, table construction, text sanitisation and the vector plan live
here so :mod:`detour_lab.reporting.pdf` can stay a readable document assembly
script. Nothing in this module knows anything about routing, evidence or
accessibility: it draws strings it is given.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

__all__ = [
    "FONT_FALLBACK_NOTE",
    "NetworkPlan",
    "build_styles",
    "ensure_fonts",
    "font_note",
    "kv_table",
    "p",
    "sanitize",
    "table",
]

FONT_FALLBACK_NOTE = (
    "A Unicode TrueType font was not available, so the built-in Helvetica face was used. Helvetica "
    "covers the Latin-1 range; characters outside it are replaced with a visible placeholder rather "
    "than silently dropped."
)

#: Windows-native faces with wide Unicode coverage, tried in order. Registering
#: a real TrueType face means a stored observation containing an accented or
#: non-Latin character renders as a glyph instead of a black box.
_FONT_CANDIDATES: tuple[tuple[str, str, str], ...] = (
    ("DejaVuSans", "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("SegoeUI", "segoeui.ttf", "segoeuib.ttf"),
    ("Arial", "arial.ttf", "arialbd.ttf"),
)

_font_regular = "Helvetica"
_font_bold = "Helvetica-Bold"
_font_note = ""
_fonts_ready = False


def ensure_fonts() -> None:
    """Register the first available Unicode TrueType face, once per process."""
    global _font_regular, _font_bold, _font_note, _fonts_ready
    if _fonts_ready:
        return
    _fonts_ready = True
    windows_fonts = Path("C:/Windows/Fonts")
    if not windows_fonts.is_dir():  # pragma: no cover - non-Windows development machine
        _font_note = FONT_FALLBACK_NOTE
        return
    for name, regular, bold in _FONT_CANDIDATES:
        regular_path = windows_fonts / regular
        bold_path = windows_fonts / bold
        if not regular_path.exists():
            continue
        try:
            pdfmetrics.registerFont(TTFont(name, str(regular_path)))
            if bold_path.exists():
                pdfmetrics.registerFont(TTFont(f"{name}-Bold", str(bold_path)))
                pdfmetrics.registerFontFamily(
                    name,
                    normal=name,
                    bold=f"{name}-Bold",
                    italic=name,
                    boldItalic=f"{name}-Bold",
                )
            _font_regular = name
            _font_bold = f"{name}-Bold" if bold_path.exists() else name
            return
        except Exception:  # pragma: no cover - an unreadable font must not stop a report
            continue
    _font_note = FONT_FALLBACK_NOTE


def font_note() -> str:
    return _font_note


def regular_font() -> str:
    return _font_regular


def bold_font() -> str:
    return _font_bold


def sanitize(text: object) -> str:
    """Make stored text safe and readable inside a PDF string.

    XML-significant characters are escaped because :class:`Paragraph` parses a
    small markup subset; everything else passes through untouched so the reader
    sees the stored value verbatim. Control characters become a visible
    placeholder instead of being dropped, so a corrupted record is evident
    rather than silently shortened.
    """
    out: list[str] = []
    for char in str(text):
        if char in "&<>":
            out.append({"&": "&amp;", "<": "&lt;", ">": "&gt;"}[char])
        elif ord(char) < 32 and char not in "\n\t":
            out.append("\ufffd")
        else:
            out.append(char)
    return "".join(out)


_TABLE_HEADER = colors.HexColor("#12324f")
_ROW_ALT = colors.HexColor("#eef3f8")

_STATE_COLOURS = {
    "PASS": colors.HexColor("#1d7a54"),
    "FAIL": colors.HexColor("#8a1f11"),
    "UNKNOWN": colors.HexColor("#8a6100"),
    "NOT_APPLICABLE": colors.HexColor("#55636f"),
}


def state_colour(state: str | None):
    return _STATE_COLOURS.get(state or "", colors.HexColor("#5a6b7b"))


def build_styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DLTitle", parent=sample["Title"], fontName=_font_bold, fontSize=23, leading=27,
            textColor=colors.HexColor("#12324f"), spaceAfter=4,
        ),
        "subtitle": ParagraphStyle(
            "DLSubtitle", parent=sample["Normal"], fontName=_font_regular, fontSize=11, leading=15,
            textColor=colors.HexColor("#33506b"),
        ),
        "h1": ParagraphStyle(
            "DLH1", parent=sample["Heading1"], fontName=_font_bold, fontSize=13, leading=17,
            textColor=colors.HexColor("#12324f"), spaceBefore=13, spaceAfter=5,
        ),
        "h2": ParagraphStyle(
            "DLH2", parent=sample["Heading2"], fontName=_font_bold, fontSize=10.5, leading=14,
            textColor=colors.HexColor("#2a4a68"), spaceBefore=8, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "DLBody", parent=sample["Normal"], fontName=_font_regular, fontSize=9, leading=12.5,
            alignment=TA_LEFT, spaceAfter=5,
        ),
        "small": ParagraphStyle(
            "DLSmall", parent=sample["Normal"], fontName=_font_regular, fontSize=7.6, leading=10,
            textColor=colors.HexColor("#4a5a6a"),
        ),
        "warn": ParagraphStyle(
            "DLWarn", parent=sample["Normal"], fontName=_font_bold, fontSize=9.5, leading=13,
            textColor=colors.HexColor("#8a1f11"),
        ),
        "note": ParagraphStyle(
            "DLNote", parent=sample["Normal"], fontName=_font_regular, fontSize=8.2, leading=11,
            textColor=colors.HexColor("#3a4a5a"), backColor=colors.HexColor("#f4f7fa"),
            borderPadding=5, spaceBefore=3, spaceAfter=6,
        ),
    }


def p(text: object, style: ParagraphStyle) -> Paragraph:
    return Paragraph(sanitize(text), style)


def table(rows: list[list], widths: list[float], *, size: float = 7.2) -> Table:
    """A table that paginates without losing information.

    ``repeatRows=1`` re-emits the header on every continuation page and each row
    may split, so a long findings or evidence table never silently truncates.
    """
    built = Table(rows, colWidths=widths, repeatRows=1, splitByRow=1, hAlign="LEFT")
    built.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), _TABLE_HEADER),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), _font_bold),
                ("FONTSIZE", (0, 0), (-1, -1), size),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3ced9")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
                ("TOPPADDING", (0, 0), (-1, -1), 2.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return built


def kv_table(pairs: Iterable[tuple[str, object]], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [[p(key, styles["small"]), p(value, styles["mono"] if "mono" in styles else styles["small"])] for key, value in pairs]
    built = Table(rows, colWidths=[58 * mm, 108 * mm], hAlign="LEFT")
    built.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c3ced9")),
                ("BACKGROUND", (0, 0), (0, -1), _ROW_ALT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return built


class NetworkPlan(Flowable):
    """Vector plan of the reported phase graph. Pure geometry; no verdicts.

    Edge style is encoded twice - by line weight and by dash pattern as well as
    by colour - so a reader who cannot distinguish the colours still reads the
    same information. Every edge is also labelled with its id, and the full
    tabular listing accompanies the figure.
    """

    _EDGE_WEIGHT: ClassVar[dict[str, float]] = {
        "PASS": 2.2,
        "UNKNOWN": 1.6,
        "FAIL": 1.7,
        "NOT_APPLICABLE": 1.2,
    }

    def __init__(self, network, width: float = 166 * mm, height: float = 90 * mm, padding: float = 9 * mm):
        super().__init__()
        self.network = network
        self.width = width
        self.height = height
        self.padding = padding

    def _scale(self) -> tuple[float, float]:
        span_x = self.network.bound_width or 1.0
        span_y = self.network.bound_height or 1.0
        return ((self.width - 2 * self.padding) / span_x, (self.height - 2 * self.padding) / span_y)

    def _point(self, x: float, y: float) -> tuple[float, float]:
        scale_x, scale_y = self._scale()
        return (
            self.padding + (x - self.network.bound_x) * scale_x,
            self.height - self.padding - (y - self.network.bound_y) * scale_y,
        )

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        return min(self.width, avail_width), self.height

    def draw(self) -> None:
        canvas = self.canv
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#c3ced9"))
        canvas.setLineWidth(0.5)
        canvas.rect(0, 0, self.width, self.height)

        positions = {n.id: (n.x, n.y) for n in self.network.nodes}
        for edge in self.network.edges:
            start, end = positions.get(edge.u), positions.get(edge.v)
            if start is None or end is None:  # pragma: no cover - graph validation guarantees this
                continue
            x1, y1 = self._point(*start)
            x2, y2 = self._point(*end)
            state = edge.state or ""
            if edge.temporary or edge.closed_in_phase:
                canvas.setDash(3, 2)
                colour = _STATE_COLOURS["UNKNOWN"] if edge.temporary else _STATE_COLOURS["FAIL"]
                label = f"{edge.id}{' T' if edge.temporary else ' X'}"
            else:
                canvas.setDash()
                colour = state_colour(state)
                label = edge.id
            canvas.setStrokeColor(colour)
            canvas.setLineWidth(self._EDGE_WEIGHT.get(state, 1.2))
            canvas.line(x1, y1, x2, y2)
            canvas.setDash()

            canvas.setFont(_font_regular, 5.0)
            width = pdfmetrics.stringWidth(label, _font_regular, 5.0)
            canvas.setFillColor(colors.HexColor("#33465a"))
            canvas.drawString(min((x1 + x2) / 2 + 2, self.width - width - 2), (y1 + y2) / 2 + 1.5, label)

        for node in self.network.nodes:
            x, y = self._point(node.x, node.y)
            canvas.setFillColor(_STATE_COLOURS["NOT_APPLICABLE"])
            canvas.setStrokeColor(colors.HexColor("#33465a"))
            canvas.circle(x, y, 2.6, stroke=1, fill=1)
            canvas.setFillColor(colors.HexColor("#22323f"))
            canvas.setFont(_font_regular, 5.4)
            canvas.drawString(x + 3.4, y + 1.4, node.id)
        canvas.restoreState()