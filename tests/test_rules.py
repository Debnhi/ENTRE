import unittest
from datetime import date

from app import rules


class ReglasTest(unittest.TestCase):
    def test_add_months_fin_de_mes(self):
        self.assertEqual(rules.add_months(date(2025, 2, 28), 12), date(2026, 2, 28))
        self.assertEqual(rules.add_months(date(2024, 2, 29), 12), date(2025, 2, 28))
        self.assertEqual(rules.add_months(date(2025, 8, 31), 6), date(2026, 2, 28))

    def test_estado_licencia(self):
        hoy = date(2026, 11, 4)
        self.assertEqual(rules.estado_licencia(None, hoy), "SIN_REGISTRO")
        self.assertEqual(rules.estado_licencia(date(2026, 11, 3), hoy), "VENCIDA")
        self.assertEqual(rules.estado_licencia(date(2026, 11, 4), hoy), "POR_VENCER")
        self.assertEqual(rules.estado_licencia(date(2026, 12, 4), hoy), "POR_VENCER")
        self.assertEqual(rules.estado_licencia(date(2026, 12, 5), hoy), "VIGENTE")

    def test_codigo3_vence_a_2(self):
        hoy = date(2026, 11, 4)
        self.assertEqual(rules.codigo_medico_efectivo(3, date(2025, 11, 4), hoy), (3, False))
        self.assertEqual(rules.codigo_medico_efectivo(3, date(2025, 11, 3), hoy), (2, True))

    def test_codigos_1_y_4_no_vencen(self):
        hoy = date(2030, 1, 1)
        for c in (1, 4):
            self.assertEqual(rules.codigo_medico_efectivo(c, date(2020, 1, 1), hoy), (c, False))

    def test_rotacion(self):
        r0 = rules.rotacion_turnos(date(2026, 11, 2))
        self.assertEqual(r0["asignacion"], {"turno_1": "A", "turno_2": "B", "turno_3": "C"})
        self.assertEqual(r0["siguiente_rotacion"], "2026-11-30")
        r1 = rules.rotacion_turnos(date(2026, 11, 30))
        self.assertEqual(r1["periodo"], 1)
        self.assertEqual(r1["asignacion"], {"turno_1": "C", "turno_2": "A", "turno_3": "B"})
        rm = rules.rotacion_turnos(date(2026, 11, 1))
        self.assertEqual(rm["periodo"], -1)

    def test_grupo_d_jueves_a_domingo(self):
        self.assertFalse(rules.rotacion_turnos(date(2026, 11, 4))["grupo_d_trabaja"])  # miercoles
        self.assertTrue(rules.rotacion_turnos(date(2026, 11, 5))["grupo_d_trabaja"])   # jueves
        self.assertTrue(rules.rotacion_turnos(date(2026, 11, 8))["grupo_d_trabaja"])   # domingo
        self.assertFalse(rules.rotacion_turnos(date(2026, 11, 9))["grupo_d_trabaja"])  # lunes


if __name__ == "__main__":
    unittest.main()
