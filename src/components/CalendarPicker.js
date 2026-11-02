import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { ChevronLeft, ChevronRight } from 'lucide-react-native';

const P = {
  navy: '#034AA6', g100: '#E2E8F0', g400: '#546080', g800: '#02204A',
  white: '#FFFFFF', bg: '#F4FAE9',
};

const MONTHS = [
  'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
];
const MONTHS_SHORT = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
const WEEKDAYS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']; // empieza en lunes
const YEARS_PER_PAGE = 12;
const MIN_YEAR = 1900;
const MAX_YEAR = new Date().getFullYear() + 10;

function daysInMonth(year, month) {
  return new Date(year, month + 1, 0).getDate();
}

function firstWeekdayMondayFirst(year, month) {
  const jsDay = new Date(year, month, 1).getDay(); // 0=domingo..6=sábado
  return (jsDay + 6) % 7; // 0=lunes..6=domingo
}

function isSameDay(a, b) {
  return !!a && !!b && a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

// Calendario propio (grilla de días) para usar como picker de fecha en web,
// donde el <input type="date"> nativo del navegador se ve como texto plano
// ("dd/mm/aaaa") en vez de un calendario visual como en el teléfono.
//
// Navegar mes a mes es carísimo para fechas lejanas (ej. fecha de nacimiento
// 30-40 años atrás), así que el encabezado es tocable: "Septiembre 2026" abre
// una grilla de años, y desde ahí una grilla de meses, antes de volver a los
// días — como los pickers nativos de iOS/Android en modo calendario.
export default function CalendarPicker({ value, onSelect }) {
  const initial = value || new Date();
  const [viewYear, setViewYear] = useState(initial.getFullYear());
  const [viewMonth, setViewMonth] = useState(initial.getMonth());
  const [mode, setMode] = useState('days'); // 'days' | 'months' | 'years'
  const [yearsPageStart, setYearsPageStart] = useState(
    initial.getFullYear() - (initial.getFullYear() % YEARS_PER_PAGE)
  );

  const today = new Date();

  if (mode === 'years') {
    const years = Array.from({ length: YEARS_PER_PAGE }, (_, i) => yearsPageStart + i);
    return (
      <View style={s.container}>
        <View style={s.header}>
          <TouchableOpacity
            onPress={() => setYearsPageStart((y) => Math.max(MIN_YEAR, y - YEARS_PER_PAGE))}
            style={s.navBtn}>
            <ChevronLeft size={18} color={P.navy} />
          </TouchableOpacity>
          <Text style={s.headerText}>{yearsPageStart} – {yearsPageStart + YEARS_PER_PAGE - 1}</Text>
          <TouchableOpacity
            onPress={() => setYearsPageStart((y) => Math.min(MAX_YEAR, y + YEARS_PER_PAGE))}
            style={s.navBtn}>
            <ChevronRight size={18} color={P.navy} />
          </TouchableOpacity>
        </View>
        <View style={s.grid3}>
          {years.map((y) => (
            <TouchableOpacity
              key={y}
              style={[s.gridItem, y === viewYear && s.gridItemSelected]}
              onPress={() => { setViewYear(y); setMode('months'); }}>
              <Text style={[s.gridItemText, y === viewYear && s.gridItemTextSelected]}>{y}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    );
  }

  if (mode === 'months') {
    return (
      <View style={s.container}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => setViewYear((y) => y - 1)} style={s.navBtn}>
            <ChevronLeft size={18} color={P.navy} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => { setYearsPageStart(viewYear - (viewYear % YEARS_PER_PAGE)); setMode('years'); }}>
            <Text style={s.headerText}>{viewYear}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setViewYear((y) => y + 1)} style={s.navBtn}>
            <ChevronRight size={18} color={P.navy} />
          </TouchableOpacity>
        </View>
        <View style={s.grid3}>
          {MONTHS_SHORT.map((m, i) => (
            <TouchableOpacity
              key={m}
              style={[s.gridItem, i === viewMonth && s.gridItemSelected]}
              onPress={() => { setViewMonth(i); setMode('days'); }}>
              <Text style={[s.gridItemText, i === viewMonth && s.gridItemTextSelected]}>{m}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    );
  }

  const totalDays = daysInMonth(viewYear, viewMonth);
  const leadingBlanks = firstWeekdayMondayFirst(viewYear, viewMonth);
  const cells = [...Array(leadingBlanks).fill(null), ...Array.from({ length: totalDays }, (_, i) => i + 1)];

  const goPrevMonth = () => {
    if (viewMonth === 0) { setViewMonth(11); setViewYear((y) => y - 1); }
    else setViewMonth((m) => m - 1);
  };
  const goNextMonth = () => {
    if (viewMonth === 11) { setViewMonth(0); setViewYear((y) => y + 1); }
    else setViewMonth((m) => m + 1);
  };

  return (
    <View style={s.container}>
      <View style={s.header}>
        <TouchableOpacity onPress={goPrevMonth} style={s.navBtn}>
          <ChevronLeft size={18} color={P.navy} />
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setMode('months')}>
          <Text style={s.headerText}>{MONTHS[viewMonth]} {viewYear}</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={goNextMonth} style={s.navBtn}>
          <ChevronRight size={18} color={P.navy} />
        </TouchableOpacity>
      </View>

      <View style={s.weekRow}>
        {WEEKDAYS.map((w, i) => (
          <Text key={i} style={s.weekLabel}>{w}</Text>
        ))}
      </View>

      <View style={s.grid}>
        {cells.map((day, i) => {
          if (day == null) return <View key={i} style={s.cell} />;
          const cellDate = new Date(viewYear, viewMonth, day);
          const selected = isSameDay(cellDate, value);
          const isToday = !selected && isSameDay(cellDate, today);
          return (
            <TouchableOpacity key={i} style={s.cell} onPress={() => onSelect(cellDate)}>
              <View style={[s.dayCircle, selected && s.dayCircleSelected, isToday && s.dayCircleToday]}>
                <Text style={[s.dayText, selected && s.dayTextSelected]}>{day}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container:   { width: 280 },
  header:      { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  navBtn:      { width: 30, height: 30, borderRadius: 10, backgroundColor: P.bg, alignItems: 'center', justifyContent: 'center' },
  headerText:  { fontSize: 14, fontWeight: '700', color: P.navy, paddingHorizontal: 4 },
  weekRow:     { flexDirection: 'row' },
  weekLabel:   { flexBasis: '14.2857%', textAlign: 'center', fontSize: 11, fontWeight: '700', color: P.g400, marginBottom: 4 },
  grid:        { flexDirection: 'row', flexWrap: 'wrap' },
  cell:        { flexBasis: '14.2857%', alignItems: 'center', justifyContent: 'center', paddingVertical: 3 },
  dayCircle:   { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  dayCircleSelected: { backgroundColor: P.navy },
  dayCircleToday:    { borderWidth: 1, borderColor: P.navy },
  dayText:     { fontSize: 12, color: P.g800 },
  dayTextSelected: { color: 'white', fontWeight: '700' },
  grid3:       { flexDirection: 'row', flexWrap: 'wrap' },
  gridItem:    { flexBasis: '33.333%', paddingVertical: 12, alignItems: 'center', justifyContent: 'center', borderRadius: 12 },
  gridItemSelected: { backgroundColor: P.navy },
  gridItemText:{ fontSize: 13, fontWeight: '600', color: P.g800 },
  gridItemTextSelected: { color: 'white' },
});
