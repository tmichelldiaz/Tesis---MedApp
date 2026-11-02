import React, { useCallback, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { ArrowLeft, ArrowUpRight, ArrowDown, Minus, BrainCircuit, FileText } from 'lucide-react-native';
import { useFocusEffect } from '@react-navigation/native';
import { listValues, getExamSummary, listDocuments } from '../services/api';
import { inRange, trendOf, evolutionOf, verdictLabel, summaryText, sortByRecency, unitSuffix } from '../utils/labValues';
import { shortExamName, formatExamName } from '../utils/examNames';
import { explainExam } from '../utils/examInfo';
import { iconForExam, softColorForExam } from '../utils/examIcons';
import TrendChart from '../components/TrendChart';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g200: '#94A3B8', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

function formatDate(iso) {
  if (!iso) return 'Sin fecha';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' });
}

export default function ExamDetailScreen({ route, navigation }) {
  const { examName } = route.params;
  const [history, setHistory] = useState(null);
  const [error, setError] = useState(null);
  const [aiSummary, setAiSummary] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiDone, setAiDone] = useState(false); // ya se intentó el resumen con IA (con o sin éxito)

  useFocusEffect(useCallback(() => {
    let active = true;
    // /values filtra por substring en el backend; aquí se necesita el mismo
    // examen exacto que se agrupó en el Dashboard, así que se filtra en el
    // cliente por coincidencia exacta (insensible a mayúsculas) en vez de
    // confiar en el substring del backend, que podría mezclar exámenes de
    // nombre parecido pero distinto (ej. "Glucosa" vs "Glucosa en ayunas").
    Promise.all([listValues(), listDocuments().catch(() => [])])
      .then(([rows, docs]) => {
        if (!active) return;
        const createdAt = Object.fromEntries(docs.map((d) => [d.id, d.created_at || '']));
        const matching = rows.filter((r) => r.exam.toLowerCase() === examName.toLowerCase());
        setHistory(sortByRecency(matching, createdAt));
      })
      .catch((e) => active && setError(e.message));
    // Resumen con IA: si el servidor lo tiene apagado o falla, se queda la
    // explicación general que ya está en pantalla; nunca se muestra un error.
    setAiLoading(true);
    setAiDone(false);
    getExamSummary(examName)
      .then((r) => active && setAiSummary(r?.summary || null))
      .catch(() => {})
      .finally(() => {
        if (!active) return;
        setAiLoading(false);
        setAiDone(true);
      });
    return () => { active = false; };
  }, [examName]));

  const Icon = iconForExam(examName);
  // Mismo color que tenía la tarjeta en el inicio (llega por parámetro).
  const color = route.params.tone || softColorForExam(examName);
  const latest = history?.[history.length - 1];
  const previous = history && history.length > 1 ? history[history.length - 2] : null;
  const trend = latest ? trendOf(latest, previous) : null;
  const status = latest ? inRange(latest) : null;
  const evolution = history ? evolutionOf(history) : null;
  const shortName = shortExamName(examName);
  const explanation = explainExam(shortName, examName);
  const result = history && history.length > 0 ? summaryText(history) : '';

  // El mensaje que abre el chat es una pregunta natural, como la escribiría el
  // paciente, y NO lleva el valor ni el rango: así el asistente tiene que
  // buscar el dato en el historial (la misma búsqueda que usa cuando el
  // paciente pregunta con sus palabras) y se comprueba que siempre lo encuentre.
  const askAI = () => {
    navigation.navigate('Tabs', {
      screen: 'Chat',
      params: {
        prefillQuestion: `Explícame con más detalle mi resultado de ${shortName}: qué mide, qué significa mi valor y cómo ha cambiado.`,
      },
    });
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: P.white }}>
      <ScrollView style={{ flex: 1, backgroundColor: P.bg }} showsVerticalScrollIndicator={false}>
        <View style={s.header}>
          <TouchableOpacity style={s.backBtn} onPress={() => navigation.goBack()}>
            <ArrowLeft size={18} color="white" />
          </TouchableOpacity>
          <View style={[s.iconCircle, { backgroundColor: color.bg }]}>
            <Icon size={26} color={color.fg} />
          </View>
          <Text style={s.examName}>{shortName}</Text>
          {shortName !== formatExamName(examName) && <Text style={s.fullName}>{formatExamName(examName)}</Text>}
        </View>

        <View style={{ padding: 16, gap: 16 }}>
          {error && (
            <View style={s.errorBox}><Text style={s.errorText}>{error}</Text></View>
          )}

          {history === null && !error && (
            <ActivityIndicator color={P.navy} style={{ marginTop: 20 }} />
          )}

          {latest && (
            <View style={s.currentCard}>
              <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 6 }}>
                <Text style={s.currentValue}>{latest.value_raw}</Text>
                <Text style={s.currentUnit}>{unitSuffix(latest.value_raw, latest.unit)}</Text>
                {trend === 'up' && <ArrowUpRight size={18} color={P.g400} />}
                {trend === 'down' && <ArrowDown size={18} color={P.g400} />}
                {trend === 'same' && <Minus size={18} color={P.g400} />}
              </View>
              <Text style={s.currentDate}>Último resultado: {formatDate(latest.date)}</Text>
              <View style={s.chipRow}>
                {status !== null && (
                  <View style={[s.badge, { backgroundColor: status ? P.light : P.accent }]}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: status ? P.navy : '#7A1F3D' }}>
                      {status ? 'En rango' : 'Fuera de rango'}
                    </Text>
                  </View>
                )}
                {evolution && (
                  <View style={[s.badge, { backgroundColor: evolution.verdict === 'worse' ? P.accent : evolution.verdict === 'better' ? P.light : P.g100 }]}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: evolution.verdict === 'worse' ? '#7A1F3D' : P.navy }}>
                      {verdictLabel(evolution.verdict)}
                    </Text>
                  </View>
                )}
              </View>
            </View>
          )}

          {history && history.length > 0 && (
            <View style={[s.card, s.chartShadow]}>
              <Text style={s.sectionTitle}>Evolución</Text>
              <TrendChart points={history} />
            </View>
          )}

          {(!!explanation || !!result || !!aiSummary) && (
            <View style={s.card}>
              <View style={s.summaryHead}>
                <FileText size={16} color={P.navy} />
                <Text style={[s.sectionTitle, { marginBottom: 0 }]}>Resumen</Text>
              </View>
              {!aiSummary && !aiDone ? (
                // Mientras llega el resumen no se muestra otro texto: así no aparece uno genérico y luego cambia.
                <View style={s.summaryWaiting}>
                  <ActivityIndicator size="small" color={P.navy} />
                  <Text style={s.summaryNote}>Preparando tu resumen...</Text>
                </View>
              ) : aiSummary ? (
                <>
                  <Text style={s.summaryText}>{aiSummary}</Text>
                  <Text style={s.summaryNote}>
                    Resumen generado con IA a partir de tus resultados. Puede contener errores y no reemplaza la valoración de tu médico.
                  </Text>
                </>
              ) : (
                <>
                  {!!explanation && (
                    <>
                      <Text style={s.summaryLabel}>Qué es</Text>
                      <Text style={s.summaryText}>{explanation}</Text>
                    </>
                  )}
                  {!!result && (
                    <>
                      <Text style={[s.summaryLabel, !!explanation && { marginTop: 12 }]}>Tu resultado</Text>
                      <Text style={s.summaryText}>{result}</Text>
                    </>
                  )}
                  <Text style={s.summaryNote}>
                    Información general con tus propios datos. No reemplaza la valoración de tu médico.
                  </Text>
                </>
              )}
            </View>
          )}

          <TouchableOpacity style={s.aiCard} onPress={askAI}>
            <View style={s.aiIconBox}>
              <BrainCircuit size={20} color="white" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontWeight: '700', fontSize: 13, color: P.g800 }}>Consultar más a detalle en el chat</Text>
              <Text style={{ fontSize: 11, marginTop: 2, color: P.g400 }}>
                Pregúntale a la IA qué significa este resultado para ti.
              </Text>
            </View>
            <ArrowUpRight size={16} color={P.navy} />
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header:      { padding: 20, paddingTop: 44, paddingBottom: 24, backgroundColor: P.navy, borderBottomLeftRadius: 28, borderBottomRightRadius: 28, alignItems: 'center', gap: 10 },
  backBtn:     { position: 'absolute', top: 44, left: 20, width: 36, height: 36, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' },
  iconCircle:  { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  fullName:    { fontSize: 11, color: 'rgba(255,255,255,0.7)', textAlign: 'center', paddingHorizontal: 30, lineHeight: 15 },
  chipRow:     { flexDirection: 'row', gap: 8, flexWrap: 'wrap', justifyContent: 'center' },
  summaryHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  summaryLabel:{ fontSize: 11, fontWeight: '700', color: P.g400, letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 3 },
  summaryWaiting: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6 },
  summaryText: { fontSize: 14, lineHeight: 21, color: P.g800 },
  summaryNote: { fontSize: 11, lineHeight: 15, color: P.g400, marginTop: 10 },
  examName:    { fontSize: 20, fontWeight: '700', color: 'white', textAlign: 'center', paddingHorizontal: 30 },
  card:        { borderRadius: 20, padding: 16, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 12, elevation: 2 },
  chartShadow: { shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.14, shadowRadius: 16, elevation: 8 },
  currentCard: { borderRadius: 20, padding: 18, alignItems: 'center', gap: 6, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 12, elevation: 2 },
  currentValue:{ fontSize: 34, fontWeight: '900', color: P.g800 },
  currentUnit: { fontSize: 14, color: P.g400, marginBottom: 6 },
  currentDate: { fontSize: 12, color: P.g400 },
  badge:       { marginTop: 4, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  sectionTitle:{ fontSize: 14, fontWeight: '700', color: P.g800, marginBottom: 10 },
  aiCard:      { borderRadius: 20, padding: 16, flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 12, elevation: 2 },
  aiIconBox:   { width: 40, height: 40, borderRadius: 12, backgroundColor: P.navy, alignItems: 'center', justifyContent: 'center' },
  errorBox:    { padding: 12, borderRadius: 14, backgroundColor: '#FDE2E2' },
  errorText:   { fontSize: 12, color: '#9B1C1C' },
});
