"""Acceso a SQLite (libreria estandar) y esquema."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("GPS_DB_PATH", Path(__file__).resolve().parent.parent / "data" / "entrenamientos.db"))

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS personas (
    gmin TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    centro_costos TEXT NOT NULL,
    grupo TEXT NOT NULL CHECK (grupo IN ('A','B','C','D')),
    activo INTEGER NOT NULL DEFAULT 1,
    codigo_medico INTEGER NOT NULL DEFAULT 1 CHECK (codigo_medico IN (1,2,3,4)),
    fecha_codigo_medico TEXT,
    ambito_codigo_medico TEXT NOT NULL DEFAULT 'GENERAL'
);

CREATE TABLE IF NOT EXISTS habilidades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    vigencia_meses INTEGER NOT NULL DEFAULT 12
);

CREATE TABLE IF NOT EXISTS cursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmin TEXT NOT NULL REFERENCES personas(gmin),
    habilidad_id INTEGER NOT NULL REFERENCES habilidades(id),
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK (tipo IN ('CURSO','REFRESH')),
    calificacion REAL NOT NULL,
    aprobado INTEGER NOT NULL,
    instructor TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cursos_pers_hab ON cursos(gmin, habilidad_id, fecha);

CREATE TABLE IF NOT EXISTS solicitudes_medicas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gmin TEXT NOT NULL REFERENCES personas(gmin),
    habilidad_id INTEGER REFERENCES habilidades(id),
    motivo TEXT NOT NULL,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE' CHECK (estado IN ('PENDIENTE','RESUELTA')),
    solicitante TEXT NOT NULL,
    fecha_solicitud TEXT NOT NULL,
    codigo_asignado INTEGER,
    medico TEXT,
    fecha_resolucion TEXT,
    comentario TEXT
);

CREATE TABLE IF NOT EXISTS restricciones_medicas (
    gmin TEXT NOT NULL REFERENCES personas(gmin),
    habilidad_id INTEGER NOT NULL REFERENCES habilidades(id),
    codigo INTEGER NOT NULL,
    origen TEXT NOT NULL,
    fecha TEXT NOT NULL,
    PRIMARY KEY (gmin, habilidad_id)
);

CREATE TABLE IF NOT EXISTS usuarios (
    gmin TEXT PRIMARY KEY REFERENCES personas(gmin),
    nombre TEXT NOT NULL,
    rol TEXT NOT NULL CHECK (rol IN ('instructor','supervisor','medico','admin')),
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sesiones (
    token TEXT PRIMARY KEY,
    gmin TEXT NOT NULL REFERENCES usuarios(gmin),
    creado TEXT NOT NULL,
    expira TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sesiones_gmin ON sesiones(gmin);

CREATE TABLE IF NOT EXISTS bitacora (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    gmin TEXT NOT NULL,
    rol TEXT NOT NULL,
    accion TEXT NOT NULL,
    entidad TEXT NOT NULL,
    referencia TEXT,
    detalle TEXT
);

"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def session(path: Path | str | None = None):
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: Path | str | None = None) -> None:
    target = Path(path or DB_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    with session(target) as conn:
        conn.executescript(SCHEMA) 
