import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert, ActivityIndicator } from 'react-native';
import { RefreshCw } from 'lucide-react-native';
import Constants from 'expo-constants';
import { checkAndApplyUpdate, currentBuildInfo } from '../services/otaUpdate';

const P = { navy: '#034AA6', bg: '#F4FAE9', g400: '#546080', g800: '#02204A' };

// Fila de Configuración: qué versión está corriendo y un botón para buscar actualizaciones
// sin tener que reiniciar la app varias veces.
export default function VersionRow() {
  const [busy, setBusy] = useState(false);
  const info = currentBuildInfo();
  const version = Constants.expoConfig?.version || '';
  const detail = !info.enabled
    ? 'sin actualizaciones automáticas en este modo'
    : info.embedded
      ? 'versión de fábrica'
      : `actualización ${info.updateId}`;

  const search = async () => {
    setBusy(true);
    const result = await checkAndApplyUpdate();
    setBusy(false);
    const messages = {
      none: ['Ya estás al día', 'Tienes la última versión disponible.'],
      unavailable: ['No disponible', 'Las actualizaciones automáticas no funcionan en este modo de ejecución.'],
      error: ['No se pudo comprobar', 'Revisa tu conexión a internet e intenta de nuevo.'],
      applied: ['Actualizando', 'La app se va a reiniciar con la versión nueva.'],
    };
    const [title, body] = messages[result] || messages.error;
    Alert.alert(title, body);
  };

  return (
    <View style={s.row}>
      <View style={s.icon}><RefreshCw size={19} color={P.navy} /></View>
      <View style={{ flex: 1 }}>
        <Text style={s.title}>MedApp {version}</Text>
        <Text style={s.sub}>{detail}</Text>
      </View>
      <TouchableOpacity style={s.btn} onPress={search} disabled={busy}>
        {busy ? <ActivityIndicator size="small" color="white" /> : <Text style={s.btnText}>Buscar</Text>}
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 14 },
  icon: { width: 38, height: 38, borderRadius: 11, backgroundColor: P.bg, alignItems: 'center', justifyContent: 'center' },
  title: { fontSize: 15, fontWeight: '600', color: P.g800 },
  sub: { fontSize: 12, color: P.g400, marginTop: 2 },
  btn: { minWidth: 70, paddingVertical: 9, paddingHorizontal: 14, borderRadius: 12, backgroundColor: P.navy, alignItems: 'center' },
  btnText: { fontSize: 13, fontWeight: '700', color: 'white' },
});
