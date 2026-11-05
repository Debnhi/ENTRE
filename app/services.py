"""Logica de aplicacion: combina reglas puras con la base de datos."""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime

from . import rules


class Usuario:
    """Identidad resuelta del lado del servidor: gmin (login) + nombre + rol.

    El rol SIEMPRE viene de la tabla `usuarios` (ver auth.resolver_sesion).
    Nunca se construye a partir de algo que envie el cliente sin validar.
    """

    def __init__(self, gmin: str, nombre: str, rol: str):
        self.gmin = gmin      # identificador unico, se usa en la bitacora
        self.nombre = nombre  # nombre para mostrar (ej. como "instructor" en cursos)
        self.rol = rol


def hoy() -> date:
    override = os.environ.get("GPS_HOY")
    return date.fromisoformat(override) if override else date.today()


def log(conn: sqlite3.Connection, user: Usuario, accion: str, entidad: str,
        referencia: str | None = None, detalle: str | None = None) -> None:
    conn.execute(
        "INSERT INTO bitacora (ts, gmin, rol, accion, entidad, referencia, detalle)"
        " VALUES (?,?,?,?,?,?,?)",
        (datetime.now().isoformat(timespec="seconds"), user.gmin, user.rol,
         accion, entidad, referencia, detalle),
    )




# ---------------------------------------------------------------- licencias
def _ultimo_curso_aprobado(conn: sqlite3.Connection, gmin: str, habilidad_id: int):
    return conn.execute(
        "SELECT * FROM cursos WHERE gmin=? AND habilidad_id=? AND aprobado=1"
        " ORDER BY fecha DESC, id DESC LIMIT 1",
        (gmin, habilidad_id),
    ).fetchone()


def _medico_para_habilidad(persona: sqlite3.Row, restr: dict, habilidad_id: int, hoy_: date) -> dict:
    cod, auto = rules.codigo_medico_efectivo(
        persona["codigo_medico"],
        date.fromisoformat(persona["fecha_codigo_medico"]) if persona["fecha_codigo_medico"] else None,
        hoy_,
    )
    if habilidad_id in restr:
        return {"codigo": restr[habilidad_id]["codigo"], "origen": restr[habilidad_id]["origen"]}
    return {"codigo": cod, "origen": "PERSONA"}


def licencias_de_persona(conn: sqlite3.Connection, gmin: str, hoy_: date) -> list[dict]:
    persona = conn.execute("SELECT * FROM personas WHERE gmin=?", (gmin,)).fetchone()
    if persona is None:
        return []
    restr = {
        r["habilidad_id"]: r
        for r in conn.execute("SELECT * FROM restricciones_medicas WHERE gmin=?", (gmin,))
    }
    out = []
    for h in conn.execute("SELECT * FROM habilidades ORDER BY nombre"):
        curso = _ultimo_curso_aprobado(conn, gmin, h["id"])
        vig = None
        fecha_curso = None
        if curso:
            fecha_curso = date.fromisoformat(curso["fecha"])
            vig = rules.vigencia_licencia(fecha_curso, h["vigencia_meses"])
        out.append({
            "gmin": gmin,
            "nombre": persona["nombre"],
            "centro_costos": persona["centro_costos"],
            "grupo": persona["grupo"],
            "habilidad_id": h["id"],
            "habilidad": h["nombre"],
            "fecha_curso": fecha_curso.isoformat() if fecha_curso else None,
            "tipo": curso["tipo"] if curso else None,
            "calificacion": curso["calificacion"] if curso else None,
            "vigencia": vig.isoformat() if vig else None,
            "dias_restantes": rules.dias_restantes(vig, hoy_),
            "estado": rules.estado_licencia(vig, hoy_),
            "medico": _medico_para_habilidad(persona, restr, h["id"], hoy_),
        })
    return out


def licencias_registradas(conn: sqlite3.Connection, hoy_: date) -> list[dict]:
    """Solo pares persona+habilidad con al menos un curso aprobado, personas activas."""
    rows = []
    gmins = [r["gmin"] for r in conn.execute(
        "SELECT DISTINCT p.gmin FROM personas p JOIN cursos c ON c.gmin=p.gmin"
        " WHERE p.activo=1 AND c.aprobado=1 ORDER BY p.gmin")]
    for g in gmins:
        rows.extend(l for l in licencias_de_persona(conn, g, hoy_) if l["estado"] != "SIN_REGISTRO")
    return rows


def registrar_curso(conn: sqlite3.Connection, user: Usuario, gmin: str, habilidad_id: int,
                    fecha: date, tipo: str, calificacion: float) -> dict:
    p = conn.execute("SELECT * FROM personas WHERE gmin=?", (gmin,)).fetchone()
    if p is None:
        raise LookupError("Persona no encontrada")
    h = conn.execute("SELECT * FROM habilidades WHERE id=?", (habilidad_id,)).fetchone()
    if h is None:
        raise LookupError("Habilidad no encontrada")
    aprobado = calificacion >= rules.CALIFICACION_MINIMA
    cur = conn.execute(
        "INSERT INTO cursos (gmin, habilidad_id, fecha, tipo, calificacion, aprobado, instructor)"
        " VALUES (?,?,?,?,?,?,?)",
        (gmin, habilidad_id, fecha.isoformat(), tipo, calificacion, int(aprobado), user.nombre),
    )
    vig = rules.vigencia_licencia(fecha, h["vigencia_meses"]) if aprobado else None
    log(conn, user, "CAPTURA_CALIFICACION", "curso", f"{gmin}/{h['nombre']}",
        f"{tipo} {fecha} cal={calificacion} {'APROBADO' if aprobado else 'REPROBADO'}"
        + (f" vigencia={vig}" if vig else ""))
    return {"id": cur.lastrowid, "aprobado": aprobado,
            "vigencia": vig.isoformat() if vig else None,
            "minimo": rules.CALIFICACION_MINIMA}


# ------------------------------------------------------------------- medico
def asignar_codigo_medico(conn: sqlite3.Connection, user: Usuario, gmin: str, codigo: int,
                          ambito: str, fecha: date, detalle_origen: str = "MEDICO") -> dict:
    p = conn.execute("SELECT * FROM personas WHERE gmin=?", (gmin,)).fetchone()
    if p is None:
        raise LookupError("Persona no encontrada")
    anterior = p["codigo_medico"]
    conn.execute(
        "UPDATE personas SET codigo_medico=?, fecha_codigo_medico=?, ambito_codigo_medico=? WHERE gmin=?",
        (codigo, fecha.isoformat(), ambito, gmin),
    )
    # un nuevo codigo reemplaza las restricciones automaticas previas
    conn.execute("DELETE FROM restricciones_medicas WHERE gmin=? AND origen='MPS_AUTO'", (gmin,))
    aplicadas = []
    if codigo == 3 and ambito == "MPS":
        for nombre in rules.HABILIDADES_BLOQUEO_MPS:
            h = conn.execute("SELECT id FROM habilidades WHERE nombre=?", (nombre,)).fetchone()
            if h:
                conn.execute(
                    "INSERT OR REPLACE INTO restricciones_medicas (gmin, habilidad_id, codigo, origen, fecha)"
                    " VALUES (?,?,?,?,?)", (gmin, h["id"], 3, "MPS_AUTO", fecha.isoformat()))
                aplicadas.append(nombre)
    log(conn, user, "CODIGO_MEDICO", "persona", gmin,
        f"{anterior}->{codigo} ambito={ambito} origen={detalle_origen}"
        + (f" auto-aplicado a: {', '.join(aplicadas)}" if aplicadas else ""))
    vig = rules.vigencia_codigo_medico(codigo, fecha)
    return {"gmin": gmin, "codigo": codigo, "vigencia": vig.isoformat() if vig else None,
            "restricciones_automaticas": aplicadas}


def proceso_diario(conn: sqlite3.Connection, user: Usuario, hoy_: date) -> dict:
    """Aplica reglas automaticas: codigo 3 vencido -> 2 (bitacora por cada cambio)."""
    cambios = []
    for p in conn.execute("SELECT * FROM personas WHERE activo=1 AND codigo_medico=3").fetchall():
        fecha = date.fromisoformat(p["fecha_codigo_medico"]) if p["fecha_codigo_medico"] else None
        nuevo, auto = rules.codigo_medico_efectivo(3, fecha, hoy_)
        if auto:
            conn.execute(
                "UPDATE personas SET codigo_medico=2, fecha_codigo_medico=? WHERE gmin=?",
                (hoy_.isoformat(), p["gmin"]))
            conn.execute("DELETE FROM restricciones_medicas WHERE gmin=? AND origen='MPS_AUTO'", (p["gmin"],))
            log(conn, user, "CODIGO_MEDICO_AUTO", "persona", p["gmin"],
                f"3->2 por vencimiento de 12 meses (asignado {p['fecha_codigo_medico']})")
            cambios.append(p["gmin"])
    log(conn, user, "PROCESO_DIARIO", "sistema", hoy_.isoformat(), f"codigos 3->2: {len(cambios)}")
    return {"fecha": hoy_.isoformat(), "codigos_3_a_2": cambios}


# ------------------------------------------------------------------ resumen
def resumen(conn: sqlite3.Connection, hoy_: date) -> dict:
    lic = licencias_registradas(conn, hoy_)
    conteo = {"VIGENTE": 0, "POR_VENCER": 0, "VENCIDA": 0}
    por_hab: dict[str, dict] = {}
    for l in lic:
        conteo[l["estado"]] += 1
        d = por_hab.setdefault(l["habilidad"], {"VIGENTE": 0, "POR_VENCER": 0, "VENCIDA": 0})
        d[l["estado"]] += 1
    personas = conn.execute("SELECT COUNT(*) c FROM personas WHERE activo=1").fetchone()["c"]
    medicos = {r["codigo_medico"]: r["c"] for r in conn.execute(
        "SELECT codigo_medico, COUNT(*) c FROM personas WHERE activo=1 GROUP BY codigo_medico")}
    pend = conn.execute("SELECT COUNT(*) c FROM solicitudes_medicas WHERE estado='PENDIENTE'").fetchone()["c"]
    c3_por_vencer = []
    for p in conn.execute("SELECT * FROM personas WHERE activo=1 AND codigo_medico=3"):
        vig = rules.vigencia_codigo_medico(3, date.fromisoformat(p["fecha_codigo_medico"])) if p["fecha_codigo_medico"] else None
        if vig and (vig - hoy_).days <= rules.UMBRAL_POR_VENCER_DIAS:
            c3_por_vencer.append({"gmin": p["gmin"], "nombre": p["nombre"], "vigencia": vig.isoformat()})
    return {
        "fecha": hoy_.isoformat(),
        "personas_activas": personas,
        "licencias": conteo,
        "por_habilidad": [{"habilidad": k, **v} for k, v in sorted(por_hab.items())],
        "codigos_medicos": {str(k): medicos.get(k, 0) for k in rules.CODIGOS_MEDICOS},
        "solicitudes_pendientes": pend,
        "codigo3_por_vencer": c3_por_vencer,
        "rotacion": rules.rotacion_turnos(hoy_),
    }
