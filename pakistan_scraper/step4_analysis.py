"""
======================================================
 گام ۴: تحلیل داده‌ها و نمایش تغییرات
======================================================

این فایل:
  - روند هر شاخص را از 2010 تا آخرین سال موجود نشون می‌ده
  - بهترین و بدترین سال را پیدا می‌کنه
  - میانگین دهه ۲۰۱۰ و دهه ۲۰۲۰ را مقایسه می‌کنه
  - تغییر کلی (از 2010 تا آخر) را محاسبه می‌کنه
"""

import pandas as pd
import numpy as np


# ---------------------------------------------------
# گام ۴.۱ - بارگذاری داده‌ها
# ---------------------------------------------------
def load_data(filepath="pakistan_prosperity_raw.csv"):
    df = pd.read_csv(filepath, index_col=["دسته", "شاخص"], encoding="utf-8-sig")
    df.columns = df.columns.astype(int)
    return df


# ---------------------------------------------------
# گام ۴.۲ - خلاصه آماری یک شاخص
# ---------------------------------------------------
def indicator_summary(series: pd.Series, name: str) -> dict:
    """
    آمار خلاصه یک شاخص زمانی رو حساب می‌کنه.

    Args:
        series: مقادیر سالانه (index = سال)
        name: نام شاخص

    Returns:
        dict با فیلدهای مفید
    """
    clean = series.dropna()

    if clean.empty:
        return {"شاخص": name, "وضعیت": "داده موجود نیست"}

    first_year = clean.index[0]
    last_year = clean.index[-1]
    first_val = clean.iloc[0]
    last_val = clean.iloc[-1]

    # تغییر کلی
    if first_val and first_val != 0:
        change_pct = ((last_val - first_val) / abs(first_val)) * 100
    else:
        change_pct = None

    # بهترین و بدترین سال
    best_year = clean.idxmax()
    worst_year = clean.idxmin()

    # میانگین دهه ۲۰۱۰ و ۲۰۲۰
    decade_2010 = clean[clean.index.isin(range(2010, 2020))].mean()
    decade_2020 = clean[clean.index.isin(range(2020, 2027))].mean()

    return {
        "شاخص": name,
        "اولین سال": first_year,
        "مقدار اول": first_val,
        "آخرین سال": last_year,
        "مقدار آخر": last_val,
        "تغییر %": change_pct,
        "بهترین سال": best_year,
        "بالاترین مقدار": clean[best_year],
        "بدترین سال": worst_year,
        "پایین‌ترین مقدار": clean[worst_year],
        "میانگین ۲۰۱۰-۲۰۱۹": decade_2010,
        "میانگین ۲۰۲۰-۲۰۲۶": decade_2020,
        "تعداد سال دارای داده": len(clean),
    }


# ---------------------------------------------------
# گام ۴.۳ - نمایش جدول روند
# ---------------------------------------------------
def print_trend_table(series: pd.Series, name: str, unit: str = ""):
    """
    جدول تغییرات سالانه یک شاخص را چاپ می‌کنه.
    """
    clean = series.dropna()
    if clean.empty:
        print(f"  {name}: داده موجود نیست")
        return

    print(f"\n  📊 {name} {unit}")
    print(f"  {'سال':<8} {'مقدار':>18} {'تغییر':>12}")
    print(f"  {'-' * 40}")

    prev = None
    for year, val in clean.items():
        if prev is not None and prev != 0:
            delta = val - prev
            arrow = "↑" if delta > 0 else "↓"
            delta_str = f"{arrow} {abs(delta):,.2f}"
        else:
            delta_str = "  ---"

        print(f"  {year:<8} {val:>18,.2f} {delta_str:>12}")
        prev = val


# ---------------------------------------------------
# گام ۴.۴ - مقایسه دو دهه برای یک دسته
# ---------------------------------------------------
def compare_decades(df: pd.DataFrame, category: str):
    """
    میانگین هر شاخص را در دو دهه مقایسه می‌کنه.
    """
    try:
        cat_df = df.loc[category]
    except KeyError:
        print(f"  دسته '{category}' پیدا نشد")
        return

    years_2010s = [y for y in range(2010, 2020) if y in df.columns]
    years_2020s = [y for y in range(2020, 2027) if y in df.columns]

    rows = []
    for indicator in cat_df.index:
        row = cat_df.loc[indicator]
        avg_2010s = row[years_2010s].mean() if years_2010s else None
        avg_2020s = row[years_2020s].mean() if years_2020s else None

        if pd.notna(avg_2010s) and pd.notna(avg_2020s) and avg_2010s != 0:
            change = ((avg_2020s - avg_2010s) / abs(avg_2010s)) * 100
        else:
            change = None

        rows.append({
            "شاخص": indicator,
            "میانگین ۲۰۱۰-۲۰۱۹": avg_2010s,
            "میانگین ۲۰۲۰-۲۰۲۶": avg_2020s,
            "تغییر %": change,
        })

    result = pd.DataFrame(rows).set_index("شاخص")
    return result


# ---------------------------------------------------
# اجرای اصلی
# ---------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  تحلیل داده‌های Prosperity پاکستان (2010-2026)")
    print("=" * 60)

    # بارگذاری
    try:
        df = load_data("pakistan_prosperity_raw.csv")
        print(f"\n✅ داده‌ها بارگذاری شدند: {df.shape[0]} شاخص، {df.shape[1]} سال\n")
    except FileNotFoundError:
        print("❌ ابتدا step3_scraper.py را اجرا کن تا فایل CSV ساخته بشه")
        exit(1)

    # -----------------------------------------------
    # نمایش روند GDP سرانه
    # -----------------------------------------------
    print("\n" + "=" * 60)
    print("  GDP سرانه پاکستان - روند سالانه")
    print("=" * 60)

    try:
        gdp_pc = df.loc[("رشد اقتصادی", "GDP سرانه (دلار)")]
        print_trend_table(gdp_pc, "GDP سرانه", "(دلار آمریکا)")
        summary = indicator_summary(gdp_pc, "GDP سرانه")
        print(f"\n  📌 خلاصه:")
        print(f"     از {summary['اولین سال']} تا {summary['آخرین سال']}")
        if summary.get('تغییر %'):
            print(f"     تغییر کلی: {summary['تغییر %']:+.1f}%")
    except KeyError:
        print("  داده GDP سرانه موجود نیست")

    # -----------------------------------------------
    # مقایسه دو دهه - همه دسته‌ها
    # -----------------------------------------------
    categories = df.index.get_level_values(0).unique().tolist()

    for cat in categories:
        print(f"\n{'=' * 60}")
        print(f"  مقایسه دو دهه: {cat}")
        print(f"{'=' * 60}")

        result = compare_decades(df, cat)
        if result is not None and not result.empty:
            # فقط ردیف‌هایی که داده دارند
            result = result.dropna(subset=["میانگین ۲۰۱۰-۲۰۱۹", "میانگین ۲۰۲۰-۲۰۲۶"])

            if not result.empty:
                # قالب‌بندی اعداد
                pd.set_option("display.float_format", "{:,.2f}".format)
                pd.set_option("display.max_colwidth", 45)
                pd.set_option("display.width", 120)
                print(result.to_string())
            else:
                print("  (داده کافی برای مقایسه وجود ندارد)")

    print(f"\n\n✅ تحلیل کامل شد. برای خروجی نهایی step5_output.py را اجرا کن.")
