import io
import json
import unittest
from unittest.mock import patch
from openpyxl import load_workbook
import database
import planning
import storage
import test_planning


class BatchTests(unittest.TestCase):
    def setUp(self):
        test_planning.PlanningTests.setUp(self)
        employees=database.read_catalog('empleados')
        employees['002']=dict(nombre='Ana',apellido='Prueba',area='OPERACIONES',rfid='')
        database.write_catalog('empleados',employees)
        for employee in ('001','002'):
            planning.assign_week(employee,'2026-10-19',['T3']+['DESCANSO']*6,'jefe')
        with patch('time_sync.sincronizar_ntp'):
            from run import create_app
            self.app=create_app()
        self.app.config['TESTING']=True
        self.client=self.app.test_client()
        self.client.post('/login',data={'usuario':'jefe','password':'test'})

    def operation(self,employee,kind,**fields):
        data=dict(emp_id=employee,fecha='2026-10-19',tipo=kind,**fields)
        return dict(action='/aprobaciones/guardar_incidencia',fields=[[k,v] for k,v in data.items()])

    def send(self,operations):
        return self.client.post('/guardar_cambios',data={'operaciones':json.dumps(operations)})

    def mark(self,employee,entry,exit):
        storage.registrar_marcacion(employee,'ENTRADA',entry)
        storage.registrar_marcacion(employee,'SALIDA',exit)

    def test_all_edited_employees_and_types_are_saved_individually(self):
        self.mark('001','2026-10-19 22:10:00','2026-10-20 07:00:00')
        result=self.send([self.operation('001','HE',he_estado='aprobada'),
            self.operation('001','TARDANZA',tardanza_estado='invalidada',motivo_tardanza='Falla externa'),
            self.operation('002','FALTANTE',cod_ausencia='310')])
        self.assertEqual(result.status_code,200,result.data)
        self.assertEqual(result.json['guardados'],3)
        with database.reading() as db:
            rows=db.execute('SELECT empleado_id,tipo,estado,segundos_detectados FROM incidencias ORDER BY empleado_id,tipo').fetchall()
            self.assertEqual([tuple(r) for r in rows],[('001','HE','aprobada',3600),('001','TARDANZA','invalidada',600),('002','FALTANTE','remunerado',25200)])
            actions=[r[0] for r in db.execute('SELECT accion FROM auditoria_planificacion')]
            for kind in ('HE','TARDANZA','FALTANTE'): self.assertIn('INCIDENCIA_'+kind,actions)
            self.assertNotIn('DECIDIR_NOVEDAD',actions)

    def test_one_invalid_change_rolls_back_the_entire_batch(self):
        self.mark('001','2026-10-19 22:00:00','2026-10-20 07:00:00')
        result=self.send([self.operation('001','HE',he_estado='aprobada'),self.operation('002','FALTANTE',cod_ausencia='732')])
        self.assertEqual(result.status_code,400)
        self.assertEqual(planning.decisions('2026-10-19','2026-10-19'),{})
        with database.reading() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM incidencias').fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM auditoria_planificacion WHERE accion='GUARDADO_FORMULARIO'").fetchone()[0],0)

    def test_only_detected_controls_and_no_combined_payloads(self):
        self.mark('001','2026-10-19 22:00:00','2026-10-20 06:00:00')
        result=self.client.get('/aprobaciones?fecha_inicio=2026-10-19&fecha_fin=2026-10-19')
        html=result.get_data(as_text=True)
        self.assertNotIn('data-incidencia="HE"',html)
        self.assertNotIn('data-incidencia="TARDANZA"',html)
        self.assertEqual(html.count('data-incidencia="FALTANTE"'),1)
        for name in ('remunerada','tipo_dia','incluir_anticipadas'):
            self.assertNotIn('name="'+name+'"',html)
        for kind,fields in [('HE',dict(he_estado='aprobada')),('TARDANZA',dict(tardanza_estado='validada')),('FALTANTE',dict(cod_ausencia='310'))]:
            self.assertEqual(self.send([self.operation('001',kind,**fields)]).status_code,400)
        result=self.send([self.operation('002','FALTANTE',cod_ausencia='310',remunerada='no')])
        self.assertEqual(result.status_code,400)

    def test_lateness_and_missing_time_have_distinct_codes_and_quantities(self):
        self.mark('001','2026-10-19 22:10:00','2026-10-20 05:30:00')
        result=self.send([self.operation('001','TARDANZA',tardanza_estado='validada'),self.operation('001','FALTANTE',cod_ausencia='310')])
        self.assertEqual(result.status_code,200,result.data)
        row=planning.report('OPERACIONES','001','2026-10-19','2026-10-19')[0]
        late=[c for c in row['conceptos'] if c['con_codigo']=='732']
        missing=[c for c in row['conceptos'] if c['con_codigo']=='310']
        self.assertAlmostEqual(late[0]['cantidad_horas'],1/6)
        self.assertAlmostEqual(missing[0]['cantidad_horas'],.5)
        self.assertAlmostEqual(row['descuento_horas'],1/6)

    def test_generic_saving_updates_multiple_weeks_and_rejects_unsafe_routes(self):
        operations=[]
        for employee in ('001','002'):
            data=dict(emp_id=employee,semana='2026-10-19',turno_fijo='T1',aplicar_fijo='on')
            operations.append(dict(action='/planificacion',fields=list(map(list,data.items()))))
        response=self.send(operations)
        self.assertEqual(response.status_code,200,response.data)
        saved=planning.assignments('2026-10-19','2026-10-25')
        self.assertEqual(len(saved),14)
        self.assertEqual(saved[('002','2026-10-24')]['turno_id'],'T1')
        response=self.send([dict(action='https://example.com/planificacion',fields=[])])
        self.assertEqual(response.status_code,400)
        response=self.send([dict(action='/admin/usuarios/eliminar/admin',fields=[])])
        self.assertEqual(response.status_code,400)

    def test_exports_keep_different_days_separate(self):
        planning.assign_week('001','2026-10-19',['T3','T3']+['DESCANSO']*5,'jefe')
        for day,next_day in [('2026-10-19','2026-10-20'),('2026-10-20','2026-10-21')]:
            self.mark('001',day+' 22:10:00',next_day+' 06:00:00')
        response=self.client.get('/exportar?emp_id=001&fecha_inicio=2026-10-19&fecha_fin=2026-10-20')
        self.assertEqual(response.status_code,200)
        sheet=load_workbook(io.BytesIO(response.data))['Novedades RRHH']
        rows=[r for r in sheet.iter_rows(min_row=2,values_only=True) if r[1]=='732']
        self.assertEqual(len(rows),2)
        self.assertEqual({r[6] for r in rows},{'2026-10-19','2026-10-20'})
        response.close()

    def test_multiple_employee_edits_include_uploaded_biometrics(self):
        import numpy as np
        self.client.get('/logout')
        self.client.post('/login',data={'usuario':'admin','password':'test'})
        vector=io.BytesIO()
        np.save(vector,np.zeros(128))
        vector.seek(0)
        operations=[]
        for employee,name in [('001','Primero'),('002','Segundo')]:
            fields=dict(nuevo_emp_id=employee,nombre=name,apellido='Prueba',area='OPERACIONES',rfid='')
            operations.append(dict(action='/colaboradores/editar/'+employee,fields=list(map(list,fields.items())),files=[['archivo_npy','file_0']] if employee=='001' else []))
        response=self.client.post('/guardar_cambios',data={'operaciones':json.dumps(operations),'file_0':(vector,'vector.npy')})
        self.assertEqual(response.status_code,200,response.data)
        employees=database.read_catalog('empleados')
        self.assertEqual(employees['001']['nombre'],'Primero')
        self.assertEqual(employees['002']['nombre'],'Segundo')
        self.assertEqual(len(employees['001']['vector_facial']),128)

    def test_batch_cannot_cross_the_coordinators_area(self):
        employees=database.read_catalog('empleados')
        employees['003']=dict(nombre='Otra',apellido='Área',area='MANTENIMIENTO')
        database.write_catalog('empleados',employees)
        planning.assign_week('003','2026-10-19',['T3']+['DESCANSO']*6,'admin')
        self.mark('001','2026-10-19 22:00:00','2026-10-20 07:00:00')
        result=self.send([self.operation('001','HE',he_estado='aprobada'),self.operation('003','FALTANTE',cod_ausencia='310')])
        self.assertEqual(result.status_code,400)
        self.assertEqual(planning.decisions('2026-10-19','2026-10-19'),{})

    def test_missing_time_uses_central_code_policy(self):
        config=database.read_catalog('config')
        config['politicas_ausencia']={'100':True}
        database.write_catalog('config',config)
        result=self.send([self.operation('002','FALTANTE',cod_ausencia='100')])
        self.assertEqual(result.status_code,200,result.data)
        row=planning.report('OPERACIONES','002','2026-10-19','2026-10-19')[0]
        self.assertEqual(row['descuento_horas'],0)
        self.assertEqual(row['permiso_horas'],7)


if __name__=='__main__': unittest.main()
