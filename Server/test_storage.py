import csv
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import database
import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.paths = patch.multiple(database, BASE_DIR=self.root, DATABASE_PATH=self.root / 'test.sqlite3')
        self.paths.start()
        self.defaults = dict(config={}, empleados={'001': dict(nombre='José', apellido='Pérez', area='OPERACIONES', rfid='CARD')},
                             usuarios={}, areas=['OPERACIONES'], turnos={}, aprobaciones={})
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.paths.stop)

    def test_import_once_preserves_ids_unicode_and_duplicate_source_rows(self):
        (self.root / 'empleados.json').write_text(json.dumps(self.defaults['empleados']), encoding='utf-8')
        with (self.root / 'marcaciones.csv').open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=database.FIELDS)
            writer.writeheader()
            row = dict.fromkeys(database.FIELDS, '')
            row.update(ID_Registro='legacy', ID_Personal='001', Fecha_Hora='2026-10-15 06:00:00')
            writer.writerows([row, row])
        database.initialize(self.defaults)
        database.initialize(self.defaults)
        self.assertEqual(len(database.marks()), 2)
        self.assertEqual(database.read_catalog('empleados')['001']['nombre'], 'José')

    def test_failed_import_rolls_back_and_can_retry(self):
        source = self.root / 'usuarios.json'
        source.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            database.initialize(self.defaults)
        source.write_text('{}', encoding='utf-8')
        database.initialize(self.defaults)
        self.assertIn('001', database.read_catalog('empleados'))

    def test_parallel_marks_and_invalid_timestamp(self):
        database.initialize(self.defaults)
        def mark(_):
            storage.registrar_marcacion('CARD', 'ENTRADA', '2026-10-15 06:00:00')
        with ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(mark, range(25)))
        self.assertEqual(len(database.marks(employee='001')), 25)
        with self.assertRaises(ValueError):
            storage.registrar_marcacion('NEW', 'ENTRADA', 'invalid')
        self.assertNotIn('NEW', database.read_catalog('empleados'))

    def test_adjustment_rename_and_backup(self):
        database.initialize(self.defaults)
        storage.guardar_o_actualizar_marcacion_diaria('001', '2026-10-15', '06:00', '14:30', 'admin')
        self.assertEqual(storage.obtener_registros_agrupados('TODAS')[0]['horas_totales'], 8)
        database.write_catalog('aprobaciones', {'001': {'2026-10-15': {'turno_id': 'T1'}}})
        storage.actualizar_codigo_empleado_sistema('001', '002', 'José', 'Pérez', 'OPERACIONES', 'CARD')
        self.assertEqual(len(database.marks(employee='002')), 2)
        self.assertIn('002', database.read_catalog('aprobaciones'))
        backup = database.backup(self.root / 'backup.sqlite3')
        with self.assertRaises(FileExistsError):
            database.backup(backup)
        with patch.object(database, 'DATABASE_PATH', backup):
            self.assertEqual(len(database.marks()), 2)
        with self.assertRaises(RuntimeError):
            with database.transaction():
                database.write_catalog('usuarios', {'temporary': {}})
                raise RuntimeError('rollback')
        self.assertEqual(database.read_catalog('usuarios'), {})


if __name__ == '__main__':
    unittest.main()
