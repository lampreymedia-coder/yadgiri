import { useMemo, useState } from 'react';
import { useAppState, PILLARS, type Pillar } from '../lib/store';
import { toJalali, J_MONTHS, dayKey, addDays, WEEKDAYS_FA, jalaliToDate, jalaliMonthLength } from '../lib/jalali';
import { toFa } from '../lib/fmt';

type Range = 'week' | 'month' | 'year';

const PILLAR_COLOR: Record<Pillar, string> = {
  worship: 'var(--c-worship)',
  knowledge: 'var(--c-knowledge)',
  body: 'var(--c-body)',
  people: 'var(--c-people)',
  order: 'var(--c-order)',
};

export default function Progress() {
  const state = useAppState();
  const [range, setRange] = useState<Range>('week');
  const today = new Date();

  /** درصد انجام یک روز؛ null یعنی داده‌ای ثبت نشده */
  const dayPct = (d: Date): number | null => {
    const s = state.days[dayKey(d)]?.summary;
    if (!s || s.total === 0) return null;
    return s.done / s.total;
  };

  // --- هفته: ۷ روز اخیر (امروز آخرین ستون)
  const weekData = useMemo(() => {
    const out: { label: string; pct: number | null }[] = [];
    for (let i = 6; i >= 0; i -= 1) {
      const d = addDays(today, -i);
      out.push({
        label: WEEKDAYS_FA[d.getDay()].slice(0, 1),
        pct: dayPct(d),
      });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.days]);

  // --- ماه: هیت‌مپ ماه جلالی جاری
  const j = toJalali(today);
  const monthLen = jalaliMonthLength(j.jy, j.jm);
  const monthCells = useMemo(() => {
    const cells: { day: number; pct: number | null; isFuture: boolean }[] = [];
    for (let d = 1; d <= monthLen; d += 1) {
      const date = jalaliToDate(j.jy, j.jm, d);
      cells.push({
        day: d,
        pct: dayPct(date),
        isFuture: date > today,
      });
    }
    return cells;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.days, j.jy, j.jm]);

  // --- سال: میانگین هر ماه جلالی سال جاری
  const yearData = useMemo(() => {
    const out: { label: string; pct: number | null }[] = [];
    for (let m = 1; m <= 12; m += 1) {
      const len = jalaliMonthLength(j.jy, m);
      let sum = 0;
      let count = 0;
      for (let d = 1; d <= len; d += 1) {
        const p = dayPct(jalaliToDate(j.jy, m, d));
        if (p !== null) {
          sum += p;
          count += 1;
        }
      }
      out.push({ label: J_MONTHS[m - 1].slice(0, 3), pct: count ? sum / count : null });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.days, j.jy]);

  // --- آمار کلی
  const stats = useMemo(() => {
    let steady = 0; // روزهای ≥۸۰٪ در ۳۰ روز اخیر
    let recorded = 0;
    let totalDone = 0;
    for (let i = 0; i < 30; i += 1) {
      const s = state.days[dayKey(addDays(today, -i))]?.summary;
      if (s && s.total > 0) {
        recorded += 1;
        totalDone += s.done;
        if (s.done / s.total >= 0.8) steady += 1;
      }
    }
    const focus30 = state.focus
      .filter((f) => {
        const d = new Date(f.at);
        return (today.getTime() - d.getTime()) / 86400000 <= 30;
      })
      .reduce((a, b) => a + b.minutes, 0);
    const reviews30 = Object.values(state.reviews).filter((r) => {
      const d = new Date(r.savedAt);
      return (today.getTime() - d.getTime()) / 86400000 <= 30;
    }).length;
    return { steady, recorded, totalDone, focus30, reviews30 };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.days, state.focus, state.reviews]);

  // --- ستون‌های پنج‌گانه در ۷ روز اخیر
  const pillarWeek = useMemo(() => {
    const acc: Record<Pillar, { done: number; total: number }> = {
      worship: { done: 0, total: 0 },
      knowledge: { done: 0, total: 0 },
      body: { done: 0, total: 0 },
      people: { done: 0, total: 0 },
      order: { done: 0, total: 0 },
    };
    for (let i = 0; i < 7; i += 1) {
      const s = state.days[dayKey(addDays(today, -i))]?.summary;
      if (!s) continue;
      for (const p of PILLARS) {
        acc[p.code].done += s.pillars[p.code].done;
        acc[p.code].total += s.pillars[p.code].total;
      }
    }
    return acc;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.days]);

  const bars = range === 'week' ? weekData : range === 'year' ? yearData : null;

  return (
    <>
      <div className="range-tabs">
        {(
          [
            ['week', 'هفته'],
            ['month', 'ماه'],
            ['year', 'سال'],
          ] as [Range, string][]
        ).map(([r, label]) => (
          <button key={r} className={range === r ? 'active' : ''} onClick={() => setRange(r)}>
            {label}
          </button>
        ))}
      </div>

      <div className="card">
        <h3>
          {range === 'week' && '📊 درصد انجام برنامه — ۷ روز اخیر'}
          {range === 'month' && `📅 ${J_MONTHS[j.jm - 1]} ${toFa(j.jy)}`}
          {range === 'year' && `📊 میانگین ماه‌های سال ${toFa(j.jy)}`}
        </h3>

        {bars && (
          <div className="bars">
            {bars.map((b, i) => (
              <div className="bar-col" key={i}>
                <span className="bar-label" style={{ minHeight: 14 }}>
                  {b.pct !== null ? `${toFa(Math.round(b.pct * 100))}٪` : ''}
                </span>
                <div
                  className={`bar ${b.pct === null ? 'empty' : ''}`}
                  style={{ height: `${Math.max(3, (b.pct ?? 0) * 100)}%` }}
                />
                <span className="bar-label">{b.label}</span>
              </div>
            ))}
          </div>
        )}

        {range === 'month' && (
          <div className="heatmap">
            {monthCells.map((c) => (
              <div
                key={c.day}
                className="heat-cell"
                style={
                  c.pct !== null
                    ? {
                        background: `color-mix(in srgb, var(--c-accent) ${Math.round(
                          20 + c.pct * 80,
                        )}%, var(--card-2))`,
                        color: c.pct > 0.5 ? '#04231b' : undefined,
                        fontWeight: 700,
                      }
                    : c.isFuture
                      ? { opacity: 0.35 }
                      : undefined
                }
                title={c.pct !== null ? `${Math.round(c.pct * 100)}٪` : ''}
              >
                {toFa(c.day)}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card">
        <h3>🏆 آمار ۳۰ روز اخیر</h3>
        <div className="stat-grid">
          <div className="stat">
            <div className="num">{toFa(stats.steady)}</div>
            <div className="lbl">روزِ درخشان (≥۸۰٪) از ۳۰ روز</div>
          </div>
          <div className="stat">
            <div className="num">{toFa(stats.totalDone)}</div>
            <div className="lbl">کار انجام‌شده</div>
          </div>
          <div className="stat">
            <div className="num">{toFa(stats.focus30)}</div>
            <div className="lbl">دقیقه تمرکز عمیق</div>
          </div>
          <div className="stat">
            <div className="num">{toFa(stats.reviews30)}</div>
            <div className="lbl">مرور شبانه ثبت‌شده</div>
          </div>
        </div>
      </div>

      <div className="card">
        <h3>🧭 پنج ستون زندگی — این هفته</h3>
        {PILLARS.map((p) => {
          const s = pillarWeek[p.code];
          const pct = s.total ? s.done / s.total : 0;
          return (
            <div key={p.code} style={{ marginBottom: 10 }}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.8rem',
                  fontWeight: 700,
                  marginBottom: 4,
                }}
              >
                <span>
                  {p.emoji} {p.title}
                </span>
                <span className="muted">
                  {toFa(s.done)} از {toFa(s.total)}
                </span>
              </div>
              <div
                style={{
                  height: 10,
                  borderRadius: 8,
                  background: 'var(--card-2)',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${pct * 100}%`,
                    height: '100%',
                    borderRadius: 8,
                    background: PILLAR_COLOR[p.code],
                    transition: 'width 0.5s ease',
                  }}
                />
              </div>
            </div>
          );
        })}
        {Object.values(pillarWeek).every((s) => s.total === 0) && (
          <p className="muted">
            هنوز داده‌ای ثبت نشده — از صفحه‌ی «امروز» شروع کن و کارها را تیک بزن؛ این
            نمودارها خودشان جلو می‌روند. 🌱
          </p>
        )}
      </div>
    </>
  );
}
