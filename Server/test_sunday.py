import io
import json
import unittest
from unittest.mock import patch
from openpyxl import load_workbook
import database
import planning
import incidents
import storage
import test_planning

DAY='2026-10-25'


class SundayTests(unittest.TestCase):
    def setUp(self):
        test_planning.PlanningTests.setUp(self)
        planning.assign_week('001','2026-10-19',['T1']*6+['DESCANSO'],'jefe')

    def mark(self,entry,exit):
        storage.registrar_marcacion('001','ENTRADA',entry)
        storage.registrar_marcacion('001','SALIDA',exit)

    def row(self):
        return planning.report('OPERACIONES','001',DAY,DAY,now=test_planning.NOW)[0]

    def approve(self):
        incidents.validate('OPERACIONES','001',DAY,'DOMINGO',{'domingo_estado':'aprobada'},'jefe')

    def test_four_hours_recognizes_eight_without_absence(self):
        self.mark(DAY+' 08:00:00',DAY+' 12:00:00')
        result=self.row()
        self.assertEqual(result['horas_totales'],4)
        self.assertEqual(result['horas_fin_semana'],8)
        self.assertEqual(result['complemento_dominical'],4)
        self.assertEqual(result['extra_horas'],0)
        self.assertFalse(result['ausencia'])
        self.assertEqual(result['ausencia_horas'],0)
        self.assertEqual(result['tardanza_min'],0)
        self.assertIn('DOMINGO_PENDIENTE',result['alertas'])
        self.approve()
        result=self.row()
        weekend=[c for c in result['conceptos'] if c['con_codigo']=='652']
        self.assertEqual(weekend[0]['cantidad_horas'],8)
        self.assertEqual(weekend[0]['factor'],1.5)
        self.assertEqual(result['horas_equivalentes'],8)
        self.assertNotIn('DOMINGO_PENDIENTE',result['alertas'])
        self.assertEqual(planning.assignments(DAY,DAY)[('001',DAY)]['turno_id'],'DESCANSO')

    def test_ten_hours_gives_eight_weekend_and_two_weekend_overtime(self):
        self.mark(DAY+' 08:00:00',DAY+' 18:00:00')
        self.approve()
        incidents.validate('OPERACIONES','001',DAY,'HE',{'he_estado':'aprobada'},'jefe')
        result=self.row()
        weekend=[c for c in result['conceptos'] if c['tratamiento']=='FIN_SEMANA']
        extra=[c for c in result['conceptos'] if c['tratamiento']=='HE']
        self.assertEqual(sum(c['cantidad_horas'] for c in weekend),8)
        self.assertEqual(sum(c['cantidad_horas'] for c in extra),2)
        self.assertEqual({c['con_codigo'] for c in extra},{'858'})
        with database.reading() as db:
            rows=db.execute("SELECT tipo,segundos_detectados FROM incidencias WHERE empleado_id='001' AND fecha=? ORDER BY tipo",(DAY,)).fetchall()
            self.assertEqual([tuple(r) for r in rows],[('DOMINGO',28800),('HE',7200)])
            source=json.loads(db.execute("SELECT fuente_json FROM incidencias WHERE tipo='DOMINGO'").fetchone()[0])
            self.assertEqual(source['regla'],'ALICAPSA_DOMINGO_MINIMO_8')

    def test_night_limits_and_overtime_continue_as_weekend_after_midnight(self):
        planning.assign_week('001','2026-10-19',['T3']*6+['DESCANSO'],'jefe')
        self.mark(DAY+' 22:00:00','2026-10-26 07:00:00')
        self.assertEqual(self.row()['horas_ordinarias'],7)
        self.assertEqual(self.row()['extra_horas'],1)
        self.approve()
        incidents.validate('OPERACIONES','001',DAY,'HE',{'he_estado':'aprobada'},'jefe')
        extra=[c for c in self.row()['conceptos'] if c['tratamiento']=='HE']
        self.assertEqual(extra[0]['con_codigo'],'860')
        self.assertEqual(extra[0]['factor'],2.625)
        self.assertEqual(self.row()['horas_equivalentes'],8)

    def test_manual_overnight_sunday_uses_next_day_exit(self):
        storage.guardar_o_actualizar_marcacion_diaria('001',DAY,'22:00','07:00','jefe')
        rows=database.marks(employee='001',start=DAY,end='2026-10-26')
        self.assertEqual(rows[1]['Fecha_Hora'],'2026-10-26 07:00:00')
        storage.guardar_o_actualizar_marcacion_diaria('001',DAY,'22:00','06:00','jefe')
        rows=database.marks(employee='001',start=DAY,end='2026-10-26')
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[1]['Fecha_Hora'],'2026-10-26 06:00:00')

    def test_sunday_without_work_does_not_receive_payment(self):
        result=self.row()
        self.assertEqual(result['estado'],'DESCANSO')
        self.assertEqual(incidents.quantities(result)['DOMINGO'],0)
        self.assertEqual(result['horas_pagables'],0)
        with self.assertRaises(ValueError): self.approve()

    def test_incomplete_sunday_is_not_paid_automatically(self):
        storage.registrar_marcacion('001','ENTRADA',DAY+' 08:00:00')
        result=self.row()
        self.assertEqual(result['estado'],'REVISAR')
        self.assertEqual(incidents.quantities(result)['DOMINGO'],0)

    def test_reference_breaks_are_used_without_fabricating_actual_hours(self):
        shifts=database.read_catalog('turnos')
        shifts['T1']=planning.validate_shift(dict(nombre='Mañana',entrada='06:00',salida='14:30',descansos=[['12:00','12:30']]))
        database.write_catalog('turnos',shifts)
        planning.assign_week('001','2026-10-19',['T1']*6+['DESCANSO'],'jefe',renew=True)
        self.mark(DAY+' 06:55:00',DAY+' 14:30:00')
        result=self.row()
        self.assertAlmostEqual(result['horas_totales'],7+5/60)
        self.assertEqual(result['horas_fin_semana'],8)
        self.assertEqual(result['extra_horas'],0)
        self.assertFalse(result['ausencia'])

    def test_validation_page_separates_weekend_base_and_overtime(self):
        self.mark(DAY+' 08:00:00',DAY+' 18:00:00')
        with patch('time_sync.sincronizar_ntp'):
            from run import create_app
            app=create_app()
        client=app.test_client()
        client.post('/login',data={'usuario':'jefe','password':'test'})
        response=client.get('/aprobaciones?fecha_inicio='+DAY+'&fecha_fin='+DAY)
        html=response.get_data(as_text=True)
        self.assertEqual(html.count('data-incidencia="DOMINGO"'),1)
        self.assertEqual(html.count('data-incidencia="HE"'),1)
        self.assertNotIn('data-incidencia="FALTANTE"',html)
        self.assertIn('Horas de fin de semana',html)
        self.assertIn('HE de fin de semana',html)
        self.approve()
        incidents.validate('OPERACIONES','001',DAY,'HE',{'he_estado':'aprobada'},'jefe')
        response=client.get('/exportar?emp_id=001&fecha_inicio='+DAY+'&fecha_fin='+DAY)
        sheet=load_workbook(io.BytesIO(response.data))['Novedades RRHH']
        rows=list(sheet.iter_rows(min_row=2,values_only=True))
        self.assertTrue(any(r[1]=='652' and r[2]==8 and r[7]=='DOMINGO' and r[8] for r in rows))
        self.assertTrue(any(r[1]=='858' and r[2]==2 and r[7]=='HE' for r in rows))
        response.close()

    def test_v4_migration_preserves_incidence_and_child_identifiers(self):
        with database.transaction() as db:
            db.execute('DROP TABLE incidencia_conceptos')
            db.execute('DROP TABLE incidencias')
            db.execute("CREATE TABLE incidencias(id INTEGER PRIMARY KEY,empleado_id TEXT NOT NULL,fecha TEXT NOT NULL,tipo TEXT CHECK(tipo IN ('HE','TARDANZA','FALTANTE')),segundos_detectados INTEGER,codigo TEXT,estado TEXT,motivo TEXT,usuario TEXT,actualizado TEXT,activa INTEGER,UNIQUE(empleado_id,fecha,tipo))")
            db.execute('CREATE TABLE incidencia_conceptos(id INTEGER PRIMARY KEY,incidencia_id INTEGER REFERENCES incidencias(id),ordinal INTEGER,codigo TEXT,horas REAL,factor REAL,tratamiento TEXT)')
            db.execute("INSERT INTO incidencias VALUES (91,'001','2026-10-19','TARDANZA',600,'732','validada','','jefe','2026-10-20',1)")
            db.execute("INSERT INTO incidencia_conceptos VALUES (81,91,0,'732',0.166666,1,'DESCUENTO')")
            database.initialize_incidents(db)
            self.assertEqual(db.execute('SELECT id FROM incidencias').fetchone()[0],91)
            self.assertEqual(tuple(db.execute('SELECT id,incidencia_id FROM incidencia_conceptos').fetchone()),(81,91))
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            database.initialize_incidents(db)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM incidencias').fetchone()[0],1)


if __name__=='__main__': unittest.main()
