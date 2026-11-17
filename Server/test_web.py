import io
import unittest
from unittest.mock import patch

from openpyxl import load_workbook
import database
import test_storage


class WebTests(unittest.TestCase):
    def setUp(self):
        test_storage.StorageTests.setUp(self)
        self.defaults['usuarios'] = {'admin': {'pass': 'test', 'area': 'TODAS', 'nombre': 'Admin'},
                                    'jefe': {'pass': 'test', 'area': 'LOGISTICA', 'nombre': 'Jefe'}}
        database.initialize(self.defaults)
        with patch('time_sync.sincronizar_ntp'):
            from run import create_app
            self.app = create_app()
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def login(self, user='admin'):
        response = self.client.post('/login', data={'usuario': user, 'password': 'test'})
        self.assertEqual(response.status_code, 302)

    def test_pages_exports_and_backup(self):
        self.login()
        for page in ['/', '/colaboradores', '/turnos', '/aprobaciones', '/admin/areas',
                     '/admin/usuarios', '/config', '/consola']:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(page).status_code, 200)
        for page in ['/exportar']:
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(load_workbook(io.BytesIO(response.data)).sheetnames)
            response.close()
        self.assertEqual(self.client.get('/exportar/rrhh').status_code, 409)
        response = self.client.post('/admin/backup')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.startswith(b'SQLite format 3'))
        response.close()

    def test_both_mark_protocols_and_validation(self):
        payload = dict(empleado_id='001', tipo_marcacion='ENTRADA', fecha_hora='2026-10-15 06:00:00')
        self.assertEqual(self.client.post('/api/marcaciones', json=payload).status_code, 200)
        self.assertEqual(self.client.post('/api/marcar', data='001,SALIDA,2026-10-15 14:30:00').status_code, 200)
        self.assertEqual(len(database.marks()), 2)
        payload['fecha_hora'] = 'invalid'
        self.assertEqual(self.client.post('/api/marcaciones', json=payload).status_code, 400)
        self.assertEqual(len(database.marks()), 2)
        self.assertEqual(self.client.get('/api/historial/001').json['historial'][0]['horas'], '8.0 hrs')

    def test_area_restriction(self):
        self.login('jefe')
        response = self.client.post('/aprobaciones/guardar_fila', data={'emp_id': '001', 'fecha': '2026-10-15'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(database.read_catalog('aprobaciones'), {})
        self.assertEqual(self.client.post('/admin/backup').status_code, 302)


if __name__ == '__main__':
    unittest.main()
