# اسکرپر داده‌های Prosperity پاکستان

داده‌های شاخص‌های رفاه پاکستان از World Bank API (2010-2026)

## نصب

```bash
pip install requests pandas openpyxl
```

## اجرا

```bash
# اجرای همه گام‌ها یکجا
python run_all.py
```

یا گام به گام:

```bash
python step1_setup.py     # تست اتصال به API
python step2_indicators.py # نمایش لیست شاخص‌ها
python step3_scraper.py   # دریافت همه داده‌ها
python step4_analysis.py  # تحلیل و مقایسه
python step5_output.py    # خروجی Excel و گزارش
```

## خروجی‌ها

| فایل | توضیح |
|------|-------|
| `pakistan_prosperity.xlsx` | Excel با Sheet جداگانه برای هر دسته |
| `pakistan_report.txt` | گزارش متنی کامل با روند سالانه |
| `PAK_*.csv` | CSV جداگانه برای هر دسته |

## شاخص‌های پوشش داده شده

| دسته | تعداد شاخص |
|------|-----------|
| رشد اقتصادی | 6 |
| درآمد و فقر | 6 |
| سلامت | 6 |
| آموزش | 5 |
| زیرساخت | 6 |
| بازار کار | 5 |
| تجارت و مالیه | 6 |
| محیط زیست | 3 |
| **مجموع** | **43** |

## منبع

World Bank Open Data API - رایگان، بدون نیاز به API Key
