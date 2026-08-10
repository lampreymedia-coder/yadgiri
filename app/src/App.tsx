import { useEffect, useState } from 'react';
import { useAppState, setState, exportJSON, importJSON } from './lib/store';
import Icon from './ui/Icon';
import Today from './pages/Today';
import Progress from './pages/Progress';
import Focus from './pages/Focus';
import Review from './pages/Review';
import Books from './pages/Books';

export type Tab = 'today' | 'progress' | 'focus' | 'books' | 'review';

const TABS: { id: Tab; title: string; icon: string }[] = [
  { id: 'today', title: 'امروز', icon: 'today' },
  { id: 'progress', title: 'روند رشد', icon: 'progress' },
  { id: 'focus', title: 'حالت تمرکز', icon: 'focus' },
  { id: 'books', title: 'کتاب‌خانه', icon: 'book' },
  { id: 'review', title: 'مرور روز', icon: 'review' },
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
    meta?.setAttribute('content', state.theme === 'dark' ? '#0b0f1a' : '#f3f5fb');
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
      alert(ok ? 'بازیابی با موفقیت انجام شد.' : 'فایل نامعتبر است.');
    };
    input.click();
  };

  const NavButtons = ({ className }: { className?: string }) => (
    <div className={className}>
      {TABS.map((t) => (
        <button
          key={t.id}
          className={`nav-item ${tab === t.id ? 'active' : ''}`}
          onClick={() => setTab(t.id)}
        >
          <Icon name={t.icon} size={20} />
          {t.title}
        </button>
      ))}
    </div>
  );

  return (
    <div className="shell">
      <aside className="side-rail">
        <div className="side-brand">
          <div className="brand-mark">
            <Icon name="check" size={20} />
          </div>
          <div>
            <div className="brand-title">روزنما</div>
            <div className="brand-sub">زندگی، رشد، تمرکز</div>
          </div>
        </div>
        <NavButtons className="side-nav" />
        <div className="side-foot">کاملاً آفلاین و خصوصی · روی همین دستگاه</div>
      </aside>

      <div className="shell-body">
        <div className="main-pane">
          <header className="topbar">
            <div className="brand">
              <div className="brand-mark">
                <Icon name="check" size={18} />
              </div>
              <div>
                <p className="brand-title">روزنما</p>
                <p className="brand-sub">برنامه‌ی زندگی، رشد و تمرکز</p>
              </div>
            </div>
            <div className="top-actions">
              <button
                className="icon-btn"
                onClick={toggleTheme}
                title={state.theme === 'dark' ? 'حالت روز' : 'حالت شب'}
                aria-label="تعویض تم"
              >
                <Icon name={state.theme === 'dark' ? 'sun' : 'moon'} size={18} />
              </button>
              <button
                className="icon-btn"
                onClick={() => setShowSettings(true)}
                title="تنظیمات"
                aria-label="تنظیمات"
              >
                <Icon name="settings" size={18} />
              </button>
            </div>
          </header>

          <main className="content">
            {tab === 'today' && <Today />}
            {tab === 'progress' && <Progress />}
            {tab === 'focus' && <Focus />}
            {tab === 'books' && <Books />}
            {tab === 'review' && <Review />}
          </main>
        </div>
      </div>

      <nav className="bottom-nav">
        <NavButtons className="max" />
      </nav>

      {showSettings && (
        <div className="modal-backdrop" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>تنظیمات</h3>
            <div className="field">
              <label htmlFor="city-select">شهر برای محاسبه‌ی اوقات شرعی</label>
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
              رایانه از خروجی JSON استفاده کنید.
            </p>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-soft" style={{ flex: 1 }} onClick={doExport}>
                <Icon name="export" size={16} />
                گرفتن پشتیبان
              </button>
              <button className="btn btn-soft" style={{ flex: 1 }} onClick={doImport}>
                <Icon name="import" size={16} />
                بازیابی
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
