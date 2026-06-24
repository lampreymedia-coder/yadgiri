"""
======================================================
 گام ۳: اسکرپر اصلی - دریافت داده‌ها از Data360
======================================================

این فایل برای هر شاخص:
  1. شناسه Data360 را می‌سازد.
  2. endpoint /data را با فیلتر کشور پاکستان صدا می‌زند.
  3. سال‌های 2010 تا 2026 را به جدول ثابت تبدیل می‌کند.
  4. metadata/topicهای Data360 را هم کنار داده ذخیره می‌کند.
"""

from pathlib import Path
import time

import pandas as pd

from data360_client import (
    DEFAULT_COUNTRY,
    DEFAULT_DATABASE_ID,
    DEFAULT_END_YEAR,
    DEFAULT_START_YEAR,
    extract_data360_topics,
    fetch_admin_metadata,
    fetch_indicator_data,
    get_session,
    normalize_series,
    select_best_series,
)
from step2_indicators import iter_indicators


COUNTRY = DEFAULT_COUNTRY
START_YEAR = DEFAULT_START_YEAR
END_YEAR = DEFAULT_END_YEAR
OUTPUT_DIR = Path("outputs")
RAW_OUTPUT = OUTPUT_DIR / "pakistan_prosperity_raw.csv"
DELAY_BETWEEN_REQUESTS = 0.2


def scrape_all_indicators() -> pd.DataFrame:
    """همه شاخص‌ها را از Data360 دریافت و به DataFrame عریض تبدیل می‌کند."""
    indicators = list(iter_indicators())
    years = list(range(START_YEAR, END_YEAR + 1))
    session = get_session()

    print("  دریافت metadata شاخص‌ها از Data360...")
    metadata_by_id = fetch_admin_metadata(
        [item["data360_id"] for item in indicators],
        session=session,
    )

    rows = []
    total = len(indicators)
    for index, item in enumerate(indicators, start=1):
        print(f"  [{index}/{total}] {item['name_fa']} ({item['data360_id']})")
        try:
            raw_rows = fetch_indicator_data(
                item["data360_id"],
                database_id=DEFAULT_DATABASE_ID,
                country=COUNTRY,
                session=session,
            )
            selected = select_best_series(raw_rows, country=COUNTRY)
            values = normalize_series(selected, start_year=START_YEAR, end_year=END_YEAR)
        except Exception as exc:
            print(f"    هشدار: دریافت این شاخص ناموفق بود: {exc}")
            selected = None
            values = {year: None for year in years}

        admin_metadata = metadata_by_id.get(item["data360_id"], {})
        topic_labels, topic_ids = extract_data360_topics(admin_metadata)
        non_null_count = sum(value is not None for value in values.values())

        row = {
            "دسته": item["category"],
            "شاخص": item["name_fa"],
            "کد World Bank": item["world_bank_code"],
            "کد Data360": item["data360_id"],
            "پایگاه داده": DEFAULT_DATABASE_ID,
            "کشور": COUNTRY,
            "واحد": selected.get("UNIT_MEASURE") if selected else None,
            "بازه منبع": selected.get("range") if selected else None,
            "موضوع‌های Data360": topic_labels,
            "کد موضوع‌های Data360": topic_ids,
            "تعداد سال دارای داده": non_null_count,
        }
        row.update(values)
        rows.append(row)
        time.sleep(DELAY_BETWEEN_REQUESTS)

    df = pd.DataFrame(rows)
    metadata_columns = [
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
    df = df[metadata_columns + years]
    return df


def save_raw_data(df: pd.DataFrame, filepath: Path = RAW_OUTPUT) -> None:
    """فایل خام عریض را ذخیره می‌کند."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    print(f"\n✅ داده خام ذخیره شد: {filepath}")


if __name__ == "__main__":
    print("=" * 65)
    print("  شروع دریافت داده‌های Prosperity پاکستان از World Bank Data360")
    print(f"  کشور: {COUNTRY}")
    print(f"  بازه زمانی خروجی: {START_YEAR} تا {END_YEAR}")
    print("=" * 65)

    data_frame = scrape_all_indicators()
    save_raw_data(data_frame)

    print(f"\n  تعداد شاخص‌ها: {len(data_frame)}")
    print(f"  تعداد ستون‌های سالانه: {END_YEAR - START_YEAR + 1}")
    print("\n  پیش‌نمایش:")
    print(data_frame.head(8).to_string(index=False))
    print("\n  آماده برای گام ۴: تحلیل تغییرات سالانه...")
