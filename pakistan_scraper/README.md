# اسکرپر داده‌های Prosperity پاکستان از World Bank Data360

این پروژه داده‌های مربوط به پاکستان را از صفحه زیر به شکل قابل تحلیل استخراج می‌کند:

<https://data360.worldbank.org/en/economy/PAK?tab=Prosperity>

روش کار به جای parse کردن HTML، استفاده از endpointهای JSON خود Data360 است. این روش برای آموزش web scraping بهتر است چون یاد می‌گیریم اول منبع داده پشت صفحه را پیدا کنیم و بعد داده ساخت‌یافته را تمیز دریافت کنیم.

## نصب

```bash
cd pakistan_scraper
python3 -m pip install -r requirements.txt
```

## اجرای سریع

```bash
cd pakistan_scraper
python3 run_all.py
```

## اجرای گام‌به‌گام

```bash
cd pakistan_scraper

python3 step1_setup.py       # تست اتصال به Data360 API
python3 step2_indicators.py  # دیدن فهرست شاخص‌ها و کد Data360
python3 step3_scraper.py     # دریافت داده خام 2010 تا 2026
python3 step4_analysis.py    # تحلیل تغییرات سالانه و دوره‌ای
python3 step5_output.py      # ساخت Excel، CSV و گزارش فارسی
```

## خروجی‌ها

همه خروجی‌ها در پوشه `outputs/` ساخته می‌شوند:

| فایل | توضیح |
|------|-------|
| `pakistan_prosperity_raw.csv` | جدول عریض؛ هر شاخص یک ردیف و سال‌های 2010 تا 2026 ستون هستند |
| `pakistan_prosperity_yearly_changes.csv` | جدول long؛ هر ردیف یک شاخص در یک سال با تغییر نسبت به مقدار قبلی |
| `pakistan_prosperity_summary.csv` | خلاصه هر شاخص: اولین/آخرین مقدار، تغییر کل، بیشینه/کمینه، میانگین دوره‌ها |
| `pakistan_prosperity.xlsx` | فایل Excel با sheetهای raw، summary، yearly_changes، metadata و sheet جدا برای هر دسته |
| `pakistan_report.txt` | گزارش فارسی بخش‌بندی‌شده و خوانا |
| `PAK_*.csv` | CSV جداگانه برای هر دسته شاخص |

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

## نکته درباره سال‌های 2025 و 2026

خروجی همیشه ستون‌های 2010 تا 2026 را دارد، چون بازه درخواستی همین است. اگر Data360 هنوز برای 2025 یا 2026 مقدار منتشر نکرده باشد، مقدار آن سال‌ها خالی می‌ماند و در گزارش با «ندارد» نمایش داده می‌شود.

## endpointهای اصلی

- داده سری زمانی:
  `https://data360api.worldbank.org/data360/portal/v1/data`
- metadata شاخص‌ها:
  `https://data360api.worldbank.org/data360/portal/v1/adminmetadata`
- hierarchy موضوع‌ها:
  `https://data360api.worldbank.org/data360/portal/v1/hierarchy?type=site&id=HCL_TOPICS_D360`

## تبدیل کد World Bank به Data360

مثال:

| World Bank | Data360 |
|------------|---------|
| `NY.GDP.PCAP.CD` | `WB_WDI_NY_GDP_PCAP_CD` |

یعنی نقطه‌ها (`.`) به زیرخط (`_`) تبدیل می‌شوند و پیشوند `WB_WDI_` اضافه می‌شود.
