import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';

const P = {
  navy: '#034AA6', g100: '#E2E8F0', g200: '#94A3B8', g800: '#02204A', white: '#FFFFFF', bg: '#F4FAE9',
};

const HOURS = Array.from({ length: 12 }, (_, i) => i + 1); // 1..12
const MINUTES = Array.from({ length: 12 }, (_, i) => i * 5); // 00, 05, ..., 55

function to12Hour(date) {
  const h24 = date.getHours();
  const period = h24 >= 12 ? 'PM' : 'AM';
  let hour = h24 % 12;
  if (hour === 0) hour = 12;
  return { hour, minute: date.getMinutes(), period };
}

const pad2 = (n) => String(n).padStart(2, '0');

// Selector de hora tipo reloj para web (columnas de hora / minuto + AM-PM),
// paralelo al DateTimePicker nativo que ya se usa en iOS/Android.
export default function TimePickerWeb({ value, onSelect }) {
  const base = value || new Date();
  const { hour, minute, period } = to12Hour(base);
  const closestMinute = MINUTES.reduce(
    (a, b) => (Math.abs(b - minute) < Math.abs(a - minute) ? b : a), 0
  );

  const apply = (h, m, p) => {
    const next = new Date(base);
    let h24 = h % 12;
    if (p === 'PM') h24 += 12;
    next.setHours(h24, m, 0, 0);
    onSelect(next);
  };

  return (
    <View style={s.container}>
      <Text style={s.currentLabel}>{pad2(hour)}:{pad2(minute)} {period}</Text>
      <View style={s.columns}>
        <ScrollView style={s.column} showsVerticalScrollIndicator={false}>
          {HOURS.map((h) => (
            <TouchableOpacity
              key={h}
              style={[s.item, h === hour && s.itemSelected]}
              onPress={() => apply(h, minute, period)}>
              <Text style={[s.itemText, h === hour && s.itemTextSelected]}>{pad2(h)}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <ScrollView style={s.column} showsVerticalScrollIndicator={false}>
          {MINUTES.map((m) => (
            <TouchableOpacity
              key={m}
              style={[s.item, m === closestMinute && s.itemSelected]}
              onPress={() => apply(hour, m, period)}>
              <Text style={[s.itemText, m === closestMinute && s.itemTextSelected]}>{pad2(m)}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <View style={s.periodColumn}>
          {['AM', 'PM'].map((p) => (
            <TouchableOpacity
              key={p}
              style={[s.periodBtn, p === period && s.periodBtnSelected]}
              onPress={() => apply(hour, minute, p)}>
              <Text style={[s.periodText, p === period && s.periodTextSelected]}>{p}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  container:   { width: 220, alignItems: 'center' },
  currentLabel:{ fontSize: 16, fontWeight: '700', color: P.g800, marginBottom: 10 },
  columns:     { flexDirection: 'row', gap: 8, height: 160 },
  column:      { width: 60, backgroundColor: P.bg, borderRadius: 12 },
  item:        { paddingVertical: 8, alignItems: 'center' },
  itemSelected:{ backgroundColor: P.navy, borderRadius: 8 },
  itemText:    { fontSize: 13, color: P.g800 },
  itemTextSelected: { color: 'white', fontWeight: '700' },
  periodColumn:{ width: 50, justifyContent: 'center', gap: 8 },
  periodBtn:   { paddingVertical: 10, borderRadius: 10, backgroundColor: P.bg, alignItems: 'center' },
  periodBtnSelected: { backgroundColor: P.navy },
  periodText:  { fontSize: 12, fontWeight: '700', color: P.g800 },
  periodTextSelected:{ color: 'white' },
});
