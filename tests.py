"""Tests unitarios para funciones de calculo y utilidades."""
import unittest
import datetime


class TestFormatoMoneda(unittest.TestCase):
    def setUp(self):
        from utils import formato_moneda_visual, procesar_monto_input
        self.fmt = formato_moneda_visual
        self.proc = procesar_monto_input

    def test_formato_ars(self):
        self.assertEqual(self.fmt(1500.50, "ARS"), "$ 1.500,50")

    def test_formato_usd(self):
        self.assertEqual(self.fmt(250.00, "USD"), "US$ 250,00")

    def test_formato_none(self):
        self.assertEqual(self.fmt(None, "ARS"), "")

    def test_formato_cero(self):
        self.assertEqual(self.fmt(0, "ARS"), "$ 0,00")

    def test_formato_grande(self):
        result = self.fmt(1000000.99, "ARS")
        self.assertIn("1.000.000", result)

    def test_procesar_entero(self):
        self.assertEqual(self.proc(100), 100.0)

    def test_procesar_float(self):
        self.assertEqual(self.proc(99.5), 99.5)

    def test_procesar_string_coma(self):
        self.assertEqual(self.proc("1.500,50"), 1500.5)

    def test_procesar_string_pesos(self):
        self.assertEqual(self.proc("$ 2.000,00"), 2000.0)

    def test_procesar_string_dolares(self):
        self.assertEqual(self.proc("US$ 100,00"), 100.0)

    def test_procesar_vacio(self):
        self.assertEqual(self.proc(""), 0.0)

    def test_procesar_none(self):
        self.assertEqual(self.proc(None), 0.0)


class TestConfig(unittest.TestCase):
    def test_meses_nombres_len(self):
        from config import MESES_NOMBRES
        self.assertEqual(len(MESES_NOMBRES), 12)

    def test_lista_meses_len(self):
        from config import LISTA_MESES_LARGA
        # 10 years * 12 months = 120
        self.assertEqual(len(LISTA_MESES_LARGA), 120)

    def test_indice_mes_actual(self):
        from config import INDICE_MES_ACTUAL, LISTA_MESES_LARGA, MESES_NOMBRES
        hoy = datetime.date.today()
        expected = f"{MESES_NOMBRES[hoy.month - 1]} {hoy.year}"
        if expected in LISTA_MESES_LARGA:
            self.assertEqual(LISTA_MESES_LARGA[INDICE_MES_ACTUAL], expected)

    def test_opciones_pago(self):
        from config import OPCIONES_PAGO
        self.assertIn("Efectivo", OPCIONES_PAGO)
        self.assertIn("Tarjeta de Credito", OPCIONES_PAGO)


class TestSalarios(unittest.TestCase):
    def test_salario_enero_2026(self):
        from logic import calcular_monto_salario_mes
        result = calcular_monto_salario_mes("Enero 2026")
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 341000.0 * 2.5)

    def test_salario_junio_aguinaldo(self):
        from logic import calcular_monto_salario_mes
        result = calcular_monto_salario_mes("Junio 2026")
        base = 367800.0 * 2.5
        self.assertAlmostEqual(result, base * 1.5)

    def test_salario_mes_desconocido(self):
        from logic import calcular_monto_salario_mes
        result = calcular_monto_salario_mes("Enero 2030")
        self.assertIsNone(result)


class TestAuth(unittest.TestCase):
    def test_sha256_hash(self):
        import hashlib
        from auth import check_hashes
        password = "test123"
        sha_hash = hashlib.sha256(password.encode()).hexdigest()
        self.assertTrue(check_hashes(password, sha_hash))

    def test_sha256_wrong_password(self):
        import hashlib
        from auth import check_hashes
        sha_hash = hashlib.sha256("correct".encode()).hexdigest()
        self.assertFalse(check_hashes("wrong", sha_hash))

    def test_bcrypt_hash(self):
        try:
            import bcrypt
            from auth import make_hashes, check_hashes
            password = "test_bcrypt_123"
            hashed = make_hashes(password)
            self.assertTrue(check_hashes(password, hashed))
            self.assertFalse(check_hashes("wrong", hashed))
        except ImportError:
            self.skipTest("bcrypt not installed")


if __name__ == '__main__':
    unittest.main()
