# Runbook — نصب روی ویندوز و عیب‌یابی

همه‌چیز روی **یک رایانه ویندوز** اجرا می‌شود. Docker، WSL، Caddy، Redis و
دیتابیس ابری استفاده نمی‌شود.

## نصب اول (گام‌به‌گام)

1. Python 3.12 را از python.org نصب کنید. تیک **Add python.exe to PATH** را بزنید.
2. PostgreSQL 16 یا 17 را نصب کنید. پورت **5432**. کاربر `postgres` و رمزی که
   خودتان انتخاب می‌کنید. دیتابیس بسازید:

   ```
   CREATE DATABASE bale_archive;
   CREATE EXTENSION IF NOT EXISTS pg_trgm;
   ```

3. پوشه پروژه را باز کنید، فایل `.env.example` را کپی کنید به `.env`.
4. در `.env` این دو را پر کنید:
   - `BALE_BOT_TOKEN` = توکن ربات بله
   - `DATABASE_URL=postgresql+asyncpg://postgres:رمز_شما@localhost:5432/bale_archive`
5. PowerShell را **به‌عنوان Administrator** باز کنید:

   ```
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   .\scripts\install.ps1
   .\scripts\run.ps1
   ```

   اگر `polling_started` را دیدید ربات روشن است. یک‌بار در بله به ربات
   `/start` بزنید.

## سرویس دائمی با NSSM

بدون NSSM، با بستن پنجره PowerShell ربات می‌میرد.

1. NSSM را از https://nssm.cc/download بگیرید و `nssm.exe` را در PATH بگذارید
   (یا مسیر کامل را به اسکریپت بدهید).
2. PowerShell Administrator:

   ```
   .\scripts\install-service.ps1
   ```

3. سرویس `BaleArchiveBot` باید در `services.msc` وضعیت Running داشته باشد.
4. توقف / شروع:

   ```
   nssm stop BaleArchiveBot
   nssm start BaleArchiveBot
   ```

5. لاگ‌ها: `data\bot-stdout.log` و `data\bot-stderr.log`

`PYTHONUTF8=1` توسط اسکریپت سرویس ست می‌شود تا متن فارسی خراب نشود.

## Windows Defender

پوشه `MEDIA_ROOT` (پیش‌فرض `data\media` داخل پروژه) را به **استثناهای
Windows Defender** اضافه کنید:

Windows Security → Virus & threat protection → Exclusions → Add folder.

بدون این کار فایل‌های دانلودی ممکن است قرنطینه شوند و ربات نتواند رسانه را
ذخیره کند.

## Windows Update

ری‌استارت خودکار Windows Update را غیرفعال کنید یا به یک ساعت مشخص محدود
کنید (مثلاً ۳ صبح). ری‌استارت بی‌خبر سرویس ربات را قطع می‌کند تا دفعه بعد
که ویندوز بالا می‌آید NSSM دوباره آن را روشن کند — در این فاصله پیام‌ها
معطل می‌مانند.

Settings → Windows Update → Advanced options → Active hours
یا Group Policy: Configure Automatic Updates.

## بکاپ شبانه با Task Scheduler

اسکریپت `scripts\backup.ps1` با `pg_dump.exe` از دیتابیس بکاپ می‌گیرد و
۳۰ روز نگه می‌دارد (پوشه `BACKUP_DIR`، پیش‌فرض `data\backups`).

1. Task Scheduler را باز کنید → Create Task.
2. General: Run whether user is logged on or not، Run with highest privileges.
3. Triggers: Daily، مثلاً 01:00.
4. Actions: Start a program
   - Program: `powershell.exe`
   - Arguments: `-NoProfile -ExecutionPolicy Bypass -File "C:\path\to\bale-archive-bot\scripts\backup.ps1"`
   - Start in: پوشه پروژه
5. یک‌بار دستی Run کنید و وجود فایل `.dump` را در `data\backups` ببینید.

بازیابی آزمایشی (الزامی بعد از استقرار اول):

```
.\scripts\restore.ps1 -DumpPath data\backups\backup-YYYYMMDD-HHMMSS.dump
```

وقتی پرسید، `RESTORE` را تایپ کنید.

| تاریخ | فایل بکاپ | نتیجه | امضا |
|-------|-----------|-------|------|
| _هنوز اجرا نشده_ | — | — | — |

## عیب‌یابی

### 1. ربات هیچ پیامی را نمی‌بیند
وب‌هوک قدیمی را پاک کنید: `python scripts\set_webhook.py --delete`
سرویس را با `nssm restart BaleArchiveBot` ری‌استارت کنید.

### 2. «آرشیو» نوشتم ولی تأییدی نیامد
ربات باید **ادمین گروه** باشد. داخل همان گروه بنویسید `/archive` یا `آرشیو`.
باید پیام «این گروه به‌عنوان آرشیو خصوصی ثبت شد» بیاید. اگر نیامد، یک‌بار
در پی‌وی ربات `/start` بزنید.

### 3. در گروه رصد پیام می‌دهم ولی سؤال هشتگ نمی‌آید
ربات را ادمین کنید (دسترسی ارسال پیام). سؤال هشتگ **همان زیر پیام در گروه**
ظاهر می‌شود؛ لازم نیست پی‌وی را استارت کرده باشید. محتوای فورواردی هم
پذیرفته می‌شود.

### 4. پیام‌های گروه حذف نمی‌شوند
ربات را ادمین با دسترسی «حذف پیام» کنید. تا وقتی گروه آرشیو ثبت نشده باشد
عمداً چیزی حذف نمی‌شود تا داده از دست نرود.

### 5. دیتابیس در دسترس نیست
PostgreSQL Service در `services.msc` باید Running باشد. پورت 5432. رمز
`DATABASE_URL` را چک کنید. آپدیت‌ها موقتاً در `data\spool` ذخیره می‌شوند.

### 6. بله 429 می‌دهد
خودکار با `retry_after` صبر می‌کند. در `.env` مقدار `RATE_GLOBAL_RPS` را
کاهش دهید و سرویس را ری‌استارت کنید.

### 7. کیبورد قدیمی کار نمی‌کند
منقضی شده. محتوای جدید بفرستید یا `/resume`.

### 8. فایل‌ها ذخیره نمی‌شوند
`MEDIA_ROOT` و استثنای Defender را چک کنید. فایل‌های خیلی بزرگ فقط در گروه
آرشیو بله می‌مانند (محدودیت دانلود بله).

### 9. مهاجرت دیتابیس: pg_trgm
یک‌بار در pgAdmin: `CREATE EXTENSION IF NOT EXISTS pg_trgm;` سپس
`.\.venv\Scripts\python.exe -m alembic upgrade head`

### 10. دو نسخه همزمان
فقط یک سرویس NSSM و هیچ پنجره `run.ps1` اضافه. وگرنه getUpdates conflict.

### 11. ساعت شمسی اشتباه
بسته `tzdata` باید نصب باشد (`install.ps1` نصب می‌کند). `TZ=Asia/Tehran`.
بدون tzdata روی ویندوز zoneinfo کار نمی‌کند.

### 12. متن فارسی در لاگ به‌هم‌ریخته
`PYTHONUTF8=1` را در سرویس NSSM چک کنید (`nssm edit BaleArchiveBot` →
Environment).

### 13. Windows فایل لاگ را قفل کرده
ورکر رسانه بعد از هر فایل هندل را می‌بندد. اگر چرخش لاگ NSSM شکست خورد،
آنتی‌ویروس را روی `data\` استثنا کنید.

### 14. سرویس بعد از آپدیت ویندوز بالا نمی‌آید
NSSM روی Automatic است؛ اگر نیامد `nssm start BaleArchiveBot`. Active hours
را محدود کنید (بخش Windows Update بالا).
