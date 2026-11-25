"""Create a separate, auditable demonstration database from a consistent copy."""
import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
import database

KEY = 'demostracion'
ACTOR = 'DEMO'


def status():
    with database.reading() as db:
        row=db.execute('SELECT valor FROM metadata WHERE clave=?',(KEY,)).fetchone()
    return json.loads(row[0]) if row else None


def evaluation_time():
    demo=status()
    return datetime.fromisoformat(demo['evaluado_al']) if demo else None


def create(destination, start, end):
    import planning
    import incidents
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    if first>last or (first.year,first.month)!=(last.year,last.month):
        raise ValueError('La demostración debe estar dentro de un mismo mes')
    source=database.DATABASE_PATH.resolve()
    if status(): raise ValueError('Genere la demostración desde la base original, no desde otra demostración')
    if not database.read_catalog('empleados'): raise ValueError('Registre colaboradores antes de generar la demostración')
    target=Path(destination).resolve()
    if target==source: raise ValueError('La demostración necesita un archivo diferente de la base original')
    # backup() exclusively creates the destination: an existing file is never overwritten.
    database.backup(target)
    database.DATABASE_PATH=target
    try:
        with database.transaction() as db:
            demo=dict(desde=start,hasta=end,evaluado_al=datetime.combine(last+timedelta(days=1),datetime.min.time()).replace(hour=12).isoformat(),
                descripcion='Datos simulados para presentación; no utilizar para pagar salarios')
            db.execute('INSERT INTO metadata VALUES (?,?)',(KEY,json.dumps(demo,ensure_ascii=False)))
            # Only this new copy is modified. Preserve copied originals in its audit as well.
            mark_end=(last+timedelta(days=2)).isoformat()
            previous=[dict(r) for r in db.execute('SELECT * FROM marcaciones WHERE Fecha_Hora>=? AND Fecha_Hora<?',(start,mark_end))]
            planning.audit(db,'',start,'DEMO_REEMPLAZAR_PERIODO',dict(marcaciones=previous),dict(desde=start,hasta=end),ACTOR)
            db.execute('DELETE FROM incidencia_conceptos WHERE incidencia_id IN (SELECT id FROM incidencias WHERE fecha BETWEEN ? AND ?)',(start,end))
            for table in ('incidencias','decisiones','asignaciones'):
                db.execute(f'DELETE FROM {table} WHERE fecha BETWEEN ? AND ?',(start,end))
            db.execute('DELETE FROM validaciones_bono WHERE mes=?',(first.strftime('%Y-%m'),))
            db.execute('DELETE FROM marcaciones WHERE Fecha_Hora>=? AND Fecha_Hora<?',(start,mark_end))
            db.execute('DELETE FROM terminal_events WHERE kind=? AND (substr(json_extract(payload,\'$.fecha_hora\'),1,10) BETWEEN ? AND ?)',('mark',start,(last+timedelta(days=1)).isoformat()))
            approvals=database.read_catalog('aprobaciones')
            database.write_catalog('aprobaciones',{employee:{day:value for day,value in days.items() if not start<=day<=end} for employee,days in approvals.items()})

            shifts=database.read_catalog('turnos')
            definitions={
                'DEMO-D':dict(nombre='DEMO · Día 06:00–14:30',entrada='06:00',salida='14:30',descansos=[['12:00','12:30']],descanso_remunerado=False),
                'DEMO-N':dict(nombre='DEMO · Noche 22:00–06:00 (descanso simulado)',entrada='22:00',salida='06:00',descansos=[['02:00','03:00']],descanso_remunerado=False)}
            for key,value in definitions.items():
                shift=planning.validate_shift(value)
                planning.audit(db,'',start,'DEMO_DEFINIR_TURNO',shifts.get(key),dict(id=key,**shift),ACTOR)
                shifts[key]=shift
            database.write_catalog('turnos',shifts)

            employees=database.read_catalog('empleados')
            cases=[]
            actions=[]
            for index,(employee,info) in enumerate(employees.items()):
                shift_id='DEMO-N' if index%7 in (1,4) else 'DEMO-D'
                shift=shifts[shift_id]
                for day in planning.dates(start,end):
                    current=date.fromisoformat(day)
                    if info.get('fecha_ingreso') and day<info['fecha_ingreso']: continue
                    daynum=current.day
                    rest=current.weekday()==6
                    assigned='DESCANSO' if rest else shift_id
                    snapshot={} if rest else shift
                    db.execute('INSERT INTO asignaciones VALUES (?,?,?,?,?,?)',(employee,day,assigned,json.dumps(snapshot,ensure_ascii=False),ACTOR,planning.today().isoformat()))
                    planning.audit(db,employee,day,'DEMO_ASIGNAR_TURNO',None,dict(turno_id=assigned,turno=snapshot),ACTOR)
                    scenario='Asistencia normal'
                    arrival,departure=planning.bounds(day,shift)
                    local_actions=[]
                    absent=False
                    only_entry=False
                    only_exit=False
                    if rest:
                        if index==3 and daynum==15:
                            arrival=datetime.combine(current,datetime.min.time()).replace(hour=6)
                            departure=arrival+timedelta(hours=4)
                            scenario='Domingo: 4 horas reales y mínimo de 8 por convenio'
                            local_actions=[('DOMINGO',dict(domingo_estado='aprobada',motivo_domingo='DEMO: reconocer mínimo dominical'))]
                        elif index==2 and daynum==22:
                            arrival=datetime.combine(current,datetime.min.time()).replace(hour=6)
                            # Includes the simulated half-hour unpaid lunch break.
                            departure=arrival+timedelta(hours=10.5)
                            scenario='Domingo: 8 horas base y 2 HE pendientes'
                            local_actions=[('DOMINGO',dict(domingo_estado='aprobada',motivo_domingo='DEMO: domingo trabajado'))]
                        else: continue
                    elif (index,daynum) in ((0,10),(1,12),(3,13),(4,18),(5,21),(5,23)):
                        absent=True
                        codes={(0,10):'310',(1,12):'730',(4,18):'750',(5,21):'730'}
                        code=codes.get((index,daynum),'')
                        scenario='Ausencia '+(code or 'pendiente de código del coordinador')
                        if code: local_actions=[('FALTANTE',dict(cod_ausencia=code))]
                    elif (index,daynum) in ((2,21),(5,20)):
                        only_entry=True;scenario='Falta marcar salida'
                    elif (index,daynum) in ((3,20),(5,24)):
                        only_exit=True;scenario='Salida sin entrada; requiere ajuste del coordinador'
                    else:
                        late={(0,23):10,(0,30):20,(1,24):10,(2,11):15,(2,17):20,(4,11):10,(4,25):12}.get((index,daynum),0)
                        extra={(0,18):2,(1,19):1.5,(1,27):2,(2,28):2,(4,26):1,(5,9):1}.get((index,daynum),0)
                        missing={(0,26):2,(2,20):1,(4,11):.5}.get((index,daynum),0)
                        if late:
                            arrival+=timedelta(minutes=late)
                            scenario=f'Tardanza de {late} minutos'
                            if (index,daynum)==(1,24):
                                local_actions.append(('TARDANZA',dict(tardanza_estado='invalidada',motivo_tardanza='DEMO: falla externa del lector verificada')))
                            elif (index,daynum)!=(4,25): local_actions.append(('TARDANZA',dict(tardanza_estado='validada')))
                        elif (index+daynum)%5==0:
                            arrival-=timedelta(minutes=5)
                        if extra:
                            departure+=timedelta(hours=extra)
                            scenario=f'{extra:g} horas extra '+('pendientes' if (index,daynum) in ((1,27),(5,9)) else 'aprobadas')
                            if (index,daynum) not in ((1,27),(5,9)):
                                local_actions.append(('HE',dict(he_estado='aprobada',motivo_he='DEMO: sobretiempo autorizado')))
                        if missing:
                            departure-=timedelta(hours=missing)
                            scenario+=f'; faltante de {missing:g} horas'
                            local_actions.append(('FALTANTE',dict(cod_ausencia='310' if index==0 else '750')))
                    cases.append(dict(empleado_id=employee,nombre=f"{info.get('nombre','')} {info.get('apellido','')}".strip(),fecha=day,turno=shift_id,escenario=scenario))
                    if not absent:
                        for kind,instant in [('ENTRADA',arrival),('SALIDA',departure)]:
                            if kind=='ENTRADA' and only_exit or kind=='SALIDA' and only_entry: continue
                            identifier='DEMO-'+uuid.uuid5(uuid.NAMESPACE_URL,f'alicapsa/{employee}/{day}/{kind}').hex
                            mark=dict(ID_Registro=identifier,ID_Personal=employee,Nombre=cases[-1]['nombre'],Area=str(info.get('area','')).upper().replace('Í','I'),
                                Tipo=kind,Fecha_Hora=instant.strftime('%Y-%m-%d %H:%M:%S'),IP_Origen='SIMULACION',Estado='Aprobado',Nota=f'DEMO · Jornada {day} · {scenario}')
                            database.insert_mark(mark)
                            planning.audit(db,employee,day,'DEMO_MARCACION',None,mark,ACTOR)
                    actions.extend((employee,day,kind,data) for kind,data in local_actions)

            # Apply decisions only after every simulated punch exists.
            for employee,day,kind,data in actions:
                incidents.validate('TODAS',employee,day,kind,data,ACTOR)
            rows=planning.report('TODAS','',start,end)
            incidents.sync(rows,ACTOR)
            summary=dict(base=str(target),desde=start,hasta=end,evaluado_al=demo['evaluado_al'],colaboradores=len(employees),
                marcaciones_simuladas=db.execute("SELECT count(*) FROM marcaciones WHERE IP_Origen='SIMULACION'").fetchone()[0],
                jornadas_completas=sum(r['estado']=='COMPLETO' for r in rows),ausencias=sum(r['ausencia'] for r in rows),
                jornadas_con_he=sum(r['extra_horas']>0 for r in rows),jornadas_con_tardanza=sum(r['tardanza_min']>0 for r in rows),
                jornadas_para_revision=sum(r['estado'] in ('REVISAR','SIN_TURNO') for r in rows),
                domingos_trabajados=sum(bool(r.get('dia_descanso_trabajado')) for r in rows),casos=cases)
            if any(r['estado'] in ('PROGRAMADO','EN_CURSO') for r in rows): raise RuntimeError('La fecha de evaluación no cerró todas las jornadas')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise RuntimeError('La copia de demostración no pasó integridad')
            planning.audit(db,'',start,'DEMO_GENERADA',None,{k:v for k,v in summary.items() if k!='casos'},ACTOR)
        return summary
    finally:
        database.DATABASE_PATH=source
