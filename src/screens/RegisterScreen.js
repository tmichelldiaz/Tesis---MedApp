import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  SafeAreaView, ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import KeyboardAwareScroll from '../components/KeyboardAwareScroll';
import { HeartPulse, CircleAlert, Check, ShieldCheck } from 'lucide-react-native';
import { useAuth } from '../context/AuthContext';
import PolicyModal from '../components/PolicyModal';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

// Mismas reglas que _validate_password_strength en el backend — se checan
// aquí también para que el usuario vea en vivo qué le falta, en vez de
// enterarse solo cuando el servidor rechaza el registro.
const PASSWORD_RULES = [
  { test: (p) => p.length >= 8, label: 'Al menos 8 caracteres' },
  { test: (p) => /[A-ZÁÉÍÓÚÑ]/.test(p), label: 'Una letra mayúscula' },
  { test: (p) => /[a-záéíóúñ]/.test(p), label: 'Una letra minúscula' },
  { test: (p) => /\d/.test(p), label: 'Un número' },
  { test: (p) => /[^\w\s]/.test(p), label: 'Un símbolo (ej. !@#$%)' },
];

// Solo datos de cuenta acá. Los datos médicos (fecha de nacimiento, sexo,
// peso, tipo de sangre) se piden después, ya con la cuenta creada, en
// CompleteProfileScreen — separar los dos pasos reduce la fricción de este
// formulario y deja claro que uno es "crear cuenta" y el otro "tu salud".
export default function RegisterScreen({ navigation }) {
  const { register } = useAuth();
  const [nombre, setNombre] = useState('');
  const [apellido, setApellido] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [policyDecision, setPolicyDecision] = useState(null); // null | 'accepted' | 'declined'
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const passwordChecks = PASSWORD_RULES.map((r) => ({ ...r, ok: r.test(password) }));
  const passwordValid = passwordChecks.every((c) => c.ok);

  const submit = async () => {
    if (!nombre.trim() || !apellido.trim() || !email.trim()) {
      return setError('Completa tu nombre, apellido y correo.');
    }
    if (!passwordValid) return setError('Tu contraseña todavía no cumple los requisitos de seguridad.');
    if (password !== confirmPassword) return setError('Las contraseñas no coinciden.');
    if (policyDecision !== 'accepted') return setError('Debes leer y aceptar la política de protección de datos.');

    setError(null);
    setLoading(true);
    try {
      await register({
        email: email.trim(), password, nombre: nombre.trim(), apellido: apellido.trim(),
        acceptPolicy: true,
      });
      // No navegamos manualmente: AppNavigator detecta que el perfil médico
      // todavía está incompleto y muestra CompleteProfileScreen automático.
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
          <Text style={s.title}>Crea tu cuenta</Text>
          <Text style={s.subtitle}>Tu información queda separada de la de cualquier otro usuario.</Text>

          <View style={s.card}>
            {error && (
              <View style={s.errorBox}>
                <CircleAlert size={14} color="#9B1C1C" />
                <Text style={s.errorText}>{error}</Text>
              </View>
            )}

            <View style={{ flexDirection: 'row', gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Text style={s.label}>Nombre</Text>
                <TextInput style={s.input} value={nombre} onChangeText={setNombre} placeholder="Jennifer" placeholderTextColor={P.g400} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.label}>Apellido</Text>
                <TextInput style={s.input} value={apellido} onChangeText={setApellido} placeholder="Suárez" placeholderTextColor={P.g400} />
              </View>
            </View>

            <Text style={s.label}>Correo</Text>
            <TextInput
              style={s.input}
              placeholder="tu@correo.com"
              placeholderTextColor={P.g400}
              value={email}
              onChangeText={setEmail}
              autoCapitalize="none"
              keyboardType="email-address"
            />

            <Text style={s.label}>Contraseña</Text>
            <TextInput
              style={s.input}
              placeholder="Crea una contraseña segura"
              placeholderTextColor={P.g400}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />
            {password.length > 0 && (
              <View style={s.checklist}>
                {passwordChecks.map((c) => (
                  <View key={c.label} style={s.checkRow}>
                    <View style={[s.checkDot, c.ok && s.checkDotOk]}>
                      {c.ok && <Check size={9} color="white" />}
                    </View>
                    <Text style={[s.checkLabel, c.ok && s.checkLabelOk]}>{c.label}</Text>
                  </View>
                ))}
              </View>
            )}

            <Text style={s.label}>Confirma tu contraseña</Text>
            <TextInput
              style={s.input}
              placeholder="Escríbela de nuevo"
              placeholderTextColor={P.g400}
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry
            />
            {confirmPassword.length > 0 && confirmPassword !== password && (
              <Text style={s.mismatchText}>Las contraseñas no coinciden todavía.</Text>
            )}

            <TouchableOpacity style={s.policyRow} onPress={() => setPolicyModalOpen(true)}>
              <View style={[
                s.checkbox,
                policyDecision === 'accepted' && s.checkboxChecked,
                policyDecision === 'declined' && s.checkboxDeclined,
              ]}>
                {policyDecision === 'accepted' && <Check size={13} color="white" />}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.policyText}>
                  {policyDecision === 'accepted'
                    ? 'Aceptaste la política de protección de datos.'
                    : policyDecision === 'declined'
                    ? 'Rechazaste la política — no puedes crear la cuenta sin aceptarla.'
                    : 'Debes leer la política de protección de datos.'}
                </Text>
                <View style={s.policyLinkRow}>
                  <ShieldCheck size={12} color={P.navy} />
                  <Text style={s.policyLink}>
                    {policyDecision ? 'Volver a leerla' : 'Leer la política'}
                  </Text>
                </View>
              </View>
            </TouchableOpacity>

            <TouchableOpacity style={s.submitBtn} onPress={submit} disabled={loading}>
              {loading ? <ActivityIndicator color="white" /> : <Text style={s.submitText}>Crear cuenta</Text>}
            </TouchableOpacity>

            <TouchableOpacity style={s.linkRow} onPress={() => navigation.navigate('Login')}>
              <Text style={s.linkText}>¿Ya tienes cuenta? <Text style={s.linkStrong}>Inicia sesión</Text></Text>
            </TouchableOpacity>
          </View>
        </KeyboardAwareScroll>
      </KeyboardAvoidingView>

      <PolicyModal
        visible={policyModalOpen}
        onClose={() => setPolicyModalOpen(false)}
        onAccept={() => { setPolicyDecision('accepted'); setPolicyModalOpen(false); }}
        onDecline={() => { setPolicyDecision('declined'); setPolicyModalOpen(false); }}
      />
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
  checklist:  { marginTop: 8, gap: 4 },
  checkRow:   { flexDirection: 'row', alignItems: 'center', gap: 7 },
  checkDot:   { width: 15, height: 15, borderRadius: 8, borderWidth: 1.5, borderColor: P.g100, alignItems: 'center', justifyContent: 'center' },
  checkDotOk: { backgroundColor: '#1E6B3A', borderColor: '#1E6B3A' },
  checkLabel: { fontSize: 11, color: P.g400 },
  checkLabelOk: { color: '#1E6B3A', fontWeight: '600' },
  mismatchText: { fontSize: 11, color: '#9B1C1C', marginTop: 4 },
  policyRow:  { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginTop: 20, padding: 12, borderRadius: 14, backgroundColor: P.bg },
  checkbox:   { width: 20, height: 20, borderRadius: 6, borderWidth: 1.5, borderColor: P.g400, alignItems: 'center', justifyContent: 'center', marginTop: 1, backgroundColor: 'white' },
  checkboxChecked: { backgroundColor: '#1E6B3A', borderColor: '#1E6B3A' },
  checkboxDeclined: { borderColor: '#9B1C1C' },
  policyText: { fontSize: 12, color: P.g400, lineHeight: 17 },
  policyLinkRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 4 },
  policyLink: { fontSize: 12, fontWeight: '700', color: P.navy },
  submitBtn:  { marginTop: 18, backgroundColor: P.navy, borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  submitText: { color: 'white', fontWeight: '700', fontSize: 14 },
  linkRow:    { marginTop: 14, alignItems: 'center' },
  linkText:   { fontSize: 12, color: P.g400 },
  linkStrong: { color: P.navy, fontWeight: '700' },
  errorBox:   { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 10, backgroundColor: '#FDE2E2', marginBottom: 6 },
  errorText:  { flex: 1, fontSize: 12, color: '#9B1C1C' },
});
