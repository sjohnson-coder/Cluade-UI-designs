// Seeds a rich, realistic demo dataset so the app is useful on first run.
// Sponsor rows mirror the shape of the UK Register of Licensed Sponsors (Workers).
import { load, persist, table } from './db.js';
import { scoreJobForProfile } from './services/scoring.js';

const SPONSORS = [
  { organisation_name: 'NHS England', town: 'Leeds', county: 'West Yorkshire', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: "Guy's and St Thomas' NHS Foundation Trust", town: 'London', county: 'Greater London', rating: 'A rating', route: 'Skilled Worker, Health and Care Worker' },
  { organisation_name: 'Manchester University NHS Foundation Trust', town: 'Manchester', county: 'Greater Manchester', rating: 'A rating', route: 'Health and Care Worker' },
  { organisation_name: 'Sunrise Care Group Ltd', town: 'Birmingham', county: 'West Midlands', rating: 'A rating', route: 'Health and Care Worker' },
  { organisation_name: 'Monzo Bank Limited', town: 'London', county: 'Greater London', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: 'Revolut Ltd', town: 'London', county: 'Greater London', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: 'Arm Limited', town: 'Cambridge', county: 'Cambridgeshire', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: 'Ocado Group plc', town: 'Hatfield', county: 'Hertfordshire', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: 'Rolls-Royce plc', town: 'Derby', county: 'Derbyshire', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: 'Deloitte LLP', town: 'London', county: 'Greater London', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: 'BrightFuture Academy Trust', town: 'Bristol', county: 'Bristol', rating: 'A rating', route: 'Skilled Worker' },
  { organisation_name: 'Greenwave Renewables Ltd', town: 'Glasgow', county: 'Glasgow City', rating: 'A rating', route: 'Skilled Worker' },
];

const JOBS = [
  {
    title: 'Registered Nurse (Band 5) — General Medicine',
    company: "Guy's and St Thomas' NHS Foundation Trust",
    location: 'London', region: 'Greater London', remote: 'On-site',
    salary_min: 28407, salary_max: 34581, currency: 'GBP',
    sector: 'Healthcare', seniority: 'Mid', contract: 'Full-time',
    source: 'NHS Jobs', source_url: 'https://www.jobs.nhs.uk/candidate', nhs: true, band: 'Band 5',
    closing_date: daysFromNow(9), posted_date: daysFromNow(-4),
    description: 'We are seeking a compassionate Registered Nurse (NMC registered) to join our general medicine ward. Essential: NMC registration, evidence of safe patient care, medication administration, care planning, safeguarding awareness, and effective communication with the multidisciplinary team. Desirable: acute medicine experience, mentorship of student nurses, and quality improvement involvement. We welcome overseas applicants and provide Health and Care Worker visa sponsorship and relocation support. Supporting information against the person specification is required.',
    essential_criteria: ['NMC registration', 'Safe patient care', 'Medication administration', 'Safeguarding awareness', 'Communication with MDT', 'Accurate documentation'],
    desirable_criteria: ['Acute medicine experience', 'Mentorship of students', 'Quality improvement'],
  },
  {
    title: 'Senior Backend Engineer (Go / TypeScript)',
    company: 'Monzo Bank Limited',
    location: 'London', region: 'Greater London', remote: 'Hybrid',
    salary_min: 85000, salary_max: 110000, currency: 'GBP',
    sector: 'Technology', seniority: 'Senior', contract: 'Full-time',
    source: 'Greenhouse', source_url: 'https://boards.greenhouse.io/monzo', nhs: false,
    closing_date: daysFromNow(21), posted_date: daysFromNow(-2),
    description: 'Join our platform team building resilient, distributed banking services. You will design and ship microservices in Go and TypeScript, own reliability (SLOs, on-call), work with Kubernetes, and improve CI/CD. We offer Skilled Worker visa sponsorship for eligible candidates and support relocation to the UK. Requirements: strong distributed systems experience, API design, PostgreSQL, observability, and testing discipline.',
    essential_criteria: ['Distributed systems', 'Go or TypeScript', 'PostgreSQL', 'Kubernetes', 'API design', 'Testing discipline'],
    desirable_criteria: ['Fintech experience', 'Event-driven architecture', 'Observability tooling'],
  },
  {
    title: 'Senior Care Assistant — Sponsorship Available',
    company: 'Sunrise Care Group Ltd',
    location: 'Birmingham', region: 'West Midlands', remote: 'On-site',
    salary_min: 23200, salary_max: 25600, currency: 'GBP',
    sector: 'Care', seniority: 'Mid', contract: 'Full-time',
    source: 'Employer site', source_url: 'https://example.com/sunrisecare/jobs', nhs: false,
    closing_date: daysFromNow(6), posted_date: daysFromNow(-6),
    description: 'Sunrise Care Group is a licensed Health and Care Worker sponsor. We are hiring experienced Senior Care Assistants to lead care delivery, support medication rounds, and mentor junior staff. Certificate of Sponsorship available for suitable candidates. Care Certificate and enhanced DBS required. Essential: person-centred care, safeguarding, moving and handling, dignity and respect, and record keeping.',
    essential_criteria: ['Person-centred care', 'Safeguarding', 'Moving and handling', 'Medication support', 'Record keeping', 'Care Certificate'],
    desirable_criteria: ['NVQ Level 3 Health & Social Care', 'Dementia care experience', 'Team leadership'],
  },
  {
    title: 'Data Analyst — Commercial Insights',
    company: 'Ocado Group plc',
    location: 'Hatfield', region: 'Hertfordshire', remote: 'Hybrid',
    salary_min: 45000, salary_max: 55000, currency: 'GBP',
    sector: 'Technology', seniority: 'Mid', contract: 'Full-time',
    source: 'Lever', source_url: 'https://jobs.lever.co/ocado', nhs: false,
    closing_date: daysFromNow(14), posted_date: daysFromNow(-1),
    description: 'We are looking for a Data Analyst to turn commercial data into actionable insight. You will build dashboards, run SQL analysis, work with Python and stakeholders across the business. Skilled Worker visa sponsorship considered for exceptional candidates. Requirements: SQL, data visualisation (Looker/Tableau), stakeholder communication, and statistical literacy.',
    essential_criteria: ['SQL', 'Data visualisation', 'Stakeholder communication', 'Statistical literacy', 'Python'],
    desirable_criteria: ['Retail/e-commerce domain', 'dbt', 'A/B testing'],
  },
  {
    title: 'Mechanical Design Engineer',
    company: 'Rolls-Royce plc',
    location: 'Derby', region: 'East Midlands', remote: 'On-site',
    salary_min: 42000, salary_max: 52000, currency: 'GBP',
    sector: 'Engineering', seniority: 'Mid', contract: 'Full-time',
    source: 'Workday', source_url: 'https://rolls-royce.wd3.myworkdayjobs.com', nhs: false,
    closing_date: daysFromNow(18), posted_date: daysFromNow(-8),
    description: 'Design engineer role within our aerospace division. You will develop mechanical components, run CAD and FEA, support manufacturing, and ensure compliance with airworthiness standards. Visa sponsorship under the Skilled Worker route available for eligible engineers. Essential: mechanical engineering degree, CAD (CATIA/NX), FEA, tolerancing, and design for manufacture.',
    essential_criteria: ['Mechanical engineering degree', 'CAD (CATIA or NX)', 'FEA', 'Design for manufacture', 'GD&T tolerancing'],
    desirable_criteria: ['Aerospace domain', 'Chartered Engineer status', 'Materials science'],
  },
  {
    title: 'Customer Support Associate (No Sponsorship)',
    company: 'QuickShip Logistics',
    location: 'Leeds', region: 'West Yorkshire', remote: 'On-site',
    salary_min: 22000, salary_max: 23500, currency: 'GBP',
    sector: 'Business', seniority: 'Entry', contract: 'Full-time',
    source: 'Job board', source_url: 'https://example.com/quickship', nhs: false,
    closing_date: daysFromNow(11), posted_date: daysFromNow(-3),
    description: 'Front-line customer support role. You must have the right to work in the UK — we are unable to offer visa sponsorship for this position. Responsibilities: handle customer queries via phone and email, use our CRM, and resolve delivery issues.',
    essential_criteria: ['Right to work in the UK', 'Customer service', 'CRM usage', 'Communication'],
    desirable_criteria: ['Logistics experience'],
  },
  {
    title: 'Secondary School Teacher — Mathematics',
    company: 'BrightFuture Academy Trust',
    location: 'Bristol', region: 'South West', remote: 'On-site',
    salary_min: 30000, salary_max: 46525, currency: 'GBP',
    sector: 'Education', seniority: 'Mid', contract: 'Full-time',
    source: 'Employer site', source_url: 'https://example.com/brightfuture', nhs: false,
    closing_date: daysFromNow(4), posted_date: daysFromNow(-10),
    description: 'We are recruiting a qualified Mathematics teacher for KS3 and KS4. QTS required (or willingness to obtain). We are a licensed Skilled Worker sponsor and welcome overseas-trained teachers. Essential: subject knowledge, lesson planning, behaviour management, safeguarding, and assessment.',
    essential_criteria: ['QTS or equivalent', 'Mathematics subject knowledge', 'Lesson planning', 'Behaviour management', 'Safeguarding', 'Assessment'],
    desirable_criteria: ['A-level teaching', 'Form tutor experience', 'Exam board familiarity'],
  },
  {
    title: 'Renewables Project Engineer',
    company: 'Greenwave Renewables Ltd',
    location: 'Glasgow', region: 'Scotland', remote: 'Hybrid',
    salary_min: 40000, salary_max: 50000, currency: 'GBP',
    sector: 'Engineering', seniority: 'Mid', contract: 'Full-time',
    source: 'Ashby', source_url: 'https://jobs.ashbyhq.com/greenwave', nhs: false,
    closing_date: daysFromNow(25), posted_date: daysFromNow(-5),
    description: 'Support the delivery of onshore wind and solar projects. You will manage project schedules, coordinate contractors, and ensure HSE compliance. Skilled Worker sponsorship available. Essential: engineering background, project coordination, stakeholder management, and HSE awareness.',
    essential_criteria: ['Engineering background', 'Project coordination', 'Stakeholder management', 'HSE awareness', 'Scheduling'],
    desirable_criteria: ['Renewables sector', 'PRINCE2', 'Contractor management'],
  },
];

function daysFromNow(n) {
  const d = new Date();
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export function seed({ force = false } = {}) {
  const db = load();
  if (db.jobs.length && !force) return { skipped: true };

  // Reset seedable tables (leave user-created applications intact unless forced).
  db.sponsor_records = [];
  db.jobs = [];
  db.users = db.users.filter((u) => u.email !== 'demo@visacopilot.app');
  db.career_profiles = [];
  db.work_experiences = [];
  db.skills = [];
  db.job_scores = [];

  const now = new Date().toISOString();
  SPONSORS.forEach((s, i) =>
    db.sponsor_records.push({ id: `sp_${i + 1}`, ...s, import_date: now })
  );

  // Demo user + career vault (single source of truth for the AI engines).
  const user = {
    id: 'demo-user',
    email: 'demo@visacopilot.app',
    name: 'Amara Okafor',
    role: 'candidate',
    subscription_plan: 'Pro',
    created_at: now,
  };
  db.users.push(user);

  const profile = {
    id: 'demo-profile',
    user_id: user.id,
    target_roles: ['Registered Nurse', 'Staff Nurse', 'Healthcare Practitioner'],
    visa_status: 'Requires Skilled Worker / Health and Care Worker sponsorship',
    location: 'London (open to relocation)',
    salary_expectation: 30000,
    sectors: ['Healthcare', 'Care'],
    nhs_preferences: { bands: ['Band 5'], staff_group: 'Nursing and Midwifery', registration: 'NMC' },
    created_at: now,
  };
  db.career_profiles.push(profile);

  const work = [
    {
      id: 'we_1', profile_id: profile.id,
      employer: 'Lagos University Teaching Hospital', title: 'Staff Nurse',
      start_date: '2020-03', end_date: '2024-11',
      responsibilities: 'Delivered ward-based nursing care on a 32-bed general medical ward. Administered medication, recorded observations, escalated deteriorating patients, and supported care planning within the multidisciplinary team.',
      achievements: 'Mentored 6 student nurses; contributed to a documentation audit that improved record completeness across the ward.',
      metrics: '32-bed ward, up to 8 patients per shift, 6 students mentored',
      evidence_status: 'verified',
    },
    {
      id: 'we_2', profile_id: profile.id,
      employer: 'St Raphael Community Clinic', title: 'Registered Nurse (Bank)',
      start_date: '2019-01', end_date: '2020-02',
      responsibilities: 'Provided outpatient nursing care, wound management, and health education. Maintained accurate documentation and safeguarding awareness.',
      achievements: 'Introduced a wound-care checklist adopted by the clinic team.',
      metrics: 'Outpatient clinic, ~20 patients per day',
      evidence_status: 'verified',
    },
  ];
  work.forEach((w) => db.work_experiences.push(w));

  const skills = [
    ['Patient care', 'Clinical', 'expert'], ['Medication administration', 'Clinical', 'advanced'],
    ['Safeguarding', 'Clinical', 'advanced'], ['Care planning', 'Clinical', 'advanced'],
    ['Documentation', 'Clinical', 'expert'], ['Communication', 'Soft', 'expert'],
    ['Mentorship', 'Soft', 'advanced'], ['NMC registration (in progress)', 'Qualification', 'intermediate'],
    ['Wound management', 'Clinical', 'advanced'], ['Multidisciplinary teamwork', 'Soft', 'advanced'],
  ];
  skills.forEach(([skill, category, level], i) =>
    db.skills.push({ id: `sk_${i + 1}`, profile_id: profile.id, skill, category, level, evidence_source: 'CV' })
  );

  JOBS.forEach((j, i) => {
    const rec = { id: `job_${i + 1}`, status: 'active', ...j, created_at: now };
    db.jobs.push(rec);
  });

  // Precompute scores for the demo profile against every job.
  db.job_scores = [];
  db.jobs.forEach((job) => {
    const score = scoreJobForProfile(job, { profile, skills: db.skills, sponsors: db.sponsor_records });
    db.job_scores.push({ id: `js_${job.id}`, job_id: job.id, user_id: user.id, ...score, created_at: now });
  });

  persist();
  return { seeded: true, jobs: db.jobs.length, sponsors: db.sponsor_records.length };
}

// Allow `npm run seed`
if (import.meta.url === `file://${process.argv[1]}`) {
  const res = seed({ force: true });
  console.log('Seed complete:', res);
}
