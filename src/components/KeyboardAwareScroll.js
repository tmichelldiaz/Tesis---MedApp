import React, { useEffect, useRef } from 'react';
import { ScrollView, Keyboard, TextInput } from 'react-native';

// ScrollView que lleva el campo enfocado a la vista cuando aparece el teclado.
//
// KeyboardAvoidingView achica el área visible, pero en Android (que dibuja de
// borde a borde desde Expo SDK 53) el ScrollView no se desplaza solo hasta el
// campo que se está escribiendo: en un formulario largo como el registro, el
// campo queda debajo del teclado aunque el área ya se haya reducido.
export default function KeyboardAwareScroll({ children, ...props }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    const sub = Keyboard.addListener('keyboardDidShow', () => {
      const input = TextInput.State.currentlyFocusedInput?.();
      const scroll = scrollRef.current;
      if (!input || !scroll) return;
      // Espera a que KeyboardAvoidingView termine de reacomodar el área visible.
      setTimeout(() => {
        const inner = scroll.getInnerViewRef?.() ?? scroll.getInnerViewNode?.();
        if (!inner) return;
        input.measureLayout(
          inner,
          (_x, y) => scroll.scrollTo({ y: Math.max(0, y - 96), animated: true }),
          () => {},
        );
      }, 150);
    });
    return () => sub.remove();
  }, []);

  return (
    <ScrollView
      ref={scrollRef}
      keyboardShouldPersistTaps="handled"
      keyboardDismissMode="on-drag"
      {...props}>
      {children}
    </ScrollView>
  );
}
