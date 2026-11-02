import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Modal, Animated, Easing } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Defs, Mask, Rect } from 'react-native-svg';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { measureTarget } from '../services/tourTargets';
import { navigationRef } from '../navigation/navigationRef';
import { useAuth } from '../context/AuthContext';

const P = { navy: '#034AA6', bg: '#F4FAE9', white: '#FFFFFF', g400: '#546080', g800: '#02204A' };

const keyFor = (userId) => `medapp_tutorial_seen_${userId}`;

// ¿Ya hizo este paciente el recorrido? Si no se puede leer el dato, se asume que sí para no estorbar.
export async function tutorialPending(userId) {
  if (!userId) return false;
  try {
    return (await AsyncStorage.getItem(keyFor(userId))) !== '1';
  } catch (e) {
    return false;
  }
}

export async function markTutorialSeen(userId) {
  if (!userId) return;
  try { await AsyncStorage.setItem(keyFor(userId), '1'); } catch (e) {}
}

// Cada paso lleva al paciente a una pantalla real de la app y señala el elemento del que habla.
// `pad` agranda el recuadro; si el elemento no se encuentra, el mensaje queda al centro.
const STEPS = [
  {
    tab: 'Dashboard', target: null,
    title: 'Te muestro la app',
    body: 'MedApp te ayuda a entender tu historia clínica. Vamos a recorrerla juntas, pantalla por pantalla. Dura menos de un minuto.',
    note: 'No reemplaza a tu médico: te ayuda a prepararte para hablar con él.',
  },
  {
    tab: 'Dashboard', target: 'keyResults', pad: 8,
    title: 'Tus resultados clave',
    body: 'Aquí aparecen los valores más importantes de tu última historia, con su evolución y si están dentro o fuera de rango.',
    note: 'Toca cualquiera para ver su gráfica y una explicación sencilla.',
  },
  {
    tab: 'Dashboard', target: 'bell', pad: 6, round: true,
    title: 'Tus avisos',
    body: 'La campana te avisa de citas que ya pasaron, preguntas pendientes y resultados fuera de rango. El círculo rosa desaparece cuando los ves.',
  },
  {
    tab: 'Chat', target: 'tab-Chat', pad: 8, padBottom: 22,
    title: 'Pregúntale al asistente',
    body: 'Pregunta por tus exámenes, pídele que agende una cita o que guarde una pregunta para tu médico.',
    note: 'Ejemplo: "¿cómo van mis linfocitos?" o "agéndame una cita el lunes".',
  },
  {
    tab: 'Upload', target: 'tab-Upload', pad: 8, padBottom: 22,
    title: 'Sube tus historias',
    body: 'Carga un PDF o una foto de tu historia o de un examen. La app lee los resultados sola; tú no tienes que escribir nada.',
  },
  {
    tab: 'Library', target: 'tab-Library', pad: 8, padBottom: 22,
    title: 'Tu biblioteca',
    body: 'Aquí quedan todos tus documentos, organizados por tipo. Puedes abrirlos, cambiarles la categoría o eliminar una historia.',
  },
  {
    tab: 'Calendar', target: 'tab-Calendar', pad: 8, padBottom: 22,
    title: 'Citas y recordatorios',
    body: 'Agenda tus citas y escribe lo que quieres preguntar. Se guardan en tu Google Calendar y te avisamos el día antes, 2 horas antes y después para saber cómo te fue.',
    note: 'Puedes editar o eliminar una cita cuando quieras.',
  },
];

// Aviso para abrir el recorrido desde cualquier parte (p. ej. Configuración → Ver el tutorial).
const listeners = new Set();
export const startTour = () => listeners.forEach((fn) => fn());

const goToTab = (tab) => {
  try {
    if (navigationRef.isReady()) navigationRef.navigate('Tabs', { screen: tab });
  } catch (e) {}
};

// Se monta una sola vez, fuera de las pantallas: abre el recorrido la primera vez que entra el paciente
// y cuando se pide desde Configuración, y recuerda que ya lo vio.
export function GuidedTourHost() {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let active = true;
    tutorialPending(user?.id).then((pending) => { if (active && pending) setOpen(true); });
    return () => { active = false; };
  }, [user?.id]);

  useEffect(() => {
    const fn = () => setOpen(true);
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    markTutorialSeen(user?.id);
  }, [user?.id]);

  return <GuidedTour visible={open} onClose={close} onNavigate={goToTab} />;
}

const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const MOVE_MS = 280;
const AnimatedRect = Animated.createAnimatedComponent(Rect);

// Recorrido guiado: oscurece la app real y deja iluminado el elemento que se está explicando.
// Para que se sienta fluido, el recuadro y la tarjeta se deslizan de un paso al siguiente y el texto solo
// cambia cuando ya se sabe dónde va el nuevo recuadro (nunca se ve un paso a medias).
export default function GuidedTour({ visible, onClose, onNavigate, onUpload }) {
  const [step, setStep] = useState(0);
  const [shown, setShown] = useState(null); // { index, rect } del paso que se está mostrando
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [cardH, setCardH] = useState(0);
  const insets = useSafeAreaInsets();
  const runId = useRef(0);
  const lastTab = useRef(null);
  const placed = useRef(false);
  const hole = useRef({
    x: new Animated.Value(0), y: new Animated.Value(0), w: new Animated.Value(0), h: new Animated.Value(0),
    card: new Animated.Value(0),
  }).current;

  const last = step === STEPS.length - 1;
  const shownIndex = shown ? shown.index : step;
  const current = STEPS[shownIndex];

  // Va a la pantalla del paso y mide el elemento. Las pestañas de abajo siempre están en pantalla, así
  // que se miden al instante; lo demás espera solo si hubo cambio de pantalla.
  useEffect(() => {
    if (!visible) return undefined;
    const id = ++runId.current;
    const wanted = STEPS[step];
    (async () => {
      const changedTab = lastTab.current !== wanted.tab;
      lastTab.current = wanted.tab;
      onNavigate?.(wanted.tab);
      if (!wanted.target) {
        setShown({ index: step, rect: null });
        return;
      }
      const isTabButton = wanted.target.startsWith('tab-');
      if (!isTabButton && changedTab) await wait(260);
      for (let attempt = 0; attempt < 14; attempt++) {
        if (runId.current !== id) return;
        const found = await measureTarget(wanted.target);
        if (runId.current !== id) return;
        if (found) {
          setShown({ index: step, rect: found });
          return;
        }
        await wait(120);
      }
      if (runId.current === id) setShown({ index: step, rect: null });
    })();
    return () => { runId.current += 1; };
  }, [visible, step]);

  // Al cerrarse, se olvida todo para que la próxima vez empiece limpio.
  useEffect(() => {
    if (visible) return;
    placed.current = false;
    lastTab.current = null;
    setShown(null);
    setStep(0);
    setCardH(0);
  }, [visible]);

  const finish = useCallback((andUpload) => {
    runId.current += 1;
    onClose();
    onNavigate?.(andUpload ? 'Upload' : 'Dashboard');
    if (andUpload) onUpload?.();
  }, [onClose, onNavigate, onUpload]);

  // Recuadro iluminado, ajustado para que no se salga de la pantalla.
  const rect = shown?.rect;
  let target = null;
  if (rect && size.h) {
    const pad = current.pad || 0;
    const x = Math.max(4, rect.x - pad);
    const y = Math.max(4, rect.y - pad);
    const right = Math.min(size.w - 4, rect.x + rect.w + pad);
    const bottom = Math.min(size.h - 4, rect.y + rect.h + pad + (current.padBottom || 0));
    // Un recuadro muy alto dejaría sin sitio a la tarjeta: se ilumina solo su parte de arriba.
    target = { x, y, w: right - x, h: Math.min(bottom - y, Math.round(size.h * 0.3)) };
  }

  // La tarjeta se coloca debajo del recuadro, o encima si no cabe, y siempre dentro de la zona libre:
  // ni bajo la barra de estado ni bajo los botones del sistema (atrás, inicio, recientes).
  const minTop = insets.top + 8;
  const maxBottom = size.h - Math.max(insets.bottom, 16) - 8;
  let cardTop = minTop;
  if (!target) {
    cardTop = Math.max(minTop, (maxBottom + minTop - cardH) / 2);
  } else {
    const below = target.y + target.h + 14;
    const above = target.y - 14 - cardH;
    if (below + cardH <= maxBottom) cardTop = below;
    else if (above >= minTop) cardTop = above;
    else cardTop = Math.max(minTop, maxBottom - cardH);
  }

  // Desliza recuadro y tarjeta hacia su sitio nuevo (la primera vez, sin animar).
  const targetKey = target ? `${target.x}|${target.y}|${target.w}|${target.h}` : 'none';
  useEffect(() => {
    if (!shown || !size.h || !cardH) return;
    const to = target || { x: size.w / 2, y: size.h / 2, w: 0, h: 0 };
    if (!placed.current) {
      placed.current = true;
      hole.x.setValue(to.x); hole.y.setValue(to.y); hole.w.setValue(to.w); hole.h.setValue(to.h);
      hole.card.setValue(cardTop);
      return;
    }
    const cfg = { duration: MOVE_MS, easing: Easing.out(Easing.cubic), useNativeDriver: false };
    Animated.parallel([
      Animated.timing(hole.x, { toValue: to.x, ...cfg }),
      Animated.timing(hole.y, { toValue: to.y, ...cfg }),
      Animated.timing(hole.w, { toValue: to.w, ...cfg }),
      Animated.timing(hole.h, { toValue: to.h, ...cfg }),
      Animated.timing(hole.card, { toValue: cardTop, ...cfg }),
    ]).start();
  }, [shown, size.w, size.h, cardH, cardTop, targetKey]);

  const dim = 'rgba(2,32,74,0.78)';
  const ready = !!shown && !!cardH;
  const radius = current.round ? 30 : 18; // esquinas del recuadro iluminado: siempre redondeadas

  return (
    <Modal visible={visible} transparent animationType="fade" statusBarTranslucent onRequestClose={() => finish(false)}>
      <View
        style={s.root}
        onLayout={(e) => setSize({ w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height })}>
        {size.h > 0 && (
          <Svg width={size.w} height={size.h} style={s.dimLayer} pointerEvents="none">
            <Defs>
              <Mask id="tourHole" x="0" y="0" width={size.w} height={size.h}>
                <Rect x="0" y="0" width={size.w} height={size.h} fill="white" />
                <AnimatedRect x={hole.x} y={hole.y} width={hole.w} height={hole.h} rx={radius} ry={radius} fill="black" />
              </Mask>
            </Defs>
            <Rect x="0" y="0" width={size.w} height={size.h} fill={dim} mask="url(#tourHole)" />
            <AnimatedRect
              x={hole.x} y={hole.y} width={hole.w} height={hole.h} rx={radius} ry={radius}
              fill="none" stroke="white" strokeWidth={target ? 3 : 0}
            />
          </Svg>
        )}

        <Animated.View pointerEvents="box-none" style={[s.cardWrap, { top: hole.card, opacity: ready ? 1 : 0 }]}>
          <View style={s.card} onLayout={(e) => setCardH(e.nativeEvent.layout.height)}>
            <Text style={s.counter}>{shownIndex + 1} de {STEPS.length}</Text>
            <Text style={s.title}>{current.title}</Text>
            <Text style={s.body}>{current.body}</Text>
            {!!current.note && (
              <View style={s.noteBox}><Text style={s.note}>{current.note}</Text></View>
            )}

            <View style={s.dots}>
              {STEPS.map((st, i) => <View key={st.title} style={[s.dot, i === shownIndex && s.dotActive]} />)}
            </View>

            {last ? (
              <>
                <TouchableOpacity style={s.primaryBtn} onPress={() => finish(true)}>
                  <Text style={s.primaryText}>Subir mi primera historia</Text>
                </TouchableOpacity>
                <TouchableOpacity style={s.textBtn} onPress={() => finish(false)}>
                  <Text style={s.textBtnLabel}>Explorar primero</Text>
                </TouchableOpacity>
              </>
            ) : (
              <View style={s.btnRow}>
                <TouchableOpacity onPress={() => finish(false)} hitSlop={10} style={s.skipBtn}>
                  <Text style={s.skipText}>Omitir</Text>
                </TouchableOpacity>
                {step > 0 && (
                  <TouchableOpacity style={s.backBtn} onPress={() => setStep(step - 1)}>
                    <Text style={s.backText}>Atrás</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity style={s.nextBtn} onPress={() => setStep(step + 1)}>
                  <Text style={s.primaryText}>Siguiente</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
        </Animated.View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  root:        { flex: 1 },
  dimLayer:    { position: 'absolute', top: 0, left: 0 },
  cardWrap:    { position: 'absolute', left: 0, right: 0, paddingHorizontal: 18 },
  card:        { backgroundColor: P.white, borderRadius: 24, padding: 20, gap: 10, shadowColor: '#000', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.2, shadowRadius: 16, elevation: 8 },
  counter:     { fontSize: 12, fontFamily: 'Poppins_500Medium', color: P.g400 },
  title:       { fontSize: 19, fontFamily: 'Poppins_700Bold', color: P.g800 },
  body:        { fontSize: 14, lineHeight: 21, color: P.g400 },
  noteBox:     { backgroundColor: P.bg, borderRadius: 14, paddingVertical: 10, paddingHorizontal: 14 },
  note:        { fontSize: 12.5, lineHeight: 18, fontFamily: 'Poppins_500Medium', color: P.navy },
  dots:        { flexDirection: 'row', gap: 6, paddingVertical: 4 },
  dot:         { width: 7, height: 7, borderRadius: 4, backgroundColor: '#E2E8F0' },
  dotActive:   { width: 20, backgroundColor: P.navy },
  btnRow:      { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  skipBtn:     { flex: 1 },
  skipText:    { fontSize: 14, fontFamily: 'Poppins_600SemiBold', color: P.g400 },
  backBtn:     { paddingVertical: 12, paddingHorizontal: 14 },
  backText:    { fontSize: 14, fontFamily: 'Poppins_600SemiBold', color: P.navy },
  nextBtn:     { backgroundColor: P.navy, borderRadius: 14, paddingVertical: 12, paddingHorizontal: 22 },
  primaryBtn:  { alignItems: 'center', backgroundColor: P.navy, borderRadius: 14, paddingVertical: 14, marginTop: 4 },
  primaryText: { fontSize: 14, fontFamily: 'Poppins_600SemiBold', color: 'white' },
  textBtn:     { alignItems: 'center', paddingVertical: 8 },
  textBtnLabel:{ fontSize: 14, fontFamily: 'Poppins_600SemiBold', color: P.navy },
});
