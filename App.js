import { useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { navigationRef } from './src/navigation/navigationRef';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { View, Text, TextInput, StyleSheet, Platform, ActivityIndicator, useWindowDimensions } from 'react-native';
import {
  useFonts,
  Poppins_400Regular,
  Poppins_500Medium,
  Poppins_600SemiBold,
  Poppins_700Bold,
  Poppins_800ExtraBold,
} from '@expo-google-fonts/poppins';
import AppNavigator from './src/navigation/AppNavigator';
import { AuthProvider } from './src/context/AuthContext';
import { setupNotifications } from './src/services/deviceSync';
import { checkAndApplyUpdate } from './src/services/otaUpdate';
import ErrorBoundary from './src/components/ErrorBoundary';
import { installGlobalErrorReporting, setCurrentScreen } from './src/services/errorReport';


// Al tocar un aviso de cita: los recordatorios abren Citas (donde están las preguntas) y
// el de "¿cómo te fue?" abre el chat con el mensaje ya escrito para contarlo.
function openFromReminder(response) {
  try {
    if (!navigationRef.isReady()) return;
    const data = response?.notification?.request?.content?.data || {};
    if (data.screen === 'Chat' && data.prefill) {
      navigationRef.navigate('Tabs', { screen: 'Chat', params: { prefillQuestion: data.prefill } });
    } else {
      navigationRef.navigate('Tabs', { screen: 'Calendar' });
    }
  } catch (e) {}
}

setupNotifications();
installGlobalErrorReporting();

// Para que la app se vea igual en todos los celulares: Android deja elegir un tamaño de letra y de pantalla
// muy distintos entre personas, y eso descuadraba los textos. La letra puede crecer, pero con tope.
Text.defaultProps = { ...(Text.defaultProps || {}), maxFontSizeMultiplier: 1.15 };
TextInput.defaultProps = { ...(TextInput.defaultProps || {}), maxFontSizeMultiplier: 1.15 };

const trackScreen = () => {
  try { setCurrentScreen(navigationRef.getCurrentRoute()?.name || null); } catch (e) {}
};

export default function App() {
  const [fontsLoaded] = useFonts({
    Poppins_400Regular,
    Poppins_500Medium,
    Poppins_600SemiBold,
    Poppins_700Bold,
    Poppins_800ExtraBold,
  });
  // Todos los hooks deben llamarse siempre, en el mismo orden, en cada
  // render — por eso useWindowDimensions va aquí arriba, antes de cualquier
  // return condicional (fontsLoaded), y no después.
  const { width } = useWindowDimensions();

  // Al abrir la app se busca una actualización y, si hay, se aplica al instante (en vez de esperar
  // al siguiente arranque en frío).
  useEffect(() => {
    if (Platform.OS === 'web') return undefined;
    const timer = setTimeout(() => { checkAndApplyUpdate(); }, 1500);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (Platform.OS === 'web') return undefined;
    let sub;
    try {
      const N = require('expo-notifications');
      sub = N.addNotificationResponseReceivedListener(openFromReminder);
      // App cerrada: si se abrió tocando un recordatorio, se va a Citas cuando la navegación esté lista.
      N.getLastNotificationResponseAsync().then((r) => {
        if (r) setTimeout(() => openFromReminder(r), 1200);
      }).catch(() => {});
    } catch (e) {}
    return () => { try { sub?.remove(); } catch (e) {} };
  }, []);

  if (!fontsLoaded) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#C2D7F2' }}>
        <ActivityIndicator size="large" color="#034AA6" />
      </View>
    );
  }

  // La "carcasa" de teléfono es solo decorativa, para simular un celular
  // cuando se ve desde un navegador de escritorio ancho. En un celular real
  // (o cualquier ventana angosta) mostrarla dejaría la app chiquita en medio
  // de la pantalla — ahí se renderiza a pantalla completa, igual que nativo.
  const isNarrowWeb = Platform.OS === 'web' && width < 500;

  if (Platform.OS === 'web' && !isNarrowWeb) {
    return (
      <SafeAreaProvider>
        <View style={styles.wrapper}>
          <View style={styles.phone}>
            <View style={styles.notch} />
            <View style={{ flex: 1, overflow: 'hidden' }}>
              <AuthProvider>
                <NavigationContainer ref={navigationRef}>
                  <AppNavigator />
                </NavigationContainer>
              </AuthProvider>
            </View>
            <View style={styles.homeBar} />
          </View>
        </View>
      </SafeAreaProvider>
    );
  }

  return (
    <SafeAreaProvider>
      <ErrorBoundary>
        <AuthProvider>
          <NavigationContainer ref={navigationRef} onStateChange={trackScreen}>
            <AppNavigator />
          </NavigationContainer>
        </AuthProvider>
      </ErrorBoundary>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    flex: 1,
    backgroundColor: '#C2D7F2',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '100vh',
  },
  phone: {
    width: 390,
    height: 844,
    backgroundColor: '#FFFFFF',
    borderRadius: 50,
    borderWidth: 10,
    borderColor: '#02204A',
    overflow: 'hidden',
    shadowColor: '#1B3085',
    shadowOffset: { width: 0, height: 30 },
    shadowOpacity: 0.35,
    shadowRadius: 60,
    position: 'relative',
    flexDirection: 'column',
  },
  notch: {
    width: 130,
    height: 30,
    backgroundColor: '#02204A',
    borderRadius: 20,
    alignSelf: 'center',
    marginTop: 0,
    zIndex: 10,
  },
  homeBar: {
    width: 120,
    height: 5,
    backgroundColor: '#02204A',
    borderRadius: 3,
    alignSelf: 'center',
    marginBottom: 8,
    opacity: 0.3,
  },
});

