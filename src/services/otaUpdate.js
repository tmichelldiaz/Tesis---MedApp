// Actualizaciones automáticas (EAS Update) de la app.
//
// Por defecto Expo descarga la actualización en segundo plano al abrir la app y la usa
// recién en el SIGUIENTE arranque en frío. En la práctica eso significa que, si la app se
// cierra con "atrás" o se deja en segundo plano, la corrección nunca llega. Aquí se
// descarga y se aplica al instante: se busca al abrir la app y también a pedido del paciente.
//
// En desarrollo, en la web o si el módulo no está, no hace nada.

import { Platform } from 'react-native';

function updates() {
  if (Platform.OS === 'web') return null;
  try {
    const U = require('expo-updates');
    return U && U.isEnabled ? U : null;
  } catch (e) {
    return null;
  }
}

// Qué está corriendo ahora: la versión de fábrica del instalador o una actualización.
export function currentBuildInfo() {
  let U = null;
  if (Platform.OS !== 'web') {
    try { U = require('expo-updates'); } catch (e) { U = null; }
  }
  if (!U || !U.isEnabled) return { enabled: false, updateId: null, embedded: true, runtime: null };
  return {
    enabled: true,
    updateId: U.updateId ? String(U.updateId).slice(0, 8) : null,
    embedded: !!U.isEmbeddedLaunch,
    runtime: U.runtimeVersion || null,
  };
}

// Resultado: 'applied' (se descargó y la app se reinicia sola), 'none' (ya tiene la última),
// 'unavailable' (sin actualizaciones en este modo) o 'error' (sin conexión u otro fallo).
export async function checkAndApplyUpdate() {
  const U = updates();
  if (!U) return 'unavailable';
  try {
    const check = await U.checkForUpdateAsync();
    if (!check.isAvailable) return 'none';
    const fetched = await U.fetchUpdateAsync();
    if (!fetched.isNew) return 'none';
    await U.reloadAsync();
    return 'applied';
  } catch (e) {
    return 'error';
  }
}
