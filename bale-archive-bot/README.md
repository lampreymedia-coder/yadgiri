# ربات آرشیو بله (Bale Archive Bot)

ربات آرشیو برای پیام‌رسان **بله** که در دیتابیس موجود **`Bale_Archive`** (MySQL 8.0) می‌نویسد.
این دیتابیس را نیروی انسانی طراحی کرده است. ربات هیچ جدول یا دیتابیسی نمی‌سازد.

## روند کار

1. ادمین داخل گروه `/register` را می‌زند و **واحد سازمانی** گروه را از فهرست `OrgUnits` انتخاب می‌کند. نتیجه: یک ردیف در `BaleGroups`.
2. عضو گروه پیامی می‌فرستد. ربات در **پیام خصوصی** از او می‌پرسد: «بله / خیر / انصراف».
3. «بله»، سپس انتخاب حداقل یک هشتگ (از جدول `Hashtags`) و در صورت تمایل «📝 توضیحات» (پاسخ Reply به پیام ربات)، سپس پیش‌نمایش، سپس **«تأیید نهایی»**.
4. فقط در این لحظه `Posts` (با `Source='bale'`، `OrgUnitId` گروه و `UserNote`) و `PostHashtags` و `PostMedia` در **یک تراکنش** نوشته می‌شوند.
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

برای به‌روزرسانی فقط خط آخر را دوباره بزنید. برای عوض کردن شاخه: `... deploy.sh --branch claude/merged-schema` (بعد از آن، اجرای بدون `--branch` روی همان شاخه می‌ماند). `deploy.sh` این کارها را انجام می‌دهد:

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
| `app/db/` | تنها جای SQL و نام جدول/ستون‌ها (`repo.py`، `reports.py`، `schema.py`) |
| `app/domain/archive.py` | تنها کدی که `Posts` می‌نویسد (بعد از تأیید نهایی) |
| `app/preflight.py`، `scripts/preflight.py` | بررسی فقط‌خواندنی دیتابیس هنگام شروع |
| `scripts/deploy.sh`، `backup.sh`، `run.sh` | نصب، پشتیبان‌گیری، اجرای دستی |
| `deploy/balebot.service` | سرویس systemd (کاربر `balebot`، `TZ=Asia/Tehran`، `PYTHONUTF8=1`) |

فایل‌هایی که ربات روی دیسک نگه می‌دارد (نه در دیتابیس)، همه زیر `/var/lib/balebot`:

- `offset`
- `admins.json`
- `media/<سال>/<ماه>/`

صفحه‌ی سلامت فقط روی `http://127.0.0.1:8000/healthz` در دسترس است.

## ساختار دیتابیس (ادغام‌شده)

ربات فقط با این ۸ جدول کار می‌کند:
`Users`، `BaleGroups`، `BaleGroupMembers`، `Hashtags`، `Posts`، `PostHashtags`، `PostMedia`، `OrgUnits` (فقط خواندن).

- ربات کاربر را فقط با `BaleChatId` پیدا می‌کند و ردیف‌های `Users` را تغییر نمی‌دهد. تنها استثنا پر کردن `BaleUsername` خالی است.
- ربات فقط پست‌های `Source='bale'` را می‌سازد، گزارش می‌گیرد و لغو می‌کند.
- جدول‌های `zz_old_*` و `DatabankItems` خوانده نمی‌شوند.

## لینک فایل‌ها و فایل‌های بزرگ

- لینک مشاهده: `http://95.38.191.89:8090/m/<شماره>/<امضا>`. تابع `build_media_url` آن را می‌سازد. بخش‌های اکسل، پنل و اعلان همه از همین تابع استفاده می‌کنند.
- فایل‌های بالای ۲۰ مگابایت را ربات نمی‌تواند دانلود کند. لینک بارگذاری این فایل‌ها (`/u/...`) در پی‌وی برای مدیران فرستاده می‌شود و در پنل، بخش «📦» هم دیده می‌شود.
- صفحه‌ی سلامت فقط روی `127.0.0.1:8000` در دسترس است.
- `scripts/compress_existing.py`: فشرده‌سازی فایل‌های قبلی. پیش‌فرض فقط گزارش می‌دهد؛ با `--apply` اجرا می‌شود.
- `scripts/export_excel.sh`: اکسل کامل را در `/root/bale-archive.xlsx` می‌سازد.

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
