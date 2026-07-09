// Shared text-analysis helpers used by scoring, CV, and NHS engines.
// Deterministic and dependency-free so results are explainable and repeatable.

export const STOPWORDS = new Set(
  ('a an the and or of to in for with on at by from as is are be will you your we our '
    + 'this that these those role job work working experience able ability strong good '
    + 'excellent must have has having who what which within across using use used will '
    + 'candidate candidates applicant applicants team teams other others including etc '
    + 'per uk our their they them it its into out up down over under more most such can '
    + 'may should would could also than then them us me my i he she his her not no yes '
    // job-advert filler that is not a real skill/keyword
    + 'seeking join looking welcome welcomes compassionate essential desirable evidence '
    + 'provide provides provided require requires suitable available offer offers considered '
    + 'exceptional actual involvement based join us join our part full time role position '
    + 'responsibilities requirements ideal successful opportunity opportunities apply applying '
    + 'you will duties day-to-day well like new join keen able every')
    .split(/\s+/)
);

export function normalise(str = '') {
  return String(str).toLowerCase().replace(/[^a-z0-9+#. ]/g, ' ').replace(/\s+/g, ' ').trim();
}

export function tokens(str = '') {
  return normalise(str)
    .split(' ')
    .map((t) => t.replace(/^[.#]+|[.#]+$/g, '')) // trim edge dots/hashes ("ward." → "ward", keep "node.js")
    .filter(Boolean);
}

export function contentTokens(str = '') {
  return tokens(str).filter((t) => t.length > 2 && !STOPWORDS.has(t));
}

// Extract candidate keyword phrases (1–2 grams) ranked by frequency.
export function keywords(str = '', limit = 40) {
  const toks = contentTokens(str);
  const freq = new Map();
  const bump = (k) => freq.set(k, (freq.get(k) || 0) + 1);
  toks.forEach(bump);
  for (let i = 0; i < toks.length - 1; i++) {
    const bg = `${toks[i]} ${toks[i + 1]}`;
    bump(bg);
  }
  return [...freq.entries()]
    .filter(([k, c]) => (k.includes(' ') ? c >= 2 : c >= 1))
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([k]) => k);
}

// Does a haystack contain a phrase (all words present, order-independent)?
export function contains(haystack, phrase) {
  const h = normalise(haystack);
  return phrase.split(' ').every((w) => new RegExp(`\\b${escapeRe(w)}`).test(h));
}

function escapeRe(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Simple token-set similarity (Jaccard) for fuzzy company-name matching.
export function jaccard(a, b) {
  const A = new Set(contentTokens(a));
  const B = new Set(contentTokens(b));
  if (!A.size || !B.size) return 0;
  let inter = 0;
  A.forEach((t) => { if (B.has(t)) inter++; });
  return inter / (A.size + B.size - inter);
}

export function titleCase(str = '') {
  return str.replace(/\b\w/g, (c) => c.toUpperCase());
}
