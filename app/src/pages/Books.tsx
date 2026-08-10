import { useMemo, useState } from 'react';
import {
  useAppState,
  setState,
  uid,
  type ReadingBook,
} from '../lib/store';
import { BOOK_SUGGESTIONS, BOOK_CATEGORIES } from '../data/books';
import { dayKey, toJalali, J_MONTHS, jalaliMonthLength } from '../lib/jalali';
import { toFa } from '../lib/fmt';
import Icon from '../ui/Icon';

export default function Books() {
  const state = useAppState();
  const [cat, setCat] = useState<(typeof BOOK_CATEGORIES)[number]>('همه');
  const [showAdd, setShowAdd] = useState(false);
  const [logBookId, setLogBookId] = useState<string | null>(null);
  const [pages, setPages] = useState('10');

  const active = state.books.filter((b) => b.status === 'active');
  const done = state.books.filter((b) => b.status === 'done');

  const j = toJalali(new Date());
  const daysLeft = Math.max(1, jalaliMonthLength(j.jy, j.jm) - j.jd + 1);

  const suggestions = useMemo(
    () =>
      BOOK_SUGGESTIONS.filter(
        (b) => cat === 'همه' || b.category === cat,
      ).filter((b) => !state.books.some((x) => x.title === b.title)),
    [cat, state.books],
  );

  const adopt = (s: (typeof BOOK_SUGGESTIONS)[0]) => {
    const book: ReadingBook = {
      id: uid(),
      title: s.title,
      author: s.author,
      totalPages: s.pages,
      pagesRead: 0,
      status: 'active',
      startedAt: Date.now(),
    };
    // اگر کتاب فعالی هست، قبلی را متوقف کن
    setState((p) => ({
      ...p,
      books: [
        ...p.books.map((b) =>
          b.status === 'active' ? { ...b, status: 'paused' as const } : b,
        ),
        book,
      ],
    }));
  };

  const current = active[0];
  const dailyTarget = current
    ? Math.ceil((current.totalPages - current.pagesRead) / daysLeft)
    : 0;

  const logPages = () => {
    if (!logBookId) return;
    const n = Math.max(1, Number(pages) || 0);
    setState((p) => {
      const books = p.books.map((b) => {
        if (b.id !== logBookId) return b;
        const pagesRead = Math.min(b.totalPages, b.pagesRead + n);
        const finished = pagesRead >= b.totalPages;
        return {
          ...b,
          pagesRead,
          status: finished ? ('done' as const) : b.status,
          finishedAt: finished ? Date.now() : b.finishedAt,
        };
      });
      return {
        ...p,
        books,
        readingLogs: [
          ...p.readingLogs,
          { id: uid(), bookId: logBookId, date: dayKey(new Date()), pages: n, at: Date.now() },
        ],
      };
    });
    setLogBookId(null);
    setPages('10');
  };

  return (
    <>
      {current ? (
        <div className="card">
          <h3>کتاب ماه جاری</h3>
          <div style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
            <div className="book-cover">{current.title.slice(0, 1)}</div>
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 900, fontSize: '1.05rem' }}>{current.title}</div>
              <div className="muted">{current.author}</div>
              <div className="progress-line">
                <span
                  style={{
                    width: `${(current.pagesRead / current.totalPages) * 100}%`,
                  }}
                />
              </div>
              <div
                className="muted"
                style={{ marginTop: 6, display: 'flex', justifyContent: 'space-between' }}
              >
                <span>
                  {toFa(current.pagesRead)} از {toFa(current.totalPages)} صفحه
                </span>
                <span>
                  {toFa(Math.round((current.pagesRead / current.totalPages) * 100))}٪
                </span>
              </div>
              <div
                style={{
                  marginTop: 12,
                  padding: '10px 12px',
                  background: 'var(--card-2)',
                  borderRadius: 12,
                  fontSize: '0.85rem',
                }}
              >
                هدف امروز:{' '}
                <b style={{ color: 'var(--c-accent)' }}>{toFa(dailyTarget)} صفحه</b>
                <span className="muted">
                  {' '}
                  · تا پایان {J_MONTHS[j.jm - 1]} {toFa(daysLeft)} روز مانده
                </span>
              </div>
              <button
                className="btn btn-primary"
                style={{ marginTop: 12 }}
                onClick={() => {
                  setLogBookId(current.id);
                  setPages(String(dailyTarget || 10));
                }}
              >
                ثبت مطالعه‌ی امروز
              </button>
            </div>
          </div>
        </div>
      ) : (
        <div className="card empty-state">
          <div className="big">
            <Icon name="book" size={36} />
          </div>
          <div style={{ fontWeight: 800, color: 'var(--text-strong)' }}>
            هنوز کتاب فعالی ندارید
          </div>
          <div className="muted">
            از پیشنهادها یکی را انتخاب کنید یا کتاب خودتان را اضافه کنید.
          </div>
        </div>
      )}

      {active.length > 1 && (
        <div className="card">
          <h3>کتاب‌های دیگر در حال مطالعه</h3>
          {active.slice(1).map((b) => (
            <div key={b.id} className="book-card" onClick={() => setLogBookId(b.id)}>
              <div className="book-cover">{b.title.slice(0, 1)}</div>
              <div className="meta">
                <div className="title">{b.title}</div>
                <div className="author">{b.author}</div>
                <div className="progress-line">
                  <span style={{ width: `${(b.pagesRead / b.totalPages) * 100}%` }} />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="section-title">پیشنهادهای مطالعه</div>
      <p className="muted" style={{ marginTop: -6, marginBottom: 10 }}>
        چند گزینه‌ی خوب برای مسیر معنوی، رشد فردی و فرزندپروری — یا کتاب خودتان را
        اضافه کنید.
      </p>
      <div className="chips" style={{ marginBottom: 12 }}>
        {BOOK_CATEGORIES.map((c) => (
          <button
            key={c}
            className={`chip ${cat === c ? 'active' : ''}`}
            onClick={() => setCat(c)}
          >
            {c}
          </button>
        ))}
      </div>

      <div className="desktop-grid">
        {suggestions.map((s) => (
          <button key={s.id} className="book-card" onClick={() => adopt(s)}>
            <div
              className="book-cover"
              style={{
                background:
                  s.category === 'معنوی'
                    ? 'linear-gradient(160deg,#8b7cf6,#6366f1)'
                    : s.category === 'فرزندپروری'
                      ? 'linear-gradient(160deg,#fb7185,#f97366)'
                      : s.category === 'رشد فردی'
                        ? 'linear-gradient(160deg,#2dd4bf,#14b8a6)'
                        : 'linear-gradient(160deg,#38bdf8,#6366f1)',
              }}
            >
              {s.title.slice(0, 1)}
            </div>
            <div className="meta">
              <div className="title">{s.title}</div>
              <div className="author">
                {s.author} · {toFa(s.pages)} صفحه
              </div>
              <span className="tag">{s.category}</span>
              <div className="blurb">{s.blurb}</div>
            </div>
          </button>
        ))}
      </div>

      <button className="btn btn-ghost" style={{ width: '100%', marginTop: 8 }} onClick={() => setShowAdd(true)}>
        <Icon name="plus" size={16} />
        افزودن کتاب خودم
      </button>

      {done.length > 0 && (
        <div className="card" style={{ marginTop: 16 }}>
          <h3>کتاب‌های تمام‌شده</h3>
          {done.map((b) => (
            <div key={b.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border)' }}>
              <b>{b.title}</b>
              <div className="muted">{b.author}</div>
            </div>
          ))}
        </div>
      )}

      {showAdd && <AddBookModal onClose={() => setShowAdd(false)} />}

      {logBookId && (
        <div className="modal-backdrop" onClick={() => setLogBookId(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3 style={{ marginTop: 0 }}>ثبت صفحات امروز</h3>
            <div className="field">
              <label htmlFor="pages-read">چند صفحه خواندید؟</label>
              <input
                id="pages-read"
                name="pages"
                type="number"
                min="1"
                value={pages}
                onChange={(e) => setPages(e.target.value)}
                autoFocus
              />
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className="btn btn-primary" style={{ flex: 2 }} onClick={logPages}>
                ثبت
              </button>
              <button className="btn btn-soft" style={{ flex: 1 }} onClick={() => setLogBookId(null)}>
                انصراف
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function AddBookModal({ onClose }: { onClose: () => void }) {
  const [title, setTitle] = useState('');
  const [author, setAuthor] = useState('');
  const [total, setTotal] = useState('200');

  const save = () => {
    if (!title.trim()) return;
    const book: ReadingBook = {
      id: uid(),
      title: title.trim(),
      author: author.trim() || 'نامشخص',
      totalPages: Math.max(1, Number(total) || 200),
      pagesRead: 0,
      status: 'active',
      startedAt: Date.now(),
    };
    setState((p) => ({
      ...p,
      books: [
        ...p.books.map((b) =>
          b.status === 'active' ? { ...b, status: 'paused' as const } : b,
        ),
        book,
      ],
    }));
    onClose();
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginTop: 0 }}>کتاب جدید</h3>
        <div className="field">
          <label htmlFor="book-title">عنوان</label>
          <input
            id="book-title"
            name="title"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="نام کتاب"
            autoFocus
          />
        </div>
        <div className="field">
          <label htmlFor="book-author">نویسنده</label>
          <input
            id="book-author"
            name="author"
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="نام نویسنده"
          />
        </div>
        <div className="field">
          <label htmlFor="book-pages">تعداد صفحات</label>
          <input
            id="book-pages"
            name="pages"
            type="number"
            min="1"
            value={total}
            onChange={(e) => setTotal(e.target.value)}
          />
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-primary" style={{ flex: 2 }} onClick={save}>
            افزودن و شروع
          </button>
          <button className="btn btn-soft" style={{ flex: 1 }} onClick={onClose}>
            انصراف
          </button>
        </div>
      </div>
    </div>
  );
}
