import { createNavigationContainerRef } from '@react-navigation/native';

// Una sola referencia a la navegación para todo lo que vive fuera de las pantallas
// (recordatorios que abren la app, recorrido guiado).
export const navigationRef = createNavigationContainerRef();
