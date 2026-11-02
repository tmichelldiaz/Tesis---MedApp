import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  StyleSheet, SafeAreaView, ActivityIndicator, Alert, Modal, Pressable, Animated,
} from 'react-native';
import {
  Bell, BrainCircuit, ArrowUpRight,
  ClipboardList, Cake, Weight, Droplets, Pencil, LogOut,
  MessageCircle, X, Trash2, Settings, Mail, ShieldCheck, Sparkles, RefreshCw,
} from 'lucide-react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { listValues, getProfile, getNotifications, listAppointments, listDocuments, reprocessAllDocuments } from '../services/api';
import { confirmAction } from '../utils/confirm';
import { summarizeByExam, ageFromBirthDate, keyExams, unitSuffix } from '../utils/labValues';
import { shortExamName } from '../utils/examNames';
import { iconForExam, assignSoftColors } from '../utils/examIcons';
import Sparkline from '../components/Sparkline';
import NextAppointmentCard, { nextAppointment } from '../components/NextAppointmentCard';
import HeaderIllustration from '../components/HeaderIllustration';
import ProfileEditModal from '../components/ProfileEditModal';
import PolicyModal from '../components/PolicyModal';
import { DeviceSyncSetting } from '../components/DeviceSyncPrompt';
import VersionRow from '../components/VersionRow';
import { startTour } from '../components/GuidedTour';
import { tourRef } from '../services/tourTargets';
import { loadNoticeState, markSeen, dismiss, visibleNotices, hasUnseen, noticeKey } from '../services/noticeState';
import { syncAppointments } from '../services/deviceSync';
import { useAuth } from '../context/AuthContext';

const P = {
  navy:   '#034AA6',
  blue:   '#7998FB',
  blueL:  '#9AB0FC',
  light:  '#C2D7F2',
  bg:     '#F4FAE9',
  white:  '#FFFFFF',
  g50:    '#F8FAF4',
  g100:   '#E2E8F0',
  g200:   '#94A3B8',
  g400:   '#546080',
  g800:   '#02204A',
  accent: '#F29BB2',
};

const RECENT_COUNT = 4;

const ICON_FOR_NOTICE_TYPE = {
  appointment: ClipboardList,
  question: MessageCircle,
  lab: Droplets,
};

// Título corto y color suave de cada tipo de aviso (mismos colores que las tarjetas de resultados).
const NOTICE_LOOK = {
  appointment: { title: 'Cita pasada',          bg: '#DCE9F9', fg: '#034AA6' },
  question:    { title: 'Pregunta pendiente',   bg: '#EBE4FB', fg: '#6B4FD6' },
  lab:         { title: 'Resultados por revisar', bg: '#FDE8EE', fg: '#D6456F' },
};
const DEFAULT_NOTICE_LOOK = { title: 'Aviso', bg: '#DDF3EA', fg: '#1F8A62' };

export default function DashboardScreen() {
  const navigation = useNavigation();
  const { user, logout, deleteAccount } = useAuth();
  const [exams, setExams] = useState(null);
  const [profile, setProfile] = useState(null);
  const [error, setError] = useState(null);
  const [editingProfile, setEditingProfile] = useState(false);
  const [appointments, setAppointments] = useState(null);
  const [notices, setNotices] = useState([]);
  const [notifOpen, setNotifOpen] = useState(false);
  const [noticeState, setNoticeState] = useState({ seen: [], dismissed: [] });
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [policyOpen, setPolicyOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const greetingAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(greetingAnim, {
      toValue: 1, duration: 500, useNativeDriver: true,
    }).start();
  }, []);

  const confirmLogout = () => {
    setMenuOpen(false);
    Alert.alert('Cerrar sesión', '¿Seguro que quieres salir de tu cuenta?', [
      { text: 'Cancelar', style: 'cancel' },
      { text: 'Cerrar sesión', style: 'destructive', onPress: logout },
    ]);
  };

  const confirmDeleteAccount = () => {
    setMenuOpen(false);
    Alert.alert(
      'Borrar cuenta',
      'Esto elimina tu cuenta y TODA tu información de forma permanente: documentos, historias, citas y preguntas. No se puede deshacer. ¿Seguro que quieres continuar?',
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Borrar cuenta',
          style: 'destructive',
          onPress: async () => {
            setDeleting(true);
            try {
              await deleteAccount();
            } catch (e) {
              setDeleting(false);
              Alert.alert('Error', e.message);
            }
          },
        },
      ]
    );
  };

  useFocusEffect(
    useCallback(() => {
      let active = true;
      // Se necesita la fecha de subida de cada archivo para saber cuál es la última historia.
      Promise.all([listValues(), listDocuments().catch(() => [])])
        .then(([rows, docs]) => {
          if (!active) return;
          const createdAt = Object.fromEntries(docs.map((d) => [d.id, d.created_at || '']));
          setExams(summarizeByExam(rows, createdAt));
        })
        .catch((e) => active && setError(e.message));
      getProfile()
        .then((p) => active && setProfile(p))
        .catch(() => {});
      listAppointments()
        .then((rows) => {
          if (!active) return;
          setAppointments(rows);
          syncAppointments(user?.id, rows); // citas nuevas (p. ej. las que agenda el asistente)
        })
        .catch(() => active && setAppointments(false));
      Promise.all([getNotifications(), loadNoticeState(user?.id)])
        .then(([r, state]) => {
          if (!active) return;
          setNotices(r.notices);
          setNoticeState(state);
        })
        .catch(() => {});
      return () => { active = false; };
    }, [])
  );

  // Al abrir la campana, los avisos pasan a "vistos" y el círculo se apaga.
  // Vuelve a leer todas las historias con los modelos actuales (si falla alguna, queda como estaba).
  const rereadHistories = async () => {
    const ok = await confirmAction(
      'Releer mis historias',
      'Vamos a volver a leer todas tus historias con el modelo más preciso. Tarda unos minutos y puedes seguir usando la app. Si algo falla, la historia queda como estaba.',
      'Releer',
    );
    if (!ok) return;
    try {
      const { count } = await reprocessAllDocuments();
      setSettingsOpen(false);
      Alert.alert(
        count ? 'Releyendo tus historias' : 'No hay historias para releer',
        count ? `Estamos leyendo ${count} ${count === 1 ? 'historia' : 'historias'} de nuevo. Mira el avance en Biblioteca.` : 'Cuando subas una historia aparecerá aquí.',
      );
    } catch (e) {
      Alert.alert('No se pudo iniciar', e.message);
    }
  };

  // El círculo se apaga en el mismo instante (sin esperar al guardado en el teléfono).
  const openNotices = () => {
    const shown = visibleNotices(notices, noticeState);
    setNotifOpen(true);
    setNoticeState((st) => ({ ...st, seen: [...new Set([...st.seen, ...shown.map(noticeKey)])] }));
    markSeen(user?.id, shown).then(setNoticeState).catch(() => {});
  };

  // Descartar un aviso con la X: no vuelve a salir mientras sea el mismo.
  const discardNotice = (notice) => dismiss(user?.id, notice).then(setNoticeState);

  // Tocar un aviso lleva a donde se resuelve.
  const goToNotice = (notice) => {
    setNotifOpen(false);
    if (notice.type === 'lab') navigation.navigate('Library');
    else navigation.navigate('Calendar');
  };

  const recent = exams ? keyExams(exams, RECENT_COUNT) : [];
  const tones = assignSoftColors(recent.map((e) => e.exam));
  const recentRows = [];
  for (let i = 0; i < recent.length; i += 2) recentRows.push(recent.slice(i, i + 2));
  const age = profile ? ageFromBirthDate(profile.birth_date) : null;
  const hasProfileInfo = profile && (profile.name || age != null || profile.weight_kg || profile.blood_type);
  const firstName = profile?.name ? profile.name.split(' ')[0] : null;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: P.navy }}>
      <ScrollView style={{ flex: 1, backgroundColor: P.bg }} showsVerticalScrollIndicator={false}>

        {/* Header azul: iconos arriba, saludo centrado verticalmente abajo */}
        <View style={s.profileHeader}>
          <View style={s.headerTopRow}>
            <View ref={tourRef('bell')} collapsable={false}>
              <TouchableOpacity style={s.topIconBtn} onPress={openNotices}>
                <Bell size={22} color="white" />
                {hasUnseen(notices, noticeState) && <View style={s.notifDot} />}
              </TouchableOpacity>
            </View>
            <TouchableOpacity style={s.topIconBtn} onPress={() => setMenuOpen(true)}>
              <LogOut size={22} color="white" />
            </TouchableOpacity>
          </View>

          <View style={s.greetingArea}>
            <Animated.View
              style={{
                flex: 1,
                opacity: greetingAnim,
                transform: [{ translateY: greetingAnim.interpolate({ inputRange: [0, 1], outputRange: [12, 0] }) }],
              }}>
              <Text style={s.greeting}>Hola{firstName ? `, ${firstName}` : ''}</Text>
              <TouchableOpacity style={s.editRow} onPress={() => setEditingProfile(true)}>
                <Pencil size={13} color="rgba(255,255,255,0.75)" />
                <Text style={s.editText}>{hasProfileInfo ? 'Editar información' : 'Completa tu información'}</Text>
              </TouchableOpacity>
            </Animated.View>
            <HeaderIllustration size={64} />
          </View>
        </View>

        {hasProfileInfo && (
          <View style={s.infoChipsRow}>
            {age != null && (
              <View style={s.infoChip}>
                <Cake size={22} color={P.navy} />
                <Text style={s.infoChipValue}>{age}</Text>
                <Text style={s.infoChipLabel}>años</Text>
              </View>
            )}
            {profile?.weight_kg != null && (
              <View style={s.infoChip}>
                <Weight size={22} color={P.navy} />
                <Text style={s.infoChipValue}>{profile.weight_kg}</Text>
                <Text style={s.infoChipLabel}>kg</Text>
              </View>
            )}
            {profile?.blood_type && (
              <View style={s.infoChip}>
                <Droplets size={22} color={P.navy} />
                <Text style={s.infoChipValue}>{profile.blood_type}</Text>
                <Text style={s.infoChipLabel}>RH</Text>
              </View>
            )}
          </View>
        )}

        <View style={{ padding: 16, gap: 20 }}>

          {error && (
            <View style={s.errorBox}>
              <Text style={s.errorText}>{error}</Text>
            </View>
          )}

          {exams === null && (
            <ActivityIndicator color={P.navy} style={{ marginTop: 20 }} />
          )}

          {exams?.length === 0 && (
            <View style={s.emptyBox}>
              {/* El recorrido ilumina solo el mensaje, no el botón, para que su tarjeta no lo tape */}
              <View ref={tourRef('keyResults')} collapsable={false} style={{ alignItems: 'center', gap: 10 }}>
                <ClipboardList size={32} color={P.navy} />
                <Text style={s.emptyTitle}>Todavía no hay resultados</Text>
                <Text style={s.emptySub}>
                  Sube tu primera historia clínica para que aparezcan aquí tus exámenes.
                </Text>
              </View>
              <TouchableOpacity style={s.emptyBtn} onPress={() => navigation.navigate('Upload')}>
                <Text style={s.emptyBtnText}>Ir a Subir</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* AI summary */}
          {exams?.length > 0 && (
            <TouchableOpacity
              style={s.aiCard}
              onPress={() => navigation.navigate('Chat')}>
              <View style={s.aiIconBox}>
                <BrainCircuit size={22} color="white" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={{ fontWeight: '700', fontSize: 13, color: P.g800 }}>Asistente IA</Text>
                <Text style={{ fontSize: 12, marginTop: 2, color: P.g400 }}>
                  Pregúntale sobre tus resultados y su evolución.
                </Text>
              </View>
              <ArrowUpRight size={16} color={P.navy} />
            </TouchableOpacity>
          )}

          {/* Próxima cita: fecha, lugar y las preguntas que el paciente quiere hacer */}
          {appointments !== null && appointments !== false && (
            <NextAppointmentCard
              appointment={nextAppointment(appointments)}
              tone={assignSoftColors(appointments.map((a) => a.id))[nextAppointment(appointments)?.id]}
              onOpen={() => navigation.navigate('Calendar')}
            />
          )}

          {/* Resultados clave: los 4 más importantes en 2 columnas; cada uno
              abre el detalle con gráfica, resumen y enlace al chat */}
          {recent.length > 0 && (
            <View>
              <View style={s.sectionHeader}>
                <Text style={s.sectionTitle}>Resultados clave</Text>
                {exams.length > RECENT_COUNT && (
                  <Text style={s.sectionCount}>{recent.length} de {exams.length}</Text>
                )}
              </View>
              <View style={{ gap: 10 }}>
                {recentRows.map((row, ri) => (
                  <View key={ri} ref={ri === 0 ? tourRef('keyResults') : undefined} collapsable={false} style={s.tileRow}>
                    {row.map((e) => {
                      const Icon = iconForExam(e.exam);
                      const color = tones[e.exam];
                      const outOfRange = e.status === false;
                      const lineColor = outOfRange ? '#D6456F' : color.fg;
                      const series = (e.history || []).map((h) => h.value_numeric);
                      return (
                        <TouchableOpacity
                          key={e.exam}
                          style={s.tile}
                          activeOpacity={0.85}
                          accessibilityLabel={`${shortExamName(e.exam)}: ${e.value_raw}`}
                          onPress={() => navigation.navigate('ExamDetail', { examName: e.exam, tone: color })}>
                          <View style={s.tileTop}>
                            <View style={[s.tileIconBox, { backgroundColor: color.bg }]}>
                              <Icon size={18} color={color.fg} />
                            </View>
                            <Text style={s.tileTitle}>{shortExamName(e.exam)}</Text>
                          </View>
                          <View style={s.tileValueRow}>
                            <Text style={s.tileValue} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
                              {e.value_raw}
                            </Text>
                            {!!unitSuffix(e.value_raw, e.unit) && <Text style={s.tileUnit} numberOfLines={1}>{e.unit}</Text>}
                          </View>
                          <Sparkline
                            values={series}
                            low={e.reference_low}
                            high={e.reference_high}
                            color={lineColor}
                          />
                          {e.status !== null ? (
                            <View style={[s.badge, { backgroundColor: outOfRange ? '#FDE8EE' : '#E3F3EA' }]}>
                              <View style={[s.badgeDot, { backgroundColor: outOfRange ? '#D6456F' : '#2E8B57' }]} />
                              <Text style={{ fontSize: 10, fontWeight: '700', color: outOfRange ? '#B02A55' : '#1F6B42' }}>
                                {outOfRange ? 'Fuera de rango' : 'En rango'}
                              </Text>
                            </View>
                          ) : null}
                        </TouchableOpacity>
                      );
                    })}
                    {row.length === 1 && <View style={{ flex: 1 }} />}
                  </View>
                ))}
              </View>
            </View>
          )}
        </View>
      </ScrollView>

      <ProfileEditModal
        visible={editingProfile}
        profile={profile}
        onClose={() => setEditingProfile(false)}
        onSaved={setProfile}
      />

      <Modal visible={notifOpen} transparent animationType="slide" onRequestClose={() => setNotifOpen(false)}>
        <Pressable style={s.modalOverlay} onPress={() => setNotifOpen(false)}>
          <Pressable style={s.notifSheet}>
            <View style={s.notifHeader}>
              <Text style={s.notifTitle}>Notificaciones</Text>
              <TouchableOpacity onPress={() => setNotifOpen(false)} style={s.notifCloseBtn}>
                <X size={19} color={P.g800} />
              </TouchableOpacity>
            </View>
            <ScrollView showsVerticalScrollIndicator={false} style={{ maxHeight: 420 }}>
              {visibleNotices(notices, noticeState).length === 0 && (
                <Text style={s.notifEmpty}>No tienes notificaciones por ahora.</Text>
              )}
              {visibleNotices(notices, noticeState).map((n) => {
                const Icon = ICON_FOR_NOTICE_TYPE[n.type] || Bell;
                const look = NOTICE_LOOK[n.type] || DEFAULT_NOTICE_LOOK;
                return (
                  <TouchableOpacity key={`${n.type}|${n.text}`} style={s.notifRow} onPress={() => goToNotice(n)} activeOpacity={0.7}>
                    <View style={[s.notifIcon, { backgroundColor: look.bg }]}>
                      <Icon size={19} color={look.fg} />
                    </View>
                    <View style={s.notifBody}>
                      <Text style={s.notifItemTitle}>{look.title}</Text>
                      <Text style={s.notifText}>{n.text}</Text>
                    </View>
                    <TouchableOpacity
                      onPress={() => discardNotice(n)}
                      hitSlop={10}
                      accessibilityLabel="Descartar aviso"
                      style={s.notifDismiss}>
                      <X size={16} color={P.g400} />
                    </TouchableOpacity>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={menuOpen} transparent animationType="slide" onRequestClose={() => setMenuOpen(false)}>
        <Pressable style={s.modalOverlay} onPress={() => setMenuOpen(false)}>
          <Pressable style={s.notifSheet}>
            <View style={s.notifHeader}>
              <Text style={s.notifTitle}>Tu cuenta</Text>
              <TouchableOpacity onPress={() => setMenuOpen(false)} style={s.notifCloseBtn}>
                <X size={19} color={P.g800} />
              </TouchableOpacity>
            </View>
            <TouchableOpacity
              style={s.menuRow}
              onPress={() => { setMenuOpen(false); setSettingsOpen(true); }}>
              <View style={s.notifIcon}>
                <Settings size={19} color={P.navy} />
              </View>
              <Text style={s.menuRowText}>Configuración</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.menuRow} onPress={confirmLogout}>
              <View style={s.notifIcon}>
                <LogOut size={19} color={P.navy} />
              </View>
              <Text style={s.menuRowText}>Cerrar sesión</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.menuRow} onPress={confirmDeleteAccount} disabled={deleting}>
              <View style={[s.notifIcon, { backgroundColor: '#FDE2E2' }]}>
                <Trash2 size={19} color="#9B1C1C" />
              </View>
              <Text style={[s.menuRowText, { color: '#9B1C1C' }]}>
                {deleting ? 'Borrando cuenta...' : 'Borrar cuenta'}
              </Text>
            </TouchableOpacity>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={settingsOpen} transparent animationType="slide" onRequestClose={() => setSettingsOpen(false)}>
        <Pressable style={s.modalOverlay} onPress={() => setSettingsOpen(false)}>
          <Pressable style={s.notifSheet}>
            <View style={s.notifHeader}>
              <Text style={s.notifTitle}>Configuración</Text>
              <TouchableOpacity onPress={() => setSettingsOpen(false)} style={s.notifCloseBtn}>
                <X size={19} color={P.g800} />
              </TouchableOpacity>
            </View>
            <View style={s.menuRow}>
              <View style={s.notifIcon}>
                <Mail size={19} color={P.navy} />
              </View>
              <Text style={s.menuRowText}>{user?.email}</Text>
            </View>
            <DeviceSyncSetting appointments={Array.isArray(appointments) ? appointments : []} />
            <TouchableOpacity
              style={s.menuRow}
              onPress={() => { setSettingsOpen(false); startTour(); }}>
              <View style={s.notifIcon}>
                <Sparkles size={19} color={P.navy} />
              </View>
              <Text style={s.menuRowText}>Ver el tutorial de la app</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.menuRow} onPress={rereadHistories}>
              <View style={s.notifIcon}>
                <RefreshCw size={19} color={P.navy} />
              </View>
              <Text style={s.menuRowText}>Releer mis historias con el modelo nuevo</Text>
            </TouchableOpacity>
            <VersionRow />
            <TouchableOpacity
              style={s.menuRow}
              onPress={() => { setSettingsOpen(false); setPolicyOpen(true); }}>
              <View style={s.notifIcon}>
                <ShieldCheck size={19} color={P.navy} />
              </View>
              <Text style={s.menuRowText}>Leer la política de protección de datos</Text>
            </TouchableOpacity>
          </Pressable>
        </Pressable>
      </Modal>

      <PolicyModal visible={policyOpen} readOnly onClose={() => setPolicyOpen(false)} />

    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topIconBtn:  { width: 46, height: 46, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center', position: 'relative' },
  notifDot:    { position: 'absolute', top: 9, right: 9, width: 10, height: 10, borderRadius: 5, backgroundColor: '#F29BB2', borderWidth: 2, borderColor: P.navy },
  profileHeader:{ minHeight: 220, paddingHorizontal: 20, paddingTop: 50, paddingBottom: 24, backgroundColor: P.navy, borderBottomLeftRadius: 28, borderBottomRightRadius: 28 },
  headerTopRow:{ flexDirection: 'row', justifyContent: 'flex-end', gap: 8 },
  greetingArea:{ flex: 1, flexDirection: 'row', alignItems: 'center' },
  greeting:    { fontSize: 34, fontFamily: 'Poppins_700Bold', color: 'white' },
  editRow:     { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 },
  editText:    { fontSize: 13, fontFamily: 'Poppins_500Medium', color: 'rgba(255,255,255,0.8)' },
  infoChipsRow:{ flexDirection: 'row', gap: 10, paddingHorizontal: 16, marginTop: -18, marginBottom: 4 },
  infoChip:    { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: P.white, borderRadius: 16, paddingVertical: 12, paddingHorizontal: 12, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 10, elevation: 3 },
  infoChipValue:{ fontSize: 17, fontWeight: '700', color: P.g800 },
  infoChipLabel:{ fontSize: 12, color: P.g400 },
  sectionHeader:{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 },
  sectionTitle:{ fontSize: 16, fontFamily: 'Poppins_700Bold', color: '#02204A' },
  sectionCount:{ fontSize: 12, color: P.g400 },
  aiCard:      { borderRadius: 20, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: '#FFFFFF', shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 12, elevation: 2 },
  aiIconBox:   { width: 44, height: 44, borderRadius: 14, backgroundColor: '#034AA6', alignItems: 'center', justifyContent: 'center' },
  tileRow:     { flexDirection: 'row', gap: 10 },
  tile:        { flex: 1, minWidth: 0, padding: 14, borderRadius: 22, backgroundColor: '#FFFFFF', gap: 10, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.14, shadowRadius: 16, elevation: 8 },
  tileTop:     { flexDirection: 'row', alignItems: 'center', gap: 8 },
  tileIconBox: { width: 34, height: 34, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  badgeDot:    { width: 6, height: 6, borderRadius: 3 },
  tileTitle:   { flex: 1, fontSize: 13, lineHeight: 17, fontWeight: '700', color: P.g800 },
  tileValueRow:{ flexDirection: 'row', alignItems: 'flex-end', gap: 4 },
  tileValue:   { flexShrink: 1, fontSize: 26, fontWeight: '900', color: P.g800, letterSpacing: -0.5 },
  tileUnit:    { flexShrink: 1, fontSize: 11, color: P.g400, marginBottom: 3 },
  badge:       { flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 4, borderRadius: 999 },
  errorBox:    { padding: 12, borderRadius: 14, backgroundColor: '#FDE2E2' },
  errorText:   { fontSize: 12, color: '#9B1C1C' },
  emptyBox:    { alignItems: 'center', gap: 10, paddingVertical: 30, paddingHorizontal: 20, backgroundColor: P.white, borderRadius: 20 },
  emptyTitle:  { fontSize: 15, fontFamily: 'Poppins_700Bold', color: P.g800 },
  emptySub:    { fontSize: 12, color: P.g400, textAlign: 'center', lineHeight: 18 },
  emptyBtn:    { marginTop: 6, paddingHorizontal: 18, paddingVertical: 10, borderRadius: 12, backgroundColor: P.navy },
  emptyBtnText:{ fontSize: 13, fontWeight: '700', color: 'white' },
  modalOverlay:{ flex: 1, backgroundColor: 'rgba(2,32,74,0.4)', justifyContent: 'flex-end' },
  notifSheet:  { backgroundColor: P.white, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, paddingBottom: 30 },
  notifHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  notifTitle:  { fontSize: 17, fontFamily: 'Poppins_700Bold', color: P.g800 },
  notifCloseBtn:{ width: 34, height: 34, borderRadius: 11, backgroundColor: P.bg, alignItems: 'center', justifyContent: 'center' },
  notifEmpty:  { fontSize: 13, color: P.g400, textAlign: 'center', paddingVertical: 20 },
  notifRow:    { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 14, marginBottom: 10, borderRadius: 18, backgroundColor: P.bg },
  notifIcon:   { width: 38, height: 38, borderRadius: 12, backgroundColor: P.bg, alignItems: 'center', justifyContent: 'center' },
  notifBody:   { flex: 1, minWidth: 0, gap: 3 },
  notifItemTitle:{ fontSize: 14, fontFamily: 'Poppins_700Bold', color: P.g800 },
  notifDismiss:{ width: 30, height: 30, alignItems: 'center', justifyContent: 'center' },
  notifText:   { fontSize: 13, color: P.g400, lineHeight: 19 },
  menuRow:     { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14 },
  menuRowText: { fontSize: 15, fontWeight: '600', color: P.g800 },
});
