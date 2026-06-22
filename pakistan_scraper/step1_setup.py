"""
======================================================
 گام ۱: آشنایی با World Bank API و تست اتصال
======================================================

World Bank یک API کاملاً رایگان و عمومی دارد:
  https://api.worldbank.org/v2/

ساختار URL:
  /v2/country/{country_code}/indicator/{indicator_code}
  ?format=json
  &date={start}:{end}
  &per_page={تعداد نتایج}

برای پاکستان: country_code = PAK
"""

import requests
import json

# ---------------------------------------------------
# تابع کمکی: دریافت داده از API
# ---------------------------------------------------
def fetch_worldbank(indicator_code, country="PAK", start=2010, end=2026, per_page=100):
    """
    از World Bank API داده می‌گیره.

    Args:
        indicator_code: کد شاخص (مثل NY.GDP.MKTP.CD برای GDP)
        country: کد ۳ حرفی کشور
        start: سال شروع
        end: سال پایان
        per_page: حداکثر تعداد نتایج

    Returns:
        list of dicts یا None اگر خطا داشت
    """
    url = (
        f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator_code}"
        f"?format=json&date={start}:{end}&per_page={per_page}"
    )

    print(f"  درحال دریافت: {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # API یک لیست ۲ عنصری برمی‌گردونه:
        # [0] = اطلاعات pagination
        # [1] = داده‌های واقعی
        if len(data) < 2 or data[1] is None:
            print(f"  هیچ داده‌ای برای {indicator_code} پیدا نشد")
            return []

        return data[1]

    except requests.exceptions.RequestException as e:
        print(f"  خطا در دریافت داده: {e}")
        return []


# ---------------------------------------------------
# تست اول: فقط یک شاخص ساده
# ---------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  تست اتصال به World Bank API")
    print("=" * 60)

    # GDP (تولید ناخالص داخلی) پاکستان
    print("\n[۱] دریافت GDP پاکستان (2020-2023)...")
    gdp_data = fetch_worldbank("NY.GDP.MKTP.CD", start=2020, end=2023)

    if gdp_data:
        print("\n  نتایج خام (JSON):")
        print(json.dumps(gdp_data[0], indent=4, ensure_ascii=False))

        print("\n  فرمت ساده:")
        for entry in gdp_data:
            year = entry.get("date")
            value = entry.get("value")
            if value is not None:
                print(f"    سال {year}: ${value:,.0f}")

        print("\n✅ اتصال موفق! گام ۱ کامل شد.")
    else:
        print("\n❌ خطا در اتصال. اینترنت را چک کنید.")
