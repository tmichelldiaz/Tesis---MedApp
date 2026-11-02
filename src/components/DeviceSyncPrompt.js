import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, Switch, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { CalendarPlus, BellRing } from 'lucide-react-native';
import { useAuth } from '../context/AuthContext';
import {
  isSupported, getPreference, enable, decline, disable, syncAppointments,
} from '../services/deviceSync';

const P = {
  navy: '#034AA6', light: '#C2D7F2', white: '#FFFFFF', g100: '#E2E8F0',
  g400: '#546080', g800: '#02204A',
};

function explain(result) {
  if (!result.ok) {
    return 'No diste permiso, así que no se activó. Puedes activarlo después desde Configuración, o en los permisos del teléfono.';
  }
  const where = result.calendarName ? `tu calendario "${result.calendarName}"` : 'tu calendario';
  if (result.calendar && result.notifications) {
    return `Listo. Tus citas quedarán en ${where}. Te avisaremos el día antes, dos horas antes y después de la cita.`;
  }
  if (result.calendar) {
    return `Tus citas quedarán en ${where}. Sin permiso de notificaciones no podremos mandarte los recordatorios.`;
  }
  return 'Te avisaremos antes de cada cita. Sin permiso de calendario no podremos guardarlas en tu calendario.';
}

function useDevicePreference() {
  const { user } = useAuth();
  const [pref, setPref] = useState(undefined); // undefined = cargando
  const supported = isSupported();

  const reload = useCallback(async () => {
    if (!supported || !user?.id) { setPref(false); return; }
    setPref(await getPreference(user.id));
  }, [supported, user?.id]);

  useEffect(() => { reload(); }, [reload]);
  return { user, pref, setPref, supported };
}

// Aviso que aparece una sola vez en Citas, cuando ya hay citas y todavía no se
// le ha preguntado al paciente.
export function DeviceSyncBanner({ appointments }) {
  const { user, pref, setPref, supported } = useDevicePreference();
  const [busy, setBusy] = useState(false);

  if (!supported || pref !== null || !appointments?.length) return null;

  const accept = async () => {
    setBusy(true);
    try {
      const result = await enable(user.id, appointments);
      setPref(result.ok);
      Alert.alert(result.ok ? 'Activado' : 'No se activó', explain(result));
    } finally {
      setBusy(false);
    }
  };

  const later = async () => {
    await decline(user.id);
    setPref(false);
  };

  return (
    <View style={s.banner}>
      <View style={s.bannerTop}>
        <View style={s.iconBox}><CalendarPlus size={22} color={P.navy} /></View>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>Que no se te pase ninguna cita</Text>
          <Text style={s.sub}>
            Guarda tus citas en tu Google Calendar y recibe avisos el día antes y dos horas antes,
            con las preguntas que quieres hacerle a tu médico, y otro después de la cita para
            contarnos cómo te fue.
          </Text>
        </View>
      </View>
      <Text style={s.privacy}>
        En tu Google Calendar se guarda el nombre de la cita, el médico y el lugar; tus preguntas no.
        Los avisos sí las nombran para que no se te olviden: si no quieres que se vean en la pantalla
        bloqueada, ocúltalas en los ajustes de notificaciones del teléfono.
      </Text>
      <View style={s.actions}>
        <TouchableOpacity style={s.secondary} onPress={later} disabled={busy}>
          <Text style={s.secondaryText}>Ahora no</Text>
        </TouchableOpacity>
        <TouchableOpacity style={s.primary} onPress={accept} disabled={busy}>
          {busy ? <ActivityIndicator color="white" /> : <Text style={s.primaryText}>Activar</Text>}
        </TouchableOpacity>
      </View>
    </View>
  );
}

// Interruptor para Configuración: activar o apagar la función en cualquier momento.
export function DeviceSyncSetting({ appointments }) {
  const { user, pref, setPref, supported } = useDevicePreference();
  const [busy, setBusy] = useState(false);
  if (!supported) return null;

  const toggle = async (value) => {
    setBusy(true);
    try {
      if (value) {
        const result = await enable(user.id, appointments || []);
        setPref(result.ok);
        Alert.alert(result.ok ? 'Activado' : 'No se activó', explain(result));
      } else {
        await disable(user.id);
        setPref(false);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={s.settingRow}>
      <View style={s.settingIcon}><BellRing size={19} color={P.navy} /></View>
      <View style={{ flex: 1 }}>
        <Text style={s.settingTitle}>Citas en mi calendario y recordatorios</Text>
        <Text style={s.settingSub}>Se guardan en tu Google Calendar, con avisos antes de cada cita.</Text>
      </View>
      <Switch
        value={pref === true}
        onValueChange={toggle}
        disabled={busy || pref === undefined}
        trackColor={{ true: P.navy, false: P.g100 }}
      />
    </View>
  );
}

export { syncAppointments };

const s = StyleSheet.create({
  banner: { backgroundColor: P.white, borderRadius: 22, padding: 18, gap: 12, borderWidth: 1.5, borderColor: P.light, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.07, shadowRadius: 14, elevation: 3 },
  bannerTop: { flexDirection: 'row', gap: 14 },
  iconBox: { width: 44, height: 44, borderRadius: 14, backgroundColor: '#DCE9F9', alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 15, fontWeight: '700', color: P.g800 },
  sub: { fontSize: 13, lineHeight: 19, color: P.g400, marginTop: 4 },
  privacy: { fontSize: 11, lineHeight: 16, color: P.g400 },
  actions: { flexDirection: 'row', gap: 10 },
  secondary: { flex: 1, paddingVertical: 12, borderRadius: 14, alignItems: 'center', backgroundColor: '#F1F5FB' },
  secondaryText: { fontSize: 13, fontWeight: '700', color: P.g400 },
  primary: { flex: 1.4, paddingVertical: 12, borderRadius: 14, alignItems: 'center', backgroundColor: P.navy },
  primaryText: { fontSize: 13, fontWeight: '700', color: 'white' },
  settingRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14 },
  settingIcon: { width: 38, height: 38, borderRadius: 11, backgroundColor: '#F4FAE9', alignItems: 'center', justifyContent: 'center' },
  settingTitle: { fontSize: 15, fontWeight: '600', color: P.g800 },
  settingSub: { fontSize: 12, color: P.g400, marginTop: 2 },
});
