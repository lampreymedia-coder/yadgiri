"""
======================================================
 اجرای کامل همه گام‌ها یکجا
======================================================

فقط این فایل را اجرا کن:
  python run_all.py

و همه چیز خودکار انجام می‌شه.
"""

import sys

print("""
╔══════════════════════════════════════════════════════╗
║   اسکرپر داده‌های Prosperity پاکستان               ║
║   منبع: World Bank API (رایگان، بدون نیاز به Key)  ║
║   بازه: 2010 تا 2026                               ║
╚══════════════════════════════════════════════════════╝
""")

# --- گام ۱: بررسی وابستگی‌ها ---
print("🔍 بررسی پکیج‌های مورد نیاز...")
try:
    import requests
    import pandas
    import openpyxl
    print("  ✅ همه پکیج‌ها نصب هستند\n")
except ImportError as e:
    print(f"  ❌ پکیج مفقود: {e}")
    print("  اجرا کن: pip install requests pandas openpyxl")
    sys.exit(1)

# --- گام ۲: دریافت داده‌ها ---
print("📡 گام ۱: دریافت داده‌ها از World Bank API...")
from step3_scraper import scrape_all_indicators, to_dataframe
all_data = scrape_all_indicators()
df = to_dataframe(all_data)
df.to_csv("pakistan_prosperity_raw.csv", encoding="utf-8-sig")
print(f"\n  ✅ {len(df)} شاخص دریافت و ذخیره شد\n")

# --- گام ۳: تحلیل ---
print("📊 گام ۲: تحلیل داده‌ها...")
from step4_analysis import load_data, compare_decades
df = load_data("pakistan_prosperity_raw.csv")

categories = df.index.get_level_values(0).unique().tolist()
print(f"  ✅ {len(categories)} دسته تحلیل شد\n")

# --- گام ۴: خروجی ---
print("💾 گام ۳: تولید خروجی‌ها...")
from step5_output import export_excel, generate_text_report, export_category_csvs
export_excel(df)
generate_text_report(df)
export_category_csvs(df)

print("""
╔══════════════════════════════════════════════════════╗
║   ✅ همه مراحل با موفقیت انجام شد!                 ║
║                                                      ║
║   فایل‌های خروجی:                                   ║
║   📊 pakistan_prosperity.xlsx                        ║
║   📝 pakistan_report.txt                             ║
║   📂 PAK_*.csv (یک فایل برای هر دسته)              ║
╚══════════════════════════════════════════════════════╝
""")
