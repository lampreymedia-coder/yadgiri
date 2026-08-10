import { useSyncExternalStore } from 'react';

export type Pillar = 'worship' | 'knowledge' | 'body' | 'people' | 'order';
export type Intensity = 'min' | 'normal' | 'peak';

export const PILLARS: { code: Pillar; title: string; emoji: string }[] = [
  { code: 'worship', title: 'عبادت', emoji: '🕌' },
  { code: 'knowledge', title: 'علم', emoji: '📚' },
  { code: 'body', title: 'بدن', emoji: '💪' },
  { code: 'people', title: 'خلق', emoji: '🤝' },
  { code: 'order', title: 'نظم', emoji: '🗂️' },
];

export const PILLAR_TITLE: Record<Pillar, string> = {
  worship: 'عبادت',
  knowledge: 'علم',
  body: 'بدن',
  people: 'خلق',
  order: 'نظم',
};

/** برنامه یا جلسه‌ای که کاربر خودش اضافه می‌کند */
export interface CustomHabit {
  id: string;
  title: string;
  pillar: Pillar;
  /** روزهای تکرار با getDay()؛ خالی یعنی فقط یک روز مشخص */
  weekdays: number[];
  /** برای جلسه‌ی یک‌باره: کلید روز */
  date?: string;
  time?: string; // "HH:MM"
  durationMinutes?: number;
  createdAt: number;
}

export interface DaySummary {
  done: number;
  total: number;
  pillars: Record<Pillar, { done: number; total: number }>;
}

export interface DayState {
  checks: Record<string, boolean>;
  intensity: Intensity;
  summary?: DaySummary;
}

export interface Review {
  date: string;
  pillars: Record<Pillar, boolean>;
  bestMoment: string;
  shortfall: string;
  tomorrowChange: string;
  tomorrowTasks: string[];
  sleepHours?: number;
  savedAt: number;
}

export interface FocusSession {
  date: string;
  minutes: number;
  ambience: string;
  at: number;
}

export interface AppState {
  theme: 'dark' | 'light';
  city: { name: string; lat: number; lng: number };
  habits: CustomHabit[];
  days: Record<string, DayState>;
  reviews: Record<string, Review>;
  focus: FocusSession[];
}

const KEY = 'rooznama-state-v1';

const DEFAULT_STATE: AppState = {
  theme: 'dark',
  city: { name: 'تهران', lat: 35.6892, lng: 51.389 },
  habits: [],
  days: {},
  reviews: {},
  focus: [],
};

function load(): AppState {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULT_STATE;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT_STATE, ...parsed };
  } catch {
    return DEFAULT_STATE;
  }
}

let state: AppState = load();
const listeners = new Set<() => void>();
let saveTimer: number | undefined;

function persist() {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* حافظه پر — نادیده بگیر */
    }
  }, 150);
}

export function getState(): AppState {
  return state;
}

export function setState(updater: (prev: AppState) => AppState) {
  state = updater(state);
  persist();
  listeners.forEach((l) => l());
}

export function useAppState(): AppState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
  );
}

export function getDayState(date: string): DayState {
  return state.days[date] ?? { checks: {}, intensity: 'normal' };
}

export function updateDay(date: string, patch: Partial<DayState>) {
  setState((prev) => ({
    ...prev,
    days: {
      ...prev.days,
      [date]: { ...getDayState(date), ...prev.days[date], ...patch },
    },
  }));
}

export function exportJSON(): string {
  return JSON.stringify(state, null, 2);
}

export function importJSON(raw: string): boolean {
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== 'object' || parsed === null) return false;
    state = { ...DEFAULT_STATE, ...parsed };
    persist();
    listeners.forEach((l) => l());
    return true;
  } catch {
    return false;
  }
}

export function uid(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}
