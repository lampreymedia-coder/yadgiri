import dayjs from 'dayjs'
import 'dayjs/locale/fa'

dayjs.locale('fa')

export const toDateKey = (input?: string | Date) => dayjs(input).format('YYYY-MM-DD')

export const fromDateKey = (dateKey: string) => dayjs(dateKey)

export const formatPersianDate = (input: string | Date, options?: Intl.DateTimeFormatOptions) =>
  new Intl.DateTimeFormat('fa-IR', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    ...options,
  }).format(dayjs(input).toDate())

export const formatCompactPersianDate = (input: string | Date) =>
  new Intl.DateTimeFormat('fa-IR', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(dayjs(input).toDate())

export const getWeekStart = (dateKey: string) => {
  const date = fromDateKey(dateKey)
  const day = date.day()
  const diff = day === 6 ? 0 : day + 1

  return date.subtract(diff, 'day')
}

export const getNextDays = (dateKey: string, total = 6) =>
  Array.from({ length: total }, (_, index) => fromDateKey(dateKey).add(index, 'day'))

export const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)
