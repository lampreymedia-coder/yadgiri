/**
 * موتور صدای محیطی نسل ۲ — صداهای کوزی و دلنشین
 * ریورب کانولوشن، لایه‌های چندگانه، لوفای با سوئینگ الکتریک
 * کاملاً آفلاین؛ هیچ فایلی لازم نیست.
 */

export type AmbienceKind =
  | 'lofi'
  | 'rain'
  | 'fire'
  | 'ocean'
  | 'cafe'
  | 'piano'
  | 'forest'
  | 'brown';

export const AMBIENCES: {
  kind: AmbienceKind;
  title: string;
  desc: string;
  icon: string;
}[] = [
  { kind: 'lofi', title: 'لوفای گرم', desc: 'آکورد الکتریک، سوئینگ و خش گرام', icon: 'headphones' },
  { kind: 'rain', title: 'باران پشت پنجره', desc: 'بارش نرم با ریورب اتاق', icon: 'rain' },
  { kind: 'fire', title: 'شومینه‌ی آرام', desc: 'هیزم و ترق‌وتروق ملایم', icon: 'fire' },
  { kind: 'ocean', title: 'ساحل شب', desc: 'موج آرام با فضای وسیع', icon: 'waves' },
  { kind: 'cafe', title: 'کافه‌ی دنج', desc: 'زمزمه‌ی دور و فنجان', icon: 'cup' },
  { kind: 'piano', title: 'پیانوی رویایی', desc: 'نت‌های نرم با پد گرم', icon: 'piano' },
  { kind: 'forest', title: 'شب تابستان', desc: 'جیرجیرک و باد ملایم میان درختان', icon: 'leaf' },
  { kind: 'brown', title: 'نویز قهوه‌ای', desc: 'صدای یکنواخت برای حذف مزاحمت', icon: 'wind' },
];

function makeNoise(ctx: AudioContext, type: 'white' | 'pink' | 'brown', seconds = 6): AudioBuffer {
  const rate = ctx.sampleRate;
  const n = Math.floor(rate * seconds);
  const buf = ctx.createBuffer(2, n, rate);
  for (let ch = 0; ch < 2; ch += 1) {
    const data = buf.getChannelData(ch);
    if (type === 'white') {
      for (let i = 0; i < n; i += 1) data[i] = Math.random() * 2 - 1;
    } else if (type === 'brown') {
      let last = 0;
      for (let i = 0; i < n; i += 1) {
        const white = Math.random() * 2 - 1;
        last = (last + 0.02 * white) / 1.02;
        data[i] = Math.max(-1, Math.min(1, last * 3.5));
      }
    } else {
      let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0;
      for (let i = 0; i < n; i += 1) {
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
  }
  return buf;
}

/** ضربه‌ی پاسخ مصنوعی برای ریورب گرم و کوتاه */
function impulseResponse(ctx: AudioContext, seconds = 2.4, decay = 2.2): AudioBuffer {
  const rate = ctx.sampleRate;
  const n = Math.floor(rate * seconds);
  const buf = ctx.createBuffer(2, n, rate);
  for (let ch = 0; ch < 2; ch += 1) {
    const data = buf.getChannelData(ch);
    for (let i = 0; i < n; i += 1) {
      data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / n, decay);
    }
  }
  return buf;
}

function loop(ctx: AudioContext, buf: AudioBuffer): AudioBufferSourceNode {
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
  volume = 0.72;

  private ensureCtx(): AudioContext {
    if (!this.ctx) {
      const Ctx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new Ctx();
    }
    if (this.ctx.state === 'suspended') void this.ctx.resume();
    return this.ctx;
  }

  setVolume(v: number) {
    this.volume = v;
    if (this.master && this.ctx) {
      this.master.gain.setTargetAtTime(v, this.ctx.currentTime, 0.08);
    }
  }

  stop() {
    this.timers.forEach((t) => window.clearInterval(t));
    this.timers = [];
    this.stops.forEach((fn) => {
      try {
        fn();
      } catch {
        /* ignore */
      }
    });
    this.stops = [];
    if (this.master && this.ctx) {
      const m = this.master;
      m.gain.setTargetAtTime(0, this.ctx.currentTime, 0.15);
      window.setTimeout(() => {
        try {
          m.disconnect();
        } catch {
          /* ignore */
        }
      }, 500);
    }
    this.master = null;
    this.current = null;
  }

  /** خروجی مشترک: dry + wet (ریورب) */
  private bus(ctx: AudioContext, reverbMix = 0.28) {
    const master = ctx.createGain();
    master.gain.value = 0;
    master.connect(ctx.destination);
    master.gain.setTargetAtTime(this.volume, ctx.currentTime, 0.5);

    const dry = ctx.createGain();
    dry.gain.value = 1 - reverbMix;
    dry.connect(master);

    const wet = ctx.createGain();
    wet.gain.value = reverbMix;
    const convolver = ctx.createConvolver();
    convolver.buffer = impulseResponse(ctx, 2.6, 2.4);
    wet.connect(convolver);
    convolver.connect(master);

    this.master = master;
    this.stops.push(() => {
      try {
        convolver.disconnect();
      } catch {
        /* ignore */
      }
    });
    return { dry, wet, master };
  }

  private add(src: AudioBufferSourceNode | OscillatorNode) {
    src.start();
    this.stops.push(() => {
      try {
        src.stop();
      } catch {
        /* ignore */
      }
    });
  }

  start(kind: AmbienceKind) {
    this.stop();
    const ctx = this.ensureCtx();
    this.current = kind;
    const mix =
      kind === 'lofi' || kind === 'piano'
        ? 0.32
        : kind === 'ocean' || kind === 'forest'
          ? 0.38
          : kind === 'cafe'
            ? 0.22
            : 0.26;
    const { dry, wet } = this.bus(ctx, mix);
    const out = (node: AudioNode, wetAlso = true) => {
      node.connect(dry);
      if (wetAlso) node.connect(wet);
    };

    switch (kind) {
      case 'lofi':
        this.lofi(ctx, out);
        break;
      case 'rain':
        this.rain(ctx, out);
        break;
      case 'fire':
        this.fire(ctx, out);
        break;
      case 'ocean':
        this.ocean(ctx, out);
        break;
      case 'cafe':
        this.cafe(ctx, out);
        break;
      case 'piano':
        this.piano(ctx, out);
        break;
      case 'forest':
        this.forest(ctx, out);
        break;
      case 'brown':
        this.brown(ctx, out);
        break;
    }
  }

  private rain(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    // لایه‌ی پایه: بارش یکنواخت
    const base = loop(ctx, makeNoise(ctx, 'pink', 8));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 1600;
    lp.Q.value = 0.7;
    const g = ctx.createGain();
    g.gain.value = 0.42;
    base.connect(lp).connect(g);
    out(g);
    this.add(base);

    // لایه‌ی قطرات ریزتر
    const drops = loop(ctx, makeNoise(ctx, 'white', 5));
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 4800;
    bp.Q.value = 0.55;
    const g2 = ctx.createGain();
    g2.gain.value = 0.045;
    drops.connect(bp).connect(g2);
    out(g2, false);
    this.add(drops);

    // لرزش آرام فیلتر (حس باد پشت پنجره)
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.07;
    const lg = ctx.createGain();
    lg.gain.value = 280;
    lfo.connect(lg).connect(lp.frequency);
    lfo.start();
    this.stops.push(() => lfo.stop());
  }

  private ocean(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    const base = loop(ctx, makeNoise(ctx, 'brown', 10));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 620;
    const swell = ctx.createGain();
    swell.gain.value = 0.32;
    base.connect(lp).connect(swell);
    out(swell);
    this.add(base);

    const lfo = ctx.createOscillator();
    lfo.type = 'sine';
    lfo.frequency.value = 0.08;
    const lg = ctx.createGain();
    lg.gain.value = 0.2;
    lfo.connect(lg).connect(swell.gain);

    const lfo2 = ctx.createOscillator();
    lfo2.frequency.value = 0.055;
    const lg2 = ctx.createGain();
    lg2.gain.value = 260;
    lfo2.connect(lg2).connect(lp.frequency);
    lfo.start();
    lfo2.start();
    this.stops.push(() => {
      lfo.stop();
      lfo2.stop();
    });

    // لایه‌ی سفید ملایم برای کف موج
    const foam = loop(ctx, makeNoise(ctx, 'white', 6));
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 2200;
    const fg = ctx.createGain();
    fg.gain.value = 0.025;
    foam.connect(hp).connect(fg);
    out(fg, false);
    this.add(foam);
  }

  private fire(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    const base = loop(ctx, makeNoise(ctx, 'brown', 8));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 340;
    const g = ctx.createGain();
    g.gain.value = 0.48;
    base.connect(lp).connect(g);
    out(g);
    this.add(base);

    // نفس آرام آتش
    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.18;
    const lg = ctx.createGain();
    lg.gain.value = 0.08;
    lfo.connect(lg).connect(g.gain);
    lfo.start();
    this.stops.push(() => lfo.stop());

    const crackle = () => {
      if (!this.master) return;
      const t = ctx.currentTime;
      const src = ctx.createBufferSource();
      src.buffer = makeNoise(ctx, 'white', 0.08);
      const bp = ctx.createBiquadFilter();
      bp.type = 'bandpass';
      bp.frequency.value = 1200 + Math.random() * 3200;
      bp.Q.value = 5 + Math.random() * 4;
      const env = ctx.createGain();
      env.gain.setValueAtTime(0.0001, t);
      env.gain.exponentialRampToValueAtTime(0.18 + Math.random() * 0.22, t + 0.004);
      env.gain.exponentialRampToValueAtTime(0.0001, t + 0.04 + Math.random() * 0.07);
      src.connect(bp).connect(env);
      out(env, false);
      src.start(t);
    };
    this.timers.push(
      window.setInterval(() => {
        if (Math.random() < 0.7) crackle();
        if (Math.random() < 0.2) window.setTimeout(crackle, 40 + Math.random() * 100);
      }, 280),
    );
  }

  private cafe(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    const murmur = loop(ctx, makeNoise(ctx, 'pink', 8));
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 380;
    bp.Q.value = 0.85;
    const g = ctx.createGain();
    g.gain.value = 0.36;
    murmur.connect(bp).connect(g);
    out(g);
    this.add(murmur);

    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.28;
    const lg = ctx.createGain();
    lg.gain.value = 110;
    lfo.connect(lg).connect(bp.frequency);
    lfo.start();
    this.stops.push(() => lfo.stop());

    // فنجان و قاشق گاه‌به‌گاه
    this.timers.push(
      window.setInterval(() => {
        if (!this.master || Math.random() > 0.28) return;
        const t = ctx.currentTime;
        const osc = ctx.createOscillator();
        osc.type = 'sine';
        osc.frequency.value = 1600 + Math.random() * 2400;
        const env = ctx.createGain();
        env.gain.setValueAtTime(0.0001, t);
        env.gain.exponentialRampToValueAtTime(0.018 + Math.random() * 0.015, t + 0.003);
        env.gain.exponentialRampToValueAtTime(0.0001, t + 0.28);
        osc.connect(env);
        out(env, false);
        osc.start(t);
        osc.stop(t + 0.35);
      }, 3200),
    );
  }

  private brown(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    const base = loop(ctx, makeNoise(ctx, 'brown', 8));
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 780;
    const g = ctx.createGain();
    g.gain.value = 0.5;
    base.connect(lp).connect(g);
    out(g);
    this.add(base);
  }

  private forest(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    // باد ملایم میان برگ‌ها
    const wind = loop(ctx, makeNoise(ctx, 'pink', 8));
    const bp = ctx.createBiquadFilter();
    bp.type = 'bandpass';
    bp.frequency.value = 900;
    bp.Q.value = 0.6;
    const g = ctx.createGain();
    g.gain.value = 0.18;
    wind.connect(bp).connect(g);
    out(g);
    this.add(wind);

    const lfo = ctx.createOscillator();
    lfo.frequency.value = 0.05;
    const lg = ctx.createGain();
    lg.gain.value = 0.08;
    lfo.connect(lg).connect(g.gain);
    lfo.start();
    this.stops.push(() => lfo.stop());

    // جیرجیرک‌های شب
    const chirp = () => {
      if (!this.master) return;
      const t = ctx.currentTime + Math.random() * 0.2;
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      const f = 2800 + Math.random() * 2200;
      osc.frequency.setValueAtTime(f, t);
      const env = ctx.createGain();
      env.gain.setValueAtTime(0.0001, t);
      env.gain.exponentialRampToValueAtTime(0.025 + Math.random() * 0.02, t + 0.01);
      env.gain.exponentialRampToValueAtTime(0.0001, t + 0.08 + Math.random() * 0.06);
      const hp = ctx.createBiquadFilter();
      hp.type = 'highpass';
      hp.frequency.value = 1800;
      osc.connect(hp).connect(env);
      out(env, false);
      osc.start(t);
      osc.stop(t + 0.2);
    };
    this.timers.push(
      window.setInterval(() => {
        chirp();
        if (Math.random() < 0.5) window.setTimeout(chirp, 60 + Math.random() * 120);
      }, 380),
    );
  }

  private piano(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    // پد گرم زیر پیانو
    const padNotes = [130.81, 164.81, 196.0, 246.94]; // Cmaj7
    padNotes.forEach((f) => {
      const osc = ctx.createOscillator();
      osc.type = 'sine';
      osc.frequency.value = f;
      const g = ctx.createGain();
      g.gain.value = 0.035;
      const lp = ctx.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = 900;
      osc.connect(lp).connect(g);
      out(g);
      this.add(osc);
    });

    // ملودی آرام روی مقیاس پنتاتونیک
    const scale = [261.63, 293.66, 329.63, 392.0, 440.0, 523.25, 587.33, 659.25];
    let step = 0;
    const play = () => {
      if (!this.master) return;
      const t = ctx.currentTime + 0.02;
      const note = scale[(step + Math.floor(Math.random() * 2)) % scale.length];
      // دو اسیلاتور کمی جدا برای حس پیانو
      [0, 0.003].forEach((det, i) => {
        const osc = ctx.createOscillator();
        osc.type = i === 0 ? 'triangle' : 'sine';
        osc.frequency.value = note * (1 + det);
        const env = ctx.createGain();
        env.gain.setValueAtTime(0.0001, t);
        env.gain.exponentialRampToValueAtTime(0.09 / (i + 1), t + 0.03);
        env.gain.exponentialRampToValueAtTime(0.03, t + 1.2);
        env.gain.exponentialRampToValueAtTime(0.0001, t + 2.8);
        const lp = ctx.createBiquadFilter();
        lp.type = 'lowpass';
        lp.frequency.value = 2200;
        osc.connect(lp).connect(env);
        out(env);
        osc.start(t);
        osc.stop(t + 3);
      });
      step = (step + (Math.random() < 0.35 ? 1 : 2)) % scale.length;
    };
    play();
    this.timers.push(window.setInterval(play, 2100 + Math.random() * 400));
  }

  private lofi(ctx: AudioContext, out: (n: AudioNode, w?: boolean) => void) {
    // خش صفحه‌ی گرام
    const vinyl = loop(ctx, makeNoise(ctx, 'white', 5));
    const hp = ctx.createBiquadFilter();
    hp.type = 'highpass';
    hp.frequency.value = 2800;
    const vg = ctx.createGain();
    vg.gain.value = 0.014;
    vinyl.connect(hp).connect(vg);
    out(vg, false);
    this.add(vinyl);

    // پیشرفت آکورد گرم با سوئینگ
    const chords: number[][] = [
      [174.61, 220.0, 261.63, 329.63], // Fmaj7
      [164.81, 196.0, 246.94, 293.66], // Em7
      [146.83, 174.61, 220.0, 261.63], // Dm7
      [130.81, 164.81, 196.0, 246.94], // Cmaj7
    ];
    const bass = [87.31, 82.41, 73.42, 65.41];
    let step = 0;
    const barSec = 3.6;

    const playChord = () => {
      if (!this.master) return;
      const t = ctx.currentTime + 0.03;
      const notes = chords[step % chords.length];
      const warm = ctx.createBiquadFilter();
      warm.type = 'lowpass';
      warm.frequency.value = 1400;
      out(warm);

      notes.forEach((f, i) => {
        // الکتریک: دو اسیلاتور با کمی دتیون
        [1, 1.004].forEach((mul, k) => {
          const osc = ctx.createOscillator();
          osc.type = k === 0 ? 'triangle' : 'sine';
          osc.frequency.value = f * mul * (1 + (Math.random() - 0.5) * 0.0015);
          const env = ctx.createGain();
          env.gain.setValueAtTime(0.0001, t);
          env.gain.exponentialRampToValueAtTime(0.055 / (k + 1), t + 0.35 + i * 0.04);
          env.gain.exponentialRampToValueAtTime(0.022, t + barSec * 0.65);
          env.gain.exponentialRampToValueAtTime(0.0001, t + barSec + 0.15);
          osc.connect(env).connect(warm);
          osc.start(t);
          osc.stop(t + barSec + 0.2);
        });
      });

      // بیس نرم
      const b = ctx.createOscillator();
      b.type = 'sine';
      b.frequency.value = bass[step % bass.length];
      const bEnv = ctx.createGain();
      bEnv.gain.setValueAtTime(0.0001, t);
      bEnv.gain.exponentialRampToValueAtTime(0.11, t + 0.12);
      bEnv.gain.exponentialRampToValueAtTime(0.0001, t + barSec * 0.85);
      b.connect(bEnv);
      out(bEnv);
      b.start(t);
      b.stop(t + barSec);

      // سوئینگ: ضربه در ۰ و ۰٫۶ میزان
      [0, barSec * 0.58].forEach((off) => {
        const k = ctx.createOscillator();
        k.type = 'sine';
        k.frequency.setValueAtTime(95, t + off);
        k.frequency.exponentialRampToValueAtTime(42, t + off + 0.14);
        const kEnv = ctx.createGain();
        kEnv.gain.setValueAtTime(0.0001, t + off);
        kEnv.gain.exponentialRampToValueAtTime(0.14, t + off + 0.01);
        kEnv.gain.exponentialRampToValueAtTime(0.0001, t + off + 0.24);
        k.connect(kEnv);
        out(kEnv, false);
        k.start(t + off);
        k.stop(t + off + 0.3);

        // های‌هت نرم
        const hat = ctx.createBufferSource();
        hat.buffer = makeNoise(ctx, 'white', 0.05);
        const hatBp = ctx.createBiquadFilter();
        hatBp.type = 'highpass';
        hatBp.frequency.value = 6000;
        const hatEnv = ctx.createGain();
        hatEnv.gain.setValueAtTime(0.0001, t + off + 0.02);
        hatEnv.gain.exponentialRampToValueAtTime(0.03, t + off + 0.025);
        hatEnv.gain.exponentialRampToValueAtTime(0.0001, t + off + 0.08);
        hat.connect(hatBp).connect(hatEnv);
        out(hatEnv, false);
        hat.start(t + off + 0.02);
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
      const start = t + i * 0.24;
      env.gain.setValueAtTime(0.0001, start);
      env.gain.exponentialRampToValueAtTime(0.2, start + 0.02);
      env.gain.exponentialRampToValueAtTime(0.0001, start + 1.8);
      const convolver = ctx.createConvolver();
      convolver.buffer = impulseResponse(ctx, 1.8, 2.5);
      const wet = ctx.createGain();
      wet.gain.value = 0.35;
      osc.connect(env);
      env.connect(ctx.destination);
      env.connect(wet).connect(convolver).connect(ctx.destination);
      osc.start(start);
      osc.stop(start + 2);
    });
  }
}

export const ambience = new AmbienceEngine();
