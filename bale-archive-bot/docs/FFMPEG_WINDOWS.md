# نصب ffmpeg روی ویندوز سرور (برای فشرده‌سازی ویدیو)

ربات بعد از دانلود ویدیو، اگر `ffmpeg` روی PATH باشد، نسخهٔ فشرده
می‌سازد (`VIDEO_COMPRESSION_ENABLED=true`). اگر ffmpeg نباشد، فایل اصلی
نگه داشته می‌شود و فقط در لاگ می‌نویسد — ربات از کار نمی‌افتد.

## نصب پیشنهادی (بدون نیاز به کامپایل)

### روش ۱ — دانلود رسمی build ویندوز

1. از یکی از buildهای پایدار ویندوز (مثلاً gyan.dev یا BtbN) فایل
   **ffmpeg-release-essentials.zip** را بگیرید.
2. ZIP را در مسیری ثابت باز کنید، مثلاً:
   `C:\Tools\ffmpeg\`
3. داخل پوشه باید `bin\ffmpeg.exe` باشد.
4. `C:\Tools\ffmpeg\bin` را به **System PATH** اضافه کنید:
   - Settings → System → About → Advanced system settings → Environment Variables
   - در System variables → Path → Edit → New → همان مسیر `bin`
5. یک **Command Prompt جدید** باز کنید و بزنید:

```bat
ffmpeg -version
```

باید نسخه چاپ شود. اگر گفت unrecognized، PATH درست نیست یا پنجره را
بعد از تغییر PATH نبسته و دوباره باز نکرده‌اید.

6. سرویس ربات (NSSM / Task Scheduler) را **یک‌بار Restart** کنید تا
   همان PATH جدید را ببیند.

### روش ۲ — winget (ویندوز ۱۰/۱۱ با App Installer)

```bat
winget install --id Gyan.FFmpeg -e
```

بعد از نصب، ترمینال را ببندید و دوباره `ffmpeg -version` را چک کنید،
سپس سرویس ربات را Restart کنید.

## تنظیمات `.env` مربوط

```
VIDEO_COMPRESSION_ENABLED=true
VIDEO_CRF=24
VIDEO_MAX_HEIGHT=720
VIDEO_AUDIO_BITRATE=96k
KEEP_ORIGINAL_VIDEO=false
```

- CRF بالاتر = حجم کمتر / کیفیت کمتر (۲۴ پیش‌فرض متعادل است).
- ارتفاع بیشتر از اصل بزرگ نمی‌شود (`min(720, ih)`).
- اگر نتیجه از اصل بزرگ‌تر باشد یا کمتر از ۱۵٪ صرفه‌جویی کند، اصل نگه
  داشته می‌شود.
- فشرده‌سازی فقط در worker پس‌زمینه است؛ ویزارد کاربر را معطل نمی‌کند.

## مهاجرت دیتابیس

ستون‌های حجم/فشرده‌سازی با Alembic اضافه می‌شوند:

```bat
alembic upgrade head
```

باید تا revision `0002` جلو برود.

## بررسی

در پی‌وی ادمین:

```
/disk
```

فضای آزاد، حجم ذخیره‌شده، صرفه‌جویی فشرده‌سازی و حذف تکراری را نشان می‌دهد.
