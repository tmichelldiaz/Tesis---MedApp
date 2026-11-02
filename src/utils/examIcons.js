import {
  Droplet, FlaskConical, HeartPulse, Activity, Scale, Thermometer, Pill,
} from 'lucide-react-native';

// Mapea el nombre de un examen a un ícono que realmente tiene que ver con lo
// que mide, en vez de ciclar por posición (que hacía que exámenes sin
// relación entre sí compartieran ícono al azar).
const RULES = [
  [/gluc|azucar|diabet/i, Droplet],
  [/colesterol|ldl|hdl|triglic/i, HeartPulse],
  [/hemoglobina|hematocrit|globul|leucocit|plaquet|eritrocit|hemograma/i, Droplet],
  [/creatinina|urea|renal|nitrogeno|riñon/i, Activity],
  [/tsh|tiroid|t3|t4/i, FlaskConical],
  [/presion|tension|arterial|cardiac|cardio/i, HeartPulse],
  [/peso|imc|talla|estatura/i, Scale],
  [/temperatura|fiebre/i, Thermometer],
  [/medicamento|dosis|mg|tableta/i, Pill],
];

export function iconForExam(examName) {
  const name = examName || '';
  for (const [pattern, Icon] of RULES) {
    if (pattern.test(name)) return Icon;
  }
  return FlaskConical;
}

const PALETTE = [
  { bg: '#F29BB2', fg: '#02204A' },
  { bg: '#7998FB', fg: '#FFFFFF' },
  { bg: '#034AA6', fg: '#FFFFFF' },
  { bg: '#C2D7F2', fg: '#034AA6' },
];

// Color estable por examen (mismo examen = mismo color siempre en toda la
// app), en vez de por posición en una lista que cambia de tamaño y orden.
export function colorForExam(examName) {
  const name = examName || '';
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) % 997;
  }
  return PALETTE[hash % PALETTE.length];
}

// Colores suaves por examen para las tarjetas del inicio y las citas: fondo claro
// y un tono más fuerte para el ícono y la línea. Son los mismos 5 tonos de las
// categorías de la Biblioteca (azul, rosado, morado, menta y durazno).
const SOFT = [
  { bg: '#DCE9F9', fg: '#034AA6' },
  { bg: '#FDE8EE', fg: '#D6456F' },
  { bg: '#EBE4FB', fg: '#6B4FD6' },
  { bg: '#DDF3EA', fg: '#1F8A62' },
  { bg: '#FFEBD2', fg: '#C26A12' },
];

function hashOf(name) {
  let hash = 0;
  for (let i = 0; i < (name || '').length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) % 997;
  }
  return hash;
}

// Color preferido de un examen (siempre el mismo para el mismo nombre).
export function softColorForExam(examName) {
  return SOFT[hashOf(examName) % SOFT.length];
}

// Reparte los colores entre las tarjetas que se muestran juntas para que no se
// repitan: cada examen parte de su color preferido y, si ya lo tomó otra tarjeta,
// pasa al siguiente libre. Con más tarjetas que colores se vuelven a usar.
export function assignSoftColors(examNames) {
  const used = new Set();
  const out = {};
  for (const name of examNames) {
    let idx = hashOf(name) % SOFT.length;
    if (used.size < SOFT.length) {
      while (used.has(idx)) idx = (idx + 1) % SOFT.length;
      used.add(idx);
    }
    out[name] = SOFT[idx];
  }
  return out;
}
