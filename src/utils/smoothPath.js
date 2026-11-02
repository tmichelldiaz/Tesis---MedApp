// Curva suave que pasa por todos los puntos sin "rebotar" más allá de ellos (interpolación monótona
// de Fritsch-Carlson): una subida sigue siendo subida, así que la línea nunca inventa picos ni valles.
// Los puntos van de izquierda a derecha, en coordenadas de pantalla: [{ x, y }, ...].

const f = (n) => Number(n.toFixed(2));

export function smoothPath(points) {
  const n = points.length;
  if (n === 0) return '';
  if (n === 1) return `M${f(points[0].x)},${f(points[0].y)}`;

  const dx = [];
  const slope = [];
  for (let i = 0; i < n - 1; i++) {
    dx.push(points[i + 1].x - points[i].x || 1);
    slope.push((points[i + 1].y - points[i].y) / dx[i]);
  }

  const tangent = new Array(n);
  tangent[0] = slope[0];
  tangent[n - 1] = slope[n - 2];
  for (let i = 1; i < n - 1; i++) {
    tangent[i] = slope[i - 1] * slope[i] <= 0 ? 0 : (slope[i - 1] + slope[i]) / 2;
  }
  for (let i = 0; i < n - 1; i++) {
    if (slope[i] === 0) {
      tangent[i] = 0;
      tangent[i + 1] = 0;
      continue;
    }
    const a = tangent[i] / slope[i];
    const b = tangent[i + 1] / slope[i];
    const sum = a * a + b * b;
    if (sum > 9) {
      const tau = 3 / Math.sqrt(sum);
      tangent[i] = tau * a * slope[i];
      tangent[i + 1] = tau * b * slope[i];
    }
  }

  let d = `M${f(points[0].x)},${f(points[0].y)}`;
  for (let i = 0; i < n - 1; i++) {
    const third = dx[i] / 3;
    const c1x = points[i].x + third;
    const c1y = points[i].y + tangent[i] * third;
    const c2x = points[i + 1].x - third;
    const c2y = points[i + 1].y - tangent[i + 1] * third;
    d += ` C${f(c1x)},${f(c1y)} ${f(c2x)},${f(c2y)} ${f(points[i + 1].x)},${f(points[i + 1].y)}`;
  }
  return d;
}

// La misma curva cerrada hacia abajo, para rellenar el área bajo la línea.
export function areaPath(points, bottom) {
  if (points.length < 2) return '';
  const first = points[0];
  const last = points[points.length - 1];
  return `${smoothPath(points)} L${f(last.x)},${f(bottom)} L${f(first.x)},${f(bottom)} Z`;
}
