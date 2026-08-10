// تولید آیکون‌های PNG بدون هیچ وابستگی — رمزگذار PNG خالص
import { deflateSync } from 'node:zlib';
import { writeFileSync, mkdirSync } from 'node:fs';

function crc32(buf) {
  let table = crc32.table;
  if (!table) {
    table = crc32.table = new Int32Array(256).map((_, n) => {
      let c = n;
      for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      return c;
    });
  }
  let crc = -1;
  for (const b of buf) crc = (crc >>> 8) ^ table[(crc ^ b) & 0xff];
  return (crc ^ -1) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}

function encodePNG(size, rgba) {
  const raw = Buffer.alloc((size * 4 + 1) * size);
  for (let y = 0; y < size; y += 1) {
    raw[y * (size * 4 + 1)] = 0;
    rgba.copy(raw, y * (size * 4 + 1) + 1, y * size * 4, (y + 1) * size * 4);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0);
  ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // RGBA
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function drawIcon(size) {
  const img = Buffer.alloc(size * size * 4);
  const cx = size / 2;
  const cy = size / 2;
  const radius = size * 0.23; // شعاع گوشه‌ها
  const inset = size * 0.02;

  // رنگ گرادیان: فیروزه‌ای → بنفش-آبی
  const top = [45, 212, 191];
  const bottom = [91, 92, 246];

  const insideRounded = (x, y) => {
    const x0 = inset, y0 = inset, x1 = size - inset, y1 = size - inset;
    if (x < x0 || x > x1 || y < y0 || y > y1) return false;
    const rx = Math.max(x0 + radius - x, x - (x1 - radius), 0);
    const ry = Math.max(y0 + radius - y, y - (y1 - radius), 0);
    return rx * rx + ry * ry <= radius * radius;
  };

  // حلقه‌ی پیشرفت + تیک
  const ringR = size * 0.30;
  const ringW = size * 0.055;
  // تیک: دو پاره‌خط
  const p1 = [cx - size * 0.13, cy + size * 0.01];
  const p2 = [cx - size * 0.03, cy + size * 0.11];
  const p3 = [cx + size * 0.16, cy - size * 0.10];
  const thick = size * 0.045;

  const distSeg = (px, py, a, b) => {
    const dx = b[0] - a[0], dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((px - a[0]) * dx + (py - a[1]) * dy) / (dx * dx + dy * dy)));
    const ex = a[0] + t * dx - px, ey = a[1] + t * dy - py;
    return Math.hypot(ex, ey);
  };

  for (let y = 0; y < size; y += 1) {
    for (let x = 0; x < size; x += 1) {
      const i = (y * size + x) * 4;
      if (!insideRounded(x, y)) continue;
      const t = y / size;
      let r = lerp(top[0], bottom[0], t);
      let g = lerp(top[1], bottom[1], t);
      let b = lerp(top[2], bottom[2], t);

      const d = Math.hypot(x - cx, y - cy);
      // حلقه (سه‌چهارم دایره)
      const ang = Math.atan2(y - cy, x - cx);
      const inRing = Math.abs(d - ringR) < ringW && !(ang > -2.5 && ang < -0.9);
      const inCheck =
        distSeg(x, y, p1, p2) < thick || distSeg(x, y, p2, p3) < thick;
      if (inRing || inCheck) {
        r = 255; g = 255; b = 255;
      }
      img[i] = Math.round(r);
      img[i + 1] = Math.round(g);
      img[i + 2] = Math.round(b);
      img[i + 3] = 255;
    }
  }
  return encodePNG(size, img);
}

mkdirSync('public/icons', { recursive: true });
writeFileSync('public/icons/icon-192.png', drawIcon(192));
writeFileSync('public/icons/icon-512.png', drawIcon(512));
console.log('آیکون‌ها ساخته شد ✅');
