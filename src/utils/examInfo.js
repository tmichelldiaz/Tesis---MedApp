// Explicación corta y general de qué mide cada examen y cómo se lee, en
// lenguaje sencillo. Está escrita a mano (no la genera un modelo) para que sea
// estable, gratis y sin riesgo de inventar. Es información general, nunca un
// diagnóstico: la interpretación de un resultado concreto la hace el médico.
//
// Las claves son los títulos cortos de examNames.js. `when` permite afinar por
// el nombre completo (p. ej. PI-RADS solo si el examen lo menciona).

const INFO = {
  'PSA': 'El PSA (antígeno prostático específico) es una proteína que produce la próstata y se mide en sangre. Sirve para vigilar la salud de la próstata. Puede subir por varias causas además del cáncer, como inflamación, infección o un crecimiento benigno, por eso se interpreta junto con otros estudios.',
  'PSA libre': 'Es la parte del PSA que circula sin unirse a otras proteínas. Se compara con el PSA total para ayudar a distinguir causas benignas de otras que requieren más estudio.',
  'Densidad PSA': 'Relaciona el PSA con el tamaño de la próstata (PSA dividido por su volumen). Ayuda a saber si un PSA elevado se explica por una próstata grande. Por debajo de 0,15 se suele considerar bajo.',
  'RM próstata': [
    { when: /pi-?rads/i, text: 'Es una resonancia magnética que toma imágenes detalladas de la próstata. La escala PI-RADS va de 1 a 5 e indica qué tan sospechosa se ve una zona: 1 y 2 muy poco probable, 3 dudosa, 4 y 5 probable. Por eso un valor de 3 o más suele llevar al médico a considerar una biopsia.' },
    { text: 'Es una resonancia magnética que toma imágenes detalladas de la próstata para ver si hay zonas que merezcan más estudio.' },
  ],
  'Biopsia próstata': 'Toma pequeñas muestras de tejido de la próstata para estudiarlas al microscopio. Es el estudio que confirma si hay células cancerosas. "Negativa" significa que no se encontraron en las muestras tomadas; el médico decide si hace falta seguimiento.',
  'Peso próstata': 'Es el tamaño estimado de la próstata, en gramos. En un adulto joven suele rondar los 20 a 30 g, y con los años es común que crezca de forma benigna. Su tamaño ayuda a interpretar el PSA.',
  'HbA1c': 'La hemoglobina glicosilada muestra el promedio de azúcar en la sangre de los últimos 2 a 3 meses. Menos de 5,7 % se considera normal, de 5,7 a 6,4 % es prediabetes y 6,5 % o más sugiere diabetes.',
  'Glucosa': 'Mide el azúcar en la sangre. En ayunas, menos de 100 mg/dL es normal, de 100 a 125 sugiere prediabetes y 126 o más sugiere diabetes, que el médico confirma con otra prueba.',
  'Colesterol total': 'Es la suma de los tipos de colesterol en la sangre. Un nivel alto aumenta con el tiempo el riesgo de enfermedades del corazón; lo deseable es menos de 200 mg/dL.',
  'Colesterol LDL': 'Es el llamado "colesterol malo": se acumula en las paredes de las arterias. Mientras más bajo, mejor; la meta depende de tu riesgo cardiovascular y la define tu médico.',
  'Colesterol HDL': 'Es el llamado "colesterol bueno": ayuda a retirar colesterol de las arterias. En este caso un valor más alto es mejor.',
  'Triglicéridos': 'Son un tipo de grasa en la sangre que viene de lo que comes y de lo que produce el cuerpo. Los valores altos se asocian a más riesgo cardiovascular; menos de 150 mg/dL se considera normal.',
  'Creatinina': 'Es un desecho de los músculos que filtran los riñones. Si sube, los riñones pueden estar filtrando menos; también varía con la masa muscular y la hidratación.',
  'TSH': 'Es la hormona que le indica a la tiroides cuánto trabajar. Una TSH alta suele indicar una tiroides lenta (hipotiroidismo) y una baja, una tiroides acelerada.',
  'T4 libre': 'Es la hormona activa que produce la tiroides. Se interpreta junto con la TSH para saber cómo está funcionando la glándula.',
  'Hemoglobina': 'Es la proteína de los glóbulos rojos que transporta el oxígeno. Un valor bajo puede indicar anemia.',
  'Hematocrito': 'Es el porcentaje de la sangre que corresponde a glóbulos rojos. Se interpreta junto con la hemoglobina.',
  'Leucocitos': 'Son los glóbulos blancos, parte de las defensas del cuerpo. Suben con infecciones o inflamación y pueden bajar por otras causas.',
  'Plaquetas': 'Son las células que ayudan a que la sangre coagule.',
  'Presión arterial': 'Es la fuerza con la que la sangre empuja las paredes de las arterias. Se dan dos números; alrededor de 120/80 mmHg se considera normal para la mayoría de los adultos.',
  'Peso': 'Es tu peso corporal. Lo que más importa es cómo cambia con el tiempo y su relación con tu talla.',
  'IMC': 'El índice de masa corporal relaciona el peso con la talla. Entre 18,5 y 24,9 se considera peso normal.',
};

export function explainExam(shortName, fullName) {
  const entry = INFO[shortName];
  if (!entry) return '';
  if (typeof entry === 'string') return entry;
  const hit = entry.find((e) => !e.when || e.when.test(fullName || ''));
  return hit ? hit.text : '';
}
