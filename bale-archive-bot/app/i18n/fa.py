"""تمام رشته‌های فارسی نمایش‌داده‌شده به کاربر.

هیچ رشته‌ی فارسی‌ای خارج از این ماژول در منطق برنامه وجود ندارد.
توابع این ماژول فقط قالب‌بندی متن انجام می‌دهند.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import jdatetime

_TEHRAN = ZoneInfo("Asia/Tehran")
_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

# ─── ابزار قالب‌بندی ───


def fa_digits(value: int | float | str) -> str:
    """تبدیل ارقام لاتین به فارسی برای نمایش."""
    return str(value).translate(_FA_DIGITS)


def jalali_date(dt: datetime) -> str:
    """تاریخ شمسی به شکل ۱۴۰۵/۰۵/۲۸."""
    local = dt.astimezone(_TEHRAN)
    j = jdatetime.datetime.fromgregorian(datetime=local)
    return fa_digits(j.strftime("%Y/%m/%d"))


def jalali_time(dt: datetime) -> str:
    """ساعت محلی تهران به شکل ۱۴:۰۵."""
    local = dt.astimezone(_TEHRAN)
    return fa_digits(local.strftime("%H:%M"))


def format_bytes(size: int | None) -> str:
    """نمایش حجم فایل به فارسی."""
    if not size:
        return "نامشخص"
    if size >= 1024**3:
        return f"{fa_digits(round(size / 1024**3, 1))} گیگابایت"
    if size >= 1024**2:
        return f"{fa_digits(round(size / 1024**2, 1))} مگابایت"
    if size >= 1024:
        return f"{fa_digits(round(size / 1024, 1))} کیلوبایت"
    return f"{fa_digits(size)} بایت"


def format_duration(seconds: int | None) -> str:
    """نمایش مدت صوت/ویدیو به شکل ۳:۲۱."""
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return fa_digits(f"{minutes}:{secs:02d}")


CONTENT_TYPE_NAMES: dict[str, str] = {
    "text": "متن",
    "link": "لینک",
    "image": "تصویر",
    "video": "کلیپ",
    "animation": "انیمیشن",
    "voice": "پیام صوتی",
    "audio": "صوت",
    "document": "سند",
    "sticker": "استیکر",
    "contact": "مخاطب",
    "location": "مکان",
    "album": "آلبوم",
    "other": "محتوا",
}


def content_type_name(content_type: str) -> str:
    return CONTENT_TYPE_NAMES.get(content_type, CONTENT_TYPE_NAMES["other"])


# ─── گام ۱: تصمیم ───


def decision_prompt(
    name: str,
    content_type: str,
    group_title: str,
    dt: datetime,
    short_id: str = "",
    excerpt: str = "",
) -> str:
    excerpt_line = f"متن: «{excerpt}»\n" if excerpt else ""
    code_line = f"کد: {short_id}\n" if short_id else ""
    return (
        f"سلام {name}\n"
        "\n"
        f"گروه رصد: «{group_title}»\n"
        f"نوع: {content_type_name(content_type)}\n"
        f"{jalali_date(dt)}  {jalali_time(dt)}\n"
        f"{code_line}"
        f"{excerpt_line}"
        "\n"
        "همان پیام را بالاتر برایتان فرستادم تا با پیام دیگر قاطی نشود.\n"
        "برای آرشیو، هشتگ را انتخاب کنید. برای رد کردن، انصراف بزنید."
    )


def decision_subject_fallback(group_title: str, content_type: str, excerpt: str) -> str:
    excerpt_line = f"\n«{excerpt}»" if excerpt else ""
    title = group_title or "گروه رصد"
    return f"پیام از گروه «{title}» — {content_type_name(content_type)}{excerpt_line}"


BTN_SAVE_YES = "بله، انتخاب هشتگ"
BTN_SAVE_NO = "خیر، فقط در گروه بماند"
BTN_CANCEL_DELETE = "انصراف"

IMAGE_KEEP_PROMPT = (
    "این پیام هم متن دارد هم تصویر.\n"
    "خیلی از تصویرها تزئینی‌اند و آرشیو کردنشان لازم نیست.\n"
    "\n"
    "تصویر هم ذخیره شود؟"
)
BTN_IMAGE_YES = "بله، متن و تصویر"
BTN_IMAGE_NO = "فقط متن، بدون تصویر"

PREVIEW_IMAGE_INCLUDED = "تصویر: ذخیره می‌شود"
PREVIEW_IMAGE_TEXT_ONLY = "تصویر: ذخیره نمی‌شود (فقط متن)"

# ─── گام ۲: تعداد هشتگ ───

TAG_COUNT_PROMPT = "کدام هشتگ؟ می‌توانید یک یا چند مورد را با هم انتخاب کنید."

_COUNT_EMOJI = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣"}
_COUNT_WORD = {1: "یک", 2: "دو", 3: "سه", 4: "چهار", 5: "پنج"}


def btn_tag_count(count: int, total_active: int) -> str:
    emoji = _COUNT_EMOJI.get(count, "")
    word = _COUNT_WORD.get(count, fa_digits(count))
    if count == total_active and count <= 3:
        return f"{emoji} هر {word} هشتگ".strip()
    return f"{emoji} {word} هشتگ".strip()


BTN_TAG_COUNT_ALL = "🔢 همه"
BTN_TAG_COUNT_FREE = "🎯 انتخاب آزاد"
BTN_BACK = "⬅️ بازگشت"

# ─── گام ۳: انتخاب هشتگ ───


def tag_select_prompt(
    selected: int, target: int | None, group_title: str = "", short_id: str = ""
) -> str:
    del target
    header = f"گروه رصد: «{group_title}»\n" if group_title else ""
    code = f"کد: {short_id}\n" if short_id else ""
    return (
        f"{header}{code}"
        "هشتگ‌ها را انتخاب کنید. می‌توانید یک یا چند مورد را بزنید.\n"
        "دوباره زدن، انتخاب را برمی‌دارد.\n"
        "\n"
        f"{seed_tag_titles()}\n"
        f"انتخاب‌شده: {fa_digits(selected)}"
    )


TAG_UNCHECKED = "⬜️"
TAG_CHECKED = "✅"
BTN_CONFIRM_CONTINUE = "✔️ تایید و ادامه"
BTN_CONFIRM_CONTINUE_DISABLED = "✔️ ..."

TOAST_TAG_LIMIT_TEMPLATE = (
    "شما {count} هشتگ انتخاب کرده‌اید. اول یکی را بردارید یا به مرحله‌ی قبل برگردید."
)


def toast_tag_limit(count: int) -> str:
    return TOAST_TAG_LIMIT_TEMPLATE.format(count=fa_digits(_COUNT_WORD.get(count, count)))


TOAST_NO_TAG_SELECTED = "هنوز هیچ هشتگی انتخاب نکرده‌اید."
TOAST_NEED_FULL_COUNT = "هنوز تعداد هشتگ‌ها کامل نشده است."

# ─── گام ۴: پیش‌نمایش ───


def preview_prompt(
    sender_name: str,
    username: str | None,
    group_title: str,
    content_type: str,
    details: str,
    size_text: str,
    hashtags: str,
    excerpt: str,
    dt: datetime,
    short_id: str,
    image_line: str = "",
) -> str:
    username_part = f" (@{username})" if username else ""
    extra = f"{image_line}\n" if image_line else ""
    return (
        "پیش‌نمایش ثبت\n"
        "\n"
        f"فرستنده: {sender_name}{username_part}\n"
        f"گروه: {group_title}\n"
        f"نوع: {content_type_name(content_type)} {details}\n"
        f"حجم: {size_text}\n"
        f"هشتگ‌ها: {hashtags}\n"
        f"{extra}"
        f"متن: «{excerpt}»\n"
        f"زمان: {jalali_date(dt)}  {jalali_time(dt)}\n"
        f"کد: {short_id}\n"
        "\n"
        "از صحت این اطلاعات مطمئن هستید؟ می‌توانید هشتگ‌ها را اصلاح کنید یا به مرحله قبل برگردید."
    )


BTN_FINAL_CONFIRM = "✅ تایید نهایی و ذخیره"
BTN_EDIT_TAGS = "🏷 اصلاح هشتگ‌ها"
BTN_EDIT_NOTE = "📝 افزودن/ویرایش توضیح"
BTN_BACK_TO_PREV = "⬅️ بازگشت به مرحله‌ی قبل"
BTN_CANCEL = "❌ انصراف"

NOTE_PROMPT = "📝 توضیح خود را در یک پیام بفرستید. برای انصراف، دکمه‌ی بازگشت را بزنید."

# ─── گام ۵: موفقیت ───

USER_SAVED = "آرشیو شد."


def user_saved(missing_archives: list[str] | None = None) -> str:
    missing = missing_archives or []
    if not missing:
        return USER_SAVED
    return (
        f"{USER_SAVED}\n"
        f"به گروه آرشیو کپی نشد چون اتصال {' '.join(missing)} قطع است.\n"
        "گروه را از نو نسازید. داخل همان گروه آرشیو /archive بزنید و همان هشتگ را انتخاب کنید."
    )


def missing_archive_howto(hashtags: list[str] | None = None) -> str:
    tags = " ".join(hashtags) if hashtags else seed_tag_titles_comma()
    return (
        "اتصال گروه‌های آرشیو قطع است. خود گروه‌ها در بله مانده‌اند؛ "
        "فقط حافظهٔ این ماشین از نو ساخته شده و ربات دیگر شناسهٔ آن‌ها را ندارد.\n"
        "گروه‌ها را از نو نسازید.\n"
        "\n"
        f"هشتگ‌های بدون گروه: {tags}\n"
        "\n"
        "برای وصل دوباره، در هر گروه آرشیو دو نفره (یادگیری، شبکه و منبع، محتوایی، سند):\n"
        "۱) داخل همان گروه بنویسید /archive\n"
        "۲) در پیام خصوصی، همان هشتگ را برای آن گروه انتخاب کنید.\n"
        "\n"
        "بعد از این کار، محتوای بعدی همان‌جا کپی می‌شود. "
        "محتوای همین الان را دوباره در گروه رصد بفرستید."
    )


def success_message(short_id: str, hashtags: str, group_title: str, undo_minutes: int) -> str:
    del short_id, hashtags, group_title, undo_minutes
    return USER_SAVED


def published_header(sender_name: str, hashtags: str) -> str:
    return f"{sender_name}\n{hashtags}"


def archive_footer(sender_name: str, hashtags: str, content_type: str, short_id: str) -> str:
    return f"{hashtags}\n{sender_name}  ·  {content_type_name(content_type)}\n{short_id}"


def republished_header(sender_name: str) -> str:
    return sender_name


DECLINED_MESSAGE = "در آرشیو ذخیره نشد."
CANCELLED_MESSAGE = "ثبت لغو شد."

# ─── اعلان به ادمین ───


def admin_new_submission(
    name: str,
    bale_user_id: int,
    group_title: str,
    content_type: str,
    details: str,
    hashtags: str,
    short_id: str,
    dt: datetime,
    today_total: int,
    missing_archives: list[str] | None = None,
) -> str:
    missing = missing_archives or []
    missing_line = ""
    if missing:
        missing_line = (
            "\nگروه آرشیو ناقص: " + " ".join(missing) + "\nگروه‌های قبلی را از نو نسازید. "
            "داخل همان گروه آرشیو /archive بزنید و هشتگ را انتخاب کنید."
        )
    return (
        "داده جدید ذخیره شد\n"
        "\n"
        f"کاربر: {name} ({fa_digits(bale_user_id)})\n"
        f"گروه رصد: {group_title}\n"
        f"نوع: {content_type_name(content_type)} {details}\n"
        f"هشتگ: {hashtags}\n"
        f"کد: {short_id}\n"
        f"{jalali_date(dt)}  {jalali_time(dt)}"
        f"{missing_line}\n"
        "\n"
        f"مجموع امروز: {fa_digits(today_total)} مورد"
    )


def admin_batch_submissions(count: int, window_minutes: int) -> str:
    return (
        "🆕 ثبت‌های جدید\n"
        "\n"
        f"در {fa_digits(window_minutes)} دقیقه‌ی گذشته {fa_digits(count)} داده‌ی جدید ثبت شد."
    )


def admin_intake_failure_alert(reason: str) -> str:
    return (
        "🚨 هشدار: دریافت داده با خطا مواجه شد\n"
        "\n"
        f"علت: {reason}\n"
        "پیام کاربر حذف نشده و در صف انتظار نگه داشته شده است."
    )


def admin_spam_alert(name: str, bale_user_id: int, count: int) -> str:
    return (
        "⚠️ هشدار اسپم\n"
        "\n"
        f"کاربر {name} ({fa_digits(bale_user_id)}) در یک ساعت "
        f"{fa_digits(count)} مورد ارسال کرده است."
    )


def admin_error_alert(error_kind: str) -> str:
    return f"🚨 خطای مدیریت‌نشده در ربات\n\nنوع خطا: {error_kind}\nجزئیات در لاگ سیستم ثبت شده است."


# ─── پیام‌های خطا و وضعیت ───

ERR_BUSY = "⏳ یک لحظه صبر کنید، درخواست قبلی هنوز در حال پردازش است."
ERR_EXPIRED = "⚠️ این گفت‌وگو منقضی شده است. لطفاً محتوا را دوباره ارسال کنید."
ERR_NOT_YOURS = "🔒 این گفت‌وگو متعلق به شما نیست."
ERR_SERVER = (
    "❗️ ارتباط با سرور برقرار نشد. محتوای شما از بین نرفته و تا لحظاتی دیگر دوباره تلاش می‌کنیم."
)
ERR_DEGRADED = "⚠️ سیستم موقتاً در دسترس نیست. محتوای شما نگه داشته شده و به‌زودی پردازش می‌شود."
ERR_UNKNOWN_COMMAND = "دستور نامعتبر است. برای راهنما /help را بزنید."
ERR_SPAM_LIMIT = "⚠️ سقف ارسال ساعتی شما پر شده است. کمی بعد دوباره تلاش کنید."
ERR_GENERIC = "😔 مشکلی پیش آمد. لطفاً دوباره تلاش کنید."
ERR_UNDO_NOT_FOUND = "کدی با این مشخصات پیدا نشد یا متعلق به شما نیست."
ERR_UNDO_EXPIRED = "⚠️ مهلت لغو این ثبت گذشته است."

UNDO_SUCCESS = "↩️ ثبت لغو شد."

WIZARD_EXPIRED_FINAL = "⚠️ این گفت‌وگو منقضی شده است."


def reminder_message(content_type: str) -> str:
    return (
        f"⏰ هنوز منتظر تعیین هشتگ برای {content_type_name(content_type)} شما هستیم.\n"
        "اگر تصمیم نگیرید، به‌زودی طبق سیاست پیش‌فرض منتشر می‌شود."
    )


def expired_republished_message(short_id: str) -> str:
    return f"مهلت هشتگ‌گذاری تمام شد. پیام {short_id} در گروه ماند و در آرشیو ذخیره نشد."


def duplicate_warning(name: str, days_ago: int, short_id: str) -> str:
    return (
        f"⚠️ این محتوا قبلاً ({fa_digits(days_ago)} روز پیش) توسط {name} "
        f"با کد {short_id} ثبت شده است. باز هم ثبت شود؟"
    )


BTN_DUPLICATE_CONTINUE = "✅ بله، دوباره ثبت شود"
BTN_DUPLICATE_ABORT = "❌ خیر، منصرف شدم"

# ─── حالت درون‌گروهی (کاربر بدون پی‌وی) ───

BTN_OPEN_PRIVATE = "💬 گفت‌وگوی خصوصی با ربات"


def group_fallback_hint(bot_username: str) -> str:
    return f"برای انتخاب هشتگ، گفتگوی خصوصی ربات را باز کنید:\nhttps://ble.ir/{bot_username}"


def group_role_private_hint(bot_username: str) -> str:
    if bot_username:
        return f"نقش این گروه را در گفتگوی خصوصی مشخص کنید:\nhttps://ble.ir/{bot_username}"
    return "یک بار در گفتگوی خصوصی ربات /start را بزنید، بعد نقش گروه را مشخص کنید."


def onboard_message(bot_username: str) -> str:
    return (
        "راهنمای آرشیو\n"
        "────────────────\n"
        "محتوای گروه رصد می‌ماند. اگر نیاز به هشتگ و ذخیره باشد، "
        "ربات فقط از فرستنده در پیام خصوصی می‌پرسد.\n"
        "\n"
        f"یک بار ربات @{bot_username} را استارت کنید."
    )


# ─── دستورهای کاربر ───


def start_message(name: str) -> str:
    return (
        f"سلام {name}\n"
        "\n"
        "من ربات آرشیو هستم. وقتی در گروه رصد محتوا بفرستید، "
        "اینجا از شما می‌پرسم در کدام هشتگ ذخیره شود.\n"
        "\n"
        "/my — ثبت‌های شما\n"
        "/undo کد — لغو ثبت\n"
        "/resume — ادامه گفتگوی نیمه‌کاره\n"
        "/help — راهنما"
    )


def start_owner_setup(name: str) -> str:
    return (
        f"سلام {name}\n"
        "\n"
        "ربات روشن است و شما مدیر آن هستید.\n"
        "\n"
        f"{archive_group_setup()}\n"
        "\n"
        "منوی مدیریت: /panel"
    )


START_RESUME = "ادامه دسته‌بندی همان پیام:"


def bot_added_ask_role(group_title: str) -> str:
    return (
        f"ربات به گروه «{group_title}» اضافه شد.\n"
        "\n"
        "نقش این گروه چیست؟\n"
        "\n"
        "رصد: اعضا محتوا می‌فرستند و هشتگ در پیام خصوصی انتخاب می‌شود. "
        "بازو را اضافه کنید و بعد یکی از مدیران گروه آن را از فهرست اعضا "
        "به مدیر (ادمین) ارتقا دهد تا متن عادی و فوروارد بدون منشن دریافت شود.\n"
        "آرشیو: فقط محل نگهداری یک هشتگ است. برای هر هشتگ یک گروه جدا بسازید."
    )


BOT_JOIN_DENIED = "فقط مدیر ربات یا مدیر همان گروه می‌تواند بازو را اضافه کند."


def bot_join_waiting_for_admin(group_title: str) -> str:
    return (
        f"بازو به گروه «{group_title}» اضافه شد و خارج نمی‌شود.\n"
        "حالا یکی از مدیران گروه، بازو را از فهرست اعضا به مدیر (ادمین) ارتقا دهد.\n"
        "بعد از مدیرشدن، متن عادی یا فوروارد را بدون منشن بفرستید."
    )


def research_admin_setup_done(group_title: str) -> str:
    return (
        f"گروه «{group_title}» به‌عنوان گروه رصد فعال شد.\n"
        "متن عادی، فایل و پیام فورواردشده از این گروه، بدون منشن، "
        "سؤال هشتگ را در خصوصی فرستنده باز می‌کند."
    )


def bot_left_unauthorized_group(group_title: str) -> str:
    return f"این ربات فقط با دعوت مدیر وارد گروه می‌شود و از «{group_title}» خارج شد."


def admin_unauthorized_add(group_title: str, adder_name: str) -> str:
    who = adder_name or "نامشخص"
    return (
        f"کسی غیر از مدیر، ربات را به گروه «{group_title}» اضافه کرد.\n"
        f"اضافه‌کننده: {who}\n"
        "ربات از آن گروه خارج شد."
    )


GROUP_HELLO = "ربات در این گروه فعال است. محتوا را بفرستید؛ سؤال هشتگ در پیام خصوصی می‌آید."

GROUP_GOT_IT = "این پیام برای بایگانی مناسب نیست. متن، عکس، فایل، صوت یا کلیپ بفرستید."

BOT_READY_PING = "ربات روشن است.\nهمین‌جا پیام بفرستید، یا ربات را به گروه اضافه کنید."


def receive_backlog(pending: int) -> str:
    return (
        "ربات روشن است. مسیر تونل پیام‌رسان قطع شده بود "
        f"و {fa_digits(pending)} پیام در صف مانده بود.\n"
        "الان از مسیر پشتیبان گرفته می‌شوند؛ لازم نیست دوباره بفرستید."
    )


BTN_ADD_TO_GROUP = "افزودن ربات به گروه"


BTN_GROUP_IS_RESEARCH = "گروه رصد"
BTN_GROUP_IS_ARCHIVE = "گروه آرشیو هشتگ"


def archive_tag_prompt(group_title: str) -> str:
    return (
        f"گروه «{group_title}» آرشیو کدام هشتگ باشد؟\n"
        "\n"
        f"اسم گروه بهتر است با هشتگ یکی باشد: {seed_tag_titles_comma()}.\n"
        "فقط شما و ربات در این گروه باشید."
    )


def archive_set_done(group_title: str, hashtag: str) -> str:
    return f"گروه «{group_title}» به‌عنوان آرشیو {hashtag} ثبت شد."


def archive_already_set(group_title: str) -> str:
    return (
        f"گروه «{group_title}» آرشیو هشتگ است.\n"
        "اینجا فقط نسخه‌های ذخیره‌شده می‌آید. سؤال هشتگ در گروه‌های رصد پرسیده می‌شود."
    )


def research_set_done(group_title: str, bot_username: str | None = None) -> str:
    del bot_username
    return (
        f"گروه «{group_title}» به‌عنوان گروه رصد ثبت شد.\n"
        "\n"
        "حالا یکی از مدیران گروه، بازو را از فهرست اعضا به مدیر (ادمین) ارتقا دهد.\n"
        "مالک‌بودن لازم نیست؛ هر مدیر همان گروه می‌تواند بازو را مدیر کند.\n"
        "بعد از آن متن عادی، فایل و پیام فورواردشده بدون منشن، سؤال هشتگ را "
        "در خصوصی فرستنده باز می‌کند."
    )


def research_need_admin(group_title: str, bot_username: str | None = None) -> str:
    del bot_username
    return (
        f"گروه «{group_title}» از قبل رصد است.\n"
        "\n"
        "اگر پیام عادی یا فوروارد نمی‌رسد، از فهرست اعضای گروه مطمئن شوید "
        "بازو مدیر (ادمین) شده است.\n"
        "بعد از مدیرشدن، منشن لازم نیست."
    )


def research_rejoined(group_title: str, bot_username: str | None = None) -> str:
    del bot_username
    return (
        f"بازو دوباره به گروه «{group_title}» اضافه شد و نقش رصد حفظ شده است.\n"
        "حالا متن عادی یا پیام فورواردشده در گروه بفرستید؛ بدون منشن، "
        "سؤال هشتگ در خصوصی فرستنده باز می‌شود."
    )


def research_delivery_gap(
    group_title: str,
    *,
    member_count: int,
    admin_count: int,
    bot_is_admin: bool,
    almost_all_admins: bool,
    withheld: bool,
) -> str:
    """Explain why the hashtag question did not arrive for a research group."""
    parts = [f"گروه «{group_title}»."]
    if withheld:
        parts.append(
            "بله متن عادی این گروه را برای ربات نفرستاد؛ " "برای همین سؤال هشتگ در خصوصی نیامد."
        )
    if not bot_is_admin:
        parts.append("بازو هنوز مدیر گروه نیست. از فهرست اعضا آن را به مدیر (ادمین) ارتقا دهید.")
    if almost_all_admins:
        parts.append(
            f"الان {fa_digits(admin_count)} مدیر از {fa_digits(member_count)} عضو "
            "در این گروه هستند. در بله وقتی تقریباً همه مدیر باشند، "
            "بازو پیام عادی و فوروارد را نمی‌گیرد."
        )
        parts.append(
            "تنظیم «همه اعضا مدیر هستند» را خاموش کنید و چند نفر را "
            "از مدیر بودن درآورید تا حداقل دو عضو عادی بماند."
        )
    parts.append(
        "اگر سازنده گروه ربات را مسدود کرده، تا رفع مسدود، پیام گروه به بازو نمی‌رسد. "
        "یک گروه رصد تازه بسازید که خودتان سازنده‌اش باشید و همه را مدیر نکنید."
    )
    parts.append(
        "تا آن وقت همان محتوا را همین‌جا در خصوصی برای ربات بفرستید " "و گروه رصد را انتخاب کنید."
    )
    return "\n\n".join(parts)


ARCHIVE_SET_DONE = "این گروه به‌عنوان آرشیو خصوصی ثبت شد."
ARCHIVE_SET_NEED_PRIVATE = (
    "اول در پیام خصوصی ربات /start را بزنید تا مدیر شوید، بعد دوباره /archive را بفرستید."
)
RESEARCH_GROUP_READY = (
    "این گروه به‌عنوان گروه رصد ثبت شد.\n"
    "ربات را در گروه ادمین کنید تا پیام‌ها دیده شوند و سؤال هشتگ در خصوصی بیاید."
)
ALREADY_OWNER = "شما از قبل مدیر ربات هستید."


HELP_MESSAGE = (
    "راهنمای ربات آرشیو\n"
    "────────────────\n"
    "۱. محتوا را در گروه رصد بفرستید (متن، عکس، کلیپ، صوت، سند و هر فایل دیگر).\n"
    "۲. ربات در خصوصی می‌پرسد هشتگ بخورد یا نه.\n"
    "۳. اگر پیام هم متن دارد هم تصویر، جداگانه می‌پرسد تصویر هم ذخیره شود یا نه.\n"
    "۴. اگر بله، همان‌جا چهار هشتگ نشان داده می‌شود: یادگیری، شبکه و منبع، محتوایی، سند.\n"
    "۵. یک یا چند هشتگ را بزنید؛ قبل از تأیید نهایی می‌توانید اصلاح کنید.\n"
    "\n"
    "استیکر و گیف بایگانی نمی‌شوند.\n"
    "\n"
    "/my — آخرین ثبت‌ها\n"
    "/undo کد — لغو ثبت\n"
    "/resume — ادامه گفتگوی نیمه‌کاره\n"
)

MY_EMPTY = "هنوز هیچ ثبتی ندارید."
MY_HEADER = "🗂 آخرین ثبت‌های شما:"


def my_item_line(short_id: str, content_type: str, status_fa: str, dt: datetime) -> str:
    return (
        f"• {short_id} — {content_type_name(content_type)} — {status_fa} — "
        f"{jalali_date(dt)} {jalali_time(dt)}"
    )


STATUS_NAMES: dict[str, str] = {
    "draft": "پیش‌نویس",
    "awaiting_decision": "در انتظار تصمیم",
    "awaiting_tag_count": "در انتظار تصمیم تصویر",
    "awaiting_tags": "در انتظار انتخاب هشتگ",
    "awaiting_confirm": "در انتظار تایید",
    "completed": "ثبت‌شده",
    "declined": "بدون هشتگ",
    "cancelled": "لغوشده",
    "expired": "منقضی",
    "failed": "ناموفق",
}


def status_name(status: str) -> str:
    return STATUS_NAMES.get(status, status)


RESUME_NOTHING = "گفت‌وگوی نیمه‌کاره‌ای پیدا نشد."
RESUME_HEADER = "🔄 ادامه‌ی گفت‌وگوی قبلی:"

# ─── پنل ادمین ───

PANEL_HEADER = "🛠 پنل مدیریت"
BTN_PANEL_STATS = "📊 آمار کلی"
BTN_PANEL_TOP_USERS = "🥇 کاربران فعال"
BTN_PANEL_TOP_TAGS = "🏷 هشتگ‌های پرکاربرد"
BTN_PANEL_TAGS = "🗂 مدیریت هشتگ‌ها"
BTN_PANEL_GROUPS = "👥 گروه‌ها"
BTN_PANEL_HEALTH = "❤️ سلامت سیستم"
BTN_PANEL_SETTINGS = "⚙️ تنظیمات"
BTN_PANEL_EXPORT = "📤 خروجی اکسل"

REPORT_DIVIDER = "──────────────────────────"


def stats_report(
    range_text: str,
    total: int,
    contributors: int,
    total_bytes: int,
    tag_lines: list[str],
    type_line: str,
    top_user_lines: list[str],
) -> str:
    parts = [
        "📊 گزارش کلی آرشیو",
        REPORT_DIVIDER,
        f"بازه: {range_text}",
        "",
        f"📦 مجموع داده‌ها: {fa_digits(total)} مورد",
        f"👥 مشارکت‌کنندگان: {fa_digits(contributors)} نفر",
        f"💾 حجم کل: {format_bytes(total_bytes)}",
        "",
        "🏷 به تفکیک هشتگ",
    ]
    parts.extend(tag_lines or ["  (داده‌ای نیست)"])
    parts.extend(["", "📁 به تفکیک نوع", f"  {type_line}" if type_line else "  (داده‌ای نیست)"])
    parts.extend(["", "🥇 فعال‌ترین کاربران"])
    parts.extend(top_user_lines or ["  (داده‌ای نیست)"])
    parts.append(REPORT_DIVIDER)
    return "\n".join(parts)


TAG_INACTIVE_SUFFIX = " (غیرفعال)"


def tag_title_with_state(title_fa: str, is_active: bool) -> str:
    return title_fa if is_active else f"{title_fa}{TAG_INACTIVE_SUFFIX}"


def range_between(label: str, to_date: str) -> str:
    return f"{label} تا {fa_digits(to_date)}"


def matrix_row_total(total: int) -> str:
    return f"جمع {fa_digits(total)}"


def range_label(kind: str) -> str:
    labels = {
        "today": "امروز",
        "week": "هفته‌ی اخیر",
        "month": "ماه اخیر",
        "all": "کل بازه",
    }
    return labels.get(kind, kind)


def bar_line(title: str, count: int, share_pct: float, bar: str, width: int = 16) -> str:
    dots = "." * max(2, width - len(title))
    return f"  {title} {dots} {fa_digits(count)}  ({fa_digits(round(share_pct))}٪) {bar}"


def ranked_user_line(rank: int, name: str, count: int, width: int = 20) -> str:
    dots = "." * max(2, width - len(name))
    return f"  {fa_digits(rank)}. {name} {dots} {fa_digits(count)}"


HEALTH_HEADER = "❤️ سلامت سیستم"


def health_report(
    in_progress: int,
    failed: int,
    outbox_pending: int,
    media_backlog: int,
    last_update_id: int | None,
    db_size: str,
) -> str:
    return (
        f"{HEALTH_HEADER}\n"
        f"{REPORT_DIVIDER}\n"
        f"🔄 در جریان: {fa_digits(in_progress)}\n"
        f"❌ ناموفق: {fa_digits(failed)}\n"
        f"📤 صف خروجی: {fa_digits(outbox_pending)}\n"
        f"📎 رسانه‌ی در انتظار: {fa_digits(media_backlog)}\n"
        f"🔢 آخرین آپدیت: {fa_digits(last_update_id) if last_update_id else 'ندارد'}\n"
        f"💽 حجم دیتابیس: {db_size}"
    )


TAGS_HEADER = "🗂 هشتگ‌های تعریف‌شده:"


def tag_line(
    title_fa: str, hashtag: str, slug: str, is_active: bool, items: int | None = None
) -> str:
    status = "" if is_active else " (غیرفعال)"
    count = f" — {fa_digits(items)} مورد" if items is not None else ""
    return f"• {title_fa} {hashtag} [{slug}]{status}{count}"


ADDTAG_PROMPT_TITLE = "🏷 عنوان فارسی هشتگ جدید را بفرستید:"
ADDTAG_PROMPT_EMOJI = "ایموجی هشتگ را بفرستید (یا «-» برای رد شدن):"
ADDTAG_PROMPT_DESC = "توضیح کوتاه هشتگ را بفرستید (یا «-» برای رد شدن):"


def addtag_preview(title_fa: str, hashtag: str, slug: str) -> str:
    return f"🏷 پیش‌نمایش هشتگ جدید\n\nعنوان: {title_fa}\nهشتگ: {hashtag}\nشناسه: {slug}\n\nثبت شود؟"


BTN_YES = "✅ بله"
BTN_NO = "❌ خیر"

ADDTAG_DONE = "✅ هشتگ جدید ثبت شد و از این پس در کیبورد انتخاب ظاهر می‌شود."
ADDTAG_DUPLICATE = "⚠️ هشتگی با این عنوان یا شناسه از قبل وجود دارد."
TAG_NOT_FOUND = "هشتگی با این شناسه پیدا نشد."
TAG_DISABLED_DONE = "✅ هشتگ غیرفعال شد. داده‌های قبلی دست‌نخورده می‌مانند."
TAG_CONFIRM_DISABLE = "آیا از غیرفعال‌کردن این هشتگ مطمئن هستید؟"
TAG_REORDER_DONE = "✅ ترتیب هشتگ‌ها به‌روزرسانی شد."
TAG_REORDER_USAGE = (
    "شناسه‌ها را با فاصله و به ترتیب دلخواه بفرستید. مثال:\n"
    "/reordertags learning content network_source"
)
TAG_EDIT_USAGE = "قالب: /edittag شناسه عنوان جدید"
TAG_EDIT_DONE = "✅ هشتگ ویرایش شد."

GROUPS_HEADER = "👥 گروه‌های ثبت‌شده:"


def group_line(
    title: str | None,
    bale_chat_id: int,
    is_active: bool,
    can_delete: bool,
    role: str | None = None,
    tag: str | None = None,
) -> str:
    status = "فعال" if is_active else "غیرفعال"
    delete_perm = "حذف دارد" if can_delete else "حذف ندارد"
    if role == "archive":
        role_part = f" — آرشیو {tag or ''}".rstrip()
    elif role == "research":
        role_part = " — رصد"
    else:
        role_part = ""
    return (
        f"• {title or 'بدون عنوان'} ({fa_digits(bale_chat_id)}) — "
        f"{status} — {delete_perm}{role_part}"
    )


SETTINGS_HEADER = "⚙️ تنظیمات زمان اجرا:"
SETTINGS_USAGE = "برای تغییر: /settings کلید مقدار"
SETTINGS_UPDATED = "✅ تنظیم به‌روزرسانی شد."

BROADCAST_PROMPT = "متن اعلان را بفرستید:"
BROADCAST_CONFIRM_TEMPLATE = "این پیام به {n} گروه ارسال می‌شود. مطمئن هستید؟"


def broadcast_confirm(group_count: int) -> str:
    return BROADCAST_CONFIRM_TEMPLATE.format(n=fa_digits(group_count))


BROADCAST_SENT = "✅ اعلان در صف ارسال قرار گرفت."
BROADCAST_CANCELLED = "لغو شد."

EXPORT_PREPARING = "⏳ در حال آماده‌سازی خروجی..."
EXPORT_EMPTY = "داده‌ای برای خروجی در این بازه نیست."

SEARCH_USAGE = "قالب: /search عبارت"
SEARCH_EMPTY = "نتیجه‌ای پیدا نشد."
SEARCH_HEADER = "🔎 نتایج جست‌وجو:"


def search_result_line(short_id: str, content_type: str, snippet: str, dt: datetime | None) -> str:
    date_part = f" — {jalali_date(dt)}" if dt else ""
    return f"• {short_id} [{content_type_name(content_type)}]{date_part}\n  {snippet}"


GET_USAGE = "قالب: /get کد"
GET_NOT_FOUND = "موردی با این کد پیدا نشد."
GET_NO_ARCHIVE = "برای این مورد پیام آرشیوی ثبت نشده است."

USER_USAGE = "قالب: /user شناسه یا @نام‌کاربری"
USER_NOT_FOUND = "کاربری با این مشخصات پیدا نشد."


def user_report_header(name: str, username: str | None, bale_user_id: int) -> str:
    username_part = f" (@{username})" if username else ""
    return f"👤 کارنامه‌ی {name}{username_part} — {fa_digits(bale_user_id)}"


TYPE_USAGE = "قالب: /type نوع — انواع: متن، لینک، تصویر، کلیپ، صوت، سند و..."
TAG_BROWSE_USAGE = "قالب: /tag شناسه [شماره صفحه]"

FORGET_USAGE = "قالب: /forget شناسه‌ی عددی کاربر"
FORGET_DONE = "✅ داده‌های هویتی کاربر پاک و دسترسی او مسدود شد."

DIGEST_HEADER = "📬 گزارش دوره‌ای آرشیو"

TOP_TAGS_HEADER = "🏷 پردیتاترین هشتگ‌ها:"
TOP_USERS_HEADER = "🥇 رتبه‌بندی کاربران:"


def top_tag_line(
    rank: int, title_fa: str, hashtag: str, items: int, contributors: int, share_pct: float
) -> str:
    return (
        f"{fa_digits(rank)}. {title_fa} {hashtag} — {fa_digits(items)} مورد — "
        f"{fa_digits(contributors)} نفر — {fa_digits(round(share_pct, 1))}٪"
    )


TYPE_MATRIX_HEADER = "📁 ماتریس هشتگ × نوع محتوا:"
TREND_HEADER = "📈 روند روزانه (۳۰ روز اخیر):"

ONBOARD_PINNED = "✅ پیام راهنما ارسال و پین شد."
ONBOARD_PIN_FAILED = "پیام راهنما ارسال شد ولی پین‌کردن ممکن نبود."

# ─── هشتگ‌های اولیه (seed) ───

SEED_TAGS: tuple[tuple[str, str, str], ...] = (
    # (slug, title_fa, hashtag)
    ("learning", "یادگیری", "#یادگیری"),
    ("network_source", "شبکه و منبع", "#شبکه_و_منبع"),
    ("content", "محتوایی", "#محتوایی"),
    ("document", "سند", "#سند"),
)

AUTO_TAG_FALLBACK = ("no_category", "بدون دسته", "#بدون_دسته")


def seed_tag_titles() -> str:
    return " · ".join(title for _slug, title, _hashtag in SEED_TAGS)


def seed_tag_titles_comma() -> str:
    return "، ".join(title for _slug, title, _hashtag in SEED_TAGS)


def archive_group_setup() -> str:
    names = "\n".join(f"• {title}" for _slug, title, _hashtag in SEED_TAGS)
    count = fa_digits(len(SEED_TAGS))
    return (
        f"راه‌اندازی {count} گروه آرشیو\n"
        "────────────────\n"
        "برای هر هشتگ یک گروه خصوصی دو نفره بسازید: فقط شما و ربات.\n"
        "اسم گروه را دقیقاً همین بگذارید:\n"
        "\n"
        f"{names}\n"
        "\n"
        "در هر گروه:\n"
        "۱) ربات را عضو کنید و ادمین کنید (دسترسی حذف پیام).\n"
        "۲) داخل همان گروه بنویسید /archive\n"
        "۳) در پیام خصوصی، همان هشتگ را برای آن گروه انتخاب کنید.\n"
        "\n"
        "گروه رصد جداست: ربات را آنجا هم ادمین کنید و نقش «گروه رصد» را بزنید.\n"
        "پرسش هشتگ فقط در خصوصی فرستنده است."
    )
