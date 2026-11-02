import React, { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Modal, Pressable,
  StyleSheet, ActivityIndicator, ScrollView, KeyboardAvoidingView, Platform,
} from 'react-native';
import KeyboardAwareScroll from './KeyboardAwareScroll';
import { X } from 'lucide-react-native';
import DateTimeField from './DateTimeField';
import { updateProfile } from '../services/api';

const P = {
  navy: '#034AA6', light: '#C2D7F2', bg: '#F4FAE9', white: '#FFFFFF',
  g100: '#E2E8F0', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

const BLOOD_TYPES = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
const SEX_OPTIONS = ['Femenino', 'Masculino', 'Prefiero no decir'];

function toDate(isoDate) {
  if (!isoDate) return null;
  const [y, m, d] = isoDate.split('-').map(Number);
  return new Date(y, m - 1, d);
}

function toIsoDate(date) {
  const pad2 = (n) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())}`;
}

export default function ProfileEditModal({ visible, profile, onClose, onSaved }) {
  const [name, setName] = useState('');
  const [birthDate, setBirthDate] = useState(null);
  const [sex, setSex] = useState(null);
  const [weight, setWeight] = useState('');
  const [bloodType, setBloodType] = useState(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!visible) return;
    setName(profile?.name || '');
    setBirthDate(toDate(profile?.birth_date));
    setSex(profile?.sex || null);
    setWeight(profile?.weight_kg != null ? String(profile.weight_kg) : '');
    setBloodType(profile?.blood_type || null);
    setError(null);
  }, [visible, profile]);

  const save = async () => {
    if (!name.trim()) return setError('Ponle tu nombre.');
    const weightNum = weight.trim() ? Number(weight.replace(',', '.')) : null;
    if (weight.trim() && (Number.isNaN(weightNum) || weightNum <= 0)) {
      return setError('El peso debe ser un número positivo.');
    }
    setSaving(true);
    setError(null);
    try {
      const updated = await updateProfile({
        name: name.trim(),
        birth_date: birthDate ? toIsoDate(birthDate) : null,
        sex,
        weight_kg: weightNum,
        blood_type: bloodType,
      });
      onSaved(updated);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.overlay} onPress={onClose}>
        <KeyboardAvoidingView behavior="padding">
          <Pressable style={s.sheet}>
            <View style={s.header}>
              <Text style={s.title}>Tu información</Text>
              <TouchableOpacity onPress={onClose} style={s.closeBtn}>
                <X size={18} color={P.g800} />
              </TouchableOpacity>
            </View>

            <KeyboardAwareScroll showsVerticalScrollIndicator={false} style={{ maxHeight: 420 }}>
              <View style={{ gap: 10 }}>
                {error && (
                  <View style={s.errorBox}>
                    <Text style={s.errorText}>{error}</Text>
                  </View>
                )}

                <Text style={s.label}>Nombre</Text>
                <TextInput
                  style={s.input}
                  placeholder="¿Cómo te llamas?"
                  placeholderTextColor={P.g400}
                  value={name}
                  onChangeText={setName}
                />

                <Text style={s.label}>Fecha de nacimiento</Text>
                <DateTimeField mode="date" placeholder="Elige tu fecha de nacimiento" value={birthDate} onChange={setBirthDate} />

                <Text style={s.label}>Sexo</Text>
                <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                  {SEX_OPTIONS.map((opt) => (
                    <TouchableOpacity
                      key={opt}
                      style={[s.chip, sex === opt && s.chipSelected]}
                      onPress={() => setSex(opt === sex ? null : opt)}>
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
                      onPress={() => setBloodType(bt === bloodType ? null : bt)}>
                      <Text style={[s.chipText, bloodType === bt && s.chipTextSelected]}>{bt}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </KeyboardAwareScroll>

            <TouchableOpacity style={s.saveBtn} onPress={save} disabled={saving}>
              {saving ? <ActivityIndicator color="white" /> : <Text style={s.saveBtnText}>Guardar</Text>}
            </TouchableOpacity>
          </Pressable>
        </KeyboardAvoidingView>
      </Pressable>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay:    { flex: 1, backgroundColor: 'rgba(2,32,74,0.4)', justifyContent: 'flex-end' },
  sheet:      { backgroundColor: P.white, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 20, paddingBottom: 30 },
  header:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  title:      { fontSize: 16, fontWeight: '700', color: P.g800 },
  closeBtn:   { width: 32, height: 32, borderRadius: 10, backgroundColor: P.bg, alignItems: 'center', justifyContent: 'center' },
  label:      { fontSize: 12, fontWeight: '600', color: P.g400, marginTop: 2 },
  input:      { borderWidth: 1, borderColor: P.g100, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, fontSize: 13, color: P.g800 },
  chip:       { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: P.bg, borderWidth: 1, borderColor: P.g100 },
  chipSelected:{ backgroundColor: P.navy, borderColor: P.navy },
  chipText:   { fontSize: 12, fontWeight: '700', color: P.g800 },
  chipTextSelected:{ color: 'white' },
  saveBtn:    { marginTop: 16, paddingVertical: 13, borderRadius: 12, backgroundColor: P.navy, alignItems: 'center' },
  saveBtnText:{ color: 'white', fontWeight: '700', fontSize: 13 },
  errorBox:   { padding: 10, borderRadius: 10, backgroundColor: '#FDE2E2' },
  errorText:  { fontSize: 12, color: '#9B1C1C' },
});
