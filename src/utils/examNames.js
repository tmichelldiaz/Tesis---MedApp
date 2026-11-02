// Los nombres que salen de las historias son largos ("RM multiparamétrica de
// próstata PI-RADS..."). En tarjetas pequeñas se muestra un título corto; el
// nombre completo se conserva en la pantalla de detalle.

// Orden importa: la primera regla que coincide gana, así que lo más específico
// va antes ("densidad de PSA" antes que "PSA").
const SHORT_NAMES = [
  [/densidad.*psa|psa.*densidad/i, 'Densidad PSA'],
  [/psa.*libre|libre.*psa/i, 'PSA libre'],
  [/\bpsa\b|ant[ií]geno prost/i, 'PSA'],
  [/(rm|resonancia).*pr[oó]st[aá]t|pr[oó]st[aá]t.*(rm|resonancia)/i, 'RM próstata'],
  [/biopsia.*pr[oó]st[aá]t/i, 'Biopsia próstata'],
  [/peso.*pr[oó]st[aá]t|volumen.*pr[oó]st[aá]t/i, 'Peso próstata'],
  [/hemoglobina\s*glic|hba1c|a1c/i, 'HbA1c'],
  [/gluc[oó]sa|glicemia|glucemia/i, 'Glucosa'],
  [/colesterol.*ldl|\bldl\b/i, 'Colesterol LDL'],
  [/colesterol.*hdl|\bhdl\b/i, 'Colesterol HDL'],
  [/colesterol/i, 'Colesterol total'],
  [/triglic[eé]ridos/i, 'Triglicéridos'],
  [/creatinina/i, 'Creatinina'],
  [/\btsh\b|hormona estimulante.*tiroid/i, 'TSH'],
  [/t4\s*libre|tiroxina libre/i, 'T4 libre'],
  [/hemoglobina(?!.*(corpuscular|glic))/i, 'Hemoglobina'],
  [/hematocrito/i, 'Hematocrito'],
  [/leucocitos/i, 'Leucocitos'],
  [/plaquetas/i, 'Plaquetas'],
  [/presi[oó]n arterial|tensi[oó]n arterial/i, 'Presión arterial'],
  [/\bpeso\b/i, 'Peso'],
  [/\bimc\b|[ií]ndice de masa/i, 'IMC'],
];

// Siglas que se dejan en mayúsculas aunque el resto del nombre pase a minúsculas.
const ACRONYMS = new Set([
  'ldl', 'hdl', 'vldl', 'psa', 'tsh', 'vcm', 'hcm', 'chcm', 'pcr', 'vsg', 'alt', 'ast', 'ggt',
  'rm', 'tac', 'imc', 'hba1c', 'rdw', 'mpv', 'inr', 'tp', 'ttp', 'bun', 'adn', 'vih', 'cea',
  'ca', 'fsh', 'lh', 'gh', 'acth', 'ft3', 'ft4', 't3', 't4', 'igg', 'igm', 'iga', 'ige',
]);

// Palabras que llegan sin tilde en muchos laboratorios (todo en mayúsculas) y que
// leen mal así. Es una lista corta de las más comunes; lo demás se deja como viene.
const ACCENTS = {
  globulos: 'glóbulos', hematies: 'hematíes', trigliceridos: 'triglicéridos',
  proteina: 'proteína', proteinas: 'proteínas', acido: 'ácido', urico: 'úrico',
  creatinina: 'creatinina', hemoglobina: 'hemoglobina', corpuscular: 'corpuscular',
  glicosilada: 'glicosilada', glucemia: 'glucemia', prostatico: 'prostático',
  prostatica: 'prostática', antigeno: 'antígeno', especifico: 'específico',
  bilirrubina: 'bilirrubina', fosfatasa: 'fosfatasa', alcalina: 'alcalina', calcio: 'calcio',
  plaquetas: 'plaquetas', leucocitos: 'leucocitos', neutrofilos: 'neutrófilos',
  linfocitos: 'linfocitos', monocitos: 'monocitos', eosinofilos: 'eosinófilos',
  basofilos: 'basófilos', hematocrito: 'hematocrito', volumen: 'volumen',
  medio: 'medio', media: 'media', recuento: 'recuento', indice: 'índice',
  densidad: 'densidad', resonancia: 'resonancia', magnetica: 'magnética',
  multiparametrica: 'multiparamétrica', biopsia: 'biopsia', ecografia: 'ecografía',
  tension: 'tensión', presion: 'presión',
};

// "RECUENTO GLOBULOS BLANCOS" -> "Recuento glóbulos blancos": primera letra en
// mayúscula y el resto en minúscula, sin perder las siglas. Un nombre que ya es
// solo una sigla (TSH, PSA) se queda como está.
export function formatExamName(name) {
  const text = (name || '').trim().replace(/\s+/g, ' ');
  if (!text) return '';
  const words = text.split(' ');
  if (words.length === 1 && /^[A-ZÁÉÍÓÚÑ0-9]{2,5}$/.test(words[0])) return words[0];
  const fixed = words.map((raw) => {
    const lower = raw.toLowerCase();
    const bare = lower.replace(/[^a-záéíóúñ0-9]/g, '');
    if (bare === 'hba1c') return raw.replace(/hba1c/i, 'HbA1c');
    if (ACRONYMS.has(bare)) return raw.toUpperCase();
    // Número romano o código corto en mayúsculas dentro de una frase (p. ej. "PI-RADS").
    if (/^[A-Z]{2,}-[A-Z]+$/.test(raw)) return raw;
    const stripped = bare in ACCENTS ? lower.replace(bare, ACCENTS[bare]) : lower;
    return stripped;
  });
  const sentence = fixed.join(' ');
  return sentence.charAt(0).toUpperCase() + sentence.slice(1);
}

// Palabras de enlace que, escritas en mayúscula dentro de una frase en mayúsculas, se bajan a minúscula.
const SMALL_WORDS = new Set(['DE', 'EN', 'LA', 'EL', 'LOS', 'LAS', 'DEL', 'Y', 'O', 'CON', 'POR', 'PARA', 'UN', 'UNA', 'AL', 'SU', 'SUS']);

// Un nombre de examen copiado tal cual del laboratorio ("RECUENTO DE GLOBULOS BLANCOS") deja la
// pregunta en mayúsculas. Esto baja a minúscula solo las palabras que vienen TODAS en mayúscula,
// conserva las siglas (LDL, TSH, PSA...), repone la tilde de las palabras comunes y deja la
// primera letra de la frase en mayúscula. Las palabras que ya estaban bien escritas no se tocan.
export function formatQuestion(text) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim();
  if (!clean) return '';
  const fixed = clean.replace(/[A-ZÁÉÍÓÚÑ0-9]{2,}(?:-[A-ZÁÉÍÓÚÑ0-9]+)*/g, (word) => {
    const lower = word.toLowerCase();
    const bare = lower.replace(/[^a-záéíóúñ0-9]/g, '');
    if (bare === 'hba1c') return 'HbA1c';
    if (ACRONYMS.has(bare)) return word;
    if (word.length === 2 && !SMALL_WORDS.has(word)) return word;       // una sigla de 2 letras: se deja
    if (/\d/.test(word) && /[A-Z]/.test(word)) return word;               // códigos como "T4L"
    if (word.includes('-')) return word;                                    // "PI-RADS"
    return bare in ACCENTS ? lower.replace(bare, ACCENTS[bare]) : lower;
  });
  // "BLANCOS Y PLAQUETAS": la Y u O suelta entre palabras ya en minúscula también se baja.
  const joined = fixed.replace(/([a-záéíóúñ]) ([YO]) (?=[a-záéíóúñ])/g, (_, before, w) => `${before} ${w.toLowerCase()} `);
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}

const MAX_CHARS = 52;
const TRAILING = new Set(['de', 'del', 'la', 'el', 'los', 'las', 'en', 'y', 'e', 'o', 'con', 'sin', 'para', 'por', 'a']);

// Nombre corto para las tarjetas. Primero las reglas conocidas; si no aplica
// ninguna se usa el nombre completo bien escrito, sin recortarlo con puntos
// suspensivos (en pantalla pasa a la línea de abajo). Solo un nombre muy largo se
// reduce, siempre cortando entre palabras y sin dejar nunca una palabra a medias.
export function shortExamName(name) {
  const full = (name || '').trim();
  if (!full) return 'Examen';
  for (const [pattern, short] of SHORT_NAMES) {
    if (pattern.test(full)) return short;
  }
  const core = full.replace(/\(.*?\)/g, ' ').split(/[,;:–—]/)[0].replace(/\s+/g, ' ').trim() || full;
  if (core.length <= MAX_CHARS) return formatExamName(core);
  let out = '';
  for (const w of core.split(' ')) {
    const next = out ? `${out} ${w}` : w;
    if (next.length > MAX_CHARS && out) break;
    out = next;
  }
  // Nunca terminar en "de", "y", "con"...: queda a medias.
  const parts = out.split(' ');
  while (parts.length > 1 && TRAILING.has(parts[parts.length - 1].toLowerCase())) parts.pop();
  return formatExamName(parts.join(' '));
}
