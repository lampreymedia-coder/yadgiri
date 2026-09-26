# راهنمای استقرار ربات آرشیو بله روی سرور ویندوز

این راهنما برای کسی نوشته شده که برنامه‌نویس نیست.
هر قدم **یک کار** است. دستورها را کپی کنید و در سرور اجرا کنید.
بعد از هر دستور ببینید آیا همان چیزی که نوشته شده را می‌بینید یا نه.

**مسیر پیشنهادی روی سرور:** `C:\bots\yadgiri`  
**شاخهٔ کد:** `cursor/owner-post-insert-7da1`  
**ریپوی گیت‌هاب:** `https://github.com/lampreymedia-coder/yadgiri`

هشدارهای مهم قبل از شروع:

- جداول ربات فقط در دیتابیس `bale_archive` ساخته می‌شوند.
- **هرگز** `DATABASE_URL` را به دیتابیس `ehya` وصل نکنید.
- پورت ۱۴۳۳ را به اینترنت باز نکنید؛ ربات روی همین سرور است.
- توکن ربات را فقط داخل فایل `.env` بگذارید، نه در چت و نه در گیت‌هاب.

---

## قدم ۰ — چیزهایی که باید از قبل روی سرور باشد

بررسی کنید این‌ها نصب‌اند:

1. ویندوز سرور
2. Python 3.12 (با تیک Add to PATH)
3. SQL Server + برنامهٔ SSMS
4. ODBC Driver **17** for SQL Server
5. Git for Windows
6. توکن ربات بله

اگر Git ندارید، از [git-scm.com](https://git-scm.com/download/win) نصب کنید.

---

## قدم ۱ — ساخت پوشهٔ کار

PowerShell را **به‌عنوان Administrator** باز کنید و این را بزنید:

```
New-Item -ItemType Directory -Force -Path C:\bots\yadgiri | Out-Null
cd C:\bots\yadgiri
```

**اگر درست باشد:** مسیر فعلی شما می‌شود `C:\bots\yadgiri` و خطایی نمی‌بینید.

---

## قدم ۲ — آوردن کد از گیت‌هاب (اولین بار)

اگر پوشه هنوز خالی است:

```
cd C:\bots\yadgiri
git clone --branch cursor/owner-post-insert-7da1 --single-branch https://github.com/lampreymedia-coder/yadgiri.git .
```

**اگر درست باشد:** پوشه‌های `bale-archive-bot` و شاید `pakistan_scraper` را می‌بینید.

سپس وارد پوشهٔ ربات شوید:

```
cd C:\bots\yadgiri\bale-archive-bot
```

**اگر درست باشد:** فایل‌هایی مثل `README.md`، `.env.example` و پوشهٔ `scripts` را می‌بینید.

---

## قدم ۳ — ساخت دیتابیس `bale_archive` با COLLATE فارسی

1. برنامهٔ **SSMS** را باز کنید و به همان SQL Server محلی وصل شوید.
2. New Query بزنید و این را اجرا کنید:

```
CREATE DATABASE bale_archive
COLLATE Persian_100_CI_AS;
```

**اگر درست باشد:** پیام شبیه `Commands completed successfully` می‌آید.

اگر خطا داد که این COLLATE را نمی‌شناسد، این را بزنید:

```
CREATE DATABASE bale_archive
COLLATE Arabic_100_CI_AS;
```

**یادآوری:** این دیتابیس جدا از `ehya` است. `ehya` را لمس نکنید.

---

## قدم ۴ — محدود کردن حافظه SQL Server (سرور ۲ گیگ رم)

در همان SSMS این را یک‌بار اجرا کنید:

```
EXEC sys.sp_configure N'show advanced options', 1;
RECONFIGURE;
EXEC sys.sp_configure N'max server memory (MB)', 512;
RECONFIGURE;
```

**اگر درست باشد:** بدون خطا تمام می‌شود.

برای اطمینان:

```
EXEC sys.sp_configure N'max server memory (MB)';
```

در ستون config_value / run_value باید حدود **512** باشد.

---

## قدم ۵ — ساخت فایل تنظیمات `.env`

در PowerShell:

```
cd C:\bots\yadgiri\bale-archive-bot
copy .env.example .env
notepad .env
```

در Notepad حداقل این‌ها را پر کنید:

1. `BALE_BOT_TOKEN=` توکن واقعی ربات
2. `DATABASE_URL=` دقیقاً به این شکل (کاربر و رمز خودتان را بگذارید):

```
DATABASE_URL=mssql+aioodbc://USER:PASSWORD@localhost:1433/bale_archive?driver=ODBC+Driver+17+for+SQL+Server&TrustServerCertificate=yes
```

3. `OWNER_POST_SYNC=false` بماند (فعلاً خاموش)
4. `RUN_MODE=polling` بماند

ذخیره کنید و Notepad را ببندید.

**اگر درست باشد:** فایل `.env` کنار `.env.example` وجود دارد و داخلش توکن و آدرس `bale_archive` هست — نه `ehya`.

اگر رمز SQL نویسه‌های خاص دارد (`@` `:` `/` `#`)، باید URL-encode شود؛ در غیر این صورت از Trusted Connection استفاده کنید (نمونه در `.env.example` هست).

---

## قدم ۶ — اجازهٔ اجرای اسکریپت‌های PowerShell

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

اگر پرسید، `Y` بزنید.

**اگر درست باشد:** پیام تغییر policy می‌آید یا می‌گوید از قبل تنظیم است.

---

## قدم ۷ — نصب برنامه‌ها و ساخت جداول

```
cd C:\bots\yadgiri\bale-archive-bot
.\scripts\install.ps1
```

**اگر درست باشد:** بدون خطای قرمز تمام می‌شود، پوشهٔ `.venv` ساخته می‌شود، و جداول در `bale_archive` ساخته می‌شوند.

اگر گفت Alembic / ODBC خطا داد: Driver 17، نام دیتابیس `bale_archive`، و کاربر/رمز را دوباره چک کنید.

---

## قدم ۸ — تست اتصال به دیتابیس

```
cd C:\bots\yadgiri\bale-archive-bot
.\.venv\Scripts\python.exe scripts\check_db.py
```

**اگر درست باشد:** چیزی شبیه `database_ok` می‌بینید.

اگر خطا بود، قبل از روشن کردن ربات همان را حل کنید.

---

## قدم ۹ — روشن کردن ربات برای اولین بار (پنجره باز)

```
cd C:\bots\yadgiri\bale-archive-bot
.\scripts\run.ps1
```

**اگر درست باشد:** در خروجی عبارتی شبیه `polling_started` می‌بینید و پنجره باز می‌ماند.

سپس در بله به ربات بروید و بفرستید:

```
/start
```

**اگر درست باشد:** ربات جواب فارسی می‌دهد و شما به‌عنوان مدیر شناخته می‌شوید.

برای توقف موقت: در همان پنجره `Ctrl+C` بزنید.

---

## قدم ۱۰ — تبدیل به سرویس ویندوز با NSSM (همیشه روشن)

ربات با بستن پنجره خاموش می‌شود. برای ماندگاری:

1. NSSM را از https://nssm.cc/download بگیرید و `nssm.exe` را جایی مثل `C:\bots\nssm\nssm.exe` بگذارید.
2. PowerShell را Administrator باز کنید:

```
cd C:\bots\yadgiri\bale-archive-bot
.\scripts\install-service.ps1
```

اگر اسکریپت مسیر NSSM را نفهمید، طبق پیام خودش مسیر `nssm.exe` را بدهید.

**اگر درست باشد:** سرویس (معمولاً با نامی شبیه `BaleArchiveBot`) نصب می‌شود و Running است.

بررسی:

```
Get-Service *Bale*
```

یا در `services.msc` سرویس ربات را پیدا کنید — وضعیت باید **Running** باشد.

---

## جدول خطاهای محتمل

| چه می‌بینید | معنی ساده | چه کار کنید |
|---|---|---|
| `ODBC Driver` پیدا نشد | درایور ۱۷ نصب نیست یا اسمش در آدرس اشتباه است | Driver 17 را نصب کنید؛ در `.env` دقیقاً `ODBC+Driver+17+for+SQL+Server` باشد |
| `Login failed` / `Cannot open database` | کاربر/رمز اشتباه یا دیتابیس ساخته نشده | در SSMS دیتابیس `bale_archive` و کاربر را چک کنید؛ به `ehya` وصل نباشید |
| `Alembic failed` | جداول ساخته نشدند | قدم ۷ را بعد از درست شدن اتصال دوباره بزنید |
| `getUpdates conflict` | دو ربات همزمان با یک توکن روشن‌اند | فقط یک `run.ps1` یا یک سرویس NSSM بماند؛ دومی را ببندید |
| ربات جواب نمی‌دهد | سرویس خاموش است یا توکن غلط است | `Get-Service *Bale*`؛ توکن `.env`؛ لاگ سرویس |
| متن فارسی `???` می‌شود | نوع ستون یا COLLATE اشتباه است | مطمئن شوید از همین نسخهٔ کد با NVARCHAR و دیتابیس با COLLATE فارسی استفاده می‌کنید |
| سرور خیلی کند / رم کم | SQL Server زیاد رم گرفته | قدم ۴ (۵۱۲ مگابایت) را دوباره اجرا کنید |
| `git: command not found` | Git نصب نیست | Git for Windows را نصب کنید و PowerShell را دوباره باز کنید |

---

## دفعات بعد: آوردن تغییرات جدید از گیت‌هاب

وقتی روی لپ‌تاپ تغییر جدید commit و push شد، روی سرور:

### الف) اگر ربات با NSSM سرویس است — اول متوقفش کنید

```
nssm stop BaleArchiveBot
```

(اگر نام سرویس فرق دارد، همان نامی که در `Get-Service *Bale*` دیدید.)

**اگر درست باشد:** سرویس Stopped می‌شود.

### ب) آخرین کد را بگیرید

```
cd C:\bots\yadgiri
git fetch origin
git checkout cursor/owner-post-insert-7da1
git pull origin cursor/owner-post-insert-7da1
```

**اگر درست باشد:** پیام دانلود/به‌روزرسانی می‌آید و خطای conflict نمی‌بینید.

اگر `git pull` دربارهٔ فایل‌های محلی هشدار داد، **فایل `.env` را دست نزنید و پاک نکنید**. فقط بگویید تا کمکتان کنند؛ معمولاً `.env` در گیت نیست.

### ج) نصب وابستگی‌ها و مهاجرت (اگر لازم شد)

```
cd C:\bots\yadgiri\bale-archive-bot
.\scripts\install.ps1
```

**اگر درست باشد:** نصب بدون خطا تمام می‌شود.

### د) سرویس را دوباره روشن کنید

```
nssm start BaleArchiveBot
```

**اگر درست باشد:** `Get-Service *Bale*` وضعیت Running نشان می‌دهد و ربات در بله جواب می‌دهد.

---

## چک‌لیست نهایی بعد از استقرار اول

- [ ] دیتابیس `bale_archive` ساخته شده (نه `ehya`)
- [ ] حافظه SQL Server حدود ۵۱۲ مگابایت است
- [ ] `.env` توکن و `DATABASE_URL` درست دارد؛ `OWNER_POST_SYNC=false`
- [ ] `check_db.py` گفته `database_ok`
- [ ] یک‌بار با `run.ps1` کار کرده و `/start` جواب داده
- [ ] سرویس NSSM Running است
- [ ] پورت ۱۴۳۳ به اینترنت باز نیست

---

## قدم ۱۱ — سنجش سرعت روی سرور واقعی (بعد از اینکه ربات کار کرد)

تست بار روی لپ‌تاپ شلوغ قابل اتکا نیست. وقتی ربات روی سرور روشن و پایدار است،
همین تست را **روی سرور** اجرا کنید و عدد p95 را یادداشت کنید.

۱) سرویس را موقتاً متوقف کنید (تا تداخل نداشته باشد):

```
nssm stop BaleArchiveBot
```

**اگر درست باشد:** سرویس Stopped است.

۲) تست بار را اجرا کنید:

```
cd C:\bots\yadgiri\bale-archive-bot
.\.venv\Scripts\python.exe -m pytest tests\e2e\test_load.py -q --tb=line
```

**اگر درست باشد:** یا همه پاس می‌شود، یا اگر فقط آستانهٔ زمان رد شد، در پیام خطا
عددی شبیه `p95 latency X.XXs` می‌بینید.

۳) عدد p95 را اینجا یادداشت کنید: `..........` ثانیه

- اگر p95 زیر حدود ۲ ثانیه بود: عالی است.
- اگر بین ۲ تا ۳ ثانیه بود: قابل قبول برای شروع؛ بعداً دوباره بسنجید.
- اگر **بالای ۳ ثانیه** بود: رم ۲ گیگ سرور احتمالاً کم است و باید تصمیم بگیرید
  (ارتقای رم، کاهش بار SQL Server، یا تغییر معماری).

۴) سرویس را دوباره روشن کنید:

```
nssm start BaleArchiveBot
```

**اگر درست باشد:** سرویس Running است و ربات در بله جواب می‌دهد.

---

اگر وسط راه گیر کردید، همان پیام خطا را عیناً کپی کنید؛ با جدول بالا یا با پشتیبان فنی قابل پیگیری است.
