"""Autenticacion: login por GMIN y tokens de sesion.

El rol de cada usuario se define UNICAMENTE en la tabla `usuarios` de la base
de datos, usando el GMIN como llave; el cliente (navegador) nunca puede
elegir ni enviar su propio rol. No se usa contrasena: el acceso se resuelve
100% por la base de datos (esto es una demo; antes de produccion esto debe
reemplazarse por el inicio de sesion corporativo de GM, SSO, y las sesiones
deben moverse a un almacen compartido).
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from datetime import datetime, timedelta

DURACION_SESION_HORAS = 8

# Ajusta este patron al formato ficticio de GMIN que estes usando en pruebas
GMIN_PATTERN = re.compile(r"^[0-9]{9}$")

def formato_gmin_valido(gmin: str) -> bool:
    return bool(GMIN_PATTERN.match(gmin.strip()))

def buscar_usuario_por_gmin(conn: sqlite3.Connection, gmin: str) -> sqlite3.Row | None:
    gmin = gmin.strip()
    return conn.execute(
        "SELECT gmin, nombre, rol, activo FROM usuarios WHERE gmin=?", (gmin,)
    ).fetchone()

def crear_sesion(conn: sqlite3.Connection, gmin: str) -> dict:
    token = secrets.token_urlsafe(32)
    ahora = datetime.now()
    expira = ahora + timedelta(hours=DURACION_SESION_HORAS)
    conn.execute(
        "INSERT INTO sesiones (token, gmin, creado, expira) VALUES (?,?,?,?)",
        (token, gmin, ahora.isoformat(timespec="seconds"), expira.isoformat(timespec="seconds")),
    )
    return {"token": token, "expira": expira.isoformat(timespec="seconds")}

def resolver_sesion(conn: sqlite3.Connection, token: str) -> sqlite3.Row | None:
    row = conn.execute(
        "SELECT s.token, s.expira, u.gmin, u.nombre, u.rol, u.activo FROM sesiones s"
        " JOIN usuarios u ON u.gmin = s.gmin WHERE s.token=?",
        (token,),
    ).fetchone()
    if row is None:
        return None
    if datetime.fromisoformat(row["expira"]) < datetime.now():
        conn.execute("DELETE FROM sesiones WHERE token=?", (token,))
        return None
    if not row["activo"]:
        return None
    return row

def eliminar_sesion(conn: sqlite3.Connection, token: str) -> None:
    conn.execute("DELETE FROM sesiones WHERE token=?", (token,))

def eliminar_sesiones_de(conn: sqlite3.Connection, gmin: str) -> None:
    conn.execute("DELETE FROM sesiones WHERE gmin=?", (gmin,))
