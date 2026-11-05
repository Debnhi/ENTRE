"""Reglas de negocio puras (sin base de datos) para entrenamientos GPS SLP.

Todas las funciones reciben la fecha de referencia ("hoy") como parametro para
que sean deterministas y faciles de probar.
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta

VIGENCIA_LICENCIA_MESES = 12
VIGENCIA_CODIGO3_MESES = 12
UMBRAL_POR_VENCER_DIAS = 30
CALIFICACION_MINIMA = 80
ANCLA_ROTACION = date(2026, 11, 2)
SEMANAS_POR_ROTACION = 4
HABILIDADES_BLOQUEO_MPS = (
    "Bloqueo de energias peligrosas",
    "Bloqueo de Celdas",
)
CODIGOS_MEDICOS = (1, 2, 3, 4)
CODIGOS_QUE_NO_VENCEN = (1, 4)


def add_months(d: date, months: int) -> date:
    """Suma meses calendario; si el dia no existe usa el ultimo dia del mes."""
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def vigencia_licencia(fecha_curso: date, meses: int = VIGENCIA_LICENCIA_MESES) -> date:
    return add_months(fecha_curso, meses)


def estado_licencia(
    vigencia: date | None, hoy: date, umbral: int = UMBRAL_POR_VENCER_DIAS
) -> str:
    """Estado calculado: SIN_REGISTRO, VENCIDA, POR_VENCER o VIGENTE.

    Nunca se copia el estatus capturado a mano: se calcula siempre por fecha.
    """
    if vigencia is None:
        return "SIN_REGISTRO"
    if vigencia < hoy:
        return "VENCIDA"
    if (vigencia - hoy).days <= umbral:
        return "POR_VENCER"
    return "VIGENTE"


def dias_restantes(vigencia: date | None, hoy: date) -> int | None:
    return None if vigencia is None else (vigencia - hoy).days


def vigencia_codigo_medico(codigo: int, fecha_codigo: date | None) -> date | None:
    """Solo el codigo 3 vence (12 meses). 1 y 4 los cambia unicamente el medico."""
    if codigo == 3 and fecha_codigo is not None:
        return add_months(fecha_codigo, VIGENCIA_CODIGO3_MESES)
    return None


def codigo_medico_efectivo(
    codigo: int, fecha_codigo: date | None, hoy: date
) -> tuple[int, bool]:
    """Devuelve (codigo_efectivo, cambio_automatico).

    Codigo 3 vencido pasa automaticamente a 2.
    """
    vig = vigencia_codigo_medico(codigo, fecha_codigo)
    if vig is not None and vig < hoy:
        return 2, True
    return codigo, False


def aplica_bloqueo_mps(nombre_habilidad: str) -> bool:
    return nombre_habilidad in HABILIDADES_BLOQUEO_MPS


def rotacion_turnos(fecha: date) -> dict:
    """Rotacion de grupos A/B/C cada 4 semanas; grupo D fijo jueves-domingo.

    Los grupos A, B y C ocupan los turnos 1, 2 y 3 y avanzan un lugar en cada
    rotacion (ancla: ANCLA_ROTACION, un lunes).
    """
    dias = (fecha - ANCLA_ROTACION).days
    periodo = dias // (7 * SEMANAS_POR_ROTACION)  # puede ser negativo
    grupos = ["A", "B", "C"]
    asignacion = {
        f"turno_{i + 1}": grupos[(i - periodo) % 3] for i in range(3)
    }
    inicio = ANCLA_ROTACION + timedelta(weeks=SEMANAS_POR_ROTACION * periodo)
    siguiente = inicio + timedelta(weeks=SEMANAS_POR_ROTACION)
    return {
        "fecha": fecha.isoformat(),
        "periodo": periodo,
        "inicio_periodo": inicio.isoformat(),
        "siguiente_rotacion": siguiente.isoformat(),
        "asignacion": asignacion,
        "grupo_d_trabaja": fecha.weekday() in (3, 4, 5, 6),  # jue-dom
    }
