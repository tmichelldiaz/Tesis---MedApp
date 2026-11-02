// Helpers compartidos entre Dashboard y el detalle de un examen, para no
// duplicar la lógica de "¿está en rango?" / "¿subió o bajó?" en dos pantallas.

export function inRange(v) {
  if (v.value_numeric == null) return null;
  if (v.reference_low != null && v.value_numeric < v.reference_low) return false;
  if (v.reference_high != null && v.value_numeric > v.reference_high) return false;
  if (v.reference_low == null && v.reference_high == null) return null;
  return true;
}

export function trendOf(latest, previous) {
  if (!previous || latest.value_numeric == null || previous.value_numeric == null) return null;
  if (latest.value_numeric > previous.value_numeric) return 'up';
  if (latest.value_numeric < previous.value_numeric) return 'down';
  return 'same';
}

// Distancia de un valor al rango de referencia: 0 si está dentro (o no hay
// rango). Sirve para saber si un cambio acerca o aleja al paciente de lo normal.
function distanceOutside(v) {
  if (v.value_numeric == null) return 0;
  if (v.reference_low != null && v.value_numeric < v.reference_low) return v.reference_low - v.value_numeric;
  if (v.reference_high != null && v.value_numeric > v.reference_high) return v.value_numeric - v.reference_high;
  return 0;
}

const SAME_TOLERANCE = 0.02;

// Compara el último resultado con el anterior y dice si mejoró o empeoró.
// "Mejor" significa más cerca del rango de referencia, no "más bajo": subir la
// hemoglobina puede ser bueno y subir la glucosa no. Sin rango de referencia no
// se juzga, solo se describe el cambio. Devuelve null si no hay con qué comparar.
export function evolutionOf(history) {
  const numeric = (history || []).filter((h) => h.value_numeric != null);
  if (numeric.length < 2) return null;
  const latest = numeric[numeric.length - 1];
  const previous = numeric[numeric.length - 2];
  const change = latest.value_numeric - previous.value_numeric;
  const base = Math.abs(previous.value_numeric) || 1;
  const pct = (change / base) * 100;
  const hasRange = latest.reference_low != null || latest.reference_high != null;
  const nearlySame = Math.abs(change) / base < SAME_TOLERANCE;

  let verdict;
  if (!hasRange) {
    verdict = nearlySame ? 'same' : change > 0 ? 'up' : 'down';
  } else {
    const before = distanceOutside(previous);
    const after = distanceOutside(latest);
    if (before === 0 && after === 0) verdict = 'stable';
    else if (Math.abs(after - before) / (Math.max(before, after) || 1) < SAME_TOLERANCE) verdict = 'same';
    else verdict = after < before ? 'better' : 'worse';
  }
  return { verdict, change, pct, latest, previous, hasRange };
}

const VERDICT_LABEL = {
  better: 'Mejoró', worse: 'Empeoró', stable: 'Estable',
  same: 'Sin cambios', up: 'Subió', down: 'Bajó',
};
export const verdictLabel = (verdict) => VERDICT_LABEL[verdict] || null;

const fmtNum = (n) => String(Math.round(n * 100) / 100).replace('.', ',');
const fmtDay = (iso) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  if (!m) return null;
  return new Date(+m[1], +m[2] - 1, +m[3]).toLocaleDateString('es-CO', { day: 'numeric', month: 'short', year: 'numeric' });
};
// Algunos valores ya traen su unidad dentro del texto ("1.8 cm"): agregarla de nuevo daba "1.8 cm cm".
export function unitSuffix(raw, unit) {
  if (!unit) return '';
  const clean = (t) => String(t || '').toLowerCase().replace(/\s+/g, ' ').trim();
  const r = clean(raw);
  const u = clean(unit);
  if (!u || r === u || r.endsWith(` ${u}`) || r.endsWith(u)) return '';
  return unit;
}

// El valor tal como se muestra: con su unidad una sola vez.
export const withUnit = (raw, unit) => [raw, unitSuffix(raw, unit)].filter((x) => x !== '' && x != null).join(' ');

// Resumen en lenguaje sencillo, armado solo con los datos del paciente (sin
// IA, así que no cuesta ni puede inventar nada). Lo que no se puede afirmar,
// no se afirma: sin rango de referencia no dice si es bueno o malo.
export function summaryText(history) {
  const rows = history || [];
  const latest = rows[rows.length - 1];
  if (!latest) return '';
  const when = fmtDay(latest.date);
  const parts = [`Tu último resultado es ${withUnit(latest.value_raw, latest.unit)}${when ? ` (${when})` : ''}.`];

  const status = inRange(latest);
  const hasLow = latest.reference_low != null;
  const hasHigh = latest.reference_high != null;
  if (status !== null) {
    const range = hasLow && hasHigh ? `${latest.reference_low} a ${latest.reference_high}`
      : hasHigh ? `hasta ${latest.reference_high}` : `desde ${latest.reference_low}`;
    parts.push(status
      ? `Está dentro del rango de referencia (${range}).`
      : `Está fuera del rango de referencia (${range}).`);
  }

  const evo = evolutionOf(rows);
  if (evo) {
    const before = withUnit(evo.previous.value_raw, evo.previous.unit);
    const prevWhen = fmtDay(evo.previous.date);
    const since = `${before}${prevWhen ? ` el ${prevWhen}` : ''}`;
    const pct = Math.abs(evo.pct) >= 0.5 ? ` (${evo.pct > 0 ? '+' : '−'}${(Math.round(Math.abs(evo.pct) * 10) / 10).toString().replace('.', ',')} %)` : '';
    if (evo.verdict === 'better') parts.push(`Mejoró: venía de ${since}${pct} y ahora está más cerca de lo normal.`);
    else if (evo.verdict === 'worse') parts.push(`Empeoró: venía de ${since}${pct} y ahora está más lejos de lo normal.`);
    else if (evo.verdict === 'stable') parts.push(`Se mantiene dentro del rango; antes fue ${since}${pct}.`);
    else if (evo.verdict === 'same') parts.push(`Sin cambios importantes frente a ${since}.`);
    else parts.push(`${evo.verdict === 'up' ? 'Subió' : 'Bajó'} frente a ${since}${pct}. Sin un rango de referencia no puedo decir si eso es bueno o malo.`);
  }
  return parts.join(' ');
}

// Qué tan importante es mostrar un examen en el inicio: primero lo que está
// fuera de rango, luego lo que tiene historial para graficar, luego lo reciente.
export function importanceScore(exam) {
  let score = 0;
  if (exam.status === false) score += 100;
  if ((exam.history || []).filter((h) => h.value_numeric != null).length >= 2) score += 10;
  if (exam.value_numeric != null) score += 5;
  return score;
}

// Los resultados clave del inicio: los `count` más importantes de la ÚLTIMA historia
// que subió el paciente. Si esa historia tiene menos de `count` exámenes, se completa
// con los más importantes de las historias anteriores, de la más reciente hacia atrás.
export function keyExams(exams, count) {
  if (exams.length === 0) return [];
  const newest = exams.reduce((best, e) => (e.uploaded_at > best.uploaded_at ? e : best), exams[0]);
  const fromNewest = exams.filter((e) => e.document_id === newest.document_id);
  const older = exams
    .filter((e) => e.document_id !== newest.document_id)
    .sort((a, b) => b.uploaded_at.localeCompare(a.uploaded_at));
  return [...topExams(fromNewest, count), ...topExams(older, count)].slice(0, count);
}

export function topExams(exams, count) {
  return exams
    .map((e, i) => ({ e, i, score: importanceScore(e) }))
    .sort((a, b) => b.score - a.score || a.i - b.i)
    .slice(0, count)
    .map((x) => x.e);
}

// Agrupa filas de /values por examen (insensible a mayúsculas), ordena cada
// grupo por fecha y devuelve un resumen por examen: valor más reciente,
// tendencia contra el anterior, y si está dentro del rango de referencia.
// Orden de "más viejo a más nuevo": primero por la fecha del examen y, cuando no
// tiene fecha o es la misma, por la fecha en que se subió el archivo. Sin esto el
// servidor entrega los archivos del más nuevo al más viejo y un examen sin fecha
// terminaba mostrando el resultado del archivo más viejo como "el último".
export function sortByRecency(rows, createdAtByDoc = {}) {
  const stamp = (r) => r.document_created_at || createdAtByDoc[r.document_id] || '';
  return [...rows].sort(
    (a, b) => (a.date || '').localeCompare(b.date || '') || stamp(a).localeCompare(stamp(b))
  );
}

export function summarizeByExam(rows, createdAtByDoc = {}) {
  const byExam = new Map();
  for (const row of rows) {
    const key = row.exam.toLowerCase();
    if (!byExam.has(key)) byExam.set(key, []);
    byExam.get(key).push(row);
  }
  const exams = [];
  for (const rawGroup of byExam.values()) {
    const group = sortByRecency(rawGroup, createdAtByDoc);
    const latest = group[group.length - 1];
    const previous = group.length > 1 ? group[group.length - 2] : null;
    exams.push({
      ...latest,
      trend: trendOf(latest, previous),
      status: inRange(latest),
      history: group,
      uploaded_at: latest.document_created_at || createdAtByDoc[latest.document_id] || '',
    });
  }
  exams.sort(
    (a, b) => (b.date || '').localeCompare(a.date || '') || b.uploaded_at.localeCompare(a.uploaded_at)
  );
  return exams;
}

export function ageFromBirthDate(isoDate) {
  if (!isoDate) return null;
  // No usar `new Date(isoDate)` directo: un string "solo fecha" (YYYY-MM-DD)
  // se interpreta como medianoche UTC, y en zonas horarias negativas
  // (Colombia, UTC-5) eso corre la fecha local un día hacia atrás. Se
  // parsean los componentes a mano para que sea una fecha local, no UTC.
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(isoDate);
  if (!match) return null;
  const [, y, m, d] = match.map(Number);
  const birth = new Date(y, m - 1, d);
  if (Number.isNaN(birth.getTime())) return null;
  const now = new Date();
  let age = now.getFullYear() - birth.getFullYear();
  const hasHadBirthdayThisYear =
    now.getMonth() > birth.getMonth() ||
    (now.getMonth() === birth.getMonth() && now.getDate() >= birth.getDate());
  if (!hasHadBirthdayThisYear) age -= 1;
  return age;
}

const compact = (text) => String(text || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '');

// A veces el valor llega con el nombre del examen delante ("PIRADS 2" para el examen PIRADS): lo que
// importa es solo "2". Se quita el nombre cuando va al principio y queda algo después.
export function cleanValueRaw(raw, exam) {
  if (raw == null || !exam) return raw;
  const text = String(raw).trim();
  const target = compact(exam);
  if (!target) return raw;
  const tokens = text.split(/\s+/);
  for (let k = 1; k < tokens.length; k++) {
    if (compact(tokens.slice(0, k).join(' ')) === target) {
      const rest = tokens.slice(k).join(' ').replace(/^[:\-–]\s*/, '').trim();
      return rest || raw;
    }
  }
  return raw;
}
