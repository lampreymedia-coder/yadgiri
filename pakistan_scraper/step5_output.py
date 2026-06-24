"""
======================================================
 گام ۵: خروجی کامل - Excel + CSV + گزارش فارسی
======================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from step4_analysis import build_summary, build_yearly_changes, load_data, year_columns


OUTPUT_DIR = Path("outputs")
EXCEL_OUTPUT = OUTPUT_DIR / "pakistan_prosperity.xlsx"
SUMMARY_OUTPUT = OUTPUT_DIR / "pakistan_prosperity_summary.csv"
YEARLY_OUTPUT = OUTPUT_DIR / "pakistan_prosperity_yearly_changes.csv"
REPORT_OUTPUT = OUTPUT_DIR / "pakistan_report.txt"


def format_value(value, decimals: int = 2) -> str:
    """یک عدد را به شکل خوانا فرمت می‌کند."""
    if value is None or pd.isna(value):
        return "ندارد"
    value = float(value)
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:,.2f} میلیارد"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:,.2f} میلیون"
    return f"{value:,.{decimals}f}"


def _safe_sheet_name(name: str) -> str:
    """Excel نام sheet بیشتر از 31 کاراکتر و بعضی کاراکترها را قبول نمی‌کند."""
    for char in "[]:*?/\\":  # noqa: W605
        name = name.replace(char, "-")
    return name[:31] or "Sheet"


def export_excel(
    df: pd.DataFrame,
    yearly_changes: pd.DataFrame,
    summary: pd.DataFrame,
    filepath: Path = EXCEL_OUTPUT,
) -> None:
    """یک فایل Excel با sheetهای جداگانه می‌سازد."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="raw_values", index=False)
        yearly_changes.to_excel(writer, sheet_name="yearly_changes", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)

        metadata_cols = [col for col in df.columns if not str(col).isdigit()]
        df[metadata_cols].to_excel(writer, sheet_name="metadata", index=False)

        for category, category_df in df.groupby("دسته", sort=False):
            category_df.to_excel(writer, sheet_name=_safe_sheet_name(category), index=False)

    print(f"  ✅ فایل Excel ذخیره شد: {filepath}")


def export_csvs(
    df: pd.DataFrame,
    yearly_changes: pd.DataFrame,
    summary: pd.DataFrame,
    output_dir: Path = OUTPUT_DIR,
) -> None:
    """CSVهای اصلی و CSV جداگانه برای هر دسته را ذخیره می‌کند."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_OUTPUT, index=False, encoding="utf-8-sig")
    yearly_changes.to_csv(YEARLY_OUTPUT, index=False, encoding="utf-8-sig")
    print(f"  ✅ {SUMMARY_OUTPUT}")
    print(f"  ✅ {YEARLY_OUTPUT}")

    for category, category_df in df.groupby("دسته", sort=False):
        filename = output_dir / f"PAK_{category.replace(' ', '_').replace('/', '_')}.csv"
        category_df.to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"  ✅ {filename}")


def _direction(change_pct) -> str:
    if change_pct is None or pd.isna(change_pct):
        return "بدون محاسبه"
    if change_pct > 0:
        return "افزایش"
    if change_pct < 0:
        return "کاهش"
    return "بدون تغییر"


def generate_text_report(
    df: pd.DataFrame,
    yearly_changes: pd.DataFrame,
    summary: pd.DataFrame,
    filepath: Path = REPORT_OUTPUT,
) -> str:
    """گزارش فارسی بخش‌بندی‌شده تولید می‌کند."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    years = year_columns(df)
    lines = []

    lines.append("=" * 78)
    lines.append("گزارش جامع شاخص‌های Prosperity پاکستان")
    lines.append("منبع داده: World Bank Data360 API")
    lines.append("صفحه مرجع: https://data360.worldbank.org/en/economy/PAK?tab=Prosperity")
    lines.append("بازه خروجی: 2010 تا 2026")
    lines.append(f"تاریخ تهیه: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("توضیح مهم: اگر برای 2025 یا 2026 مقدار نمی‌بینید، یعنی منبع Data360 هنوز مقدار منتشر نکرده است.")
    lines.append("=" * 78)

    for category, category_df in df.groupby("دسته", sort=False):
        category_summary = summary[summary["دسته"] == category]
        lines.append(f"\n\n## {category}")
        lines.append("-" * 78)
        lines.append(f"تعداد شاخص در این بخش: {len(category_df)}")

        for _, raw_row in category_df.iterrows():
            item_summary = category_summary[
                category_summary["کد Data360"] == raw_row["کد Data360"]
            ].iloc[0]
            item_changes = yearly_changes[
                yearly_changes["کد Data360"] == raw_row["کد Data360"]
            ]

            lines.append(f"\n### {raw_row['شاخص']}")
            lines.append(f"- کد World Bank: {raw_row['کد World Bank']}")
            lines.append(f"- کد Data360: {raw_row['کد Data360']}")
            lines.append(f"- واحد: {raw_row.get('واحد') or 'نامشخص'}")
            lines.append(f"- موضوع Data360: {raw_row.get('موضوع‌های Data360') or 'نامشخص'}")

            if item_summary.get("وضعیت") != "دارای داده":
                lines.append("- وضعیت: داده‌ای برای بازه درخواستی موجود نیست.")
                continue

            change_pct = item_summary.get("تغییر کل %")
            lines.append(
                "- خلاصه: "
                f"از {int(item_summary['اولین سال موجود'])} تا {int(item_summary['آخرین سال موجود'])}، "
                f"مقدار از {format_value(item_summary['مقدار اولین سال'])} به "
                f"{format_value(item_summary['مقدار آخرین سال'])} رسید؛ "
                f"تغییر کل {format_value(item_summary['تغییر کل'])} "
                f"({format_value(change_pct)} درصد، {_direction(change_pct)})."
            )
            lines.append(
                f"- میانگین 2010-2019: {format_value(item_summary.get('میانگین 2010-2019'))} | "
                f"میانگین 2020-2026: {format_value(item_summary.get('میانگین 2020-2026'))}"
            )
            lines.append(
                f"- بیشترین مقدار: {format_value(item_summary.get('بیشترین مقدار'))} "
                f"در {int(item_summary['سال بیشترین مقدار'])} | "
                f"کمترین مقدار: {format_value(item_summary.get('کمترین مقدار'))} "
                f"در {int(item_summary['سال کمترین مقدار'])}"
            )

            lines.append("")
            lines.append("سال | مقدار | تغییر نسبت به مقدار قبلی")
            lines.append("--- | ---: | ---:")
            for _, change_row in item_changes.iterrows():
                value = change_row["مقدار"]
                change = change_row["تغییر نسبت به مقدار قبلی %"]
                change_text = "ندارد" if pd.isna(change) else f"{change:+.2f}%"
                lines.append(f"{int(change_row['سال'])} | {format_value(value)} | {change_text}")

    report_text = "\n".join(lines)
    filepath.write_text(report_text, encoding="utf-8")
    print(f"  ✅ گزارش متنی ذخیره شد: {filepath}")
    return report_text


if __name__ == "__main__":
    print("=" * 78)
    print("  تولید خروجی‌های نهایی")
    print("=" * 78)

    try:
        data_frame = load_data()
    except FileNotFoundError:
        print("❌ ابتدا step3_scraper.py را اجرا کن")
        raise SystemExit(1)

    yearly = build_yearly_changes(data_frame)
    summary_df = build_summary(data_frame)

    print("\n[۱] ساخت فایل Excel...")
    export_excel(data_frame, yearly, summary_df)

    print("\n[۲] ساخت CSVها...")
    export_csvs(data_frame, yearly, summary_df)

    print("\n[۳] ساخت گزارش متنی...")
    report = generate_text_report(data_frame, yearly, summary_df)

    print("\n" + "=" * 78)
    print("  ✅ همه خروجی‌ها آماده است!")
    print("  فایل‌ها داخل پوشه outputs هستند.")
    print("=" * 78)
    print("\n  پیش‌نمایش گزارش:")
    print("\n".join(report.splitlines()[:35]))
