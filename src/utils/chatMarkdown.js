// Las tablas de Markdown no caben en un celular: las columnas quedan tan
// angostas que las palabras se parten letra por letra. Antes de dibujar la
// respuesta, cada tabla se convierte en una lista legible:
//
//   | Categoría | Qué quiere decir | Probabilidad |      **PI-RADS 4**
//   |-----------|------------------|--------------|  →   - Qué quiere decir: Hallazgo sospechoso
//   | PI-RADS 4 | Hallazgo ...     | Alta         |      - Probabilidad: Alta
//
// Con dos columnas queda una sola línea por fila ("**Término**: explicación").

const ROW = /^\s*\|.*\|\s*$/;
const SEPARATOR = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;

function cellsOf(line) {
  return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
}

const plain = (text) => text.replace(/\*\*/g, '').trim();

function tableToList(header, rows) {
  const out = [];
  if (header.length === 2) {
    for (const r of rows) {
      if (!r[0] && !r[1]) continue;
      out.push(`- **${plain(r[0] || '')}**: ${r[1] || ''}`.trimEnd());
    }
    return out;
  }
  for (const r of rows) {
    if (!r.some(Boolean)) continue;
    out.push('', `**${plain(r[0] || header[0] || '')}**`);
    for (let i = 1; i < header.length; i++) {
      if (r[i]) out.push(`- ${plain(header[i])}: ${r[i]}`);
    }
  }
  out.push('');
  return out;
}

export function prepareMarkdown(text) {
  if (!text || !text.includes('|')) return text;
  const lines = text.split('\n');
  const out = [];
  for (let i = 0; i < lines.length; i++) {
    if (ROW.test(lines[i]) && i + 1 < lines.length && SEPARATOR.test(lines[i + 1])) {
      const header = cellsOf(lines[i]);
      const rows = [];
      i += 2;
      while (i < lines.length && ROW.test(lines[i])) {
        rows.push(cellsOf(lines[i]));
        i++;
      }
      i--;
      out.push('', ...tableToList(header, rows));
    } else {
      out.push(lines[i]);
    }
  }
  return out.join('\n');
}
