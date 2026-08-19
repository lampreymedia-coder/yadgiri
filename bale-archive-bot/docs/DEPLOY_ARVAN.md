# استقرار روی ابر آروان — گام به گام

از صفر تا ربات فعال. هر بخش را به ترتیب انجام دهید.

## ۱) پیش‌نیازها

- یک ربات بله ساخته‌شده از طریق @BotFather بله و توکن آن
- حساب [ابر آروان](https://panel.arvancloud.ir)
- (برای وب‌هوک) یک دامنه — اگر دامنه ندارید با `RUN_MODE=polling` جلو بروید

## ۲) دیتابیس ابری (DBaaS) — مهم‌ترین قدم

> دیتابیس را روی خود سرور نصب **نکنید**. تک‌نقطه‌ی شکست این سیستم دیتابیس است.

1. پنل آروان → «دیتابیس ابری» → ساخت PostgreSQL نسخه ۱۷ با نود Standby.
2. یک دیتابیس `bale_archive` و دو کاربر بسازید:
   - `bot_app` — کاربر برنامه (SELECT/INSERT/UPDATE/DELETE)
   - `bot_migrate` — کاربر مهاجرت (ALTER/CREATE)
3. «شبکه‌های مجاز» را فقط به IP سرور اپ محدود کنید (پورت ۵۴۳۲).
4. اتصال SSL را الزامی کنید.
5. رشته‌ی اتصال:

```
DATABASE_URL=postgresql+asyncpg://bot_app:<pass>@<host>:5432/bale_archive?ssl=require
```

*[جای اسکرین‌شات: صفحه‌ی ساخت دیتابیس ابری]*

## ۳) فضای ابری (Object Storage)

1. پنل آروان → «فضای ابری» → دو باکت **خصوصی** بسازید:
   - `bale-archive-media` (رسانه‌ها)
   - `bale-archive-backup` (بکاپ شبانه)
2. کلید دسترسی بسازید و `S3_ACCESS_KEY` / `S3_SECRET_KEY` را بردارید.
3. endpoint بر اساس منطقه:
   - سیمین (تهران): `https://s3.ir-thr-at1.arvanstorage.ir`
   - شهریار (تبریز): `https://s3.ir-tbz-sh1.arvanstorage.ir`

*[جای اسکرین‌شات: ساخت باکت خصوصی]*

## ۴) سرور ابری (ابرک)

1. یک ابرک Ubuntu 24.04 با ۲vCPU / 4GB بسازید.
2. امنیت پایه:

```bash
adduser deploy && usermod -aG sudo,docker deploy
# ورود فقط با کلید SSH؛ در /etc/ssh/sshd_config:
#   PasswordAuthentication no
#   PermitRootLogin no
sudo timedatectl set-timezone Asia/Tehran
```

3. گروه امنیتی: فقط ۲۲ (SSH از IP خودتان)، ۴۴۳ و ۸۸ (وب‌هوک) باز باشد.
4. Docker را نصب کنید: `curl -fsSL https://get.docker.com | sh`

## ۵) استقرار برنامه

```bash
git clone <repo> bale-archive-bot && cd bale-archive-bot
cp .env.example .env
nano .env    # مقداردهی: توکن، DATABASE_URL، ARCHIVE_CHAT_ID، ADMIN_USER_IDS، کلیدهای S3
docker compose up --build -d
docker compose run --rm app python scripts/seed_tags.py
docker compose logs -f app   # باید polling_started را ببینید
```

### ساخت کانال آرشیو (ARCHIVE_CHAT_ID)

1. یک **گروه یا کانال خصوصی** بسازید که فقط شما و ربات عضو آن باشید.
2. ربات را ادمین کنید.
3. یک پیام بفرستید؛ سپس با `docker compose logs app | grep chat` یا متد
   `getChat` شناسه‌ی عددی (منفی) را پیدا و در `.env` بگذارید.

### فعال‌سازی در گروه‌ها

1. ربات را به هر گروه رصد اضافه کنید و **ادمین با دسترسی حذف پیام** کنید.
2. در گروه `/onboard` بزنید تا پیام راهنما پین شود.

## ۶) وب‌هوک (اختیاری — نیازمند دامنه)

1. رکورد A دامنه را به IP ابرک بدهید.
2. در `Caddyfile` دامنه را جایگزین کنید.
3. در `.env`:

```
RUN_MODE=webhook
WEBHOOK_BASE_URL=https://your.domain
WEBHOOK_SECRET_PATH=<خروجی: python -c "import secrets;print(secrets.token_urlsafe(24))">
```

4. اجرا:

```bash
docker compose --profile webhook up -d
docker compose run --rm app python scripts/set_webhook.py
docker compose run --rm app python scripts/set_webhook.py --info   # بررسی
```

بله فقط پورت‌های ۴۴۳ و ۸۸ را قبول می‌کند؛ Caddy گواهی TLS را خودکار می‌گیرد.

## ۷) بکاپ شبانه

روی سرور (خارج از کانتینر) `s3cmd` و `postgresql-client` نصب کنید و cron بسازید:

```bash
sudo apt install -y s3cmd postgresql-client
crontab -e
# هر شب ساعت ۳:
0 3 * * * cd /home/deploy/bale-archive-bot && set -a && . ./.env && set +a && ./scripts/backup.sh >> /var/log/bale-backup.log 2>&1
```

**تست بازیابی الزامی است** (بکاپ تست‌نشده بکاپ نیست):

```bash
# روی یک دیتابیس آزمایشی:
DATABASE_URL=postgresql://bot_migrate:...@host:5432/bale_archive_test \
  ./scripts/restore.sh s3://bale-archive-backup/pg/backup-<stamp>.dump.gz
```

نتیجه‌ی تست را در `docs/RUNBOOK.md` (بخش آخر) ثبت کنید.

## ۸) probe اجباری API

قبل از بهره‌برداری، یک بار روی گروه تست:

```bash
docker compose run --rm -e PROBE_CHAT_ID=<گروه تست> app python scripts/api_probe.py
```

خروجی در `docs/BALE_API_NOTES.md` ذخیره می‌شود.

## ۹) پایش

- `https://<server>:8000/healthz` — وضعیت (در polling هم فعال است)
- `/metrics` — Prometheus (اگر `METRICS_ENABLED=true`)
- `/health` در چت ادمین — آمار صف‌ها و دیتابیس
