"""Memoria persistente del agente: dos piezas de LangGraph sobre el mismo
Postgres que ya usa el resto del sistema (Cloud SQL en producción).

- El checkpointer (por thread_id) hace que una conversación en curso, o una
  confirmación pendiente, sobreviva a un reinicio del backend entre un
  mensaje y el siguiente.
- El store (por paciente, no por thread_id) es memoria de largo plazo que
  cruza entre conversaciones distintas: lo que el agente guarda ahí para un
  paciente sigue disponible aunque abra un chat nuevo.

Si no hay una conexión a Postgres utilizable (por ejemplo, en pruebas locales
sin base de datos real, o si settings.database_url viene vacío), ambas piezas
caen de vuelta a sus versiones en memoria del proceso, para no romper nada
que no dependa de esto — el resto de la app sigue funcionando igual."""

import logging
from contextlib import ExitStack
from functools import lru_cache

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres import PostgresStore

log = logging.getLogger("medapp.agent.memory")

# Mantiene abiertas las conexiones de Postgres mientras viva el proceso — se
# entra al context manager una sola vez por URL (ver los @lru_cache abajo) y
# nunca se cierra explícitamente; el proceso las libera al terminar.
_resources = ExitStack()


def _psycopg_conn_string(database_url: str) -> str:
    """La app usa el URL con el prefijo de SQLAlchemy (postgresql+psycopg://);
    los clientes de LangGraph esperan un connection string de psycopg normal."""
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


@lru_cache
def get_checkpointer(database_url: str) -> PostgresSaver | InMemorySaver:
    if database_url:
        try:
            saver = _resources.enter_context(
                PostgresSaver.from_conn_string(_psycopg_conn_string(database_url))
            )
            saver.setup()
            return saver
        except Exception:
            log.exception(
                "No se pudo usar Postgres para la memoria del agente; "
                "se usa memoria en proceso (no persiste entre reinicios)."
            )
    return InMemorySaver()


@lru_cache
def get_store(database_url: str) -> PostgresStore | InMemoryStore:
    if database_url:
        try:
            store = _resources.enter_context(
                PostgresStore.from_conn_string(_psycopg_conn_string(database_url))
            )
            store.setup()
            return store
        except Exception:
            log.exception(
                "No se pudo usar Postgres para la memoria de largo plazo del "
                "agente; se usa memoria en proceso (no cruza entre reinicios)."
            )
    return InMemoryStore()


def reset_connections() -> None:
    """Cierra y olvida las conexiones a Postgres: la siguiente petición abre unas nuevas. Se usa cuando la base
    cerró una conexión que llevaba tiempo inactiva ("server closed the connection unexpectedly")."""
    try:
        _resources.close()
    except Exception:
        log.warning("Al cerrar las conexiones de memoria", exc_info=True)
    get_checkpointer.cache_clear()
    get_store.cache_clear()


def warm_up(database_url: str) -> None:
    """Crea las tablas de Postgres (si hacen falta) y abre la conexión al
    arrancar el proceso, para que ese costo lo pague el despliegue y no la
    primera petición real de un paciente (setup() la primera vez toma unos
    segundos: crear tablas e índices)."""
    get_checkpointer(database_url)
    get_store(database_url)


def memory_namespace(user_id: str) -> tuple[str, str]:
    return ("memoria", user_id)


def recall(store, user_id: str, limit: int = 10) -> list[str]:
    """Recuerdos guardados para este paciente, más recientes primero."""
    try:
        items = store.search(memory_namespace(user_id), limit=limit)
    except Exception:
        log.exception("No se pudo leer la memoria de largo plazo del paciente %s", user_id)
        return []
    return [item.value.get("recuerdo", "") for item in items if item.value.get("recuerdo")]


def list_memories(store, user_id: str, limit: int = 100) -> list[dict]:
    """Lo mismo que `recall`, pero con el id de cada recuerdo, para que el
    paciente pueda ver y borrar lo que el agente recuerda de él."""
    items = store.search(memory_namespace(user_id), limit=limit)
    return [
        {"id": item.key, "text": item.value["recuerdo"]}
        for item in items
        if item.value.get("recuerdo")
    ]


def forget(store, user_id: str, key: str) -> bool:
    """Borra un recuerdo del paciente. False si no existe (o no es suyo: el
    namespace lleva su user_id, así que no se puede tocar el de otro)."""
    namespace = memory_namespace(user_id)
    if store.get(namespace, key) is None:
        return False
    store.delete(namespace, key)
    return True


def _thread_ids(saver, user_id: str) -> list[str]:
    """Conversaciones del paciente en el checkpointer. Sus thread_id empiezan
    por '{user_id}:' (los arma el backend, nunca el cliente)."""
    prefix = f"{user_id}:"
    if isinstance(saver, PostgresSaver):
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = saver.conn.execute(
            "SELECT DISTINCT thread_id FROM checkpoints WHERE thread_id LIKE %s", (escaped + "%",)
        ).fetchall()
        return [row["thread_id"] for row in rows]
    return [t for t in getattr(saver, "storage", {}) if str(t).startswith(prefix)]


def delete_user_memory(database_url: str, user_id: str) -> None:
    """Derecho de supresión: borra TODO lo que el agente guardó del paciente, o
    sea sus recuerdos de largo plazo y el contenido de todas sus conversaciones.
    Si algo falla lanza la excepción: es preferible que la cuenta no se borre y
    el paciente reintente, a que queden datos de salud huérfanos en la base."""
    store = get_store(database_url)
    namespace = memory_namespace(user_id)
    for _ in range(100):  # tope por si un borrado fallara en silencio
        items = store.search(namespace, limit=100)
        if not items:
            break
        for item in items:
            store.delete(namespace, item.key)

    saver = get_checkpointer(database_url)
    for thread_id in _thread_ids(saver, user_id):
        saver.delete_thread(thread_id)
