import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, ScrollView, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, ActivityIndicator, Modal,
  Pressable, Alert, KeyboardAvoidingView, Platform
} from 'react-native';
import Markdown from 'react-native-markdown-display';
import { Menu, Plus, Trash2, MessageCircle } from 'lucide-react-native';
import { SUGGESTED_QUESTIONS } from '../constants/chatSuggestions';
import { prepareMarkdown } from '../utils/chatMarkdown';
import { sendAgentChat, resumeAgentChat } from '../services/api';
import { useConversations } from '../hooks/useConversations';
import { useAuth } from '../context/AuthContext';
import AgentConfirmCard from '../components/AgentConfirmCard';

const P = {
  navy: '#034AA6', blue: '#7998FB', light: '#C2D7F2',
  bg: '#F4FAE9', white: '#FFFFFF', g100: '#E2E8F0',
  g200: '#94A3B8', g400: '#546080', g800: '#02204A',
  accent: '#F29BB2',
};

const markdownStyles = {
  body:        { fontSize: 14, lineHeight: 22, color: '#02204A' },
  strong:      { fontWeight: '700', color: '#034AA6' },
  em:          { fontStyle: 'italic' },
  paragraph:   { marginTop: 2, marginBottom: 8 },
  heading1:    { fontSize: 16, fontWeight: '700', color: '#034AA6', marginTop: 10, marginBottom: 4 },
  heading2:    { fontSize: 15, fontWeight: '700', color: '#034AA6', marginTop: 10, marginBottom: 4 },
  heading3:    { fontSize: 14, fontWeight: '700', color: '#034AA6', marginTop: 8, marginBottom: 2 },
  heading4:    { fontSize: 14, fontWeight: '700', color: '#034AA6', marginTop: 8, marginBottom: 2 },
  bullet_list: { marginTop: 2, marginBottom: 8 },
  ordered_list:{ marginTop: 2, marginBottom: 8 },
  list_item:   { marginBottom: 4 },
  bullet_list_icon: { color: '#F29BB2', marginRight: 8, marginTop: 1 },
  ordered_list_icon:{ color: '#034AA6', fontWeight: '700', marginRight: 8 },
  // Línea separadora tenue en lugar de la raya negra gruesa por defecto.
  hr:          { backgroundColor: '#E2E8F0', height: 1, marginVertical: 12 },
  blockquote:  { backgroundColor: '#F1F5FB', borderLeftWidth: 3, borderLeftColor: '#7998FB', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 4, marginVertical: 6 },
  code_inline: { backgroundColor: '#F1F5FB', color: '#034AA6', borderRadius: 4, paddingHorizontal: 4 },
  // Las tablas se convierten en listas antes de dibujar (prepareMarkdown); esto
  // queda solo como respaldo suave por si alguna se cuela.
  table:       { borderWidth: 0, borderRadius: 12, backgroundColor: '#F8FAFC', marginVertical: 8 },
  thead:       { backgroundColor: '#EEF3FB' },
  th:          { padding: 8, fontWeight: '700' },
  td:          { padding: 8 },
  tr:          { borderBottomWidth: 1, borderColor: '#E2E8F0' },
};

export default function ChatScreen({ route, navigation }) {
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const sendingRef = useRef(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [pendingConfirmation, setPendingConfirmation] = useState(null); // {action, resumeState}
  const [confirmBusy, setConfirmBusy] = useState(false);
  const scrollRef = useRef(null);
  const pendingPrefillRef = useRef(null);

  const { user } = useAuth();
  const {
    conversations,
    currentId,
    setCurrentId,
    loaded,
    createNewConversation,
    startConversation,
    addMessage,
    addMessageTo,
    deleteConversation,
  } = useConversations(user?.id);

  // Leer mensajes directamente del estado
  const messages = conversations.find(c => c.id === currentId)?.messages || [];

  const scrollDown = () => setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 100);

  // El id de la conversación local se manda como thread_id: así el agente
  // recuerda lo hablado entre turnos de la MISMA conversación (el checkpointer
  // del ejecutor vive del lado del backend, indexado por ese id).
  const handleAgentResult = (result, conversationId = currentId) => {
    if (result.status === 'done') {
      addMessageTo(conversationId, { role: 'assistant', content: result.reply });
      setPendingConfirmation(null);
    } else {
      setPendingConfirmation({ action: result.action, resumeState: result.resume_state });
    }
    scrollDown();
  };

  const send = async (overrideText) => {
    const text = (overrideText ?? input).trim();
    // Una sola consulta a la vez, aunque la pantalla pida enviar dos veces en el mismo instante.
    if (!text || loading || pendingConfirmation || sendingRef.current) return;
    sendingRef.current = true;

    const userMsg = { role: 'user', content: text };
    const isNewConversation = messages.length === 0;

    addMessage(userMsg);
    setInput('');
    setLoading(true);
    scrollDown();

    try {
      const result = await sendAgentChat(text, currentId, isNewConversation);
      handleAgentResult(result);
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      sendingRef.current = false;
      setLoading(false);
      scrollDown();
    }
  };

  const decide = async (decision, editedArgs) => {
    if (!pendingConfirmation) return;
    setConfirmBusy(true);
    try {
      const result = await resumeAgentChat(pendingConfirmation.resumeState, decision, editedArgs || null);
      handleAgentResult(result);
    } catch (e) {
      Alert.alert('Error', e.message);
    } finally {
      setConfirmBusy(false);
    }
  };

  // Si venimos de "Consultar más a detalle en el chat" (detalle de un examen): se abre una conversación
  // completamente nueva que ya trae la pregunta, y esa pregunta se manda sola, una sola vez, y el chat responde.
  // Se espera a que carguen las conversaciones guardadas: si no, esa carga reemplazaría la recién creada.
  useEffect(() => {
    const q = route?.params?.prefillQuestion;
    if (!q || !loaded) return;
    navigation.setParams({ prefillQuestion: undefined });
    askInNewConversation(q);
  }, [route?.params?.prefillQuestion, loaded]);

  const askInNewConversation = async (text) => {
    if (sendingRef.current) return;
    sendingRef.current = true;
    setPendingConfirmation(null);
    const conversationId = startConversation(text); // ya contiene la pregunta del paciente
    setLoading(true);
    scrollDown();
    try {
      const result = await sendAgentChat(text, conversationId, true);
      handleAgentResult(result, conversationId);
    } catch (e) {
      // Que nunca se quede "cargando" sin decir nada: el error queda escrito en la propia conversación.
      addMessageTo(conversationId, {
        role: 'assistant',
        content: `No pude responder en este momento (${e.message}). Vuelve a abrir el examen y toca de nuevo "Consultar más a detalle en el chat".`,
      });
    } finally {
      sendingRef.current = false;
      setLoading(false);
      scrollDown();
    }
  };

  const handleNewChat = () => {
    setPendingConfirmation(null);
    createNewConversation();
    setMenuOpen(false);
  };

  const handleSelectConv = (id) => {
    setPendingConfirmation(null);
    setCurrentId(id);
    setMenuOpen(false);
  };

  const handleDelete = (id) => {
    Alert.alert(
      'Eliminar conversación',
      '¿Estás segura de que quieres eliminar esta conversación?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Eliminar', style: 'destructive', onPress: () => deleteConversation(id) },
      ]
    );
  };

  const formatDate = (iso) => {
    const d = new Date(iso);
    return d.toLocaleDateString('es-ES', { day: '2-digit', month: 'short' });
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: P.white }}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior="padding">

      {/* Header */}
      <View style={s.header}>
        <View style={{ width: 38 }} />
        <View style={{ alignItems: 'center' }}>
          <Text style={s.headerTitle}>Asistente IA</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            <View style={s.onlineDot} />
            <Text style={s.headerSub}>Conectado</Text>
          </View>
        </View>
        <TouchableOpacity style={s.menuBtn} onPress={() => setMenuOpen(true)}>
          <Menu size={20} color="white" />
        </TouchableOpacity>
      </View>

      {/* Mensajes */}
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1, backgroundColor: P.bg }}
        contentContainerStyle={{ padding: 16, paddingBottom: 16, gap: 12 }}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}>

        {messages.length === 0 && (
          <View style={s.emptyBox}>
            <View style={s.emptyIcon}>
              <MessageCircle size={28} color={P.navy} />
            </View>
            <Text style={s.emptyTitle}>¿En qué puedo ayudarte?</Text>
            <Text style={s.emptySub}>
              Pregúntame sobre tus resultados médicos, agenda citas o pídeme que anote algo para tu médico.
            </Text>
            <Text style={s.suggestLabel}>Puedes empezar con una de estas:</Text>
            <View style={s.suggestWrap}>
              {SUGGESTED_QUESTIONS.map((q) => (
                <TouchableOpacity
                  key={q}
                  style={s.suggestChip}
                  disabled={loading || !loaded}
                  onPress={() => send(q)}>
                  <Text style={s.suggestText}>{q}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {messages.map((m, i) => (
          <View key={i} style={m.role === 'user' ? s.userRow : s.aiRow}>
            {m.role === 'user' ? (
              <View style={s.userBubble}>
                <Text style={s.userText}>{m.content}</Text>
              </View>
            ) : (
              <View style={s.aiBubble}>
                <Markdown style={markdownStyles}>{prepareMarkdown(m.content)}</Markdown>
              </View>
            )}
          </View>
        ))}

        {loading && (
          <View style={s.aiRow}>
            <View style={[s.aiBubble, { flexDirection: 'row', alignItems: 'center', gap: 10 }]}>
              <ActivityIndicator color={P.navy} />
              <Text style={{ flexShrink: 1, fontSize: 13, color: P.g400 }}>
                Pensando tu respuesta... puede tardar unos segundos.
              </Text>
            </View>
          </View>
        )}

        {pendingConfirmation && (
          <View style={s.aiRow}>
            <AgentConfirmCard
              action={pendingConfirmation.action}
              busy={confirmBusy}
              onApprove={() => decide('approve')}
              onReject={() => decide('reject')}
              onEdit={(editedArgs) => decide('edit', editedArgs)}
            />
          </View>
        )}
      </ScrollView>

      {/* Input */}
      <View style={s.inputBar}>
        <TextInput
          style={s.input}
          value={input}
          onChangeText={setInput}
          placeholder={pendingConfirmation ? 'Responde la confirmación de arriba...' : 'Escribe tu pregunta...'}
          placeholderTextColor={P.g400}
          multiline
          editable={!pendingConfirmation}
        />
        <TouchableOpacity
          style={[s.sendBtn, (!input.trim() || loading || pendingConfirmation) && { opacity: 0.5 }]}
          onPress={() => send()}
          disabled={!input.trim() || loading || !!pendingConfirmation}>
          <Text style={s.sendArrow}>→</Text>
        </TouchableOpacity>
      </View>
      </KeyboardAvoidingView>

      {/* Modal historial */}
      <Modal
        visible={menuOpen}
        transparent
        animationType="slide"
        onRequestClose={() => setMenuOpen(false)}>
        <Pressable style={s.modalOverlay} onPress={() => setMenuOpen(false)}>
          <Pressable style={s.drawer}>
            <View style={s.drawerHandle} />

            <View style={s.drawerHeader}>
              <Text style={s.drawerTitle}>Conversaciones</Text>
              <TouchableOpacity onPress={handleNewChat} style={s.newChatBtn}>
                <Plus size={16} color={P.navy} />
                <Text style={s.newChatText}>Nueva</Text>
              </TouchableOpacity>
            </View>

            <ScrollView showsVerticalScrollIndicator={false}>
              {conversations.length === 0 && (
                <Text style={{ color: P.g400, textAlign: 'center', marginTop: 20 }}>
                  No hay conversaciones aún.
                </Text>
              )}
              {conversations.map(conv => (
                <TouchableOpacity
                  key={conv.id}
                  style={[s.convRow, conv.id === currentId && s.convRowActive]}
                  onPress={() => handleSelectConv(conv.id)}>
                  <View style={s.convIcon}>
                    <MessageCircle
                      size={16}
                      color={conv.id === currentId ? P.navy : P.g400}
                    />
                  </View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text
                      style={[s.convTitle, conv.id === currentId && { color: P.navy }]}
                      numberOfLines={1}>
                      {conv.title}
                    </Text>
                    <Text style={s.convDate}>{formatDate(conv.createdAt)}</Text>
                  </View>
                  <TouchableOpacity
                    onPress={() => handleDelete(conv.id)}
                    style={s.deleteBtn}>
                    <Trash2 size={15} color={P.g400} />
                  </TouchableOpacity>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header:        { backgroundColor: '#034AA6', paddingTop: 44, paddingBottom: 20, paddingHorizontal: 20, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomLeftRadius: 28, borderBottomRightRadius: 28 },
  headerTitle:   { fontWeight: '700', color: 'white', fontSize: 15 },
  headerSub:     { fontSize: 10, color: 'rgba(255,255,255,0.65)' },
  onlineDot:     { width: 6, height: 6, borderRadius: 3, backgroundColor: '#4ADE80' },
  menuBtn:       { width: 38, height: 38, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  emptyBox:      { alignItems: 'center', marginTop: 60, paddingHorizontal: 30 },
  emptyIcon:     { width: 64, height: 64, borderRadius: 20, backgroundColor: '#C2D7F2', alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  emptyTitle:    { fontSize: 18, fontWeight: '700', color: '#02204A', marginBottom: 8 },
  suggestLabel:  { fontSize: 12, fontWeight: '700', color: '#546080', marginTop: 22, marginBottom: 10, letterSpacing: 0.3 },
  suggestWrap:   { gap: 8, alignSelf: 'stretch' },
  suggestChip:   { paddingVertical: 11, paddingHorizontal: 14, borderRadius: 16, backgroundColor: '#FFFFFF', borderWidth: 1, borderColor: '#C2D7F2' },
  suggestText:   { fontSize: 13, fontWeight: '600', color: '#034AA6', lineHeight: 18 },
  emptySub:      { fontSize: 13, color: '#546080', textAlign: 'center', lineHeight: 20 },
  userRow:       { alignItems: 'flex-end' },
  aiRow:         { alignItems: 'flex-start' },
  userBubble:    { backgroundColor: '#034AA6', padding: 14, borderRadius: 18, borderBottomRightRadius: 4, maxWidth: '85%' },
  userText:      { color: 'white', fontSize: 14, lineHeight: 20 },
  aiBubble:      { backgroundColor: '#FFFFFF', padding: 14, borderRadius: 18, borderBottomLeftRadius: 4, maxWidth: '85%', borderWidth: 1, borderColor: '#E2E8F0' },
  // En flujo normal (no absoluta): KeyboardAvoidingView solo sube lo que está en
  // el flujo, un hijo con position:absolute ignora su relleno y el teclado lo tapa.
  inputBar:      { flexDirection: 'row', padding: 12, gap: 8, backgroundColor: '#FFFFFF', borderTopWidth: 1, borderColor: '#E2E8F0' },
  input:         { flex: 1, backgroundColor: '#F4FAE9', borderRadius: 16, padding: 12, fontSize: 14, maxHeight: 100, color: '#02204A' },
  sendBtn:       { width: 44, height: 44, borderRadius: 14, backgroundColor: '#034AA6', alignItems: 'center', justifyContent: 'center' },
  sendArrow:     { color: 'white', fontSize: 20 },
  modalOverlay:  { flex: 1, backgroundColor: 'rgba(2,32,74,0.4)', justifyContent: 'flex-end' },
  drawer:        { backgroundColor: '#FFFFFF', borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: 20, paddingBottom: 40, maxHeight: '80%' },
  drawerHandle:  { width: 40, height: 5, borderRadius: 3, backgroundColor: '#E2E8F0', alignSelf: 'center', marginBottom: 20 },
  drawerHeader:  { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 },
  drawerTitle:   { fontSize: 18, fontWeight: '700', color: '#02204A' },
  newChatBtn:    { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 12, backgroundColor: '#C2D7F2' },
  newChatText:   { fontSize: 13, fontWeight: '700', color: '#034AA6' },
  convRow:       { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderRadius: 16, marginBottom: 8, backgroundColor: '#F4FAE9' },
  convRowActive: { backgroundColor: '#C2D7F2' },
  convIcon:      { width: 36, height: 36, borderRadius: 10, backgroundColor: '#FFFFFF', alignItems: 'center', justifyContent: 'center' },
  convTitle:     { fontSize: 13, fontWeight: '600', color: '#546080' },
  convDate:      { fontSize: 11, color: '#546080', marginTop: 2 },
  deleteBtn:     { padding: 6 },
});
