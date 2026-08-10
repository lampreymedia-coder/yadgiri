# رشدیار

رشدیار یک برنامه‌ریز فارسی و سبک برای رشد فردی، عبادت، تمرکز، خانواده و پیگیری پیشرفت است. این نسخه به‌صورت **PWA نصب‌پذیر** ساخته شده تا روی اندروید و دسکتاپ به‌سادگی اجرا شود.

## امکانات این نسخه

- برنامه روزانه **خودکار** بر اساس الگوهای تکرارشونده
- **هبیت‌ترکر** با ۵ لنگر ثابت و حداقل‌های شکست‌ناپذیر
- **فوکس تایمر** با صداهای محیطی داخلی
- ثبت **برنامه‌های سفارشی** با کمترین اصطکاک
- بخش **محاسبه شب** و سه اولویت فردا
- نمودار **روند رشد هفتگی**
- کاملاً **آفلاین** با ذخیره‌سازی محلی
- **نصب‌پذیر** روی موبایل و دسکتاپ

## اجرا

```bash
npm install
npm run dev
```

برای بیلد:

```bash
npm run build
```

## ساختار

- `src/data/appData.ts` داده‌های پیش‌فرض و الگوهای روزانه
- `src/store/usePlannerStore.ts` ذخیره‌سازی محلی و state اصلی
- `src/utils/ambientAudio.ts` موتور صداهای تمرکز
- `src/components/` اجزای UI

## نکته محصولی

این نسخه از روی فایل برنامه روزانه شما طراحی شده، اما عمداً انعطاف‌پذیرتر شده تا:

- مجبور نباشید هر روز همه چیز را دستی وارد کنید
- در عین حال بتوانید جلسه یا کار جدید را سریع اضافه کنید
- روند رشدتان را در هفته و روز ببینید

## ارتقاهای بعدی پیشنهادی

- تقویم ماهانه و قمری
- پیشنهاد هوشمند برنامه بر اساس روز کاری/مرخصی
- همگام‌سازی ابری
- صوت‌های بیشتر و پلی‌لیست‌های کاربر
- ویجت اندروید
# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some Oxlint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the Oxlint configuration

If you are developing a production application, we recommend enabling type-aware lint rules by installing `oxlint-tsgolint` and editing `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

See the [Oxlint rules documentation](https://oxc.rs/docs/guide/usage/linter/rules) for the full list of rules and categories.
