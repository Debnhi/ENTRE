"""Datos de demostracion 100% ficticios (sin informacion personal real)."""
from __future__ import annotations

from datetime import date, timedelta

from . import db, services

HABILIDADES = [
    "Bloqueo de energias peligrosas",
    "Bloqueo de Celdas",
    "Tugger T-210 y T-224 y carro eléctrico",
    "Dispositivos de Elevacion",
    "Certificacion: Trabajos en Alturas",
]

PERSONAS = [
    ("900000001", "Juan", "CC-1001", "A"),
    ("900000002", "Roberto", "CC-1001", "B"),
    ("900000003", "Karla", "CC-1002", "C"),
    ("900000004", "Javier", "CC-1002", "D"),
    ("900000005", "Liz", "CC-1003", "A"),
    ("900000010", "Admin Demo", "CC-ADMIN", "A"),
    ("900000011", "Instructor Demo", "CC-CAP", "B"),
    ("900000012", "Supervisor Demo", "CC-SUP", "C"),
    ("900000013", "Medico Demo", "CC-MED", "D"),
]

# Cuentas de demostracion: el ROL vive aqui, en la base de datos, y se resuelve
# por GMIN (no se elige en pantalla, y ya no hay contrasena). GMIN ficticios.
USUARIOS_DEMO = [
    ("900000010", "Admin Demo", "admin"),
    ("900000011", "Instructor Demo", "instructor"),
    ("900000012", "Supervisor Demo", "supervisor"),
    ("900000013", "Medico Demo", "medico"),
]

def seed(path=None, hoy: date | None = None) -> bool:
    """Carga datos solo si la base esta vacia. Devuelve True si cargo."""
    hoy = hoy or services.hoy()
    db.init_db(path)
    sistema = services.Usuario("SEED", "Sistema (Seed)", "admin")
    with db.session(path) as conn:
        if conn.execute("SELECT COUNT(*) c FROM personas").fetchone()["c"]:
            return False
        for nombre in HABILIDADES:
            conn.execute("INSERT INTO habilidades (nombre) VALUES (?)", (nombre,))
        hid = {r["nombre"]: r["id"] for r in conn.execute("SELECT * FROM habilidades")}
        for g, n, cc, grp in PERSONAS:
            conn.execute("INSERT INTO personas (gmin, nombre, centro_costos, grupo) VALUES (?,?,?,?)",
                         (g, n, cc, grp))

        def curso(gmin, hab, dias_atras, cal=90.0, tipo="CURSO"):
            services.registrar_curso(conn, sistema, gmin, hid[hab],
                                     hoy - timedelta(days=dias_atras), tipo, cal)

        curso("900000001", HABILIDADES[0], 60)      # vigente
        curso("900000001", HABILIDADES[2], 340)     # por vencer (~25 dias)
        curso("900000002", HABILIDADES[0], 400, tipo="REFRESH")  # vencida
        curso("900000002", HABILIDADES[4], 100)
        curso("900000003", HABILIDADES[3], 20)
        curso("900000003", HABILIDADES[1], 200)
        curso("900000004", HABILIDADES[2], 10, 70.0)  # reprobado: no genera licencia
        curso("900000005", HABILIDADES[0], 359)     # por vencer

        # codigos medicos
        services.asignar_codigo_medico(conn, sistema, "900000001", 4, "GENERAL", hoy - timedelta(days=300))
        services.asignar_codigo_medico(conn, sistema, "900000003", 3, "MPS", hoy - timedelta(days=120))
        services.asignar_codigo_medico(conn, sistema, "900000005", 3, "GENERAL", hoy - timedelta(days=380))

        conn.execute(
            "INSERT INTO solicitudes_medicas (gmin, habilidad_id, motivo, solicitante, fecha_solicitud)"
            " VALUES (?,?,?,?,?)",
            ("900000002", hid[HABILIDADES[4]], "Revalidacion previa a curso de alturas",
             "Supervisor Demo", hoy.isoformat()))

        for gmin, nombre, rol in USUARIOS_DEMO:
            conn.execute(
                "INSERT INTO usuarios (gmin, nombre, rol) VALUES (?,?,?)", (gmin, nombre, rol))

        services.log(conn, sistema, "SEED", "sistema", None, "datos ficticios de demostracion")
    return True

if __name__ == "__main__":
    print("Seed cargado" if seed() else "La base ya tenia datos; no se modifico")
