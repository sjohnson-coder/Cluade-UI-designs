// Thin fetch wrapper around the REST API.
const BASE = '/api';

async function req(path, { method = 'GET', body } = {}) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${txt}`);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  status: () => req('/status'),
  me: () => req('/me'),
  vault: () => req('/vault'),
  addExperience: (b) => req('/vault/experience', { method: 'POST', body: b }),
  addSkill: (b) => req('/vault/skill', { method: 'POST', body: b }),

  jobs: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null)).toString();
    return req('/jobs' + (q ? '?' + q : ''));
  },
  job: (id) => req('/jobs/' + id),
  addJob: (b) => req('/jobs', { method: 'POST', body: b }),

  cvScan: (b) => req('/cv/scan', { method: 'POST', body: b }),
  cvSurgeon: (b) => req('/cv/surgeon', { method: 'POST', body: b }),
  cvStress: (b) => req('/cv/stress-test', { method: 'POST', body: b }),

  nhsMatrix: (b) => req('/nhs/matrix', { method: 'POST', body: b }),
  nhsStatement: (b) => req('/nhs/statement', { method: 'POST', body: b }),

  interviewQuestions: (b) => req('/interview/questions', { method: 'POST', body: b }),
  interviewScore: (b) => req('/interview/score', { method: 'POST', body: b }),

  applications: () => req('/applications'),
  saveApplication: (b) => req('/applications', { method: 'POST', body: b }),
  updateApplication: (id, b) => req('/applications/' + id, { method: 'PATCH', body: b }),
  deleteApplication: (id) => req('/applications/' + id, { method: 'DELETE' }),

  sponsors: (q = '') => req('/sponsors' + (q ? '?q=' + encodeURIComponent(q) : '')),
  audit: () => req('/audit'),
};
