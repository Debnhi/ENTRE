"""API FastAPI + interfaz web estatica.

Seguridad del login (resumen):
- El cliente NUNCA envia ni elige su rol. Solo envia su GMIN en
  /api/auth/login y recibe un token de sesion opaco.
- Cada endpoint protegido resuelve el token contra la tabla `sesiones` y
  obtiene el rol desde la tabla `usuarios` (ver auth.resolver_sesion).
- El acceso depende 100% de que el GMIN exista en la tabla `usuarios`
  (que a su vez depende de que exista en `personas`). No hay contrasena.
Esto es una base razonable para una demo interna; antes de produccion debe
integrarse con el inicio de sesion corporativo (SSO) de GM.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.security.utils import get_authorization_scheme_param
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import auth, db, rules, seed as seed_mod, services
from .services import Usuario

STATIC = Path(__file__).resolve().parent / "static"
ROLES = ("instructor", "supervisor", "medico", "admin")


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_mod.seed()
    with db.session() as conn:
                services.proceso_diario(conn, Usuario("SEED", "Sistema", "admin"), services.hoy())
    yield


app = FastAPI(title="Entrenamientos y Licencias GPS SLP", version="0.2.0", lifespan=lifespan)


# ---------------------------------------------------------------- dependencias
def get_conn():
    conn = db.connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def usuario_actual(authorization: str | None = Header(default=None),
                   conn: sqlite3.Connection = Depends(get_conn)) -> Usuario:
    scheme, token = get_authorization_scheme_param(authorization or "")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sesion no iniciada")
    row = auth.resolver_sesion(conn, token)
    if row is None:
        raise HTTPException(401, "La sesion no es valida o ya expiro")
    return Usuario(row["gmin"], row["nombre"], row["rol"])



def requiere(*roles: str):
    def dep(user: Usuario = Depends(usuario_actual)) -> Usuario:
        if user.rol != "admin" and user.rol not in roles:
            raise HTTPException(403, f"El rol '{user.rol}' no puede realizar esta accion")
        return user
    return dep


# --------------------------------------------------------------------- modelos
class LoginIn(BaseModel):
    gmin: str = Field(pattern=r"^\d{6,10}$")

class UsuarioIn(BaseModel):
    gmin: str = Field(pattern=r"^\d{6,10}$")
    rol: Literal["instructor", "supervisor", "medico", "admin"]



class UsuarioPatchIn(BaseModel):
    rol: Literal["instructor", "supervisor", "medico", "admin"] | None = None
    activo: bool | None = None


class PersonaIn(BaseModel):
    gmin: str = Field(pattern=r"^\d{6,10}$")
    nombre: str = Field(min_length=2, max_length=120)
    centro_costos: str = Field(min_length=1, max_length=30)
    grupo: Literal["A", "B", "C", "D"]


class CambioAreaIn(BaseModel):
    centro_costos: str = Field(min_length=1, max_length=30)
    grupo: Literal["A", "B", "C", "D"]


class CursoIn(BaseModel):
    gmin: str
    habilidad_id: int
    fecha: date
    tipo: Literal["CURSO", "REFRESH"] = "CURSO"
    calificacion: float = Field(ge=0, le=100)


class SolicitudIn(BaseModel):
    gmin: str
    habilidad_id: int | None = None
    motivo: str = Field(min_length=3, max_length=300)


class ResolverIn(BaseModel):
    codigo: Literal[1, 2, 3, 4]
    ambito: Literal["GENERAL", "MPS"] = "GENERAL"
    comentario: str | None = Field(default=None, max_length=300)


class CodigoIn(BaseModel):
    codigo: Literal[1, 2, 3, 4]
    ambito: Literal["GENERAL", "MPS"] = "GENERAL"


# ------------------------------------------------------------------- auth api
@app.post("/api/auth/login")
def login(body: LoginIn, conn: sqlite3.Connection = Depends(get_conn)):
    gmin = body.gmin.strip()
    if not auth.formato_gmin_valido(gmin):
        raise HTTPException(422, "Formato de GMIN invalido")
    row = auth.buscar_usuario_por_gmin(conn, gmin)
    if not row or not row["activo"]:
        services.log(conn, Usuario(gmin, "desconocido", "desconocido"), "LOGIN_FALLIDO", "usuario", gmin)
        raise HTTPException(401, "GMIN no encontrado o sin acceso")
    sesion = auth.crear_sesion(conn, gmin)
    services.log(conn, Usuario(gmin, row["nombre"], row["rol"]), "LOGIN", "usuario", gmin)
    return {"token": sesion["token"], "expira": sesion["expira"], "gmin": gmin,
            "nombre": row["nombre"], "rol": row["rol"]}

@app.get("/api/auth/me")
def me(user: Usuario = Depends(usuario_actual)):
    return {"gmin": user.gmin, "nombre": user.nombre, "rol": user.rol}

@app.post("/api/auth/logout")
def logout(authorization: str | None = Header(default=None),
          conn: sqlite3.Connection = Depends(get_conn), user: Usuario = Depends(usuario_actual)):
    _, token = get_authorization_scheme_param(authorization or "")
    auth.eliminar_sesion(conn, token)
    services.log(conn, user, "LOGOUT", "usuario", user.gmin)
    return {"ok": True}



# ----------------------------------------------------------- administracion
@app.get("/api/usuarios")
def get_usuarios(conn: sqlite3.Connection = Depends(get_conn), _: Usuario = Depends(requiere("admin"))):
    return [dict(r) for r in conn.execute(
        "SELECT gmin, nombre, rol, activo, creado FROM usuarios ORDER BY gmin")]

@app.post("/api/usuarios", status_code=201)
def crear_usuario(body: UsuarioIn, conn: sqlite3.Connection = Depends(get_conn),
                  user: Usuario = Depends(requiere("admin"))):
    gmin = body.gmin.strip()
    persona = conn.execute("SELECT nombre FROM personas WHERE gmin=?", (gmin,)).fetchone()
    if not persona:
        raise HTTPException(404, "No existe una persona con ese GMIN; crea primero su registro en Personas")
    try:
        conn.execute(
            "INSERT INTO usuarios (gmin, nombre, rol) VALUES (?,?,?)",
            (gmin, persona["nombre"], body.rol))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ese GMIN ya tiene una cuenta de acceso")
    services.log(conn, user, "ALTA_USUARIO", "usuario", gmin, f"rol={body.rol}")
    return {"gmin": gmin}

@app.patch("/api/usuarios/{gmin}")
def editar_usuario(gmin: str, body: UsuarioPatchIn, conn: sqlite3.Connection = Depends(get_conn),
                   user: Usuario = Depends(requiere("admin"))):
    gmin = gmin.strip()
    row = conn.execute("SELECT * FROM usuarios WHERE gmin=?", (gmin,)).fetchone()
    if not row:
        raise HTTPException(404, "Usuario no encontrado")
    if gmin == user.gmin and body.activo is False:
        raise HTTPException(400, "No puedes desactivar tu propia cuenta")
    nuevo_rol = body.rol or row["rol"]
    nuevo_activo = row["activo"] if body.activo is None else int(body.activo)
    conn.execute("UPDATE usuarios SET rol=?, activo=? WHERE gmin=?", (nuevo_rol, nuevo_activo, gmin))
    if nuevo_activo == 0:
        auth.eliminar_sesiones_de(conn, gmin)
    services.log(conn, user, "EDITAR_USUARIO", "usuario", gmin,
                 f"rol {row['rol']}->{nuevo_rol}, activo {row['activo']}->{nuevo_activo}")
    return {"gmin": gmin, "rol": nuevo_rol, "activo": bool(nuevo_activo)}



# ------------------------------------------------------------------ endpoints
@app.get("/api/salud")
def salud():
    return {"ok": True, "hoy": services.hoy().isoformat()}


@app.get("/api/config")
def config():
    return {
        "vigencia_licencia_meses": rules.VIGENCIA_LICENCIA_MESES,
        "umbral_por_vencer_dias": rules.UMBRAL_POR_VENCER_DIAS,
        "calificacion_minima": rules.CALIFICACION_MINIMA,
        "vigencia_codigo3_meses": rules.VIGENCIA_CODIGO3_MESES,
        "ancla_rotacion": rules.ANCLA_ROTACION.isoformat(),
        "roles": ROLES,
    }


@app.get("/api/resumen")
def get_resumen(conn: sqlite3.Connection = Depends(get_conn), _: Usuario = Depends(usuario_actual)):
    return services.resumen(conn, services.hoy())


@app.get("/api/rotacion")
def get_rotacion(fecha: date | None = None, _: Usuario = Depends(usuario_actual)):
    return rules.rotacion_turnos(fecha or services.hoy())


@app.get("/api/habilidades")
def get_habilidades(conn: sqlite3.Connection = Depends(get_conn), _: Usuario = Depends(usuario_actual)):
    return [dict(r) for r in conn.execute("SELECT * FROM habilidades ORDER BY nombre")]


@app.get("/api/personas")
def get_personas(q: str = "", grupo: str = "", conn: sqlite3.Connection = Depends(get_conn),
                 _: Usuario = Depends(usuario_actual)):
    sql = "SELECT * FROM personas WHERE activo=1"
    args: list = []
    if q:
        sql += " AND (gmin LIKE ? OR nombre LIKE ? OR centro_costos LIKE ?)"
        args += [f"%{q}%"] * 3
    if grupo:
        sql += " AND grupo=?"
        args.append(grupo)
    hoy = services.hoy()
    out = []
    for p in conn.execute(sql + " ORDER BY gmin", args):
        d = dict(p)
        cod, auto = rules.codigo_medico_efectivo(
            p["codigo_medico"],
            date.fromisoformat(p["fecha_codigo_medico"]) if p["fecha_codigo_medico"] else None, hoy)
        vig = rules.vigencia_codigo_medico(
            p["codigo_medico"], date.fromisoformat(p["fecha_codigo_medico"]) if p["fecha_codigo_medico"] else None)
        d.update(codigo_medico_efectivo=cod, vigencia_codigo_medico=vig.isoformat() if vig else None)
        out.append(d)
    return out


@app.post("/api/personas", status_code=201)
def crear_persona(body: PersonaIn, conn: sqlite3.Connection = Depends(get_conn),
                  user: Usuario = Depends(requiere("supervisor"))):
    try:
        conn.execute("INSERT INTO personas (gmin, nombre, centro_costos, grupo) VALUES (?,?,?,?)",
                     (body.gmin, body.nombre, body.centro_costos, body.grupo))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Ya existe una persona con ese GMIN")
    services.log(conn, user, "ALTA", "persona", body.gmin, f"{body.centro_costos}/{body.grupo}")
    return {"gmin": body.gmin}


@app.get("/api/personas/{gmin}")
def get_persona(gmin: str, conn: sqlite3.Connection = Depends(get_conn),
                _: Usuario = Depends(usuario_actual)):
    p = conn.execute("SELECT * FROM personas WHERE gmin=?", (gmin,)).fetchone()
    if not p:
        raise HTTPException(404, "Persona no encontrada")
    hoy = services.hoy()
    fecha = date.fromisoformat(p["fecha_codigo_medico"]) if p["fecha_codigo_medico"] else None
    cod, _auto = rules.codigo_medico_efectivo(p["codigo_medico"], fecha, hoy)
    vig = rules.vigencia_codigo_medico(p["codigo_medico"], fecha)
    cursos = [dict(r) for r in conn.execute(
        "SELECT c.*, h.nombre habilidad FROM cursos c JOIN habilidades h ON h.id=c.habilidad_id"
        " WHERE gmin=? ORDER BY fecha DESC, c.id DESC", (gmin,))]
    return {
        "persona": {**dict(p), "codigo_medico_efectivo": cod,
                    "vigencia_codigo_medico": vig.isoformat() if vig else None},
        "licencias": services.licencias_de_persona(conn, gmin, hoy),
        "cursos": cursos,
    }


@app.patch("/api/personas/{gmin}/area")
def cambiar_area(gmin: str, body: CambioAreaIn, conn: sqlite3.Connection = Depends(get_conn),
                 user: Usuario = Depends(requiere("supervisor"))):
    p = conn.execute("SELECT * FROM personas WHERE gmin=?", (gmin,)).fetchone()
    if not p:
        raise HTTPException(404, "Persona no encontrada")
    # La validacion medica sigue a la persona: solo cambian centro de costos y grupo.
    conn.execute("UPDATE personas SET centro_costos=?, grupo=? WHERE gmin=?",
                 (body.centro_costos, body.grupo, gmin))
    services.log(conn, user, "CAMBIO_AREA", "persona", gmin,
                 f"{p['centro_costos']}/{p['grupo']} -> {body.centro_costos}/{body.grupo}"
                 f" (codigo medico {p['codigo_medico']} se conserva)")
    return {"gmin": gmin, "centro_costos": body.centro_costos, "grupo": body.grupo,
            "codigo_medico": p["codigo_medico"]}


@app.post("/api/personas/{gmin}/codigo-medico")
def cambiar_codigo(gmin: str, body: CodigoIn, conn: sqlite3.Connection = Depends(get_conn),
                   user: Usuario = Depends(requiere("medico"))):
    try:
        return services.asignar_codigo_medico(conn, user, gmin, body.codigo, body.ambito, services.hoy())
    except LookupError as e:
        raise HTTPException(404, str(e))


@app.get("/api/licencias")
def get_licencias(q: str = "", estado: str = "", habilidad_id: int | None = None,
                  conn: sqlite3.Connection = Depends(get_conn), _: Usuario = Depends(usuario_actual)):
    rows = services.licencias_registradas(conn, services.hoy())
    if q:
        ql = q.lower()
        rows = [r for r in rows if ql in r["gmin"] or ql in r["nombre"].lower()
                or ql in r["habilidad"].lower() or ql in r["centro_costos"].lower()]
    if estado:
        rows = [r for r in rows if r["estado"] == estado]
    if habilidad_id:
        rows = [r for r in rows if r["habilidad_id"] == habilidad_id]
    order = {"VENCIDA": 0, "POR_VENCER": 1, "VIGENTE": 2}
    rows.sort(key=lambda r: (order[r["estado"]], r["vigencia"] or ""))
    return rows


@app.get("/api/licencias.csv")
def licencias_csv(conn: sqlite3.Connection = Depends(get_conn), user: Usuario = Depends(usuario_actual)):
    rows = services.licencias_registradas(conn, services.hoy())
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["GMIN", "Nombre", "Centro costos", "Grupo", "Habilidad", "Fecha curso",
                "Vigencia", "Dias restantes", "Estado", "Codigo medico"])
    for r in rows:
        w.writerow([r["gmin"], r["nombre"], r["centro_costos"], r["grupo"], r["habilidad"],
                    r["fecha_curso"], r["vigencia"], r["dias_restantes"], r["estado"], r["medico"]["codigo"]])
    services.log(conn, user, "EXPORTAR_CSV", "licencias", None, f"{len(rows)} filas")
    return Response(buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=licencias.csv"})


@app.post("/api/cursos", status_code=201)
def capturar_curso(body: CursoIn, conn: sqlite3.Connection = Depends(get_conn),
                   user: Usuario = Depends(requiere("instructor"))):
    if body.fecha > services.hoy():
        raise HTTPException(422, "La fecha del curso no puede ser futura")
    try:
        return services.registrar_curso(conn, user, body.gmin, body.habilidad_id,
                                        body.fecha, body.tipo, body.calificacion)
    except LookupError as e:
        raise HTTPException(404, str(e))


@app.get("/api/solicitudes-medicas")
def get_solicitudes(estado: str = "", conn: sqlite3.Connection = Depends(get_conn),
                    _: Usuario = Depends(usuario_actual)):
    sql = ("SELECT s.*, p.nombre, h.nombre habilidad FROM solicitudes_medicas s"
           " JOIN personas p ON p.gmin=s.gmin LEFT JOIN habilidades h ON h.id=s.habilidad_id")
    args: list = []
    if estado:
        sql += " WHERE s.estado=?"
        args.append(estado)
    return [dict(r) for r in conn.execute(sql + " ORDER BY s.id DESC", args)]


@app.post("/api/solicitudes-medicas", status_code=201)
def crear_solicitud(body: SolicitudIn, conn: sqlite3.Connection = Depends(get_conn),
                    user: Usuario = Depends(requiere("supervisor", "instructor"))):
    if not conn.execute("SELECT 1 FROM personas WHERE gmin=?", (body.gmin,)).fetchone():
        raise HTTPException(404, "Persona no encontrada")
    cur = conn.execute(
        "INSERT INTO solicitudes_medicas (gmin, habilidad_id, motivo, solicitante, fecha_solicitud)"
        " VALUES (?,?,?,?,?)",
        (body.gmin, body.habilidad_id, body.motivo, user.nombre, services.hoy().isoformat()))
    services.log(conn, user, "SOLICITUD_MEDICA", "solicitud", str(cur.lastrowid),
                 f"{body.gmin}: {body.motivo}")
    return {"id": cur.lastrowid}


@app.post("/api/solicitudes-medicas/{sid}/resolver")
def resolver_solicitud(sid: int, body: ResolverIn, conn: sqlite3.Connection = Depends(get_conn),
                       user: Usuario = Depends(requiere("medico"))):
    s = conn.execute("SELECT * FROM solicitudes_medicas WHERE id=?", (sid,)).fetchone()
    if not s:
        raise HTTPException(404, "Solicitud no encontrada")
    if s["estado"] == "RESUELTA":
        raise HTTPException(409, "La solicitud ya fue resuelta")
    hoy = services.hoy()
    res = services.asignar_codigo_medico(conn, user, s["gmin"], body.codigo, body.ambito, hoy,
                                         detalle_origen=f"solicitud {sid}")
    conn.execute(
        "UPDATE solicitudes_medicas SET estado='RESUELTA', codigo_asignado=?, medico=?,"
        " fecha_resolucion=?, comentario=? WHERE id=?",
        (body.codigo, user.nombre, hoy.isoformat(), body.comentario, sid))
    services.log(conn, user, "RESOLVER_SOLICITUD", "solicitud", str(sid), f"codigo {body.codigo}")
    return res


@app.post("/api/proceso-diario")
def post_proceso_diario(conn: sqlite3.Connection = Depends(get_conn),
                        user: Usuario = Depends(requiere("supervisor", "medico"))):
    return services.proceso_diario(conn, user, services.hoy())


@app.get("/api/bitacora")
def get_bitacora(limit: int = Query(200, le=1000), entidad: str = "",
                 conn: sqlite3.Connection = Depends(get_conn), _: Usuario = Depends(usuario_actual)):
    sql = "SELECT * FROM bitacora"
    args: list = []
    if entidad:
        sql += " WHERE entidad=?"
        args.append(entidad)
    return [dict(r) for r in conn.execute(sql + " ORDER BY id DESC LIMIT ?", args + [limit])]


# ------------------------------------------------------------------- frontend
@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
