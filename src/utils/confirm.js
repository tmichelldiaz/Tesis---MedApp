import { Alert, Platform } from 'react-native';

// Pregunta "¿seguro?" antes de una acción que no se puede deshacer. En el celular usa el diálogo
// del sistema; en la web (donde Alert de React Native no hace nada) usa el del navegador.
// Devuelve true si el paciente confirma.
export function confirmAction(title, message, confirmText = 'Eliminar') {
  return new Promise((resolve) => {
    if (Platform.OS === 'web') {
      resolve(typeof window !== 'undefined' && window.confirm(`${title}\n\n${message}`));
      return;
    }
    Alert.alert(
      title,
      message,
      [
        { text: 'Cancelar', style: 'cancel', onPress: () => resolve(false) },
        { text: confirmText, style: 'destructive', onPress: () => resolve(true) },
      ],
      { cancelable: true, onDismiss: () => resolve(false) },
    );
  });
}
