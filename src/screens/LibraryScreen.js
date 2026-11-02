import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput,
  StyleSheet, SafeAreaView, ActivityIndicator,
} from 'react-native';
import {
  FileText, Search, X, ChevronDown, ChevronUp, Plus,
  CircleCheck, CircleAlert, RefreshCw, Trash2, Pencil, FolderOpen,
  MessageCircle, LineChart,
} from 'lucide-react-native';
import { useNavigation, useFocusEffect } from '@react-navigation/native';
import { confirmAction } from '../utils/confirm';
import {
  listDocuments, retryDocument, deleteDocument, setDocumentCategory,
} from '../services/api';
import { CATEGORIES, UNCLASSIFIED, CATEGORY_STYLE } from '../constants/categories';
import CategoryPickerModal from '../components/CategoryPickerModal';
import { withUnit, cleanValueRaw } from '../utils/labValues';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g200: '#94A3B8', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

const STATUS = {
  processing: { label: 'PROCESANDO', bg: P.light, fg: P.navy },
  ready: { label: 'LISTO', bg: '#DDF3E4', fg: '#1E6B3A' },
  failed: { label: 'ERROR', bg: '#FDE2E2', fg: '#9B1C1C' },
};

const formatDate = (iso) =>
  new Date(iso).toLocaleString('es-ES', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  });

// La búsqueda ya no mira dentro del bundle OKF (el paciente no ve esos
// nombres de sección técnicos) — solo el nombre del archivo.
const matches = (doc, query) => doc.filename.toLowerCase().includes(query.toLowerCase());

// Mes en que se subió el archivo, para agrupar la lista ("Octubre 2026").
const monthKey = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? 'sin-fecha' : `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};
const monthLabel = (iso) => {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Sin fecha';
  const text = d.toLocaleDateString('es-ES', { month: 'long', year: 'numeric' });
  return text.charAt(0).toUpperCase() + text.slice(1);
};

const countLabel = (n) => (n > 0 ? `${n} ${n === 1 ? 'archivo' : 'archivos'}` : 'Sin archivos');

export default function LibraryScreen() {
  const navigation = useNavigation();
  const [docs, setDocs] = useState([]);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState('');
  const [openId, setOpenId] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [pickingCategoryFor, setPickingCategoryFor] = useState(null);
  const [listOpen, setListOpen] = useState(true); // "Todos los archivos" se puede ocultar de una vez
  const [closedMonths, setClosedMonths] = useState({}); // meses que el paciente ocultó
  const [valuesOpen, setValuesOpen] = useState({}); // historias con la lista de valores desplegada

  const refresh = useCallback(async () => {
    try {
      setDocs(await listDocuments());
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useFocusEffect(useCallback(() => { refresh(); }, [refresh]));

  const hasProcessing = docs.some((d) => d.status === 'processing');
  useEffect(() => {
    if (!hasProcessing) return undefined;
    const timer = setInterval(refresh, 3000);
    return () => clearInterval(timer);
  }, [hasProcessing, refresh]);

  const retry = async (id) => {
    try {
      const updated = await retryDocument(id);
      setDocs((current) => current.map((d) => (d.id === id ? updated : d)));
    } catch (e) {
      setError(e.message);
    }
  };

  const remove = async (id, filename) => {
    const ok = await confirmAction(
      '¿Eliminar esta historia?',
      `Se borrarán "${filename || 'el archivo'}" y los resultados que salieron de él. No se puede deshacer.`,
    );
    if (!ok) return;
    try {
      await deleteDocument(id);
      setDocs((current) => current.filter((d) => d.id !== id));
      if (openId === id) setOpenId(null);
    } catch (e) {
      setError(e.message);
    }
  };

  const changeCategory = async (docId, category) => {
    setPickingCategoryFor(null);
    try {
      const updated = await setDocumentCategory(docId, category);
      setDocs((current) => current.map((d) => (d.id === docId ? updated : d)));
    } catch (e) {
      setError(e.message);
    }
  };

  const counts = {};
  for (const doc of docs) {
    const key = doc.category || UNCLASSIFIED;
    counts[key] = (counts[key] || 0) + 1;
  }

  const searched = search ? docs.filter((d) => matches(d, search)) : docs;
  const results = selectedCategory
    ? searched.filter((d) => (d.category || UNCLASSIFIED) === selectedCategory)
    : searched;
  // Más recientes primero, agrupados por el mes en que se subieron.
  const months = [];
  const byKey = {};
  for (const doc of [...results].sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)))) {
    const key = monthKey(doc.created_at);
    if (!byKey[key]) {
      byKey[key] = { key, label: monthLabel(doc.created_at), docs: [] };
      months.push(byKey[key]);
    }
    byKey[key].docs.push(doc);
  }
  const toggleMonth = (key) => setClosedMonths((current) => ({ ...current, [key]: !current[key] }));

  const readyCount = docs.length ? docs.filter((d) => d.status === 'ready').length : 0;
  const totalMb = docs.reduce((sum, d) => sum + (d.size || 0), 0) / (1024 * 1024);

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: P.white }}>
      <ScrollView style={{ flex: 1, backgroundColor: P.bg }} showsVerticalScrollIndicator={false}>

        <View style={s.header}>
          <Text style={s.title}>Biblioteca</Text>
          <Text style={s.subtitle}>Todo tu historial médico, por categoría.</Text>

          <View style={s.searchBox}>
            <Search size={17} color="rgba(255,255,255,0.5)" />
            <TextInput
              style={s.searchInput}
              placeholder="Buscar por nombre o contenido..."
              placeholderTextColor="rgba(255,255,255,0.5)"
              value={search}
              onChangeText={(text) => { setSearch(text); setListOpen(true); }}
            />
            {search.length > 0 && (
              <TouchableOpacity onPress={() => setSearch('')}>
                <X size={15} color="rgba(255,255,255,0.6)" />
              </TouchableOpacity>
            )}
          </View>
        </View>

        <View style={{ padding: 16, gap: 18 }}>

          <View style={s.statsRow}>
            {[
              { label: 'Archivos', value: docs.length },
              { label: 'Listos', value: readyCount },
              { label: 'MB Total', value: totalMb.toFixed(1) },
            ].map(({ label, value }) => (
              <View key={label} style={s.statCard}>
                <Text style={s.statValue}>{value}</Text>
                <Text style={s.statLabel}>{label}</Text>
              </View>
            ))}
          </View>

          {error && (
            <View style={s.errorBox}>
              <CircleAlert size={16} color="#9B1C1C" />
              <Text style={s.errorText}>{error}</Text>
            </View>
          )}

          {docs.length > 0 && (
            <View style={{ gap: 10 }}>
              <Text style={s.gridTitle}>Categorías</Text>
              <View style={s.grid}>
                {CATEGORIES.map((cat) => {
                  const style = CATEGORY_STYLE[cat];
                  const Icon = style.icon;
                  const active = selectedCategory === cat;
                  return (
                    <TouchableOpacity
                      key={cat}
                      style={s.tile}
                      onPress={() => { setSelectedCategory(active ? null : cat); setListOpen(true); }}>
                      <View style={[
                        s.tileIconBox,
                        { backgroundColor: active ? style.fg : style.bg },
                        active && s.tileIconBoxActive,
                      ]}>
                        <Icon size={27} color={active ? 'white' : style.fg} />
                      </View>
                      <Text style={[s.tileLabel, active && s.tileLabelActive]} numberOfLines={1}>
                        {style.label}
                      </Text>
                      <Text style={s.tileCount}>{countLabel(counts[cat])}</Text>
                    </TouchableOpacity>
                  );
                })}
                {counts[UNCLASSIFIED] > 0 && (
                  <TouchableOpacity
                    style={s.tile}
                    onPress={() => { setSelectedCategory(selectedCategory === UNCLASSIFIED ? null : UNCLASSIFIED); setListOpen(true); }}>
                    <View style={[
                      s.tileIconBox,
                      { backgroundColor: selectedCategory === UNCLASSIFIED ? P.g400 : P.g100 },
                    ]}>
                      <FolderOpen size={27} color={selectedCategory === UNCLASSIFIED ? 'white' : P.g400} />
                    </View>
                    <Text style={[s.tileLabel, selectedCategory === UNCLASSIFIED && s.tileLabelActive]} numberOfLines={1}>
                      Sin clasificar
                    </Text>
                    <Text style={s.tileCount}>{countLabel(counts[UNCLASSIFIED])}</Text>
                  </TouchableOpacity>
                )}
              </View>
              {selectedCategory && (
                <TouchableOpacity onPress={() => setSelectedCategory(null)}>
                  <Text style={s.showAll}>Mostrar todos</Text>
                </TouchableOpacity>
              )}
            </View>
          )}

          <View style={s.sectionHeader}>
            <TouchableOpacity
              style={s.sectionToggle}
              onPress={() => setListOpen((v) => !v)}
              accessibilityLabel={listOpen ? 'Ocultar archivos' : 'Mostrar archivos'}>
              {listOpen ? <ChevronUp size={18} color={P.g400} /> : <ChevronDown size={18} color={P.g400} />}
              <Text style={s.sectionTitle}>
                {selectedCategory ? selectedCategory.toUpperCase() : 'TODOS LOS ARCHIVOS'} ({results.length})
              </Text>
            </TouchableOpacity>
            {selectedCategory && selectedCategory !== UNCLASSIFIED && (
              <TouchableOpacity
                style={s.addToSectionBtn}
                onPress={() => navigation.navigate('Upload', { presetCategory: selectedCategory })}>
                <Plus size={14} color={P.navy} />
                <Text style={s.addToSectionText}>Añadir aquí</Text>
              </TouchableOpacity>
            )}
          </View>

          {listOpen && results.length === 0 && (
            <Text style={{ textAlign: 'center', color: P.g400, marginTop: 20 }}>
              {docs.length === 0
                ? 'Aún no has subido ningún documento. Ve a la pestaña Subir.'
                : 'No se encontraron archivos.'}
            </Text>
          )}

          {listOpen && months.map((month) => {
            const monthOpen = !closedMonths[month.key];
            return (
              <View key={month.key} style={{ gap: 12 }}>
                <TouchableOpacity style={s.monthHeader} onPress={() => toggleMonth(month.key)}>
                  {monthOpen ? <ChevronUp size={15} color={P.g400} /> : <ChevronDown size={15} color={P.g400} />}
                  <Text style={s.monthTitle}>{month.label}</Text>
                  <Text style={s.monthCount}>{countLabel(month.docs.length)}</Text>
                </TouchableOpacity>
                {monthOpen && month.docs.map((doc) => {
            const st = STATUS[doc.status] || STATUS.processing;
            const open = openId === doc.id;
            // El archivo toma el color de su categoría; sin clasificar queda gris.
            const tone = CATEGORY_STYLE[doc.category] || { bg: P.g100, fg: P.g400 };
            return (
              <View key={doc.id} style={s.card}>
                <TouchableOpacity
                  style={s.fileRow}
                  onPress={() => setOpenId(open ? null : doc.id)}>
                  <View style={[s.fileIcon, { backgroundColor: doc.status === 'failed' ? '#FDE2E2' : tone.bg }]}>
                    <FileText size={24} color={doc.status === 'failed' ? '#9B1C1C' : tone.fg} />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.fileName} numberOfLines={1}>{doc.filename}</Text>
                    <Text style={s.fileDate}>{formatDate(doc.created_at)}</Text>
                  </View>
                  <View style={[s.badge, { backgroundColor: st.bg }]}>
                    {doc.status === 'processing' && (
                      <ActivityIndicator size="small" color={st.fg} style={{ marginRight: 6 }} />
                    )}
                    <Text style={[s.badgeText, { color: st.fg }]}>{st.label}</Text>
                  </View>
                  {open ? <ChevronUp size={18} color={P.g400} /> : <ChevronDown size={18} color={P.g400} />}
                </TouchableOpacity>

                {open && (
                  <View style={s.detail}>
                    {doc.status !== 'processing' && (
                      <TouchableOpacity
                        style={[s.categoryPill, { backgroundColor: tone.bg }]}
                        onPress={() => setPickingCategoryFor(doc.id)}>
                        <Text style={[s.categoryPillText, { color: tone.fg }]}>{doc.category || UNCLASSIFIED}</Text>
                        <Pencil size={11} color={tone.fg} />
                      </TouchableOpacity>
                    )}

                    {doc.status === 'ready' && doc.values_before != null && (
                      <Text style={s.detailText}>
                        Releída con el modelo nuevo: {(doc.lab_values || []).length} valores (antes {doc.values_before}).
                      </Text>
                    )}

                    {doc.status === 'ready' && (doc.lab_values || []).length > 0 && (
                      <View style={{ gap: 6 }}>
                        <TouchableOpacity
                          style={s.valuesToggle}
                          onPress={() => setValuesOpen((cur) => ({ ...cur, [doc.id]: !cur[doc.id] }))}>
                          <Text style={s.valuesToggleText}>
                            {valuesOpen[doc.id] ? 'Ocultar' : 'Ver'} los {(doc.lab_values || []).length} valores leídos
                          </Text>
                          {valuesOpen[doc.id] ? <ChevronUp size={14} color={P.navy} /> : <ChevronDown size={14} color={P.navy} />}
                        </TouchableOpacity>
                        {valuesOpen[doc.id] && (doc.lab_values || []).map((v, i) => (
                          <View key={i} style={s.valueRow}>
                            <Text style={s.valueName}>{v.exam}</Text>
                            <Text style={s.valueText}>{withUnit(cleanValueRaw(v.value_raw, v.exam), v.unit)}</Text>
                          </View>
                        ))}
                      </View>
                    )}

                    {doc.status === 'processing' && (
                      <Text style={s.detailText}>
                        Leyendo el documento con IA y armando el bundle. Puede tardar un minuto.
                      </Text>
                    )}

                    {doc.status === 'failed' && (
                      <>
                        <Text style={[s.detailText, { color: '#9B1C1C' }]}>{doc.error}</Text>
                        <View style={{ flexDirection: 'row', gap: 10 }}>
                          <TouchableOpacity style={[s.actionBtn, { flex: 1 }]} onPress={() => retry(doc.id)}>
                            <RefreshCw size={15} color={P.navy} />
                            <Text style={s.actionText}>Reintentar</Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            style={[s.actionBtn, s.deleteBtn, { flex: 1 }]}
                            onPress={() => remove(doc.id, doc.filename)}>
                            <Trash2 size={15} color="#9B1C1C" />
                            <Text style={[s.actionText, { color: '#9B1C1C' }]}>Eliminar</Text>
                          </TouchableOpacity>
                        </View>
                      </>
                    )}

                    {doc.status === 'ready' && (
                      <>
                        <View style={s.okRow}>
                          <CircleCheck size={16} color="#1E6B3A" />
                          <Text style={s.okText}>Cargado correctamente</Text>
                        </View>

                        <TouchableOpacity
                          style={s.actionBtn}
                          onPress={() => navigation.navigate('Chat', {
                            prefillQuestion: `Cuéntame qué encontraste en mi documento "${doc.filename}".`,
                          })}>
                          <MessageCircle size={15} color={P.navy} />
                          <Text style={s.actionText}>Preguntarle a la IA sobre esta historia</Text>
                        </TouchableOpacity>

                        {(doc.lab_values || []).length > 0 && (() => {
                          // Un botón por cada valor leído (no por examen distinto), para que sean tantos como el conteo.
                          // Si un examen sale varias veces, se distingue con su valor.
                          const values = doc.lab_values || [];
                          const times = {};
                          values.forEach((v) => { times[v.exam] = (times[v.exam] || 0) + 1; });
                          return (
                            <View style={{ gap: 8 }}>
                              <Text style={s.examsLabel}>Ver gráficas de esta historia ({values.length})</Text>
                              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
                                {values.map((v, i) => (
                                  <TouchableOpacity
                                    key={`${v.exam}-${i}`}
                                    style={s.examChip}
                                    onPress={() => navigation.navigate('ExamDetail', { examName: v.exam })}>
                                    <LineChart size={12} color={P.navy} />
                                    <Text style={s.examChipText}>
                                      {times[v.exam] > 1 ? `${v.exam} · ${cleanValueRaw(v.value_raw, v.exam)}` : v.exam}
                                    </Text>
                                  </TouchableOpacity>
                                ))}
                              </View>
                            </View>
                          );
                        })()}

                        <TouchableOpacity style={[s.actionBtn, s.deleteBtn]} onPress={() => remove(doc.id, doc.filename)}>
                          <Trash2 size={15} color="#9B1C1C" />
                          <Text style={[s.actionText, { color: '#9B1C1C' }]}>Eliminar esta historia</Text>
                        </TouchableOpacity>
                      </>
                    )}
                  </View>
                )}
              </View>
            );
          })}
              </View>
            );
          })}
        </View>
      </ScrollView>

      <CategoryPickerModal
        visible={!!pickingCategoryFor}
        current={docs.find((d) => d.id === pickingCategoryFor)?.category}
        onClose={() => setPickingCategoryFor(null)}
        onSelect={(cat) => changeCategory(pickingCategoryFor, cat)}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header:      { padding: 20, paddingTop: 44, paddingBottom: 20, backgroundColor: P.navy, borderBottomLeftRadius: 28, borderBottomRightRadius: 28 },
  title:       { fontSize: 24, fontWeight: '700', color: 'white' },
  subtitle:    { fontSize: 13, color: 'rgba(255,255,255,0.65)', marginTop: 4 },
  searchBox:   { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 16, borderRadius: 16, padding: 13, backgroundColor: 'rgba(255,255,255,0.25)' },
  searchInput: { flex: 1, fontSize: 13, color: 'white' },
  statsRow:    { flexDirection: 'row', gap: 10 },
  statCard:    { flex: 1, borderRadius: 20, paddingVertical: 18, paddingHorizontal: 12, textAlign: 'center', backgroundColor: P.white, alignItems: 'center', shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2 },
  statValue:   { fontSize: 24, fontWeight: '900', color: P.navy },
  statLabel:   { fontSize: 12, fontWeight: '600', color: P.g400, marginTop: 4 },

  gridTitle:   { fontSize: 13, fontWeight: '700', color: P.g400, textTransform: 'uppercase', letterSpacing: 0.5 },
  grid:        { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  tile:        { flexBasis: '47%', flexGrow: 1, alignItems: 'center', gap: 6, backgroundColor: P.white, borderRadius: 20, paddingVertical: 16, paddingHorizontal: 8, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.07, shadowRadius: 14, elevation: 3 },
  tileIconBox: { width: 58, height: 58, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  tileIconBoxActive: { shadowColor: P.navy, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.35, shadowRadius: 10, elevation: 6 },
  tileLabel:   { fontSize: 14, fontWeight: '700', color: P.g800, textAlign: 'center' },
  tileLabelActive: { color: P.navy },
  tileCount:   { fontSize: 11, color: P.g400 },
  showAll:     { fontSize: 12, fontWeight: '700', color: P.navy, textAlign: 'center' },

  sectionHeader:{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sectionTitle:{ fontSize: 13, fontWeight: '700', color: P.g400, letterSpacing: 0.5 },
  sectionToggle:{ flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 4 },
  monthHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  valuesToggle: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingVertical: 4 },
  valuesToggleText: { fontSize: 12, fontWeight: '700', color: P.navy },
  valueRow:    { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12, paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: P.g100 },
  valueName:   { flex: 1, fontSize: 12, color: P.g400, lineHeight: 17 },
  valueText:   { maxWidth: '45%', fontSize: 12, fontWeight: '700', color: P.g800, textAlign: 'right', lineHeight: 17 },
  monthTitle:  { flex: 1, fontSize: 13, fontFamily: 'Poppins_700Bold', color: P.g800 },
  monthCount:  { fontSize: 12, color: P.g400 },
  addToSectionBtn:{ flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, backgroundColor: P.light },
  addToSectionText:{ fontSize: 11, fontWeight: '700', color: P.navy },
  errorBox:    { flexDirection: 'row', alignItems: 'flex-start', gap: 8, padding: 12, borderRadius: 14, backgroundColor: '#FDE2E2' },
  errorText:   { flex: 1, fontSize: 12, color: '#9B1C1C', lineHeight: 17 },

  card:         { borderRadius: 22, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2, overflow: 'hidden' },
  fileRow:      { paddingVertical: 18, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', gap: 14 },
  fileIcon:     { width: 54, height: 54, borderRadius: 27, alignItems: 'center', justifyContent: 'center' },
  fileName:     { fontSize: 15, fontWeight: '700', color: P.g800 },
  fileDate:     { fontSize: 12, color: P.g400, marginTop: 3 },
  badge:        { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 5, borderRadius: 999 },
  badgeText:    { fontSize: 11, fontWeight: '700' },
  detail:       { paddingHorizontal: 18, paddingBottom: 18, gap: 12, borderTopWidth: 1, borderTopColor: P.g100, paddingTop: 14 },
  detailText:   { fontSize: 13, color: P.g400, lineHeight: 18 },
  okRow:        { flexDirection: 'row', alignItems: 'center', gap: 6 },
  okText:       { fontSize: 13, fontWeight: '700', color: '#1E6B3A' },
  categoryPill: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: P.light },
  categoryPillText: { fontSize: 12, fontWeight: '700', color: P.navy },
  examsLabel:   { fontSize: 11, fontWeight: '700', color: P.g400, textTransform: 'uppercase', letterSpacing: 0.5 },
  examChip:     { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 18, backgroundColor: P.bg, maxWidth: '100%' },
  examChipText: { flexShrink: 1, fontSize: 11, fontWeight: '600', color: P.navy },
  actionBtn:    { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 10, borderRadius: 12, backgroundColor: P.light },
  actionText:   { fontSize: 13, fontWeight: '700', color: P.navy },
  deleteBtn:    { backgroundColor: '#FDE2E2' },
});
