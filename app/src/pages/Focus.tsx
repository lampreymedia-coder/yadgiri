import { useEffect, useMemo, useRef, useState } from 'react';
import { ambience, AMBIENCES, type AmbienceKind } from '../audio/engine';
import { setState, useAppState } from '../lib/store';
import { dayKey } from '../lib/jalali';
import { toFa, secToClock } from '../lib/fmt';
import Icon from '../ui/Icon';

const FOCUS_MINUTES = [25, 50, 70, 90];
const BREAK_MINUTES = [5, 10, 15, 30];

const PRESETS = [
  { id: 'pomodoro', title: 'پومودورو', focus: 25, break: 5, hint: 'کوتاه و پرتکرار' },
  { id: 'deep', title: 'عمیق', focus: 50, break: 10, hint: 'مطالعه و کار فکری' },
  { id: 'long', title: 'بلند', focus: 90, break: 15, hint: 'پروژه‌ی سنگین' },
] as const;

type Phase = 'idle' | 'focus' | 'break';

export default function Focus() {
  const state = useAppState();
  const [focusMin, setFocusMin] = useState(50);
  const [breakMin, setBreakMin] = useState(10);
  const [phase, setPhase] = useState<Phase>('idle');
  const [running, setRunning] = useState(false);
  const [remaining, setRemaining] = useState(50 * 60);
  const [playing, setPlaying] = useState<AmbienceKind | null>(null);
  const [volume, setVolume] = useState(0.72);
  const [preset, setPreset] = useState<string>('deep');
  const endAtRef = useRef<number | null>(null);
  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);

  const totalSec = (phase === 'break' ? breakMin : focusMin) * 60;

  const todayFocus = useMemo(() => {
    const key = dayKey(new Date());
    return state.focus
      .filter((f) => f.date === key)
      .reduce((a, b) => a + b.minutes, 0);
  }, [state.focus]);

  useEffect(() => {
    if (!running) return;
    const tick = window.setInterval(() => {
      if (endAtRef.current === null) return;
      const left = Math.max(0, Math.round((endAtRef.current - Date.now()) / 1000));
      setRemaining(left);
      if (left <= 0) onPhaseEnd();
    }, 400);
    return () => window.clearInterval(tick);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running, phase]);

  useEffect(() => {
    const nav = navigator as Navigator & {
      wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> };
    };
    if (running && nav.wakeLock) {
      nav.wakeLock
        .request('screen')
        .then((l) => {
          wakeLockRef.current = l;
        })
        .catch(() => {});
    }
    return () => {
      wakeLockRef.current?.release().catch(() => {});
      wakeLockRef.current = null;
    };
  }, [running]);

  const logSession = (minutes: number) => {
    if (minutes < 3) return;
    setState((p) => ({
      ...p,
      focus: [
        ...p.focus,
        { date: dayKey(new Date()), minutes, ambience: playing ?? 'silence', at: Date.now() },
      ],
    }));
  };

  const onPhaseEnd = () => {
    ambience.chime();
    if (phase === 'focus') {
      logSession(focusMin);
      setPhase('break');
      setRemaining(breakMin * 60);
      endAtRef.current = Date.now() + breakMin * 60 * 1000;
    } else {
      setPhase('idle');
      setRunning(false);
      setRemaining(focusMin * 60);
      endAtRef.current = null;
      ambience.stop();
      setPlaying(null);
    }
  };

  const start = () => {
    setPhase('focus');
    setRemaining(focusMin * 60);
    endAtRef.current = Date.now() + focusMin * 60 * 1000;
    setRunning(true);
    if (!ambience.current) {
      ambience.start('lofi');
      setPlaying('lofi');
    }
  };

  const pause = () => {
    setRunning(false);
    endAtRef.current = null;
  };

  const resume = () => {
    endAtRef.current = Date.now() + remaining * 1000;
    setRunning(true);
  };

  const reset = () => {
    if (phase === 'focus') {
      const elapsedMin = Math.round((focusMin * 60 - remaining) / 60);
      logSession(elapsedMin);
    }
    setPhase('idle');
    setRunning(false);
    setRemaining(focusMin * 60);
    endAtRef.current = null;
  };

  const toggleAmbience = (kind: AmbienceKind) => {
    if (playing === kind) {
      ambience.stop();
      setPlaying(null);
    } else {
      ambience.setVolume(volume);
      ambience.start(kind);
      setPlaying(kind);
    }
  };

  const applyPreset = (id: string) => {
    const p = PRESETS.find((x) => x.id === id);
    if (!p || phase !== 'idle') return;
    setPreset(id);
    setFocusMin(p.focus);
    setBreakMin(p.break);
    setRemaining(p.focus * 60);
  };

  const displaySec = phase === 'idle' ? focusMin * 60 : remaining;
  const progress = phase === 'idle' ? 0 : 1 - remaining / totalSec;
  const R = 110;
  const C = 2 * Math.PI * R;

  return (
    <div className="focus-wrap">
      <div className="desktop-grid">
        <div className="card">
          <h3 style={{ textAlign: 'right' }}>حالت تمرکز</h3>
          <p className="muted" style={{ textAlign: 'right', marginTop: -4 }}>
            مدت را انتخاب کنید، فضای صوتی را روشن کنید و شروع بزنید. پس از پایان،
            استراحت به‌صورت خودکار آغاز می‌شود.
          </p>

          <div className="preset-row">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                className={`preset ${preset === p.id ? 'active' : ''}`}
                onClick={() => applyPreset(p.id)}
                disabled={phase !== 'idle'}
              >
                <strong>{p.title}</strong>
                <span>
                  {toFa(p.focus)}/{toFa(p.break)} دقیقه
                </span>
              </button>
            ))}
          </div>

          <div className="timer-ring">
            <svg width="250" height="250">
              <circle cx="125" cy="125" r={R} fill="none" stroke="var(--card-2)" strokeWidth="11" />
              <circle
                cx="125"
                cy="125"
                r={R}
                fill="none"
                stroke={phase === 'break' ? 'var(--c-order)' : 'var(--c-accent)'}
                strokeWidth="11"
                strokeLinecap="round"
                strokeDasharray={C}
                strokeDashoffset={C * (1 - progress)}
                style={{ transition: 'stroke-dashoffset 0.4s linear' }}
              />
            </svg>
            <div className="time">
              <div className="phase">
                {phase === 'focus' && 'در حال تمرکز'}
                {phase === 'break' && 'زمان استراحت'}
                {phase === 'idle' && 'آماده‌ی شروع'}
              </div>
              <div className="clock">{secToClock(displaySec)}</div>
              {playing && (
                <div className="phase">
                  {AMBIENCES.find((a) => a.kind === playing)?.title}
                  <span className="eq">
                    <span />
                    <span />
                    <span />
                  </span>
                </div>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 14 }}>
            {phase === 'idle' && (
              <button className="btn btn-primary" style={{ maxWidth: 240 }} onClick={start}>
                <Icon name="play" size={16} />
                شروع تمرکز
              </button>
            )}
            {phase !== 'idle' && running && (
              <button className="btn btn-soft" onClick={pause}>
                <Icon name="pause" size={16} />
                مکث
              </button>
            )}
            {phase !== 'idle' && !running && (
              <button className="btn btn-primary" style={{ maxWidth: 200 }} onClick={resume}>
                <Icon name="play" size={16} />
                ادامه
              </button>
            )}
            {phase !== 'idle' && (
              <button className="btn btn-soft" onClick={reset}>
                <Icon name="stop" size={16} />
                پایان
              </button>
            )}
          </div>

          <div style={{ textAlign: 'right' }}>
            <div className="muted" style={{ marginBottom: 6, fontWeight: 700 }}>
              مدت تمرکز
            </div>
            <div className="chips" style={{ marginBottom: 12 }}>
              {FOCUS_MINUTES.map((m) => (
                <button
                  key={m}
                  className={`chip ${focusMin === m ? 'active' : ''}`}
                  onClick={() => {
                    setFocusMin(m);
                    setPreset('');
                    if (phase === 'idle') setRemaining(m * 60);
                  }}
                  disabled={phase !== 'idle'}
                >
                  {toFa(m)} دقیقه
                </button>
              ))}
            </div>
            <div className="muted" style={{ marginBottom: 6, fontWeight: 700 }}>
              مدت استراحت
            </div>
            <div className="chips">
              {BREAK_MINUTES.map((m) => (
                <button
                  key={m}
                  className={`chip ${breakMin === m ? 'active' : ''}`}
                  onClick={() => {
                    setBreakMin(m);
                    setPreset('');
                  }}
                >
                  {toFa(m)} دقیقه
                </button>
              ))}
            </div>
          </div>
        </div>

        <div>
          <div className="card" style={{ textAlign: 'right' }}>
            <h3>فضای صوتی تمرکز</h3>
            <p className="muted" style={{ marginTop: -4 }}>
              صداهای کوزی و دلنشین — با یک لمس پخش می‌شوند؛ کاملاً آفلاین و بدون حجم.
            </p>
            <div className="ambience-grid">
              {AMBIENCES.map((a) => (
                <button
                  key={a.kind}
                  className={`amb-card ${playing === a.kind ? 'playing' : ''}`}
                  onClick={() => toggleAmbience(a.kind)}
                >
                  <div className="ico-wrap">
                    <Icon name={a.icon} size={20} />
                  </div>
                  <div className="name">
                    {a.title}
                    {playing === a.kind && (
                      <span className="eq">
                        <span />
                        <span />
                        <span />
                      </span>
                    )}
                  </div>
                  <div className="desc">{a.desc}</div>
                </button>
              ))}
            </div>
            <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
              <Icon name="wind" size={16} />
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={volume}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  setVolume(v);
                  ambience.setVolume(v);
                }}
                style={{ flex: 1, accentColor: 'var(--c-accent)' }}
                aria-label="بلندی صدا"
              />
              <Icon name="headphones" size={16} />
            </div>
          </div>

          <div className="card">
            <h3>تمرکز امروز</h3>
            <div className="stat-grid">
              <div className="stat">
                <div className="num">{toFa(todayFocus)}</div>
                <div className="lbl">دقیقه تمرکز ثبت‌شده</div>
              </div>
              <div className="stat">
                <div className="num">
                  {toFa(state.focus.filter((f) => f.date === dayKey(new Date())).length)}
                </div>
                <div className="lbl">جلسه‌ی امروز</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
