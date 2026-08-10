/** پیشنهادهای کتاب — کاربر می‌تواند انتخاب کند یا کتاب خودش را اضافه کند */

export interface BookSuggestion {
  id: string;
  title: string;
  author: string;
  pages: number;
  category: 'معنوی' | 'رشد فردی' | 'فرزندپروری' | 'ادبیات' | 'تاریخ' | 'علمی';
  blurb: string;
}

export const BOOK_SUGGESTIONS: BookSuggestion[] = [
  {
    id: 'kah',
    title: 'کتاب آه',
    author: 'سید مهدی شجاعی',
    pages: 220,
    category: 'معنوی',
    blurb: 'روایتی لطیف از مصائب اهل‌بیت؛ مناسب مطالعه‌ی شبانه.',
  },
  {
    id: 'hamaseh',
    title: 'حماسه‌ی حسینی (جلد ۱)',
    author: 'مرتضی مطهری',
    pages: 280,
    category: 'معنوی',
    blurb: 'تحلیل عمیق قیام عاشورا؛ مناسب مطالعه‌ی صبح.',
  },
  {
    id: 'hossein-zaban',
    title: 'حسین از زبان حسین',
    author: 'محمدعلی جاودان',
    pages: 190,
    category: 'معنوی',
    blurb: 'کلام امام حسین(ع) با شرح کوتاه و خواندنی.',
  },
  {
    id: 'atomic',
    title: 'عادت‌های اتمی',
    author: 'جیمز کلیر',
    pages: 320,
    category: 'رشد فردی',
    blurb: 'سیستم ساخت عادت‌های کوچک و پایدار؛ کاربردی برای برنامه‌ی روزانه.',
  },
  {
    id: 'deep-work',
    title: 'کار عمیق',
    author: 'کال نیوپورت',
    pages: 300,
    category: 'رشد فردی',
    blurb: 'تمرکز عمیق در دنیای پر نویز؛ مکمل عالی حالت تمرکز.',
  },
  {
    id: 'essentialism',
    title: 'اصل‌گرایی',
    author: 'گرگ مک‌کیون',
    pages: 270,
    category: 'رشد فردی',
    blurb: 'کمتر، اما بهتر؛ برای سبک‌کردن برنامه‌ی سنگین.',
  },
  {
    id: 'parenting',
    title: 'فرزندپروری باهوش هیجانی',
    author: 'جان گاتمن',
    pages: 310,
    category: 'فرزندپروری',
    blurb: 'مهارت‌های هیجانی برای ارتباط عمیق با فرزند.',
  },
  {
    id: 'how-children',
    title: 'کودکان چگونه موفق می‌شوند',
    author: 'پل تاف',
    pages: 260,
    category: 'فرزندپروری',
    blurb: 'نقش شخصیت و پشتکار در رشد کودک، فراتر از نمره.',
  },
  {
    id: 'little-prince',
    title: 'شازده کوچولو',
    author: 'آنتوان دو سنت‌اگزوپری',
    pages: 120,
    category: 'ادبیات',
    blurb: 'کوتاه، عمیق و دلنشین؛ مناسب پایان روز.',
  },
  {
    id: 'kimia',
    title: 'کیمیاگر',
    author: 'پائولو کوئیلو',
    pages: 200,
    category: 'ادبیات',
    blurb: 'داستان جست‌وجوی معنا؛ انگیزه‌بخش و روان.',
  },
  {
    id: 'sapiens',
    title: 'انسان خردمند',
    author: 'یووال نوح هراری',
    pages: 450,
    category: 'تاریخ',
    blurb: 'روایت بزرگ تاریخ انسان؛ برای مطالعه‌ی عمیق آخر هفته.',
  },
  {
    id: 'thinking-fast',
    title: 'تفکر سریع و کند',
    author: 'دنیل کانمن',
    pages: 500,
    category: 'علمی',
    blurb: 'دو سیستم فکر کردن؛ برای فهم بهتر تصمیم‌های روزانه.',
  },
];

export const BOOK_CATEGORIES = [
  'همه',
  'معنوی',
  'رشد فردی',
  'فرزندپروری',
  'ادبیات',
  'تاریخ',
  'علمی',
] as const;
