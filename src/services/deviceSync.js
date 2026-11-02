// Calendario del teléfono + recordatorios locales para las citas del paciente.
//
// - Las citas se agregan al calendario principal del paciente (el de su cuenta de
//   Google en Android, el calendario predeterminado en iOS) y se mantienen al día
//   cuando la cita cambia o se borra. Solo si no hay ninguno disponible se crea
//   un calendario local llamado "MedApp".
// - Se programan avisos locales: el día antes y dos horas antes, que le
//   recuerdan revisar en la app las preguntas para su médico.
//
// Privacidad: el evento de calendario lleva el nombre de la cita, el médico y el lugar (y, al
// estar en Google Calendar, se sincroniza con esa cuenta); nunca el contenido de las
// preguntas. Los recordatorios SÍ nombran las preguntas pendientes (el paciente lo pidió,
// para no olvidarlas en la consulta) pero no el médico ni el motivo, y se quedan en el
// teléfono. Una notificación en la pantalla bloqueada la puede ver cualquiera: Android
// permite ocultar el contenido sensible desde sus ajustes de notificaciones.
//
// Todo está protegido: sin permiso, en la web o con una versión de la app sin los
// módulos nativos, estas funciones simplemente no hacen nada.

import { Platform } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { formatQuestion } from '../utils/examNames';

const SUPPORTED = Platform.OS === 'android' || Platform.OS === 'ios';
const CALENDAR_NAME = 'MedApp';
const CHANNEL_ID = 'citas';
const EVENT_MINUTES = 60;
const GRACE_MS = 60 * 60 * 1000; // una cita en curso todavía cuenta como vigente
const stateKey = (userId) => `medapp_devsync_${userId}`;

function nativeCalendar() {
  if (!SUPPORTED) return null;
  try { return require('expo-calendar'); } catch (e) { return null; }
}

function nativeNotifications() {
  if (!SUPPORTED) return null;
  try { return require('expo-notifications'); } catch (e) { return null; }
}

export const isSupported = () =>
  SUPPORTED && !!nativeCalendar() && !!nativeNotifications();

// ---------------------------------------------------------------------------
// Estado guardado en el teléfono (por usuario)
// ---------------------------------------------------------------------------

const EMPTY = { enabled: null, calendarId: null, calendarName: null, events: {}, reminders: {} };

async function loadState(userId) {
  if (!userId) return { ...EMPTY };
  try {
    const raw = await AsyncStorage.getItem(stateKey(userId));
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : { ...EMPTY };
  } catch (e) {
    return { ...EMPTY };
  }
}

async function saveState(userId, state) {
  if (!userId) return;
  try { await AsyncStorage.setItem(stateKey(userId), JSON.stringify(state)); } catch (e) {}
}

// null = nunca se le preguntó, true = activado, false = lo rechazó o lo apagó.
export async function getPreference(userId) {
  return (await loadState(userId)).enabled;
}

// ---------------------------------------------------------------------------
// Avisos: configuración que debe correr al abrir la app
// ---------------------------------------------------------------------------

export async function setupNotifications() {
  const N = nativeNotifications();
  if (!N) return;
  try {
    N.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });
    if (Platform.OS === 'android') {
      await N.setNotificationChannelAsync(CHANNEL_ID, {
        name: 'Recordatorios de citas',
        importance: N.AndroidImportance.HIGH,
      });
    }
  } catch (e) {}
}

// ---------------------------------------------------------------------------
// Permisos
// ---------------------------------------------------------------------------

async function ensureCalendarPermission(ask) {
  const C = nativeCalendar();
  if (!C) return false;
  try {
    let res = await C.getCalendarPermissions();
    if (!res.granted && ask) res = await C.requestCalendarPermissions();
    return !!res.granted;
  } catch (e) {
    return false;
  }
}

async function ensureNotificationPermission(ask) {
  const N = nativeNotifications();
  if (!N) return false;
  try {
    await setupNotifications(); // en Android el canal debe existir antes de pedir permiso
    let res = await N.getPermissionsAsync();
    if (!res.granted && ask) res = await N.requestPermissionsAsync();
    return !!res.granted;
  } catch (e) {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Calendario
// ---------------------------------------------------------------------------

// Elige dónde escribir las citas, en este orden:
//   1. el calendario que ya se había elegido antes;
//   2. el calendario principal de la cuenta de Google;
//   3. el calendario predeterminado (iOS) o cualquier calendario principal editable;
//   4. cualquier calendario editable;
//   5. si no hay ninguno, un calendario local "MedApp".
async function pickCalendar(state) {
  const C = nativeCalendar();
  const calendars = await C.getCalendars(C.EntityTypes.EVENT);
  const writable = calendars.filter((c) => c.allowsModifications !== false);
  const isGoogle = (c) => c.source?.type === 'com.google';

  const chosen = writable.find((c) => c.id === state.calendarId);
  if (chosen) return chosen;

  const google = writable.find((c) => isGoogle(c) && c.isPrimary)
    || writable.find((c) => isGoogle(c) && c.ownerAccount && c.title === c.ownerAccount);
  if (google) return google;

  if (Platform.OS === 'ios') {
    try {
      const def = C.getDefaultCalendarSync();
      if (def) return def;
    } catch (e) {}
  }
  const primary = writable.find((c) => c.isPrimary);
  if (primary) return primary;
  if (writable.length > 0) return writable[0];

  return createLocalCalendar();
}

// Respaldo: calendario local del teléfono, sin cuenta ni nube.
async function createLocalCalendar() {
  const C = nativeCalendar();
  const source = Platform.OS === 'ios'
    ? C.getDefaultCalendarSync().source
    : { name: CALENDAR_NAME, isLocalAccount: true };
  return C.createCalendar({
    title: CALENDAR_NAME,
    name: CALENDAR_NAME,
    color: '#034AA6',
    entityType: C.EntityTypes.EVENT,
    source,
    accessLevel: C.CalendarAccessLevel.OWNER,
    isVisible: true,
    isSynced: false,
  });
}

// Sube cuando cambia CÓMO se escribe el evento: así los que ya están en el calendario se actualizan solos.
const EVENT_FORMAT = 'v2';

const signatureOf = (a) =>
  [EVENT_FORMAT, a.title, a.doctor_name || '', a.location || '', a.notes || '', a.scheduled_at].join('|');

// El título del evento es el nombre de la cita ("Control de ovarios con Dra. Pepita"), sin prefijos repetidos.
export function eventTitle(a) {
  const title = (a.title || '').trim() || 'Cita médica';
  const doctor = (a.doctor_name || '').trim();
  if (!doctor || title.toLowerCase().includes(doctor.toLowerCase())) return title;
  return `${title} con ${doctor}`;
}

// Descripción del evento: todo lo que se sabe de la cita, más el recordatorio de las preguntas.
export function eventNotes(a) {
  const lines = [];
  if (a.doctor_name) lines.push(`Médico: ${a.doctor_name}`);
  if (a.location) lines.push(`Lugar: ${a.location}`);
  if (a.notes) lines.push(`Notas: ${a.notes}`);
  lines.push('', 'Antes de ir, revisa en MedApp las preguntas que quieres hacerle a tu médico.');
  return lines.join('\n').trim();
}

function eventDetails(a) {
  const start = new Date(a.scheduled_at);
  return {
    title: eventTitle(a),
    startDate: start,
    endDate: new Date(start.getTime() + EVENT_MINUTES * 60 * 1000),
    location: a.location || null,
    notes: eventNotes(a),
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    alarms: [{ relativeOffset: -60 }],
  };
}

async function syncEvents(state, upcoming, allIds) {
  const C = nativeCalendar();
  const calendar = await pickCalendar(state);
  if (state.calendarId && state.calendarId !== calendar.id) {
    // Cambió el calendario elegido: los eventos anteriores ya no sirven de referencia.
    state.events = {};
  }
  state.calendarId = calendar.id;
  state.calendarName = calendar.title || CALENDAR_NAME;

  // Citas borradas en la app: se quita su evento del calendario.
  for (const [apptId, entry] of Object.entries(state.events)) {
    if (allIds.has(apptId)) continue;
    try { await (await C.ExpoCalendarEvent.get(entry.eventId)).delete(); } catch (e) {}
    delete state.events[apptId];
  }

  for (const a of upcoming) {
    const sig = signatureOf(a);
    const entry = state.events[a.id];
    try {
      if (!entry) {
        const event = await calendar.createEvent(eventDetails(a));
        state.events[a.id] = { eventId: event.id, sig };
      } else if (entry.sig !== sig) {
        const details = eventDetails(a);
        try {
          const event = await C.ExpoCalendarEvent.get(entry.eventId);
          await event.update(details);
          state.events[a.id] = { eventId: entry.eventId, sig };
        } catch (e) {
          // El evento ya no existe (lo borró el paciente): se vuelve a crear con los datos nuevos.
          const event = await calendar.createEvent(details);
          state.events[a.id] = { eventId: event.id, sig };
        }
      }
    } catch (e) {
      // Una cita que falla no debe impedir que se sincronicen las demás.
    }
  }
}

// ---------------------------------------------------------------------------
// Recordatorios
// ---------------------------------------------------------------------------

const MAX_SHOWN = 3;
const MAX_QUESTION_CHARS = 70;

function shorten(text) {
  const clean = formatQuestion(text);
  return clean.length > MAX_QUESTION_CHARS ? `${clean.slice(0, MAX_QUESTION_CHARS - 1).trimEnd()}…` : clean;
}

// "No olvides preguntarle: 1) ..., 2) ..." con hasta 3 preguntas y cuántas más quedan.
function questionsLine(questions) {
  if (questions.length === 0) {
    return 'Si hay algo que quieras preguntarle, anótalo en MedApp para no olvidarlo.';
  }
  const shown = questions.slice(0, MAX_SHOWN).map((q, i) => `${i + 1}) ${shorten(q)}`).join(' ');
  const extra = questions.length - MAX_SHOWN;
  return `No olvides preguntarle: ${shown}${extra > 0 ? ` (y ${extra} más)` : ''}`;
}

function reminderContent(kind, a, questions) {
  const hour = new Date(a.scheduled_at).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' });
  if (kind === 'after') {
    return {
      title: '¿Cómo te fue en tu cita?',
      body: 'Cuéntame qué te dijo el médico y lo dejamos anotado en MedApp.',
      data: {
        screen: 'Chat',
        appointmentId: a.id,
        prefill: `Ya tuve mi cita "${a.title}". Quiero contarte cómo me fue y anotar lo que me dijo el médico.`,
      },
    };
  }
  const title = kind === 'day' ? 'Tu cita es mañana' : 'Tu cita es pronto: en 2 horas';
  return {
    title,
    body: `A las ${hour}. ${questionsLine(questions)}`,
    data: { screen: 'Calendar', appointmentId: a.id },
  };
}

async function cancelReminders(ids) {
  const N = nativeNotifications();
  for (const id of ids || []) {
    try { await N.cancelScheduledNotificationAsync(id); } catch (e) {}
  }
}

async function syncReminders(state, upcoming, allIds) {
  const N = nativeNotifications();

  for (const [apptId, entry] of Object.entries(state.reminders)) {
    if (allIds.has(apptId)) continue;
    await cancelReminders(entry.ids);
    delete state.reminders[apptId];
  }

  const now = Date.now();
  for (const a of upcoming) {
    const pending = (a.questions || []).filter((q) => !q.answered).map((q) => q.text);
    const sig = `${signatureOf(a)}|${pending.join('¦')}`;
    const entry = state.reminders[a.id];
    if (entry && entry.sig === sig) continue;
    await cancelReminders(entry?.ids);

    const start = new Date(a.scheduled_at).getTime();
    // El día antes, 2 horas antes y, ya pasada la consulta, un aviso para contar cómo les fue.
    const plan = [
      ['day', start - 24 * 60 * 60 * 1000],
      ['hours', start - 2 * 60 * 60 * 1000],
      ['after', start + 2 * 60 * 60 * 1000],
    ];
    const ids = [];
    for (const [kind, at] of plan) {
      if (at <= now + 60 * 1000) continue; // ya pasó o es inminente
      try {
        const id = await N.scheduleNotificationAsync({
          content: reminderContent(kind, a, pending),
          trigger: { type: N.SchedulableTriggerInputTypes.DATE, date: new Date(at), channelId: CHANNEL_ID },
        });
        ids.push(id);
      } catch (e) {}
    }
    state.reminders[a.id] = { sig, ids };
  }
}

// ---------------------------------------------------------------------------
// API pública
// ---------------------------------------------------------------------------

// Las sincronizaciones se encolan: el inicio y la pantalla de citas pueden
// pedirla a la vez y no deben pisarse entre sí.
let queue = Promise.resolve();

export function syncAppointments(userId, appointments) {
  queue = queue.then(() => runSync(userId, appointments)).catch(() => {});
  return queue;
}

async function runSync(userId, appointments) {
  if (!isSupported() || !userId || !Array.isArray(appointments)) return;
  const state = await loadState(userId);
  if (state.enabled !== true) return;

  const allIds = new Set(appointments.map((a) => a.id));
  const limit = Date.now() - GRACE_MS;
  const upcoming = appointments.filter((a) => {
    const t = new Date(a.scheduled_at).getTime();
    return !Number.isNaN(t) && t >= limit;
  });

  if (await ensureCalendarPermission(false)) {
    try { await syncEvents(state, upcoming, allIds); } catch (e) {}
  }
  if (await ensureNotificationPermission(false)) {
    try { await syncReminders(state, upcoming, allIds); } catch (e) {}
  }
  await saveState(userId, state);
}

// Activa la función: pide los permisos y sincroniza. Devuelve
// { ok, calendar, notifications, calendarName } para que la pantalla explique qué quedó activo.
export async function enable(userId, appointments) {
  if (!isSupported()) return { ok: false, calendar: false, notifications: false };
  const calendar = await ensureCalendarPermission(true);
  const notifications = await ensureNotificationPermission(true);
  const state = await loadState(userId);
  state.enabled = calendar || notifications;
  await saveState(userId, state);
  if (state.enabled) await syncAppointments(userId, appointments);
  const after = await loadState(userId);
  return { ok: state.enabled, calendar, notifications, calendarName: after.calendarName };
}

export async function decline(userId) {
  const state = await loadState(userId);
  state.enabled = false;
  await saveState(userId, state);
}

// Quita los avisos y, si se pide, también los eventos que MedApp puso en el calendario.
export async function teardown(userId, { removeEvents = false } = {}) {
  const N = nativeNotifications();
  try { await N?.cancelAllScheduledNotificationsAsync(); } catch (e) {}
  const state = await loadState(userId);
  state.reminders = {};
  if (removeEvents) {
    const C = nativeCalendar();
    for (const entry of Object.values(state.events)) {
      try { await (await C.ExpoCalendarEvent.get(entry.eventId)).delete(); } catch (e) {}
    }
    state.events = {};
  }
  await saveState(userId, state);
}

// Apagar desde Configuración: quita eventos y avisos, y recuerda que se apagó.
export async function disable(userId) {
  await teardown(userId, { removeEvents: true });
  const state = await loadState(userId);
  state.enabled = false;
  await saveState(userId, state);
}
