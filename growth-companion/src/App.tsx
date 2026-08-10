import { useEffect, useMemo, useState } from 'react'
import dayjs from 'dayjs'
import {
  AudioLines,
  CheckCircle2,
  Flame,
  ListTodo,
  NotebookPen,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Sparkles,
  Timer,
  Trash2,
} from 'lucide-react'

import './App.css'
import ProgressChart from './components/ProgressChart'
import SectionCard from './components/SectionCard'
import { appName, dayTemplates, focusPresets, habits, weeklyRatings } from './data/appData'
import { usePlannerStore } from './store/usePlannerStore'
import type { BlockCategory, ScheduleBlock, Soundscape } from './types'
import { playCompletionChime, soundLabels, startAmbientSound, stopAmbientSound } from './utils/ambientAudio'
import {
  formatCompactPersianDate,
  formatPersianDate,
  fromDateKey,
  getNextDays,
  getWeekStart,
  toDateKey,
} from './utils/date'

function App() {
  const {
    selectedDateKey,
    completedBlocksByDate,
    completedHabitsByDate,
    quickTasks,
    focusSessions,
    notesByDate,
    tomorrowByDate,
    weeklyRatings: persistedRatings,
    setSelectedDate,
    toggleBlock,
    toggleHabit,
    addQuickTask,
    removeQuickTask,
    addFocusSession,
    setNote,
    setTomorrowLines,
    setWeeklyRating,
  } = usePlannerStore()

  const [quickTitle, setQuickTitle] = useState('')
  const [quickCategory, setQuickCategory] = useState<BlockCategory>('focus')
  const [quickDuration, setQuickDuration] = useState('')
  const [focusMinutes, setFocusMinutes] = useState(50)
  const [remainingSeconds, setRemainingSeconds] = useState(50 * 60)
  const [isRunning, setIsRunning] = useState(false)
  const [selectedSound, setSelectedSound] = useState<Soundscape>('cosmic')

  const selectedDate = fromDateKey(selectedDateKey)
  const todayKey = toDateKey(new Date())
  const selectedTemplate = dayTemplates[selectedDate.day()]
  const quickTasksForDay = quickTasks.filter((task) => task.dateKey === selectedDateKey)
  const quickBlocks: ScheduleBlock[] = quickTasksForDay.map((task) => ({
    id: task.id,
    title: task.title,
    start: task.durationLabel ? `${task.durationLabel} دقیقه` : 'افزوده‌شده',
    category: task.category,
    note: 'بلوک سفارشی شما',
  }))
  const scheduleBlocks = [...selectedTemplate.blocks, ...quickBlocks]
  const completedBlocks = completedBlocksByDate[selectedDateKey] ?? []
  const completedHabits = completedHabitsByDate[selectedDateKey] ?? []
  const nextDays = getNextDays(selectedDateKey, 6)

  const blockCompletion = scheduleBlocks.length
    ? Math.round((completedBlocks.length / scheduleBlocks.length) * 100)
    : 0
  const habitCompletion = habits.length ? Math.round((completedHabits.length / habits.length) * 100) : 0

  const weeklyFocusMinutes = useMemo(() => {
    const weekStart = getWeekStart(selectedDateKey)
    const weekEnd = weekStart.add(6, 'day')

    return focusSessions
      .filter((session) => {
        const current = dayjs(session.dateKey)

        return current.isAfter(weekStart.subtract(1, 'day')) && current.isBefore(weekEnd.add(1, 'day'))
      })
      .reduce((sum, session) => sum + session.durationMinutes, 0)
  }, [focusSessions, selectedDateKey])

  const anchorStreak = useMemo(() => {
    const anchorIds = habits.filter((habit) => habit.group === 'anchors').map((habit) => habit.id)
    let cursor = dayjs(todayKey)
    let streak = 0

    while (streak < 60) {
      const key = cursor.format('YYYY-MM-DD')
      const completed = new Set(completedHabitsByDate[key] ?? [])

      if (!anchorIds.every((id) => completed.has(id))) {
        break
      }

      streak += 1
      cursor = cursor.subtract(1, 'day')
    }

    return streak
  }, [completedHabitsByDate, todayKey])

  const chartData = weeklyRatings.map((rating) => ({
    name: rating.title,
    value: persistedRatings[rating.id] ?? 3,
    color: rating.color,
  }))

  const statCards = [
    {
      icon: <ListTodo size={18} />,
      title: 'انجام برنامه امروز',
      value: `${blockCompletion}%`,
      note: `${completedBlocks.length} از ${scheduleBlocks.length} بلوک`,
    },
    {
      icon: <CheckCircle2 size={18} />,
      title: 'هبیت‌های امروز',
      value: `${habitCompletion}%`,
      note: `${completedHabits.length} از ${habits.length} عادت`,
    },
    {
      icon: <Timer size={18} />,
      title: 'تمرکز این هفته',
      value: `${weeklyFocusMinutes}د`,
      note: 'مجموع سشن‌های فوکس',
    },
    {
      icon: <Flame size={18} />,
      title: 'استریک لنگرها',
      value: `${anchorStreak} روز`,
      note: 'روزهای پیوسته با ۵ لنگر',
    },
  ]

  const groupedHabits = {
    anchors: habits.filter((habit) => habit.group === 'anchors'),
    minimums: habits.filter((habit) => habit.group === 'minimums'),
    growth: habits.filter((habit) => habit.group === 'growth'),
  }

  const lastFocusSessions = focusSessions.slice(0, 4)
  const noteValue = notesByDate[selectedDateKey] ?? ''
  const tomorrowText = (tomorrowByDate[selectedDateKey] ?? []).join('\n')

  useEffect(() => {
    if (!isRunning) {
      setRemainingSeconds(focusMinutes * 60)
    }
  }, [focusMinutes, isRunning])

  useEffect(() => {
    if (!isRunning) {
      return
    }

    const timerId = window.setInterval(() => {
      setRemainingSeconds((previous) => Math.max(previous - 1, 0))
    }, 1000)

    return () => {
      window.clearInterval(timerId)
    }
  }, [isRunning])

  useEffect(() => {
    if (!isRunning || remainingSeconds > 0) {
      return
    }

    setIsRunning(false)
    void stopAmbientSound()
    void playCompletionChime()
    addFocusSession(selectedDateKey, focusMinutes, selectedSound)
    setRemainingSeconds(focusMinutes * 60)
  }, [addFocusSession, focusMinutes, isRunning, remainingSeconds, selectedDateKey, selectedSound])

  useEffect(() => {
    if (!isRunning) {
      return
    }

    void startAmbientSound(selectedSound)
  }, [isRunning, selectedSound])

  useEffect(() => {
    return () => {
      void stopAmbientSound()
    }
  }, [])

  const handleAddQuickTask = () => {
    if (!quickTitle.trim()) {
      return
    }

    addQuickTask(selectedDateKey, quickTitle, quickCategory, quickDuration.trim())
    setQuickTitle('')
    setQuickDuration('')
  }

  const handleToggleTimer = async () => {
    if (isRunning) {
      setIsRunning(false)
      await stopAmbientSound()
      return
    }

    await startAmbientSound(selectedSound)
    setIsRunning(true)
  }

  const handleResetTimer = async () => {
    setIsRunning(false)
    setRemainingSeconds(focusMinutes * 60)
    await stopAmbientSound()
  }

  const formatTimer = (totalSeconds: number) => {
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60

    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }

  return (
    <main className="app-shell">
      <section className="hero-panel">
        <div className="hero-panel__copy">
          <span className="eyebrow">
            <Sparkles size={16} />
            برنامه‌ریز رشد، عبادت و تمرکز
          </span>
          <h1>{appName}</h1>
          <p className="hero-panel__lead">
            یک همراه سبک و نصب‌پذیر برای اندروید و دسکتاپ که برنامه‌های تکرارشونده‌ات را
            خودش می‌چیند، پیشرفتت را نشان می‌دهد و برای مطالعه و تمرکز فضاسازی می‌کند.
          </p>
          <div className="hero-badges">
            <span>نصب‌پذیر (PWA)</span>
            <span>آفلاین و سبک</span>
            <span>برنامه خودکار روزانه</span>
          </div>
        </div>

        <div className="hero-panel__insight">
          <div className="insight-chip">
            <NotebookPen size={18} />
            {selectedTemplate.title}
          </div>
          <p>{selectedTemplate.summary}</p>
          <ul>
            {selectedTemplate.prompts.map((prompt) => (
              <li key={prompt}>{prompt}</li>
            ))}
          </ul>
        </div>
      </section>

      <section className="date-strip" aria-label="انتخاب روز">
        {nextDays.map((date) => {
          const key = date.format('YYYY-MM-DD')
          const active = key === selectedDateKey

          return (
            <button
              key={key}
              type="button"
              className={active ? 'date-pill active' : 'date-pill'}
              onClick={() => setSelectedDate(key)}
            >
              <span>{formatCompactPersianDate(date.toDate())}</span>
              {key === todayKey ? <small>امروز</small> : null}
            </button>
          )
        })}
      </section>

      <section className="stats-grid">
        {statCards.map((card) => (
          <article key={card.title} className="stat-card">
            <div className="stat-card__icon">{card.icon}</div>
            <div>
              <p className="stat-card__title">{card.title}</p>
              <strong>{card.value}</strong>
              <span>{card.note}</span>
            </div>
          </article>
        ))}
      </section>

      <section className="content-grid">
        <SectionCard
          title="امروز چه چیزی برایت از قبل آماده شده؟"
          subtitle={`${formatPersianDate(selectedDate.toDate())} • ${selectedTemplate.mood}`}
          className="schedule-card"
        >
          <div className="schedule-list">
            {scheduleBlocks.map((block) => {
              const isChecked = completedBlocks.includes(block.id)

              return (
                <label
                  key={block.id}
                  className={isChecked ? 'schedule-item done' : 'schedule-item'}
                  data-category={block.category}
                >
                  <input
                    type="checkbox"
                    checked={isChecked}
                    onChange={() => toggleBlock(selectedDateKey, block.id)}
                  />
                  <div className="schedule-item__time">{block.start}</div>
                  <div className="schedule-item__body">
                    <div className="schedule-item__title-row">
                      <strong>{block.title}</strong>
                      {block.autoGenerated ? <span className="mini-badge">خودکار</span> : null}
                    </div>
                    {block.end ? (
                      <span className="schedule-item__range">
                        تا {block.end}
                      </span>
                    ) : null}
                    {block.note ? <p>{block.note}</p> : null}
                  </div>
                </label>
              )
            })}
          </div>
        </SectionCard>

        <SectionCard
          title="عادت‌ها و حداقل‌های شکست‌ناپذیر"
          subtitle="روز بد داشته باش، روز صفر هرگز"
          className="habits-card"
        >
          <div className="habit-groups">
            {(
              [
                ['anchors', '۵ لنگر ثابت'],
                ['minimums', 'حداقل‌ها'],
                ['growth', 'رشد نرم'],
              ] as const
            ).map(([groupKey, label]) => (
              <div key={groupKey} className="habit-group">
                <h3>{label}</h3>
                <div className="habit-list">
                  {groupedHabits[groupKey].map((habit) => {
                    const isChecked = completedHabits.includes(habit.id)

                    return (
                      <button
                        key={habit.id}
                        type="button"
                        className={isChecked ? 'habit-pill checked' : 'habit-pill'}
                        onClick={() => toggleHabit(selectedDateKey, habit.id)}
                      >
                        <div>
                          <strong>{habit.title}</strong>
                          <span>{habit.description}</span>
                        </div>
                        {isChecked ? <CheckCircle2 size={18} /> : null}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard
          title="فوکِس مود"
          subtitle="یک بازه عمیق بساز و با صدای محیط واردش شو"
          className="focus-card"
          action={
            <div className="timer-live">
              <AudioLines size={16} />
              <span>{soundLabels[selectedSound]}</span>
            </div>
          }
        >
          <div className="focus-card__top">
            <div className="preset-row">
              {focusPresets.map((preset) => (
                <button
                  key={preset}
                  type="button"
                  className={focusMinutes === preset ? 'preset active' : 'preset'}
                  onClick={() => setFocusMinutes(preset)}
                >
                  {preset} دقیقه
                </button>
              ))}
            </div>

            <label className="sound-select">
              <span>فضای پخش</span>
              <select
                value={selectedSound}
                onChange={(event) => setSelectedSound(event.target.value as Soundscape)}
              >
                {Object.entries(soundLabels).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="timer-shell">
            <div className="timer-orb">
              <span>{formatTimer(remainingSeconds)}</span>
              <small>{isRunning ? 'در حال تمرکز' : 'آماده برای شروع'}</small>
            </div>

            <div className="timer-actions">
              <button type="button" className="primary-btn" onClick={() => void handleToggleTimer()}>
                {isRunning ? <Pause size={18} /> : <Play size={18} />}
                {isRunning ? 'توقف موقت' : 'شروع تمرکز'}
              </button>
              <button type="button" className="ghost-btn" onClick={() => void handleResetTimer()}>
                <RotateCcw size={18} />
                بازنشانی
              </button>
            </div>
          </div>

          <div className="focus-history">
            <h3>آخرین سشن‌ها</h3>
            <div className="focus-history__list">
              {lastFocusSessions.length ? (
                lastFocusSessions.map((session) => (
                  <div key={session.id} className="focus-history__item">
                    <strong>{session.durationMinutes} دقیقه</strong>
                    <span>{formatPersianDate(session.dateKey, { month: 'short', day: 'numeric' })}</span>
                    <small>{soundLabels[session.sound]}</small>
                  </div>
                ))
              ) : (
                <p className="empty-state">اولین سشن تمرکزت را شروع کن تا اینجا ثبت شود.</p>
              )}
            </div>
          </div>
        </SectionCard>

        <SectionCard
          title="روند رشد هفتگی"
          subtitle="هر ستون را از ۱ تا ۵ امتیاز بده تا پیشرفتت دیده شود"
          className="progress-card"
        >
          <div className="rating-grid">
            {weeklyRatings.map((rating) => (
              <label key={rating.id} className="rating-card">
                <div className="rating-card__header">
                  <strong>{rating.title}</strong>
                  <span>{persistedRatings[rating.id] ?? 3} / ۵</span>
                </div>
                <p>{rating.description}</p>
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={persistedRatings[rating.id] ?? 3}
                  onChange={(event) => setWeeklyRating(rating.id, Number(event.target.value))}
                  style={{ accentColor: rating.color }}
                />
              </label>
            ))}
          </div>
          <ProgressChart data={chartData} />
        </SectionCard>

        <SectionCard
          title="اضافه‌کردن سریع برنامه یا جلسه"
          subtitle="وقتی چیز تازه‌ای پیش آمد، با کمترین اصطکاک واردش کن"
          className="capture-card"
        >
          <div className="quick-form">
            <input
              type="text"
              value={quickTitle}
              onChange={(event) => setQuickTitle(event.target.value)}
              placeholder="مثلاً جلسه مدرسه، خرید ضروری یا مطالعه اضافه"
            />
            <select
              value={quickCategory}
              onChange={(event) => setQuickCategory(event.target.value as BlockCategory)}
            >
              <option value="focus">تمرکز</option>
              <option value="study">مطالعه</option>
              <option value="family">خانواده</option>
              <option value="custom">سایر</option>
            </select>
            <input
              type="text"
              value={quickDuration}
              onChange={(event) => setQuickDuration(event.target.value)}
              placeholder="مدت تقریبی"
            />
            <button type="button" className="primary-btn" onClick={handleAddQuickTask}>
              <Plus size={18} />
              افزودن
            </button>
          </div>

          <div className="quick-list">
            {quickTasksForDay.length ? (
              quickTasksForDay.map((task) => (
                <div key={task.id} className="quick-list__item">
                  <div>
                    <strong>{task.title}</strong>
                    <span>{task.durationLabel ? `${task.durationLabel} دقیقه` : 'بدون مدت مشخص'}</span>
                  </div>
                  <button type="button" onClick={() => removeQuickTask(task.id)} aria-label="حذف">
                    <Trash2 size={16} />
                  </button>
                </div>
              ))
            ) : (
              <p className="empty-state">برای این روز هنوز برنامه سفارشی اضافه نکرده‌ای.</p>
            )}
          </div>
        </SectionCard>

        <SectionCard
          title="محاسبه شب و فردای روشن"
          subtitle="یادداشت روزت را بنویس و فقط سه اولویت فردا را مشخص کن"
          className="reflection-card"
        >
          <div className="reflection-grid">
            <label>
              <span>مرور امروز</span>
              <textarea
                rows={6}
                value={noteValue}
                onChange={(event) => setNote(selectedDateKey, event.target.value)}
                placeholder="چه چیزی خوب بود؟ کجا نیاز به جبران دارم؟"
              />
            </label>

            <label>
              <span>سه کار فردا</span>
              <textarea
                rows={6}
                value={tomorrowText}
                onChange={(event) =>
                  setTomorrowLines(
                    selectedDateKey,
                    event.target.value
                      .split('\n')
                      .map((line) => line.trim())
                      .filter(Boolean),
                  )
                }
                placeholder="هر خط یک اولویت"
              />
            </label>
          </div>
        </SectionCard>
      </section>
    </main>
  )
}

export default App
