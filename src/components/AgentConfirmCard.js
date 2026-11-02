import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { Check, X, Pencil, ShieldAlert } from 'lucide-react-native';
import { formatQuestion } from '../utils/examNames';

const P = {
  navy: '#034AA6', g100: '#E2E8F0', g200: '#94A3B8', g400: '#546080',
  g800: '#02204A', white: '#FFFFFF', accent: '#F29BB2', bg: '#F4FAE9',
};

const ARG_LABELS = {
  title: 'Título', scheduled_at: 'Fecha y hora', doctor_name: 'Médico',
  location: 'Lugar', notes: 'Notas', text: 'Pregunta', appointment_id: 'Cita vinculada',
};

const TOOL_COPY = {
  create_appointment: {
    title: 'Confirmar nueva cita',
    summary: '¿Agendo esta cita por ti?',
  },
  save_question_for_doctor: {
    title: 'Confirmar pregunta',
    summary: '¿Guardo esta pregunta para tu médico?',
  },
};

function formatDate(value) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('es-CO', {
    weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// Tarjeta de confirmación humana antes de que el agente ejecute una acción
// que escribe datos (crear cita, guardar una pregunta). No se persiste como
// mensaje del chat: es un paso intermedio, la respuesta final del agente
// (aprobada, editada o rechazada) es la que queda en la conversación.
export default function AgentConfirmCard({ action, busy, onApprove, onReject, onEdit }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(action.args);

  const copy = TOOL_COPY[action.tool] || { title: 'Confirmar acción', summary: `¿Confirmas: ${action.tool}?` };
  const entries = Object.entries(editing ? draft : action.args).filter(([, v]) => v !== null && v !== '');

  const startEdit = () => { setDraft(action.args); setEditing(true); };
  const submitEdit = () => onEdit(draft);

  return (
    <View style={s.card}>
      <View style={s.header}>
        <ShieldAlert size={16} color={P.navy} />
        <Text style={s.title}>{copy.title}</Text>
      </View>
      <Text style={s.summary}>{copy.summary}</Text>

      <View style={s.fields}>
        {entries.map(([key, value]) => (
          <View key={key} style={editing ? s.fieldCol : s.fieldRow}>
            <Text style={s.fieldLabel}>{ARG_LABELS[key] || key}</Text>
            {editing ? (
              <TextInput
                style={s.fieldInput}
                value={String(draft[key] ?? '')}
                multiline={key === 'text' || key === 'title' || key === 'notes'}
                onChangeText={(v) => setDraft((d) => ({ ...d, [key]: v }))}
              />
            ) : (
              <Text style={s.fieldValue}>
                {key === 'scheduled_at' ? formatDate(value) : key === 'text' ? formatQuestion(String(value)) : String(value)}
              </Text>
            )}
          </View>
        ))}
      </View>

      {busy ? (
        <ActivityIndicator color={P.navy} style={{ marginTop: 10 }} />
      ) : editing ? (
        <View style={s.actionsRow}>
          <TouchableOpacity style={s.secondaryBtn} onPress={() => setEditing(false)}>
            <Text style={s.secondaryText}>Cancelar</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.approveBtn} onPress={submitEdit}>
            <Check size={15} color="white" />
            <Text style={s.approveText}>Confirmar cambios</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={s.actionsRow}>
          <TouchableOpacity style={s.rejectBtn} onPress={onReject}>
            <X size={15} color="#9B1C1C" />
            <Text style={s.rejectText}>No</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.editBtn} onPress={startEdit}>
            <Pencil size={15} color={P.navy} />
            <Text style={s.editText}>Editar</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.approveBtn} onPress={onApprove}>
            <Check size={15} color="white" />
            <Text style={s.approveText}>Sí, hazlo</Text>
          </TouchableOpacity>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  card:       { backgroundColor: P.white, borderRadius: 18, borderWidth: 1, borderColor: P.light, padding: 16, gap: 12, alignSelf: 'stretch', width: '100%', shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 10, elevation: 2 },
  header:     { flexDirection: 'row', alignItems: 'center', gap: 6 },
  title:      { fontSize: 15, fontWeight: '700', color: P.g800 },
  summary:    { fontSize: 13, color: P.g400 },
  fields:     { gap: 10 },
  fieldRow:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 },
  fieldCol:   { gap: 4 },
  fieldLabel: { fontSize: 12, color: P.g400, minWidth: 78 },
  fieldValue: { fontSize: 14, lineHeight: 20, color: P.g800, fontWeight: '600', flex: 1, flexShrink: 1, textAlign: 'right' },
  fieldInput: { borderWidth: 1, borderColor: P.g100, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8, fontSize: 14, color: P.g800, textAlignVertical: 'top' },
  actionsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 },
  rejectBtn:  { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 14, backgroundColor: '#FDE2E2' },
  rejectText: { fontSize: 14, fontWeight: '700', color: '#9B1C1C' },
  editBtn:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 14, backgroundColor: P.bg },
  editText:   { fontSize: 14, fontWeight: '700', color: P.navy },
  approveBtn: { flex: 1, minWidth: 110, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 14, backgroundColor: P.navy },
  approveText:{ fontSize: 14, fontWeight: '700', color: 'white' },
  secondaryBtn:{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 12, paddingHorizontal: 16, borderRadius: 14, backgroundColor: P.bg },
  secondaryText:{ fontSize: 14, fontWeight: '700', color: P.g400 },
});
