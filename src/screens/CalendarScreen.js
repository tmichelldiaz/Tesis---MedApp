import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StyleSheet, SafeAreaView, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import KeyboardAwareScroll from '../components/KeyboardAwareScroll';
import {
  Plus, Trash2, Check, ChevronDown, ChevronUp, MapPin, Stethoscope,
  CalendarClock, MessageCircleQuestion, Pencil,
} from 'lucide-react-native';
import { useFocusEffect } from '@react-navigation/native';
import {
  listAppointments, createAppointment, updateAppointment, deleteAppointment,
  addQuestion, updateQuestion, deleteQuestion,
} from '../services/api';
import DateTimeField from '../components/DateTimeField';
import { confirmAction } from '../utils/confirm';
import { nextAppointment } from '../components/NextAppointmentCard';
import { assignSoftColors } from '../utils/examIcons';
import { DeviceSyncBanner } from '../components/DeviceSyncPrompt';
import { formatQuestion } from '../utils/examNames';
import { syncAppointments } from '../services/deviceSync';
import { useAuth } from '../context/AuthContext';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g200: '#94A3B8', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

const MONTHS = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];

function parts(scheduledAt) {
  const d = new Date(scheduledAt);
  if (Number.isNaN(d.getTime())) return { month: '--', day: '--', time: '--:--' };
  return {
    month: MONTHS[d.getMonth()],
    day: String(d.getDate()).padStart(2, '0'),
    time: d.toTimeString().slice(0, 5),
  };
}

// Combina la fecha y la hora elegidas en el picker nativo en un ISO 8601 con
// offset, para que el backend guarde la hora que el usuario realmente escogió.
function toIso(datePart, timePart) {
  const pad2 = (n) => String(n).padStart(2, '0');
  const combined = new Date(datePart);
  combined.setHours(timePart.getHours(), timePart.getMinutes(), 0, 0);
  const offsetMin = -combined.getTimezoneOffset();
  const sign = offsetMin >= 0 ? '+' : '-';
  const abs = Math.abs(offsetMin);
  const offset = `${sign}${pad2(Math.floor(abs / 60))}:${pad2(abs % 60)}`;
  return (
    `${combined.getFullYear()}-${pad2(combined.getMonth() + 1)}-${pad2(combined.getDate())}` +
    `T${pad2(combined.getHours())}:${pad2(combined.getMinutes())}:00${offset}`
  );
}

export default function CalendarScreen() {
  const { user } = useAuth();
  const [appointments, setAppointments] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState(null); // id de la cita que se está editando; null = cita nueva
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    title: '', date: null, time: null, doctor_name: '', location: '', notes: '',
  });
  const [questionDrafts, setQuestionDrafts] = useState({});

  const load = useCallback(() => {
    return listAppointments()
      .then(setAppointments)
      .catch((e) => setError(e.message));
  }, []);

  useFocusEffect(useCallback(() => {
    let active = true;
    setError(null);
    listAppointments()
      .then((rows) => active && setAppointments(rows))
      .catch((e) => active && setError(e.message));
    return () => { active = false; };
  }, []));

  const EMPTY_FORM = { title: '', date: null, time: null, doctor_name: '', location: '', notes: '' };

  const closeForm = () => {
    setForm(EMPTY_FORM);
    setEditingId(null);
    setShowForm(false);
  };

  // Abre el mismo formulario con los datos de la cita para cambiarlos.
  const startEdit = (a) => {
    const when = new Date(a.scheduled_at);
    setError(null);
    setForm({
      title: a.title || '',
      date: Number.isNaN(when.getTime()) ? null : when,
      time: Number.isNaN(when.getTime()) ? null : when,
      doctor_name: a.doctor_name || '',
      location: a.location || '',
      notes: a.notes || '',
    });
    setEditingId(a.id);
    setShowForm(true);
    setExpanded(null);
  };

  const submit = async () => {
    setError(null);
    if (!form.title.trim()) return setError('Ponle un nombre a la cita.');
    if (!form.date || !form.time) return setError('Elige la fecha y la hora de la cita.');
    setSaving(true);
    try {
      const body = {
        title: form.title.trim(),
        scheduled_at: toIso(form.date, form.time),
        doctor_name: form.doctor_name.trim() || null,
        location: form.location.trim() || null,
        notes: form.notes.trim() || null,
      };
      if (editingId) await updateAppointment(editingId, body);
      else await createAppointment(body);
      closeForm();
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id, title) => {
    const ok = await confirmAction('¿Eliminar esta cita?', `Se borrará "${title || 'la cita'}" y sus preguntas. No se puede deshacer.`);
    if (!ok) return;
    try {
      await deleteAppointment(id);
      setAppointments((prev) => prev.filter((a) => a.id !== id));
    } catch (e) {
      setError(e.message);
    }
  };

  const submitQuestion = async (appointmentId) => {
    const text = (questionDrafts[appointmentId] || '').trim();
    if (!text) return;
    try {
      const question = await addQuestion(text, appointmentId);
      setQuestionDrafts((prev) => ({ ...prev, [appointmentId]: '' }));
      setAppointments((prev) => prev.map((a) =>
        a.id === appointmentId ? { ...a, questions: [...a.questions, question] } : a
      ));
    } catch (e) {
      setError(e.message);
    }
  };

  const toggleAnswered = async (appointmentId, question) => {
    try {
      const updated = await updateQuestion(question.id, { answered: !question.answered });
      setAppointments((prev) => prev.map((a) =>
        a.id === appointmentId
          ? { ...a, questions: a.questions.map((q) => (q.id === question.id ? updated : q)) }
          : a
      ));
    } catch (e) {
      setError(e.message);
    }
  };

  const removeQuestion = async (appointmentId, questionId) => {
    try {
      await deleteQuestion(questionId);
      setAppointments((prev) => prev.map((a) =>
        a.id === appointmentId
          ? { ...a, questions: a.questions.filter((q) => q.id !== questionId) }
          : a
      ));
    } catch (e) {
      setError(e.message);
    }
  };

  // Mantiene al día el calendario del teléfono y los recordatorios con cada cambio.
  useEffect(() => {
    if (appointments) syncAppointments(user?.id, appointments);
  }, [appointments, user?.id]);

  // Próxima = la primera que todavía no pasó (no simplemente la más antigua).
  const next = nextAppointment(appointments);
  // Cada cita tiene su color; mismo reparto que en el inicio.
  const tones = assignSoftColors((appointments || []).map((a) => a.id));
  const isPast = (a) => {
    const t = new Date(a.scheduled_at).getTime();
    return !Number.isNaN(t) && t < Date.now() - 60 * 60 * 1000;
  };
  // Primero las que vienen, luego las pasadas.
  const ordered = [...(appointments || [])].sort(
    (a, b) => Number(isPast(a)) - Number(isPast(b)) || new Date(a.scheduled_at) - new Date(b.scheduled_at)
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: P.white }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding">
        <KeyboardAwareScroll style={{ flex: 1, backgroundColor: P.bg }} showsVerticalScrollIndicator={false}>

          <View style={s.header}>
            <View>
              <Text style={s.headerTitle}>Mis Citas</Text>
              <Text style={s.headerSub}>
                {appointments === null
                  ? 'Cargando...'
                  : appointments.length === 0
                  ? 'Sin citas agendadas'
                  : `${appointments.length} cita(s) agendada(s)`}
              </Text>
            </View>
            <TouchableOpacity style={s.addBtn} onPress={() => (showForm ? closeForm() : setShowForm(true))}>
              <Plus size={20} color="white" />
            </TouchableOpacity>
          </View>

          <View style={{ padding: 16, gap: 14 }}>

            {error && (
              <View style={s.errorBox}>
                <Text style={s.errorText}>{error}</Text>
              </View>
            )}

            {showForm && (
              <View style={s.card}>
                <Text style={s.cardTitle}>{editingId ? 'Editar cita' : 'Nueva cita'}</Text>
                <TextInput
                  style={s.input}
                  placeholder="¿Con quién o para qué? (ej. Control cardiología)"
                  placeholderTextColor={P.g400}
                  value={form.title}
                  onChangeText={(v) => setForm((f) => ({ ...f, title: v }))}
                />
                <View style={{ flexDirection: 'row', gap: 8 }}>
                  <DateTimeField
                    mode="date"
                    placeholder="Elige fecha"
                    value={form.date}
                    onChange={(d) => setForm((f) => ({ ...f, date: d }))}
                  />
                  <DateTimeField
                    mode="time"
                    placeholder="Elige hora"
                    value={form.time}
                    onChange={(d) => setForm((f) => ({ ...f, time: d }))}
                  />
                </View>
                <TextInput
                  style={s.input}
                  placeholder="Médico (opcional)"
                  placeholderTextColor={P.g400}
                  value={form.doctor_name}
                  onChangeText={(v) => setForm((f) => ({ ...f, doctor_name: v }))}
                />
                <TextInput
                  style={s.input}
                  placeholder="Lugar (opcional)"
                  placeholderTextColor={P.g400}
                  value={form.location}
                  onChangeText={(v) => setForm((f) => ({ ...f, location: v }))}
                />
                <TextInput
                  style={[s.input, { height: 70, textAlignVertical: 'top' }]}
                  placeholder="Notas (opcional)"
                  placeholderTextColor={P.g400}
                  value={form.notes}
                  onChangeText={(v) => setForm((f) => ({ ...f, notes: v }))}
                  multiline
                />
                <TouchableOpacity style={s.submitBtn} onPress={submit} disabled={saving}>
                  {saving
                    ? <ActivityIndicator color="white" />
                    : <Text style={s.submitBtnText}>{editingId ? 'Guardar cambios' : 'Agendar'}</Text>}
                </TouchableOpacity>
                {editingId && (
                  <TouchableOpacity style={s.cancelEditBtn} onPress={closeForm} disabled={saving}>
                    <Text style={s.cancelEditText}>Cancelar</Text>
                  </TouchableOpacity>
                )}
              </View>
            )}

            {appointments === null && (
              <ActivityIndicator color={P.navy} style={{ marginTop: 20 }} />
            )}

            {appointments?.length === 0 && !showForm && (
              <View style={s.emptyBox}>
                <CalendarClock size={32} color={P.navy} />
                <Text style={s.emptyTitle}>No tienes citas agendadas</Text>
                <Text style={s.emptySub}>
                  Agenda tu próxima cita y anota las preguntas que quieres hacerle a tu médico.
                </Text>
                <TouchableOpacity style={s.emptyBtn} onPress={() => setShowForm(true)}>
                  <Text style={s.emptyBtnText}>Agendar cita</Text>
                </TouchableOpacity>
              </View>
            )}

            <DeviceSyncBanner appointments={appointments} />

            {next && (
              <View>
                <Text style={s.sectionTitle}>Próxima Cita</Text>
                <View style={s.apptRow}>
                  <View style={[s.dateBox, { backgroundColor: tones[next.id].bg }]}>
                    <Text style={[s.dateMonth, { color: tones[next.id].fg }]}>{parts(next.scheduled_at).month}</Text>
                    <Text style={[s.dateDay, { color: tones[next.id].fg }]}>{parts(next.scheduled_at).day}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={s.apptName}>{next.title}</Text>
                    {next.doctor_name && <Text style={s.apptDoc}>{next.doctor_name}</Text>}
                  </View>
                  <Text style={s.apptTime}>{parts(next.scheduled_at).time}</Text>
                </View>
              </View>
            )}

            {appointments?.length > 0 && (
              <View>
                <Text style={s.sectionTitle}>Todas tus Citas</Text>
                <View style={{ gap: 10 }}>
                  {ordered.map((a) => {
                    const isOpen = expanded === a.id;
                    const tone = tones[a.id];
                    const past = isPast(a);
                    const pending = a.questions.filter((q) => !q.answered).length;
                    return (
                      <View key={a.id} style={[s.listCard, past && { opacity: 0.65 }]}>
                        <TouchableOpacity
                          style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}
                          onPress={() => setExpanded(isOpen ? null : a.id)}>
                          <View style={[s.dateBoxSm, { backgroundColor: tone.bg }]}>
                            <Text style={[s.dateMonthSm, { color: tone.fg }]}>{parts(a.scheduled_at).month}</Text>
                            <Text style={[s.dateDaySm, { color: tone.fg }]}>{parts(a.scheduled_at).day}</Text>
                          </View>
                          <View style={{ flex: 1, minWidth: 0 }}>
                            <Text style={s.apptName} numberOfLines={1}>{a.title}</Text>
                            <View style={s.metaRow}>
                              {a.doctor_name && (
                                <View style={s.metaItem}>
                                  <Stethoscope size={13} color={tone.fg} />
                                  <Text style={s.metaText} numberOfLines={1}>{a.doctor_name}</Text>
                                </View>
                              )}
                              {a.location && (
                                <View style={s.metaItem}>
                                  <MapPin size={13} color={tone.fg} />
                                  <Text style={s.metaText} numberOfLines={1}>{a.location}</Text>
                                </View>
                              )}
                            </View>
                          </View>
                          <Text style={[s.apptTime, { color: tone.fg }]}>{parts(a.scheduled_at).time}</Text>
                          {isOpen ? <ChevronUp size={20} color={P.g400} /> : <ChevronDown size={20} color={P.g400} />}
                        </TouchableOpacity>

                        {isOpen && (
                          <View style={s.expandedArea}>
                            {a.notes && <Text style={s.notesText}>{a.notes}</Text>}

                            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: a.notes ? 10 : 0 }}>
                              <MessageCircleQuestion size={14} color={P.navy} />
                              <Text style={s.questionsTitle}>
                                Preguntas para el médico{pending > 0 ? ` · ${pending} ${pending === 1 ? 'pendiente' : 'pendientes'}` : ''}
                              </Text>
                            </View>

                            {a.questions.map((q) => (
                              <View key={q.id} style={s.questionRow}>
                                <TouchableOpacity
                                  style={[s.checkbox, q.answered && s.checkboxChecked]}
                                  onPress={() => toggleAnswered(a.id, q)}>
                                  {q.answered && <Check size={12} color="white" />}
                                </TouchableOpacity>
                                <Text style={[s.questionText, q.answered && s.questionTextDone]}>
                                  {formatQuestion(q.text)}
                                </Text>
                                <TouchableOpacity onPress={() => removeQuestion(a.id, q.id)}>
                                  <Trash2 size={14} color={P.g400} />
                                </TouchableOpacity>
                              </View>
                            ))}

                            <View style={s.addQuestionRow}>
                              <TextInput
                                style={s.addQuestionInput}
                                placeholder="Escribe una pregunta..."
                                placeholderTextColor={P.g400}
                                value={questionDrafts[a.id] || ''}
                                onChangeText={(v) => setQuestionDrafts((prev) => ({ ...prev, [a.id]: v }))}
                                onSubmitEditing={() => submitQuestion(a.id)}
                              />
                              <TouchableOpacity onPress={() => submitQuestion(a.id)}>
                                <Plus size={18} color={P.navy} />
                              </TouchableOpacity>
                            </View>

                            <View style={s.manageRow}>
                              <TouchableOpacity style={s.editBtn} onPress={() => startEdit(a)}>
                                <Pencil size={14} color={P.navy} />
                                <Text style={s.editBtnText}>Editar cita</Text>
                              </TouchableOpacity>
                              <TouchableOpacity style={s.deleteBtn} onPress={() => remove(a.id, a.title)}>
                                <Trash2 size={13} color="#9B1C1C" />
                                <Text style={s.deleteBtnText}>Eliminar cita</Text>
                              </TouchableOpacity>
                            </View>
                          </View>
                        )}
                      </View>
                    );
                  })}
                </View>
              </View>
            )}
          </View>
        </KeyboardAwareScroll>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header:        { padding: 20, paddingTop: 44, paddingBottom: 20, backgroundColor: P.navy, borderBottomLeftRadius: 28, borderBottomRightRadius: 28, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headerTitle:   { fontWeight: '700', fontSize: 20, color: 'white' },
  headerSub:     { fontSize: 12, color: 'rgba(255,255,255,0.65)', marginTop: 2 },
  addBtn:        { width: 38, height: 38, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' },
  card:          { borderRadius: 20, padding: 18, gap: 10, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 12, elevation: 2 },
  cardTitle:     { fontSize: 15, fontWeight: '700', color: P.g800, marginBottom: 4 },
  input:         { borderWidth: 1, borderColor: P.g100, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, color: P.g800 },
  submitBtn:     { marginTop: 4, paddingVertical: 12, borderRadius: 12, backgroundColor: P.navy, alignItems: 'center' },
  submitBtnText: { color: 'white', fontWeight: '700', fontSize: 13 },
  sectionTitle:  { fontSize: 17, fontWeight: '700', color: P.g800, marginBottom: 12 },
  apptRow:       { padding: 20, borderRadius: 22, flexDirection: 'row', alignItems: 'center', gap: 16, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2 },
  dateBox:       { width: 66, height: 66, borderRadius: 20, backgroundColor: P.light, alignItems: 'center', justifyContent: 'center' },
  dateMonth:     { fontSize: 11, letterSpacing: 0.5, fontWeight: '700', color: P.navy },
  dateDay:       { fontSize: 24, fontWeight: '700', color: P.navy },
  dateBoxSm:     { width: 58, height: 58, borderRadius: 18, backgroundColor: P.light, alignItems: 'center', justifyContent: 'center' },
  dateMonthSm:   { fontSize: 10, letterSpacing: 0.5, fontWeight: '700', color: P.navy },
  dateDaySm:     { fontSize: 21, fontWeight: '700', color: P.navy },
  apptName:      { fontWeight: '700', color: P.g800, fontSize: 16 },
  apptDoc:       { fontSize: 14, marginTop: 2, fontStyle: 'italic', color: P.g400 },
  apptTime:      { fontSize: 15, fontWeight: '700', color: P.g800 },
  metaRow:       { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 6 },
  metaItem:      { flexDirection: 'row', alignItems: 'center', gap: 5, flexShrink: 1, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 999, backgroundColor: '#F1F5FB' },
  metaText:      { flexShrink: 1, fontSize: 12, fontWeight: '600', color: P.g800 },
  listCard:      { padding: 18, borderRadius: 22, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2 },
  expandedArea:  { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: P.g100, gap: 6 },
  notesText:     { fontSize: 13, color: P.g400, fontStyle: 'italic' },
  questionsTitle:{ fontSize: 13, fontWeight: '700', color: P.g800 },
  questionRow:   { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 10, paddingHorizontal: 12, borderRadius: 14, backgroundColor: '#F7FAFD' },
  checkbox:      { width: 22, height: 22, marginTop: 1, borderRadius: 7, borderWidth: 1.5, borderColor: P.g400, alignItems: 'center', justifyContent: 'center' },
  checkboxChecked:{ backgroundColor: P.navy, borderColor: P.navy },
  questionText:  { flex: 1, fontSize: 14, lineHeight: 21, color: P.g800 },
  questionTextDone:{ color: P.g400, textDecorationLine: 'line-through' },
  addQuestionRow:{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  addQuestionInput:{ flex: 1, borderWidth: 1, borderColor: P.g100, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 7, fontSize: 12, color: P.g800 },
  manageRow:     { flexDirection: 'row', alignItems: 'center', gap: 18, marginTop: 12, flexWrap: 'wrap' },
  editBtn:       { flexDirection: 'row', alignItems: 'center', gap: 6 },
  editBtnText:   { fontSize: 13, fontWeight: '700', color: P.navy },
  cancelEditBtn: { alignItems: 'center', paddingVertical: 10 },
  cancelEditText:{ fontSize: 13, fontWeight: '700', color: P.g400 },
  deleteBtn:     { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, alignSelf: 'flex-start' },
  deleteBtnText: { fontSize: 12, fontWeight: '600', color: '#9B1C1C' },
  errorBox:      { padding: 12, borderRadius: 14, backgroundColor: '#FDE2E2' },
  errorText:     { fontSize: 12, color: '#9B1C1C' },
  emptyBox:      { alignItems: 'center', gap: 10, paddingVertical: 30, paddingHorizontal: 20, backgroundColor: P.white, borderRadius: 20 },
  emptyTitle:    { fontSize: 15, fontWeight: '700', color: P.g800 },
  emptySub:      { fontSize: 12, color: P.g400, textAlign: 'center', lineHeight: 18 },
  emptyBtn:      { marginTop: 6, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 12, backgroundColor: P.navy },
  emptyBtnText:  { fontSize: 13, fontWeight: '700', color: 'white' },
});
