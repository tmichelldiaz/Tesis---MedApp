import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { reportError } from '../services/errorReport';

// Si una pantalla falla al dibujarse, en vez de cerrar la app o dejarla en blanco se muestra este aviso
// con un botón para reintentar, y el error se manda al servidor para poder arreglarlo.
export default class ErrorBoundary extends React.Component {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    reportError(error, { boundary: true, component: String(info?.componentStack || '').slice(0, 200) });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <View style={s.box}>
        <Text style={s.title}>Algo salió mal</Text>
        <Text style={s.body}>
          La app tuvo un problema. Ya avisamos al equipo para arreglarlo. Puedes intentar de nuevo.
        </Text>
        <TouchableOpacity style={s.btn} onPress={() => this.setState({ failed: false })}>
          <Text style={s.btnText}>Reintentar</Text>
        </TouchableOpacity>
      </View>
    );
  }
}

const s = StyleSheet.create({
  box:     { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 28, backgroundColor: '#F4FAE9', gap: 12 },
  title:   { fontSize: 20, fontWeight: '700', color: '#02204A' },
  body:    { fontSize: 14, lineHeight: 21, color: '#546080', textAlign: 'center' },
  btn:     { marginTop: 8, backgroundColor: '#034AA6', borderRadius: 14, paddingVertical: 12, paddingHorizontal: 28 },
  btnText: { color: 'white', fontWeight: '700', fontSize: 15 },
});
