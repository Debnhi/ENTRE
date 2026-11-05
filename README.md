# Entrenamientos y Licencias GPS SLP

Aplicacion web (FastAPI + SQLite + HTML/JS) para licencias de equipo movil/habilidades GSC y validacion medica.
**Datos de demostracion ficticios.** No cargar datos personales reales sin autorizacion y sin anonimizar.

## Ejecutar
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload             # http://127.0.0.1:8000
```
La primera vez crea `data/entrenamientos.db` con datos y cuentas ficticias. Docs de la API: `/docs`.

## Pruebas
```bash
python -m unittest discover -s tests -t .
```

## Seguridad e inicio de sesion
- El rol de cada cuenta se define **unicamente** en la tabla `usuarios` de la base de datos. La pantalla de login **no** tiene selector de rol: solo pide usuario y contrasena.
- Las contrasenas se guardan con PBKDF2-HMAC-SHA256 + salt (`app/auth.py`), nunca en texto plano.
- El login entrega un token de sesion opaco (valido 8 horas); cada endpoint protegido resuelve el rol desde la base de datos a partir de ese token, nunca confia en algo que envie el navegador.
- Bloqueo temporal (60 s) tras 5 intentos fallidos por usuario.
- Un administrador gestiona cuentas y roles desde la vista **Usuarios** (`/api/usuarios`).
- Pendiente antes de produccion: reemplazar este login por el inicio de sesion corporativo de GM (SSO/SAML), mover las sesiones a un almacen compartido y servir la app por HTTPS.

### Cuentas de demostracion (ficticias)
| Usuario | Contraseña | Rol |
|---|---|---|
| admin.demo | Admin#2026! | Administrador |
| instructor.demo | Instr#2026! | Instructor |
| supervisor.demo | Super#2026! | Supervisor |
| medico.demo | Medico#2026! | Servicio médico |

## Reglas implementadas (`app/rules.py`)
| Regla | Valor |
|---|---|
| Vigencia de licencia | fecha del ultimo curso/refresh aprobado + 12 meses calendario |
| Por vencer | <= 30 dias (propuesto, configurable) |
| Calificacion minima | 80 (supuesto: confirmar) |
| Codigo medico 3 | vence a los 12 meses y pasa a 2 (proceso diario + al arrancar) |
| Codigos 1 y 4 | no vencen; solo el medico los cambia |
| Codigo 3 en ambito MPS | se aplica a "Bloqueo de energias peligrosas" y "Bloqueo de Celdas" |
| Cambio de area | cambia centro de costos/grupo; el codigo medico se conserva |
| Rotacion | A/B/C cada 4 semanas (ancla 2026-11-02); D fijo jueves-domingo |
| Bitacora | toda accion de escritura, identificada por usuario (login) |

## Roles
instructor (captura calificaciones) · supervisor (personas, area, solicitudes) · medico (codigos, resolver) · admin (todo, incluida gestion de usuarios).

## Estructura
`app/rules.py` reglas puras · `app/auth.py` hash de contrasenas y sesiones · `app/services.py` logica con BD · `app/main.py` API · `app/static/` interfaz (sin dependencias externas) · `tests/`.

## Pendiente para produccion
SSO corporativo, hosting aprobado por TI/seguridad, importador de Excel anonimizado, respaldo de BD, almacen de sesiones compartido, HTTPS, proceso diario programado (`POST /api/proceso-diario`).
