import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000'
    }
  },
  build: {
    // The bot targets a desktop sitting next to MetaTrader 5, plus modern phones over LAN/Tailscale.
    // Raising the target lets esbuild keep native async/await, optional chaining and nullish
    // coalescing rather than downlevelling syntax this codebase uses on nearly every line.
    target: 'es2020',
    cssTarget: 'chrome100',
    sourcemap: false,
    // recharts (421 KB) landed inside the same lazy chunk as the Analytics page, so opening
    // Analytics pulled the charting library and the page code as one indivisible download, and
    // neither could be cached independently. Splitting the three large vendor libraries out means
    // a rebuild of application code no longer invalidates ~730 KB of unchanged vendor bytes in the
    // browser cache, and a page needing one charting library stops paying for the other.
    // Vite 8 bundles with rolldown, which accepts manualChunks only in its function form.
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return;
          if (id.includes('recharts') || id.includes('d3-') || id.includes('victory-vendor')) return 'vendor-recharts';
          if (id.includes('lightweight-charts')) return 'vendor-lwcharts';
          if (id.includes('react-dom') || /node_modules[\\/]react[\\/]/.test(id) || id.includes('scheduler')) return 'vendor-react';
          return;
        },
      },
    },
    chunkSizeWarningLimit: 700,
  },
});
