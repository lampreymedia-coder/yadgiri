"""All user-facing Persian texts. Bale sendMessage has no parse_mode: plain text only."""

from __future__ import annotations

from datetime import datetime

from app.mapping import POST_CONTENT_LABELS

_FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_digits(value: object) -> str:
    return str(value).translate(_FA_DIGITS)


def hashtag_label(name: str) -> str:
    """Display form of a Hashtag.name: «شبکه و منبع» → «#شبکه_و_منبع»."""
    return "#" + "_".join(name.split())


def hashtags_line(names: list[str]) -> str:
    return " ".join(hashtag_label(name) for name in names)


def content_label(code: int) -> str:
    return POST_CONTENT_LABELS.get(code, fa_digits(code))


def excerpt(body: str, limit: int = 200) -> str:
    body = (body or "").strip()
    if len(body) > limit:
        return body[:limit] + "…"
    return body


# ─── Wizard ───

BTN_SAVE_YES = "✅ بله، ذخیره شود"
BTN_SAVE_NO = "❌ خیر"
BTN_CANCEL = "انصراف"
BTN_CONTINUE = "ادامه ⬅️"
BTN_BACK = "↩️ بازگشت"
BTN_FINAL_CONFIRM = "✅ تأیید نهایی"
BTN_EDIT_TAGS = "✏️ ویرایش هشتگ‌ها"
BTN_OPEN_PRIVATE = "باز کردن گفت‌وگو با ربات"
TAG_CHECKED = "☑️"
TAG_UNCHECKED = "⬜️"


def decision_prompt(group_name: str, content_code: int, body: str) -> str:
    lines = [
        "پیام شما در گروه «" + group_name + "» رسید.",
        "نوع: " + content_label(content_code),
    ]
    short = excerpt(body)
    if short:
        lines.append("")
        lines.append(short)
    lines.append("")
    lines.append("آیا این محتوا در آرشیو ذخیره شود؟")
    return "\n".join(lines)


def tags_prompt(selected_count: int) -> str:
    return (
        "هشتگ‌های این محتوا را انتخاب کنید (یک یا چند مورد).\n"
        "انتخاب‌شده: " + fa_digits(selected_count) + "\n"
        "بعد از انتخاب، «ادامه» را بزنید."
    )


NO_ACTIVE_HASHTAGS = "فعلاً هیچ هشتگ فعالی تعریف نشده است. لطفاً به مدیر خبر دهید."
NEED_ONE_TAG = "حداقل یک هشتگ انتخاب کنید."


def preview(group_name: str, content_code: int, body: str, file_count: int, tags: list[str]) -> str:
    lines = [
        "پیش‌نمایش ثبت",
        "گروه: " + group_name,
        "نوع: " + content_label(content_code),
        "هشتگ‌ها: " + (hashtags_line(tags) or "—"),
    ]
    if file_count:
        lines.append("تعداد فایل: " + fa_digits(file_count))
    short = excerpt(body)
    if short:
        lines.append("")
        lines.append(short)
    lines.append("")
    lines.append("اگر درست است «تأیید نهایی» را بزنید.")
    return "\n".join(lines)


def saved_reply(tags: list[str]) -> str:
    return "✅ ثبت شد\n" + hashtags_line(tags)


def admin_saved_short(
    sender: str, group_name: str, content_code: int, tags: list[str], post_id: int
) -> str:
    return (
        f"• {sender} — {group_name} — {content_label(content_code)} — "
        f"{hashtags_line(tags) or '—'} — #{fa_digits(post_id)}"
    )


def admin_saved_batch(lines: list[str]) -> str:
    return (
        "🆕 " + fa_digits(len(lines)) + " ثبت جدید در چند دقیقه‌ی اخیر (اعلان تجمیعی):\n"
        + "\n".join(lines)
    )


def admin_saved(
    sender: str, group_name: str, content_code: int, tags: list[str], post_id: int
) -> str:
    return (
        "🆕 ثبت جدید\n"
        "فرستنده: " + sender + "\n"
        "گروه: " + group_name + "\n"
        "نوع: " + content_label(content_code) + "\n"
        "هشتگ‌ها: " + (hashtags_line(tags) or "—") + "\n"
        "شماره Post: " + fa_digits(post_id)
    )


SAVE_FAILED = "متأسفانه ثبت انجام نشد. پیام شما سر جایش هست؛ کمی بعد دوباره بفرستید."
TYPE_NOT_ALLOWED = "این نوع فایل فعلاً قابل ثبت نیست."
PERSON_INACTIVE = "حساب شما در آرشیو غیرفعال است و فعلاً ثبت از طرف شما پذیرفته نمی‌شود."
GROUP_NOT_ACTIVE = "این گروه دیگر در آرشیو فعال نیست."
ERR_EXPIRED = "این پرسش منقضی شده است."
ERR_NOT_YOURS = "این پرسش مربوط به شما نیست."
ERR_SPAM_LIMIT = "تعداد ارسال‌های شما در این ساعت زیاد است. کمی بعد دوباره امتحان کنید."
REMINDER = "⏳ یادآوری: پرسش ثبت این محتوا هنوز منتظر پاسخ شماست."


def dm_hint(bot_username: str) -> str:
    return (
        "برای ثبت این پیام در آرشیو، یک بار ربات را در پیام خصوصی باز کنید و «شروع» را بزنید: @"
        + bot_username
    )


def admin_check_alert(group_name: str, content_code: int, user_label: str) -> str:
    return (
        "⚠️ هشدار: ثبت یک محتوا به خاطر قید نوع محتوا (CHECK) در دیتابیس رد شد.\n"
        "گروه: " + group_name + "\n"
        "نوع: " + content_label(content_code) + " (کد " + fa_digits(content_code) + ")\n"
        "فرستنده: " + user_label + "\n"
        "احتمالاً دستورهای بخش ۵-۱۱ هنوز روی سرور اجرا نشده‌اند (python scripts/preflight.py)."
    )


# ─── Group registration ───

REGISTER_PICK_LEVEL = "سطح این گروه را انتخاب کنید (۱ تا ۷):"
REGISTER_ONLY_ADMIN = "فقط مدیر ربات می‌تواند این کار را انجام دهد."
REGISTER_ARCHIVE_REFUSED = "این گروه، گروه آرشیو است و ثبت نمی‌شود."
REGISTER_IN_GROUP_ONLY = "این دستور را داخل همان گروه بزنید."
UNREGISTER_NOT_FOUND = "این گروه ثبت نشده یا از قبل غیرفعال است."


def register_done(name: str, level: int) -> str:
    return (
        "✅ گروه «"
        + name
        + "» با سطح "
        + fa_digits(level)
        + " ثبت شد. از این به بعد ربات اینجا فعال است."
    )


def unregister_done(name: str) -> str:
    return "گروه «" + name + "» غیرفعال شد. ربات دیگر در این گروه کاری انجام نمی‌دهد."


# ─── Private commands ───

START = (
    "سلام! من ربات آرشیو هستم.\n"
    "وقتی در یکی از گروه‌های ثبت‌شده پیامی بفرستید، همین‌جا از شما می‌پرسم آیا در آرشیو "
    "ذخیره شود و زیر کدام هشتگ‌ها.\n"
    "تا وقتی «تأیید نهایی» را نزنید، هیچ چیزی ذخیره نمی‌شود."
)

HELP = (
    "راهنما\n"
    "۱. در گروه ثبت‌شده پیام، عکس، صوت، ویدیو یا فایل بفرستید.\n"
    "۲. در پیام خصوصی ربات «بله، ذخیره شود» را بزنید.\n"
    "۳. هشتگ‌ها را انتخاب کنید و «ادامه» را بزنید.\n"
    "۴. در پیش‌نمایش «تأیید نهایی» را بزنید.\n"
    "«خیر» یا «انصراف» یعنی هیچ چیزی ذخیره نشود.\n\n"
    "دستورها: /start /help /id /tags"
)

ADMIN_HELP = (
    "دستورهای مدیر\n"
    "/register — داخل گروه: ثبت گروه (با انتخاب سطح)\n"
    "/unregister — داخل گروه: غیرفعال کردن گروه\n"
    "/groups — فهرست گروه‌ها\n"
    "/stats — گزارش آرشیو\n"
    "/admins — فهرست مدیران\n"
    "/panel — پنل مدیر با دکمه\n"
    "/addadmin <شناسه عددی> — افزودن مدیر (فقط مالک)\n"
    "/removeadmin <شناسه عددی> — حذف مدیر (فقط مالک)\n"
    "/transferowner <شناسه عددی> — انتقال مالکیت (فقط مالک)"
)

UNKNOWN_COMMAND = "این دستور را نمی‌شناسم. /help را بزنید."
PRIVATE_ONLY = "این دستور را در پیام خصوصی ربات بزنید."


def your_id(user_id: int) -> str:
    return "شناسه عددی شما در بله: " + str(user_id)


def tags_list(names: list[str]) -> str:
    if not names:
        return NO_ACTIVE_HASHTAGS
    return "هشتگ‌های فعال:\n" + "\n".join(hashtag_label(name) for name in names)


def groups_list(rows: list[tuple[str, int, int, bool]]) -> str:
    """rows: (name, bale_group_id, level, is_active)."""
    if not rows:
        return "هیچ گروهی ثبت نشده است. داخل گروه /register را بزنید."
    lines = ["گروه‌های ثبت‌شده:"]
    for name, gid, level, active in rows:
        status = "فعال" if active else "غیرفعال"
        lines.append(f"• {name} — سطح {fa_digits(level)} — {status} — {gid}")
    return "\n".join(lines)


def admins_list(ids: list[int], env_ids: set[int]) -> str:
    lines = ["مدیران ربات:"]
    for admin_id in ids:
        suffix = " (از فایل .env، دائمی)" if admin_id in env_ids else ""
        lines.append(f"• {admin_id}{suffix}")
    return "\n".join(lines)


ADMIN_USAGE_ADD = "روش استفاده: /addadmin 123456789"
ADMIN_USAGE_REMOVE = "روش استفاده: /removeadmin 123456789"


def admin_added(user_id: int) -> str:
    return f"✅ {user_id} مدیر شد."


def admin_already(user_id: int) -> str:
    return f"{user_id} از قبل مدیر است."


def admin_removed(user_id: int) -> str:
    return f"{user_id} دیگر مدیر نیست."


def admin_not_found(user_id: int) -> str:
    return f"{user_id} مدیر نیست."


def admin_from_env(user_id: int) -> str:
    return f"{user_id} در فایل .env (ADMIN_USER_IDS) آمده و با این دستور حذف نمی‌شود."


ADMIN_LAST = "حداقل یک مدیر باید باقی بماند."
ADMIN_IS_OWNER = "مالک را نمی‌شود حذف کرد. اول مالکیت را منتقل کنید."
OWNER_ONLY = "فقط مالک ربات می‌تواند مدیران را اضافه یا حذف کند یا مالکیت را منتقل کند."
OWNER_ALREADY = "شما همین حالا مالک هستید."
OWNER_USAGE = "روش استفاده: /transferowner 123456789"
ASK_ADMIN_ID = "شناسه‌ی عددی مدیر جدید را بفرستید. (هر کس می‌تواند شناسه‌اش را با /id در پیوی ربات ببیند.)"
ASK_ADMIN_FORWARD = "یک پیام از مدیر جدید را همین‌جا فوروارد کنید."
FORWARD_HAS_NO_USER = "این پیام فوروارد، شناسه‌ی فرستنده را ندارد (احتمالاً به خاطر تنظیمات حریم خصوصی). از «افزودن با شناسه» استفاده کنید."
PICK_PERSON = "یک نفر را از افراد ثبت‌شده انتخاب کنید:"
NO_PEOPLE = "فرد دیگری در جدول Person نیست."
PICK_NEW_OWNER = "مالک جدید را انتخاب کنید (فقط از بین مدیران فعلی):"
BTN_YES_TRANSFER = "✅ بله، منتقل شود"
BTN_ADMIN_ADD_ID = "➕ افزودن با شناسه"
BTN_ADMIN_ADD_FWD = "➕ افزودن با فوروارد پیام"
BTN_ADMIN_ADD_PICK = "➕ انتخاب از افراد"
BTN_OWNER_TRANSFER = "👑 انتقال مالکیت"
BTN_PANEL_ADMINS = "👥 مدیران"
BTN_PANEL_BACK = "↩️ بازگشت"
PANEL_HOME = "🛠 پنل مدیر\nیکی از بخش‌ها را انتخاب کنید."


def btn_admin_remove(user_id: int) -> str:
    return f"❌ حذف {user_id}"


def confirm_transfer(user_id: int) -> str:
    return f"مالکیت ربات به {user_id} منتقل شود؟ شما مدیر باقی می‌مانید."


def owner_transferred(user_id: int) -> str:
    return f"👑 مالکیت به {user_id} منتقل شد."


def admins_panel(ids: list[int], owner: int | None, env_ids: set[int]) -> str:
    lines = ["👥 مدیران ربات:"]
    for admin_id in ids:
        tags = []
        if admin_id == owner:
            tags.append("👑 مالک")
        if admin_id in env_ids:
            tags.append("از .env")
        suffix = f" ({'، '.join(tags)})" if tags else ""
        lines.append(f"• {admin_id}{suffix}")
    return "\n".join(lines)


_BLOCKS = "█▉▊▋▌▍▎▏"


def text_bar(share: float, width: int = 10) -> str:
    """Text bar like ████▌░░░░░ for a share between 0 and 1."""
    share = max(0.0, min(1.0, share))
    eighths = round(share * width * 8)
    full, remainder = divmod(eighths, 8)
    bar = _BLOCKS[0] * full + (_BLOCKS[8 - remainder] if remainder else "")
    return bar + "░" * (width - full - (1 if remainder else 0))


def jalali(value: object, with_time: bool = False) -> str:
    """Shamsi date (and time) for a datetime/date, in Persian digits."""
    import jdatetime

    if value is None:
        return ""
    if with_time:
        converted = jdatetime.datetime.fromgregorian(datetime=value)
        return fa_digits(converted.strftime("%Y/%m/%d %H:%M"))
    day = value.date() if isinstance(value, datetime) else value
    return fa_digits(jdatetime.date.fromgregorian(date=day).strftime("%Y/%m/%d"))


def bar_lines(items: list[tuple[str, int]]) -> list[str]:
    top = max((count for _, count in items), default=0)
    return [
        f"{name}\n{text_bar(count / top if top else 0)} {fa_digits(count)}" for name, count in items
    ]


def daily_digest(now: object, report: object) -> str:
    from app.domain.reports import Report

    assert isinstance(report, Report)
    lines = [
        "📅 گزارش روزانه — " + jalali(now),
        "ثبت‌های امروز: " + fa_digits(report.total_posts),
    ]
    if report.total_posts:
        lines += ["", "هشتگ‌ها:"] + bar_lines(
            [(hashtag_label(name), count) for name, count in report.by_hashtag]
        )
        lines += ["", "نوع محتوا:"] + [
            f"{content_label(code)}: {fa_digits(count)}" for code, count in report.by_content_type
        ]
        lines += ["", "فعال‌ترین‌ها:"] + [
            f"{fa_digits(i)}. {name} — {fa_digits(count)}"
            for i, (name, count) in enumerate(report.top_users, start=1)
        ]
    return "\n".join(lines)


def report_text(report: object) -> str:
    from app.domain.reports import Report

    assert isinstance(report, Report)
    lines = [
        "📊 گزارش آرشیو",
        "کل ثبت‌ها: " + fa_digits(report.total_posts),
        "ثبت‌های امروز: " + fa_digits(report.today_posts),
        "",
        "پرکارترین کاربران:",
    ]
    if report.top_users:
        for index, (name, count) in enumerate(report.top_users, start=1):
            lines.append(f"{fa_digits(index)}. {name} — {fa_digits(count)}")
    else:
        lines.append("—")
    top = report.top_hashtag
    lines.append("")
    lines.append(
        "پردیتاترین هشتگ: " + (f"{hashtag_label(top[0])} ({fa_digits(top[1])})" if top else "—")
    )
    lines.append("")
    lines.append("به تفکیک هشتگ:")
    for name, count in report.by_hashtag:
        lines.append(f"{hashtag_label(name)}: {fa_digits(count)}")
    lines.append("")
    lines.append("به تفکیک نوع محتوا:")
    if report.by_content_type:
        for code, count in report.by_content_type:
            lines.append(f"{content_label(code)}: {fa_digits(count)}")
    else:
        lines.append("—")
    lines.append("")
    lines.append("به تفکیک گروه:")
    if report.by_group:
        for name, count in report.by_group:
            lines.append(f"{name}: {fa_digits(count)}")
    else:
        lines.append("—")
    return "\n".join(lines)


def archive_footer(sender: str, group_name: str, tags: list[str], post_id: int) -> str:
    return (
        "فرستنده: " + sender + "\n"
        "گروه: " + group_name + "\n" + hashtags_line(tags) + "\n"
        "شماره ثبت: " + fa_digits(post_id)
    )


BOT_COMMANDS = [
    {"command": "start", "description": "شروع"},
    {"command": "help", "description": "راهنما"},
    {"command": "id", "description": "شناسه عددی من"},
    {"command": "tags", "description": "هشتگ‌های فعال"},
]
