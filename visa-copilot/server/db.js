// Lightweight persistent JSON data store with atomic writes.
// Chosen for zero native dependencies so the app runs anywhere Node 18+ runs.
// In production this layer maps cleanly onto PostgreSQL/Supabase (see README).
import { readFileSync, writeFileSync, existsSync, mkdirSync, renameSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_DIR = join(__dirname, '..', 'data');
const DB_FILE = join(DATA_DIR, 'db.json');

const EMPTY = {
  users: [],
  career_profiles: [],
  work_experiences: [],
  skills: [],
  documents: [],
  jobs: [],
  sponsor_records: [],
  job_scores: [],
  tailored_applications: [],
  applications: [],
  interview_sessions: [],
  audit_logs: [],
};

let cache = null;

function ensureDir() {
  if (!existsSync(DATA_DIR)) mkdirSync(DATA_DIR, { recursive: true });
}

export function load() {
  if (cache) return cache;
  ensureDir();
  if (existsSync(DB_FILE)) {
    try {
      cache = { ...EMPTY, ...JSON.parse(readFileSync(DB_FILE, 'utf8')) };
    } catch {
      cache = structuredClone(EMPTY);
    }
  } else {
    cache = structuredClone(EMPTY);
    persist();
  }
  return cache;
}

export function persist() {
  ensureDir();
  const tmp = DB_FILE + '.tmp';
  writeFileSync(tmp, JSON.stringify(cache, null, 2));
  renameSync(tmp, DB_FILE); // atomic on POSIX
}

// Generic table helpers ------------------------------------------------------
export function table(name) {
  const db = load();
  if (!db[name]) db[name] = [];
  return db[name];
}

export function insert(name, row) {
  const rec = { id: row.id || randomUUID(), created_at: new Date().toISOString(), ...row };
  table(name).push(rec);
  persist();
  return rec;
}

export function find(name, predicate) {
  return table(name).find(predicate);
}

export function filter(name, predicate) {
  return table(name).filter(predicate);
}

export function update(name, id, patch) {
  const rows = table(name);
  const idx = rows.findIndex((r) => r.id === id);
  if (idx === -1) return null;
  rows[idx] = { ...rows[idx], ...patch, updated_at: new Date().toISOString() };
  persist();
  return rows[idx];
}

export function remove(name, id) {
  const rows = table(name);
  const idx = rows.findIndex((r) => r.id === id);
  if (idx === -1) return false;
  rows.splice(idx, 1);
  persist();
  return true;
}

export function audit(entry) {
  return insert('audit_logs', {
    action: entry.action,
    entity_type: entry.entity_type || null,
    entity_id: entry.entity_id || null,
    user_id: entry.user_id || null,
    detail: entry.detail || null,
    timestamp: new Date().toISOString(),
  });
}

export { randomUUID };
