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


def decision_prompt(name: str, content_type: str, group_title: str, dt: datetime) -> str:
    return (
        f"سلام {name}\n"
        "\n"
        f"یک {content_type_name(content_type)} از شما در گروه «{group_title}» ثبت شد.\n"
        f"{jalali_date(dt)}  {jalali_time(dt)}\n"
        "\n"
        "این محتوا باید با هشتگ در آرشیو ذخیره شود؟"
    )


BTN_SAVE_YES = "بله، انتخاب هشتگ"
BTN_SAVE_NO = "خیر، فقط در گروه بماند"
BTN_CANCEL_DELETE = "انصراف"

# ─── گام ۲: تعداد هشتگ ───

TAG_COUNT_PROMPT = (
    "این محتوا در چند هشتگ ذخیره شود؟\n"
    "\n"
    "می‌توانید یک، دو یا هر سه هشتگ را انتخاب کنید. محتوا همزمان در چند هشتگ قابل بایگانی است."
)

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


def tag_select_prompt(selected: int, target: int | None) -> str:
    if target is None:
        chosen = f"انتخاب‌شده: {fa_digits(selected)}"
    else:
        chosen = f"انتخاب‌شده: {fa_digits(selected)} از {fa_digits(target)}"
    return (
        "در کدام هشتگ قرار بگیرد؟\n"
        "برای انتخاب چندتایی، هشتگ‌ها را یکی‌یکی بزنید. دوباره زدن، انتخاب را برمی‌دارد.\n"
        f"\n{chosen}"
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
) -> str:
    username_part = f" (@{username})" if username else ""
    return (
        "پیش‌نمایش ثبت\n"
        "\n"
        f"فرستنده: {sender_name}{username_part}\n"
        f"گروه: {group_title}\n"
        f"نوع: {content_type_name(content_type)} {details}\n"
        f"حجم: {size_text}\n"
        f"هشتگ‌ها: {hashtags}\n"
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


USER_SAVED = "اطلاعات شما با موفقیت ذخیره شد."


def success_message(short_id: str, hashtags: str, group_title: str, undo_minutes: int) -> str:
    del short_id, hashtags, group_title, undo_minutes
    return USER_SAVED


def published_header(sender_name: str, hashtags: str) -> str:
    return f"{sender_name}\n{hashtags}"


def archive_footer(sender_name: str, hashtags: str, content_type: str, short_id: str) -> str:
    return f"{hashtags}\n{sender_name}  ·  {content_type_name(content_type)}\n{short_id}"


def republished_header(sender_name: str) -> str:
    return sender_name


DECLINED_MESSAGE = "ثبت شد. پیام شما در گروه می‌ماند و در آرشیو ذخیره نشد."
CANCELLED_MESSAGE = "ثبت لغو شد. پیام شما در گروه باقی است."

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
        missing_line = "\nگروه آرشیو ناقص: " + " ".join(missing)
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
        "برای راه‌اندازی:\n"
        "\n"
        "۱) ربات را به گروه‌های رصد اضافه کنید و ادمین کنید. "
        "دسترسی «حذف پیام» لازم است تا پیام‌های ربات از گروه پاک شود.\n"
        "\n"
        "۲) برای هر هشتگ یک گروه خصوصی آرشیو بسازید (فقط شما و ربات). "
        "ربات را ادمین کنید، داخل همان گروه /archive بزنید و هشتگ را انتخاب کنید.\n"
        "هشتگ‌های فعلی: یادگیری · شبکه و منبع · محتوایی\n"
        "\n"
        "۳) پرسش هشتگ فقط در پیام خصوصی فرستنده است؛ گروه شلوغ نمی‌شود.\n"
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
        "رصد: اعضا محتوا می‌فرستند و هشتگ در پیام خصوصی انتخاب می‌شود.\n"
        "آرشیو: فقط محل نگهداری یک هشتگ است. برای هر هشتگ یک گروه جدا بسازید."
    )


GROUP_HELLO = "ربات در این گروه فعال است. نقش گروه را در پیام خصوصی مشخص کنید."

GROUP_GOT_IT = "این پیام برای بایگانی مناسب نیست. متن، عکس، فایل، صوت یا کلیپ بفرستید."

BOT_READY_PING = "ربات روشن است.\nهمین‌جا پیام بفرستید، یا ربات را به گروه اضافه کنید."

BTN_ADD_TO_GROUP = "افزودن ربات به گروه"


BTN_GROUP_IS_RESEARCH = "گروه رصد"
BTN_GROUP_IS_ARCHIVE = "گروه آرشیو هشتگ"


def archive_tag_prompt(group_title: str) -> str:
    return f"گروه «{group_title}» آرشیو کدام هشتگ باشد؟\n\nبرای هر هشتگ باید یک گروه جدا ساخته شود."


def archive_set_done(group_title: str, hashtag: str) -> str:
    return f"گروه «{group_title}» به‌عنوان آرشیو {hashtag} ثبت شد."


def research_set_done(group_title: str) -> str:
    return (
        f"گروه «{group_title}» به‌عنوان گروه رصد ثبت شد.\n"
        "از این به بعد پرسش هشتگ فقط در پیام خصوصی فرستنده است."
    )


ARCHIVE_SET_DONE = "این گروه به‌عنوان آرشیو خصوصی ثبت شد."
ARCHIVE_SET_NEED_PRIVATE = (
    "اول در پیام خصوصی ربات /start را بزنید تا مدیر شوید، بعد دوباره /archive را بفرستید."
)
RESEARCH_GROUP_READY = (
    "این گروه به‌عنوان گروه رصد ثبت شد.\nپرسش هشتگ از فرستنده در پیام خصوصی انجام می‌شود."
)
ALREADY_OWNER = "شما از قبل مدیر ربات هستید."


HELP_MESSAGE = (
    "راهنمای ربات آرشیو\n"
    "────────────────\n"
    "۱. محتوا را در گروه رصد بفرستید؛ همان‌جا می‌ماند.\n"
    "۲. ربات در پیام خصوصی می‌پرسد در کدام هشتگ ذخیره شود.\n"
    "۳. می‌توانید یک یا چند هشتگ را با هم انتخاب کنید.\n"
    "۴. با دکمه بازگشت، مرحله قبل را اصلاح کنید.\n"
    "۵. پس از تأیید، داده در دیتابیس و گروه آرشیو همان هشتگ ذخیره می‌شود.\n"
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
    "awaiting_tag_count": "در انتظار تعداد هشتگ",
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
    # (slug, title_fa, hashtag) — فقط سه هشتگ اولیه؛ بقیه از پنل اضافه می‌شود.
    ("learning", "یادگیری", "#یادگیری"),
    ("network_source", "شبکه و منبع", "#شبکه_و_منبع"),
    ("content", "محتوایی", "#محتوایی"),
)

AUTO_TAG_FALLBACK = ("no_category", "بدون دسته", "#بدون_دسته")
