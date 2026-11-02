import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  SafeAreaView, ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import KeyboardAwareScroll from '../components/KeyboardAwareScroll';
import { HeartPulse, CircleAlert } from 'lucide-react-native';
import { useAuth } from '../context/AuthContext';
import DateTimeField from '../components/DateTimeField';
import { updateProfile } from '../services/api';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

const SEX_OPTIONS = ['Femenino', 'Masculino', 'Prefiero no decir'];
const BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];

function toIsoDate(date) {
  const pad2 = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

// Paso obligatorio justo después de crear la cuenta (ver RegisterScreen). Se
// pide una sola vez: una vez guardado, el Dashboard nunca lo vuelve a pedir.
// No hay botón de "saltar" a propósito — el equipo decidió que sea
// obligatorio para el piloto, así ningún paciente queda sin esta info base.
export default function CompleteProfileScreen() {
  const { markProfileComplete, logout } = useAuth();
  const [birthDate, setBirthDate] = useState(null);
  const [sex, setSex] = useState(null);
  const [weight, setWeight] = useState('');
  const [bloodType, setBloodType] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    if (!birthDate) return setError('Elige tu fecha de nacimiento.');
    if (!sex) return setError('Elige una opción de sexo.');
    const weightNum = weight.trim() ? Number(weight.replace(',', '.')) : null;
    if (!weightNum || weightNum <= 0) return setError('Ingresa tu peso.');
    if (!bloodType) return setError('Elige tu tipo de sangre.');

    setError(null);
    setLoading(true);
    try {
      await updateProfile({
        birth_date: toIsoDate(birthDate), sex, weight_kg: weightNum, blood_type: bloodType,
      });
      markProfileComplete();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: P.navy }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding">
        <KeyboardAwareScroll
          contentContainerStyle={{ flexGrow: 1, padding: 24, paddingVertical: 40 }}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag">
          <View style={s.logoBox}>
            <HeartPulse size={26} color="white" />
          </View>
          <Text style={s.title}>Tu información de salud</Text>
          <Text style={s.subtitle}>La pedimos una sola vez, aquí — no te la volvemos a preguntar.</Text>

          <View style={s.card}>
            {error && (
              <View style={s.errorBox}>
                <CircleAlert size={14} color="#9B1C1C" />
                <Text style={s.errorText}>{error}</Text>
              </View>
            )}

            <Text style={s.label}>Fecha de nacimiento</Text>
            <DateTimeField mode="date" placeholder="Elige tu fecha de nacimiento" value={birthDate} onChange={setBirthDate} />

            <Text style={s.label}>Sexo</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {SEX_OPTIONS.map((opt) => (
                <TouchableOpacity
                  key={opt}
                  style={[s.chip, sex === opt && s.chipSelected]}
                  onPress={() => setSex(opt)}>
                  <Text style={[s.chipText, sex === opt && s.chipTextSelected]}>{opt}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={s.label}>Peso (kg)</Text>
            <TextInput
              style={s.input}
              placeholder="ej. 62.5"
              placeholderTextColor={P.g400}
              value={weight}
              onChangeText={setWeight}
              keyboardType="decimal-pad"
            />

            <Text style={s.label}>Tipo de sangre</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {BLOOD_TYPES.map((bt) => (
                <TouchableOpacity
                  key={bt}
                  style={[s.chip, bloodType === bt && s.chipSelected]}
                  onPress={() => setBloodType(bt)}>
                  <Text style={[s.chipText, bloodType === bt && s.chipTextSelected]}>{bt}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity style={s.submitBtn} onPress={submit} disabled={loading}>
              {loading ? <ActivityIndicator color="white" /> : <Text style={s.submitText}>Guardar y continuar</Text>}
            </TouchableOpacity>

            <TouchableOpacity style={s.linkRow} onPress={logout}>
              <Text style={s.linkText}>¿No eres tú? <Text style={s.linkStrong}>Cerrar sesión</Text></Text>
            </TouchableOpacity>
          </View>
        </KeyboardAwareScroll>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  logoBox:    { width: 56, height: 56, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center', alignSelf: 'center', marginBottom: 12 },
  title:      { fontSize: 22, fontWeight: '700', color: 'white', textAlign: 'center' },
  subtitle:   { fontSize: 12, color: 'rgba(255,255,255,0.7)', textAlign: 'center', marginTop: 4, marginBottom: 22, paddingHorizontal: 20 },
  card:       { backgroundColor: P.white, borderRadius: 24, padding: 22, gap: 4 },
  label:      { fontSize: 11, fontWeight: '700', color: P.g400, marginTop: 10, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  input:      { borderWidth: 1, borderColor: P.g100, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: P.g800 },
  chip:       { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: P.bg, borderWidth: 1, borderColor: P.g100 },
  chipSelected: { backgroundColor: P.navy, borderColor: P.navy },
  chipText:   { fontSize: 12, fontWeight: '700', color: P.g800 },
  chipTextSelected: { color: 'white' },
  submitBtn:  { marginTop: 20, backgroundColor: P.navy, borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  submitText: { color: 'white', fontWeight: '700', fontSize: 14 },
  linkRow:    { marginTop: 14, alignItems: 'center' },
  linkText:   { fontSize: 12, color: P.g400 },
  linkStrong: { color: P.navy, fontWeight: '700' },
  errorBox:   { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 10, backgroundColor: '#FDE2E2', marginBottom: 6 },
  errorText:  { flex: 1, fontSize: 12, color: '#9B1C1C' },
});
