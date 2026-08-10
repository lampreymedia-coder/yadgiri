import dayjs from 'dayjs'

import { dayTemplates, habits } from '../data/appData'
import type { FocusSession } from '../types'

export type ProgressRange = 'week' | 'month' | 'year'

const countCompletionsInRange = (
  completedByDate: Record<string, string[]>,
  start: dayjs.Dayjs,
  end: dayjs.Dayjs,
) => {
  let total = 0

  Object.entries(completedByDate).forEach(([dateKey, items]) => {
    const current = dayjs(dateKey)

    if (
      (current.isSame(start, 'day') || current.isAfter(start, 'day')) &&
      (current.isSame(end, 'day') || current.isBefore(end, 'day'))
    ) {
      total += items.length
    }
  })

  return total
}

const expectedBlocksInRange = (start: dayjs.Dayjs, end: dayjs.Dayjs) => {
  let cursor = start.startOf('day')
  let total = 0

  while (cursor.isBefore(end) || cursor.isSame(end, 'day')) {
    total += dayTemplates[cursor.day()]?.blocks.length ?? 0
    cursor = cursor.add(1, 'day')
  }

  return total
}

const expectedHabitsInRange = (start: dayjs.Dayjs, end: dayjs.Dayjs) => {
  const days = end.diff(start, 'day') + 1
  return Math.max(days, 0) * habits.length
}

const focusMinutesInRange = (sessions: FocusSession[], start: dayjs.Dayjs, end: dayjs.Dayjs) =>
  sessions
    .filter((session) => {
      const current = dayjs(session.dateKey)

      return (
        (current.isSame(start, 'day') || current.isAfter(start, 'day')) &&
        (current.isSame(end, 'day') || current.isBefore(end, 'day'))
      )
    })
    .reduce((sum, session) => sum + session.durationMinutes, 0)

export const getRangeBounds = (range: ProgressRange, dateKey: string) => {
  const base = dayjs(dateKey)

  if (range === 'week') {
    const day = base.day()
    const diff = day === 6 ? 0 : day + 1
    const start = base.subtract(diff, 'day').startOf('day')
    return { start, end: start.add(6, 'day') }
  }

  if (range === 'month') {
    return { start: base.startOf('month'), end: base.endOf('month') }
  }

  return { start: base.startOf('year'), end: base.endOf('year') }
}

export const buildProgressSummary = (
  range: ProgressRange,
  dateKey: string,
  completedBlocksByDate: Record<string, string[]>,
  completedHabitsByDate: Record<string, string[]>,
  focusSessions: FocusSession[],
) => {
  const { start, end } = getRangeBounds(range, dateKey)
  const doneBlocks = countCompletionsInRange(completedBlocksByDate, start, end)
  const doneHabits = countCompletionsInRange(completedHabitsByDate, start, end)
  const expectedBlocks = expectedBlocksInRange(start, end)
  const expectedHabits = expectedHabitsInRange(start, end)
  const focusMinutes = focusMinutesInRange(focusSessions, start, end)
  const totalDone = doneBlocks + doneHabits
  const totalExpected = expectedBlocks + expectedHabits
  const percent = totalExpected ? Math.round((totalDone / totalExpected) * 100) : 0

  return {
    range,
    start,
    end,
    doneBlocks,
    doneHabits,
    expectedBlocks,
    expectedHabits,
    focusMinutes,
    percent: Math.min(percent, 100),
    chart: [
      {
        name: 'کارها',
        value: expectedBlocks ? Math.min(Math.round((doneBlocks / expectedBlocks) * 5), 5) : 0,
        color: '#38bdf8',
      },
      {
        name: 'عادت‌ها',
        value: expectedHabits ? Math.min(Math.round((doneHabits / expectedHabits) * 5), 5) : 0,
        color: '#34d399',
      },
      {
        name: 'تمرکز',
        value: Math.min(Math.round(focusMinutes / 60), 5),
        color: '#f472b6',
      },
    ],
  }
}
