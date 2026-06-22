"""
======================================================
 گام ۵: خروجی کامل - Excel + گزارش متنی
======================================================

خروجی‌ها:
  1. pakistan_prosperity.xlsx  - فایل Excel با Sheet جداگانه
  2. pakistan_report.txt       - گزارش متنی خوانا
"""

import pandas as pd
import numpy as np
from datetime import datetime
from step4_analysis import load_data, indicator_summary, compare_decades


# ---------------------------------------------------
# گام ۵.۱ - خروجی Excel
# ---------------------------------------------------
def export_excel(df: pd.DataFrame, filepath="pakistan_prosperity.xlsx"):
    """
    یک فایل Excel می‌سازه با:
      - Sheet اصلی: همه داده‌ها
      - یک Sheet برای هر دسته
      - Sheet خلاصه: مقایسه دو دهه
    """
    with pd.ExcelWriter(filepath, engine="openpyxl") as writer:

        # --- Sheet اول: همه داده‌ها ---
        df.to_excel(writer, sheet_name="همه داده‌ها")

        # --- Sheet جداگانه برای هر دسته ---
        categories = df.index.get_level_values(0).unique()
        for cat in categories:
            cat_df = df.loc[cat]
            # نام Sheet نباید بیشتر از 31 کاراکتر باشه
            sheet_name = cat[:31]
            cat_df.to_excel(writer, sheet_name=sheet_name)

        # --- Sheet خلاصه: مقایسه دهه‌ها ---
        summary_rows = []
        for cat in categories:
            result = compare_decades(df, cat)
            if result is not None:
                result["دسته"] = cat
                summary_rows.append(result.reset_index())

        if summary_rows:
            summary_df = pd.concat(summary_rows, ignore_index=True)
            summary_df = summary_df[["دسته", "شاخص", "میانگین ۲۰۱۰-۲۰۱۹", "میانگین ۲۰۲۰-۲۰۲۶", "تغییر %"]]
            summary_df.to_excel(writer, sheet_name="خلاصه مقایسه", index=False)

    print(f"  ✅ فایل Excel ذخیره شد: {filepath}")


# ---------------------------------------------------
# گام ۵.۲ - گزارش متنی
# ---------------------------------------------------
def format_value(val, decimals=2):
    """یک عدد را به شکل خوانا فرمت می‌کنه"""
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "ندارد"
    if abs(val) >= 1_000_000_000:
        return f"{val/1_000_000_000:,.1f} میلیارد"
    if abs(val) >= 1_000_000:
        return f"{val/1_000_000:,.1f} میلیون"
    return f"{val:,.{decimals}f}"


def generate_text_report(df: pd.DataFrame, filepath="pakistan_report.txt"):
    """
    یک گزارش متنی کامل تولید می‌کنه.
    """
    lines = []
    sep = "=" * 65

    lines.append(sep)
    lines.append("  گزارش جامع شاخص‌های رفاه پاکستان")
    lines.append(f"  منبع: World Bank Data360")
    lines.append(f"  بازه زمانی: 2010 تا 2026")
    lines.append(f"  تاریخ تهیه: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(sep)

    years = sorted(df.columns.tolist())
    categories = df.index.get_level_values(0).unique()

    for cat in categories:
        lines.append(f"\n\n{'#' * 65}")
        lines.append(f"  {cat}")
        lines.append(f"{'#' * 65}")

        try:
            cat_df = df.loc[cat]
        except KeyError:
            continue

        for indicator in cat_df.index:
            series = cat_df.loc[indicator]
            clean = series.dropna()

            lines.append(f"\n  ─── {indicator} ───")

            if clean.empty:
                lines.append("    (داده موجود نیست)")
                continue

            # جدول سالانه
            lines.append(f"    {'سال':<8} {'مقدار':>20}")
            lines.append(f"    {'-' * 30}")

            prev = None
            for year in years:
                val = series.get(year)
                if pd.notna(val):
                    if prev is not None and prev != 0:
                        delta = ((val - prev) / abs(prev)) * 100
                        arrow = "↑" if delta > 0 else "↓"
                        delta_str = f"  ({arrow}{abs(delta):.1f}%)"
                    else:
                        delta_str = ""
                    lines.append(f"    {year:<8} {format_value(val):>20}{delta_str}")
                    prev = val
                else:
                    lines.append(f"    {year:<8} {'—':>20}")

            # خلاصه
            summ = indicator_summary(series, indicator)
            lines.append(f"\n    خلاصه:")
            lines.append(f"      اولین مقدار ({summ.get('اولین سال','؟')}): {format_value(summ.get('مقدار اول'))}")
            lines.append(f"      آخرین مقدار ({summ.get('آخرین سال','؟')}): {format_value(summ.get('مقدار آخر'))}")
            if summ.get("تغییر %") is not None:
                change = summ["تغییر %"]
                trend = "بهبود ↑" if change > 0 else "کاهش ↓"
                lines.append(f"      تغییر کلی: {change:+.1f}% ({trend})")
            avg10 = summ.get("میانگین ۲۰۱۰-۲۰۱۹")
            avg20 = summ.get("میانگین ۲۰۲۰-۲۰۲۶")
            if pd.notna(avg10):
                lines.append(f"      میانگین ۲۰۱۰-۲۰۱۹: {format_value(avg10)}")
            if pd.notna(avg20):
                lines.append(f"      میانگین ۲۰۲۰-۲۰۲۶: {format_value(avg20)}")

    # انتها
    lines.append(f"\n\n{sep}")
    lines.append("  پایان گزارش")
    lines.append(sep)

    report_text = "\n".join(lines)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"  ✅ گزارش متنی ذخیره شد: {filepath}")
    return report_text


# ---------------------------------------------------
# گام ۵.۳ - خروجی CSV تمیز به تفکیک دسته
# ---------------------------------------------------
def export_category_csvs(df: pd.DataFrame):
    """یک CSV جداگانه برای هر دسته"""
    categories = df.index.get_level_values(0).unique()
    for cat in categories:
        cat_df = df.loc[cat]
        filename = f"PAK_{cat.replace(' ', '_').replace('/', '_')}.csv"
        cat_df.to_csv(filename, encoding="utf-8-sig")
        print(f"  ✅ {filename}")


# ---------------------------------------------------
# اجرای اصلی
# ---------------------------------------------------
if __name__ == "__main__":
    print("=" * 65)
    print("  تولید خروجی‌های نهایی")
    print("=" * 65)

    try:
        df = load_data("pakistan_prosperity_raw.csv")
    except FileNotFoundError:
        print("❌ ابتدا step3_scraper.py را اجرا کن")
        exit(1)

    print("\n[۱] ساخت فایل Excel...")
    export_excel(df)

    print("\n[۲] ساخت گزارش متنی...")
    report = generate_text_report(df)

    print("\n[۳] ساخت CSV‌های جداگانه...")
    export_category_csvs(df)

    print("\n" + "=" * 65)
    print("  ✅ همه خروجی‌ها آماده است!")
    print()
    print("  فایل‌های تولیدشده:")
    print("    📊 pakistan_prosperity.xlsx  - Excel با Sheet جداگانه")
    print("    📝 pakistan_report.txt       - گزارش متنی کامل")
    print("    📂 PAK_*.csv                 - CSV به تفکیک دسته")
    print("=" * 65)

    # نمایش ۳۰ خط اول گزارش
    print("\n  پیش‌نمایش گزارش:")
    print("\n".join(report.split("\n")[:30]))
