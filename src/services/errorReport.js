// Cuando algo falla en el celular de alguien, el servidor se entera: qué falló, en qué pantalla y en qué
// modelo de celular y versión de Android. Así los errores que "a mí no me salen" se pueden ver y arreglar.
// Nunca manda datos médicos ni credenciales: solo el mensaje del error, su traza y datos del dispositivo.

import { Platform } from 'react-native';
import Constants from 'expo-constants';
import { API_URL } from '../constants/api';
import { currentBuildInfo } from './otaUpdate';

const MAX_PER_SESSION = 15;
const recent = new Map(); // mensaje -> última vez enviado (para no repetir el mismo error sin parar)
let sent = 0;
let currentScreen = null;

export const setCurrentScreen = (name) => { currentScreen = name; };

function deviceInfo() {
  const c = Platform.constants || {};
  let build = {};
  try { build = currentBuildInfo(); } catch (e) {}
  return {
    os: Platform.OS,
    android: c.Release ? `${c.Release} (API ${c.Version})` : undefined,
    model: [c.Brand, c.Model].filter(Boolean).join(' ') || undefined,
    appVersion: Constants.expoConfig?.version,
    update: build.embedded ? 'de fábrica' : build.updateId,
  };
}

export function reportError(error, context = {}) {
  try {
    const message = String(error?.message || error || 'error desconocido').slice(0, 500);
    const now = Date.now();
    if (sent >= MAX_PER_SESSION || (recent.get(message) && now - recent.get(message) < 60000)) return;
    recent.set(message, now);
    sent += 1;
    fetch(`${API_URL}/client-errors`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        stack: String(error?.stack || '').slice(0, 3000),
        context: JSON.stringify({ screen: currentScreen, ...context }).slice(0, 500),
        device: deviceInfo(),
      }),
    }).catch(() => {});
  } catch (e) {
    // reportar un error nunca debe causar otro
  }
}

// Errores de JavaScript que nadie capturó: se reportan y luego sigue el manejo normal de la app.
export function installGlobalErrorReporting() {
  try {
    const utils = global.ErrorUtils;
    if (!utils || utils.__medappInstalled) return;
    const previous = utils.getGlobalHandler?.();
    utils.setGlobalHandler((error, isFatal) => {
      reportError(error, { fatal: !!isFatal });
      previous?.(error, isFatal);
    });
    utils.__medappInstalled = true;
  } catch (e) {}
}
