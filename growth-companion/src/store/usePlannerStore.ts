import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import type { BlockCategory, FocusSession, QuickTask, Soundscape } from '../types'
import { toDateKey } from '../utils/date'

export type ThemeMode = 'dark' | 'light'
export type AppTab = 'today' | 'progress' | 'focus' | 'review'

interface PlannerState {
  selectedDateKey: string
  activeTab: AppTab
  theme: ThemeMode
  completedBlocksByDate: Record<string, string[]>
  completedHabitsByDate: Record<string, string[]>
  quickTasks: QuickTask[]
  focusSessions: FocusSession[]
  notesByDate: Record<string, string>
  tomorrowByDate: Record<string, string[]>
  setSelectedDate: (dateKey: string) => void
  setActiveTab: (tab: AppTab) => void
  setTheme: (theme: ThemeMode) => void
  toggleTheme: () => void
  toggleBlock: (dateKey: string, blockId: string) => void
  toggleHabit: (dateKey: string, habitId: string) => void
  addQuickTask: (dateKey: string, title: string, category: BlockCategory, durationLabel?: string) => void
  removeQuickTask: (taskId: string) => void
  addFocusSession: (dateKey: string, durationMinutes: number, sound: Soundscape) => void
  setNote: (dateKey: string, note: string) => void
  setTomorrowLines: (dateKey: string, lines: string[]) => void
}

const toggleCollection = (collection: Record<string, string[]>, key: string, itemId: string) => {
  const current = collection[key] ?? []
  const nextItems = current.includes(itemId)
    ? current.filter((id) => id !== itemId)
    : [...current, itemId]

  return {
    ...collection,
    [key]: nextItems,
  }
}

export const usePlannerStore = create<PlannerState>()(
  persist(
    (set) => ({
      selectedDateKey: toDateKey(new Date()),
      activeTab: 'today',
      theme: 'dark',
      completedBlocksByDate: {},
      completedHabitsByDate: {},
      quickTasks: [],
      focusSessions: [],
      notesByDate: {},
      tomorrowByDate: {},
      setSelectedDate: (dateKey) => set({ selectedDateKey: dateKey }),
      setActiveTab: (tab) => set({ activeTab: tab }),
      setTheme: (theme) => set({ theme }),
      toggleTheme: () =>
        set((state) => ({
          theme: state.theme === 'dark' ? 'light' : 'dark',
        })),
      toggleBlock: (dateKey, blockId) =>
        set((state) => ({
          completedBlocksByDate: toggleCollection(state.completedBlocksByDate, dateKey, blockId),
        })),
      toggleHabit: (dateKey, habitId) =>
        set((state) => ({
          completedHabitsByDate: toggleCollection(state.completedHabitsByDate, dateKey, habitId),
        })),
      addQuickTask: (dateKey, title, category, durationLabel) =>
        set((state) => ({
          quickTasks: [
            {
              id: `quick-${crypto.randomUUID()}`,
              dateKey,
              title: title.trim(),
              category,
              durationLabel,
            },
            ...state.quickTasks,
          ],
        })),
      removeQuickTask: (taskId) =>
        set((state) => ({
          quickTasks: state.quickTasks.filter((task) => task.id !== taskId),
        })),
      addFocusSession: (dateKey, durationMinutes, sound) =>
        set((state) => ({
          focusSessions: [
            {
              id: `focus-${crypto.randomUUID()}`,
              dateKey,
              durationMinutes,
              sound,
              completedAt: new Date().toISOString(),
            },
            ...state.focusSessions,
          ],
        })),
      setNote: (dateKey, note) =>
        set((state) => ({
          notesByDate: {
            ...state.notesByDate,
            [dateKey]: note,
          },
        })),
      setTomorrowLines: (dateKey, lines) =>
        set((state) => ({
          tomorrowByDate: {
            ...state.tomorrowByDate,
            [dateKey]: lines.filter(Boolean).slice(0, 3),
          },
        })),
    }),
    {
      name: 'roshdyar-store',
      version: 2,
    },
  ),
)
