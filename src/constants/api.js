import { Platform, NativeModules } from 'react-native';

const PORT = 8000;

function resolveApiUrl() {
  if (process.env.EXPO_PUBLIC_API_URL) return process.env.EXPO_PUBLIC_API_URL;

  if (Platform.OS === 'web') {
    const host = typeof window !== 'undefined' && window.location.hostname;
    return `http://${host || 'localhost'}:${PORT}`;
  }

  // En el celular, el backend corre en el mismo computador que el bundler de Expo.
  const scriptURL = NativeModules?.SourceCode?.scriptURL || '';
  const host = scriptURL.match(/^https?:\/\/([^/:]+)/)?.[1];
  return `http://${host || 'localhost'}:${PORT}`;
}

export const API_URL = resolveApiUrl();
