"""PDF, Excel and CSV from one ReportData, so the numbers always match the preview.

PDF uses ReportLab (pure Python, so it installs the same way on Windows, macOS, Linux and the
servers): A4, farm letterhead, summary cards, a vector chart, tables with repeating headers,
signature lines and "Page x of y". Black and white printable (greys only, with patterns kept
distinct by shade)."""

from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from django.core.files.storage import default_storage
from django.utils import timezone

from .builders import Column, ReportData

GREYS = ["#1a1a1a", "#7a7a7a", "#b5b5b5", "#4a4a4a", "#d9d9d9", "#9a9a9a"]


def filename(data: ReportData, ext: str) -> str:
    return f"{data.key}_{data.period.start:%Y%m%d}-{data.period.end:%Y%m%d}.{ext}"


def cell_text(value: Any, col: Column) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, dt.date):
        return f"{value:%d %b %Y}"
    if col.type == "percent":
        return f"{value}%"
    return str(value)


def card_text(card: Any) -> str:
    return (
        f"{card.value}{card.unit}"
        if card.unit == "%"
        else f"{card.value}{(' ' + card.unit) if card.unit else ''}"
    )


# --- CSV ------------------------------------------------------------------------------------------


def to_csv(data: ReportData) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([data.title])
    w.writerow(["Period", data.period.label()])
    for card in data.summary:
        w.writerow([card.label, card_text(card)])
    for table in data.tables:
        w.writerow([])
        w.writerow([table.title])
        w.writerow([c.label for c in table.columns])
        for row in table.rows:
            w.writerow(
                [
                    (
                        row.get(c.key).isoformat()  # type: ignore[union-attr]
                        if isinstance(row.get(c.key), dt.date)
                        else ("" if row.get(c.key) is None else row.get(c.key))
                    )
                    for c in table.columns
                ]
            )
    return ("﻿" + out.getvalue()).encode("utf-8")  # BOM so Excel opens it as UTF-8


# --- Excel ----------------------------------------------------------------------------------------


def to_xlsx(data: ReportData, farm: Any, user: Any) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="1B5E20")

    ws = wb.active
    ws.title = "Summary"
    ws.append([farm.name])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([data.title])
    ws["A2"].font = Font(bold=True, size=12)
    ws.append(["Period", data.period.start, data.period.end])
    ws["B3"].number_format = ws["C3"].number_format = "dd mmm yyyy"
    ws.append(
        [
            "Generated",
            timezone.localtime().replace(tzinfo=None),
            f"by {user.full_name}" if user else "",
        ]
    )
    ws["B4"].number_format = "dd mmm yyyy hh:mm"
    ws.append([])
    ws.append(["Measure", "Value"])
    for c in ws[6]:
        c.font, c.fill = head_font, head_fill
    for card in data.summary:
        ws.append([card.label + (" (%)" if card.unit == "%" else ""), card.value])
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 16

    if data.chart and data.chart.labels:
        ws_c = wb.create_sheet("Chart data")
        ws_c.append(["", *[s["name"] for s in data.chart.series]])
        for c in ws_c[1]:
            c.font, c.fill = head_font, head_fill
        for i, label in enumerate(data.chart.labels):
            ws_c.append([label, *[s["values"][i] for s in data.chart.series]])
        ws_c.column_dimensions["A"].width = 22

    used: set[str] = set()
    for table in data.tables:
        name = table.title[:31] or table.key[:31]
        while name in used:
            name = name[:28] + str(len(used))
        used.add(name)
        sheet = wb.create_sheet(name)
        sheet.append([c.label for c in table.columns])
        for c in sheet[1]:
            c.font, c.fill = head_font, head_fill
            c.alignment = Alignment(vertical="center")
        for row in table.rows:
            values = []
            for col in table.columns:
                v = row.get(col.key)
                if col.type == "percent" and isinstance(v, (int, float)):
                    v = v / 100
                values.append(v)
            sheet.append(values)
        for idx, col in enumerate(table.columns, start=1):
            letter = get_column_letter(idx)
            fmt = {"date": "dd mmm yyyy", "percent": "0%", "number": "General"}.get(col.type)
            if fmt:
                for cell in sheet[letter][1:]:
                    cell.number_format = fmt
            width = max(
                [len(col.label), *[len(cell_text(r.get(col.key), col)) for r in table.rows[:200]]]
            )
            sheet.column_dimensions[letter].width = min(max(width + 2, 10), 50)
        sheet.freeze_panes = "A2"
        if table.rows:
            sheet.auto_filter.ref = sheet.dimensions
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# --- PDF ------------------------------------------------------------------------------------------


def _logo(farm: Any) -> Any:
    from reportlab.platypus import Image

    if not getattr(farm, "logo", None):
        return None
    try:
        with default_storage.open(farm.logo.name, "rb") as fh:
            raw = io.BytesIO(fh.read())
        img = Image(raw, width=40, height=40, kind="proportional")
        return img
    except Exception:  # noqa: BLE001 - a missing logo never stops the report
        return None


def _chart(data: ReportData, width: float) -> Any:
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.legends import Legend
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors

    chart = data.chart
    if not chart or not chart.labels or not chart.series:
        return None
    height = 190
    d = Drawing(width, height)
    d.add(String(0, height - 12, chart.title, fontName="Helvetica-Bold", fontSize=10))
    bc = VerticalBarChart()
    bc.x, bc.y = 30, 40
    per_group = 1 if chart.stacked else len(chart.series)
    bc.width, bc.height = min(width - 40, 70 + 45 * len(chart.labels) * per_group), height - 80
    bc.data = [[float(v or 0) for v in s["values"]] for s in chart.series]
    bc.categoryAxis.categoryNames = [lbl[:12] for lbl in chart.labels]
    many = len(chart.labels) > 8
    bc.categoryAxis.labels.angle = 45 if many else 0
    bc.categoryAxis.labels.boxAnchor = "ne" if many else "n"
    bc.categoryAxis.labels.fontSize = 6 if many else 7
    bc.valueAxis.labels.fontSize = 7
    bc.valueAxis.valueMin = 0
    top = max(
        [sum(col) for col in zip(*bc.data, strict=False)]
        if chart.stacked
        else [max(s) for s in bc.data] or [0]
    )
    bc.valueAxis.valueMax = max(top * 1.15, 4)
    bc.valueAxis.valueStep = max(round(bc.valueAxis.valueMax / 4), 1)
    if chart.stacked:
        bc.categoryAxis.style = "stacked"
    for i in range(len(chart.series)):
        bc.bars[i].fillColor = colors.HexColor(GREYS[i % len(GREYS)])
        bc.bars[i].strokeColor = colors.black
        bc.bars[i].strokeWidth = 0.3
    d.add(bc)
    if len(chart.series) > 1:
        lg = Legend()
        lg.x, lg.y = width - 10, height - 8
        lg.alignment = "right"
        lg.boxAnchor = "ne"
        lg.columnMaximum = 1
        lg.fontSize = 7
        lg.dx = lg.dy = 7
        lg.deltax = 95
        lg.colorNamePairs = [
            (colors.HexColor(GREYS[i % len(GREYS)]), s["name"]) for i, s in enumerate(chart.series)
        ]
        lg.variColumn = 1
        d.add(lg)
    return d


def to_pdf(data: ReportData, farm: Any, user: Any) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    styles = getSampleStyleSheet()
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, leading=10)
    cell = ParagraphStyle("cell", parent=styles["Normal"], fontSize=7.5, leading=9)
    head = ParagraphStyle("head", parent=cell, fontName="Helvetica-Bold")
    h1 = ParagraphStyle(
        "h1", parent=styles["Title"], fontSize=16, leading=19, alignment=0, spaceAfter=2
    )
    h2 = ParagraphStyle(
        "h2", parent=styles["Heading2"], fontSize=11, leading=14, spaceBefore=8, spaceAfter=4
    )
    right = ParagraphStyle("right", parent=small, alignment=TA_RIGHT)
    big = ParagraphStyle("big", parent=styles["Normal"], fontSize=14, leading=17)

    buf = io.BytesIO()
    margin = 15 * mm
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=18 * mm,
        title=f"{data.title} – {farm.name}",
        author=user.full_name if user else "Smart Farm",
    )
    width = A4[0] - 2 * margin
    story: list[Any] = []

    # Letterhead
    details = " · ".join(
        x
        for x in [
            getattr(farm, "location", ""),
            getattr(farm, "county", ""),
            getattr(farm, "phone", ""),
            getattr(farm, "email", ""),
        ]
        if x
    )
    logo = _logo(farm)
    letter = [
        Paragraph(
            f"<b>{_esc(farm.name)}</b>",
            ParagraphStyle("farm", parent=styles["Normal"], fontSize=13, leading=16),
        ),
        Paragraph(_esc(details), small),
    ]
    generated = f"Generated {timezone.localtime():%d %b %Y %H:%M}" + (
        f" by {_esc(user.full_name)}" if user else ""
    )
    top = Table(
        [[logo or "", letter, Paragraph(generated, right)]],
        colWidths=[46 if logo else 0.1, width * 0.55, width * 0.45 - (46 if logo else 0.1)],
    )
    top.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, 0), 1, colors.black),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story += [top, Spacer(1, 8), Paragraph(_esc(data.title), h1)]
    period = (
        "As at " + f"{timezone.localdate():%d %b %Y}"
        if data.key == "livestock_register"
        else f"Period: {data.period.label()}"
    )
    if data.filters:
        period += " · Filters: " + ", ".join(
            f"{k.replace('_', ' ')}: {v}" for k, v in data.filters.items()
        )
    story += [Paragraph(_esc(period), small), Spacer(1, 8)]

    # Summary cards (4 per row)
    if data.summary:
        per_row = 4
        cells = [
            [
                [Paragraph(_esc(c.label), cell), Paragraph(f"<b>{_esc(card_text(c))}</b>", big)]
                for c in data.summary[i : i + per_row]
            ]
            for i in range(0, len(data.summary), per_row)
        ]
        for r in cells:
            r += [""] * (per_row - len(r))  # type: ignore[list-item]
        cards = Table(cells, colWidths=[width / per_row] * per_row)
        cards.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story += [cards, Spacer(1, 10)]

    chart = _chart(data, width)
    if chart is not None:
        story += [chart, Spacer(1, 6)]

    for table in data.tables:
        story.append(Paragraph(_esc(table.title), h2))
        if not table.rows:
            story.append(Paragraph("No records in this period.", small))
            continue
        rows = [[Paragraph(_esc(c.label), head) for c in table.columns]]
        rows += [
            [Paragraph(_esc(cell_text(r.get(c.key), c)), cell) for c in table.columns]
            for r in table.rows
        ]
        t = LongTable(rows, repeatRows=1, colWidths=_widths(table.columns, width))
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9d9d9")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    (
                        "ROWBACKGROUNDS",
                        (0, 1),
                        (-1, -1),
                        [colors.white, colors.HexColor("#f4f4f4")],
                    ),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        story.append(t)

    # Signature lines
    sign = Table(
        [
            ["", "", ""],
            [
                Paragraph("Farm manager<br/>Name, signature and date", small),
                "",
                Paragraph("Veterinary officer<br/>Name, signature and date", small),
            ],
        ],
        colWidths=[width * 0.42, width * 0.16, width * 0.42],
        rowHeights=[34, None],
    )
    sign.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (0, 0), 0.75, colors.black),
                ("LINEBELOW", (2, 0), (2, 0), 0.75, colors.black),
            ]
        )
    )
    story += [Spacer(1, 18), KeepTogether([sign])]

    footer = f"{farm.name} · {data.title}"
    doc.build(story, canvasmaker=_numbered(footer))
    return buf.getvalue()


def _widths(columns: list[Column], width: float) -> list[float]:
    weight = {"date": 1.1, "number": 0.8, "percent": 0.8}
    w = [
        weight.get(
            c.type,
            1.6 if c.key in ("details", "symptoms", "title", "action", "cause", "kids") else 1.2,
        )
        for c in columns
    ]
    total = sum(w)
    return [width * x / total for x in w]


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _numbered(footer: str) -> Any:
    from reportlab.pdfgen import canvas

    class NumberedCanvas(canvas.Canvas):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._pages: list[dict[str, Any]] = []

        def showPage(self) -> None:
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._pages)
            for state in self._pages:
                self.__dict__.update(state)
                self.setFont("Helvetica", 7.5)
                self.setFillGray(0.3)
                self.drawString(15 * 2.8346, 10 * 2.8346, footer[:110])
                self.drawRightString(
                    self._pagesize[0] - 15 * 2.8346,
                    10 * 2.8346,
                    f"Page {self._pageNumber} of {total}",
                )
                super().showPage()
            super().save()

    return NumberedCanvas


RENDERERS = {
    "pdf": ("application/pdf", to_pdf),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", to_xlsx),
    "csv": ("text/csv; charset=utf-8", lambda data, farm, user: to_csv(data)),
}


def render(data: ReportData, fmt: str, farm: Any, user: Any) -> tuple[bytes, str, str]:
    content_type, fn = RENDERERS[fmt]
    return fn(data, farm, user), content_type, filename(data, fmt)
