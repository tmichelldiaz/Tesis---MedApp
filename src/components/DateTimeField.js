import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Platform, Modal, Pressable,
} from 'react-native';
import { Calendar, Clock } from 'lucide-react-native';
import CalendarPicker from './CalendarPicker';
import TimePickerWeb from './TimePickerWeb';

// Este import solo existe de verdad en iOS/Android; en web el paquete no
// tiene una implementación nativa (ver DateTimePicker más abajo), por eso el
// picker propio (CalendarPicker/TimePickerWeb) es el que se usa ahí.
import DateTimePicker from '@react-native-community/datetimepicker';

const P = {
  navy: '#034AA6', g100: '#E2E8F0', g400: '#546080', g800: '#02204A', white: '#FFFFFF',
};

function formatDate(d) {
  return d.toLocaleDateString('es-CO', { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric' });
}

function formatTime(d) {
  return d.toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit', hour12: true });
}

// Selector de fecha ("mode='date'") u hora ("mode='time'"): siempre abre un
// picker visual (calendario / reloj con AM-PM), nunca pide escribir texto.
// - Android: diálogo nativo del sistema.
// - iOS: hoja modal con el picker nativo (calendario en grilla / spinner).
// - Web: el <input type="date"/"time"> del navegador se ve como texto plano
//   ("dd/mm/aaaa"), así que se usa un calendario y un reloj propios
//   (CalendarPicker/TimePickerWeb) dentro de la misma hoja modal.
export default function DateTimeField({ mode, value, onChange, placeholder }) {
  const [open, setOpen] = useState(false);
  const Icon = mode === 'date' ? Calendar : Clock;
  const label = value ? (mode === 'date' ? formatDate(value) : formatTime(value)) : placeholder;

  const field = (
    <TouchableOpacity style={s.field} onPress={() => setOpen(true)}>
      <Icon size={16} color={P.navy} />
      <Text style={[s.fieldText, !value && s.placeholder]} numberOfLines={1}>{label}</Text>
    </TouchableOpacity>
  );

  if (Platform.OS === 'web') {
    return (
      <>
        {field}
        <Modal visible={open} transparent animationType="fade" onRequestClose={() => setOpen(false)}>
          <Pressable style={s.overlay} onPress={() => setOpen(false)}>
            <Pressable style={s.webSheet}>
              {mode === 'date' ? (
                <CalendarPicker
                  value={value}
                  onSelect={(d) => { onChange(d); setOpen(false); }}
                />
              ) : (
                <>
                  <TimePickerWeb value={value} onSelect={onChange} />
                  <TouchableOpacity style={s.doneBtn} onPress={() => setOpen(false)}>
                    <Text style={s.doneText}>Listo</Text>
                  </TouchableOpacity>
                </>
              )}
            </Pressable>
          </Pressable>
        </Modal>
      </>
    );
  }

  const handleChange = (event, selected) => {
    if (Platform.OS === 'android') setOpen(false);
    if (event.type === 'dismissed') return;
    if (selected) onChange(selected);
  };

  return (
    <>
      {field}

      {open && Platform.OS === 'android' && (
        <DateTimePicker
          value={value || new Date()}
          mode={mode}
          is24Hour={false}
          display="default"
          onChange={handleChange}
        />
      )}

      {Platform.OS === 'ios' && (
        <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
          <Pressable style={s.overlay} onPress={() => setOpen(false)}>
            <Pressable style={s.sheet}>
              <DateTimePicker
                value={value || new Date()}
                mode={mode}
                is24Hour={false}
                locale="es-CO"
                display={mode === 'date' ? 'inline' : 'spinner'}
                onChange={handleChange}
              />
              <TouchableOpacity style={s.doneBtn} onPress={() => setOpen(false)}>
                <Text style={s.doneText}>Listo</Text>
              </TouchableOpacity>
            </Pressable>
          </Pressable>
        </Modal>
      )}
    </>
  );
}

const s = StyleSheet.create({
  field:      { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: P.g100, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10 },
  fieldText:  { fontSize: 13, color: P.g800, flexShrink: 1 },
  placeholder:{ color: P.g400 },
  overlay:    { flex: 1, backgroundColor: 'rgba(2,32,74,0.4)', alignItems: 'center', justifyContent: 'center' },
  sheet:      { backgroundColor: P.white, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, alignItems: 'center', position: 'absolute', bottom: 0, left: 0, right: 0 },
  webSheet:   { backgroundColor: P.white, borderRadius: 20, padding: 20, alignItems: 'center', shadowColor: '#1A2040', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.2, shadowRadius: 24, elevation: 8 },
  doneBtn:    { marginTop: 14, backgroundColor: P.navy, borderRadius: 12, paddingVertical: 10, paddingHorizontal: 24, alignSelf: 'stretch', alignItems: 'center' },
  doneText:   { color: 'white', fontWeight: '700', fontSize: 13 },
});
