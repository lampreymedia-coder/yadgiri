"""
======================================================
 اجرای کامل همه گام‌ها یکجا
======================================================

فقط اجرا کن:
  python3 run_all.py
"""

import sys


print("""
╔════════════════════════════════════════════════════════════════╗
║   اسکرپر داده‌های Prosperity پاکستان                         ║
║   منبع: World Bank Data360 API                                ║
║   بازه خروجی: 2010 تا 2026                                    ║
╚════════════════════════════════════════════════════════════════╝
""")

print("🔍 بررسی پکیج‌های مورد نیاز...")
try:
    import openpyxl  # noqa: F401
    import pandas  # noqa: F401
    import requests  # noqa: F401

    print("  ✅ همه پکیج‌ها نصب هستند\n")
except ImportError as exc:
    print(f"  ❌ پکیج مفقود: {exc}")
    print("  اجرا کن: python3 -m pip install -r requirements.txt")
    sys.exit(1)


print("📡 گام ۱: دریافت داده‌ها از Data360...")
from step3_scraper import save_raw_data, scrape_all_indicators

df = scrape_all_indicators()
save_raw_data(df)
print(f"\n  ✅ {len(df)} شاخص دریافت و ذخیره شد\n")


print("📊 گام ۲: تحلیل داده‌ها...")
from step4_analysis import build_summary, build_yearly_changes

yearly = build_yearly_changes(df)
summary = build_summary(df)
print(f"  ✅ {len(yearly)} ردیف تغییرات سالانه ساخته شد")
print(f"  ✅ {len(summary)} ردیف خلاصه ساخته شد\n")


print("💾 گام ۳: تولید خروجی‌ها...")
from step5_output import export_csvs, export_excel, generate_text_report

export_excel(df, yearly, summary)
export_csvs(df, yearly, summary)
generate_text_report(df, yearly, summary)


print("""
╔════════════════════════════════════════════════════════════════╗
║   ✅ همه مراحل با موفقیت انجام شد!                           ║
║                                                                ║
║   فایل‌های خروجی داخل پوشه outputs ساخته شدند:                ║
║   - pakistan_prosperity.xlsx                                   ║
║   - pakistan_prosperity_raw.csv                                ║
║   - pakistan_prosperity_summary.csv                            ║
║   - pakistan_prosperity_yearly_changes.csv                     ║
║   - pakistan_report.txt                                        ║
║   - PAK_*.csv                                                  ║
╚════════════════════════════════════════════════════════════════╝
""")
