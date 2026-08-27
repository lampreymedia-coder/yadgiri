# Handoff — ربات آرشیو بله (`@orbitionadminbot`)

این فایل بستهٔ کامل تحویل به نفر بعدی است. توکن، رمز دیتابیس و کلید S3 **اینجا نیست**؛ فقط در `.env` محلی‌اند (`gitignore`). مالک توکن را جداگانه می‌دهد.

تاریخ این نوشته: **2026-08-27**.  
آخرین کامیت هنگام نوشتن: روی شاخه `cursor/bale-archive-bot-7da1`.  
PR: https://github.com/lampreymedia-coder/yadgiri/pull/7  
پایه: `claude/upbeat-shannon-1pe012`  
ریپو: `lampreymedia-coder/yadgiri`  
کد ربات: پوشه `bale-archive-bot/` (ریشه گیت `/workspace` است)

کلون:

```
git clone https://github.com/lampreymedia-coder/yadgiri.git
cd yadgiri
git checkout cursor/bale-archive-bot-7da1
```

تست‌ها هنگام این نوشته: **160 passed, 2 skipped** (`cd bale-archive-bot && pytest -q`).

---

## محصول مورد نظر مالک (فاطمه)

ربات در **چند گروه رصد** عضو می‌شود. اعضا متن عادی، فایل، صوت و **فوروارد** می‌فرستند (**بدون منشن، بدون `/start` بعد از راه‌اندازی**). ربات **در گروه جواب نمی‌دهد و ری‌اکشن نمی‌گذارد**. سؤال هشتگ در **پیام خصوصی فرستنده** باز می‌شود. بعد از تأیید، محتوا با `copyMessage` به **یک گروه آرشیو خصوصی به‌ازای هر هشتگ** می‌رود.

چهار هشتگ دانه:

| slug | عنوان | هشتگ |
|------|--------|------|
| learning | یادگیری | `#یادگیری` |
| network_source | شبکه و منبع | `#شبکه_و_منبع` |
| content | محتوایی | `#محتوایی` |
| document | سند | `#سند` |

ویزارد: چند هشتگ قابل انتخاب؛ مرحله «تعداد هشتگ» از UX حذف شده (کد هنوز `cnt` دارد برای سازگاری). پیش‌نمایش «اصلاح هشتگ». استیکر و GIF نادیده. صوت/فایل فوراً ویزارد را باز می‌کنند. ویرایش پیام مبدأ، متن ذخیره‌شده را عوض می‌کند. بعد از آرشیو/انصراف، پیام‌های خصوصی ویزارد پاک می‌شوند؛ خلاصه ۳۰ ثانیه‌ای.

زبان UI فقط فارسی، همه در `app/i18n/fa.py`. کد و کامنت انگلیسی. قواعد: `.cursorrules`.

مالک **رد کرده**:

- منشن اجباری به‌عنوان UX اصلی
- الزام اینکه فقط **سازنده گروه** بتواند ربات را اضافه کند
- ترک فوری گروه اگر بازو اول عضو شود و هنوز ادمین نباشد (در بله معمولاً اول عضو می‌کنند بعد ادمین)
- ری‌اکشن / جواب داخل گروه رصد

مالک **خواسته**: هر مدیر همان گروه بتواند ربات را اضافه کند.

---

## هویت زنده بله

- یوزرنیم: `orbitionadminbot`
- bot_id: `517468618`
- API: `https://tapi.bale.ai`
- مالک/ادمین ربات: فاطمه `1290496049` (`ADMIN_USER_IDS`)
- `getMe` فیلد `can_read_all_group_messages` ندارد
- `setMyCommands` روی این استقرار **501 Not Implemented**
- وب‌هوک باید خالی باشد: `getWebhookInfo.url == ""`
- لینک افزودن به گروه: `https://ble.ir/orbitionadminbot?startgroup=start`
- اسناد API: https://docs.bale.ai
- گروه دولوپر بله (از کارهای قبلی): `ble.ir/join/GYi6oKS2Zm`

### گروه‌های ثبت‌شده (SQLite زنده، 2026-08-27)

| id | chat_id | عنوان | نقش | وضعیت |
|----|---------|--------|-----|--------|
| 1 | 5807512128 | cyber Economy | research | **کار می‌کند** — متن عادی و فوروارد می‌رسد |
| 2 | 4891222369 | آرشیو یادگیری | archive / learning | بایند شده |
| 3 | 5057982323 | آرشیو محتوایی | archive / content | بایند شده |
| 4 | 5738693515 | آرشیو سند | archive / document | بایند شده |
| 5 | 4738899236 | آرشیو شبکه و منبع | archive / network_source | بایند شده؛ همچنین مقدار `archive_chat_id` کلی |
| 6 | 4388261948 | تست ربات | research | **متن عادی نمی‌رسد** |
| 7 | 6301700238 | سنجش ربات | نقش هنوز انتخاب نشده (`role_asked: true`) | جوین ثبت شد 2026-08-27 09:57 UTC |

کاربران دیده‌شده:

| id | bale_user_id | نام | username | is_admin |
|----|--------------|-----|----------|----------|
| 1 | 2037137626 | علیرضا قدس | arghods | 0 |
| 2 | 1290496049 | فاطمه | — | **1** |
| 3 | 828391251 | محمدحسین علیپوری | mhalipouri | 0 |
| 4 | 39895898 | رادخوش | fradkhosh | 0 |

سازنده «تست ربات»: `765620369` محمدرضا بهروزی زاد `@mrbehroozizad` — ربات را **مسدود** کرده (`403 bot was blocked by the user` روی DM). فاطمه آنجا ادمین است نه سازنده.

تنها intake موفق از «تست ربات»: submission 38 `xdajzb` با متن بعد از منشن (`@orbitionadminbot یک متن آزمایشی`) در 2026-08-26 18:32. بعد از آن هیچ متن عادی از `4388261948` در `getUpdates` نیامده.

سابمیشن‌ها: ۴۱ ردیف — ۴۰ تا از گروه ۱ (cyber Economy)، ۱ تا از گروه ۶. وضعیت: ۹ completed، ۱۶ cancelled، ۱۶ expired.

`app_settings`:

```
archive_chat_id              = 4738899236
archive_chat:learning        = 4891222369
archive_chat:content         = 5057982323
archive_chat:document        = 5738693515
archive_chat:network_source  = 4738899236
```

---

## آنچه واقعاً کار می‌کند

در **cyber Economy** (`5807512128`): فاطمه سازنده است. اعضا ~۵، ادمین‌ها ~۳ (ربات ادمین است). متن `.`، «سلام»، فوروارد، صوت — همه می‌آیند و ویزارد خصوصی باز می‌شود. همین پروسس پولینگ هر دو گروه را می‌خواند؛ پس خرابی «تست ربات» فریز پولر نیست.

مسیر جایگزین که مالک **رد کرده** ولی از نظر API کار می‌کند: `@orbitionadminbot متن` (منشن با محتوا). `strip_leading_bot_mention` منشن را از متن جدا می‌کند.

مسیر خصوصی: `INGEST_MODE=hybrid` — اگر کاربر محتوا را در DM بفرستد، ویزارد باز می‌شود و اگر چند گروه رصد باشد گروه را انتخاب می‌کند.

الگوی گروه رصد که ثابت شده کار می‌کند:

1. فاطمه **سازنده** گروه باشد
2. همه را مدیر نکند
3. بازو را اول **عضو** سپس **ادمین** کند

---

## باگ باز (این را نفر بعدی باید حل کند)

### 1) بله متن عادی بعضی گروه‌ها را به بازو نمی‌دهد — مشکل اصلی محصول

دیسپچر فقط چیزی را آرشیو می‌کند که `getUpdates` برگرداند. در «تست ربات» حتی وقتی ربات `administrator` است با `can_delete_messages` / `can_restrict_members` / `can_promote_members` / `can_pin_messages`:

- جوین و پیام سرویس (`message_id=0`, بدون text) می‌آید
- منشن با محتوا می‌آید
- **متن عادی و فوروارد نمی‌آید**

مقایسه زنده (2026-08-27):

- cyber Economy: 5 عضو، 3 ادمین، فاطمه **creator**، ربات ادمین
- تست ربات: 7 عضو، 6 ادمین (تقریباً همه مدیر)، فاطمه ادمین نه سازنده، سازنده ربات را بلاک کرده. خاموش کردن toggle «همه مدیر» افراد قبلی را از ادمینی درنیاورد.

فرضیه‌ها (هیچ‌کدام با Bot HTTP API قابل اجبار نیستند):

1. گروه «همه اعضا مدیر» / تقریباً همه مدیر → بله مثل Privacy Mode تلگرام فقط command/mention/service می‌دهد؛ ادمین‌کردن بازو در این گروه کافی نیست
2. سازنده گروه ربات را بلاک کرده → تحویل پیام گروه قطع می‌شود
3. فقط وقتی **سازنده** بازو را اضافه/ادمین کند، متن عادی می‌رسد (cyber Economy این‌طور است)
4. تنظیم حریم خصوصی BotFather بله اگر وجود داشته باشد (مستند رسمی HTTP معادل `/setprivacy` ندارد؛ `getMe` هم فلگ ندارد)

کد **نمی‌تواند** پیام‌هایی را که بله نفرستاده اختراع کند. `getChatHistory` در فهرست متدهای تأییدشده نیست.

لاگ تشخیص: `update_received` با `text_preview=` خالی و `message_id=0` یعنی آپدیت سرویس آمده، محتوا نیامده. اگر اصلاً `update_received` برای آن chat_id نباشد، بله آپدیت را نداده.

### 2) سؤال رصد/آرشیو

کامیت `cba6925` رویداد `my_chat_member`/`chat_member` را به جوین تبدیل می‌کند. گروه «سنجش ربات» (`6301700238`) در DB ثبت شد با `role_asked: true` ولی **نقش انتخاب نشد** — یعنی سؤال رفته (یا باید رفته باشد) و دکمه زده نشده، یا DM به کسی رسیده که ندیده.

اگر رویداد جوین نرسد، کار دستی: در گروه `/start` یا `@orbitionadminbot`.

### 3) میزبان ۲۴/۷ نیست

این ربات روی Cloud Agent VM اجرا شده. VM در بیکاری مکالمه **می‌خوابد**. `keep_alive.sh` + watchdog فقط تا وقتی VM بیدار است کمک می‌کند. استقرار دائم باید **ویندوز مالک + NSSM** باشد (`docs/DEPLOY_WINDOWS.md`). خرابی فعلی «تست ربات» از خواب VM نبود؛ پولر زنده بود و cyber Economy همزمان پیام می‌گرفت.

---

## چیزهایی که امتحان شد و نتیجه نداد / برنگردانید

تاریخچه شاخه (جدید به قدیم، مرتبط):

| کامیت | چه کرد | نگه دارید؟ |
|--------|--------|------------|
| `cba6925` | سؤال رصد/آرشیو برای هر جوین، حتی مدیر گروه غیرسراسری؛ `my_chat_member` | بله |
| `2e2f0f5` | تشخیص practically-all-admins و توضیح به کاربر وقتی بله متن نمی‌دهد | بله |
| `4e44f7f` | عضو می‌شود، **ترک نمی‌کند**، منتظر ارتقا می‌ماند | بله — مالک صریح خواست |
| `39f1b45` | هر مدیر تأییدشدهٔ همان گروه بتواند اضافه کند | بله — مالک صریح خواست |
| `3dd9a39` | الزام سازنده گروه | **برنگردانید** — مالک رد کرد |
| `31bfad9` | الزام ادمین بودن بازو برای intake در گروه‌های اضافه | نرم شده؛ ادمین لازم است برای دیدن پیام ولی ترک فوری ممنوع |
| `ff81c36` | fallback منشن | نگه دارید به‌عنوان fallback، نه UX اصلی |
| `df8f91a` | استارتاپ را روی پاکسازی چت خصوصی بلاک نکن | بله |
| `7c3501a` | ویرایش مبدأ متن ذخیره‌شده را عوض می‌کند | بله |
| `5a08a1c` | جواب داخل گروه رصد حذف شد | بله |
| `a5618d5` | تلاش ری‌اکشن تگ — API ندارد | بی‌فایده |
| `2e85d08` | `keep_alive` هر بار `.env` را دوباره می‌خواند | بله |
| `f884e87` | وب‌هوک مرده را ول کن، پولینگ | بله |
| `e6fa26e` | هشتگ سند + حذف مرحله تعداد | بله |
| `869cf31` | تشخیص گروه بله با `chat.type` نه id منفی | بله — idهای بله مثبت‌اند |

**هرگز** `pkill -f 'python -m app.main'` نزنید اگر همان رشته در دستور kill باشد؛ با PID بکشید.

offset پولینگ را از دیسک restore نکنید (Bale بعد از idle ممکن است id را ریست کند). `polling_started offset=None`.

userbot / `aiobale` (کلاینت کاربر) با قاعده «فقط متدهای تأییدشده Bot API» سازگار نیست مگر مالک صریحاً عوض کند.

---

## جریان کد فعلی

ورود گروه (`register_group_events` در `app/handlers/group_intake.py`):

1. جوین از `new_chat_members` / `new_chat_member` / `group_chat_created` **یا** از `Update.my_chat_member` / `chat_member` (`membership_event_as_message`)
2. اگر بازو هنوز ادمین نیست: **خارج نمی‌شود**. `pending_admin=true`، DM انتظار ارتقا، و اگر نقش خالی است کیبورد رصد/آرشیو برای اضافه‌کننده
3. اضافه‌کننده باید مدیر/سازنده **همان گروه** باشد وگرنه leave
4. مدیر سراسری ربات لازم نیست؛ مدیر گروه کافی است
5. دکمه‌های `srg`/`sar`/`stg`/`srb` پشت `is_admin` سراسری قفل نیستند (`ROLE_SETUP_ACTIONS`)
6. بعد از ارتقا، `_activate_pending_group` از hello، batch، یا رویداد membership صدا زده می‌شود
7. اگر تقریباً همه ادمین باشند (`app/domain/delivery.py`: اعضا ≥ ۵ و ادمین‌ها ≥ اعضا−۱)، بعد از انتخاب رصد توضیح می‌دهد که بله ممکن است متن ندهد
8. منشن اول خط از محتوا جدا می‌شود
9. استیکر/GIF ignore
10. پیام خالی گروه (stub / `ContentType.OTHER` بدون محتوا) اگر نقش رصد باشد به فرستنده می‌گوید بله متن را نداد
11. اگر `needs_role` هنوز true باشد، محتوا پردازش نمی‌شود تا نقش مشخص شود

ویزارد خصوصی (`app/handlers/wizard.py`): تصمیم → انتخاب هشتگ (چندانتخاب) → پیش‌نمایش → `copyMessage` به هر گروه آرشیو بایندشده.

`INGEST_MODE=hybrid`: محتوا در DM هم intake می‌شود.

---

## دستورها

عمومی (خصوصی مگر ذکر شده):

| دستور | کار |
|--------|-----|
| `/start` | در خصوصی: آنبورد؛ در گروه: hello / فعال‌سازی نقش |
| `/help` | راهنما |
| `/my` | آخرین ثبت‌ها |
| `/undo [کد]` | لغو |
| `/resume` | ادامه ویزارد |

در گروه: منشن تنها `@orbitionadminbot` = hello. متن «آرشیو» / `/archive` = بایند گروه آرشیو.

ادمین سراسری (فاطمه): `/panel` `/stats` `/top_users` `/top_tags` `/tag` `/type` `/user` `/search` `/get` `/export` `/tags` `/addtag` `/edittag` `/disabletag` `/reordertags` `/groups` `/health` `/settings` `/broadcast` `/forget` `/onboard`

Callback scheme: `1|<act>|<sid>|<arg>` حداکثر ۶۴ بایت ASCII (`app/bale/keyboards.py`).

نقش گروه: `srg` رصد، `sar` آرشیو، `stg` انتخاب هشتگ آرشیو، `srb` بازگشت.

ویزارد: `yes` `no` `cx` `cnt` `tg` `ok` `bk` `fin` `edt` `nt` `pgt` `gr` `noop`.

---

## اجرا

```
cd bale-archive-bot
# .env را از .env.example بسازید و BALE_BOT_TOKEN + DATABASE_URL را پر کنید
python -m pip install -e ".[dev]"   # Python >= 3.12
python -m app.main
# یا: bash scripts/keep_alive.sh
```

Health: `GET http://127.0.0.1:8000/healthz`  
پولینگ کوتاه‌فاصله (idle 2s، busy 0.3s)، POST `getUpdates` اول (مثل python-bale-bot داخل ایران).

تولید ویندوز: Postgres محلی + NSSM — `docs/DEPLOY_WINDOWS.md`, `docs/RUNBOOK.md`, `docs/ADMIN_GUIDE.md`.  
این محیط Cloud از SQLite استفاده می‌کند (فقط برای تست زنده).

قبل از PR: `ruff` + `black` + `mypy --strict` + `pytest`.

توکن فقط در `.env`. لاگ httpx نباید URL کامل را چاپ کند.

---

## متغیرهای `.env` این محیط Cloud (بدون توکن)

```
BALE_BOT_TOKEN=<فقط در .env محلی>
BALE_API_BASE=https://tapi.bale.ai
RUN_MODE=polling
ARCHIVE_CHAT_ID=
ADMIN_CHAT_ID=
ADMIN_USER_IDS=1290496049
ALLOWED_GROUP_IDS=
INGEST_MODE=hybrid
DATABASE_URL=sqlite+aiosqlite:////workspace/bale-archive-bot/data/bot.db
STATE_BACKEND=postgres
STORAGE_BACKEND=local
MEDIA_ROOT=data/media
MEDIA_DOWNLOAD_ENABLED=true
LOG_LEVEL=INFO
LOG_FORMAT=console
TZ=Asia/Tehran
METRICS_ENABLED=true
PYTHONUTF8=1
SPOOL_DIR=data/spool
BACKUP_DIR=data/backups
WEBHOOK_BASE_URL=
WEBHOOK_SECRET_PATH=
```

`data/` و `.env` در gitignoreاند. بک‌آپ SQLite زنده: `bale-archive-bot/data/bot.db` (روی همین VM؛ در گیت نیست).

نمونه تولید: `DATABASE_URL=postgresql+asyncpg://postgres:YOUR_PASSWORD@localhost:5432/bale_archive`

---

## محدودیت API بله

فقط متدهای `app/bale/methods.py` / `scripts/api_probe.py`. متد ابداعی ممنوع (`.cursorrules` بند ۹).

استفاده‌شده و موجود زنده: `getMe` `getUpdates` `deleteWebhook` `getWebhookInfo` `sendMessage` `copyMessage` `forwardMessage` `editMessageText` `deleteMessage` `getChat` `getChatMember` `getChatAdministrators` `getChatMembersCount` `leaveChat` `getFile` `answerCallbackQuery` (capability-gated) …

وجود ندارد / خراب برای این محصول:

- `setMessageReaction` → 404
- `editMessageReplyMarkup` (فقط `editMessageText` با keyboard)
- `parse_mode`
- long-poll رسمی روی `getUpdates` (docs: فقط offset/limit)
- `getChatHistory`
- `promoteChatMember` از طرف خود بازو روی خودش: 403
- `setMyCommands`: 501
- `can_read_all_group_messages` روی `getMe`
- HTTP معادل `/setprivacy`

اسناد داخلی: `docs/BALE_API_NOTES.md` — بخش probe هنوز کامل پر نشده؛ قبل از استقرار جدی `python scripts/api_probe.py`.

id گروه‌های بله در این استقرار **مثبت** است (مثل تلگرام منفی نیست). تشخیص گروه با `chat.type`.

---

## ساختار مهم

```
app/main.py                 پولینگ + healthz:8000 + scheduler
app/config.py               Settings از env
app/core/dispatcher.py      مسیر آپدیت
app/core/receive.py         سیاست webhook مرده → polling
app/core/fsm.py             WizardState
app/handlers/group_intake.py جوین، نقش، intake گروه، private-first
app/handlers/wizard.py      ویزارد خصوصی
app/handlers/admin.py       پنل، /archive، callback نقش
app/handlers/user_commands.py /start /help /my /undo /resume
app/domain/delivery.py      تشخیص practically-all-admins
app/domain/group_roles.py   research vs archive + bind هشتگ
app/domain/submission.py    intake/archive/copy
app/domain/classify.py      نوع محتوا + نرمال‌سازی فارسی
app/i18n/fa.py              تمام رشته‌های فارسی + SEED_TAGS
app/bale/client.py          httpx، retry، بدون لو توکن
app/bale/methods.py         فقط متدهای تأییدشده
app/bale/models.py          pydantic Update/Message (extra=allow)
app/db/models.py            ORM
alembic/                    اسکیما Postgres
docs/DECISIONS.md           D-01 … D-16
docs/DEPLOY_WINDOWS.md      NSSM
docs/ADMIN_GUIDE.md         راهنمای فارسی ادمین
docs/RUNBOOK.md             عملیات ویندوز
tests/fakes/fake_bale.py    بدون شبکه
scripts/keep_alive.sh       ریستارت حلقه‌ای
scripts/api_probe.py        پروب متدها
```

README.md **قدیمی است** (هنوز ویزارد داخل گروه را توصیف می‌کند). منبع حقیقت رفتار: DECISIONS D-09/D-10/D-16 و همین فایل.

---

## قواعد پروژه (`.cursorrules`)

1. کد و کامنت انگلیسی؛ رشته‌های کاربر فارسی
2. هیچ فارسی‌ای خارج از `app/i18n/fa.py`
3. SQL فقط SQLAlchemy / bind — نه f-string
4. شبکه با timeout و retry
5. نه `except:` نه `except Exception: pass`
6. type hint کامل؛ `mypy --strict`
7. نه TODO / NotImplementedError در تحویل
8. نه توکن در مخزن
9. فقط متدهای تأییدشده بله
10. قبل از PR: ruff + black + mypy + pytest

---

## تست‌های کلیدی جوین / تحویل

- `test_bot_added_as_member_waits_for_admin_promotion_without_leaving`
- `test_group_admin_can_add_then_promote_and_first_plain_text_is_processed`
- `test_group_admin_add_auto_registers_research_and_accepts_ordinary_forward` (الان اول کیبورد نقش می‌خواهد، بعد `srg`)
- `test_my_chat_member_join_asks_research_or_archive`
- `test_mention_with_content_opens_wizard_without_archiving_mention`
- `test_empty_group_stub_notifies_sender_when_bale_withholds_text`
- `tests/unit/test_delivery.py`

تست‌ها شبکه نمی‌زنند. پاس شدن تست **ثابت نمی‌کند** بله متن عادی را در یک گروه واقعی می‌دهد.

---

## پیشنهاد عملی به نفر بعدی

1. توکن را از مالک بگیرید؛ در گیت و در Issue پیست نکنید.
2. ربات را **۲۴/۷ روی ویندوز مالک** با NSSM بالا بیاورید؛ روی Cloud Agent تست زنده پایدار نیست. این VM با بیکاری مکالمه می‌خوابد.
3. برای گروه رصد جدید: فاطمه **سازنده** باشد، همه را مدیر نکند، بازو را عضو سپس ادمین کند — الگوی cyber Economy.
4. در «تست ربات»: چند نفر را دستی از ادمینی درآورید (خاموش کردن toggle کافی نبود) و از محمدرضا بخواهید ربات را آنبلاک کند، یا گروه را رها کنید.
5. در «سنجش ربات» دکمه رصد/آرشیو را بزنید؛ اگر DM نیامد در گروه `/start` بفرستید.
6. اگر باز هم `getUpdates` متن نداد، موضوع **پلتفرم بله** است (BotFather / پشتیبانی بله / گروه دولوپر)، نه ویزارد.
7. منشن را به‌عنوان fallback نگه دارید ولی مالک آن را به‌عنوان UX اصلی نمی‌خواهد.
8. SQLite این محیط را کپی کنید اگر تاریخچه ثبت‌ها لازم است؛ در گیت نیست: `bale-archive-bot/data/bot.db`.
9. README را با رفتار واقعی (ویزارد خصوصی) به‌روز کنید وقتی فرصت شد.

---

## تماس / مالکیت

- مالک محصول در بله: فاطمه `1290496049`
- ایمیل صاحب ریپو/ایجنت (از متادیتای Cloud Agent): `conventiontv1@gmail.com`
- ایجنت قبلی: https://cursor.com/agents/bc-96f4bad6-c4e5-49ce-9d23-bb1292357da1
- شاخه: `cursor/bale-archive-bot-7da1`
- PR: https://github.com/lampreymedia-coder/yadgiri/pull/7
