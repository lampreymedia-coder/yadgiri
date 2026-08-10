/**
 * موتور صدای محیطی — همه‌ی صداها با Web Audio ساخته می‌شوند (سنتز زنده).
 * هیچ فایل صوتی‌ای لازم نیست؛ کاملاً آفلاین و بسیار سبک.
 */

export type AmbienceKind =
  | 'rain'
  | 'ocean'
  | 'fire'
  | 'cafe'
  | 'brown'
  | 'lofi';

export const AMBIENCES: { kind: AmbienceKind; title: string; emoji: string; desc: string }[] = [
  { kind: 'lofi', title: 'لوفای آرام', emoji: '🎧', desc: 'آکوردهای گرم با تِمپوی کند' },
  { kind: 'rain', title: 'باران ملایم', emoji: '🌧️', desc: 'صدای باران پشت پنجره' },
  { kind: 'fire', title: 'شومینه', emoji: '🔥', desc: 'هیزم و ترق‌وتروق آتش' },
  { kind: 'ocean', title: 'موج دریا', emoji: '🌊', desc: 'رفت‌وآمد آرام موج‌ها' },
  { kind: 'cafe', title: 'همهمه‌ی کافه', emoji: '☕', desc: 'زمزمه‌ی دور یک کافه‌ی دنج' },
  { kind: 'brown', title: 'نویز آرام', emoji: '🌬️', desc: 'صدای یکنواخت برای حذف مزاحمت' },
];

function makeNoiseBuffer(ctx: AudioContext, type: 'white' | 'pink' | 'brown', seconds = 4): AudioBuffer {
  const rate = ctx.sampleRate;
  const buf = ctx.createBuffer(1, rate * seconds, rate);
  const data = buf.getChannelData(0);
  if (type === 'white') {
    for (let i = 0; i < data.length; i += 1) data[i] = Math.random() * 2 - 1;
  } else if (type === 'brown') {
    let last = 0;
    for (let i = 0; i < data.length; i += 1) {
      const white = Math.random() * 2 - 1;
      last = (last + 0.02 * white) / 1.02;
      data[i] = last * 3.5;
    }
  } else {
    // pink — فیلتر Paul Kellet
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
    for (let i = 0; i < data.length; i += 1) {
      const w = Math.random() * 2 - 1;
      b0 = 0.99886 * b0 + w * 0.0555179;
      b1 = 0.99332 * b1 + w * 0.0750759;
      b2 = 0.969 * b2 + w * 0.153852;
      b3 = 0.8665 * b3 + w * 0.3104856;
      b4 = 0.55 * b4 + w * 0.5329522;
      b5 = -0.7616 * b5 - w * 0.016898;
      data[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11;
      b6 = w * 0.115926;
    }
  }
  return buf;
}

function loopNoise(ctx: AudioContext, buf: AudioBuffer): AudioBufferSourceNode {
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.loop = true;
  return src;
}

class AmbienceEngine {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private stops: (() => void)[] = [];
  private timers: number[] = [];
  current: AmbienceKind | null = null;
  volume = 0.7;

  private ensureCtx(): AudioContext {
    if (!this.ctx) {
      const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new Ctx();
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume();
    return this.ctx;
  }

  setVolume(v: number) {
    this.volume = v;
    if (this.master && this.ctx) {
      this.master.gain.setTargetAtTime(v, this.ctx.currentTime, 0.05);
    }
  }

  stop() {
    this.timers.forEach((t) => window.clearInterval(t));
    this.timers = [];
    this.stops.forEach((fn) => {
      try { fn(); } catch { /* ignore */ }
    });
    this.stops = [];
    if (this.master && this.ctx) {
      const m = this.master;
      m.gain.setTargetAtTime(0, this.ctx.currentTime, 0.1);
      window.setTimeout(() => m.disconnect(), 400);
    }
    this.master = null;
    this.current = null;
  }

  start(kind: AmbienceKind) {
    this.stop();
    const ctx = this.ensureCtx();
    const master = ctx.createGain();
    master.gain.value = 0;
    master.connect(ctx.destination);
    master.gain.setTargetAtTime(this.volume, ctx.currentTime, 0.4);
    this.master = master;
    this.current = kind;

    switch (kind) {
      case 'rain': this.rain(ctx, master); break;
      case 'ocean': this.ocean(ctx, master); break;
      case 'fire': this.fire(ctx, master); break;
      case 'cafe': this.cafe(ctx, master); break;
      case 'brown': this.brownNoise(ctx, master); break;
      case 'lofi': this.lofi(ctx, master); break;
    }
  }

  private addSource(src: AudioBufferSourceNode) {
    src.start();
    this.stops.push(() => src.stop());
  }

  private rain(ctx: AudioContext, out: GainNode) {
    // لایه‌ی پس‌زمینه: بارش یکنواخت
    const base = loopNoise(ctx, makeNoiseBuffer(ctx, 'pink'));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 1400;
    const g = ctx.createGain();
    g.gain.value = 0.5;
    base.connect(lp).connect(g).connect(out);
    this.addSource(base);
    // لایه‌ی قطره‌های ریز
    const hiss = loopNoise(ctx, makeNoiseBuffer(ctx, 'white'));
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 5200;
    bp.Q.value = 0.6;
    const g2 = ctx.createGain();
    g2.gain.value = 0.06;
    hiss.connect(bp).connect(g2).connect(out);
    this.addSource(hiss);
  }

  private ocean(ctx: AudioContext, out: GainNode) {
    const base = loopNoise(ctx, makeNoiseBuffer(ctx, 'brown'));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 700;
    const swell = ctx.createGain();
    swell.gain.value = 0.35;
    // موج: LFO آرام روی بلندی و فیلتر
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.09;
    const lfoGain = ctx.createGain();
    lfoGain.gain.value = 0.22;
    lfo.connect(lfoGain).connect(swell.gain);
    const lfo2 = ctx.createOscillator();
    lfo2.frequency.value = 0.07;
    const lfo2Gain = ctx.createGain();
    lfo2Gain.gain.value = 320;
    lfo2.connect(lfo2Gain).connect(lp.frequency);
    base.connect(lp).connect(swell).connect(out);
    lfo.start();
    lfo2.start();
    this.addSource(base);
    this.stops.push(() => { lfo.stop(); lfo2.stop(); });
  }

  private fire(ctx: AudioContext, out: GainNode) {
    const base = loopNoise(ctx, makeNoiseBuffer(ctx, 'brown'));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 380;
    const g = ctx.createGain();
    g.gain.value = 0.5;
    base.connect(lp).connect(g).connect(out);
    this.addSource(base);
    // ترق‌وتروق تصادفی
    const crackle = () => {
      if (!this.master) return;
      const t = ctx.currentTime;
      const src = ctx.createBufferSource();
      src.buffer = makeNoiseBuffer(ctx, 'white', 0.06);
      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass';
      bp.frequency.value = 1500 + Math.random() * 3500;
      bp.Q.value = 6;
      const env = ctx.createGain();
      env.gain.setValueAtTime(0.001, t);
      env.gain.exponentialRampToValueAtTime(0.25 + Math.random() * 0.3, t + 0.005);
      env.gain.exponentialRampToValueAtTime(0.001, t + 0.05 + Math.random() * 0.08);
      src.connect(bp).connect(env).connect(out);
      src.start(t);
    };
    this.timers.push(window.setInterval(() => {
      if (Math.random() < 0.75) crackle();
      if (Math.random() < 0.25) window.setTimeout(crackle, 60 + Math.random() * 120);
    }, 220));
  }

  private cafe(ctx: AudioContext, out: GainNode) {
    // زمزمه: نویز صورتی باندپس با مدولاسیون کند و نامنظم
    const murmur = loopNoise(ctx, makeNoiseBuffer(ctx, 'pink'));
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 420;
    bp.Q.value = 0.9;
    const g = ctx.createGain();
    g.gain.value = 0.4;
    murmur.connect(bp).connect(g).connect(out);
    this.addSource(murmur);
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.31;
    const lg = ctx.createGain();
    lg.gain.value = 130;
    lfo.connect(lg).connect(bp.frequency);
    lfo.start();
    this.stops.push(() => lfo.stop());
    // صدای فنجان و قاشق گاه‌به‌گاه
    this.timers.push(window.setInterval(() => {
      if (!this.master || Math.random() > 0.3) return;
      const t = ctx.currentTime;
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = 1800 + Math.random() * 2600;
      const env = ctx.createGain();
      env.gain.setValueAtTime(0.0001, t);
      env.gain.exponentialRampToValueAtTime(0.02 + Math.random() * 0.02, t + 0.004);
      env.gain.exponentialRampToValueAtTime(0.0001, t + 0.25);
      osc.connect(env).connect(out);
      osc.start(t);
      osc.stop(t + 0.3);
    }, 2600));
  }

  private brownNoise(ctx: AudioContext, out: GainNode) {
    const base = loopNoise(ctx, makeNoiseBuffer(ctx, 'brown'));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 900;
    const g = ctx.createGain();
    g.gain.value = 0.55;
    base.connect(lp).connect(g).connect(out);
    this.addSource(base);
  }

  private lofi(ctx: AudioContext, out: GainNode) {
    // خش صفحه‌ی گرام
    const vinyl = loopNoise(ctx, makeNoiseBuffer(ctx, 'white'));
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 3000;
    const vg = ctx.createGain();
    vg.gain.value = 0.012;
    vinyl.connect(hp).connect(vg).connect(out);
    this.addSource(vinyl);

    // پیشرفت آکورد: Fmaj7 → Em7 → Dm7 → Cmaj7 (فرکانس‌ها بر حسب هرتز)
    const chords: number[][] = [
      [174.61, 220.0, 261.63, 329.63], // Fmaj7
      [164.81, 196.0, 246.94, 293.66], // Em7
      [146.83, 174.61, 220.0, 261.63], // Dm7
      [130.81, 164.81, 196.0, 246.94], // Cmaj7
    ];
    const bass = [87.31, 82.41, 73.42, 65.41];
    let step = 0;
    const barSec = 3.4;

    const playChord = () => {
      if (!this.master) return;
      const t = ctx.currentTime + 0.02;
      const notes = chords[step % chords.length];
      const warm = ctx.createBiquadFilter();
      warm.type = 'lowpass';
      warm.frequency.value = 1100;
      warm.connect(out);
      notes.forEach((f, i) => {
        const osc = ctx.createOscillator();
        osc.type = 'triangle';
        osc.frequency.value = f * (1 + (Math.random() - 0.5) * 0.002);
        const env = ctx.createGain();
        env.gain.setValueAtTime(0.0001, t);
        env.gain.exponentialRampToValueAtTime(0.05, t + 0.4 + i * 0.03);
        env.gain.exponentialRampToValueAtTime(0.02, t + barSec * 0.7);
        env.gain.exponentialRampToValueAtTime(0.0001, t + barSec);
        osc.connect(env).connect(warm);
        osc.start(t);
        osc.stop(t + barSec + 0.1);
      });
      // بیس نرم
      const b = ctx.createOscillator();
      b.type = 'sine';
      b.frequency.value = bass[step % bass.length];
      const bEnv = ctx.createGain();
      bEnv.gain.setValueAtTime(0.0001, t);
      bEnv.gain.exponentialRampToValueAtTime(0.09, t + 0.15);
      bEnv.gain.exponentialRampToValueAtTime(0.0001, t + barSec * 0.9);
      b.connect(bEnv).connect(out);
      b.start(t);
      b.stop(t + barSec);
      // ضرب آرام (کیک نرم) دو بار در هر میزان
      [0, barSec / 2].forEach((off) => {
        const k = ctx.createOscillator();
        k.type = 'sine';
        k.frequency.setValueAtTime(120, t + off);
        k.frequency.exponentialRampToValueAtTime(45, t + off + 0.12);
        const kEnv = ctx.createGain();
        kEnv.gain.setValueAtTime(0.0001, t + off);
        kEnv.gain.exponentialRampToValueAtTime(0.16, t + off + 0.01);
        kEnv.gain.exponentialRampToValueAtTime(0.0001, t + off + 0.22);
        k.connect(kEnv).connect(out);
        k.start(t + off);
        k.stop(t + off + 0.3);
      });
      step += 1;
    };
    playChord();
    this.timers.push(window.setInterval(playChord, barSec * 1000));
  }

  /** زنگ ملایم پایان تایمر */
  chime() {
    const ctx = this.ensureCtx();
    const t = ctx.currentTime;
    [523.25, 659.25, 783.99].forEach((f, i) => {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = f;
      const env = ctx.createGain();
      const start = t + i * 0.22;
      env.gain.setValueAtTime(0.0001, start);
      env.gain.exponentialRampToValueAtTime(0.22, start + 0.02);
      env.gain.exponentialRampToValueAtTime(0.0001, start + 1.6);
      osc.connect(env).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + 1.8);
    });
  }
}

export const ambience = new AmbienceEngine();
