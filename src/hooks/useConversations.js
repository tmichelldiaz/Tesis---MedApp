import { useState, useEffect, useRef } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

// Cada usuario tiene su propia clave de almacenamiento (medapp_conversations_<id>).
// Antes había una sola clave global para todos los usuarios del dispositivo,
// lo que significaba que cualquiera que iniciara sesión en el mismo celular
// veía las conversaciones de la cuenta anterior. Con el id del usuario en la
// clave, cada cuenta arranca con su chat en blanco y solo ve lo suyo.
const storageKeyFor = (userId) => (userId ? `medapp_conversations_${userId}` : null);

export const useConversations = (userId) => {
  const [conversations, setConversations] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  // true cuando ya se leyeron las conversaciones guardadas. Antes de eso no es
  // seguro crear ni escribir en una conversación: la carga las reemplazaría.
  const [loaded, setLoaded] = useState(false);
  const conversationsRef = useRef([]);
  const storageKey = storageKeyFor(userId);

  // Mantener ref sincronizada
  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);

  useEffect(() => {
    if (!storageKey) {
      conversationsRef.current = [];
      setConversations([]);
      setCurrentId(null);
      setLoaded(false);
      return;
    }
    setLoaded(false);
    loadConversations(storageKey).finally(() => setLoaded(true));
  }, [storageKey]);

  const loadConversations = async (key) => {
    try {
      const data = await AsyncStorage.getItem(key);
      if (data) {
        const parsed = JSON.parse(data);
        if (parsed.length > 0) {
          setConversations(parsed);
          conversationsRef.current = parsed;
          setCurrentId(parsed[0].id);
          return;
        }
      }
      // Primera vez de este usuario en este dispositivo
      const newConv = makeNewConv();
      setConversations([newConv]);
      conversationsRef.current = [newConv];
      setCurrentId(newConv.id);
      await AsyncStorage.setItem(key, JSON.stringify([newConv]));
    } catch (e) {
      console.log('Error cargando:', e);
    }
  };

  const makeNewConv = () => ({
    id: Date.now().toString(),
    title: 'Nueva conversación',
    createdAt: new Date().toISOString(),
    messages: [],
  });

  const saveConversations = async (convs) => {
    if (!storageKey) return;
    try {
      await AsyncStorage.setItem(storageKey, JSON.stringify(convs));
    } catch (e) {
      console.log('Error guardando:', e);
    }
  };

  const createNewConversation = () => {
    const newConv = makeNewConv();
    const updated = [newConv, ...conversationsRef.current];
    conversationsRef.current = updated;
    setConversations(updated);
    setCurrentId(newConv.id);
    saveConversations(updated);
  };

  const getCurrentMessages = () => {
    const conv = conversationsRef.current.find(c => c.id === currentId);
    return conv ? conv.messages : [];
  };

  // Conversación nueva que ya nace con su primer mensaje, en un solo paso (sin esperar a que el estado se
  // actualice entre medio). Devuelve el id: quien llama puede seguir escribiendo en ella sin depender de
  // cuál es la conversación "actual" en ese momento.
  const startConversation = (firstMessage) => {
    const newConv = makeNewConv();
    newConv.messages = [{ role: 'user', content: firstMessage }];
    newConv.title = firstMessage.length > 45 ? firstMessage.slice(0, 45) + '...' : firstMessage;
    const updated = [newConv, ...conversationsRef.current];
    conversationsRef.current = updated;
    setConversations(updated);
    setCurrentId(newConv.id);
    saveConversations(updated);
    return newConv.id;
  };

  const addMessage = (message) => addMessageTo(currentId, message);

  const addMessageTo = (conversationId, message) => {
    const current = conversationsRef.current;
    const updated = current.map(c => {
      if (c.id !== conversationId) return c;

      const newMessages = [...c.messages, message];

      // Título = primeras 45 letras del primer mensaje del usuario
      let title = c.title;
      if (c.messages.length === 0 && message.role === 'user') {
        title = message.content.length > 45
          ? message.content.slice(0, 45) + '...'
          : message.content;
      }

      return { ...c, messages: newMessages, title };
    });

    conversationsRef.current = updated;
    setConversations(updated);
    saveConversations(updated);
  };

  const deleteConversation = (id) => {
    const updated = conversationsRef.current.filter(c => c.id !== id);
    conversationsRef.current = updated;
    setConversations(updated);
    saveConversations(updated);

    if (currentId === id) {
      if (updated.length > 0) {
        setCurrentId(updated[0].id);
      } else {
        createNewConversation();
      }
    }
  };

  return {
    conversations,
    currentId,
    setCurrentId,
    loaded,
    createNewConversation,
    startConversation,
    getCurrentMessages,
    addMessage,
    addMessageTo,
    deleteConversation,
  };
};
