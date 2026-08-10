import { useEffect, useState } from 'react';
import { useAppState, setState, exportJSON, importJSON } from './lib/store';
import Today from './pages/Today';
import Progress from './pages/Progress';
import Focus from './pages/Focus';
import Review from './pages/Review';

type Tab = 'today' | 'progress' | 'focus' | 'review';

const TABS: { id: Tab; title: string; ico: string }[] = [
  { id: 'today', title: 'امروز', ico: '☀️' },
  { id: 'progress', title: 'روند رشد', ico: '📈' },
  { id: 'focus', title: 'حالت تمرکز', ico: '🎯' },
  { id: 'review', title: 'مرور روز', ico: '🌙' },
];

const CITIES = [
  { name: 'تهران', lat: 35.6892, lng: 51.389 },
  { name: 'مشهد', lat: 36.2605, lng: 59.6168 },
  { name: 'اصفهان', lat: 32.6539, lng: 51.666 },
  { name: 'شیراز', lat: 29.5918, lng: 52.5837 },
  { name: 'تبریز', lat: 38.0962, lng: 46.2738 },
  { name: 'قم', lat: 34.6416, lng: 50.8746 },
  { name: 'اهواز', lat: 31.3183, lng: 48.6706 },
  { name: 'کرج', lat: 35.8327, lng: 50.9916 },
];

export default function App() {
  const state = useAppState();
  const [tab, setTab] = useState<Tab>('today');
  const [showSettings, setShowSettings] = useState(false);

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', state.theme);
    const meta = document.querySelector('meta[name="theme-color"]');
    meta?.setAttribute('content', state.theme === 'dark' ? '#0e1120' : '#f4f6fc');
  }, [state.theme]);

  const toggleTheme = () =>
    setState((p) => ({ ...p, theme: p.theme === 'dark' ? 'light' : 'dark' }));

  const doExport = () => {
    const blob = new Blob([exportJSON()], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `rooznama-backup-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  const doImport = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'application/json';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      const ok = importJSON(await file.text());
      alert(ok ? 'بازیابی با موفقیت انجام شد ✅' : 'فایل نامعتبر است ❌');
    };
    input.click();
  };

  return (
    <div className="app">
      <div className="header">
        <div>
          <div className="title">روزنما ✨</div>
          <div className="subtitle">برنامه‌ی زندگی، رشد و تمرکز</div>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="icon-btn"
            onClick={toggleTheme}
            title={state.theme === 'dark' ? 'حالت روز' : 'حالت شب'}
          >
            {state.theme === 'dark' ? '☀️' : '🌙'}
          </button>
          <button className="icon-btn" onClick={() => setShowSettings(true)} title="تنظیمات">
            ⚙️
          </button>
        </div>
      </div>

      {tab === 'today' && <Today />}
      {tab === 'progress' && <Progress />}
      {tab === 'focus' && <Focus />}
      {tab === 'review' && <Review />}

      <nav className="bottom-nav">
        <div className="max">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`nav-item ${tab === t.id ? 'active' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <span className="ico">{t.ico}</span>
              {t.title}
            </button>
          ))}
        </div>
      </nav>

      {showSettings && (
        <div className="modal-backdrop" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>تنظیمات</h3>
            <div className="field">
              <label htmlFor="city-select">شهر (برای محاسبه‌ی اوقات شرعی — کاملاً آفلاین)</label>
              <select
                id="city-select"
                name="city"
                value={state.city.name}
                onChange={(e) => {
                  const c = CITIES.find((x) => x.name === e.target.value);
                  if (c) setState((p) => ({ ...p, city: c }));
                }}
              >
                {CITIES.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="section-title">پشتیبان‌گیری</div>
            <p className="muted">
              همه‌ی داده‌ها فقط روی همین دستگاه ذخیره می‌شود. برای جابه‌جایی بین گوشی و
              رایانه، از خروجی JSON استفاده کنید.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-soft" style={{ flex: 1 }} onClick={doExport}>
                📤 گرفتن پشتیبان
              </button>
              <button className="btn btn-soft" style={{ flex: 1 }} onClick={doImport}>
                📥 بازیابی پشتیبان
              </button>
            </div>
            <button
              className="btn btn-primary"
              style={{ marginTop: 16 }}
              onClick={() => setShowSettings(false)}
            >
              بستن
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
