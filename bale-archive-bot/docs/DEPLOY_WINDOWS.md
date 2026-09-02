# استقرار روی یک رایانه ویندوز

از صفر تا ربات روشن. Docker و سرور جدا لازم نیست.

## پیش‌نیاز

- ویندوز ۱۰/۱۱
- Python 3.12
- PostgreSQL روی localhost پورت 5432
- توکن ربات بله

## مراحل

1. `.env` را از `.env.example` بسازید و `BALE_BOT_TOKEN` و `DATABASE_URL` را پر کنید.
   نمونه:

   `DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/bale_archive`

2. `.\scripts\install.ps1`
3. یک‌بار `.\scripts\run.ps1` تا از صحت کار مطمئن شوید (`polling_started`).
4. در بله ربات را استارت کنید. شما مدیر می‌شوید.
5. ربات را به گروه رصد اضافه کنید و ادمین کنید. زیر پیام‌ها دکمه‌های هشتگ می‌آید.
6. یک گروه خصوصی دو نفره (شما + ربات) بسازید، ربات را ادمین کنید، بنویسید `آرشیو`.
7. سرویس دائمی: `.\scripts\install-service.ps1` (NSSM). جزئیات در `docs/RUNBOOK.md`.

رسانه در `MEDIA_ROOT` روی همین دیسک ذخیره می‌شود. بعداً با `STORAGE_BACKEND=s3`
می‌توان سوییچ کرد؛ الان فقط پیاده‌سازی لوکال فعال است.
