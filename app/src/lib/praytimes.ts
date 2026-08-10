/**
 * محاسبه‌ی اوقات شرعی — کاملاً آفلاین و محاسباتی (الگوریتم نجومی PrayTimes)
 * روش پیش‌فرض: ژئوفیزیک دانشگاه تهران (فجر ۱۷.۷°، عشاء ۱۴°، مغرب ۴.۵°)
 */

export interface PrayerTimes {
  /** همه بر حسب «دقیقه از نیمه‌شب» به وقت محلی دستگاه */
  fajr: number;
  sunrise: number;
  dhuhr: number;
  asr: number;
  sunset: number;
  maghrib: number;
  isha: number;
}

const DEG = Math.PI / 180;

function dtr(d: number) {
  return d * DEG;
}
function rtd(r: number) {
  return r / DEG;
}
function fixHour(h: number) {
  return ((h % 24) + 24) % 24;
}

function julian(year: number, month: number, day: number): number {
  let y = year;
  let m = month;
  if (m <= 2) {
    y -= 1;
    m += 12;
  }
  const a = Math.floor(y / 100);
  const b = 2 - a + Math.floor(a / 4);
  return (
    Math.floor(365.25 * (y + 4716)) +
    Math.floor(30.6001 * (m + 1)) +
    day +
    b -
    1524.5
  );
}

/** میل خورشید و معادله‌ی زمان برای یک روز ژولینی */
function sunPosition(jd: number) {
  const d = jd - 2451545.0;
  const g = ((357.529 + 0.98560028 * d) % 360 + 360) % 360;
  const q = ((280.459 + 0.98564736 * d) % 360 + 360) % 360;
  const l =
    ((q + 1.915 * Math.sin(dtr(g)) + 0.02 * Math.sin(dtr(2 * g))) % 360 + 360) %
    360;
  const e = 23.439 - 0.00000036 * d;
  const decl = rtd(Math.asin(Math.sin(dtr(e)) * Math.sin(dtr(l))));
  let ra = rtd(Math.atan2(Math.cos(dtr(e)) * Math.sin(dtr(l)), Math.cos(dtr(l)))) / 15;
  ra = fixHour(ra);
  const eqt = q / 15 - ra;
  return { decl, eqt };
}

export function computePrayerTimes(
  date: Date,
  lat = 35.6892,
  lng = 51.389,
): PrayerTimes {
  const jd = julian(date.getFullYear(), date.getMonth() + 1, date.getDate());
  // منطقه‌ی زمانی دستگاه بر حسب ساعت
  const tz = -date.getTimezoneOffset() / 60;

  const { decl, eqt } = sunPosition(jd + 0.5 - lng / (15 * 24));
  const noon = fixHour(12 - eqt) - lng / 15 + tz;

  /** زاویه‌ی زیر افق → فاصله‌ی زمانی از ظهر شرعی (ساعت) */
  const hourAngle = (angle: number): number => {
    const cosH =
      (-Math.sin(dtr(angle)) - Math.sin(dtr(decl)) * Math.sin(dtr(lat))) /
      (Math.cos(dtr(decl)) * Math.cos(dtr(lat)));
    return rtd(Math.acos(Math.min(1, Math.max(-1, cosH)))) / 15;
  };

  /** عصر با ضریب سایه‌ی استاندارد (شافعی=۱) */
  const asrAngle = (factor: number): number => {
    const t = -rtd(
      Math.atan(1 / (factor + Math.tan(dtr(Math.abs(lat - decl))))),
    );
    return hourAngle(t);
  };

  const toMin = (h: number) => Math.round(fixHour(h) * 60);

  return {
    fajr: toMin(noon - hourAngle(17.7)),
    sunrise: toMin(noon - hourAngle(0.833)),
    dhuhr: toMin(noon + 2 / 60),
    asr: toMin(noon + asrAngle(1)),
    sunset: toMin(noon + hourAngle(0.833)),
    maghrib: toMin(noon + hourAngle(4.5)),
    isha: toMin(noon + hourAngle(14)),
  };
}
