/** ابزارهای قالب‌بندی فارسی */

const FA_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];

export function toFa(value: number | string): string {
  return String(value).replace(/\d/g, (d) => FA_DIGITS[Number(d)]);
}

/** دقیقه از نیمه‌شب → «۰۶:۳۰» فارسی */
export function minToTime(min: number): string {
  const m = ((min % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60);
  const mm = Math.round(m % 60);
  return toFa(`${String(h).padStart(2, '0')}:${String(mm).padStart(2, '0')}`);
}

/** مدت به متن: ۹۰ → «۱ ساعت و ۳۰ دقیقه» */
export function durationFa(minutes: number): string {
  if (minutes <= 0) return '';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h && m) return `${toFa(h)} ساعت و ${toFa(m)} دقیقه`;
  if (h) return `${toFa(h)} ساعت`;
  return `${toFa(m)} دقیقه`;
}

/** ثانیه → «۴۹:۵۹» برای تایمر */
export function secToClock(totalSec: number): string {
  const s = Math.max(0, Math.round(totalSec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, '0');
  const ss = String(sec).padStart(2, '0');
  return toFa(h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`);
}
