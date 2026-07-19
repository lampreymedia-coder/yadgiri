# خزش‌گر داده‌های Pakistan Bureau of Statistics (PBS)

منبع: [https://www.pbs.gov.pk/](https://www.pbs.gov.pk/)

این اسکریپت محتوای عمومی سایت PBS را از طریق WordPress REST API، sitemap و لینک‌های HTML جمع‌آوری می‌کند و خروجی یکجا می‌دهد.

## نصب

```bash
pip install -r requirements.txt
```

## اجرا

```bash
python crawl_pbs.py
```

## خروجی‌ها (`output/`)

| فایل | توضیح |
|------|--------|
| `all_content.json` / `.csv` | صفحات، پست‌ها، محصولات، docs و آگهی‌ها با متن کامل |
| `all_content_full.json` | همان محتوا به‌همراه HTML خام |
| `media_documents.json` / `.csv` | کاتالوگ رسانه‌های سندی (PDF/Excel/ZIP/…) با URL عمومی |
| `discovered_files.json` / `.csv` | فایل‌های قابل‌دانلود کشف‌شده از HTML صفحات |
| `sitemap_urls.csv` | همه URLهای sitemap |
| `taxonomies.json` | دسته‌ها و برچسب‌ها |
| `pbs_crawl.xlsx` | ورک‌بوک اکسل خلاصه |
| `report.txt` | گزارش متنی دو زبانه |
| `crawl_meta.json` | آمار اجرا |

## آمار آخرین خزش (۱۹ ژوئیه ۲۰۲۶)

| بخش | تعداد |
|-----|------:|
| صفحات / پست‌ها / محصولات / docs | 73 / 58 / 20 / 16 |
| URLهای sitemap | 299 |
| اسناد رسانه (PDF/Excel/ZIP/…) | ۴٬۱۸۸ |
| فایل‌های کشف‌شده از HTML | ۷٬۸۹۱ |

جزئیات در `output/report.txt` و `output/crawl_meta.json`.

## نکته

فایل‌های باینری (هزاران PDF/Excel) فقط **کاتالوگ** می‌شوند (عنوان، نوع، URL، حجم در صورت موجود بودن). دانلود کامل همه باینری‌ها عمداً انجام نمی‌شود تا خروجی قابل‌حمل بماند؛ URLها برای دانلود انتخابی آماده هستند.
