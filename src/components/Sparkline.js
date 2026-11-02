import React, { useState } from 'react';
import { View } from 'react-native';
import Svg, { Path, Circle, Rect, Line, Defs, LinearGradient, Stop } from 'react-native-svg';
import { smoothPath, areaPath } from '../utils/smoothPath';

const NORMAL = '#2E8B57';

let instances = 0; // cada gráfica necesita su propio id de degradado

// Mini gráfica de las tarjetas del inicio. Siempre muestra algo útil según los
// datos que haya:
//  - 2 o más resultados: la línea de evolución (con la franja del rango normal).
//  - 1 resultado con rango de referencia: una barra con la zona normal y un
//    marcador donde cae el valor.
//  - 1 resultado sin rango: una línea punteada con un punto (sin tendencia aún).
//  - sin valor numérico (p. ej. "Negativa"): nada que dibujar.
export default function Sparkline({ values, low, high, color, height = 30 }) {
  const [width, setWidth] = useState(0);
  const [gradientId] = useState(() => `spark${++instances}`);
  const pts = (values || []).filter((v) => v != null && Number.isFinite(v));
  if (pts.length === 0) return <View style={{ height }} />;

  const pad = 4;
  const inner = Math.max(width - pad * 2, 1);
  const hasRange = low != null || high != null;

  let body = null;
  if (width > 0 && pts.length >= 2) {
    const all = hasRange ? [...pts, ...[low, high].filter((v) => v != null)] : pts;
    const min = Math.min(...all);
    const max = Math.max(...all);
    const span = max - min || 1;
    const x = (i) => pad + (i / (pts.length - 1)) * inner;
    const y = (v) => height - pad - ((v - min) / span) * (height - pad * 2);
    const coords = pts.map((v, i) => ({ x: x(i), y: y(v) }));
    const zoneTop = high != null ? y(high) : pad;
    const zoneBottom = low != null ? y(low) : height - pad;
    body = (
      <>
        {hasRange && (
          <Rect x={0} y={zoneTop} width={width} height={Math.max(zoneBottom - zoneTop, 2)} fill={NORMAL} opacity={0.12} rx={3} />
        )}
        <Defs>
          <LinearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color} stopOpacity={0.3} />
            <Stop offset="1" stopColor={color} stopOpacity={0.02} />
          </LinearGradient>
        </Defs>
        <Path d={areaPath(coords, height)} fill={`url(#${gradientId})`} />
        <Path d={smoothPath(coords)} fill="none" stroke={color} strokeWidth={2.4} strokeLinejoin="round" strokeLinecap="round" />
        <Circle cx={x(pts.length - 1)} cy={y(pts[pts.length - 1])} r={3.8} fill={color} stroke="#FFFFFF" strokeWidth={1.5} />
      </>
    );
  } else if (width > 0 && hasRange) {
    const v = pts[0];
    const lo = low != null ? low : 0;
    const hi = high != null ? high : Math.max(v, lo) * 1.6 || 1;
    const spanLow = Math.min(lo, v);
    const spanHigh = Math.max(hi, v);
    const margin = (spanHigh - spanLow || 1) * 0.15;
    const a = spanLow - margin;
    const b = spanHigh + margin;
    const pos = (n) => pad + ((n - a) / (b - a)) * inner;
    const mid = height / 2;
    const outside = (low != null && v < low) || (high != null && v > high);
    body = (
      <>
        <Rect x={pad} y={mid - 3} width={inner} height={6} rx={3} fill="#E2E8F0" />
        <Rect x={pos(lo)} y={mid - 3} width={Math.max(pos(hi) - pos(lo), 2)} height={6} rx={3} fill={NORMAL} opacity={0.45} />
        <Circle cx={pos(v)} cy={mid} r={6} fill="#FFFFFF" stroke={outside ? color : NORMAL} strokeWidth={3} />
      </>
    );
  } else if (width > 0) {
    const mid = height / 2;
    body = (
      <>
        <Line x1={pad} y1={mid} x2={width - pad} y2={mid} stroke="#CBD5E1" strokeWidth={2} strokeDasharray="4 4" strokeLinecap="round" />
        <Circle cx={width - pad - 4} cy={mid} r={4} fill={color} />
      </>
    );
  }

  return (
    <View style={{ height }} onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
      {width > 0 && (
        <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>{body}</Svg>
      )}
    </View>
  );
}
