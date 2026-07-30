import { create } from 'zustand';

export type ThemeMode = 'light' | 'dark' | 'system';
type ThemeState = { theme: ThemeMode; resolvedTheme: 'light' | 'dark'; setTheme: (theme: ThemeMode) => void; toggleTheme: () => void; };

// Same hazard as soundStore: an unguarded module-scope localStorage read blanks the whole app in
// private-browsing / cookies-blocked configurations.
function readTheme(): ThemeMode {
  let raw: string | null = null;
  try { raw = localStorage.getItem('godmode-theme'); } catch { raw = null; }
  // Default to dark, matching `<html data-theme="dark">` in index.html. Defaulting to 'light' here
  // meant a first-time visitor got the dark shell painted from the markup and then had it swapped
  // to light the moment this module executed — a visible flash on every cold load, and a theme that
  // disagreed with the document's own declared theme until something wrote to localStorage.
  return raw === 'light' || raw === 'dark' || raw === 'system' ? raw : 'dark';
}
function writeTheme(theme: ThemeMode) {
  try { localStorage.setItem('godmode-theme', theme); } catch { /* best-effort */ }
}

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

const saved = readTheme();
const initialResolved = applyTheme(saved);

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: saved,
  resolvedTheme: initialResolved,
  setTheme: (theme) => {
    const resolved = applyTheme(theme);
    writeTheme(theme);
    set({ theme, resolvedTheme: resolved });
  },
  toggleTheme: () => {
    const next: ThemeMode = get().resolvedTheme === 'light' ? 'dark' : 'light';
    const resolved = applyTheme(next);
    writeTheme(next);
    set({ theme: next, resolvedTheme: resolved });
  },
}));

if (window.matchMedia) {
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
    const savedMode = readTheme();
    if (savedMode === 'system') {
      const resolved = applyTheme('system');
      useThemeStore.setState({ theme: 'system', resolvedTheme: resolved });
    }
  });
}
