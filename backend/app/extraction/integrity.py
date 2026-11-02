"""Que ningún número del documento se pierda ni cambie al pasarlo por un modelo.

Una transcripción que omite filas de una tabla de laboratorio (en una prueba real, un modelo
conservó 16 de los 74 números de una página) hace que la app muestre menos resultados o, peor,
que el asistente conteste con otro valor. Aquí se comprueba que los números del texto original
sigan en la transcripción, y que cada valor extraído exista de verdad en el documento."""

from __future__ import annotations

import re
from collections import Counter

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
MAX_LOST_FRACTION = 0.03   # se tolera perder hasta el 3 % de los números (numeración de listas, etc.)
MIN_TOLERATED = 1


def numbers(text: str) -> Counter:
    """Los números de un texto, con la coma decimal escrita como punto."""
    return Counter(token.replace(",", ".") for token in _NUMBER.findall(text or ""))


def lost_numbers(source: str, output: str) -> list[str]:
    """Números del original que no aparecen (la misma cantidad de veces) en el resultado."""
    have = numbers(output)
    lost: list[str] = []
    for number, count in numbers(source).items():
        missing = count - have.get(number, 0)
        if missing > 0:
            lost.extend([number] * missing)
    return lost


def keeps_the_numbers(source: str, output: str) -> bool:
    total = sum(numbers(source).values())
    return len(lost_numbers(source, output)) <= max(MIN_TOLERATED, int(total * MAX_LOST_FRACTION))


def is_grounded(value_raw: str, source: str) -> bool:
    """¿Los números de este valor están en el texto original? Un valor sin números (p. ej.
    "Negativa") no se puede contrastar y se acepta."""
    wanted = numbers(value_raw)
    if not wanted:
        return True
    present = numbers(source)
    return all(n in present for n in wanted)
