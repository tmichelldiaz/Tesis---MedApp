import React, { useState, useEffect } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, Image,
  StyleSheet, SafeAreaView, ActivityIndicator, Platform,
} from 'react-native';
import { useNavigation, useRoute, useFocusEffect } from '@react-navigation/native';
import * as DocumentPicker from 'expo-document-picker';
import {
  FileUp, FileText, CircleAlert, CircleCheck, X, ArrowRight, Plus, ImagePlus, Tag,
} from 'lucide-react-native';
import { uploadDocument, setDocumentCategory, previewPdf } from '../services/api';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g200: '#94A3B8', g400: '#546080', g800: '#02204A', accent: '#F29BB2',
};

const bytes = (n) => {
  if (!n) return null;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
};

const isImage = (asset) => asset.mimeType?.startsWith('image/');
const isPdf = (asset) =>
  asset.mimeType === 'application/pdf' || asset.name?.toLowerCase().endsWith('.pdf');

export default function UploadScreen() {
  const navigation = useNavigation();
  const route = useRoute();
  const [picked, setPicked] = useState([]);
  // Vista previa de un PDF elegido en el celular: la imagen de su primera página la
  // genera el servidor (el celular no sabe dibujar PDFs), solo para confirmar.
  const [pdfPreview, setPdfPreview] = useState(null); // { status: 'loading' | 'ready' | 'failed', uri, pages }
  const [uploading, setUploading] = useState(false);
  const [uploaded, setUploaded] = useState(null);
  const [error, setError] = useState(null);
  const [presetCategory, setPresetCategory] = useState(null);

  // Si venimos de "+" en una categoría de la Biblioteca, esa categoría se fija
  // de una vez (sin esperar a que la IA la adivine) apenas termine de subir.
  useEffect(() => {
    const preset = route.params?.presetCategory;
    if (!preset) return;
    setPresetCategory(preset);
    navigation.setParams({ presetCategory: undefined });
  }, [route.params?.presetCategory]);

  useEffect(() => {
    const asset = picked.length === 1 ? picked[0] : null;
    if (!asset || !isPdf(asset) || Platform.OS === 'web') {
      setPdfPreview(null);
      return undefined;
    }
    let active = true;
    setPdfPreview({ status: 'loading' });
    previewPdf(asset)
      .then((r) => active && setPdfPreview({ status: 'ready', uri: `data:image/png;base64,${r.image_base64}`, pages: r.page_count }))
      .catch(() => active && setPdfPreview({ status: 'failed' }));
    return () => { active = false; };
  }, [picked]);

  const reset = () => {
    setPicked([]);
    setUploaded(null);
    setError(null);
  };

  const pickFiles = async (multiple) => {
    setError(null);
    setUploaded(null);
    try {
      const result = await DocumentPicker.getDocumentAsync({
        type: ['application/pdf', 'image/*'],
        copyToCacheDirectory: true,
        multiple,
      });
      if (result.canceled || !result.assets?.length) return;

      const combined = [...picked, ...result.assets];
      if (combined.some(isPdf) && combined.length > 1) {
        setError('Para combinar varias páginas selecciona solo fotos. Un PDF ya trae todas sus páginas, súbelo solo.');
        return;
      }
      setPicked(combined);
    } catch (e) {
      setError(e.message);
    }
  };

  const removeAt = (index) => setPicked((current) => current.filter((_, i) => i !== index));

  const confirmUpload = async () => {
    setUploading(true);
    setError(null);
    try {
      const created = await uploadDocument(picked);
      if (presetCategory) {
        try {
          setUploaded(await setDocumentCategory(created.id, presetCategory));
        } catch (e) {
          // el documento sí se subió; solo falló etiquetarlo, no bloquea el flujo
          setUploaded(created);
        }
      } else {
        setUploaded(created);
      }
      setPicked([]);
    } catch (e) {
      setError(e.message);
    } finally {
      setUploading(false);
    }
  };

  const multiPhoto = picked.length > 1;

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: P.white }}>
      <ScrollView
        style={{ flex: 1, backgroundColor: P.bg }}
        contentContainerStyle={{ flexGrow: 1 }}
        showsVerticalScrollIndicator={false}>

        <View style={s.header}>
          <Text style={s.title}>Subir Registro</Text>
          <Text style={s.subtitle}>Añade tu historia clínica en PDF o fotos.</Text>
        </View>

        <View style={{ flex: 1, padding: 16, gap: 14 }}>

          {presetCategory && (
            <View style={s.presetBanner}>
              <Tag size={14} color={P.navy} />
              <Text style={s.presetBannerText}>Se subirá a: {presetCategory}</Text>
              <TouchableOpacity onPress={() => setPresetCategory(null)}>
                <X size={14} color={P.navy} />
              </TouchableOpacity>
            </View>
          )}

          {picked.length === 0 && !uploaded && (
            <View style={{ flex: 1, gap: 14, justifyContent: 'center' }}>
              <TouchableOpacity style={[s.dropZone, s.dropZoneBig]} onPress={() => pickFiles(false)}>
                <View style={s.dropIconBox}>
                  <FileUp size={30} color="white" />
                </View>
                <Text style={s.dropTitle}>Añadir Registro</Text>
                <Text style={s.dropSub}>Un PDF o una sola foto</Text>
              </TouchableOpacity>

              <TouchableOpacity style={[s.dropZone, s.dropZoneBig]} onPress={() => pickFiles(true)}>
                <View style={[s.dropIconBox, { backgroundColor: P.accent }]}>
                  <ImagePlus size={30} color="white" />
                </View>
                <Text style={s.dropTitle}>Varias Fotos</Text>
                <Text style={s.dropSub}>Una foto por página</Text>
              </TouchableOpacity>
            </View>
          )}

          {picked.length > 0 && (
            <View style={s.previewCard}>
              <Text style={s.previewLabel}>
                {multiPhoto
                  ? `¿Son estas las ${picked.length} páginas correctas, en orden?`
                  : '¿Es este el documento correcto?'}
              </Text>

              {multiPhoto ? (
                <View style={s.grid}>
                  {picked.map((asset, i) => (
                    <View key={`${asset.uri}-${i}`} style={s.thumbWrap}>
                      <Image source={{ uri: asset.uri }} style={s.thumb} resizeMode="cover" />
                      <View style={s.thumbBadge}><Text style={s.thumbBadgeText}>{i + 1}</Text></View>
                      <TouchableOpacity style={s.thumbRemove} onPress={() => removeAt(i)}>
                        <X size={12} color="white" />
                      </TouchableOpacity>
                    </View>
                  ))}
                  <TouchableOpacity style={s.addMore} onPress={() => pickFiles(true)}>
                    <Plus size={20} color={P.navy} />
                  </TouchableOpacity>
                </View>
              ) : isImage(picked[0]) ? (
                <Image source={{ uri: picked[0].uri }} style={s.previewImage} resizeMode="contain" />
              ) : isPdf(picked[0]) && pdfPreview?.status === 'loading' ? (
                <View style={s.previewFallback}>
                  <ActivityIndicator color={P.navy} />
                  <Text style={s.previewFallbackText}>Preparando la vista previa...</Text>
                </View>
              ) : isPdf(picked[0]) && pdfPreview?.status === 'ready' ? (
                <View style={{ gap: 8 }}>
                  <Image source={{ uri: pdfPreview.uri }} style={s.previewPdf} resizeMode="contain" />
                  <Text style={s.previewPages}>
                    Página 1 de {pdfPreview.pages}
                  </Text>
                </View>
              ) : isPdf(picked[0]) && Platform.OS === 'web' ? (
                React.createElement('iframe', {
                  src: picked[0].uri,
                  style: { width: '100%', height: 360, border: 'none', borderRadius: 12 },
                })
              ) : (
                <View style={s.previewFallback}>
                  <FileText size={36} color={P.navy} />
                  <Text style={s.previewFallbackText}>
                    Vista previa no disponible en este dispositivo. Confirma por el nombre y el tamaño.
                  </Text>
                </View>
              )}

              {!multiPhoto && (
                <View style={s.previewMeta}>
                  <Text style={s.previewName} numberOfLines={2}>{picked[0].name}</Text>
                  {bytes(picked[0].size) && <Text style={s.previewSize}>{bytes(picked[0].size)}</Text>}
                </View>
              )}

              {uploading ? (
                <View style={s.uploadingRow}>
                  <ActivityIndicator color={P.navy} />
                  <Text style={s.uploadingText}>Subiendo...</Text>
                </View>
              ) : (
                <View style={{ flexDirection: 'row', gap: 10 }}>
                  <TouchableOpacity style={s.secondaryBtn} onPress={reset}>
                    <X size={16} color={P.g400} />
                    <Text style={s.secondaryText}>{multiPhoto ? 'Cancelar' : 'Elegir otro'}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity style={s.primaryBtn} onPress={confirmUpload}>
                    <Text style={s.primaryText}>
                      {multiPhoto ? `Confirmar y subir (${picked.length})` : 'Confirmar y subir'}
                    </Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}

          {uploaded && (
            <View style={s.successCard}>
              <View style={s.successIcon}>
                <CircleCheck size={26} color="#1E6B3A" />
              </View>
              <Text style={s.successTitle}>Subido correctamente</Text>
              <Text style={s.successSub} numberOfLines={1}>{uploaded.filename}</Text>
              <Text style={s.successHint}>
                {uploaded.category
                  ? `Categoría: ${uploaded.category}. Se está procesando con IA.`
                  : 'Se está procesando con IA, incluyendo su categoría. Lo verás en tu Biblioteca cuando esté listo.'}
              </Text>
              <View style={{ flexDirection: 'row', gap: 10, marginTop: 4 }}>
                <TouchableOpacity style={s.secondaryBtn} onPress={reset}>
                  <Text style={s.secondaryText}>Subir otro</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.primaryBtn}
                  onPress={() => navigation.navigate('Library')}>
                  <Text style={s.primaryText}>Ver en Biblioteca</Text>
                  <ArrowRight size={15} color="white" />
                </TouchableOpacity>
              </View>
            </View>
          )}

          {error && (
            <View style={s.errorBox}>
              <CircleAlert size={16} color="#9B1C1C" />
              <Text style={s.errorText}>{error}</Text>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header:       { padding: 20, paddingTop: 44, paddingBottom: 24, backgroundColor: P.navy, borderBottomLeftRadius: 28, borderBottomRightRadius: 28 },
  title:        { fontSize: 24, fontWeight: '700', color: 'white' },
  subtitle:     { fontSize: 13, color: 'rgba(255,255,255,0.65)', marginTop: 4 },
  dropZone:     { borderRadius: 28, paddingVertical: 28, paddingHorizontal: 20, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: P.g100, borderStyle: 'dashed', backgroundColor: P.white },
  // Cada tarjeta ocupa el espacio libre pero con un tope de alto: en pantallas altas
  // quedan centradas con aire alrededor en vez de estirarse de más.
  dropZoneBig:  { flex: 1, maxHeight: 230 },
  dropIconBox:  { width: 72, height: 72, borderRadius: 36, backgroundColor: P.navy, alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  dropTitle:    { fontWeight: '700', fontSize: 16, color: P.g800, textAlign: 'center' },
  dropSub:      { fontSize: 12, marginTop: 5, color: P.g400, textAlign: 'center' },
  errorBox:     { flexDirection: 'row', alignItems: 'flex-start', gap: 8, padding: 12, borderRadius: 14, backgroundColor: '#FDE2E2' },
  errorText:    { flex: 1, fontSize: 12, color: '#9B1C1C', lineHeight: 17 },
  presetBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: 14, backgroundColor: P.light },
  presetBannerText: { flex: 1, fontSize: 12, fontWeight: '700', color: P.navy },

  previewCard:      { borderRadius: 20, padding: 18, gap: 14, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 12, elevation: 2 },
  previewLabel:     { fontSize: 13, fontWeight: '700', color: P.g800 },
  previewPdf:       { width: '100%', height: 380, borderRadius: 12, backgroundColor: '#F1F5FB' },
  previewPages:     { fontSize: 11, color: P.g400, textAlign: 'center' },
  previewImage:     { width: '100%', height: 280, borderRadius: 12, backgroundColor: P.bg },
  previewFallback:  { alignItems: 'center', gap: 10, paddingVertical: 28, borderRadius: 12, backgroundColor: P.bg },
  previewFallbackText: { fontSize: 12, color: P.g400, textAlign: 'center', paddingHorizontal: 20, lineHeight: 18 },
  previewMeta:      { gap: 2 },
  previewName:      { fontSize: 13, fontWeight: '600', color: P.g800 },
  previewSize:      { fontSize: 11, color: P.g400 },
  uploadingRow:     { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 12 },
  uploadingText:    { fontSize: 13, fontWeight: '600', color: P.navy },
  secondaryBtn:     { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 14, backgroundColor: P.bg },
  secondaryText:    { fontSize: 13, fontWeight: '700', color: P.g400 },
  primaryBtn:       { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: 14, backgroundColor: P.navy },
  primaryText:      { fontSize: 13, fontWeight: '700', color: 'white' },

  grid:         { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  thumbWrap:    { width: 84, height: 84, borderRadius: 12, overflow: 'hidden', position: 'relative', backgroundColor: P.bg },
  thumb:        { width: '100%', height: '100%' },
  thumbBadge:   { position: 'absolute', left: 6, bottom: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: 'rgba(2,32,74,0.75)', alignItems: 'center', justifyContent: 'center' },
  thumbBadgeText: { fontSize: 10, fontWeight: '700', color: 'white' },
  thumbRemove:  { position: 'absolute', top: 6, right: 6, width: 20, height: 20, borderRadius: 10, backgroundColor: 'rgba(155,28,28,0.85)', alignItems: 'center', justifyContent: 'center' },
  addMore:      { width: 84, height: 84, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: P.g100, borderStyle: 'dashed' },

  successCard:  { borderRadius: 20, padding: 22, alignItems: 'center', gap: 4, backgroundColor: P.white, shadowColor: '#1A2040', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 12, elevation: 2 },
  successIcon:  { width: 52, height: 52, borderRadius: 26, backgroundColor: '#DDF3E4', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  successTitle: { fontSize: 16, fontWeight: '700', color: P.g800 },
  successSub:   { fontSize: 12, color: P.g400, marginTop: 2 },
  successHint:  { fontSize: 11, color: P.g400, textAlign: 'center', marginTop: 6, marginBottom: 10, lineHeight: 16 },
});
