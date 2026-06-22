"""
======================================================
 گام ۴: تحلیل داده‌ها و محاسبه تغییرات
======================================================

خروجی‌های اصلی این گام:
  - جدول long برای مقایسه سال‌به‌سال هر شاخص
  - جدول summary برای مقایسه اولین و آخرین مقدار موجود
  - مقایسه میانگین 2010-2019 با 2020-2026
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


RAW_INPUT = Path("outputs/pakistan_prosperity_raw.csv")
YEAR_START = 2010
YEAR_END = 2026

METADATA_COLUMNS = [
    "دسته",
    "شاخص",
    "کد World Bank",
    "کد Data360",
    "پایگاه داده",
    "کشور",
    "واحد",
    "بازه منبع",
    "موضوع‌های Data360",
    "کد موضوع‌های Data360",
    "تعداد سال دارای داده",
]


def load_data(filepath: str | Path = RAW_INPUT) -> pd.DataFrame:
    """داده خام ذخیره‌شده در گام ۳ را بارگذاری می‌کند."""
    df = pd.read_csv(filepath, encoding="utf-8-sig")
    for column in df.columns:
        if str(column).isdigit():
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def year_columns(df: pd.DataFrame) -> list[str]:
    """ستون‌های سالانه را به ترتیب برمی‌گرداند."""
    return sorted([column for column in df.columns if str(column).isdigit()], key=lambda item: int(item))


def _clean_series(row: pd.Series, years: list[str]) -> pd.Series:
    series = row[years].copy()
    series.index = [int(year) for year in years]
    return pd.to_numeric(series, errors="coerce").dropna()


def _pct_change(new_value: float, old_value: float) -> float | None:
    if pd.isna(new_value) or pd.isna(old_value) or old_value == 0:
        return None
    return ((new_value - old_value) / abs(old_value)) * 100


def indicator_summary(row: pd.Series, years: list[str]) -> dict:
    """آمار خلاصه یک شاخص را از روی ردیف wide می‌سازد."""
    clean = _clean_series(row, years)
    base = {
        "دسته": row["دسته"],
        "شاخص": row["شاخص"],
        "کد World Bank": row["کد World Bank"],
        "کد Data360": row["کد Data360"],
        "واحد": row.get("واحد"),
        "موضوع‌های Data360": row.get("موضوع‌های Data360"),
    }

    if clean.empty:
        return {
            **base,
            "وضعیت": "داده موجود نیست",
            "تعداد سال دارای داده": 0,
        }

    first_year = int(clean.index[0])
    last_year = int(clean.index[-1])
    first_value = float(clean.iloc[0])
    last_value = float(clean.iloc[-1])
    max_year = int(clean.idxmax())
    min_year = int(clean.idxmin())

    years_2010s = [year for year in clean.index if 2010 <= year <= 2019]
    years_2020s = [year for year in clean.index if 2020 <= year <= 2026]
    avg_2010s = clean.loc[years_2010s].mean() if years_2010s else None
    avg_2020s = clean.loc[years_2020s].mean() if years_2020s else None

    return {
        **base,
        "وضعیت": "دارای داده",
        "اولین سال موجود": first_year,
        "مقدار اولین سال": first_value,
        "آخرین سال موجود": last_year,
        "مقدار آخرین سال": last_value,
        "تغییر کل": last_value - first_value,
        "تغییر کل %": _pct_change(last_value, first_value),
        "سال بیشترین مقدار": max_year,
        "بیشترین مقدار": float(clean.loc[max_year]),
        "سال کمترین مقدار": min_year,
        "کمترین مقدار": float(clean.loc[min_year]),
        "میانگین 2010-2019": avg_2010s,
        "میانگین 2020-2026": avg_2020s,
        "تغییر میانگین دوره‌ها %": _pct_change(avg_2020s, avg_2010s) if avg_2010s is not None else None,
        "تعداد سال دارای داده": int(clean.count()),
    }


def build_summary(df: pd.DataFrame) -> pd.DataFrame:
    """یک جدول خلاصه برای همه شاخص‌ها می‌سازد."""
    years = year_columns(df)
    rows = [indicator_summary(row, years) for _, row in df.iterrows()]
    return pd.DataFrame(rows)


def build_yearly_changes(df: pd.DataFrame) -> pd.DataFrame:
    """داده را از حالت wide به جدول long با تغییر سالانه تبدیل می‌کند."""
    years = year_columns(df)
    rows = []
    for _, row in df.iterrows():
        previous_value = None
        previous_year = None
        for year in years:
            value = row[year]
            if pd.notna(value):
                change_abs = value - previous_value if previous_value is not None else None
                change_pct = _pct_change(value, previous_value) if previous_value is not None else None
                comparison_year = previous_year
                previous_value = value
                previous_year = int(year)
            else:
                change_abs = None
                change_pct = None
                comparison_year = None

            rows.append(
                {
                    "دسته": row["دسته"],
                    "شاخص": row["شاخص"],
                    "کد World Bank": row["کد World Bank"],
                    "کد Data360": row["کد Data360"],
                    "واحد": row.get("واحد"),
                    "سال": int(year),
                    "مقدار": value if pd.notna(value) else None,
                    "سال مقایسه قبلی": comparison_year,
                    "تغییر نسبت به مقدار قبلی": change_abs,
                    "تغییر نسبت به مقدار قبلی %": change_pct,
                }
            )
    return pd.DataFrame(rows)


def print_category_summary(summary_df: pd.DataFrame) -> None:
    """خلاصه دسته‌ها را در ترمینال چاپ می‌کند."""
    pd.set_option("display.float_format", "{:,.2f}".format)
    pd.set_option("display.max_colwidth", 42)
    pd.set_option("display.width", 150)

    for category, category_df in summary_df.groupby("دسته", sort=False):
        print(f"\n{'=' * 70}")
        print(f"  دسته: {category}")
        print(f"{'=' * 70}")
        columns = [
            "شاخص",
            "اولین سال موجود",
            "آخرین سال موجود",
            "تغییر کل %",
            "میانگین 2010-2019",
            "میانگین 2020-2026",
            "تعداد سال دارای داده",
        ]
        print(category_df[columns].to_string(index=False))


if __name__ == "__main__":
    print("=" * 70)
    print("  تحلیل داده‌های Prosperity پاکستان (2010-2026)")
    print("=" * 70)

    try:
        data_frame = load_data()
    except FileNotFoundError:
        print("❌ ابتدا step3_scraper.py را اجرا کن تا فایل outputs/pakistan_prosperity_raw.csv ساخته شود")
        raise SystemExit(1)

    summary = build_summary(data_frame)
    yearly_changes = build_yearly_changes(data_frame)

    print(f"\n✅ داده‌ها بارگذاری شدند: {len(data_frame)} شاخص")
    print(f"✅ جدول تغییرات سالانه ساخته شد: {len(yearly_changes)} ردیف")
    print_category_summary(summary)
    print("\n✅ تحلیل کامل شد. برای خروجی نهایی step5_output.py را اجرا کن.")
