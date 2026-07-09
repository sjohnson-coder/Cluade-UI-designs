// Visa Sponsorship Job Copilot — Express server (static frontend + REST API).
import express from 'express';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { load } from './db.js';
import { seed } from './seed.js';
import api from './routes/api.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PORT = process.env.PORT || 3000;

// Ensure the store exists and is seeded on first boot.
load();
const seedResult = seed();

const app = express();
app.use(express.json({ limit: '2mb' }));

// Basic request log (kept minimal; swap for pino/OpenTelemetry in production).
app.use((req, _res, next) => {
  if (req.path.startsWith('/api')) console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
  next();
});

app.use('/api', api);

// Serve the frontend.
const publicDir = join(__dirname, '..', 'public');
app.use(express.static(publicDir));
app.get('*', (_req, res) => res.sendFile(join(publicDir, 'index.html')));

app.listen(PORT, () => {
  console.log('\n  Visa Sponsorship Job Copilot');
  console.log(`  ▸ Server:   http://localhost:${PORT}`);
  console.log(`  ▸ Seed:     ${seedResult.seeded ? `${seedResult.jobs} jobs, ${seedResult.sponsors} sponsors` : 'existing data'}`);
  console.log('  ▸ AI:       set OPENAI_API_KEY or ANTHROPIC_API_KEY for LLM enrichment (optional)\n');
});
