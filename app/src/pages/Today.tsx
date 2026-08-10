import { useEffect, useMemo, useState } from 'react';
import {
  useAppState,
  setState,
  getDayState,
  updateDay,
  uid,
  PILLARS,
  PILLAR_TITLE,
  type Pillar,
  type Intensity,
  type CustomHabit,
} from '../lib/store';
import { generateDayPlan, summarize, nowAndNext, type Task } from '../engine/plan';
import { toJalali, J_MONTHS, weekdayFa, dayKey, WEEKDAYS_FA } from '../lib/jalali';
import { toFa, minToTime, durationFa } from '../lib/fmt';

const PILLAR_COLOR: Record<Pillar, string> = {
  worship: 'var(--c-worship)',
  knowledge: 'var(--c-knowledge)',
  body: 'var(--c-body)',
  people: 'var(--c-people)',
  order: 'var(--c-order)',
};

const INTENSITIES: { code: Intensity; title: string; hint: string }[] = [
  { code: 'min', title: '🪨 کف', hint: 'روز سخت — فقط ضروری‌ها' },
  { code: 'normal', title: '⚖️ عادی', hint: 'برنامه‌ی کامل روز' },
  { code: 'peak', title: '🔥 اوج', hint: 'روز پرانرژی' },
];

function Ring({ value, color, size = 40 }: { value: number; color: string; size?: number }) {
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} className="ring" style={{ display: 'block' }}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--card-2)" strokeWidth="5" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke={color}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={c * (1 - value)}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        style={{ transition: 'stroke-dashoffset 0.5s ease' }}
      />
    </svg>
  );
}

export default function Today() {
  const state = useAppState();
  const [nowMin, setNowMin] = useState(() => {
    const d = new Date();
    return d.getHours() * 60 + d.getMinutes();
  });
  const [fading, setFading] = useState<Set<string>>(new Set());
  const [showAdd, setShowAdd] = useState(false);

  useEffect(() => {
    const t = window.setInterval(() => {
      const d = new Date();
      setNowMin(d.getHours() * 60 + d.getMinutes());
    }, 30000);
    return () => window.clearInterval(t);
  }, []);

  const today = new Date();
  const key = dayKey(today);
  const dayState = state.days[key] ?? getDayState(key);
  const intensity = dayState.intensity ?? 'normal';

  const plan = useMemo(
    () => generateDayPlan(today, state, intensity),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [key, state.habits, state.reviews, state.city, intensity],
  );

  const checks = dayState.checks ?? {};
  const summary = summarize(plan.tasks, checks);
  const { current, next } = nowAndNext(plan.tasks, nowMin, checks);

  const j = toJalali(today);
  const dateLine = `${weekdayFa(today)} ${toFa(j.jd)} ${J_MONTHS[j.jm - 1]} ${toFa(j.jy)}`;

  const toggle = (task: Task) => {
    const isDone = !!checks[task.id];
    if (!isDone) {
      // انیمیشن محو، سپس ثبت
      setFading((prev) => new Set(prev).add(task.id));
      window.setTimeout(() => {
        setFading((prev) => {
          const n = new Set(prev);
          n.delete(task.id);
          return n;
        });
        const newChecks = { ...getDayState(key).checks, [task.id]: true };
        updateDay(key, {
          checks: newChecks,
          intensity,
          summary: summarize(plan.tasks, newChecks),
        });
      }, 420);
    } else {
      const newChecks = { ...checks, [task.id]: false };
      updateDay(key, {
        checks: newChecks,
        intensity,
        summary: summarize(plan.tasks, newChecks),
      });
    }
  };

  const setIntensity = (code: Intensity) => {
    updateDay(key, { intensity: code });
  };

  const removeHabit = (habitId: string) => {
    if (!confirm('این برنامه حذف شود؟')) return;
    setState((p) => ({ ...p, habits: p.habits.filter((h) => h.id !== habitId) }));
  };

  const pending = plan.tasks.filter((t) => !checks[t.id]);
  const done = plan.tasks.filter((t) => checks[t.id]);
  const pct = summary.total ? summary.done / summary.total : 0;

  return (
    <>
      <div className="card" style={{ paddingBottom: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ fontWeight: 900, fontSize: '1.05rem' }}>{dateLine}</div>
            <div className="muted" style={{ marginTop: 2 }}>
              {plan.templateTitle} · {plan.mission}
            </div>
          </div>
          <div style={{ position: 'relative', width: 54, height: 54 }}>
            <Ring value={pct} color="var(--c-accent)" size={54} />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'grid',
                placeItems: 'center',
                fontSize: '0.72rem',
                fontWeight: 900,
              }}
            >
              {toFa(Math.round(pct * 100))}٪
            </div>
          </div>
        </div>
        <div className="chips" style={{ marginTop: 12 }}>
          {INTENSITIES.map((i) => (
            <button
              key={i.code}
              className={`chip ${intensity === i.code ? 'active' : ''}`}
              onClick={() => setIntensity(i.code)}
              title={i.hint}
            >
              {i.title}
            </button>
          ))}
        </div>
      </div>

      {current && (
        <div className="now-card">
          <div className="label">⏱ اکنون</div>
          <div className="block-title">{current.title}</div>
          <div className="muted" style={{ marginBottom: 10 }}>
            {minToTime(current.start!)}
            {current.duration > 0 && ` · ${durationFa(current.duration)}`}
            {next && ` — بعدی: ${next.title} (${minToTime(next.start!)})`}
          </div>
          <button className="btn btn-primary" onClick={() => toggle(current)}>
            ✅ انجام شد
          </button>
        </div>
      )}
      {!current && next && (
        <div className="now-card">
          <div className="label">🔜 برنامه‌ی بعدی</div>
          <div className="block-title">{next.title}</div>
          <div className="muted">ساعت {minToTime(next.start!)}</div>
        </div>
      )}

      <div className="card">
        <div className="pillars-row">
          {PILLARS.map((p) => {
            const s = summary.pillars[p.code];
            return (
              <div className="pillar-cell" key={p.code}>
                <Ring
                  value={s.total ? s.done / s.total : 0}
                  color={PILLAR_COLOR[p.code]}
                />
                <div className="name">
                  {p.emoji} {p.title}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="section-title">📋 کارهای امروز ({toFa(pending.length)})</div>
      {pending.length === 0 ? (
        <div className="card empty-state">
          <div className="big">🎉</div>
          <div style={{ fontWeight: 800 }}>همه‌ی کارهای امروز انجام شد!</div>
          <div className="muted">آفرین! نمودار رشدت خودش جلو رفت.</div>
        </div>
      ) : (
        pending.map((t) => (
          <div key={t.id} className={`task ${fading.has(t.id) ? 'fading' : ''}`}>
            <button
              className={`check ${fading.has(t.id) ? 'on' : ''}`}
              onClick={() => toggle(t)}
              aria-label="انجام شد"
            >
              ✓
            </button>
            <div style={{ flex: 1 }}>
              <div className="t-title">{t.title}</div>
              <div className="t-meta">
                <span
                  className="pill-dot"
                  style={{ background: PILLAR_COLOR[t.pillar] }}
                />
                {PILLAR_TITLE[t.pillar]}
                {t.duration > 0 && <span>· {durationFa(t.duration)}</span>}
                {t.source === 'review' && <span>· 📌 از مرور دیشب</span>}
                {t.isDeep && <span>· 🧠 عمیق</span>}
              </div>
            </div>
            {t.start !== undefined && (
              <span className="time-badge">{minToTime(t.start)}</span>
            )}
            {t.source === 'habit' && (
              <button
                className="icon-btn"
                style={{ width: 30, height: 30, fontSize: '0.7rem' }}
                onClick={() => removeHabit(t.id.slice(2))}
              >
                ✕
              </button>
            )}
          </div>
        ))
      )}

      {done.length > 0 && (
        <details className="done-list">
          <summary>✅ انجام‌شده‌های امروز ({toFa(done.length)}) — نمایش/پنهان</summary>
          {done.map((t) => (
            <div key={t.id} className="task" style={{ opacity: 0.55 }}>
              <button className="check on" onClick={() => toggle(t)}>
                ✓
              </button>
              <div className="t-title" style={{ textDecoration: 'line-through' }}>
                {t.title}
              </div>
            </div>
          ))}
        </details>
      )}

      <button className="fab" onClick={() => setShowAdd(true)}>
        ＋ برنامه‌ی جدید
      </button>

      {showAdd && <AddModal onClose={() => setShowAdd(false)} todayKey={key} />}
    </>
  );
}

function AddModal({ onClose, todayKey }: { onClose: () => void; todayKey: string }) {
  const [title, setTitle] = useState('');
  const [pillar, setPillar] = useState<Pillar>('order');
  const [time, setTime] = useState('');
  const [duration, setDuration] = useState('');
  const [repeat, setRepeat] = useState(false);
  const [weekdays, setWeekdays] = useState<number[]>([]);

  const save = () => {
    if (!title.trim()) return;
    const habit: CustomHabit = {
      id: uid(),
      title: title.trim(),
      pillar,
      weekdays: repeat ? weekdays : [],
      date: repeat ? undefined : todayKey,
      time: time || undefined,
      durationMinutes: duration ? Number(duration) : undefined,
      createdAt: Date.now(),
    };
    setState((p) => ({ ...p, habits: [...p.habits, habit] }));
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>➕ برنامه یا جلسه‌ی جدید</h3>
        <div className="field">
          <label>عنوان</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="مثلاً: جلسه‌ی مطالعه با دوستان"
            autoFocus
          />
        </div>
        <div className="field">
          <label>ستون مرتبط</label>
          <select value={pillar} onChange={(e) => setPillar(e.target.value as Pillar)}>
            {PILLARS.map((p) => (
              <option key={p.code} value={p.code}>
                {p.emoji} {p.title}
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <div className="field" style={{ flex: 1 }}>
            <label>ساعت (اختیاری)</label>
            <input type="time" value={time} onChange={(e) => setTime(e.target.value)} />
          </div>
          <div className="field" style={{ flex: 1 }}>
            <label>مدت (دقیقه)</label>
            <input
              type="number"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              placeholder="۳۰"
              min="0"
            />
          </div>
        </div>
        <div className="field">
          <label>
            <input
              type="checkbox"
              checked={repeat}
              onChange={(e) => setRepeat(e.target.checked)}
              style={{ marginInlineEnd: 6 }}
            />
            تکرار هفتگی (عادت جدید)
          </label>
          {repeat && (
            <div className="weekday-picker" style={{ marginTop: 8 }}>
              {[6, 0, 1, 2, 3, 4, 5].map((wd) => (
                <button
                  key={wd}
                  className={`wd ${weekdays.includes(wd) ? 'on' : ''}`}
                  onClick={() =>
                    setWeekdays((prev) =>
                      prev.includes(wd) ? prev.filter((x) => x !== wd) : [...prev, wd],
                    )
                  }
                >
                  {WEEKDAYS_FA[wd]}
                </button>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" style={{ flex: 2 }} onClick={save}>
            ذخیره
          </button>
          <button className="btn btn-soft" style={{ flex: 1 }} onClick={onClose}>
            انصراف
          </button>
        </div>
      </div>
    </div>
  );
}
