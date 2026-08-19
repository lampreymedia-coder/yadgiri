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
        f"سلام {name} 👋\n"
        "\n"
        f"یک {content_type_name(content_type)} از شما در گروه «{group_title}» دریافت شد.\n"
        f"🕐 {jalali_date(dt)} — {jalali_time(dt)}\n"
        "\n"
        "آیا این محتوا نیاز به هشتگ‌گذاری و ذخیره‌سازی در آرشیو دارد؟"
    )


BTN_SAVE_YES = "✅ بله، ذخیره شود"
BTN_SAVE_NO = "❌ خیر، فقط در گروه منتشر شود"
BTN_CANCEL_DELETE = "🗑 انصراف و حذف کامل"

# ─── گام ۲: تعداد هشتگ ───

TAG_COUNT_PROMPT = (
    "📊 می‌خواهید این محتوا زیر چند هشتگ ذخیره شود؟\n"
    "\n"
    "می‌توانید یک یا چند هشتگ را انتخاب کنید."
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
    return f"🏷 هشتگ‌های مورد نظر را انتخاب کنید.\n\n{chosen}"


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
        "📋 پیش‌نمایش اطلاعاتی که ثبت می‌شود\n"
        "\n"
        f"👤 فرستنده: {sender_name}{username_part}\n"
        f"👥 گروه: {group_title}\n"
        f"📁 نوع محتوا: {content_type_name(content_type)} {details}\n"
        f"📦 حجم: {size_text}\n"
        f"🏷 هشتگ‌ها: {hashtags}\n"
        f"📝 متن/توضیح: «{excerpt}»\n"
        f"🕐 زمان: {jalali_date(dt)} — {jalali_time(dt)}\n"
        f"🔖 کد رهگیری: {short_id}\n"
        "\n"
        "آیا اطلاعات بالا درست است؟"
    )


BTN_FINAL_CONFIRM = "✅ تایید نهایی و ذخیره"
BTN_EDIT_TAGS = "🏷 اصلاح هشتگ‌ها"
BTN_EDIT_NOTE = "📝 افزودن/ویرایش توضیح"
BTN_BACK_TO_PREV = "⬅️ بازگشت به مرحله‌ی قبل"
BTN_CANCEL = "❌ انصراف"

NOTE_PROMPT = "📝 توضیح خود را در یک پیام بفرستید. برای انصراف، دکمه‌ی بازگشت را بزنید."

# ─── گام ۵: موفقیت ───


def success_message(short_id: str, hashtags: str, group_title: str, undo_minutes: int) -> str:
    return (
        "✅ اطلاعات شما با موفقیت ذخیره شد.\n"
        "\n"
        f"🔖 کد رهگیری: {short_id}\n"
        f"🏷 هشتگ‌ها: {hashtags}\n"
        f"📍 محل ذخیره: آرشیو گروه «{group_title}»\n"
        "\n"
        "محتوای شما در گروه منتشر شد.\n"
        f"تا {fa_digits(undo_minutes)} دقیقه می‌توانید با دستور /undo {short_id} ثبت را لغو کنید."
    )


def published_header(sender_name: str, hashtags: str) -> str:
    return f"📌 {sender_name}\n{hashtags}"


def republished_header(sender_name: str) -> str:
    return f"📎 {sender_name}"


DECLINED_MESSAGE = "باشه ✅ محتوای شما بدون هشتگ در گروه منتشر شد."
CANCELLED_MESSAGE = "🗑 ثبت لغو شد و محتوا حذف شد."

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
) -> str:
    return (
        "🆕 داده‌ی جدید ثبت شد\n"
        "\n"
        f"👤 کاربر: {name} ({fa_digits(bale_user_id)})\n"
        f"👥 گروه: {group_title}\n"
        f"📁 نوع: {content_type_name(content_type)} {details}\n"
        f"🏷 هشتگ: {hashtags}\n"
        f"🔖 کد: {short_id}\n"
        f"🕐 {jalali_date(dt)} — {jalali_time(dt)}\n"
        "\n"
        f"📊 مجموع امروز: {fa_digits(today_total)} مورد"
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
    return (
        "🚨 خطای مدیریت‌نشده در ربات\n"
        "\n"
        f"نوع خطا: {error_kind}\n"
        "جزئیات در لاگ سیستم ثبت شده است."
    )


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
    return "⌛️ مهلت هشتگ‌گذاری تمام شد.\n" f"محتوای {short_id} بدون هشتگ در گروه منتشر شد."


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
    return (
        "برای تجربه‌ی بهتر، یک بار ربات را استارت کنید تا گفت‌وگو در پیام خصوصی انجام شود:\n"
        f"@{bot_username}"
    )


def onboard_message(bot_username: str) -> str:
    return (
        "📢 راهنمای آرشیو گروه\n"
        "────────────────\n"
        "هر محتوایی که در این گروه بفرستید، ربات از شما می‌پرسد که آیا باید "
        "با هشتگ در آرشیو ذخیره شود یا نه.\n"
        "\n"
        f"برای شروع، یک بار ربات @{bot_username} را استارت کنید."
    )


# ─── دستورهای کاربر ───


def start_message(name: str) -> str:
    return (
        f"سلام {name} 👋\n"
        "\n"
        "من ربات آرشیو گروه هستم. هر محتوایی که در گروه بفرستید، از شما می‌پرسم "
        "که آیا باید با هشتگ ذخیره شود یا نه.\n"
        "\n"
        "دستورهای شما:\n"
        "/my — آخرین ثبت‌های شما\n"
        "/undo کد — لغو ثبت تا چند دقیقه پس از ثبت\n"
        "/resume — بازسازی گفت‌وگوی نیمه‌کاره\n"
        "/help — راهنما"
    )


HELP_MESSAGE = (
    "📖 راهنمای ربات آرشیو\n"
    "────────────────\n"
    "۱. محتوای خود را در گروه بفرستید.\n"
    "۲. ربات در پیام خصوصی از شما می‌پرسد که ذخیره شود یا نه.\n"
    "۳. اگر بله، هشتگ‌ها را انتخاب و تایید کنید.\n"
    "۴. محتوا با هشتگ در گروه منتشر و در آرشیو ذخیره می‌شود.\n"
    "\n"
    "دستورها:\n"
    "/my — آخرین ثبت‌های شما\n"
    "/undo کد — لغو ثبت\n"
    "/resume — ادامه‌ی گفت‌وگوی نیمه‌کاره\n"
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
    return (
        "🏷 پیش‌نمایش هشتگ جدید\n"
        "\n"
        f"عنوان: {title_fa}\n"
        f"هشتگ: {hashtag}\n"
        f"شناسه: {slug}\n"
        "\n"
        "ثبت شود؟"
    )


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


def group_line(title: str | None, bale_chat_id: int, is_active: bool, can_delete: bool) -> str:
    status = "فعال" if is_active else "غیرفعال"
    delete_perm = "✅ حذف دارد" if can_delete else "⚠️ حذف ندارد"
    return f"• {title or 'بدون عنوان'} ({fa_digits(bale_chat_id)}) — {status} — {delete_perm}"


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
