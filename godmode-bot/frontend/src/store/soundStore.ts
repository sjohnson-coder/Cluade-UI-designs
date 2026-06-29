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

const saved = localStorage.getItem('godmode-sound-enabled');
const initial = saved === null ? true : saved === 'true';
const savedPreset = (localStorage.getItem('godmode-sound-preset') as SoundPreset) || 'chime';

function tone(event: SoundEvent = 'click', preset: SoundPreset = 'chime') {
  if (typeof window === 'undefined') return;
  const AudioContextClass = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioContextClass) return;
  const ctx = new AudioContextClass();
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
    localStorage.setItem('godmode-sound-enabled', String(enabled));
    set({ enabled });
    if (enabled) tone('success', get().preset);
  },
  toggleSound: () => {
    const enabled = !get().enabled;
    localStorage.setItem('godmode-sound-enabled', String(enabled));
    set({ enabled });
    if (enabled) tone('success', get().preset);
  },
  setPreset: (preset) => {
    localStorage.setItem('godmode-sound-preset', preset);
    set({ preset });
    if (get().enabled) tone('success', preset);
  },
  play: (event = 'click') => {
    if (!get().enabled) return;
    try { tone(event, get().preset); } catch { /* sound must never break trading UI */ }
  },
}));
