import io
import json
import unittest
from datetime import datetime, date, timedelta
from unittest.mock import patch
from openpyxl import load_workbook
import database
import planning
import storage
import test_storage

NOW = datetime(2026,12,1,12)
MONDAY = '2026-10-19'


class PlanningTests(unittest.TestCase):
    def setUp(self):
        test_storage.StorageTests.setUp(self)
        self.night = planning.validate_shift(dict(nombre='Noche',entrada='22:00',salida='06:00',descansos=[['02:00','03:00']]))
        self.day = planning.validate_shift(dict(nombre='Día',entrada='08:00',salida='15:00',descansos=[]))
        self.defaults['turnos']={'T3':self.night,'T1':self.day}
        self.defaults['usuarios']={'admin':dict(nombre='Admin',area='TODAS',rol='admin',**{'pass':'test'}),
                                  'jefe':dict(nombre='Jefe',area='OPERACIONES',rol='coordinador',**{'pass':'test'}),
                                  'rrhh':dict(nombre='RH',area='TODAS',rol='rrhh',**{'pass':'test'})}
        database.initialize(self.defaults)

    def week(self, values=None, monday=MONDAY):
        planning.assign_week('001',monday,values or ['T3']+['DESCANSO']*6,'jefe')

    def mark(self, kind, stamp):
        storage.registrar_marcacion('001',kind,stamp)

    def row(self, day=MONDAY):
        return next(r for r in planning.report('TODAS','001',day,day,now=NOW) if r['turno_id'])

    def test_overnight_start_day_and_early_arrival(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 21:50:00')
        self.mark('SALIDA','2026-10-20 06:00:00')
        result=self.row()
        self.assertEqual(result['fecha'],MONDAY)
        self.assertEqual(result['horas_ordinarias'],7)
        self.assertEqual(result['horas_equivalentes'],8)
        self.assertEqual(result['anticipacion_min'],10)
        self.assertEqual(result['extra_horas'],0)
        self.assertEqual(result['salida_fecha'],'2026-10-20 06:00:00')
        self.assertEqual(planning.report('TODAS','001','2026-10-20','2026-10-20',now=NOW)[0]['estado'],'DESCANSO')

    def test_late_does_not_get_cancelled_by_staying_late(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:10:00')
        self.mark('SALIDA','2026-10-20 06:10:00')
        result=self.row()
        self.assertAlmostEqual(result['horas_ordinarias'],7-1/6)
        self.assertAlmostEqual(result['extra_horas'],1/6)
        self.assertEqual(result['tardanza_min'],10)
        self.assertFalse(result['ausencia'])
        self.assertTrue(any(c['con_codigo']=='732' for c in result['conceptos']))
        planning.save_decision('001',MONDAY,dict(he_aprobadas=True),'jefe')
        extra=[c for c in self.row()['conceptos'] if c['tratamiento']=='HE']
        self.assertEqual(extra[0]['con_codigo'],'452')
        self.assertEqual(extra[0]['factor'],1.75)

    def test_no_assumed_break_and_legal_ordinary_cap(self):
        shift=planning.validate_shift(dict(nombre='Sin pausa',entrada='22:00',salida='06:00',descansos=[]))
        database.write_catalog('turnos',{'T3':shift})
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:00:00')
        self.mark('SALIDA','2026-10-20 06:00:00')
        r=self.row()
        self.assertEqual(r['horas_totales'],8)
        self.assertEqual(r['horas_ordinarias'],7)
        self.assertEqual(r['extra_horas'],1)
        self.assertIn('HE_PENDIENTE',r['alertas'])
        planning.save_decision('001',MONDAY,dict(he_aprobadas=True),'jefe')
        self.assertEqual([c['factor'] for c in self.row()['conceptos'] if c['tratamiento']=='HE'],[1.75])

    def test_absence_paid_unpaid_and_unknown_coverage(self):
        self.week()
        r=self.row()
        self.assertEqual(r['descuento_horas'],7)
        self.assertEqual(r['conceptos'][0]['con_codigo'],'730')
        planning.save_decision('001',MONDAY,dict(cod_ausencia='310'),'jefe')
        r=self.row()
        self.assertEqual(r['permiso_horas'],7)
        self.assertEqual(r['horas_equivalentes'],8)
        self.assertEqual(r['descuento_horas'],0)
        self.assertTrue(r['ausencia'])
        self.assertEqual(planning.monthly('TODAS','2026-10',now=NOW)[0]['estado'],'NO_APLICA')
        planning.save_decision('001',MONDAY,dict(cod_ausencia='750',remunerada=True),'jefe')
        self.assertEqual(self.row()['descuento_horas'],7)
        planning.save_decision('001',MONDAY,dict(cod_ausencia='100'),'jefe')
        self.assertIn('DEFINIR_REMUNERACION_PERMISO',self.row()['alertas'])

    def test_incomplete_does_not_become_full_day_deduction(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:00:00')
        r=self.row()
        self.assertEqual(r['estado'],'REVISAR')
        self.assertEqual(r['descuento_horas'],0)
        self.assertEqual(r['conceptos'],[])

    def test_manual_adjustment_updates_next_day_exit_without_duplicate(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:05:00')
        self.mark('SALIDA','2026-10-20 06:20:00')
        storage.guardar_o_actualizar_marcacion_diaria('001',MONDAY,'22:00','06:00','jefe')
        self.assertEqual(len(database.marks()),2)
        self.assertEqual(self.row()['salida_fecha'],'2026-10-20 06:00:00')
        self.assertEqual(self.row()['horas_ordinarias'],7)
        with database.reading() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM auditoria_planificacion WHERE accion='AJUSTAR_MARCACION'").fetchone()[0],1)

    def test_missing_exit_can_be_added_and_employee_rename_keeps_plan(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:00:00')
        storage.guardar_o_actualizar_marcacion_diaria('001',MONDAY,'','06:00','jefe')
        self.assertEqual(self.row()['horas_ordinarias'],7)
        storage.actualizar_codigo_empleado_sistema('001','002','José','Pérez','OPERACIONES','CARD')
        self.assertIn(('002',MONDAY),planning.assignments(MONDAY,MONDAY))
        self.assertEqual(planning.report('TODAS','002',MONDAY,MONDAY,now=NOW)[0]['horas_ordinarias'],7)

    def test_late_incomplete_entry_stays_with_its_shift(self):
        self.week()
        self.mark('ENTRADA','2026-10-20 03:00:00')
        result=self.row()
        self.assertEqual(result['estado'],'REVISAR')
        self.assertEqual(result['descuento_horas'],0)

    def test_unplanned_day_is_pending_and_not_absence(self):
        r=planning.report('TODAS','001',MONDAY,MONDAY,now=NOW)[0]
        self.assertEqual(r['estado'],'SIN_PLAN')
        self.assertFalse(r['ausencia'])
        self.assertEqual(r['descuento_horas'],0)

    def test_fixed_week_button_assigns_six_days_and_sunday_rest(self):
        with patch('time_sync.sincronizar_ntp'):
            from run import create_app
            client=create_app().test_client()
        client.post('/login',data={'usuario':'jefe','password':'test'})
        response=client.post('/planificacion',data={'emp_id':'001','semana':MONDAY,'turno_fijo':'T3','aplicar_fijo':'on'})
        self.assertEqual(response.status_code,302)
        saved=planning.assignments(MONDAY,'2026-10-25')
        self.assertEqual([saved[('001',(date.fromisoformat(MONDAY)+timedelta(days=i)).isoformat())]['turno_id'] for i in range(7)],['T3']*6+['DESCANSO'])
        response=client.post('/planificacion',data={'emp_id':'001','semana':MONDAY,'aplicar_fijo':'on'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(planning.assignments(MONDAY,'2026-10-25'),saved)

    def test_unassigned_sunday_is_rest_and_not_missing_plan(self):
        result=planning.report('TODAS','001','2026-10-25','2026-10-25',now=NOW)[0]
        self.assertEqual(result['estado'],'DESCANSO')
        self.assertFalse(result['ausencia'])
        self.assertEqual(result['alertas'],[])
        planning.assign_week('001',MONDAY,['T3']*6+[''],'jefe')
        self.assertEqual(planning.assignments('2026-10-25','2026-10-25')[('001','2026-10-25')]['turno_id'],'DESCANSO')

    def test_saturday_night_exit_on_sunday_stays_with_saturday(self):
        self.week(['DESCANSO']*5+['T3','DESCANSO'])
        self.mark('ENTRADA','2026-10-24 22:00:00')
        self.mark('SALIDA','2026-10-25 06:00:00')
        result=self.row('2026-10-24')
        self.assertEqual(result['horas_ordinarias'],7)
        sunday=planning.report('TODAS','001','2026-10-25','2026-10-25',now=NOW)
        self.assertEqual(len(sunday),1)
        self.assertEqual(sunday[0]['estado'],'DESCANSO')

    def test_individual_rest_day_premium(self):
        self.week(['T1']+['DESCANSO']*6)
        self.mark('ENTRADA',MONDAY+' 08:00:00')
        self.mark('SALIDA',MONDAY+' 15:00:00')
        planning.save_decision('001',MONDAY,dict(tipo_dia='descanso_obligatorio'),'jefe')
        recargos=[c for c in self.row()['conceptos'] if c['tratamiento']=='RECARGO']
        self.assertEqual(recargos[0]['con_codigo'],'652')
        self.assertEqual(recargos[0]['factor'],1.5)

    def test_paid_break_must_still_be_within_shift(self):
        with self.assertRaises(ValueError):
            planning.validate_shift(dict(nombre='Inválido',entrada='08:00',salida='16:00',
                descansos=[['18:00','19:00']],descanso_remunerado=True))

    def test_web_failed_week_rolls_back_even_when_error_is_caught(self):
        with patch('time_sync.sincronizar_ntp'):
            from run import create_app
            client=create_app().test_client()
        client.post('/login',data={'usuario':'jefe','password':'test'})
        response=client.post('/planificacion',data={'emp_id':'001','semana':MONDAY,'dia_0':'T1','dia_1':'UNKNOWN'})
        self.assertEqual(response.status_code,400)
        self.assertEqual(planning.assignments(MONDAY,'2026-10-25'),{})

    def test_invalidated_lateness_preserves_actual_minutes_and_restores_pay(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:40:00')
        self.mark('SALIDA','2026-10-20 06:00:00')
        with self.assertRaises(ValueError):
            planning.save_decision('001',MONDAY,dict(tardanza_estado='invalidada'),'jefe')
        planning.save_decision('001',MONDAY,dict(tardanza_estado='invalidada',motivo_tardanza='Falla del reloj'),'jefe')
        result=self.row()
        self.assertEqual(result['tardanza_min'],40)
        self.assertEqual(result['tardanza_computable_min'],0)
        self.assertEqual(result['descuento_horas'],0)
        self.assertAlmostEqual(result['horas_equivalentes'],8)
        self.assertNotIn('TARDANZA_PENDIENTE',result['alertas'])
        self.assertFalse(result['ausencia'])
        self.assertFalse(any(c['con_codigo']=='732' for c in result['conceptos']))

    def test_explicit_rejected_overtime_is_resolved_without_pay(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:00:00')
        self.mark('SALIDA','2026-10-20 07:00:00')
        planning.save_decision('001',MONDAY,dict(he_estado='rechazada',motivo_he='No corresponde a trabajo autorizado'),'jefe')
        result=self.row()
        self.assertEqual(result['extra_horas'],1)
        self.assertEqual(result['extra_aprobadas'],0)
        self.assertNotIn('HE_PENDIENTE',result['alertas'])
        self.assertFalse(any(c['tratamiento']=='HE' for c in result['conceptos']))

    def test_bonus_approval_is_invalidated_when_attendance_changes(self):
        for monday in ['2026-09-28','2026-10-05','2026-10-12','2026-10-19','2026-10-26']:
            self.week(['DESCANSO']*7,monday)
        planning.validate_bonus('OPERACIONES','001','2026-10','APROBADO','','jefe')
        self.assertEqual(planning.monthly('OPERACIONES','2026-10',now=NOW)[0]['validacion'],'APROBADO')
        self.week(['T3']+['DESCANSO']*6)
        result=planning.monthly('OPERACIONES','2026-10',now=NOW)[0]
        self.assertEqual(result['validacion'],'PENDIENTE')
        self.assertEqual(result['estado'],'NO_APLICA')
        with self.assertRaises(ValueError):
            planning.validate_bonus('OPERACIONES','001','2026-10','APROBADO','','jefe')

    def test_role_matrix_protects_routes_and_menus(self):
        with patch('time_sync.sincronizar_ntp'):
            from run import create_app
            client=create_app().test_client()
        response=client.post('/login',data={'usuario':'rrhh','password':'test'})
        self.assertTrue(response.location.endswith('/colaboradores'))
        html=client.get('/colaboradores').get_data(as_text=True)
        self.assertNotIn('href="/aprobaciones"',html)
        for path in ['/','/bono','/planificacion','/aprobaciones','/exportar','/rrhh/calendario']:
            self.assertEqual(client.get(path).status_code,403,path)
        for path in ['/aprobaciones/guardar_fila','/bono/validar','/marcaciones/guardar_ajuste']:
            self.assertEqual(client.post(path,data={'emp_id':'001'}).status_code,403,path)
        client.get('/logout')
        client.post('/login',data={'usuario':'jefe','password':'test'})
        for path in ['/colaboradores','/colaboradores/editar/001','/colaboradores/eliminar/001']:
            self.assertEqual(client.post(path).status_code,403,path)
        self.assertEqual(client.get('/colaboradores').status_code,403)
        html=client.get('/bono').get_data(as_text=True)
        self.assertNotIn('href="/colaboradores"',html)

    def test_multi_session_work_and_partial_absence(self):
        self.week()
        self.mark('ENTRADA',MONDAY+' 22:00:00')
        self.mark('SALIDA','2026-10-20 01:00:00')
        self.mark('ENTRADA','2026-10-20 03:00:00')
        self.mark('SALIDA','2026-10-20 06:00:00')
        r=self.row()
        self.assertEqual(r['horas_ordinarias'],6)
        self.assertEqual(r['ausencia_horas'],1)
        self.assertTrue(r['ausencia'])
        planning.save_decision('001',MONDAY,dict(cod_ausencia='310'),'jefe')
        r=self.row()
        self.assertEqual(r['horas_equivalentes'],8)
        self.assertEqual(r['descuento_horas'],0)

    def test_future_shift_does_not_become_absence(self):
        self.week()
        r=planning.report('TODAS','001',MONDAY,MONDAY,now=datetime(2026,10,19,23))[0]
        self.assertEqual(r['estado'],'EN_CURSO')
        self.assertEqual(r['descuento_horas'],0)
        self.assertFalse(r['ausencia'])

    def test_snapshot_and_atomic_failed_week(self):
        self.week()
        changed=dict(self.night,entrada='23:00:00')
        database.write_catalog('turnos',{'T3':changed,'T1':self.day})
        self.week()  # Same shift does not rewrite history.
        saved=planning.assignments(MONDAY,MONDAY)[('001',MONDAY)]
        self.assertEqual(json.loads(saved['turno_json'])['entrada'],'22:00:00')
        with self.assertRaises(ValueError):
            planning.assign_week('001',MONDAY,['T1','UNKNOWN']+['DESCANSO']*5,'jefe')
        self.assertEqual(planning.assignments(MONDAY,MONDAY)[('001',MONDAY)]['turno_id'],'T3')

    def test_weekly_excess_uses_context_before_export_start(self):
        self.week(['T1']*4+['DESCANSO']*3)
        for i in range(4):
            day=(date.fromisoformat(MONDAY)+timedelta(days=i)).isoformat()
            self.mark('ENTRADA',day+' 08:00:00')
            self.mark('SALIDA',day+' 18:00:00')
            planning.save_decision('001',day,dict(he_aprobadas=True),'jefe')
        r=self.row('2026-10-22')
        extra=[c for c in r['conceptos'] if c['tratamiento']=='HE']
        self.assertEqual(sum(c['cantidad_horas'] for c in extra),3)
        self.assertEqual({c['con_codigo'] for c in extra},{'454'})
        self.assertEqual(extra[0]['factor'],2.1875)

    def test_calendar_and_midnight_premium(self):
        self.assertEqual(planning.holiday(date(2026,11,4)),'normal')
        self.assertEqual(planning.holiday(date(2026,12,20)),'feriado')
        self.assertEqual(planning.holiday(date(2026,12,21)),'descanso_compensatorio')
        self.week(['DESCANSO']*6+['T3'],monday='2026-10-26')
        self.mark('ENTRADA','2026-11-01 22:00:00')
        self.mark('SALIDA','2026-11-02 06:00:00')
        planning.save_decision('001','2026-11-01',dict(domingo_estado='aprobada'),'jefe')
        r=self.row('2026-11-01')
        premium=[c for c in r['conceptos'] if c['con_codigo']=='652']
        self.assertEqual(sum(c['cantidad_horas'] for c in premium),8)

    def test_bonus_exact_limit_and_any_paid_absence(self):
        # Explicit rests make the month complete; the two scheduled shifts total exactly 30 min.
        for monday in ['2026-09-28','2026-10-05','2026-10-12','2026-10-19','2026-10-26']:
            self.week(['DESCANSO']*7,monday)
        self.week(['T3','T3']+['DESCANSO']*5)
        for day,next_day in [(MONDAY,'2026-10-20'),('2026-10-20','2026-10-21')]:
            self.mark('ENTRADA',day+' 22:15:00')
            self.mark('SALIDA',next_day+' 06:00:00')
            planning.save_decision('001',day,dict(tardanza_estado='validada'),'jefe')
        self.assertEqual(planning.monthly('TODAS','2026-10',now=NOW)[0]['estado'],'APLICA')
        # One extra second fails; no integer-minute truncation.
        with database.transaction() as db:
            db.execute("UPDATE marcaciones SET Fecha_Hora='2026-10-19 22:15:01' WHERE Fecha_Hora='2026-10-19 22:15:00'")
        self.assertEqual(planning.monthly('TODAS','2026-10',now=NOW)[0]['estado'],'NO_APLICA')

    def test_new_web_permissions_and_exports(self):
        with patch('time_sync.sincronizar_ntp'):
            from run import create_app
            app=create_app()
        app.config['TESTING']=True
        client=app.test_client()
        client.post('/login',data={'usuario':'jefe','password':'test'})
        self.assertEqual(client.post('/turnos',data={}).status_code,403)
        self.assertEqual(client.post('/planificacion',data={'emp_id':'OTHER','semana':MONDAY}).status_code,403)
        client.post('/logout')
        client.get('/logout')
        client.post('/login',data={'usuario':'rrhh','password':'test'})
        response=client.post('/turnos',data={'turno_id':'T4','nombre':'Prueba RH','entrada':'22:00','salida':'06:00','descansos':'02:00-03:00'})
        self.assertEqual(response.status_code,302)
        for path in ['/', '/aprobaciones','/bono','/planificacion','/exportar']:
            self.assertEqual(client.get(path).status_code,403,path)
        client.get('/logout')
        client.post('/login',data={'usuario':'admin','password':'test'})
        self.week()
        for page in ['/planificacion?semana='+MONDAY,'/bono?mes=2026-10','/rrhh/calendario','/aprobaciones?fecha_inicio='+MONDAY+'&fecha_fin='+MONDAY]:
            self.assertEqual(client.get(page).status_code,200,page)
        self.mark('ENTRADA',MONDAY+' 22:00:00')
        self.mark('SALIDA','2026-10-20 07:00:00')
        query='?emp_id=001&fecha_inicio='+MONDAY+'&fecha_fin='+MONDAY
        self.assertEqual(client.get('/exportar/rrhh'+query).status_code,409)
        response=client.get('/exportar'+query)
        self.assertEqual(response.status_code,200)
        wb=load_workbook(io.BytesIO(response.data))
        self.assertIn('Bono mensual',wb.sheetnames)
        self.assertEqual(wb['Asistencia'].cell(2,7).value,'2026-10-20 07:00:00')
        response.close()
        client.post('/aprobaciones/guardar_incidencia',data={'emp_id':'001','fecha':MONDAY,'tipo':'HE','he_estado':'aprobada'})
        self.assertEqual(client.get('/exportar/rrhh'+query).status_code,200)


if __name__=='__main__': unittest.main()
