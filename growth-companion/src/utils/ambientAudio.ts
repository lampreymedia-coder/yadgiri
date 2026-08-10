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

  return new AudioCtor()
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

    channelData[index] = white * 0.28
  }

  return buffer
}

const addCleanup = (cleanup: CleanupFn) => {
  cleanupFns.push(cleanup)
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
    source.stop()
    source.disconnect()
    gainNode.disconnect()
  })
}

const createCosmicSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.18
  master.connect(context.destination)

  const drone = context.createOscillator()
  drone.type = 'sine'
  drone.frequency.value = 110

  const layer = context.createOscillator()
  layer.type = 'triangle'
  layer.frequency.value = 220

  const lfo = context.createOscillator()
  lfo.type = 'sine'
  lfo.frequency.value = 0.14

  const modGain = context.createGain()
  modGain.gain.value = 18

  const droneGain = context.createGain()
  droneGain.gain.value = 0.28

  const layerGain = context.createGain()
  layerGain.gain.value = 0.08

  const filter = context.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 900
  filter.Q.value = 0.7

  lfo.connect(modGain)
  modGain.connect(filter.frequency)

  drone.connect(droneGain)
  layer.connect(layerGain)
  droneGain.connect(filter)
  layerGain.connect(filter)
  filter.connect(master)

  drone.start()
  layer.start()
  lfo.start()

  addCleanup(() => {
    drone.stop()
    layer.stop()
    lfo.stop()
    drone.disconnect()
    layer.disconnect()
    lfo.disconnect()
    modGain.disconnect()
    droneGain.disconnect()
    layerGain.disconnect()
    filter.disconnect()
    master.disconnect()
  })
}

const createRainSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.16
  master.connect(context.destination)

  const highPass = context.createBiquadFilter()
  highPass.type = 'highpass'
  highPass.frequency.value = 900

  const bandPass = context.createBiquadFilter()
  bandPass.type = 'bandpass'
  bandPass.frequency.value = 2600
  bandPass.Q.value = 0.8

  highPass.connect(bandPass)
  bandPass.connect(master)

  makeLoopingSource(context, createNoiseBuffer(context, 'white'), highPass, 0.18)

  addCleanup(() => {
    highPass.disconnect()
    bandPass.disconnect()
    master.disconnect()
  })
}

const createBrownSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.12
  master.connect(context.destination)

  const filter = context.createBiquadFilter()
  filter.type = 'lowpass'
  filter.frequency.value = 520
  filter.Q.value = 0.5
  filter.connect(master)

  makeLoopingSource(context, createNoiseBuffer(context, 'brown'), filter, 0.22)

  addCleanup(() => {
    filter.disconnect()
    master.disconnect()
  })
}

const createPulseSound = (context: AudioContext) => {
  const master = context.createGain()
  master.gain.value = 0.18
  master.connect(context.destination)

  const tone = context.createOscillator()
  tone.type = 'sine'
  tone.frequency.value = 174

  const gainNode = context.createGain()
  gainNode.gain.value = 0.01

  tone.connect(gainNode)
  gainNode.connect(master)
  tone.start()

  const intervalId = window.setInterval(() => {
    const now = context.currentTime
    gainNode.gain.cancelScheduledValues(now)
    gainNode.gain.setValueAtTime(0.01, now)
    gainNode.gain.linearRampToValueAtTime(0.09, now + 0.05)
    gainNode.gain.linearRampToValueAtTime(0.015, now + 0.4)
  }, 1800)

  addCleanup(() => {
    window.clearInterval(intervalId)
    tone.stop()
    tone.disconnect()
    gainNode.disconnect()
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
  brown: 'نویز عمیق',
  rain: 'باران نرم',
  pulse: 'نبض تمرکز',
  silent: 'بی‌صدا',
}

export const startAmbientSound = async (sound: Soundscape) => {
  await stopAmbientSound()

  if (sound === 'silent') {
    return true
  }

  const context = getAudioContext()

  if (!context) {
    return false
  }

  activeContext = context
  soundFactories[sound](context)

  if (context.state === 'suspended') {
    await context.resume()
  }

  return true
}

export const stopAmbientSound = async () => {
  cleanupFns.forEach((cleanup) => cleanup())
  cleanupFns = []

  if (!activeContext) {
    return
  }

  const context = activeContext
  activeContext = null

  await context.close()
}

export const playCompletionChime = async () => {
  const context = getAudioContext()

  if (!context) {
    return
  }

  const oscillator = context.createOscillator()
  const gainNode = context.createGain()

  oscillator.type = 'triangle'
  oscillator.frequency.setValueAtTime(392, context.currentTime)
  oscillator.frequency.linearRampToValueAtTime(523.25, context.currentTime + 0.7)

  gainNode.gain.setValueAtTime(0.0001, context.currentTime)
  gainNode.gain.linearRampToValueAtTime(0.14, context.currentTime + 0.05)
  gainNode.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 1)

  oscillator.connect(gainNode)
  gainNode.connect(context.destination)
  oscillator.start()
  oscillator.stop(context.currentTime + 1)

  window.setTimeout(() => {
    void context.close()
  }, 1100)
}
