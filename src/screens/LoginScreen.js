import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  SafeAreaView, ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import KeyboardAwareScroll from '../components/KeyboardAwareScroll';
import { HeartPulse, CircleAlert } from 'lucide-react-native';
import { useAuth } from '../context/AuthContext';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g200: '#94A3B8', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

export default function LoginScreen({ navigation }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const submit = async () => {
    if (!email.trim() || !password) return setError('Escribe tu correo y contraseña.');
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      // Al confirmarse el login, AuthContext actualiza el token/usuario y el
      // navegador raíz cambia de pantalla solo — no hace falta navegar aquí.
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
          contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: 24 }}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag">
          <View style={s.logoBox}>
            <HeartPulse size={30} color="white" />
          </View>
          <Text style={s.title}>MedApp</Text>
          <Text style={s.subtitle}>Tu historial médico, siempre a la mano.</Text>

          <View style={s.card}>
            <Text style={s.cardTitle}>Iniciar sesión</Text>

            {error && (
              <View style={s.errorBox}>
                <CircleAlert size={14} color="#9B1C1C" />
                <Text style={s.errorText}>{error}</Text>
              </View>
            )}

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
              placeholder="••••••••"
              placeholderTextColor={P.g400}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
            />

            <TouchableOpacity style={s.submitBtn} onPress={submit} disabled={loading}>
              {loading ? <ActivityIndicator color="white" /> : <Text style={s.submitText}>Entrar</Text>}
            </TouchableOpacity>

            <TouchableOpacity style={s.linkRow} onPress={() => navigation.navigate('Register')}>
              <Text style={s.linkText}>¿No tienes cuenta? <Text style={s.linkStrong}>Regístrate</Text></Text>
            </TouchableOpacity>
          </View>
        </KeyboardAwareScroll>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  logoBox:    { width: 64, height: 64, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center', alignSelf: 'center', marginBottom: 14 },
  title:      { fontSize: 26, fontWeight: '700', color: 'white', textAlign: 'center' },
  subtitle:   { fontSize: 13, color: 'rgba(255,255,255,0.7)', textAlign: 'center', marginTop: 4, marginBottom: 28 },
  card:       { backgroundColor: P.white, borderRadius: 24, padding: 22, gap: 4 },
  cardTitle:  { fontSize: 16, fontWeight: '700', color: P.g800, marginBottom: 10 },
  label:      { fontSize: 11, fontWeight: '700', color: P.g400, marginTop: 10, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 },
  input:      { borderWidth: 1, borderColor: P.g100, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 12, fontSize: 14, color: P.g800 },
  submitBtn:  { marginTop: 20, backgroundColor: P.navy, borderRadius: 14, paddingVertical: 14, alignItems: 'center' },
  submitText: { color: 'white', fontWeight: '700', fontSize: 14 },
  linkRow:    { marginTop: 16, alignItems: 'center' },
  linkText:   { fontSize: 12, color: P.g400 },
  linkStrong: { color: P.navy, fontWeight: '700' },
  errorBox:   { flexDirection: 'row', alignItems: 'center', gap: 6, padding: 10, borderRadius: 10, backgroundColor: '#FDE2E2', marginBottom: 6 },
  errorText:  { flex: 1, fontSize: 12, color: '#9B1C1C' },
});
