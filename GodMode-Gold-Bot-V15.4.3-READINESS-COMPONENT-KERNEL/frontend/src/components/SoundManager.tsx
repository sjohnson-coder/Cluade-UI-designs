import { useEffect } from 'react';
import { useSoundStore } from '../store/soundStore';

export function useGodModeSounds() {
  const play = useSoundStore((s) => s.play);
  const enabled = useSoundStore((s) => s.enabled);

  useEffect(() => {
    const handler = (event: MouseEvent) => {
      if (!enabled) return;
      const target = event.target as HTMLElement | null;
      const clickable = target?.closest('button, .nav-item, .toggle, .select, [data-sound]');
      if (!clickable) return;
      const variant = clickable.getAttribute('data-sound') || '';
      if (variant === 'success') play('success');
      else if (variant === 'warning') play('warning');
      else if (variant === 'danger') play('danger');
      else if (variant === 'navigate' || clickable.classList.contains('nav-item')) play('navigate');
      else if (clickable.classList.contains('toggle') || clickable.classList.contains('theme-toggle')) play('toggle');
      else play('click');
    };
    document.addEventListener('click', handler, true);
    return () => document.removeEventListener('click', handler, true);
  }, [enabled, play]);
}
