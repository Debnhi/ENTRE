import os
import tempfile
import unittest

_tmp = tempfile.mkdtemp()
os.environ["GPS_DB_PATH"] = os.path.join(_tmp, "test.db")
os.environ["GPS_HOY"] = "2026-11-04"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

CREDS = {
    "instructor": ("instructor.demo", "Instr#2026!"),
    "supervisor": ("supervisor.demo", "Super#2026!"),
    "medico": ("medico.demo", "Medico#2026!"),
    "admin": ("admin.demo", "Admin#2026!"),
}


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._ctx = TestClient(app)
        cls.c = cls._ctx.__enter__()
        cls.tok = {}
        for rol, (usuario, password) in CREDS.items():
            r = cls.c.post("/api/auth/login", json={"usuario": usuario, "password": password})
            assert r.status_code == 200, r.text
            cls.tok[rol] = r.json()["token"]

    @classmethod
    def tearDownClass(cls):
        cls._ctx.__exit__(None, None, None)

    def h(self, rol):
        return {"Authorization": f"Bearer {self.tok[rol]}"}

    # --------------------------------------------------------- autenticacion
    def test_requiere_identificacion(self):
        self.assertEqual(self.c.get("/api/resumen").status_code, 401)
        self.assertEqual(self.c.get("/api/resumen", headers={"Authorization": "Bearer token-invalido"}).status_code, 401)

    def test_login_incorrecto_no_revela_si_el_usuario_existe(self):
        r1 = self.c.post("/api/auth/login", json={"usuario": "instructor.demo", "password": "mala"})
        r2 = self.c.post("/api/auth/login", json={"usuario": "no.existe.xyz", "password": "mala"})
        self.assertEqual(r1.status_code, 401)
        self.assertEqual(r2.status_code, 401)
        self.assertEqual(r1.json()["detail"], r2.json()["detail"])

    def test_bloqueo_tras_intentos_fallidos(self):
        usuario = "medico.demo"
        for _ in range(6):
            self.c.post("/api/auth/login", json={"usuario": usuario, "password": "mala"})
        r = self.c.post("/api/auth/login", json={"usuario": usuario, "password": "mala"})
        self.assertEqual(r.status_code, 429)
        # restaurar para el resto de pruebas de esta clase (nuevo login valido limpia el contador)
        from app import auth
        auth.limpiar_intentos(usuario)

    def test_el_cliente_no_puede_elegir_su_rol(self):
        # ya no existen cabeceras X-Rol: solo cuenta el rol resuelto por el servidor
        r = self.c.post("/api/cursos", headers=self.h("supervisor"), json={
            "gmin": "900000001", "habilidad_id": 1, "fecha": "2026-11-01", "calificacion": 90})
        self.assertEqual(r.status_code, 403)

    def test_token_invalidado_al_cerrar_sesion(self):
        r = self.c.post("/api/auth/login", json={"usuario": "instructor.demo", "password": "Instr#2026!"})
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        self.assertEqual(self.c.get("/api/resumen", headers=h).status_code, 200)
        self.c.post("/api/auth/logout", headers=h)
        self.assertEqual(self.c.get("/api/resumen", headers=h).status_code, 401)

    # ---------------------------------------------------------------- reglas
    def test_estado_calculado_no_copiado(self):
        lic = self.c.get("/api/licencias", headers=self.h("supervisor")).json()
        vencida = [l for l in lic if l["gmin"] == "900000002" and l["estado"] == "VENCIDA"]
        self.assertTrue(vencida)

    def test_calificacion_reprobada_no_genera_licencia(self):
        d = self.c.get("/api/personas/900000004", headers=self.h("supervisor")).json()
        tugger = [l for l in d["licencias"] if l["habilidad"].startswith("Tugger")][0]
        self.assertEqual(tugger["estado"], "SIN_REGISTRO")

    def test_captura_aprobada_renueva(self):
        antes = self.c.get("/api/personas/900000005", headers=self.h("supervisor")).json()["licencias"]
        self.assertEqual([x for x in antes if x["habilidad_id"] == 1][0]["estado"], "POR_VENCER")
        r = self.c.post("/api/cursos", headers=self.h("instructor"), json={
            "gmin": "900000005", "habilidad_id": 1, "fecha": "2026-11-03", "tipo": "REFRESH",
            "calificacion": 95})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["vigencia"], "2027-11-03")
        d = self.c.get("/api/personas/900000005", headers=self.h("supervisor")).json()
        self.assertEqual([x for x in d["licencias"] if x["habilidad_id"] == 1][0]["estado"], "VIGENTE")

    def test_fecha_futura_rechazada(self):
        r = self.c.post("/api/cursos", headers=self.h("instructor"), json={
            "gmin": "900000001", "habilidad_id": 1, "fecha": "2027-01-01", "calificacion": 90})
        self.assertEqual(r.status_code, 422)

    def test_codigo3_vencido_pasa_a_2_en_arranque(self):
        p = self.c.get("/api/personas/900000005", headers=self.h("supervisor")).json()["persona"]
        self.assertEqual(p["codigo_medico"], 2)
        bit = self.c.get("/api/bitacora?entidad=persona", headers=self.h("supervisor")).json()
        self.assertTrue(any(b["accion"] == "CODIGO_MEDICO_AUTO" and b["referencia"] == "900000005" for b in bit))

    def test_mps_codigo3_aplica_a_bloqueos(self):
        d = self.c.get("/api/personas/900000003", headers=self.h("supervisor")).json()
        bloq = [l for l in d["licencias"] if l["habilidad"] in ("Bloqueo de energias peligrosas", "Bloqueo de Celdas")]
        self.assertEqual(len(bloq), 2)
        for l in bloq:
            self.assertEqual(l["medico"], {"codigo": 3, "origen": "MPS_AUTO"})

    def test_cambio_area_conserva_codigo_medico(self):
        r = self.c.patch("/api/personas/900000001/area", headers=self.h("supervisor"),
                         json={"centro_costos": "CC-2000", "grupo": "B"})
        self.assertEqual(r.status_code, 200)
        p = self.c.get("/api/personas/900000001", headers=self.h("supervisor")).json()["persona"]
        self.assertEqual(p["codigo_medico"], 4)
        self.assertEqual(p["centro_costos"], "CC-2000")

    def test_flujo_solicitud_medica(self):
        r = self.c.post("/api/solicitudes-medicas", headers=self.h("supervisor"),
                        json={"gmin": "900000004", "motivo": "Revision anual"})
        sid = r.json()["id"]
        self.assertEqual(self.c.post(f"/api/solicitudes-medicas/{sid}/resolver", headers=self.h("supervisor"),
                                     json={"codigo": 1}).status_code, 403)
        ok = self.c.post(f"/api/solicitudes-medicas/{sid}/resolver", headers=self.h("medico"), json={"codigo": 1})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.c.post(f"/api/solicitudes-medicas/{sid}/resolver", headers=self.h("medico"),
                                     json={"codigo": 1}).status_code, 409)

    def test_alta_duplicada(self):
        body = {"gmin": "900000099", "nombre": "Persona Ficticia Nueva", "centro_costos": "CC-9", "grupo": "C"}
        self.assertEqual(self.c.post("/api/personas", headers=self.h("supervisor"), json=body).status_code, 201)
        self.assertEqual(self.c.post("/api/personas", headers=self.h("supervisor"), json=body).status_code, 409)

    def test_csv(self):
        r = self.c.get("/api/licencias.csv", headers=self.h("supervisor"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("GMIN", r.text.splitlines()[0])

    # ------------------------------------------------------- gestion usuarios
    def test_solo_admin_gestiona_usuarios(self):
        self.assertEqual(self.c.get("/api/usuarios", headers=self.h("supervisor")).status_code, 403)
        r = self.c.get("/api/usuarios", headers=self.h("admin"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(u["usuario"] == "instructor.demo" for u in r.json()))

    def test_admin_crea_y_cambia_rol_de_usuario(self):
        body = {"usuario": "nuevo.usuario.test", "nombre": "Persona Nueva", "rol": "instructor", "password": "ClaveTemp#1"}
        self.assertEqual(self.c.post("/api/usuarios", headers=self.h("admin"), json=body).status_code, 201)
        r = self.c.patch("/api/usuarios/nuevo.usuario.test", headers=self.h("admin"), json={"rol": "supervisor"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rol"], "supervisor")
        login = self.c.post("/api/auth/login", json={"usuario": "nuevo.usuario.test", "password": "ClaveTemp#1"})
        self.assertEqual(login.json()["rol"], "supervisor")  # el rol nuevo viene de la BD, no del cliente

    def test_admin_no_puede_desactivarse_a_si_mismo(self):
        r = self.c.patch("/api/usuarios/admin.demo", headers=self.h("admin"), json={"activo": False})
        self.assertEqual(r.status_code, 400)

    def test_desactivar_usuario_cierra_sus_sesiones(self):
        body = {"usuario": "temporal.sesion.test", "nombre": "Temporal", "rol": "instructor", "password": "ClaveTemp#2"}
        self.c.post("/api/usuarios", headers=self.h("admin"), json=body)
        login = self.c.post("/api/auth/login", json={"usuario": "temporal.sesion.test", "password": "ClaveTemp#2"})
        h = {"Authorization": f"Bearer {login.json()['token']}"}
        self.assertEqual(self.c.get("/api/resumen", headers=h).status_code, 200)
        self.c.patch("/api/usuarios/temporal.sesion.test", headers=self.h("admin"), json={"activo": False})
        self.assertEqual(self.c.get("/api/resumen", headers=h).status_code, 401)


if __name__ == "__main__":
    unittest.main()
