// Qué avisos de la campana ya vio el paciente y cuáles descartó.
//
// El servidor calcula los avisos cada vez (citas que ya pasaron, preguntas sin responder...), así
// que sin esto el círculo de la campana nunca se apagaba: siempre había algo "pendiente". Aquí se
// recuerda, en el teléfono y por usuario, qué avisos ya se vieron (el círculo se apaga al abrir la
// campana) y cuáles el paciente descartó con la X (no vuelven a salir mientras el aviso sea el mismo).

import AsyncStorage from '@react-native-async-storage/async-storage';

const keyFor = (userId) => `medapp_notices_${userId}`;

// Identidad estable de un aviso: su tipo y su texto.
export const noticeKey = (notice) => `${notice.type}|${notice.text}`;

async function load(userId) {
  if (!userId) return { seen: [], dismissed: [] };
  try {
    const raw = await AsyncStorage.getItem(keyFor(userId));
    const data = raw ? JSON.parse(raw) : {};
    return { seen: data.seen || [], dismissed: data.dismissed || [] };
  } catch (e) {
    return { seen: [], dismissed: [] };
  }
}

async function save(userId, state) {
  if (!userId) return;
  // Se guardan solo los últimos 200 de cada lista: los avisos viejos dejan de existir y no hay que acumularlos.
  const trimmed = { seen: state.seen.slice(-200), dismissed: state.dismissed.slice(-200) };
  try { await AsyncStorage.setItem(keyFor(userId), JSON.stringify(trimmed)); } catch (e) {}
}

export async function loadNoticeState(userId) {
  return load(userId);
}

// Avisos que el paciente no ha descartado.
export const visibleNotices = (notices, state) =>
  (notices || []).filter((n) => !state.dismissed.includes(noticeKey(n)));

// ¿Hay algún aviso visible que todavía no haya visto?
export const hasUnseen = (notices, state) =>
  visibleNotices(notices, state).some((n) => !state.seen.includes(noticeKey(n)));

export async function markSeen(userId, notices) {
  const state = await load(userId);
  const keys = (notices || []).map(noticeKey).filter((k) => !state.seen.includes(k));
  if (keys.length === 0) return state;
  const next = { ...state, seen: [...state.seen, ...keys] };
  await save(userId, next);
  return next;
}

export async function dismiss(userId, notice) {
  const state = await load(userId);
  const key = noticeKey(notice);
  const next = {
    seen: state.seen.includes(key) ? state.seen : [...state.seen, key],
    dismissed: state.dismissed.includes(key) ? state.dismissed : [...state.dismissed, key],
  };
  await save(userId, next);
  return next;
}
