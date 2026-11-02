import React, { useEffect, useRef } from 'react';
import { Animated, Easing } from 'react-native';
import Svg, { Circle, Path } from 'react-native-svg';

const AnimatedSvg = Animated.createAnimatedComponent(Svg);

// Ilustración decorativa simple (corazón + línea de pulso), con una animación
// de "latido" sutil y en loop — le da algo de vida/calidez al header, sin
// depender de imágenes/assets externos que no puedo empaquetar ni revisar
// visualmente desde aquí.
export default function HeaderIllustration({ size = 72 }) {
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 550, easing: Easing.out(Easing.quad), useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 550, easing: Easing.in(Easing.quad), useNativeDriver: true }),
        Animated.delay(700),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [pulse]);

  const scale = pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.12] });

  return (
    <Animated.View style={{ transform: [{ scale }] }}>
      <Svg width={size} height={size} viewBox="0 0 72 72">
        <Circle cx="36" cy="36" r="36" fill="rgba(255,255,255,0.14)" />
        <Circle cx="36" cy="36" r="26" fill="rgba(255,255,255,0.18)" />
        <Path
          d="M36 47 C24 39 18 32 18 25 C18 19 22.5 15 28 15 C31.5 15 34.5 17 36 20 C37.5 17 40.5 15 44 15 C49.5 15 54 19 54 25 C54 32 48 39 36 47 Z"
          fill="#F29BB2"
        />
        <Path
          d="M14 36 H24 L28 28 L33 44 L37 32 L40 36 H58"
          stroke="#FFFFFF"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
        />
      </Svg>
    </Animated.View>
  );
}
