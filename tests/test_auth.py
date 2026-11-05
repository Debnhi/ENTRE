import unittest

from app import auth


class AuthTest(unittest.TestCase):
    def test_hash_y_verificacion(self):
        h, s = auth.hash_password("Clave#2026!")
        self.assertTrue(auth.verify_password("Clave#2026!", h, s))
        self.assertFalse(auth.verify_password("otra-clave", h, s))

    def test_salts_distintos_producen_hashes_distintos(self):
        h1, s1 = auth.hash_password("misma-clave")
        h2, s2 = auth.hash_password("misma-clave")
        self.assertNotEqual(s1, s2)
        self.assertNotEqual(h1, h2)

    def test_bloqueo_por_intentos_fallidos(self):
        usuario = "usuario.prueba.bloqueo"
        auth.limpiar_intentos(usuario)
        for _ in range(auth.MAX_INTENTOS_FALLIDOS):
            self.assertEqual(auth.usuario_bloqueado(usuario), 0)
            auth.registrar_intento_fallido(usuario)
        self.assertGreater(auth.usuario_bloqueado(usuario), 0)
        auth.limpiar_intentos(usuario)
        self.assertEqual(auth.usuario_bloqueado(usuario), 0)


if __name__ == "__main__":
    unittest.main()
