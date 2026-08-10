import { computePrayerTimes } from '../lib/praytimes';
import { dayKey, addDays } from '../lib/jalali';
import {
  templateForWeekday,
  WORK_DAYS,
  SLEEP_TIME_WORK,
  SLEEP_TIME_HOME,
  WAKE_OFFSET_WORK,
  WAKE_OFFSET_HOME,
  type AnchorCode,
} from '../data/program';
import type { AppState, DaySummary, Intensity, Pillar } from '../lib/store';

export interface Task {
  id: string;
  title: string;
  /** دقیقه از نیمه‌شب؛ undefined یعنی بدون زمان مشخص */
  start?: number;
  duration: number;
  pillar: Pillar;
  isCore: boolean;
  isDeep: boolean;
  source: 'template' | 'habit' | 'review';
}

export interface DayPlan {
  date: Date;
  key: string;
  templateCode: string;
  templateTitle: string;
  mission: string;
  anchors: Record<string, number>;
  tasks: Task[];
  isWorkDay: boolean;
}

function resolveAnchor(
  anchor: AnchorCode,
  anchors: Record<string, number>,
): number | undefined {
  if (anchor.startsWith('clock:')) {
    const [h, m] = anchor.slice(6).split(':').map(Number);
    return h * 60 + m;
  }
  return anchors[anchor];
}

export function generateDayPlan(
  date: Date,
  state: AppState,
  intensity: Intensity,
): DayPlan {
  const key = dayKey(date);
  const weekday = date.getDay();
  const isWorkDay = WORK_DAYS.includes(weekday);
  const template = templateForWeekday(weekday);

  const pt = computePrayerTimes(date, state.city.lat, state.city.lng);
  const sleep = isWorkDay ? SLEEP_TIME_WORK : SLEEP_TIME_HOME;
  const wake = pt.fajr + (isWorkDay ? WAKE_OFFSET_WORK : WAKE_OFFSET_HOME);
  const anchors: Record<string, number> = {
    fajr: pt.fajr,
    sunrise: pt.sunrise,
    dhuhr: pt.dhuhr,
    asr: pt.asr,
    maghrib: pt.maghrib,
    isha: pt.isha,
    wake,
    sleep,
  };

  const tasks: Task[] = [];

  template.blocks.forEach((b, i) => {
    if (intensity === 'min' && !b.isCore) return;
    const base = resolveAnchor(b.anchor, anchors);
    tasks.push({
      id: `t:${template.code}:${i}`,
      title: b.title,
      start: base === undefined ? undefined : base + b.offset,
      duration: b.duration,
      pillar: b.pillar,
      isCore: !!b.isCore,
      isDeep: !!b.isDeep,
      source: 'template',
    });
  });

  // برنامه‌ها و جلسه‌های خود کاربر
  for (const h of state.habits) {
    const matches =
      h.weekdays.length > 0 ? h.weekdays.includes(weekday) : h.date === key;
    if (!matches) continue;
    let start: number | undefined;
    if (h.time) {
      const [hh, mm] = h.time.split(':').map(Number);
      start = hh * 60 + mm;
    }
    tasks.push({
      id: `h:${h.id}`,
      title: h.title,
      start,
      duration: h.durationMinutes ?? 0,
      pillar: h.pillar,
      isCore: false,
      isDeep: false,
      source: 'habit',
    });
  }

  // سه کار فردا از مرور دیشب
  const yesterdayKey = dayKey(addDays(date, -1));
  const review = state.reviews[yesterdayKey];
  if (review) {
    review.tomorrowTasks.forEach((t, i) => {
      if (!t.trim()) return;
      tasks.push({
        id: `r:${yesterdayKey}:${i}`,
        title: t,
        start: undefined,
        duration: 0,
        pillar: 'order',
        isCore: false,
        isDeep: false,
        source: 'review',
      });
    });
  }

  tasks.sort((a, b) => {
    if (a.start === undefined && b.start === undefined) return 0;
    if (a.start === undefined) return 1;
    if (b.start === undefined) return -1;
    return a.start - b.start;
  });

  return {
    date,
    key,
    templateCode: template.code,
    templateTitle: template.title,
    mission: template.mission,
    anchors,
    tasks,
    isWorkDay,
  };
}

export function summarize(
  tasks: Task[],
  checks: Record<string, boolean>,
): DaySummary {
  const pillars = {
    worship: { done: 0, total: 0 },
    knowledge: { done: 0, total: 0 },
    body: { done: 0, total: 0 },
    people: { done: 0, total: 0 },
    order: { done: 0, total: 0 },
  };
  let done = 0;
  for (const t of tasks) {
    pillars[t.pillar].total += 1;
    if (checks[t.id]) {
      pillars[t.pillar].done += 1;
      done += 1;
    }
  }
  return { done, total: tasks.length, pillars };
}

/** بلوک جاری و بعدی بر اساس ساعت فعلی */
export function nowAndNext(tasks: Task[], nowMin: number, checks: Record<string, boolean>) {
  const timed = tasks.filter((t) => t.start !== undefined && !checks[t.id]);
  const current = timed.find(
    (t) => t.start! <= nowMin && nowMin < t.start! + Math.max(t.duration, 10),
  );
  const next = timed.find((t) => t.start! > nowMin);
  return { current, next };
}
