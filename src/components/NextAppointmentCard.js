import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { formatQuestion } from '../utils/examNames';
import { CalendarClock, MapPin, Stethoscope, Clock, MessageCircleQuestion } from 'lucide-react-native';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2', bg: '#F4FAE9', white: '#FFFFFF',
  g100: '#E2E8F0', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

const MONTHS = ['ENE', 'FEB', 'MAR', 'ABR', 'MAY', 'JUN', 'JUL', 'AGO', 'SEP', 'OCT', 'NOV', 'DIC'];
const MAX_QUESTIONS = 3;

// La próxima cita es la primera que todavía no ha empezado. Se deja una hora de
// margen para que una cita en curso no desaparezca justo a su hora.
export function nextAppointment(appointments, now = new Date()) {
  const limit = now.getTime() - 60 * 60 * 1000;
  return (appointments || [])
    .filter((a) => {
      const t = new Date(a.scheduled_at).getTime();
      return !Number.isNaN(t) && t >= limit;
    })
    .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at))[0] || null;
}

function countdown(date, now = new Date()) {
  const startOf = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(date) - startOf(now)) / 86400000);
  if (days <= 0) return 'Hoy';
  if (days === 1) return 'Mañana';
  return `En ${days} días`;
}

export default function NextAppointmentCard({ appointment, onOpen, tone }) {
  const accent = tone || { bg: '#E6ECFF', fg: P.navy };
  if (!appointment) {
    return (
      <View style={s.emptyCard}>
        <View style={s.emptyIcon}>
          <CalendarClock size={22} color={P.navy} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={s.emptyTitle}>Sin citas próximas</Text>
          <Text style={s.emptySub}>Cuando registres una cita, aquí verás su fecha, lugar y tus preguntas.</Text>
        </View>
      </View>
    );
  }

  const date = new Date(appointment.scheduled_at);
  const pending = (appointment.questions || []).filter((q) => !q.answered);
  const shown = pending.slice(0, MAX_QUESTIONS);
  const extra = pending.length - shown.length;
  const when = date.toLocaleDateString('es-CO', { weekday: 'long', day: 'numeric', month: 'long' });
  const time = date.toTimeString().slice(0, 5);

  return (
    <View>
      <View style={s.sectionHeader}>
        <Text style={s.sectionTitle}>Próxima cita</Text>
        <TouchableOpacity onPress={onOpen} hitSlop={8}>
          <Text style={s.viewAll}>Ver todas</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity style={s.card} onPress={onOpen} activeOpacity={0.85}>
        <View style={s.topRow}>
          <View style={[s.dateBox, { backgroundColor: accent.fg }]}>
            <Text style={s.dateMonth}>{MONTHS[date.getMonth()]}</Text>
            <Text style={s.dateDay}>{String(date.getDate()).padStart(2, '0')}</Text>
          </View>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={s.title} numberOfLines={2}>{appointment.title}</Text>
            <Text style={s.when} numberOfLines={1}>{when}</Text>
          </View>
          <View style={[s.countChip, { backgroundColor: accent.bg }]}>
            <Text style={[s.countText, { color: accent.fg }]}>{countdown(date)}</Text>
          </View>
        </View>

        <View style={s.metaWrap}>
          <View style={s.metaItem}>
            <Clock size={14} color={accent.fg} />
            <Text style={s.metaText}>{time}</Text>
          </View>
          {!!appointment.doctor_name && (
            <View style={s.metaItem}>
              <Stethoscope size={14} color={accent.fg} />
              <Text style={s.metaText} numberOfLines={1}>{appointment.doctor_name}</Text>
            </View>
          )}
          {!!appointment.location && (
            <View style={s.metaItem}>
              <MapPin size={14} color={accent.fg} />
              <Text style={s.metaText} numberOfLines={1}>{appointment.location}</Text>
            </View>
          )}
        </View>

        <View style={s.divider} />

        {shown.length > 0 ? (
          <View style={{ gap: 8 }}>
            <View style={s.qHead}>
              <MessageCircleQuestion size={15} color={accent.fg} />
              <Text style={s.qTitle}>Preguntas para tu médico ({pending.length})</Text>
            </View>
            {shown.map((q) => (
              <View key={q.id} style={s.qRow}>
                <View style={[s.bullet, { backgroundColor: accent.fg }]} />
                <Text style={s.qText} numberOfLines={3}>{formatQuestion(q.text)}</Text>
              </View>
            ))}
            {extra > 0 && <Text style={s.more}>y {extra} más</Text>}
          </View>
        ) : (
          <Text style={s.noQuestions}>
            Todavía no anotaste preguntas para esta cita. Toca para agregarlas.
          </Text>
        )}
      </TouchableOpacity>
    </View>
  );
}

const shadow = { shadowColor: '#1A2040', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.07, shadowRadius: 14, elevation: 3 };

const s = StyleSheet.create({
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 },
  sectionTitle: { fontSize: 16, fontFamily: 'Poppins_700Bold', color: P.g800 },
  viewAll: { fontSize: 13, fontWeight: '600', color: P.navy },
  card: { backgroundColor: P.white, borderRadius: 22, padding: 16, gap: 12, ...shadow },
  topRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  dateBox: { width: 54, height: 58, borderRadius: 16, backgroundColor: P.navy, alignItems: 'center', justifyContent: 'center' },
  dateMonth: { fontSize: 10, fontWeight: '800', letterSpacing: 1, color: 'rgba(255,255,255,0.8)' },
  dateDay: { fontSize: 22, fontWeight: '900', color: 'white', lineHeight: 26 },
  title: { fontSize: 15, fontWeight: '700', color: P.g800 },
  when: { fontSize: 12, color: P.g400, marginTop: 2, textTransform: 'capitalize' },
  countChip: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 999, backgroundColor: '#E6ECFF' },
  countText: { fontSize: 11, fontWeight: '800', color: P.navy },
  metaWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 6, maxWidth: '100%', paddingHorizontal: 10, paddingVertical: 6, borderRadius: 999, backgroundColor: '#F1F5FB' },
  metaText: { flexShrink: 1, fontSize: 12, fontWeight: '600', color: P.g800 },
  divider: { height: 1, backgroundColor: P.g100 },
  qHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  qTitle: { fontSize: 12, fontWeight: '800', color: P.g800 },
  qRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10 },
  bullet: { width: 6, height: 6, borderRadius: 3, backgroundColor: P.accent, marginTop: 7 },
  qText: { flex: 1, fontSize: 13, lineHeight: 19, color: P.g800 },
  more: { fontSize: 12, fontWeight: '600', color: P.navy, marginLeft: 16 },
  noQuestions: { fontSize: 12, lineHeight: 18, color: P.g400 },
  emptyCard: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: P.white, borderRadius: 22, padding: 16, ...shadow },
  emptyIcon: { width: 44, height: 44, borderRadius: 14, backgroundColor: '#E6ECFF', alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { fontSize: 14, fontWeight: '700', color: P.g800 },
  emptySub: { fontSize: 12, color: P.g400, marginTop: 2 },
});
