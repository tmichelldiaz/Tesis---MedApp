"""La fecha de hoy para los modelos.

Un modelo no sabe qué día es: asume el año que más recuerda de su entrenamiento
(por eso el agente agendaba citas en 2025 estando en 2026). Tampoco calcula bien
con fechas: en una prueba real, "en un mes" salió como un mes ATRÁS. Por eso cada
llamada recibe, además del día y la hora, las fechas relativas ya calculadas
(mañana, en dos semanas, en un mes, el próximo lunes...) para que las use tal cual."""

import calendar
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import Settings

_DAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


# Zona horaria de quien hace la petición (la manda la app: "Europe/Madrid", "America/Bogota"...).
# Sin ella se usa la de Colombia, que es la configurada por defecto.
_request_zone: ContextVar[str | None] = ContextVar("request_zone", default=None)


def set_request_timezone(name: str | None) -> bool:
    """Guarda la zona de esta petición. Devuelve False (y la ignora) si el nombre no existe."""
    if not name:
        _request_zone.set(None)
        return False
    try:
        ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError):
        _request_zone.set(None)
        return False
    _request_zone.set(name.strip())
    return True


def user_timezone(settings: Settings) -> tzinfo:
    """La zona del paciente que hace la petición; si no la mandó, la de Colombia."""
    name = _request_zone.get()
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            pass
    return timezone(timedelta(hours=settings.utc_offset_hours))


def zone_label(settings: Settings) -> str:
    return _request_zone.get() or "Colombia"


def local_now(settings: Settings, now: datetime | None = None) -> datetime:
    """Ahora, en la zona del paciente (con su horario de verano si lo tiene)."""
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(user_timezone(settings))


def add_months(day: date, months: int) -> date:
    """Suma meses calendario; si el día no existe en el mes destino, usa el último (31 ene + 1 mes = 28 feb)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _label(day: date) -> str:
    return f"{day.isoformat()} ({_DAYS[day.weekday()]})"


def relative_dates(today: date) -> str:
    """Fechas relativas ya resueltas, para que el modelo no tenga que hacer cuentas."""
    parts = [
        f"mañana = {_label(today + timedelta(days=1))}",
        f"pasado mañana = {_label(today + timedelta(days=2))}",
    ]
    for weeks in (1, 2, 3):
        parts.append(f"en {weeks} {'semana' if weeks == 1 else 'semanas'} = {_label(today + timedelta(weeks=weeks))}")
    for months in (1, 2, 3, 6):
        parts.append(f"en {months} {'mes' if months == 1 else 'meses'} = {_label(add_months(today, months))}")
    for offset in range(1, 8):  # la próxima vez que cae cada día de la semana (siempre después de hoy)
        day = today + timedelta(days=offset)
        parts.append(f"próximo {_DAYS[day.weekday()]} = {day.isoformat()}")
    return "; ".join(parts)


def today_note(settings: Settings, now: datetime | None = None) -> str:
    moment = local_now(settings, now)
    minutes = int(moment.utcoffset().total_seconds() // 60)
    sign = "+" if minutes >= 0 else "-"
    offset = f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"
    return (
        f"FECHA Y HORA ACTUALES: {_DAYS[moment.weekday()]} {moment.day} de {_MONTHS[moment.month - 1]} "
        f"de {moment.year}, {moment:%H:%M} (hora de {zone_label(settings)}, UTC{offset}). "
        f"Estamos en el año {moment.year}. "
        f"FECHAS YA CALCULADAS (úsalas tal cual, no hagas cuentas de fechas): {relative_dates(moment.date())}. "
        "Las expresiones relativas (\"mañana\", \"la otra semana\", \"en un mes\") se cuentan desde HOY, no desde "
        "la fecha de otra cita ya agendada, salvo que el paciente diga explícitamente \"una semana después de esa cita\". "
        "\"La otra semana\", \"la próxima semana\" o \"la semana que viene\" sin decir el día equivale a \"en 1 semana\" "
        "(el mismo día de la semana que hoy). Si el paciente pide \"a la misma hora\" o \"con el mismo médico\", "
        "copia de la cita anterior solo la hora y el médico, nunca la fecha. "
        "Si el paciente da un día sin año, usa el año actual; si ese día ya pasó este año, usa el siguiente. "
        "Nunca agendes una cita en el pasado."
    )


def is_past(scheduled_at: str, settings: Settings, tolerance: timedelta = timedelta(hours=1)) -> bool | None:
    """True si la fecha ISO ya pasó (con un margen), False si no, None si no se puede leer."""
    try:
        when = datetime.fromisoformat(str(scheduled_at).replace("Z", "+00:00"))
    except ValueError:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=user_timezone(settings))
    return when < datetime.now(timezone.utc) - tolerance
