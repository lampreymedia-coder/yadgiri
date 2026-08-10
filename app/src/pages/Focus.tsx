import { useEffect, useRef, useState } from 'react';
import { ambience, AMBIENCES, type AmbienceKind } from '../audio/engine';
import { setState } from '../lib/store';
import { dayKey } from '../lib/jalali';
import { toFa, secToClock } from '../lib/fmt';

const FOCUS_MINUTES = [25, 50, 70, 90];
const BREAK_MINUTES = [5, 15, 30];

type Phase = 'idle' | 'focus' | 'break';

export default function Focus() {
  const [focusMin, setFocusMin] = useState(50);
  const [breakMin, setBreakMin] = useState(10);
  const [phase, setPhase] = useState<Phase>('idle');
  const [running, setRunning] = useState(false);
  const [remaining, setRemaining] = useState(50 * 60);
  const [playing, setPlaying] = useState<AmbienceKind | null>(null);
  const [volume, setVolume] = useState(0.7);
  const endAtRef = useRef<number | null>(null);
  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);

  const totalSec = (phase === 'break' ? breakMin : focusMin) * 60;

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

  // جلوگیری از خاموش‌شدن صفحه هنگام تمرکز
  useEffect(() => {
    const nav = navigator as Navigator & {
      wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> };
    };
    if (running && nav.wakeLock) {
      nav.wakeLock.request('screen').then((l) => {
        wakeLockRef.current = l;
      }).catch(() => {});
    }
    return () => {
      wakeLockRef.current?.release().catch(() => {});
      wakeLockRef.current = null;
    };
  }, [running]);

  const logSession = (minutes: number) => {
    if (minutes < 5) return;
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
      // شروع خودکار استراحت
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
    // اگر صدایی انتخاب نشده، لوفای را خودکار شروع کن
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

  const displaySec = phase === 'idle' ? focusMin * 60 : remaining;
  const progress = phase === 'idle' ? 0 : 1 - remaining / totalSec;
  const R = 108;
  const C = 2 * Math.PI * R;

  return (
    <div className="focus-wrap">
      <div className="card">
        <h3 style={{ textAlign: 'right' }}>🎯 حالت تمرکز</h3>
        <p className="muted" style={{ textAlign: 'right', marginTop: -6 }}>
          مدت تمرکز را انتخاب کن، صدا را روشن کن و شروع بزن. بعد از پایان، استراحت
          خودکار شروع می‌شود.
        </p>

        <div className="timer-ring">
          <svg width="240" height="240">
            <circle cx="120" cy="120" r={R} fill="none" stroke="var(--card-2)" strokeWidth="12" />
            <circle
              cx="120"
              cy="120"
              r={R}
              fill="none"
              stroke={phase === 'break' ? 'var(--c-order)' : 'var(--c-accent)'}
              strokeWidth="12"
              strokeLinecap="round"
              strokeDasharray={C}
              strokeDashoffset={C * (1 - progress)}
              style={{ transition: 'stroke-dashoffset 0.4s linear' }}
            />
          </svg>
          <div className="time">
            <div className="phase">
              {phase === 'focus' && '🧠 در حال تمرکز'}
              {phase === 'break' && '☕ استراحت'}
              {phase === 'idle' && 'آماده‌ی شروع'}
            </div>
            <div className="clock">{secToClock(displaySec)}</div>
            {playing && (
              <div className="phase">
                {AMBIENCES.find((a) => a.kind === playing)?.title}
                <span className="eq">
                  <span /><span /><span />
                </span>
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, justifyContent: 'center', marginBottom: 14 }}>
          {phase === 'idle' && (
            <button className="btn btn-primary" style={{ maxWidth: 240 }} onClick={start}>
              ▶️ شروع تمرکز
            </button>
          )}
          {phase !== 'idle' && running && (
            <button className="btn btn-soft" onClick={pause}>⏸ مکث</button>
          )}
          {phase !== 'idle' && !running && (
            <button className="btn btn-primary" style={{ maxWidth: 200 }} onClick={resume}>
              ▶️ ادامه
            </button>
          )}
          {phase !== 'idle' && (
            <button className="btn btn-soft" onClick={reset}>⏹ پایان</button>
          )}
        </div>

        <div style={{ textAlign: 'right' }}>
          <div className="muted" style={{ marginBottom: 6, fontWeight: 700 }}>مدت تمرکز</div>
          <div className="chips" style={{ marginBottom: 12 }}>
            {FOCUS_MINUTES.map((m) => (
              <button
                key={m}
                className={`chip ${focusMin === m ? 'active' : ''}`}
                onClick={() => {
                  setFocusMin(m);
                  if (phase === 'idle') setRemaining(m * 60);
                }}
                disabled={phase !== 'idle'}
              >
                {toFa(m)} دقیقه
              </button>
            ))}
          </div>
          <div className="muted" style={{ marginBottom: 6, fontWeight: 700 }}>مدت استراحت</div>
          <div className="chips">
            {BREAK_MINUTES.map((m) => (
              <button
                key={m}
                className={`chip ${breakMin === m ? 'active' : ''}`}
                onClick={() => setBreakMin(m)}
              >
                {toFa(m)} دقیقه
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="card" style={{ textAlign: 'right' }}>
        <h3>🎵 صدای فضای تمرکز</h3>
        <p className="muted" style={{ marginTop: -6 }}>
          روی هر کدام بزنی همان لحظه پخش می‌شود — کاملاً آفلاین، بدون فایل و بدون حجم.
        </p>
        <div className="ambience-grid">
          {AMBIENCES.map((a) => (
            <button
              key={a.kind}
              className={`amb-card ${playing === a.kind ? 'playing' : ''}`}
              onClick={() => toggleAmbience(a.kind)}
            >
              <div className="emoji">{a.emoji}</div>
              <div className="name">
                {a.title}
                {playing === a.kind && (
                  <span className="eq"><span /><span /><span /></span>
                )}
              </div>
              <div className="desc">{a.desc}</div>
            </button>
          ))}
        </div>
        <div style={{ marginTop: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: '1.1rem' }}>🔉</span>
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
          />
          <span style={{ fontSize: '1.1rem' }}>🔊</span>
        </div>
      </div>
    </div>
  );
}
