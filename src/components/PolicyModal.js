import React, { useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, Modal, ScrollView, StyleSheet, SafeAreaView,
} from 'react-native';
import { ShieldCheck, Check, X, AlertTriangle } from 'lucide-react-native';
import { POLICY_SECTIONS, POLICY_VERSION, POLICY_UPDATED_AT } from '../constants/policyContent';

const P = {
  navy: '#034AA6', light: '#C2D7F2', bg: '#F4FAE9', white: '#FFFFFF',
  g100: '#E2E8F0', g200: '#94A3B8', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

function Block({ block }) {
  switch (block.type) {
    case 'p':
      return <Text style={s.p}>{block.text}</Text>;
    case 'subheading':
      return <Text style={s.subheading}>{block.text}</Text>;
    case 'list':
      return (
        <View style={s.list}>
          {block.items.map((item, i) => (
            <View key={i} style={s.listRow}>
              <Text style={s.bullet}>{'•'}</Text>
              <Text style={s.listText}>{item}</Text>
            </View>
          ))}
        </View>
      );
    case 'ol':
      return (
        <View style={s.list}>
          {block.items.map((item, i) => (
            <View key={i} style={s.listRow}>
              <Text style={s.olNumber}>{i + 1}.</Text>
              <Text style={s.listText}>{item}</Text>
            </View>
          ))}
        </View>
      );
    case 'pairs':
      return (
        <View style={s.table}>
          {block.rows.map(([k, v], i) => (
            <View key={i} style={[s.tableRow, i === block.rows.length - 1 && { borderBottomWidth: 0 }]}>
              <Text style={s.tableKey}>{k}</Text>
              <Text style={s.tableValue}>{v}</Text>
            </View>
          ))}
        </View>
      );
    case 'callout':
      return (
        <View style={s.callout}>
          <View style={s.calloutHeader}>
            <AlertTriangle size={14} color={P.navy} />
            {block.title ? <Text style={s.calloutTitle}>{block.title}</Text> : null}
          </View>
          <Text style={s.calloutText}>{block.text}</Text>
        </View>
      );
    default:
      return null;
  }
}

export default function PolicyModal({ visible, onAccept, onDecline, onClose, readOnly = false }) {
  const scrollRef = useRef(null);
  const [reachedEnd, setReachedEnd] = useState(false);

  const handleScroll = ({ nativeEvent }) => {
    if (reachedEnd) return;
    const { layoutMeasurement, contentOffset, contentSize } = nativeEvent;
    if (layoutMeasurement.height + contentOffset.y >= contentSize.height - 40) {
      setReachedEnd(true);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={s.screen}>
        <View style={s.header}>
          <View style={s.headerLeft}>
            <ShieldCheck size={18} color={P.navy} />
            <Text style={s.headerTitle}>Política de Protección de Datos</Text>
          </View>
          <TouchableOpacity onPress={onClose} style={s.closeBtn}>
            <X size={16} color={P.g800} />
          </TouchableOpacity>
        </View>
        <Text style={s.headerMeta}>Versión {POLICY_VERSION} · Actualizada el {POLICY_UPDATED_AT}</Text>

        <ScrollView
          ref={scrollRef}
          style={s.body}
          contentContainerStyle={s.bodyContent}
          onScroll={handleScroll}
          scrollEventThrottle={100}
          showsVerticalScrollIndicator
        >
          <Text style={s.docTitle}>
            Política Integral de Protección de Datos Personales, Privacidad Médica y Tratamiento
            de Información Clínica Sensible de MedApp
          </Text>
          <Text style={s.docSubtitle}>
            {readOnly ? 'Documento completo de referencia.' : 'Lee el documento completo antes de aceptar o rechazar.'}
          </Text>

          {POLICY_SECTIONS.map((section) => (
            <View key={section.id} style={s.section}>
              <Text style={s.sectionTitle}>{section.title}</Text>
              {section.blocks.map((block, i) => (
                <Block key={i} block={block} />
              ))}
            </View>
          ))}
        </ScrollView>

        {!readOnly && !reachedEnd && (
          <Text style={s.scrollHint}>Desplázate hasta el final para poder aceptar o rechazar.</Text>
        )}

        {readOnly ? (
          <View style={s.actionsRow}>
            <TouchableOpacity style={s.acceptBtn} onPress={onClose}>
              <Text style={s.acceptText}>Cerrar</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={s.actionsRow}>
            <TouchableOpacity style={s.declineBtn} onPress={onDecline}>
              <Text style={s.declineText}>No acepto</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[s.acceptBtn, !reachedEnd && s.acceptBtnDisabled]}
              onPress={reachedEnd ? onAccept : undefined}
              disabled={!reachedEnd}
            >
              <Check size={15} color="white" />
              <Text style={s.acceptText}>Acepto</Text>
            </TouchableOpacity>
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
}

const s = StyleSheet.create({
  screen:     { flex: 1, backgroundColor: P.white },
  header:     { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingTop: 14 },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1, marginRight: 10 },
  headerTitle:{ fontSize: 15, fontWeight: '700', color: P.g800, flexShrink: 1 },
  closeBtn:   { width: 30, height: 30, borderRadius: 10, backgroundColor: P.bg, alignItems: 'center', justifyContent: 'center' },
  headerMeta: { fontSize: 11, color: P.g400, paddingHorizontal: 20, marginTop: 4, marginBottom: 10 },

  body:        { flex: 1, borderTopWidth: 1, borderTopColor: P.g100 },
  bodyContent: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 24 },

  docTitle:    { fontSize: 16, fontWeight: '800', color: P.g800, lineHeight: 22, marginBottom: 6 },
  docSubtitle: { fontSize: 12, color: P.g400, marginBottom: 18 },

  section:      { marginBottom: 22 },
  sectionTitle: { fontSize: 14, fontWeight: '800', color: P.navy, marginBottom: 8 },
  subheading:   { fontSize: 12.5, fontWeight: '700', color: P.g800, marginTop: 10, marginBottom: 4 },
  p:            { fontSize: 12.5, color: P.g400, lineHeight: 19, marginBottom: 8 },

  list:     { marginBottom: 8 },
  listRow:  { flexDirection: 'row', marginBottom: 5, paddingRight: 4 },
  bullet:   { fontSize: 12.5, color: P.navy, width: 14 },
  olNumber: { fontSize: 12.5, color: P.navy, fontWeight: '700', width: 20 },
  listText: { flex: 1, fontSize: 12.5, color: P.g400, lineHeight: 19 },

  table:      { borderWidth: 1, borderColor: P.g100, borderRadius: 12, overflow: 'hidden', marginBottom: 10 },
  tableRow:   { padding: 10, borderBottomWidth: 1, borderBottomColor: P.g100, gap: 2 },
  tableKey:   { fontSize: 11.5, fontWeight: '700', color: P.g800 },
  tableValue: { fontSize: 12, color: P.g400, lineHeight: 17 },

  callout:       { backgroundColor: P.bg, borderRadius: 12, borderWidth: 1, borderColor: P.light, padding: 12, marginBottom: 10 },
  calloutHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 5 },
  calloutTitle:  { fontSize: 12, fontWeight: '800', color: P.navy },
  calloutText:   { fontSize: 12, color: P.g800, lineHeight: 18 },

  scrollHint: { fontSize: 11, color: P.g400, textAlign: 'center', paddingTop: 6 },

  actionsRow: { flexDirection: 'row', gap: 10, paddingHorizontal: 20, paddingTop: 10, paddingBottom: 16 },
  declineBtn: { flex: 1, paddingVertical: 13, borderRadius: 14, backgroundColor: P.bg, alignItems: 'center' },
  declineText:{ fontSize: 13, fontWeight: '700', color: P.g400 },
  acceptBtn:  { flex: 1, flexDirection: 'row', gap: 6, paddingVertical: 13, borderRadius: 14, backgroundColor: P.navy, alignItems: 'center', justifyContent: 'center' },
  acceptBtnDisabled: { backgroundColor: P.g100 },
  acceptText: { fontSize: 13, fontWeight: '700', color: 'white' },
});
