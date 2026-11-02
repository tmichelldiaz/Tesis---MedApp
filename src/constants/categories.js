import { FlaskConical, Pill, Stethoscope, NotebookText, FolderOpen } from 'lucide-react-native';

// Debe coincidir exactamente con CATEGORIES en backend/app/extraction/category.py
export const CATEGORIES = [
  'Resultados de laboratorio',
  'Medicamentos',
  'Diagnósticos',
  'Notas de consulta',
  'Otro',
];

export const UNCLASSIFIED = 'Sin clasificar';

// Ícono + color representativo por categoría, para la grilla de la Biblioteca.
// No son ilustraciones tipo dibujo (no tengo ese set de assets), pero dan la
// misma sensación de "tarjetas bien separadas, con dibujo y nombre claro".
export const CATEGORY_STYLE = {
  'Resultados de laboratorio': { icon: FlaskConical, bg: '#DCE9F9', fg: '#034AA6', label: 'Laboratorio' },
  'Medicamentos': { icon: Pill, bg: '#FDE8EE', fg: '#D6456F', label: 'Medicamentos' },
  'Diagnósticos': { icon: Stethoscope, bg: '#EBE4FB', fg: '#6B4FD6', label: 'Diagnósticos' },
  'Notas de consulta': { icon: NotebookText, bg: '#DDF3EA', fg: '#1F8A62', label: 'Notas' },
  'Otro': { icon: FolderOpen, bg: '#FFEBD2', fg: '#C26A12', label: 'Otro' },
};
