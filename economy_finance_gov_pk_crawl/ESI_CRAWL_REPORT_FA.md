# خزش صفحه Economic and Social Indicators

**منبع:** https://economy.finance.gov.pk/economic-and-social-indicators
**سایت والد:** Pakistan Economy Dashboard — وزارت دارایی پاکستان (Finance Division)
**شماره فصل در داشبورد:** 1
**بازه زمانی CSV کامل:** 1980-81 تا 2025-26 (۴۶ سال مالی)
**تعداد شاخص‌ها در این فصل:** 117

## ۱) ساختار سایت و ناوبری

این صفحه فصل اول داشبورد تعاملی Pakistan Economic Survey است (۱۸ فصل + Overview):
- `0` Overview — https://economy.finance.gov.pk/
- `1` Economic and Social Indicators — https://economy.finance.gov.pk/economic-and-social-indicators ← **صفحه فعلی**
- `2` Growth and Investment — https://economy.finance.gov.pk/growth-and-investment
- `3` Agriculture — https://economy.finance.gov.pk/agriculture
- `4` Manufacturing and Mining — https://economy.finance.gov.pk/manufacturing-and-mining
- `5` Fiscal Development — https://economy.finance.gov.pk/fiscal-development
- `6` Money and Credit — https://economy.finance.gov.pk/money-and-credit
- `7` Capital Markets and Corporate Sector — https://economy.finance.gov.pk/capital-markets-and-corporate-sector
- `8` Inflation — https://economy.finance.gov.pk/inflation
- `9` Trade and Payments — https://economy.finance.gov.pk/trade-and-payments
- `10` Public Debt — https://economy.finance.gov.pk/public-debt
- `11` Education — https://economy.finance.gov.pk/education
- `12` Health and Nutrition — https://economy.finance.gov.pk/health-and-nutrition
- `13` Population, Labor Force and Employment — https://economy.finance.gov.pk/population-labor-force-and-employment
- `14` Transport and Communications — https://economy.finance.gov.pk/transport-and-communications
- `15` Energy — https://economy.finance.gov.pk/energy
- `16` Information Technology and Telecommunication — https://economy.finance.gov.pk/information-technology-and-telecommunication
- `17` Social Protection — https://economy.finance.gov.pk/social-protection
- `18` Climate Change — https://economy.finance.gov.pk/climate-change

## ۲) امکانات UI همین صفحه

- Download Complete Chapter Data (دانلود CSV کامل فصل)
- Select Indicators from Current Chapter
- Select Indicators (انتخاب بین‌فصلی)
- Select Fiscal Years
- Create Charts / Clear All
- انواع نمودار: line, area, bar, combo, pie, table
- دانلود هر نمودار: SVG / PNG / CSV

## ۳) APIهای پشت صفحه

| کاربرد | Endpoint |
|---|---|
| نمودارهای پیش‌فرض فصل ۱ | `GET https://pub-economy.finance.gov.pk/v1/defaultchart/1` |
| دانلود داده کامل فصل (CSV) | `GET https://pub-economy.finance.gov.pk/v1/chapter/file/?id=1` |
| ساخت نمودار سفارشی | `POST https://pub-economy.finance.gov.pk/v1/chapter/getGraphData` |
| کارت‌های Overview | `GET https://pub-economy.finance.gov.pk/v1/card` |

## ۴) نمودارهای پیش‌فرض صفحه

بازه نمایش پیش‌فرض: **2013-14 تا 2025-26**

### GDP (US $ billion)
- **GDP (US $ billion)**
  - 2019-20: 300.8 | 2020-21: 348.9 | 2021-22: 375.5 | 2022-23: 337.2 | 2023-24: 372.1 | 2024-25: 408.2
- **Per Capita Income (US $)**
  - 2020-21: 1677.3 | 2021-22: 1767 | 2022-23: 1547 | 2023-24: 1607 | 2024-25: 1751 | 2025-26: 1901

### Transport & Communication
- **Roads (000 km)**
  - 2019-20: 501.4 | 2020-21: 500.7 | 2021-22: 501.2 | 2022-23: 501.2 | 2023-24: 501.2 | 2024-25: 501.2
- **Motor Vehicles on Roads (mln. nos.)**
  - 2019-20: 30 | 2020-21: 32.1 | 2021-22: 34.3 | 2022-23: 35.9 | 2023-24: 37.4 | 2024-25: 37.4

### Labor Force & Employment
- **Labour Force (million)**
  - 2013-14: 60.1 | 2014-15: 61 | 2017-18: 65.5 | 2018-19: 68.8 | 2020-21: 71.8 | 2024-25: 83.1
- **Employed Labour Force (million)**
  - 2013-14: 56.5 | 2014-15: 57.4 | 2017-18: 61.7 | 2018-19: 64 | 2020-21: 67.3 | 2024-25: 77.2

### Expenditures on Education and Health
- **Expenditure on Education (as % of GDP)**
  - 2019-20: 1.9 | 2020-21: 1.4 | 2021-22: 1.7 | 2022-23: 1.5 | 2023-24: 1.2 | 2024-25: 0.8
- **Expenditure on Health (as % of GDP)**
  - 2019-20: 1.1 | 2020-21: 1 | 2021-22: 1.4 | 2022-23: 1 | 2023-24: 0.9 | 2024-25: 0.8

## ۵) دسته‌بندی کامل شاخص‌ها + آخرین مقدار

منبع: CSV کامل فصل (`/chapter/file/?id=1`). ستون خالی یعنی داده برای آن سال نیست.

### A. تولید ناخالص داخلی (سطح)

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| GDP (Rs billion) | 114039 | 2024-25 | 2007-08 | 18 |
| GDP (US $ billion) | 408.2 | 2024-25 | 2007-08 | 18 |

### B. رشد اقتصادی

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| GDP Growth Rate (%) | 3.1 | 2024-25 | 1980-81 | 45 |
| ↳ Agriculture Growth Rate (%) | 1.5 | 2024-25 | 1980-81 | 45 |
| ↳ Manufacturing Growth Rate (%) | 2 | 2024-25 | 1980-81 | 45 |
| ↳ Commodity Producing Sector Growth Rate (%) | 3.1 | 2024-25 | 1980-81 | 45 |
| ↳ Services Sector Growth Rate (%) | 3.1 | 2024-25 | 1980-81 | 45 |

### C. سرمایه‌گذاری، پس‌انداز و درآمد سرانه

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Total Investment Growth Rates (at current mp) % | 18.3 | 2024-25 | 1980-81 | 45 |
| ↳ Fixed Investment Growth Rates (%, at current mp) | 19.8 | 2024-25 | 1980-81 | 45 |
| ↳ Public Investment Growth Rates (%, at current mp) | 44.3 | 2024-25 | 1980-81 | 45 |
| ↳ Private Investment Growth Rates (including general govt., %, at current mp) | 13.2 | 2024-25 | 1980-81 | 45 |
| ↳ National Savings (as % of Total Investment) | 103.3 | 2024-25 | 1980-81 | 45 |
| ↳ Foreign Savings (as % of Total Investment) | -3.1 | 2024-25 | 1980-81 | 45 |
| ↳ Total Investment (as % of GDP current mp) | 14.3 | 2024-25 | 1980-81 | 45 |
| ↳ Total Investment, Fixed (as % of GDP current mp) | 12.7 | 2024-25 | 1980-81 | 45 |
| ↳ Total Investment, Public (as % of GDP current mp) | 3.3 | 2024-25 | 1980-81 | 45 |
| ↳ Total Investment, Private (as % of GDP current mp) | 9.5 | 2024-25 | 1980-81 | 45 |
| ↳ National Savings (as % of GDP current mp) | 14.9 | 2024-25 | 1980-81 | 45 |
| ↳ Foreign Savings (as % of GDP current mp) | -0.5 | 2024-25 | 1980-81 | 45 |
| ↳ Domestic Savings (as % of GDP current mp) | 7.9 | 2024-25 | 1980-81 | 36 |
| ↳ Per Capita Income (mp-US $) | 1751 | 2024-25 | 2005-06 | 20 |

### D. تورم و قیمت‌ها

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| GDP Deflator (growth %) | 4.2 | 2024-25 | 1980-81 | 36 |
| Consumer Price Index (CPI) (growth %) | 4.5 | 2024-25 | 1980-81 | 45 |

### E. مالیه عمومی

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Total Revenue (as % of GDP mp) | 15.8 | 2024-25 | 1980-81 | 45 |
| ↳ Tax Revenue (as % of GDP mp) | 11.2 | 2024-25 | 1980-81 | 45 |
| ↳ Non-Tax Revenue (as % of GDP mp) | 4.6 | 2024-25 | 1980-81 | 45 |
| Total Expenditure (as % of GDP mp) | 21.2 | 2024-25 | 1980-81 | 45 |
| ↳ Current Expenditure (as % of GDP mp) | 18.9 | 2024-25 | 1980-81 | 45 |
| ↳ Current Expenditure, Defence (as % of GDP mp) | 1.9 | 2024-25 | 1980-81 | 45 |
| ↳ Current Expenditure, Markup Payments (as % of GDP mp) | 7.8 | 2024-25 | 1980-81 | 45 |
| ↳ Current Expenditure, Others (as % of GDP mp) | 9.2 | 2024-25 | 1980-81 | 45 |
| Development Expenditure (as % of GDP current mp) | 2.6 | 2024-25 | 1980-81 | 45 |
| Overall Deficit (as % of GDP current mp) | 5.4 | 2024-25 | 1980-81 | 45 |

### F. پول و اعتبار

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Money and Credit (growth %) | — | — | — | 0 |
| ↳ Monetary Assets (M2) (growth %) | 12.9 | 2024-25 | 1980-81 | 45 |
| ↳ Domestic Assets (growth %) | 8.2 | 2024-25 | 1980-81 | 45 |

### G. بازار سرمایه

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Stock Exchange (growth %) | — | — | — | 0 |
| ↳ KSE 100 Index (growth %) | 60.1 | 2024-25 | 1980-81 | 45 |
| ↳ Aggregate Market Capitalization (growth %) | 46.9 | 2024-25 | 1980-81 | 45 |

### H. تجارت و تراز پرداخت‌ها

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Trade and Payments (growth %) | — | — | — | 0 |
| ↳ Exports (fob) (growth %) | 4.4 | 2024-25 | 1980-81 | 45 |
| ↳ Imports (fob) (growth %) | 11.2 | 2024-25 | 1980-81 | 45 |
| ↳ Workers' Remittances (growth %) | 26.6 | 2024-25 | 1980-81 | 45 |
| ↳ Exports (fob) As % of GDP (mp) | 7.9 | 2024-25 | 1980-81 | 45 |
| ↳ Imports (fob) As % of GDP (mp) | 14.5 | 2024-25 | 1980-81 | 45 |
| ↳ Trade Deficit As % of GDP (mp) | 6.6 | 2024-25 | 1980-81 | 45 |
| ↳ Current Account Deficit As % of GDP (mp) | 0.5 | 2024-25 | 1980-81 | 45 |

### I. کشاورزی

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Agriculture | — | — | — | 0 |
| ↳ Total Cropped Area (mln. Hectares) | 24.6 | 2024-25 | 1980-81 | 45 |
| ↳ Production | — | — | — | 0 |
| ↳ Production, Wheat (mln. tons) | 28.4 | 2024-25 | 1980-81 | 45 |
| ↳ Production, Rice (mln. tons) | 9.7 | 2024-25 | 1980-81 | 45 |
| ↳ Production, Sugarcane (mln. tons) | 84.2 | 2024-25 | 1980-81 | 45 |
| ↳ Production, Cotton (mln. bales) | 7.1 | 2024-25 | 1980-81 | 45 |
| ↳ Fertilizer Offtake (mln.N/tons) | 4.4 | 2024-25 | 1980-81 | 45 |
| ↳ Credit Disbursed (bln. Rs.) | 2577.3 | 2024-25 | 1980-81 | 45 |

### J. صنعت و تولید

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Manufacturing | — | — | — | 0 |
| ↳ Cotton Yarn (mln. Kg.) | 2665.3 | 2024-25 | 1980-81 | 45 |
| ↳ Cotton Cloth (mln. sq. mtr.) | 877.3 | 2024-25 | 1980-81 | 45 |
| ↳ Fertilizer Offtake (mln. tons) | 9.4 | 2024-25 | 1980-81 | 45 |
| ↳ Sugar (mln. tons) | 5.8 | 2024-25 | 1980-81 | 45 |
| ↳ Cement (mln. tons) | 37.8 | 2024-25 | 1980-81 | 45 |
| ↳ Soda Ash (000 tons) | 699.5 | 2024-25 | 1980-81 | 45 |
| ↳ Caustic Soda (000 tons) | 452.5 | 2024-25 | 1980-81 | 45 |
| ↳ Cigarettes (bln. nos.) | 35.2 | 2024-25 | 1980-81 | 45 |
| ↳ Jute Goods (000 tons) | 29.5 | 2024-25 | 1980-81 | 45 |

### K. انرژی

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Energy | — | — | — | 0 |
| ↳ Crude Oil Extraction (mln. Barrels) | 22.8 | 2024-25 | 1980-81 | 45 |
| ↳ Gas (production) (mcf) | 1054.8 | 2024-25 | 1980-81 | 45 |
| ↳ Electricity (installed capacity) (000 MW) | 44.5 | 2024-25 | 1980-81 | 45 |

### L. حمل‌ونقل و ارتباطات

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Transport & Communications | — | — | — | 0 |
| ↳ Roads (000 km) | 501.2 | 2024-25 | 1980-81 | 45 |
| ↳ Motor Vehicles on Roads (mln. nos.) | 37.4 | 2024-25 | 1980-81 | 45 |
| ↳ Post Offices (000 nos.) | 7 | 2024-25 | 1980-81 | 45 |
| ↳ TV Sets (000 nos.) | 25330 | 2023-24 | 2006-07 | 18 |

### M. فناوری اطلاعات و مخابرات

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Information Technology and Telecom | — | — | — | 0 |
| ↳ Telephones (mln. nos.) | 2.5 | 2024-25 | 1980-81 | 45 |
| ↳ Mobile Phones (mln. nos.) | 197.8 | 2024-25 | 2000-01 | 25 |
| ↳ Telecom Revenues (Rs. bln.) | 1075 | 2024-25 | 2018-19 | 7 |
| ↳ Teledensity (percent) | 81.1 | 2024-25 | 2018-19 | 7 |
| ↳ Broadband Subscribers (mln. nos.) | 150 | 2024-25 | 2018-19 | 7 |

### N. جمعیت و جمعیت‌شناسی

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Population (million) | 252.09 | 2024-25 | 1980-81 | 45 |
| Crude Birth Rate (per 1000 person) | 25.71 | 2024-25 | 1984-85 | 35 |
| Crude Death Rate (per 1000 person) | 5.69 | 2024-25 | 1984-85 | 35 |
| Infant Mortality Rate (per 1000 person) | 47 | 2024-25 | 1984-85 | 34 |

### O. نیروی کار و اشتغال

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Labour Force & Employment | — | — | — | 0 |
| ↳ Labour Force (million) | 83.1 | 2024-25 | 1980-81 | 39 |
| ↳ Employed Labour Force (million) | 77.2 | 2024-25 | 1980-81 | 39 |
| ↳ Un-employed Labour Force (million) | 5.9 | 2024-25 | 1980-81 | 39 |
| ↳ Un-employment Rate (% per annum) | 7.1 | 2024-25 | 1980-81 | 39 |

### P. آموزش

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Education | — | — | — | 0 |
| ↳ Primary Schools (000 nos.) | 154.9 | 2024-25 | 1980-81 | 45 |
| ↳ Primary Schools (000 nos.) Male | 88.2 | 2024-25 | 1980-81 | 45 |
| ↳ Primary Schools (000 nos.) Female | 66.7 | 2024-25 | 1980-81 | 45 |
| ↳ Middle Schools (000 nos.) | 43.9 | 2024-25 | 1980-81 | 45 |
| ↳ Middle Schools (000 nos.) Male | 22 | 2024-25 | 1980-81 | 45 |
| ↳ Middle Schools (000 nos.) Female | 21.9 | 2024-25 | 1980-81 | 45 |
| ↳ High Schools (000 nos.) | 48.7 | 2024-25 | 1980-81 | 45 |
| ↳ High Schools (000 nos.) Male | 23.6 | 2024-25 | 1980-81 | 45 |
| ↳ High Schools (000 nos.) Female | 25.1 | 2024-25 | 1980-81 | 45 |
| ↳ Technical / Vocational Institutions (nos.) | 4746 | 2024-25 | 1980-81 | 45 |
| ↳ Technical / Vocational Institutions (nos.) Male | 2804 | 2024-25 | 1980-81 | 45 |
| ↳ Technical / Vocational Institutions (nos.) Female | 1942 | 2024-25 | 1980-81 | 45 |
| ↳ Literacy Rate (percent) | 63 | 2024-25 | 1980-81 | 31 |
| ↳ Literacy Rate (percent) Male | 73 | 2024-25 | 1980-81 | 27 |
| ↳ Literacy Rate (percent) Female | 54 | 2024-25 | 1980-81 | 27 |
| ↳ Expenditure on Education (as % of GDP) | 0.8 | 2024-25 | 1980-81 | 45 |

### Q. سلامت

| شاخص | آخرین مقدار | سال | از سال | نقاط داده |
|---|---:|---|---|---:|
| Health | — | — | — | 0 |
| ↳ Registered Doctors (000 nos.) | 336.6 | 2024-25 | 1980-81 | 45 |
| ↳ Registered Nurses (000 nos.) | 138.4 | 2024-25 | 1980-81 | 45 |
| ↳ Registered Dentists (000 nos.) | 42.1 | 2024-25 | 1980-81 | 45 |
| ↳ Hospitals (nos.) | 1934 | 2024-25 | 1980-81 | 45 |
| ↳ Dispensaries (000 nos.) | 6.2 | 2024-25 | 1980-81 | 45 |
| ↳ Rural Health Centers (nos.) | 802 | 2024-25 | 1980-81 | 45 |
| ↳ TB Centres (nos.) | 486 | 2024-25 | 1980-81 | 45 |
| ↳ Total Beds (000 nos.) | 174 | 2024-25 | 1980-81 | 45 |
| ↳ Expenditure on Health (as % of GDP) | 0.8 | 2024-25 | 1980-81 | 45 |

## ۶) درخت شاخص‌های قابل انتخاب در UI (کدها)

تعداد نود: **117**

  - `1.1` GDP (Rs billion)
  - `1.2` GDP (US $ billion)
  - `1.3` GDP Growth Rate (%)
    - `1.3.1` Agriculture Growth Rate (%)
    - `1.3.2` Manufacturing Growth Rate (%)
    - `1.3.3` Commodity Producing Sector Growth Rate (%)
    - `1.3.4` Services Sector Growth Rate (%)
  - `1.4` Total Investment Growth Rates (at current mp) %
    - `1.4.1` Fixed Investment Growth Rates (%, at current mp)
    - `1.4.2` Public Investment Growth Rates (%, at current mp)
    - `1.4.3` Private Investment Growth Rates (including general govt., %, at current mp)
    - `1.4.4` National Savings (as % of Total Investment)
    - `1.4.5` Foreign Savings (as % of Total Investment)
    - `1.4.6` Total Investment (as % of GDP current mp)
    - `1.4.7` Total Investment, Fixed (as % of GDP current mp)
    - `1.4.8` Total Investment, Public (as % of GDP current mp)
    - `1.4.9` Total Investment, Private (as % of GDP current mp)
    - `1.4.10` National Savings (as % of GDP current mp)
    - `1.4.11` Foreign Savings (as % of GDP current mp)
    - `1.4.12` Domestic Savings (as % of GDP current mp)
    - `1.4.13` Per Capita Income (mp-US $)
  - `1.5` GDP Deflator (growth %)
  - `1.6` Consumer Price Index (CPI) (growth %)
  - `1.7` Total Revenue (as % of GDP mp)
    - `1.7.1` Tax Revenue (as % of GDP mp)
    - `1.7.2` Non-Tax Revenue (as % of GDP mp)
  - `1.8` Total Expenditure (as % of GDP mp)
    - `1.8.1` Current Expenditure (as % of GDP mp)
    - `1.8.2` Current Expenditure, Defence (as % of GDP mp)
    - `1.8.3` Current Expenditure, Markup Payments (as % of GDP mp)
    - `1.8.4` Current Expenditure, Others (as % of GDP mp)
  - `1.9` Development Expenditure (as % of GDP current mp)
  - `1.10` Overall Deficit (as % of GDP current mp)
  - `1.11` Money and Credit (growth %)
    - `1.11.1` Monetary Assets (M2) (growth %)
    - `1.11.2` Domestic Assets (growth %)
  - `1.12` Stock Exchange (growth %)
    - `1.12.1` KSE 100 Index (growth %)
    - `1.12.2` Aggregate Market Capitalization (growth %)
  - `1.13` Trade and Payments (growth %)
    - `1.13.1` Exports (fob) (growth %)
    - `1.13.2` Imports (fob) (growth %)
    - `1.13.3` Workers' Remittances (growth %)
    - `1.13.4` Exports (fob) As % of GDP (mp)
    - `1.13.5` Imports (fob) As % of GDP (mp)
    - `1.13.6` Trade Deficit As % of GDP (mp)
    - `1.13.7` Current Account Deficit As % of GDP (mp)
  - `1.14` Agriculture
    - `1.14.1` Total Cropped Area (mln. Hectares)
    - `1.14.2` Production
    - `1.14.3` Production, Wheat (mln. tons)
    - `1.14.4` Production, Rice (mln. tons)
    - `1.14.5` Production, Sugarcane (mln. tons)
    - `1.14.6` Production, Cotton (mln. bales)
    - `1.14.7` Fertilizer Offtake (mln.N/tons)
    - `1.14.8` Credit Disbursed (bln. Rs.)
  - `1.15` Manufacturing
    - `1.15.1` Cotton Yarn (mln. Kg.)
    - `1.15.2` Cotton Cloth (mln. sq. mtr.)
    - `1.15.3` Fertilizer Offtake (mln. tons)
    - `1.15.4` Sugar (mln. tons)
    - `1.15.5` Cement (mln. tons)
    - `1.15.6` Soda Ash (000 tons)
    - `1.15.7` Caustic Soda (000 tons)
    - `1.15.8` Cigarettes (bln. nos.)
    - `1.15.9` Jute Goods (000 tons)
  - `1.16` Energy
    - `1.16.1` Crude Oil Extraction (mln. Barrels)
    - `1.16.2` Gas (production) (mcf)
    - `1.16.3` Electricity (installed capacity) (000 MW)
  - `1.17` Transport & Communications
    - `1.17.1` Roads (000 km)
    - `1.17.2` Motor Vehicles on Roads (mln. nos.)
    - `1.17.3` Post Offices (000 nos.)
    - `1.17.4` TV Sets (000 nos.)
  - `1.18` Information Technology and Telecom
    - `1.18.1` Telephones (mln. nos.)
    - `1.18.2` Mobile Phones (mln. nos.)
    - `1.18.3` Telecom Revenues (Rs. bln.)
    - `1.18.4` Teledensity (percent)
    - `1.18.5` Broadband Subscribers (mln. nos.)
  - `1.19` Population (million)
  - `1.20` Crude Birth Rate (per 1000 person)
  - `1.21` Crude Death Rate (per 1000 person)
  - `1.22` Infant Mortality Rate (per 1000 person)
  - `1.23` Labour Force & Employment
    - `1.23.1` Labour Force (million)
    - `1.23.2` Employed Labour Force (million)
    - `1.23.3` Un-employed Labour Force (million)
    - `1.23.4` Un-employment Rate (% per annum)
  - `1.24` Education
    - `1.24.1` Primary Schools (000 nos.)
    - `1.24.2` Primary Schools (000 nos.) Male
    - `1.24.3` Primary Schools (000 nos.) Female
    - `1.24.4` Middle Schools (000 nos.)
    - `1.24.5` Middle Schools (000 nos.) Male
    - `1.24.6` Middle Schools (000 nos.) Female
    - `1.24.7` High Schools (000 nos.)
    - `1.24.8` High Schools (000 nos.) Male
    - `1.24.9` High Schools (000 nos.) Female
    - `1.24.10` Technical / Vocational Institutions (nos.)
    - `1.24.11` Technical / Vocational Institutions (nos.) Male
    - `1.24.12` Technical / Vocational Institutions (nos.) Female
    - `1.24.13` Literacy Rate (percent)
    - `1.24.14` Literacy Rate (percent) Male
    - `1.24.15` Literacy Rate (percent) Female
    - `1.24.16` Expenditure on Education (as % of GDP)
  - `1.25` Health
    - `1.25.1` Registered Doctors (000 nos.)
    - `1.25.2` Registered Nurses (000 nos.)
    - `1.25.3` Registered Dentists (000 nos.)
    - `1.25.4` Hospitals (nos.)
    - `1.25.5` Dispensaries (000 nos.)
    - `1.25.6` Rural Health Centers (nos.)
    - `1.25.7` TB Centres (nos.)
    - `1.25.8` Total Beds (000 nos.)
    - `1.25.9` Expenditure on Health (as % of GDP)

## ۷) نکات فنی خزش

- سایت پشت Cloudflare است؛ محتوا از API عمومی `pub-economy.finance.gov.pk` و باندل فرانت استخراج شد.
- CSV فصل ستون‌های `Sectors / Sub-Sectors-Level1 / Sub-Sectors-Level2` و سال‌های مالی دارد.
- در نمودار پیش‌فرض، `null` یعنی داده آن سال موجود نیست (مثلاً GDP دلاری برای 2025-26).
- فصل Climate Change در منو هست ولی فایل CSV آن فعلاً 404 است.

## فایل‌های استخراج‌شده

- `ESI_CRAWL_REPORT_FA.md` — همین گزارش
- `economic_and_social_indicators_full.csv` — کل سری زمانی فصل ۱
- `esi_indicators_flat.json` — درخت تخت شاخص‌های فصل ۱
- `dashboard_indicators_tree.json` — درخت کامل همه فصول داشبورد