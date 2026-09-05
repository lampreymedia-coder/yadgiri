# اجرای ربات روی رایانه خودتان (ویندوز + SQL Server)

این راهنما برای کسی است که می‌خواهد ربات را **روی کامپیوتر خودش** روشن کند
و دیگر به محیط Cursor وابسته نباشد.

کامپیوتر خانگی اگر خاموش شود، Sleep برود، یا اینترنت قطع شود، ربات هم
می‌ایستد. برای کار ۲۴ ساعته بعداً یک سرور (VPS) لازم است. این مراحل فقط
ربات را روی همین ویندوز به SQL Server وصل می‌کند.

توکن ربات را **هیچ‌وقت** در چت یا گیت‌هاب نگذارید. فقط داخل فایل `.env`
روی همین کامپیوتر.

## چیزهایی که باید از قبل داشته باشید

1. ویندوز ۱۰ یا ۱۱
2. Python 3.12 از [python.org](https://www.python.org/downloads/) —
   موقع نصب تیک **Add python.exe to PATH** را بزنید
3. SQL Server که از SSMS به آن وصل می‌شوید (۲۰۱۷ یا جدیدتر)
4. [ODBC Driver 18 for SQL Server](https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server)
5. توکن ربات بله (از BotFather بله)
6. کد پروژه (دانلود ZIP از گیت‌هاب، یا `git clone`)

## ۱) دیتابیس را در SSMS بسازید

SSMS را باز کنید، به همان سروری که همیشه وصل می‌شوید بروید، و این را اجرا کنید:

```
CREATE DATABASE bale_archive;
```

یک کاربر SQL با رمز بسازید که به این دیتابیس دسترسی داشته باشد
(یا اگر با Windows Authentication کار می‌کنید، همان کافی است).

اگر SQL Server Express دارید و پورت ۱۴۳۳ باز نیست:
SQL Server Configuration Manager → SQL Server Network Configuration →
TCP/IP را Enable کنید و سرویس SQL Server را Restart کنید.

## ۲) پوشه پروژه را باز کنید

مثلاً:

```
cd C:\bots\yadgiri\bale-archive-bot
```

## ۳) فایل تنظیمات را بسازید

```
copy .env.example .env
```

فایل `.env` را با Notepad باز کنید.

- `BALE_BOT_TOKEN` = توکن ربات (فقط همین‌جا)
- `ADMIN_USER_IDS` = شناسه عددی خودتان در بله (مثلاً `1290496049`)
- `DATABASE_URL` را یکی از این دو شکل بگذارید:

با کاربر و رمز SQL:

```
DATABASE_URL=mssql+aioodbc://USER:PASSWORD@localhost:1433/bale_archive?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes
```

`USER` و `PASSWORD` را عوض کنید. اگر رمز نویسه‌های خاص دارد
(`@` `: ` `/` `#`) باید URL-encode شود.

با ورود ویندوز (Trusted Connection):

```
DATABASE_URL=mssql+aioodbc://@localhost/bale_archive?driver=ODBC+Driver+18+for+SQL+Server&Trusted_Connection=yes&TrustServerCertificate=yes
```

اگر سرور شما `localhost\SQLEXPRESS` است، در آدرس بنویسید
`localhost%5CSQLEXPRESS` به‌جای `localhost`.

## ۴) نصب

PowerShell را باز کنید (ترجیحاً Run as administrator):

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
.\scripts\install.ps1
```

این اسکریپت محیط مجازی، بسته‌ها (از جمله درایور SQL Server)، پوشه‌ها و
جداول دیتابیس را می‌سازد.

اگر گفت ODBC پیدا نشد، درایور ۱۸ را نصب کنید و دوباره همین فرمان را بزنید.

برای تست اتصال، بدون چاپ رمز:

```
.\.venv\Scripts\python.exe scripts\check_db.py
```

باید بگوید `database_ok`.

## ۵) روشن کردن ربات

```
.\scripts\run.ps1
```

اگر در پنجره نوشت `polling_started`، ربات روشن است. در بله `/start` بزنید.

با بستن این پنجره ربات خاموش می‌شود. تا وقتی کامپیوتر روشن و بیدار است
و اینترنت قطع نشده، کار می‌کند.

## ۶) سرویس دائمی (اختیاری، همان کامپیوتر)

اگر می‌خواهید با بستن پنجره ربات نمیرد (ولی Sleep و خاموشی همچنان
می‌کشد):

```
.\scripts\install-service.ps1
```

جزئیات NSSM، بکاپ و عیب‌یابی: `docs/RUNBOOK.md`.

بکاپ SQL Server را از SSMS بگیرید:
دیتابیس `bale_archive` → Tasks → Back Up.
یا اگر `sqlcmd` روی PATH باشد: `.\scripts\backup.ps1`.

## اگر چیزی خطا داد

| پیام / وضعیت | کار شما |
|---|---|
| `ODBC Driver` پیدا نشد | درایور ۱۸ را نصب کنید |
| `Login failed` | کاربر/رمز یا Trusted Connection را در `.env` چک کنید |
| `Cannot open database` | `CREATE DATABASE bale_archive` را در SSMS اجرا کنید |
| `getUpdates conflict` | فقط **یک** پنجره `run.ps1` یا یک سرویس NSSM |
| ربات جواب نمی‌دهد | کامپیوتر Sleep نرفته باشد؛ اینترنت وصل باشد؛ پنجره هنوز باز باشد |

توکن را برای کسی نفرستید. اگر ربات را به سرور ۲۴ ساعته بردید، همان فایل
`.env` را آن‌جا کپی کنید و اینجا `run.ps1` را نگذارید همزمان روشن بماند.
