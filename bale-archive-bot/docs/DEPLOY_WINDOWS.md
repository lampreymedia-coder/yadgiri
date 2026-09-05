# استقرار روی یک رایانه ویندوز

از صفر تا ربات روشن. Docker و سرور جدا لازم نیست.

راهنمای ساده‌تر برای SQL Server: `docs/SELF_HOST_WINDOWS.md`.

## پیش‌نیاز

- ویندوز ۱۰/۱۱
- Python 3.12
- **Microsoft SQL Server ۲۰۱۷+** (با SSMS) **یا** PostgreSQL روی localhost
- برای SQL Server: ODBC Driver 17 یا 18
- توکن ربات بله

## مراحل

1. `.env` را از `.env.example` بسازید و `BALE_BOT_TOKEN` و `DATABASE_URL` را پر کنید.

   SQL Server:

   `DATABASE_URL=mssql+aioodbc://USER:PASSWORD@localhost:1433/bale_archive?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes`

   در SSMS یک‌بار: `CREATE DATABASE bale_archive;`

   PostgreSQL جایگزین:

   `DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/bale_archive`

2. `.\scripts\install.ps1`
3. یک‌بار `.\scripts\run.ps1` تا از صحت کار مطمئن شوید (`polling_started`).
4. در بله ربات را استارت کنید. شما مدیر می‌شوید.
5. ربات را به گروه رصد اضافه کنید و ادمین کنید. زیر پیام‌ها دکمه‌های هشتگ می‌آید.
6. یک گروه خصوصی دو نفره (شما + ربات) بسازید، ربات را ادمین کنید، بنویسید `آرشیو`.
7. سرویس دائمی: `.\scripts\install-service.ps1` (NSSM). جزئیات در `docs/RUNBOOK.md`.

رسانه در `MEDIA_ROOT` روی همین دیسک ذخیره می‌شود. بعداً با `STORAGE_BACKEND=s3`
می‌توان سوییچ کرد؛ الان فقط پیاده‌سازی لوکال فعال است.

کامپیوتر خانگی اگر Sleep برود یا خاموش شود ربات می‌ایستد. برای ۲۴ ساعته
یک VPS لازم است؛ این استقرار فقط وابستگی به Cursor را قطع می‌کند.
