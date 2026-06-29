import { create } from 'zustand';

export type ThemeMode = 'light' | 'dark' | 'system';
type ThemeState = { theme: ThemeMode; resolvedTheme: 'light' | 'dark'; setTheme: (theme: ThemeMode) => void; toggleTheme: () => void; };

function resolveTheme(theme: ThemeMode): 'light' | 'dark' {
  if (theme !== 'system') return theme;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function applyTheme(theme: ThemeMode) {
  const resolved = resolveTheme(theme);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeMode = theme;
  return resolved;
}

const saved = ((localStorage.getItem('godmode-theme') as ThemeMode) || 'light');
const initialResolved = applyTheme(saved);

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: saved,
  resolvedTheme: initialResolved,
  setTheme: (theme) => {
    const resolved = applyTheme(theme);
    localStorage.setItem('godmode-theme', theme);
    set({ theme, resolvedTheme: resolved });
  },
  toggleTheme: () => {
    const next: ThemeMode = get().resolvedTheme === 'light' ? 'dark' : 'light';
    const resolved = applyTheme(next);
    localStorage.setItem('godmode-theme', next);
    set({ theme: next, resolvedTheme: resolved });
  },
}));

if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const savedMode = (localStorage.getItem('godmode-theme') as ThemeMode) || 'light';
    if (savedMode === 'system') {
      const resolved = applyTheme('system');
      useThemeStore.setState({ theme: 'system', resolvedTheme: resolved });
    }
  });
}
