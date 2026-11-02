import React from 'react';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { View, ActivityIndicator, SafeAreaView } from 'react-native';
import { Home, MessageCircle, Upload, BookOpen, Calendar } from 'lucide-react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import DashboardScreen from '../screens/DashboardScreen';
import ChatScreen from '../screens/ChatScreen';
import UploadScreen from '../screens/UploadScreen';
import LibraryScreen from '../screens/LibraryScreen';
import CalendarScreen from '../screens/CalendarScreen';
import ExamDetailScreen from '../screens/ExamDetailScreen';
import LoginScreen from '../screens/LoginScreen';
import RegisterScreen from '../screens/RegisterScreen';
import CompleteProfileScreen from '../screens/CompleteProfileScreen';
import { useAuth } from '../context/AuthContext';

import { Colors } from '../constants/colors';
import { tourRef } from '../services/tourTargets';
import { GuidedTourHost } from '../components/GuidedTour';

const Tab = createBottomTabNavigator();
const Stack = createNativeStackNavigator();

function Tabs() {
  // La barra de botones del sistema (Android) no debe tapar las pestañas: se les suma su alto.
  const insets = useSafeAreaInsets();
  // El recorrido guiado vive aquí, fuera de las pantallas, para seguir visible cuando cambia de pestaña.
  return (
    <View style={{ flex: 1 }}>
    <GuidedTourHost />
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarStyle: {
          backgroundColor: Colors.white,
          borderTopColor: Colors.border,
          height: 78 + insets.bottom,
          paddingBottom: 10 + insets.bottom,
          paddingTop: 8,
        },
        tabBarActiveTintColor: Colors.navy,
        tabBarInactiveTintColor: Colors.textMid,
        tabBarLabelStyle: {
          fontSize: 12,
          fontWeight: '700',
        },
        tabBarIcon: ({ color, focused }) => {
          const icons = {
            Dashboard: Home,
            Chat: MessageCircle,
            Upload: Upload,
            Library: BookOpen,
            Calendar: Calendar,
          };
          const Icon = icons[route.name];
          return (
            <View ref={tourRef(`tab-${route.name}`)} collapsable={false} style={{
              width: 42,
              height: 36,
              borderRadius: 12,
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: focused ? Colors.bluePale : 'transparent',
            }}>
              <Icon size={24} color={color} strokeWidth={focused ? 2.5 : 2} />
            </View>
          );
        },
      })}
    >
      <Tab.Screen name="Dashboard" component={DashboardScreen} options={{ tabBarLabel: 'Inicio' }} />
      <Tab.Screen name="Chat"      component={ChatScreen}      options={{ tabBarLabel: 'Chat' }} />
      <Tab.Screen name="Upload"    component={UploadScreen}    options={{ tabBarLabel: 'Subir' }} />
      <Tab.Screen name="Library"   component={LibraryScreen}   options={{ tabBarLabel: 'Biblioteca' }} />
      <Tab.Screen name="Calendar"  component={CalendarScreen}  options={{ tabBarLabel: 'Citas' }} />
    </Tab.Navigator>
    </View>
  );
}

export default function AppNavigator() {
  const { token, loading, profileComplete } = useAuth();

  if (loading || (token && profileComplete === null)) {
    return (
      <SafeAreaView style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: Colors.white }}>
        <ActivityIndicator size="large" color={Colors.navy} />
      </SafeAreaView>
    );
  }

  if (!token) {
    return (
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="Login" component={LoginScreen} />
        <Stack.Screen name="Register" component={RegisterScreen} />
      </Stack.Navigator>
    );
  }

  // Perfil médico incompleto (recién registrado, o una cuenta anterior que
  // nunca lo llenó): se muestra SOLO esta pantalla, sin Tabs ni forma de
  // saltarla — es obligatoria antes de usar el resto de la app.
  if (!profileComplete) {
    return (
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        <Stack.Screen name="CompleteProfile" component={CompleteProfileScreen} />
      </Stack.Navigator>
    );
  }

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Tabs" component={Tabs} />
      <Stack.Screen
        name="ExamDetail"
        component={ExamDetailScreen}
        options={{ presentation: 'card' }}
      />
    </Stack.Navigator>
  );
}
