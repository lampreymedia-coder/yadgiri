import { create } from 'zustand'
import { persist } from 'zustand/middleware'

import { weeklyRatings } from '../data/appData'
import type { BlockCategory, FocusSession, QuickTask, Soundscape } from '../types'
import { toDateKey } from '../utils/date'

interface PlannerState {
  selectedDateKey: string
  completedBlocksByDate: Record<string, string[]>
  completedHabitsByDate: Record<string, string[]>
  quickTasks: QuickTask[]
  focusSessions: FocusSession[]
  notesByDate: Record<string, string>
  tomorrowByDate: Record<string, string[]>
  weeklyRatings: Record<string, number>
  setSelectedDate: (dateKey: string) => void
  toggleBlock: (dateKey: string, blockId: string) => void
  toggleHabit: (dateKey: string, habitId: string) => void
  addQuickTask: (dateKey: string, title: string, category: BlockCategory, durationLabel?: string) => void
  removeQuickTask: (taskId: string) => void
  addFocusSession: (dateKey: string, durationMinutes: number, sound: Soundscape) => void
  setNote: (dateKey: string, note: string) => void
  setTomorrowLines: (dateKey: string, lines: string[]) => void
  setWeeklyRating: (ratingId: string, value: number) => void
}

const defaultRatings = Object.fromEntries(weeklyRatings.map((rating) => [rating.id, 3]))

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
      completedBlocksByDate: {},
      completedHabitsByDate: {},
      quickTasks: [],
      focusSessions: [],
      notesByDate: {},
      tomorrowByDate: {},
      weeklyRatings: defaultRatings,
      setSelectedDate: (dateKey) => set({ selectedDateKey: dateKey }),
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
      setWeeklyRating: (ratingId, value) =>
        set((state) => ({
          weeklyRatings: {
            ...state.weeklyRatings,
            [ratingId]: value,
          },
        })),
    }),
    {
      name: 'roshdyar-store',
      version: 1,
    },
  ),
)
