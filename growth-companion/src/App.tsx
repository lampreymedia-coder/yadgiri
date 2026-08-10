import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2,
  Coffee,
  Home,
  Moon,
  NotebookPen,
  Pause,
  Play,
  Plus,
  RotateCcw,
  Sun,
  Target,
  Timer,
  Trash2,
  TrendingUp,
} from 'lucide-react'

import './App.css'
import ProgressChart from './components/ProgressChart'
import SectionCard from './components/SectionCard'
import {
  appName,
  dayTemplates,
  focusPresets,
  habitGroupLabels,
  habits,
  restPresets,
} from './data/appData'
import { type AppTab, usePlannerStore } from './store/usePlannerStore'
import type { BlockCategory, ScheduleBlock, Soundscape } from './types'
import {
  playCompletionChime,
  soundHints,
  soundLabels,
  startAmbientSound,
  stopAmbientSound,
} from './utils/ambientAudio'
import { formatPersianDate, fromDateKey, toDateKey } from './utils/date'
import { buildProgressSummary, type ProgressRange } from './utils/progress'

type TimerMode = 'focus' | 'rest'

const tabs: Array<{ id: AppTab; label: string; icon: typeof Home }> = [
  { id: 'today', label: 'امروز', icon: Home },
  { id: 'progress', label: 'پیشرفت', icon: TrendingUp },
  { id: 'focus', label: 'تمرکز', icon: Target },
  { id: 'review', label: 'مرور روز', icon: NotebookPen },
]

function App() {
  const {
    selectedDateKey,
    activeTab,
    theme,
    completedBlocksByDate,
    completedHabitsByDate,
    quickTasks,
    focusSessions,
    notesByDate,
    tomorrowByDate,
    setSelectedDate,
    setActiveTab,
    toggleTheme,
    toggleBlock,
    toggleHabit,
    addQuickTask,
    removeQuickTask,
    addFocusSession,
    setNote,
    setTomorrowLines,
  } = usePlannerStore()

  const [quickTitle, setQuickTitle] = useState('')
  const [quickCategory, setQuickCategory] = useState<BlockCategory>('focus')
  const [quickDuration, setQuickDuration] = useState('')
  const [focusMinutes, setFocusMinutes] = useState(50)
  const [restMinutes, setRestMinutes] = useState(5)
  const [timerMode, setTimerMode] = useState<TimerMode>('focus')
  const [remainingSeconds, setRemainingSeconds] = useState(50 * 60)
  const [isRunning, setIsRunning] = useState(false)
  const [selectedSound, setSelectedSound] = useState<Soundscape>('cosmic')
  const [isPreviewingSound, setIsPreviewingSound] = useState(false)
  const [progressRange, setProgressRange] = useState<ProgressRange>('week')
  const previewTimeoutRef = useRef<number | null>(null)

  const clearPreviewTimeout = () => {
    if (previewTimeoutRef.current !== null) {
      window.clearTimeout(previewTimeoutRef.current)
      previewTimeoutRef.current = null
    }
  }

  const selectedDate = fromDateKey(selectedDateKey)
  const todayKey = toDateKey(new Date())
  const selectedTemplate = dayTemplates[selectedDate.day()]
  const quickTasksForDay = quickTasks.filter((task) => task.dateKey === selectedDateKey)
  const quickBlocks: ScheduleBlock[] = quickTasksForDay.map((task) => ({
    id: task.id,
    title: task.title,
    start: task.durationLabel ? `${task.durationLabel} دقیقه` : 'افزوده‌شده',
    category: task.category,
    note: 'برنامه اضافه شما',
  }))
  const allBlocks = [...selectedTemplate.blocks, ...quickBlocks]
  const completedBlocks = completedBlocksByDate[selectedDateKey] ?? []
  const completedHabits = completedHabitsByDate[selectedDateKey] ?? []
  const visibleBlocks = allBlocks.filter((block) => !completedBlocks.includes(block.id))
  const visibleHabits = habits.filter((habit) => !completedHabits.includes(habit.id))
  const doneTodayCount = completedBlocks.length + completedHabits.length
  const totalTodayCount = allBlocks.length + habits.length
  const todayPercent = totalTodayCount ? Math.round((doneTodayCount / totalTodayCount) * 100) : 0

  const progressSummary = useMemo(
    () =>
      buildProgressSummary(
        progressRange,
        selectedDateKey,
        completedBlocksByDate,
        completedHabitsByDate,
        focusSessions,
      ),
    [completedBlocksByDate, completedHabitsByDate, focusSessions, progressRange, selectedDateKey],
  )

  const groupedVisibleHabits = {
    anchors: visibleHabits.filter((habit) => habit.group === 'anchors'),
    minimums: visibleHabits.filter((habit) => habit.group === 'minimums'),
    growth: visibleHabits.filter((habit) => habit.group === 'growth'),
  }

  const noteValue = notesByDate[selectedDateKey] ?? ''
  const tomorrowText = (tomorrowByDate[selectedDateKey] ?? []).join('\n')
  const lastFocusSessions = focusSessions.slice(0, 5)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
  }, [theme])

  useEffect(() => {
    if (selectedDateKey !== todayKey) {
      setSelectedDate(todayKey)
    }
  }, [selectedDateKey, setSelectedDate, todayKey])

  useEffect(() => {
    if (!isRunning) {
      const minutes = timerMode === 'focus' ? focusMinutes : restMinutes
      setRemainingSeconds(minutes * 60)
    }
  }, [focusMinutes, isRunning, restMinutes, timerMode])

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

    const finishCycle = async () => {
      setIsRunning(false)
      await stopAmbientSound()
      setIsPreviewingSound(false)
      await playCompletionChime()

      if (timerMode === 'focus') {
        addFocusSession(selectedDateKey, focusMinutes, selectedSound)
        setTimerMode('rest')
        setRemainingSeconds(restMinutes * 60)
        return
      }

      setTimerMode('focus')
      setRemainingSeconds(focusMinutes * 60)
    }

    void finishCycle()
  }, [
    addFocusSession,
    focusMinutes,
    isRunning,
    remainingSeconds,
    restMinutes,
    selectedDateKey,
    selectedSound,
    timerMode,
  ])

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

  const handleSelectSound = async (sound: Soundscape) => {
    clearPreviewTimeout()
    setSelectedSound(sound)

    if (sound === 'silent') {
      await stopAmbientSound()
      setIsPreviewingSound(false)
      return
    }

    const started = await startAmbientSound(sound)
    setIsPreviewingSound(started)

    if (!isRunning) {
      previewTimeoutRef.current = window.setTimeout(() => {
        void stopAmbientSound()
        setIsPreviewingSound(false)
      }, 4500)
    }
  }

  const handleToggleTimer = async () => {
    clearPreviewTimeout()

    if (isRunning) {
      setIsRunning(false)
      await stopAmbientSound()
      setIsPreviewingSound(false)
      return
    }

    if (timerMode === 'focus' && selectedSound !== 'silent') {
      const started = await startAmbientSound(selectedSound)
      setIsPreviewingSound(started)
    } else {
      await stopAmbientSound()
      setIsPreviewingSound(false)
    }

    setIsRunning(true)
  }

  const handleResetTimer = async () => {
    clearPreviewTimeout()
    setIsRunning(false)
    setTimerMode('focus')
    setRemainingSeconds(focusMinutes * 60)
    await stopAmbientSound()
    setIsPreviewingSound(false)
  }

  const formatTimer = (totalSeconds: number) => {
    const minutes = Math.floor(totalSeconds / 60)
    const seconds = totalSeconds % 60

    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }

  const rangeLabel =
    progressRange === 'week' ? 'این هفته' : progressRange === 'month' ? 'این ماه' : 'امسال'

  return (
    <div className="app-frame">
      <header className="topbar">
        <div>
          <p className="brand-kicker">برنامه‌ریز شخصی</p>
          <h1>{appName}</h1>
        </div>
        <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label="تغییر حالت شب و روز">
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          {theme === 'dark' ? 'حالت روز' : 'حالت شب'}
        </button>
      </header>

      <main className="page-shell">
        {activeTab === 'today' ? (
          <section className="page-stack">
            <SectionCard
              title="امروز"
              subtitle={formatPersianDate(selectedDate.toDate())}
              action={<span className="pill-soft">{todayPercent}% انجام‌شده</span>}
            >
              <div className="today-summary">
                <div>
                  <strong>{selectedTemplate.title}</strong>
                  <p>{selectedTemplate.summary}</p>
                </div>
                <div className="today-metrics">
                  <span>{visibleBlocks.length} کار باقی‌مانده</span>
                  <span>{visibleHabits.length} عادت باقی‌مانده</span>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="کارهای امروز" subtitle="با تیک‌زدن، کار از لیست امروز حذف و در پیشرفت ثبت می‌شود">
              <div className="schedule-list">
                {visibleBlocks.length ? (
                  visibleBlocks.map((block) => (
                    <label key={block.id} className="schedule-item" data-category={block.category}>
                      <input
                        type="checkbox"
                        checked={false}
                        onChange={() => toggleBlock(selectedDateKey, block.id)}
                      />
                      <div className="schedule-item__time">{block.start}</div>
                      <div className="schedule-item__body">
                        <div className="schedule-item__title-row">
                          <strong>{block.title}</strong>
                          {block.autoGenerated ? <span className="mini-badge">از برنامه</span> : null}
                        </div>
                        {block.end ? <span className="schedule-item__range">تا {block.end}</span> : null}
                        {block.note ? <p>{block.note}</p> : null}
                      </div>
                    </label>
                  ))
                ) : (
                  <p className="empty-state">عالی؛ کارهای امروز تمام شد.</p>
                )}
              </div>
            </SectionCard>

            <SectionCard title="عادت‌ها و حداقل‌ها" subtitle="روز بد داشته باش، روز صفر هرگز">
              <div className="habit-groups">
                {(Object.keys(habitGroupLabels) as Array<keyof typeof habitGroupLabels>).map((groupKey) => {
                  const items = groupedVisibleHabits[groupKey]

                  if (!items.length) {
                    return null
                  }

                  return (
                    <div key={groupKey} className="habit-group">
                      <h3>{habitGroupLabels[groupKey]}</h3>
                      <div className="habit-list">
                        {items.map((habit) => (
                          <button
                            key={habit.id}
                            type="button"
                            className="habit-pill"
                            onClick={() => toggleHabit(selectedDateKey, habit.id)}
                          >
                            <div>
                              <strong>{habit.title}</strong>
                              <span>{habit.description}</span>
                            </div>
                            <CheckCircle2 size={18} />
                          </button>
                        ))}
                      </div>
                    </div>
                  )
                })}
                {!visibleHabits.length ? <p className="empty-state">همه عادت‌های امروز ثبت شد.</p> : null}
              </div>
            </SectionCard>

            <SectionCard title="افزودن کار یا جلسه" subtitle="اگر چیزی خارج از برنامه پیش آمد، سریع ثبت کن">
              <div className="quick-form">
                <input
                  type="text"
                  value={quickTitle}
                  onChange={(event) => setQuickTitle(event.target.value)}
                  placeholder="مثلاً جلسه مدرسه یا خرید ضروری"
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
                  <p className="empty-state">هنوز کار سفارشی برای امروز نداری.</p>
                )}
              </div>
            </SectionCard>
          </section>
        ) : null}

        {activeTab === 'progress' ? (
          <section className="page-stack">
            <SectionCard
              title="روند پیشرفت"
              subtitle="هر تیک امروز، خودکار نمودار هفته، ماه و سال را جلو می‌برد"
            >
              <div className="range-row">
                {(
                  [
                    ['week', 'هفته'],
                    ['month', 'ماه'],
                    ['year', 'سال'],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={progressRange === value ? 'preset active' : 'preset'}
                    onClick={() => setProgressRange(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>

              <div className="progress-hero">
                <div>
                  <p>پیشرفت {rangeLabel}</p>
                  <strong>{progressSummary.percent}%</strong>
                </div>
                <div className="progress-hero__bars">
                  <span>{progressSummary.doneBlocks} کار انجام‌شده</span>
                  <span>{progressSummary.doneHabits} عادت ثبت‌شده</span>
                  <span>{progressSummary.focusMinutes} دقیقه تمرکز</span>
                </div>
              </div>

              <ProgressChart data={progressSummary.chart} />
            </SectionCard>

            <SectionCard title="خلاصه خودکار" subtitle="این اعداد از روی تیک‌های واقعی ساخته می‌شوند">
              <div className="summary-grid">
                <article>
                  <p>کارها</p>
                  <strong>
                    {progressSummary.doneBlocks} از {progressSummary.expectedBlocks}
                  </strong>
                </article>
                <article>
                  <p>عادت‌ها</p>
                  <strong>
                    {progressSummary.doneHabits} از {progressSummary.expectedHabits}
                  </strong>
                </article>
                <article>
                  <p>تمرکز</p>
                  <strong>{progressSummary.focusMinutes} دقیقه</strong>
                </article>
              </div>
            </SectionCard>
          </section>
        ) : null}

        {activeTab === 'focus' ? (
          <section className="page-stack">
            <SectionCard
              title="حالت تمرکز"
              subtitle="یک بازه کار عمیق بگذار و بعد استراحت کن"
              action={
                <span className="pill-soft">
                  <Timer size={14} />
                  {timerMode === 'focus' ? 'بازه تمرکز' : 'استراحت'}
                </span>
              }
            >
              <div className="focus-card__top">
                <div>
                  <p className="field-label">مدت تمرکز</p>
                  <div className="preset-row">
                    {focusPresets.map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        className={focusMinutes === preset && timerMode === 'focus' ? 'preset active' : 'preset'}
                        onClick={() => {
                          setFocusMinutes(preset)
                          setTimerMode('focus')
                        }}
                      >
                        {preset} دقیقه
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <p className="field-label">مدت استراحت</p>
                  <div className="preset-row">
                    {restPresets.map((preset) => (
                      <button
                        key={preset}
                        type="button"
                        className={restMinutes === preset ? 'preset active' : 'preset'}
                        onClick={() => setRestMinutes(preset)}
                      >
                        {preset} دقیقه
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="sound-grid">
                {(Object.keys(soundLabels) as Soundscape[]).map((sound) => (
                  <button
                    key={sound}
                    type="button"
                    className={selectedSound === sound ? 'sound-card active' : 'sound-card'}
                    onClick={() => void handleSelectSound(sound)}
                  >
                    <strong>{soundLabels[sound]}</strong>
                    <span>{soundHints[sound]}</span>
                    {selectedSound === sound && isPreviewingSound ? <small>در حال پخش</small> : null}
                  </button>
                ))}
              </div>

              <div className="timer-shell">
                <div className={timerMode === 'rest' ? 'timer-orb rest' : 'timer-orb'}>
                  <span>{formatTimer(remainingSeconds)}</span>
                  <small>
                    {isRunning
                      ? timerMode === 'focus'
                        ? 'در حال تمرکز'
                        : 'در حال استراحت'
                      : timerMode === 'focus'
                        ? 'آماده برای شروع'
                        : 'نوبت استراحت'}
                  </small>
                </div>

                <div className="timer-actions">
                  <button type="button" className="primary-btn" onClick={() => void handleToggleTimer()}>
                    {isRunning ? <Pause size={18} /> : <Play size={18} />}
                    {isRunning ? 'توقف موقت' : timerMode === 'focus' ? 'شروع تمرکز' : 'شروع استراحت'}
                  </button>
                  <button type="button" className="ghost-btn" onClick={() => void handleResetTimer()}>
                    <RotateCcw size={18} />
                    از نو
                  </button>
                  <button
                    type="button"
                    className="ghost-btn"
                    onClick={() => {
                      setTimerMode('rest')
                      setIsRunning(false)
                      setRemainingSeconds(restMinutes * 60)
                      void stopAmbientSound()
                      setIsPreviewingSound(false)
                    }}
                  >
                    <Coffee size={18} />
                    برو به استراحت
                  </button>
                </div>
              </div>
            </SectionCard>

            <SectionCard title="آخرین بازه‌های تمرکز" subtitle="ثبت خودکار بعد از پایان هر بازه">
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
                  <p className="empty-state">هنوز بازه تمرکزی ثبت نشده است.</p>
                )}
              </div>
            </SectionCard>
          </section>
        ) : null}

        {activeTab === 'review' ? (
          <section className="page-stack">
            <SectionCard title="محاسبه روز" subtitle="مرور کوتاه امروز و ثبت کارهای فردا">
              <div className="review-stats">
                <article>
                  <p>کارهای انجام‌شده امروز</p>
                  <strong>{completedBlocks.length}</strong>
                </article>
                <article>
                  <p>عادت‌های ثبت‌شده امروز</p>
                  <strong>{completedHabits.length}</strong>
                </article>
                <article>
                  <p>پیشرفت امروز</p>
                  <strong>{todayPercent}%</strong>
                </article>
              </div>
            </SectionCard>

            <SectionCard title="مرور امروز" subtitle="چه چیزی خوب بود؟ کجا نیاز به جبران داری؟">
              <textarea
                rows={8}
                value={noteValue}
                onChange={(event) => setNote(selectedDateKey, event.target.value)}
                placeholder="مرور کوتاه امروز را اینجا بنویس..."
              />
            </SectionCard>

            <SectionCard title="یادآوری فردا" subtitle="فقط سه اولویت مهم فردا را ثبت کن">
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
                placeholder={'هر خط یک کار\nمثلاً مطالعه کتاب ماه\nمثلاً تماس با خانواده'}
              />
            </SectionCard>
          </section>
        ) : null}
      </main>

      <nav className="bottom-nav" aria-label="منوی اصلی">
        {tabs.map((tab) => {
          const Icon = tab.icon

          return (
            <button
              key={tab.id}
              type="button"
              className={activeTab === tab.id ? 'nav-item active' : 'nav-item'}
              onClick={() => setActiveTab(tab.id)}
            >
              <Icon size={20} />
              <span>{tab.label}</span>
            </button>
          )
        })}
      </nav>
    </div>
  )
}

export default App
