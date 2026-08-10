import { useMemo, useState } from 'react';
import { useAppState, setState, PILLARS, type Pillar, type Review } from '../lib/store';
import { dayKey, addDays, toJalali, J_MONTHS, weekdayFa, keyToDate } from '../lib/jalali';
import { toFa } from '../lib/fmt';

const EMPTY_PILLARS: Record<Pillar, boolean> = {
  worship: false,
  knowledge: false,
  body: false,
  people: false,
  order: false,
};

export default function ReviewPage() {
  const state = useAppState();
  const today = new Date();
  const key = dayKey(today);
  const saved = state.reviews[key];

  // پیشنهاد اولیه‌ی ستون‌ها از روی تیک‌های امروز
  const suggested = useMemo(() => {
    const s = state.days[key]?.summary;
    if (!s) return EMPTY_PILLARS;
    const out = { ...EMPTY_PILLARS };
    for (const p of PILLARS) {
      const ps = s.pillars[p.code];
      out[p.code] = ps.total > 0 && ps.done / ps.total >= 0.6;
    }
    return out;
  }, [state.days, key]);

  const [pillars, setPillars] = useState<Record<Pillar, boolean>>(
    saved?.pillars ?? suggested,
  );
  const [bestMoment, setBestMoment] = useState(saved?.bestMoment ?? '');
  const [shortfall, setShortfall] = useState(saved?.shortfall ?? '');
  const [tomorrowChange, setTomorrowChange] = useState(saved?.tomorrowChange ?? '');
  const [t1, setT1] = useState(saved?.tomorrowTasks[0] ?? '');
  const [t2, setT2] = useState(saved?.tomorrowTasks[1] ?? '');
  const [t3, setT3] = useState(saved?.tomorrowTasks[2] ?? '');
  const [sleep, setSleep] = useState(saved?.sleepHours ? String(saved.sleepHours) : '');
  const [justSaved, setJustSaved] = useState(false);

  const score = Object.values(pillars).filter(Boolean).length;

  const save = () => {
    const review: Review = {
      date: key,
      pillars,
      bestMoment,
      shortfall,
      tomorrowChange,
      tomorrowTasks: [t1, t2, t3],
      sleepHours: sleep ? Number(sleep) : undefined,
      savedAt: Date.now(),
    };
    setState((p) => ({ ...p, reviews: { ...p.reviews, [key]: review } }));
    setJustSaved(true);
    window.setTimeout(() => setJustSaved(false), 2500);
  };

  // مرورهای ۷ روز گذشته
  const history = useMemo(() => {
    const out: Review[] = [];
    for (let i = 1; i <= 7; i += 1) {
      const r = state.reviews[dayKey(addDays(today, -i))];
      if (r) out.push(r);
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.reviews]);

  return (
    <>
      <div className="card">
        <h3>🌙 مرور و محاسبه‌ی امشب</h3>
        <p className="muted" style={{ marginTop: -4 }}>
          پنج دقیقه، پنج پرسش — بدون قضاوت، فقط ثبت. امتیاز امروز:{' '}
          <b style={{ color: 'var(--c-accent)' }}>{toFa(score)} از ۵</b>
        </p>

        <div className="section-title" style={{ marginTop: 8 }}>
          ۱️⃣ کدام ستون‌ها امروز سبز شدند؟
        </div>
        {PILLARS.map((p) => (
          <div
            key={p.code}
            className={`pillar-toggle ${pillars[p.code] ? 'on' : ''}`}
            onClick={() => setPillars((prev) => ({ ...prev, [p.code]: !prev[p.code] }))}
          >
            <span style={{ fontWeight: 700, fontSize: '0.88rem' }}>
              {p.emoji} {p.title}
            </span>
            <span style={{ fontSize: '1.1rem' }}>{pillars[p.code] ? '✅' : '⬜'}</span>
          </div>
        ))}

        <div className="section-title">۲️⃣ بهترین لحظه‌ی امروز چه بود؟</div>
        <div className="field">
          <input
            type="text"
            value={bestMoment}
            onChange={(e) => setBestMoment(e.target.value)}
            placeholder="یک جمله…"
          />
        </div>

        <div className="section-title">۳️⃣ کجا از خودم عقب ماندم؟</div>
        <div className="field">
          <input
            type="text"
            value={shortfall}
            onChange={(e) => setShortfall(e.target.value)}
            placeholder="فقط ثبت، بدون سرزنش…"
          />
        </div>

        <div className="section-title">۴️⃣ فردا یک چیز را متفاوت انجام می‌دهم:</div>
        <div className="field">
          <input
            type="text"
            value={tomorrowChange}
            onChange={(e) => setTomorrowChange(e.target.value)}
            placeholder="مثلاً: گوشی را زودتر کنار می‌گذارم"
          />
        </div>

        <div className="section-title">۵️⃣ سه کار مهم فردا</div>
        <p className="muted" style={{ marginTop: -6 }}>
          این سه کار، فردا خودکار در صفحه‌ی «امروز» ظاهر می‌شوند. 📌
        </p>
        {[
          [t1, setT1],
          [t2, setT2],
          [t3, setT3],
        ].map(([val, setter], i) => (
          <div className="field" key={i}>
            <input
              type="text"
              value={val as string}
              onChange={(e) => (setter as (v: string) => void)(e.target.value)}
              placeholder={`کار ${toFa(i + 1)}…`}
            />
          </div>
        ))}

        <div className="field">
          <label>🛌 دیشب چند ساعت خوابیدی؟ (اختیاری)</label>
          <input
            type="number"
            value={sleep}
            onChange={(e) => setSleep(e.target.value)}
            placeholder="۷"
            min="0"
            max="14"
            step="0.5"
          />
        </div>

        <button className="btn btn-primary" onClick={save}>
          {justSaved ? '✅ ثبت شد — شب بخیر!' : '💾 ثبت مرور امشب'}
        </button>
        {saved && !justSaved && (
          <p className="muted" style={{ textAlign: 'center', marginBottom: 0 }}>
            مرور امروز قبلاً ثبت شده؛ با ذخیره‌ی دوباره به‌روزرسانی می‌شود.
          </p>
        )}
      </div>

      {history.length > 0 && (
        <div className="card">
          <h3>🗓 مرورهای هفته‌ی گذشته</h3>
          {history.map((r) => {
            const d = keyToDate(r.date);
            const j = toJalali(d);
            const s = Object.values(r.pillars).filter(Boolean).length;
            return (
              <div
                key={r.date}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '10px 4px',
                  borderBottom: '1px solid var(--border)',
                  fontSize: '0.85rem',
                }}
              >
                <div>
                  <b>
                    {weekdayFa(d)} {toFa(j.jd)} {J_MONTHS[j.jm - 1]}
                  </b>
                  {r.bestMoment && (
                    <div className="muted" style={{ fontSize: '0.75rem' }}>
                      ✨ {r.bestMoment}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 3 }}>
                  {PILLARS.map((p) => (
                    <span
                      key={p.code}
                      className="pill-dot"
                      style={{
                        width: 12,
                        height: 12,
                        background: r.pillars[p.code]
                          ? 'var(--c-accent)'
                          : 'var(--card-2)',
                        border: '1px solid var(--border)',
                      }}
                      title={p.title}
                    />
                  ))}
                  <b style={{ marginInlineStart: 6 }}>{toFa(s)}/۵</b>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </>
  );
}
