import React, { useRef } from 'react';
import { View, Text, ScrollView, StyleSheet } from 'react-native';
import { withUnit } from '../utils/labValues';
import { smoothPath, areaPath } from '../utils/smoothPath';
import Svg, { Path, Circle, Rect, Line, Defs, LinearGradient, Stop, Text as SvgText } from 'react-native-svg';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  g100: '#E2E8F0', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

const BASE_W = 320;
const H = 200;
const PAD_X = 34;
const PAD_TOP = 34; // espacio arriba para los números, así la línea no pasa por encima de ellos
const PAD_BOTTOM = 30;
const GAP_BETWEEN_LABELS = 10;

function shortDate(iso) {
  if (!iso) return 's/f';
  const [y, m, d] = iso.split('-');
  return `${d}/${m}`;
}

const pillWidth = (text) => Math.max(text.length * 6 + 14, 30);

// Gráfica de la evolución de un examen: curva suave con el área rellena debajo y, sobre cada punto, su
// valor con la unidad (sobre un fondo blanco, para que ninguna línea lo tape). Con muchos puntos la gráfica
// se hace más ancha y se desliza hacia los lados, así todos los valores se leen completos.
export default function TrendChart({ points }) {
  const scroller = useRef(null);
  const withValue = points.filter((p) => p.value_numeric != null);

  if (withValue.length === 0) {
    return (
      <View style={s.empty}>
        <Text style={s.emptyText}>Este examen no tiene valores numéricos para graficar.</Text>
      </View>
    );
  }

  if (withValue.length === 1) {
    const only = withValue[0];
    return (
      <View style={s.empty}>
        <Text style={s.emptyBig}>{withUnit(only.value_raw, only.unit)}</Text>
        <Text style={s.emptyText}>Único valor registrado ({shortDate(only.date)}). Sube más historias para ver la tendencia.</Text>
      </View>
    );
  }

  const n = withValue.length;
  const labels = withValue.map((p) => withUnit(p.value_raw, p.unit));
  const widest = Math.max(...labels.map((t) => pillWidth(t)));

  // Ancho: el normal si todos los valores caben, o el necesario para que ninguno se monte sobre otro.
  const needed = PAD_X * 2 + (n - 1) * (widest + GAP_BETWEEN_LABELS);
  const W = Math.max(BASE_W, needed);
  const scrolls = W > BASE_W;

  const values = withValue.map((p) => p.value_numeric);
  const refLows = withValue.map((p) => p.reference_low).filter((v) => v != null);
  const refHighs = withValue.map((p) => p.reference_high).filter((v) => v != null);
  const allForRange = [...values, ...refLows, ...refHighs];
  const min = Math.min(...allForRange);
  const max = Math.max(...allForRange);
  const span = max - min || 1;

  const innerW = W - PAD_X * 2;
  const innerH = H - PAD_TOP - PAD_BOTTOM;
  const baseline = PAD_TOP + innerH;
  const x = (i) => PAD_X + (i / (n - 1)) * innerW;
  const y = (v) => PAD_TOP + innerH - ((v - min) / span) * innerH;

  const refLow = refLows.length ? Math.max(...refLows) : null;
  const refHigh = refHighs.length ? Math.min(...refHighs) : null;

  const coords = withValue.map((p, i) => ({ x: x(i), y: y(p.value_numeric) }));
  const last = withValue[n - 1];

  const chart = (
    <Svg width={scrolls ? W : '100%'} height={H} viewBox={`0 0 ${W} ${H}`}>
      <Defs>
        <LinearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={P.navy} stopOpacity={0.28} />
          <Stop offset="1" stopColor={P.navy} stopOpacity={0.02} />
        </LinearGradient>
      </Defs>

      {[0.25, 0.5, 0.75].map((f) => (
        <Line
          key={f}
          x1={PAD_X} x2={W - PAD_X} y1={PAD_TOP + innerH * f} y2={PAD_TOP + innerH * f}
          stroke={P.g100} strokeWidth={1} strokeDasharray="3 5"
        />
      ))}
      {refLow != null && refHigh != null && (
        <Rect
          x={PAD_X} y={y(refHigh)} width={innerW} height={Math.max(y(refLow) - y(refHigh), 1)}
          fill="#2E8B57" opacity={0.1} rx={6}
        />
      )}
      <Line x1={PAD_X} y1={baseline} x2={W - PAD_X} y2={baseline} stroke={P.g100} strokeWidth={1} />

      <Path d={areaPath(coords, baseline)} fill="url(#trendFill)" />
      <Path d={smoothPath(coords)} fill="none" stroke={P.navy} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />

      {withValue.map((p, i) => (
        <Circle
          key={i}
          cx={coords[i].x} cy={coords[i].y}
          r={i === n - 1 ? 6 : 4.5}
          fill={i === n - 1 ? P.accent : '#FFFFFF'}
          stroke={i === n - 1 ? '#FFFFFF' : P.navy}
          strokeWidth={2.5}
        />
      ))}

      {withValue.map((p, i) => {
        const text = labels[i];
        const pillW = pillWidth(text);
        const cx = Math.min(Math.max(coords[i].x, pillW / 2 + 2), W - pillW / 2 - 2);
        const top = Math.max(coords[i].y - 30, 2);
        const strong = i === n - 1;
        return (
          <React.Fragment key={`l${i}`}>
            <Rect
              x={cx - pillW / 2} y={top} width={pillW} height={18} rx={9}
              fill="#FFFFFF" stroke={strong ? P.accent : P.g100} strokeWidth={strong ? 1.5 : 1}
            />
            <SvgText x={cx} y={top + 12.5} fontSize={10} fontWeight="700" fill={P.g800} textAnchor="middle">
              {text}
            </SvgText>
          </React.Fragment>
        );
      })}

      {withValue.map((p, i) => (
        <SvgText key={`d${i}`} x={x(i)} y={H - 9} fontSize={9.5} fill={P.g400} textAnchor="middle">
          {shortDate(p.date)}
        </SvgText>
      ))}
    </Svg>
  );

  return (
    <View>
      {scrolls ? (
        <ScrollView
          ref={scroller}
          horizontal
          showsHorizontalScrollIndicator={false}
          onContentSizeChange={() => scroller.current?.scrollToEnd({ animated: false })}>
          {chart}
        </ScrollView>
      ) : chart}
      {scrolls && <Text style={s.refCaption}>Desliza hacia los lados para ver todos los valores</Text>}
      {refLow != null && refHigh != null && (
        <Text style={s.refCaption}>Franja verde: rango de referencia {refLow} – {refHigh} {last.unit || ''}</Text>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  empty:      { paddingVertical: 24, alignItems: 'center', gap: 6 },
  emptyBig:   { fontSize: 22, fontWeight: '900', color: P.g800 },
  emptyText:  { fontSize: 12, color: P.g400, textAlign: 'center', paddingHorizontal: 20 },
  refCaption: { fontSize: 10, color: P.g400, textAlign: 'center', marginTop: 2 },
});
