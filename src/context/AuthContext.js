import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { teardown } from '../services/deviceSync';
import {
  login as apiLogin, register as apiRegister, getMe, setAuthToken, setUnauthorizedHandler,
  deleteAccount as apiDeleteAccount, getProfile,
} from '../services/api';

const TOKEN_KEY = 'medapp_auth_token';
const AuthContext = createContext(null);

// Un perfil "completo" tiene los 4 datos médicos base que CompleteProfileScreen
// pide justo después del registro. Se calcula desde el perfil real (no desde
// un flag local de "me acabo de registrar"), así funciona igual sin importar
// si el usuario se registró ahora o hace semanas y nunca lo completó.
function isProfileComplete(profile) {
  return !!(profile?.birth_date && profile?.sex && profile?.weight_kg != null && profile?.blood_type);
}

export function AuthProvider({ children }) {
  const [token, setToken] = useState(null);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profileComplete, setProfileComplete] = useState(null); // null = todavía no se sabe

  const logout = useCallback(async () => {
    // Los avisos de citas no deben seguir sonando para otra persona en este teléfono.
    teardown(null).catch(() => {});
    setToken(null);
    setUser(null);
    setProfileComplete(null);
    setAuthToken(null);
    try { await AsyncStorage.removeItem(TOKEN_KEY); } catch (e) {}
  }, []);

  // Si el backend rechaza el token en cualquier request (expiró, es
  // inválido), api.js llama esto solo para desloguear y volver a la
  // pantalla de acceso, sin que cada pantalla tenga que manejarlo aparte.
  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  const refreshProfileComplete = useCallback(async () => {
    try {
      const profile = await getProfile();
      setProfileComplete(isProfileComplete(profile));
    } catch (e) {
      // Un error transitorio de red no debería dejar al usuario atrapado
      // sin poder entrar a la app — se vuelve a intentar la próxima vez
      // que el Dashboard pida el perfil.
      setProfileComplete(true);
    }
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const stored = await AsyncStorage.getItem(TOKEN_KEY);
        if (stored) {
          setAuthToken(stored);
          const me = await getMe();
          setToken(stored);
          setUser(me);
          await refreshProfileComplete();
        }
      } catch (e) {
        setAuthToken(null);
        try { await AsyncStorage.removeItem(TOKEN_KEY); } catch (e2) {}
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = async (email, password) => {
    const result = await apiLogin(email, password);
    setAuthToken(result.token);
    await AsyncStorage.setItem(TOKEN_KEY, result.token);
    setToken(result.token);
    setUser(result.user);
    await refreshProfileComplete();
    return result.user;
  };

  const register = async (fields) => {
    const result = await apiRegister(fields);
    setAuthToken(result.token);
    await AsyncStorage.setItem(TOKEN_KEY, result.token);
    setToken(result.token);
    setUser(result.user);
    await refreshProfileComplete();
    return result.user;
  };

  const markProfileComplete = () => setProfileComplete(true);

  const deleteAccount = async () => {
    await apiDeleteAccount();
    // Derecho de supresión: también se retiran las citas que MedApp puso en el calendario del teléfono.
    await teardown(user?.id, { removeEvents: true }).catch(() => {});
    await logout();
  };

  return (
    <AuthContext.Provider value={{
      token, user, loading, profileComplete,
      login, register, logout, deleteAccount, markProfileComplete,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de <AuthProvider>');
  return ctx;
}
