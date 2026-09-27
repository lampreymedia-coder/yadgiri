"""Excel export: right-to-left sheet, Persian headers, Shamsi dates."""

from __future__ import annotations

import io
from datetime import datetime

import jdatetime
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

from app.domain.reports import ExportRow
from app.mapping import POST_CONTENT_LABELS

HEADERS = [
    "شماره ثبت",
    "تاریخ ثبت (شمسی)",
    "تاریخ ارسال (شمسی)",
    "فرستنده",
    "شناسه بله",
    "گروه",
    "نوع محتوا",
    "هشتگ‌ها",
    "تعداد فایل",
    "متن",
]
WIDTHS = [10, 18, 18, 26, 14, 22, 12, 30, 10, 60]


def shamsi(value: datetime | None) -> str:
    if value is None:
        return ""
    return jdatetime.datetime.fromgregorian(datetime=value).strftime("%Y/%m/%d %H:%M")


def build_workbook(rows: list[ExportRow], title: str = "آرشیو") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = title[:31]
    sheet.sheet_view.rightToLeft = True
    sheet.append(HEADERS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        sheet.append(
            [
                row.post_id,
                shamsi(row.created_at),
                shamsi(row.posted_at),
                row.sender,
                row.bale_user_id,
                row.group_name,
                POST_CONTENT_LABELS.get(row.content_type, str(row.content_type)),
                row.hashtags,
                row.files,
                row.content_text,
            ]
        )
    for index, width in enumerate(WIDTHS, start=1):
        sheet.column_dimensions[sheet.cell(row=1, column=index).column_letter].width = width
    sheet.freeze_panes = "A2"
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()
