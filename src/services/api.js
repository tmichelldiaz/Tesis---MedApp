import { Platform } from 'react-native';
import { API_URL } from '../constants/api';
import { cleanValueRaw } from '../utils/labValues';
import { reportError } from './errorReport';

// Zona horaria del celular ("Europe/Madrid", "America/Bogota"...): se manda en cada petición.
const DEVICE_TIMEZONE = (() => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || null; } catch (e) { return null; }
})();

// Token de sesión, guardado en memoria y usado por cada request. AuthContext
// lo carga desde AsyncStorage al abrir la app y lo actualiza en login/logout.
let authToken = null;
let onUnauthorized = null;

export const setAuthToken = (token) => { authToken = token; };
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

// 40 s: con el servidor dormido el primer toque tarda ~20 s, y en una red lenta o desde otro país, más.
async function request(path, options = {}, { text = false, timeoutMs = 40000 } = {}) {
  const headers = { ...(options.headers || {}) };
  if (authToken) headers.Authorization = `Bearer ${authToken}`;
  // La hora de quien usa la app: el asistente cuenta "hoy" y "mañana" según su zona, no la de Colombia.
  if (DEVICE_TIMEZONE) headers['X-Timezone'] = DEVICE_TIMEZONE;

  // Sin esto, un fetch que se traba en la red (sin cortarse del todo, solo sin
  // responder) se queda esperando para siempre y la app parece congelada, sin
  // ningún error que el paciente pueda entender o sobre el que pueda actuar.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers, signal: controller.signal });
  } catch (e) {
    console.error(`Fallo de red hacia ${API_URL}${path}:`, e);
    reportError(e, { path: path.split('?')[0], network: true, timeout: e?.name === 'AbortError' });
    throw new Error(
      e?.name === 'AbortError'
        ? 'La conexión tardó demasiado. Revisa tu internet e intenta de nuevo.'
        : 'No se pudo conectar. Revisa tu conexión a internet e intenta de nuevo.'
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    // Si ya teníamos token y el servidor lo rechaza, la sesión murió (expiró
    // o es inválida) — no es un error cualquiera, hay que desloguear.
    if (response.status === 401 && authToken) {
      onUnauthorized?.();
    }
    if (response.status >= 500) reportError(new Error(`Error ${response.status} en ${path.split('?')[0]}`), { path: path.split('?')[0], status: response.status });
    let detail = `Error ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body.detail === 'string') detail = body.detail;
    } catch (e) {}
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return text ? response.text() : response.json();
}

export const register = ({
  email, password, nombre, apellido, acceptPolicy,
  birthDate, sex, weightKg, bloodType,
}) =>
  request('/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email, password, nombre, apellido, accept_policy: acceptPolicy,
      birth_date: birthDate || null, sex: sex || null,
      weight_kg: weightKg || null, blood_type: bloodType || null,
    }),
  });

export const login = (email, password) =>
  request('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  });

export const getMe = () => request('/auth/me');
export const deleteAccount = () => request('/auth/me', { method: 'DELETE' });

// Imagen de la primera página de un PDF (para confirmar antes de subirlo). No guarda nada.
export function previewPdf(asset) {
  const form = new FormData();
  if (Platform.OS === 'web' && asset.file) {
    form.append('file', asset.file, asset.name);
  } else {
    form.append('file', { uri: asset.uri, name: asset.name || 'documento.pdf', type: 'application/pdf' });
  }
  return request('/documents/preview', { method: 'POST', body: form }, { timeoutMs: 30000 });
}

export function uploadDocument(assets) {
  const list = Array.isArray(assets) ? assets : [assets];
  const form = new FormData();
  list.forEach((asset) => {
    if (Platform.OS === 'web' && asset.file) {
      form.append('files', asset.file, asset.name);
    } else {
      form.append('files', {
        uri: asset.uri,
        name: asset.name || 'documento',
        type: asset.mimeType || 'application/octet-stream',
      });
    }
  });
  return request('/documents', { method: 'POST', body: form }, { timeoutMs: 60000 });
}

export const listDocuments = () => request('/documents');
export const getDocument = (id) => request(`/documents/${id}`);
export const retryDocument = (id) => request(`/documents/${id}/retry`, { method: 'POST' });
export const reprocessAllDocuments = () => request('/documents/reprocess-all', { method: 'POST' });
export const getBundleFile = (id, name) =>
  request(`/documents/${id}/files/${encodeURIComponent(name)}`, {}, { text: true });
export const bundleUrl = (id) => `${API_URL}/documents/${id}/bundle.zip`;

export const sendChat = (messages, documentIds = null, priorContext = null) =>
  request('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: messages.map(({ role, content }) => ({ role, content })),
      document_ids: documentIds,
      prior_context: priorContext,
    }),
  }, { timeoutMs: 90000 });

// Agente (plan + ejecutor ReAct + confirmación humana antes de escribir).
// threadId = id de la conversación local: le da memoria entre turnos.
export const sendAgentChat = (question, threadId, isNewConversation = true) =>
  request('/agent/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question, thread_id: threadId, is_new_conversation: isNewConversation,
    }),
  }, { timeoutMs: 90000 });

export const resumeAgentChat = (resumeState, decision, editedArgs = null) =>
  request('/agent/chat/resume', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      resume_state: resumeState, decision, edited_args: editedArgs,
    }),
  }, { timeoutMs: 90000 });

export const deleteDocument = (id) => request(`/documents/${id}`, { method: 'DELETE' });

export const listCategories = () => request('/categories');
export const setDocumentCategory = (id, category) =>
  request(`/documents/${id}/category`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ category }),
  });
export const classifyDocumentCategory = (id) =>
  request(`/documents/${id}/classify-category`, { method: 'POST' });

// Los valores llegan sin el nombre del examen pegado ("PIRADS 2" pasa a "2"), también los ya guardados.
export const listValues = (exam) =>
  request(`/values${exam ? `?exam=${encodeURIComponent(exam)}` : ''}`).then((rows) => (
    Array.isArray(rows) ? rows.map((r) => ({ ...r, value_raw: cleanValueRaw(r.value_raw, r.exam) })) : rows
  ));

// Resumen escrito por un modelo. Devuelve { summary: string | null }: null si la
// función está apagada en el servidor, y entonces la pantalla usa la explicación
// general que ya trae la app.
export const getExamSummary = (exam) =>
  request(`/values/summary?exam=${encodeURIComponent(exam)}`);

const jsonBody = (body) => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export const listAppointments = () => request('/appointments');
export const getAppointment = (id) => request(`/appointments/${id}`);
export const createAppointment = (body) => request('/appointments', jsonBody(body));
export const updateAppointment = (id, body) =>
  request(`/appointments/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
export const deleteAppointment = (id) => request(`/appointments/${id}`, { method: 'DELETE' });

// Las preguntas son su propia colección: pueden existir sin cita (appointmentId
// null/omitido) y asignarse a una después.
export const listQuestions = ({ appointmentId, unassigned } = {}) => {
  const params = new URLSearchParams();
  if (unassigned) params.set('unassigned', 'true');
  else if (appointmentId) params.set('appointment_id', appointmentId);
  const qs = params.toString();
  return request(`/questions${qs ? `?${qs}` : ''}`);
};
export const addQuestion = (text, appointmentId = null) =>
  request('/questions', jsonBody({ text, appointment_id: appointmentId }));
export const updateQuestion = (questionId, body) =>
  request(`/questions/${questionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
export const deleteQuestion = (questionId) =>
  request(`/questions/${questionId}`, { method: 'DELETE' });

export const getNotifications = () => request('/notifications');

export const getProfile = () => request('/profile');
export const updateProfile = (body) =>
  request('/profile', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
