import type { Soundscape } from '../types'

type CleanupFn = () => void

const globalWindow = window as Window & {
  webkitAudioContext?: typeof AudioContext
}

let activeContext: AudioContext | null = null
let cleanupFns: CleanupFn[] = []

const getAudioContext = () => {
  const AudioCtor = window.AudioContext ?? globalWindow.webkitAudioContext

  if (!AudioCtor) {
    return null
  }

  if (activeContext && activeContext.state !== 'closed') {
    return activeContext
  }

  activeContext = new AudioCtor()
  return activeContext
}

const createNoiseBuffer = (context: AudioContext, tint: 'white' | 'brown') => {
  const length = context.sampleRate * 2
  const buffer = context.createBuffer(1, length, context.sampleRate)
  const channelData = buffer.getChannelData(0)
  let previous = 0

  for (let index = 0; index < length; index += 1) {
    const white = Math.random() * 2 - 1

    if (tint === 'brown') {
      previous = (previous + 0.02 * white) / 1.02
      channelData[index] = previous * 3.5
      continue
    }

    channelData[index] = white * 0.35
  }

  return buffer
}

const addCleanup = (cleanup: CleanupFn) => {
  cleanupFns.push(cleanup)
}

const clearNodes = async () => {
  cleanupFns.forEach((cleanup) => {
    try {
      cleanup()
    } catch {
      // ignore cleanup errors from already-stopped nodes
    }
  })
  cleanupFns = []
}

const makeLoopingSource = (
  context: AudioContext,
  buffer: AudioBuffer,
  destination: AudioNode,
  gainValue: number,
) => {
  const source = context.createBufferSource()
  const gainNode = context.createGain()

  source.buffer = buffer
  source.loop = true
  gainNode.gain.value = gainValue

  source.connect(gainNode)
  gainNode.connect(destination)
  source.start()

  addCleanup(() => {
    try {
      source.stop()
    } catch {
      // already stopped
    }
    source.disconnect()
    gainNode.disconnect()
  })
}

const createCosmicSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.42
  master.connect(context.destination)

  const drone = context.createOscillator()
  drone.type = 'sine'
  drone.frequency.value = 98

  const layer = context.createOscillator()
  layer.type = 'triangle'
  layer.frequency.value = 196

  const shimmer = context.createOscillator()
  shimmer.type = 'sine'
  shimmer.frequency.value = 392

  const lfo = context.createOscillator()
  lfo.type = 'sine'
  lfo.frequency.value = 0.12

  const modGain = context.createGain()
  modGain.gain.value = 28

  const droneGain = context.createGain()
  droneGain.gain.value = 0.45

  const layerGain = context.createGain()
  layerGain.gain.value = 0.18

  const shimmerGain = context.createGain()
  shimmerGain.gain.value = 0.06

  const filter = context.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 1100
  filter.Q.value = 0.8

  lfo.connect(modGain)
  modGain.connect(filter.frequency)

  drone.connect(droneGain)
  layer.connect(layerGain)
  shimmer.connect(shimmerGain)
  droneGain.connect(filter)
  layerGain.connect(filter)
  shimmerGain.connect(filter)
  filter.connect(master)

  drone.start()
  layer.start()
  shimmer.start()
  lfo.start()

  addCleanup(() => {
    drone.stop()
    layer.stop()
    shimmer.stop()
    lfo.stop()
    drone.disconnect()
    layer.disconnect()
    shimmer.disconnect()
    lfo.disconnect()
    modGain.disconnect()
    droneGain.disconnect()
    layerGain.disconnect()
    shimmerGain.disconnect()
    filter.disconnect()
    master.disconnect()
  })
}

const createRainSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.38
  master.connect(context.destination)

  const highPass = context.createBiquadFilter()
  highPass.type = 'highpass'
  highPass.frequency.value = 700

  const bandPass = context.createBiquadFilter()
  bandPass.type = 'bandpass'
  bandPass.frequency.value = 2200
  bandPass.Q.value = 0.7

  highPass.connect(bandPass)
  bandPass.connect(master)

  makeLoopingSource(context, createNoiseBuffer(context, 'white'), highPass, 0.55)

  addCleanup(() => {
    highPass.disconnect()
    bandPass.disconnect()
    master.disconnect()
  })
}

const createBrownSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.4
  master.connect(context.destination)

  const filter = context.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 480
  filter.Q.value = 0.5
  filter.connect(master)

  makeLoopingSource(context, createNoiseBuffer(context, 'brown'), filter, 0.7)

  addCleanup(() => {
    filter.disconnect()
    master.disconnect()
  })
}

const createPulseSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.4
  master.connect(context.destination)

  const tone = context.createOscillator()
  tone.type = 'sine'
  tone.frequency.value = 174

  const soft = context.createOscillator()
  soft.type = 'triangle'
  soft.frequency.value = 261.6

  const gainNode = context.createGain()
  gainNode.gain.value = 0.02

  const softGain = context.createGain()
  softGain.gain.value = 0.01

  tone.connect(gainNode)
  soft.connect(softGain)
  gainNode.connect(master)
  softGain.connect(master)
  tone.start()
  soft.start()

  const intervalId = window.setInterval(() => {
    const now = context.currentTime
    gainNode.gain.cancelScheduledValues(now)
    gainNode.gain.setValueAtTime(0.02, now)
    gainNode.gain.linearRampToValueAtTime(0.18, now + 0.08)
    gainNode.gain.linearRampToValueAtTime(0.03, now + 0.55)

    softGain.gain.cancelScheduledValues(now)
    softGain.gain.setValueAtTime(0.01, now)
    softGain.gain.linearRampToValueAtTime(0.08, now + 0.1)
    softGain.gain.linearRampToValueAtTime(0.015, now + 0.7)
  }, 1600)

  addCleanup(() => {
    window.clearInterval(intervalId)
    tone.stop()
    soft.stop()
    tone.disconnect()
    soft.disconnect()
    gainNode.disconnect()
    softGain.disconnect()
    master.disconnect()
  })
}

const soundFactories: Record<Exclude<Soundscape, 'silent'>, (context: AudioContext) => void> = {
  cosmic: createCosmicSound,
  brown: createBrownSound,
  rain: createRainSound,
  pulse: createPulseSound,
}

export const soundLabels: Record<Soundscape, string> = {
  cosmic: 'فضای کیهانی',
  brown: 'صدای عمیق',
  rain: 'باران نرم',
  pulse: 'نبض آرام',
  silent: 'بی‌صدا',
}

export const soundHints: Record<Soundscape, string> = {
  cosmic: 'برای مطالعه عمیق',
  brown: 'برای کار طولانی',
  rain: 'برای آرامش ذهن',
  pulse: 'برای شروع تمرکز',
  silent: 'فقط تایمر',
}

export const startAmbientSound = async (sound: Soundscape) => {
  await clearNodes()

  if (sound === 'silent') {
    return true
  }

  const context = getAudioContext()

  if (!context) {
    return false
  }

  if (context.state === 'suspended') {
    await context.resume()
  }

  soundFactories[sound](context)
  return true
}

export const stopAmbientSound = async () => {
  await clearNodes()

  if (!activeContext) {
    return
  }

  const context = activeContext
  activeContext = null

  if (context.state !== 'closed') {
    await context.close()
  }
}

export const playCompletionChime = async () => {
  const AudioCtor = window.AudioContext ?? globalWindow.webkitAudioContext

  if (!AudioCtor) {
    return
  }

  const context = new AudioCtor()

  if (context.state === 'suspended') {
    await context.resume()
  }

  const oscillator = context.createOscillator()
  const gainNode = context.createGain()

  oscillator.type = 'triangle'
  oscillator.frequency.setValueAtTime(392, context.currentTime)
  oscillator.frequency.linearRampToValueAtTime(523.25, context.currentTime + 0.7)

  gainNode.gain.setValueAtTime(0.0001, context.currentTime)
  gainNode.gain.linearRampToValueAtTime(0.22, context.currentTime + 0.05)
  gainNode.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 1)

  oscillator.connect(gainNode)
  gainNode.connect(context.destination)
  oscillator.start()
  oscillator.stop(context.currentTime + 1)

  window.setTimeout(() => {
    void context.close()
  }, 1100)
}
