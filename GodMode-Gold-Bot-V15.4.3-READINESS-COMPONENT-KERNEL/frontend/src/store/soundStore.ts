import { create } from 'zustand';

export type SoundEvent = 'click' | 'success' | 'warning' | 'danger' | 'toggle' | 'navigate';
export type SoundPreset = 'chime' | 'soft' | 'alert' | 'minimal';

type SoundState = {
  enabled: boolean;
  preset: SoundPreset;
  setEnabled: (enabled: boolean) => void;
  toggleSound: () => void;
  setPreset: (preset: SoundPreset) => void;
  play: (event?: SoundEvent) => void;
};

// localStorage throws outright in a few real configurations (Safari private browsing, "block all
// cookies", some kiosk/embedded webviews). These reads sit at module scope, so an exception here
// aborted the whole module graph and the dashboard rendered a blank page instead of degrading.
function readLocal(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writeLocal(key: string, value: string) {
  try { localStorage.setItem(key, value); } catch { /* preference is best-effort, never required */ }
}

const saved = readLocal('godmode-sound-enabled');
const initial = saved === null ? true : saved === 'true';
const VALID_PRESETS: SoundPreset[] = ['chime', 'soft', 'alert', 'minimal'];
const rawPreset = readLocal('godmode-sound-preset') as SoundPreset | null;
const savedPreset: SoundPreset = rawPreset && VALID_PRESETS.includes(rawPreset) ? rawPreset : 'chime';

// One AudioContext for the whole app, created lazily on first sound.
//
// tone() previously did `new AudioContextClass()` on every UI click and never closed it. Browsers
// cap concurrent AudioContexts (Chrome allows six); past that, construction throws and UI sound
// dies permanently for the session, while every leaked context holds an audio thread and hardware
// buffer. A single shared context is also what the Web Audio API is designed around.
let sharedCtx: AudioContext | null = null;
function audioContext(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextClass) return null;
  try {
    if (!sharedCtx || sharedCtx.state === 'closed') sharedCtx = new AudioContextClass();
    // Autoplay policy suspends the context until a user gesture; every caller here is one.
    if (sharedCtx.state === 'suspended') void sharedCtx.resume();
    return sharedCtx;
  } catch { return null; }
}

function tone(event: SoundEvent = 'click', preset: SoundPreset = 'chime') {
  const ctx = audioContext();
  if (!ctx) return;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  const baseMap: Record<SoundEvent, [number, number, OscillatorType]> = {
    click: [540, 0.035, 'sine'],
    success: [760, 0.07, 'triangle'],
    warning: [420, 0.08, 'sawtooth'],
    danger: [220, 0.10, 'square'],
    toggle: [620, 0.045, 'sine'],
    navigate: [680, 0.055, 'triangle'],
  };
  const presetGain: Record<SoundPreset, number> = { chime: 0.045, soft: 0.025, alert: 0.06, minimal: 0.016 };
  const presetShift: Record<SoundPreset, number> = { chime: 1, soft: 0.82, alert: 1.16, minimal: 0.72 };
  const [freq, dur, type] = baseMap[event];
  osc.frequency.value = freq * presetShift[preset];
  osc.type = preset === 'minimal' ? 'sine' : type;
  gain.gain.setValueAtTime(0.0001, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(presetGain[preset], ctx.currentTime + 0.005);
  gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + dur);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + dur + 0.015);
}

export const useSoundStore = create<SoundState>((set, get) => ({
  enabled: initial,
  preset: savedPreset,
  setEnabled: (enabled) => {
    writeLocal('godmode-sound-enabled', String(enabled));
    set({ enabled });
    if (enabled) tone('success', get().preset);
  },
  toggleSound: () => {
    const enabled = !get().enabled;
    writeLocal('godmode-sound-enabled', String(enabled));
    set({ enabled });
    if (enabled) tone('success', get().preset);
  },
  setPreset: (preset) => {
    writeLocal('godmode-sound-preset', preset);
    set({ preset });
    if (get().enabled) tone('success', preset);
  },
  play: (event = 'click') => {
    if (!get().enabled) return;
    try { tone(event, get().preset); } catch { /* sound must never break trading UI */ }
  },
}));
