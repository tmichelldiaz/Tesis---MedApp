import React from 'react';
import { View, Text, TouchableOpacity, Modal, Pressable, StyleSheet } from 'react-native';
import { Check } from 'lucide-react-native';
import { CATEGORIES, CATEGORY_STYLE } from '../constants/categories';

const P = {
  navy: '#034AA6', g100: '#E2E8F0', g200: '#94A3B8', g800: '#02204A', white: '#FFFFFF', bg: '#F4FAE9',
};

export default function CategoryPickerModal({ visible, current, onClose, onSelect }) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={s.overlay} onPress={onClose}>
        <Pressable style={s.sheet}>
          <Text style={s.title}>Elegir categoría</Text>
          {CATEGORIES.map((cat) => {
            const style = CATEGORY_STYLE[cat];
            const Icon = style.icon;
            return (
              <TouchableOpacity key={cat} style={s.row} onPress={() => onSelect(cat)}>
                <View style={[s.iconBadge, { backgroundColor: style.bg }]}>
                  <Icon size={16} color={style.fg} />
                </View>
                <Text style={[s.rowText, cat === current && s.rowTextSelected]}>{cat}</Text>
                {cat === current && <Check size={16} color={P.navy} />}
              </TouchableOpacity>
            );
          })}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay:  { flex: 1, backgroundColor: 'rgba(2,32,74,0.4)', alignItems: 'center', justifyContent: 'center' },
  sheet:    { width: 300, backgroundColor: P.white, borderRadius: 20, padding: 16, gap: 4 },
  title:    { fontSize: 14, fontWeight: '700', color: P.g800, marginBottom: 8 },
  row:      { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, paddingHorizontal: 10, borderRadius: 12 },
  iconBadge:{ width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  rowText:  { flex: 1, fontSize: 13, color: P.g800 },
  rowTextSelected: { fontWeight: '700', color: P.navy },
});
