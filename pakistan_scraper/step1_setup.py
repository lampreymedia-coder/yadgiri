"""
======================================================
 گام ۱: آشنایی با Data360 API و تست اتصال
======================================================

در صفحه Data360، داده‌ها از endpoint زیر می‌آیند:
  https://data360api.worldbank.org/data360/portal/v1/data

پارامترهای اصلی:
  database_id = WB_WDI
  indicator_id = WB_WDI_NY_GDP_PCAP_CD
  filters = [{"filterColumn":"REF_AREA","filterValue":"PAK"}]
"""

from data360_client import (
    fetch_indicator_data,
    normalize_series,
    select_best_series,
    world_bank_code_to_data360_id,
)


if __name__ == "__main__":
    print("=" * 70)
    print("  تست اتصال به World Bank Data360 API")
    print("=" * 70)

    indicator_id = world_bank_code_to_data360_id("NY.GDP.PCAP.CD")
    print(f"\n[۱] دریافت GDP سرانه پاکستان با شناسه Data360: {indicator_id}")

    rows = fetch_indicator_data(indicator_id)
    selected = select_best_series(rows)
    series = normalize_series(selected, start_year=2020, end_year=2024)

    if selected:
        print("\n  نمونه metadata سری انتخاب‌شده:")
        print(f"    REF_AREA: {selected.get('REF_AREA')}")
        print(f"    UNIT_MEASURE: {selected.get('UNIT_MEASURE')}")
        print(f"    range: {selected.get('range')}")

        print("\n  فرمت ساده:")
        for year, value in series.items():
            if value is not None:
                print(f"    سال {year}: {value:,.2f}")
            else:
                print(f"    سال {year}: داده منتشر نشده")

        print("\n✅ اتصال موفق! گام ۱ کامل شد.")
    else:
        print("\n❌ داده‌ای دریافت نشد. اتصال اینترنت یا endpoint را بررسی کن.")
