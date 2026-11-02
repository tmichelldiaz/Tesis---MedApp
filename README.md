# MedApp

Asistente móvil para pacientes que organiza su historia clínica y responde sus dudas en lenguaje sencillo.
Proyecto de tesis (Uniandes). La aplicación funciona en Android.

## Qué hace

- Registro e inicio de sesión del paciente, con aceptación de la política de tratamiento de datos.
- Carga de documentos clínicos (PDF o fotos), con desidentificación, transcripción y extracción de valores.
- Consulta de valores clínicos exactos y de su evolución en el tiempo.
- Asistente conversacional con una arquitectura híbrida: consulta de valores exactos (formato OKF), búsqueda semántica (RAG) y confirmación explícita antes de modificar datos.
- Calendario de citas y preguntas para el médico.

## Estructura

| Ruta | Contenido |
|---|---|
| `App.js`, `index.js`, `app.json`, `eas.json` | Aplicación móvil (React Native y Expo) y su configuración de construcción |
| `src/` | Pantallas, componentes, servicios, estado y utilidades de la aplicación |
| `backend/app/` | Servidor en Python (FastAPI): API, agente, procesamiento de documentos, OKF, privacidad y RAG |
| `backend/migrations/` | Scripts SQL de la base de datos |
| `backend/tests/` | Pruebas automáticas del servidor |
| `backend/scripts/` | Utilidades de apoyo |

## Servidor (backend)

Requiere Python 3.11 o superior.

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # en Linux o macOS: source .venv/bin/activate
pip install -e ".[dev]"
```

El servidor se configura con variables de entorno (los valores secretos no forman parte del repositorio):

| Variable | Uso |
|---|---|
| `DATABASE_URL` | Conexión a PostgreSQL |
| `JWT_SECRET` | Clave de firma de las sesiones |
| `OPENROUTER_API_KEY` | Clave del proveedor de modelos |
| `OPENROUTER_PROVIDERS`, `OPENROUTER_DATA_COLLECTION` | Restricción de proveedores y recolección de datos |
| `CHAT_MODEL`, `VALUES_MODEL`, `AGENT_MODEL`, ... | Modelo de cada tarea (ver `backend/app/config.py`) |
| `DLP_ENABLED`, `DLP_PROJECT` | Enmascaramiento con Cloud Sensitive Data Protection |

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Pruebas

```bash
cd backend
python -m pytest
```

Las pruebas de integración (marcadas `integration`) llaman a un proveedor externo y se excluyen por defecto.

## Aplicación móvil

```bash
npm install
# indicar la dirección del servidor
set EXPO_PUBLIC_API_URL=http://localhost:8000     # en Linux o macOS: export EXPO_PUBLIC_API_URL=...
npx expo start --android
```

La construcción de la aplicación (APK) y sus actualizaciones usan EAS (`eas.json`).

## Privacidad

El repositorio no contiene claves, datos de pacientes ni documentos clínicos. Los documentos de prueba son sintéticos.

## Licencia

MIT. Véase `LICENSE`.
