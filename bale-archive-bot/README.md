# ربات آرشیو بله (Bale Archive Bot)

ربات آرشیو برای پیام‌رسان **بله** که در دیتابیس موجود **`Bale_Archive`** (MySQL 8.0) می‌نویسد.
این دیتابیس را نیروی انسانی طراحی کرده است. ربات هیچ جدول یا دیتابیسی نمی‌سازد.

## روند کار

1. ادمین داخل گروه `/register` را می‌زند و سطح گروه (۱ تا ۷) را انتخاب می‌کند. نتیجه: یک ردیف در `EhyaGroup`.
2. عضو گروه پیامی می‌فرستد. ربات در **پیام خصوصی** از او می‌پرسد: «بله / خیر / انصراف».
3. «بله»، سپس انتخاب حداقل یک هشتگ (از جدول `Hashtag`)، سپس پیش‌نمایش، سپس **«تأیید نهایی»**.
4. فقط در این لحظه `Post` و `PostHashtag` و `PostMedia` در **یک تراکنش** نوشته می‌شوند.
   ربات زیر پیام اصلی در گروه می‌نویسد «✅ ثبت شد» و هشتگ‌ها را می‌آورد، و پیام‌های ویزارد پاک می‌شوند.
5. «خیر»، «انصراف»، منقضی شدن ویزارد (۳۰ دقیقه) یا ری‌استارت: **هیچ ردیفی** ثبت نمی‌شود.

- پیام اصلی کاربر هرگز حذف یا دوباره منتشر نمی‌شود.
- گروه ثبت‌نشده یا غیرفعال: ربات کاملاً ساکت است.
- گروه آرشیو (`ARCHIVE_CHAT_ID`) فقط یک نسخه‌ی پشتیبان داخل بله است و هرگز در دیتابیس ثبت نمی‌شود.

## نصب و به‌روزرسانی روی سرور (Ubuntu 24.04)

```bash
sudo apt-get install -y git
sudo git clone -b claude/magical-tesla-sb2d7n --depth 1 https://github.com/lampreymedia-coder/yadgiri.git /opt/balebot/src
sudo bash /opt/balebot/src/bale-archive-bot/scripts/deploy.sh
```

برای به‌روزرسانی فقط خط آخر را دوباره بزنید. `deploy.sh` این کارها را انجام می‌دهد:

- نصب پیش‌نیازها
- ساخت کاربر لینوکسی `balebot`
- آوردن کد
- نصب بسته‌ها از آینه‌ی runflare
- ساخت `/etc/balebot/balebot.env` با دسترسی 600
- پشتیبان‌گیری با `mysqldump`
- اجرای `preflight`
- راه‌اندازی سرویس systemd

## فایل‌ها

| مسیر | کار |
|---|---|
| `app/mapping.py` | نگاشت نوع محتوا به کدهای `content_type` و `media_type` |
| `app/db/repo.py` | تنها جای SQL: خواندن و نوشتن ردیف در ۷ جدول ربات |
| `app/domain/archive.py` | تنها کدی که `Post` می‌نویسد (بعد از تأیید نهایی) |
| `app/preflight.py`، `scripts/preflight.py` | بررسی فقط‌خواندنی دیتابیس هنگام شروع |
| `scripts/deploy.sh`، `backup.sh`، `run.sh` | نصب، پشتیبان‌گیری، اجرای دستی |
| `deploy/balebot.service` | سرویس systemd (کاربر `balebot`، `TZ=Asia/Tehran`، `PYTHONUTF8=1`) |

فایل‌هایی که ربات روی دیسک نگه می‌دارد (نه در دیتابیس)، همه زیر `/var/lib/balebot`:

- `offset`
- `admins.json`
- `media/<سال>/<ماه>/`

صفحه‌ی سلامت فقط روی `http://127.0.0.1:8000/healthz` در دسترس است.

## دستورها

| دستور | کجا | چه کسی |
|---|---|---|
| `/register`، `/unregister` | داخل گروه | ادمین |
| `/stats`، `/groups`، `/admins`، `/addadmin`، `/removeadmin` | پیام خصوصی | ادمین |
| `/start`، `/help`، `/id`، `/tags` | پیام خصوصی | همه |

## تست‌ها

تست‌ها یک دیتابیس MySQL **دورریختنی و محلی** از روی اسکیمای نیرو (`tests/fixtures/`) می‌سازند.
کد ربات در تست‌ها با کاربری اجرا می‌شود که فقط `SELECT/INSERT/UPDATE/DELETE` دارد.
تست‌ها هرگز به سرور وصل نمی‌شوند.

```bash
pip install -r requirements.txt pytest pytest-asyncio
python -m pytest tests/bot tests/unit -q
```
