import type { Pillar } from '../lib/store';

/**
 * قالب‌های روز — برگرفته از «روزشمار ۲.۰» (فایل پیکربندی seed)
 * زمان‌ها آفست نسبت به لنگرند (اذان/طلوع/خواب)، نه ساعت ثابت.
 */

export type AnchorCode =
  | 'fajr'
  | 'sunrise'
  | 'dhuhr'
  | 'asr'
  | 'maghrib'
  | 'isha'
  | 'wake'
  | 'sleep'
  | `clock:${string}`;

export interface BlockDef {
  title: string;
  anchor: AnchorCode;
  offset: number; // دقیقه
  duration: number; // دقیقه
  pillar: Pillar;
  isCore?: boolean;
  isDeep?: boolean;
}

export interface DayTemplate {
  code: string;
  title: string;
  mission: string;
  blocks: BlockDef[];
}

/** روزهای کاری با getDay(): شنبه=۶، یکشنبه=۰، سه‌شنبه=۲ */
export const WORK_DAYS = [6, 0, 2];

export const SLEEP_TIME_WORK = 21 * 60 + 30; // ۲۱:۳۰
export const SLEEP_TIME_HOME = 22 * 60; // ۲۲:۰۰
export const WAKE_OFFSET_WORK = -45;
export const WAKE_OFFSET_HOME = -60;

const WORK: DayTemplate = {
  code: 'WORK',
  title: 'روز کاری',
  mission: 'اتقان در کار؛ حداقلِ محکم در بقیه',
  blocks: [
    { title: 'بیداری، وضو و نماز شب', anchor: 'fajr', offset: -45, duration: 40, pillar: 'worship', isCore: true },
    { title: 'نماز صبح اول وقت + تسبیح حضرت زهرا(س)', anchor: 'fajr', offset: 0, duration: 20, pillar: 'worship', isCore: true },
    { title: 'یک صفحه قرآن با ترجمه', anchor: 'fajr', offset: 20, duration: 15, pillar: 'knowledge', isCore: true },
    { title: 'صبحانه، آماده‌شدن و حرکت (در مسیر: ذکر یا کتاب صوتی)', anchor: 'fajr', offset: 40, duration: 40, pillar: 'order' },
    { title: 'کار با نیت عبادت و اتقان', anchor: 'clock:06:00', offset: 0, duration: 540, pillar: 'order', isCore: true, isDeep: true },
    { title: 'نماز ظهر و عصر اول وقت + ۵ دقیقه سکوت', anchor: 'dhuhr', offset: 0, duration: 25, pillar: 'worship', isCore: true },
    { title: 'بازگشت و ناهار', anchor: 'clock:15:00', offset: 0, duration: 45, pillar: 'body' },
    { title: 'چرت کوتاه (۲۰ تا ۴۰ دقیقه)', anchor: 'clock:16:00', offset: 0, duration: 35, pillar: 'body', isCore: true },
    { title: 'وقت با فرزند + کارهای خانه و شام', anchor: 'clock:16:45', offset: 0, duration: 60, pillar: 'people' },
    { title: 'نماز مغرب و عشا اول وقت؛ شام سبک', anchor: 'maghrib', offset: 0, duration: 60, pillar: 'worship', isCore: true },
    { title: 'مطالعه‌ی کتاب ماه', anchor: 'sleep', offset: -105, duration: 45, pillar: 'knowledge' },
    { title: 'خاموشی صفحه‌نمایش', anchor: 'sleep', offset: -60, duration: 5, pillar: 'body' },
    { title: 'مرور روز + سه کار فردا', anchor: 'sleep', offset: -30, duration: 15, pillar: 'order', isCore: true },
  ],
};

const HOME_BODY: DayTemplate = {
  code: 'HOME_BODY',
  title: 'روز خانه — بدن',
  mission: 'ورزش اصلی هفته + کارهای معوق',
  blocks: [
    { title: 'بیداری، وضو و نماز شب باحوصله', anchor: 'fajr', offset: -60, duration: 55, pillar: 'worship', isCore: true },
    { title: 'نماز صبح اول وقت + تسبیح حضرت زهرا(س)', anchor: 'fajr', offset: 0, duration: 20, pillar: 'worship', isCore: true },
    { title: 'بین‌الطلوعین: قرآن + دعای عهد', anchor: 'fajr', offset: 25, duration: 30, pillar: 'knowledge', isCore: true },
    { title: 'صبحانه + رسیدگی سبک به خانه', anchor: 'sunrise', offset: 20, duration: 60, pillar: 'order' },
    { title: 'ورزش اصلی هفته (گرم‌کردن، قدرتی/هوازی، کشش)', anchor: 'sunrise', offset: 80, duration: 90, pillar: 'body', isDeep: true },
    { title: 'دوش و استراحت کوتاه', anchor: 'sunrise', offset: 175, duration: 15, pillar: 'body' },
    { title: 'دوره‌ی آموزشی با تمرکز + یادداشت', anchor: 'sunrise', offset: 195, duration: 90, pillar: 'knowledge', isDeep: true },
    { title: 'آشپزی ناهار به نیت اطعام', anchor: 'dhuhr', offset: -70, duration: 60, pillar: 'people' },
    { title: 'نماز ظهر و عصر اول وقت؛ ناهار', anchor: 'dhuhr', offset: 0, duration: 60, pillar: 'worship', isCore: true },
    { title: 'چرت نیم‌روزی', anchor: 'dhuhr', offset: 75, duration: 40, pillar: 'body' },
    { title: 'کارهای شخصی و معوق هفته + جبران عقب‌افتاده‌ها', anchor: 'dhuhr', offset: 130, duration: 150, pillar: 'order' },
    { title: 'نماز مغرب و عشا اول وقت؛ شام', anchor: 'maghrib', offset: 0, duration: 60, pillar: 'worship', isCore: true },
    { title: 'مطالعه‌ی کتاب ماه (بلوک بلند)', anchor: 'sleep', offset: -120, duration: 60, pillar: 'knowledge', isDeep: true },
    { title: 'مرور روز + سه کار فردا', anchor: 'sleep', offset: -30, duration: 15, pillar: 'order', isCore: true },
  ],
};

const HOME_MIND: DayTemplate = {
  code: 'HOME_MIND',
  title: 'روز خانه — کار فکری',
  mission: 'کار فکری عمیق: مطالعه و نوشتن',
  blocks: [
    { title: 'بیداری، وضو و نماز شب باحوصله', anchor: 'fajr', offset: -60, duration: 55, pillar: 'worship', isCore: true },
    { title: 'نماز صبح اول وقت + تسبیح حضرت زهرا(س)', anchor: 'fajr', offset: 0, duration: 20, pillar: 'worship', isCore: true },
    { title: 'بین‌الطلوعین: قرآن + دعای عهد', anchor: 'fajr', offset: 25, duration: 30, pillar: 'knowledge', isCore: true },
    { title: 'صبحانه + رسیدگی سبک به خانه', anchor: 'sunrise', offset: 20, duration: 60, pillar: 'order' },
    { title: 'پیاده‌روی سبک ۲۰ دقیقه', anchor: 'sunrise', offset: 80, duration: 20, pillar: 'body' },
    { title: 'کار فکری عمیق: مطالعه یا نوشتن', anchor: 'sunrise', offset: 110, duration: 105, pillar: 'knowledge', isDeep: true },
    { title: 'آشپزی ناهار', anchor: 'dhuhr', offset: -70, duration: 60, pillar: 'people' },
    { title: 'نماز ظهر و عصر اول وقت؛ ناهار', anchor: 'dhuhr', offset: 0, duration: 60, pillar: 'worship', isCore: true },
    { title: 'چرت نیم‌روزی', anchor: 'dhuhr', offset: 75, duration: 40, pillar: 'body' },
    { title: 'صله‌رحم: یک دیدار یا تماس معنادار', anchor: 'dhuhr', offset: 130, duration: 90, pillar: 'people' },
    { title: 'نماز مغرب و عشا اول وقت؛ شام', anchor: 'maghrib', offset: 0, duration: 60, pillar: 'worship', isCore: true },
    { title: 'دعای کمیل + زیارت وارث', anchor: 'maghrib', offset: 75, duration: 60, pillar: 'worship' },
    { title: 'مرور روز + سه کار فردا', anchor: 'sleep', offset: -30, duration: 15, pillar: 'order', isCore: true },
  ],
};

const THU: DayTemplate = {
  code: 'THU',
  title: 'پنجشنبه — خانواده و بازنگری',
  mission: 'سفره‌داری، خانواده، بازنگری هفتگی',
  blocks: [
    { title: 'بیداری و نماز شب', anchor: 'fajr', offset: -60, duration: 55, pillar: 'worship', isCore: true },
    { title: 'نماز صبح اول وقت + تعقیبات', anchor: 'fajr', offset: 0, duration: 25, pillar: 'worship', isCore: true },
    { title: 'دوره‌ی آموزشی یا مطالعه‌ی عمیق', anchor: 'sunrise', offset: 60, duration: 90, pillar: 'knowledge', isDeep: true },
    { title: 'آشپزی ناهار مفصل — سفره‌داری هفته', anchor: 'dhuhr', offset: -150, duration: 120, pillar: 'people' },
    { title: 'نماز ظهر اول وقت؛ ناهار خانوادگی', anchor: 'dhuhr', offset: 0, duration: 75, pillar: 'worship', isCore: true },
    { title: 'چرت، سپس تفریح و پیاده‌روی خانوادگی', anchor: 'dhuhr', offset: 90, duration: 150, pillar: 'people' },
    { title: 'صله‌رحم: دیدار یا تماس با ۳ نفر', anchor: 'maghrib', offset: -180, duration: 90, pillar: 'people' },
    { title: 'بازنگری هفتگی: نمره‌ی ۵ ستون + تنظیم هفته‌ی بعد', anchor: 'maghrib', offset: -60, duration: 30, pillar: 'order', isCore: true },
    { title: 'نماز مغرب و عشا اول وقت؛ شام', anchor: 'maghrib', offset: 0, duration: 60, pillar: 'worship', isCore: true },
    { title: 'مطالعه‌ی سبک', anchor: 'sleep', offset: -90, duration: 45, pillar: 'knowledge' },
    { title: 'مرور روز + سه کار فردا', anchor: 'sleep', offset: -30, duration: 15, pillar: 'order', isCore: true },
  ],
};

const FRI: DayTemplate = {
  code: 'FRI',
  title: 'جمعه — معنویت و تنفس',
  mission: 'غسل، ندبه، کهف، تفریح خانوادگی، تنظیم هفته',
  blocks: [
    { title: 'بیداری و نماز شب', anchor: 'fajr', offset: -60, duration: 55, pillar: 'worship', isCore: true },
    { title: 'نماز صبح اول وقت + تعقیبات؛ غسل جمعه', anchor: 'fajr', offset: 0, duration: 40, pillar: 'worship', isCore: true },
    { title: 'دعای ندبه، سپس تلاوت سوره‌ی کهف', anchor: 'sunrise', offset: 60, duration: 105, pillar: 'worship' },
    { title: 'نماز جمعه یا نماز اول وقت؛ ناهار خانوادگی', anchor: 'dhuhr', offset: 0, duration: 90, pillar: 'worship', isCore: true },
    { title: 'چرت، سپس تفریح خانوادگی', anchor: 'dhuhr', offset: 100, duration: 150, pillar: 'people' },
    { title: 'جبران کارهای عقب‌افتاده‌ی هفته', anchor: 'maghrib', offset: -120, duration: 60, pillar: 'order' },
    { title: 'ساعت استجابت: دعا + تنظیم هفته‌ی بعد', anchor: 'maghrib', offset: -45, duration: 40, pillar: 'worship', isCore: true },
    { title: 'نماز مغرب و عشا اول وقت؛ شام', anchor: 'maghrib', offset: 0, duration: 60, pillar: 'worship', isCore: true },
    { title: 'مطالعه‌ی سبک', anchor: 'sleep', offset: -90, duration: 45, pillar: 'knowledge' },
    { title: 'مرور روز — فردا روز کاری است', anchor: 'sleep', offset: -30, duration: 15, pillar: 'order', isCore: true },
  ],
};

/** انتخاب قالب بر اساس روز هفته‌ی getDay() */
export function templateForWeekday(weekday: number): DayTemplate {
  switch (weekday) {
    case 6: // شنبه
    case 0: // یکشنبه
    case 2: // سه‌شنبه
      return WORK;
    case 1: // دوشنبه
      return HOME_BODY;
    case 3: // چهارشنبه
      return HOME_MIND;
    case 4: // پنجشنبه
      return THU;
    case 5: // جمعه
    default:
      return FRI;
  }
}

export const ALL_TEMPLATES = [WORK, HOME_BODY, HOME_MIND, THU, FRI];
