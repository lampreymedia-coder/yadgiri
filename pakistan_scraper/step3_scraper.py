"""
======================================================
 گام ۳: اسکرپر اصلی - دریافت همه داده‌ها
======================================================

این فایل همه شاخص‌ها را از World Bank API می‌گیره
و به DataFrame تبدیل می‌کنه.
"""

import requests
import pandas as pd
import time
from step2_indicators import PROSPERITY_INDICATORS

# ---------------------------------------------------
# تنظیمات
# ---------------------------------------------------
COUNTRY = "PAK"
START_YEAR = 2010
END_YEAR = 2026
DELAY_BETWEEN_REQUESTS = 0.5  # ثانیه - تا سرور بلاکمون نکنه


# ---------------------------------------------------
# گام ۳.۱ - تابع دریافت یک شاخص
# ---------------------------------------------------
def fetch_indicator(code, name, country=COUNTRY):
    """یک شاخص را از API می‌گیره و به dict تبدیل می‌کنه"""

    url = (
        f"https://api.worldbank.org/v2/country/{country}"
        f"/indicator/{code}"
        f"?format=json&date={START_YEAR}:{END_YEAR}&per_page=100"
    )

    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if len(data) < 2 or not data[1]:
            return {}

        # تبدیل به dict: {سال: مقدار}
        result = {}
        for entry in data[1]:
            year = int(entry["date"])
            value = entry["value"]
            result[year] = value

        return result

    except Exception as e:
        print(f"    ⚠ خطا در {code}: {e}")
        return {}


# ---------------------------------------------------
# گام ۳.۲ - دریافت همه شاخص‌ها
# ---------------------------------------------------
def scrape_all_indicators():
    """
    همه شاخص‌های تعریف‌شده را می‌گیره.

    Returns:
        dict: {category -> {indicator_name -> {year -> value}}}
    """
    all_data = {}
    years = list(range(START_YEAR, END_YEAR + 1))

    total_indicators = sum(len(v) for v in PROSPERITY_INDICATORS.values())
    done = 0

    for category, indicators in PROSPERITY_INDICATORS.items():
        print(f"\n{'=' * 55}")
        print(f"  دسته: {category}")
        print(f"{'=' * 55}")

        category_data = {}

        for code, name in indicators.items():
            done += 1
            print(f"  [{done}/{total_indicators}] {name}...")

            raw = fetch_indicator(code, name)

            # ساخت سری زمانی کامل (سال‌های بدون داده = None)
            series = {year: raw.get(year) for year in years}
            category_data[name] = series

            time.sleep(DELAY_BETWEEN_REQUESTS)

        all_data[category] = category_data

    return all_data


# ---------------------------------------------------
# گام ۳.۳ - تبدیل به DataFrame
# ---------------------------------------------------
def to_dataframe(all_data):
    """
    داده‌ها را به یک DataFrame چند سطحی تبدیل می‌کنه.

    ستون‌ها: سال‌ها (2010 تا 2026)
    ردیف‌ها: (دسته, نام شاخص)
    """
    rows = []

    for category, indicators in all_data.items():
        # حذف ایموجی از نام دسته برای DataFrame
        cat_clean = category.split(" ", 1)[1] if " " in category else category

        for name, year_data in indicators.items():
            row = {"دسته": cat_clean, "شاخص": name}
            row.update(year_data)
            rows.append(row)

    df = pd.DataFrame(rows)
    df = df.set_index(["دسته", "شاخص"])
    df = df.sort_index()

    return df


# ---------------------------------------------------
# اجرای اصلی
# ---------------------------------------------------
if __name__ == "__main__":
    print("=" * 55)
    print("  شروع دریافت داده‌های پاکستان از World Bank")
    print(f"  بازه زمانی: {START_YEAR} تا {END_YEAR}")
    print("=" * 55)

    # دریافت داده‌ها
    all_data = scrape_all_indicators()

    # تبدیل به DataFrame
    df = to_dataframe(all_data)

    print(f"\n\n{'=' * 55}")
    print(f"  داده‌ها دریافت شدند!")
    print(f"  تعداد شاخص‌ها: {len(df)}")
    print(f"  تعداد سال‌ها: {len(df.columns)}")
    print(f"{'=' * 55}")
    print("\n  پیش‌نمایش:")
    print(df.head(10).to_string())

    # ذخیره برای گام بعدی
    df.to_csv("pakistan_prosperity_raw.csv", encoding="utf-8-sig")
    print("\n✅ داده‌ها در pakistan_prosperity_raw.csv ذخیره شدند")

    # برگردوندن df برای استفاده در فایل‌های بعدی
    print("\n  آماده برای گام ۴: تحلیل و خروجی...")
