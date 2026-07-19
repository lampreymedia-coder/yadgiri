# خزش کامل داشبورد اقتصاد پاکستان

**سایت:** https://economy.finance.gov.pk/  
**منبع داده:** API عمومی `https://pub-economy.finance.gov.pk/v1`  
**پوشش:** Overview + ۱۸ فصل Pakistan Economic Survey Dashboard

## آمار

| مورد | مقدار |
|------|------:|
| فصول با CSV | ۱۷ از ۱۸ |
| ردیف شاخص (CSV) | ۱٬۶۱۶ |
| نود درخت UI | ۱٬۶۱۶ |
| نمودار پیش‌فرض | ۵۷ |
| نقاط سری زمانی (long) | ۵۷٬۸۸۱ |
| Climate Change (فصل ۱۸) | فقط placeholder در UI — CSV فعلاً 404 |

## از کجا شروع کنید؟

| اولویت | فایل | توضیح |
|--------|------|--------|
| ۱ | `FULL_CRAWL_REPORT_FA.md` | گزارش کامل فارسی، دسته‌بندی‌شده بر اساس فصل |
| ۲ | `Pakistan_Economy_Dashboard_FULL.xlsx` | اکسل چندبرگی (کاتالوگ + آخرین مقادیر + هر فصل + نمودارها) |
| ۳ | `all_indicators_latest.csv` | آخرین مقدار همه شاخص‌ها |
| ۴ | `all_indicators_long.csv` | کل سری زمانی به‌صورت long format |
| ۵ | `chapters/` | CSV خام جداگانه هر فصل |
| ۶ | `default_charts/` | JSON نمودارهای پیش‌فرض هر فصل |
| ۷ | `catalog.json` | فهرست فصول + آمار |
| ۸ | `dashboard_indicators_tree.json` | درخت کامل شاخص‌های UI |

## فصول

| # | فصل | CSV | نمودار |
|--:|------|----:|-------:|
| 0 | Overview | — | 4 |
| 1 | Economic and Social Indicators | 117 | 4 |
| 2 | Growth and Investment | 286 | 4 |
| 3 | Agriculture | 158 | 4 |
| 4 | Manufacturing and Mining | 79 | 2 |
| 5 | Fiscal Development | 32 | 2 |
| 6 | Money and Credit | 236 | 3 |
| 7 | Capital Markets and Corporate Sector | 33 | 2 |
| 8 | Inflation | 143 | 3 |
| 9 | Trade and Payments | 185 | 3 |
| 10 | Public Debt | 3 | 3 |
| 11 | Education | 44 | 2 |
| 12 | Health and Nutrition | 59 | 4 |
| 13 | Population, Labor Force and Employment | 65 | 3 |
| 14 | Transport and Communications | 117 | 4 |
| 15 | Energy | 53 | 2 |
| 16 | Information Technology and Telecommunication | 4 | 4 |
| 17 | Social Protection | 2 | 2 |
| 18 | Climate Change | 0 | 2 (placeholder) |

## API

```
GET  /v1/card
GET  /v1/defaultchart/{chapterNum}
GET  /v1/chapter/file/?id={chapterNum}
POST /v1/chapter/getGraphData
```
