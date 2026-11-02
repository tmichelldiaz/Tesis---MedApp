// Registro de los elementos de la app que el recorrido guiado puede señalar.
// Cada pantalla marca un elemento con `tourRef('clave')`; el recorrido le pregunta dónde está en la pantalla.

const targets = {};

// Ref con función: guarda el elemento al montarse y lo olvida al desmontarse.
export const tourRef = (key) => (node) => {
  if (node) targets[key] = node;
  else delete targets[key];
};

// Posición del elemento en la ventana ({x, y, w, h}) o null si no está en pantalla.
export function measureTarget(key) {
  return new Promise((resolve) => {
    const node = targets[key];
    if (!node || typeof node.measureInWindow !== 'function') return resolve(null);
    try {
      node.measureInWindow((x, y, w, h) => {
        if (!w || !h || Number.isNaN(x) || Number.isNaN(y)) resolve(null);
        else resolve({ x, y, w, h });
      });
    } catch (e) {
      resolve(null);
    }
  });
}
