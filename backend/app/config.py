from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    data_dir: Path = BACKEND_ROOT / "data"
    cors_origins: str = "*"

    database_url: str = ""
    jwt_secret: str = "dev-secret-change-me"
    jwt_ttl_hours: int = 720  # 30 días: es una app de celular, no queremos deslogueos seguidos
    policy_version: str = "1.2"

    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # Enrutamiento de OpenRouter (solo para llamadas de chat/completions). Vacío =
    # OpenRouter elige el proveedor. Con proveedores definidos, la llamada solo
    # puede ir a ellos y no salta a otros si fallan: así la política de datos que
    # se documenta (quién procesa el texto del paciente) es la que realmente se
    # cumple. Ej.: OPENROUTER_PROVIDERS="google-vertex".
    # Zona horaria del paciente respecto a UTC (Colombia: -5, sin horario de verano).
    utc_offset_hours: int = -5

    openrouter_providers: str = ""
    openrouter_data_collection: str = ""  # "deny" = solo proveedores que no guardan ni entrenan con los datos

    vision_model: str = "qwen/qwen3.8-27b:free"
    vision_fallback_model: str = ""
    text_fallback_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    min_native_text_chars: int = 30

    # Modelo del agente que ejecuta acciones con herramientas (agendar, anotar). Vacío =
    # el del chat. Conviene uno estable: un cuelgue aquí deja al paciente esperando.
    agent_model: str = ""

    chat_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    chat_fallback_model: str = ""
    chat_max_tokens: int = 1024
    chat_context_chars: int = 14000
    chat_history_messages: int = 20
    chat_message_max_chars: int = 4000
    chat_prior_context_max_chars: int = 2000

    # Resumen en lenguaje sencillo de cada examen. Vacío = apagado: la app
    # muestra la explicación general escrita a mano y no se llama a ningún modelo.
    # Para encenderlo basta definir SUMMARY_MODEL.
    summary_model: str = ""
    summary_fallback_model: str = ""
    summary_max_tokens: int = 500

    values_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    values_fallback_model: str = ""
    values_max_tokens: int = 8192
    # Extraer valores es copiar datos, no razonar: sin "pensar" es más rápido (los modelos gratuitos sin
    # razonamiento ignoran el parámetro).
    values_no_reasoning: bool = True

    embeddings_model: str = "nvidia/nemotron-3-embed-1b:free"
    embeddings_fallback_model: str = ""
    embedding_chunk_chars: int = 2000
    rag_top_k: int = 5

    router_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    router_fallback_model: str = ""
    router_max_tokens: int = 60

    category_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    category_fallback_model: str = ""
    category_max_tokens: int = 500
    category_input_chars: int = 3000

    agent_planner_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"
    agent_planner_fallback_model: str = ""
    agent_planner_max_tokens: int = 600
    agent_executor_max_steps: int = 4
    agent_max_output_tokens: int = 1024

    # Enmascaramiento de datos de identificación con Cloud DLP (ver app/privacy).
    # Apagado por defecto: en local y en pruebas no hay credenciales de Google Cloud.
    dlp_enabled: bool = False
    dlp_project: str = ""  # vacío = el proyecto de las credenciales por defecto
    dlp_chunk_chars: int = 50000
    dlp_timeout_s: float = 30.0

    pdf_render_dpi: int = 200
    pages_per_request: int = 1
    max_pages: int = 50
    max_file_mb: int = 20

    # Cuántas llamadas a modelos corren a la vez al procesar un documento (páginas
    # y secciones de valores). 1 = en serie, que es lo que usan las pruebas; en
    # producción se sube por entorno (PARALLEL_WORKERS) porque cada llamada a un
    # modelo gratuito puede tardar un minuto.
    parallel_workers: int = 1

    request_timeout_s: float = 180.0
    max_retries: int = 6
    retry_min_wait_s: float = 2.0
    retry_max_wait_s: float = 45.0
    max_output_tokens: int = 4096
    # Tope de salida al transcribir una página. Una página normal ocupa ~1.000 tokens; si un modelo
    # entra en un bucle y repite texto sin parar, así se corta en segundos y no llena un límite enorme.
    transcribe_max_tokens: int = 6144
