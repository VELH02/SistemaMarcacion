"""One detected incidence per employee, workday and type; independent audit trail."""
import json
import database
import planning

TYPES = ('HE','TARDANZA','FALTANTE','DOMINGO')


def quantities(row):
    if row['estado'] not in ('COMPLETO','AUSENCIA') or 'TURNO_SIN_VALIDAR_RH' in row['alertas']:
        return dict.fromkeys(TYPES,0)
    return dict(HE=round(row['extra_horas']*3600),TARDANZA=round(row['tardanza_min']*60),
                FALTANTE=round(row['ausencia_horas']*3600),DOMINGO=round(row.get('horas_fin_semana',0)*3600))


def sync(rows, user='Sistema'):
    """Persist detections without merging unrelated incidents or deleting history."""
    with database.transaction() as db:
        for row in rows:
            detected=quantities(row)
            for kind in TYPES:
                prior=db.execute('SELECT * FROM incidencias WHERE empleado_id=? AND fecha=? AND tipo=?',
                                 (row['id'],row['fecha'],kind)).fetchone()
                qty=detected[kind]
                if not qty and prior is None: continue
                if kind=='DOMINGO':
                    code=row.get('codigo_domingo','652')
                    state=row.get('domingo_estado','pendiente')
                    reason=row.get('motivo_domingo','')
                    concepts=[c for c in row['conceptos'] if c['tratamiento']=='FIN_SEMANA']
                elif kind=='HE':
                    code=''
                    state=row.get('he_estado','pendiente')
                    reason=row.get('motivo_he','')
                    concepts=[c for c in row['conceptos'] if c['tratamiento']=='HE']
                elif kind=='TARDANZA':
                    code='732'
                    state=row.get('tardanza_estado','pendiente')
                    reason=row.get('motivo_tardanza','')
                    concepts=[c for c in row['conceptos'] if c['con_codigo']=='732' or c['tratamiento'].startswith('TARDANZA_')]
                else:
                    code=row['cod_ausencia']
                    state=('pendiente' if not code or row['remunerada'] is None else ('remunerado' if row['remunerada'] else 'no_remunerado'))
                    reason=''
                    concepts=[c for c in row['conceptos'] if c['tratamiento'] in ('REMUNERADO','DESCUENTO','REVISAR') and c['con_codigo']!='732']
                if not qty:
                    state='resuelta' if row['estado'] in ('COMPLETO','AUSENCIA','DESCANSO') and 'TURNO_SIN_VALIDAR_RH' not in row['alertas'] else 'no_evaluable'
                    concepts=[]
                source=row.get('fuente_domingo') if kind=='DOMINGO' else dict(entrada=row.get('entrada_fecha',''),salida=row.get('salida_fecha',''),turno=row['turno_id'],horas_reales=row['horas_totales'])
                source_json=json.dumps(source,ensure_ascii=False,sort_keys=True)
                values=dict(segundos_detectados=qty,codigo=code,estado=state,motivo=reason,activa=int(qty>0),fuente_json=source_json)
                old_concepts=[] if prior is None else [dict(c) for c in db.execute('SELECT ordinal,codigo,horas,factor,tratamiento FROM incidencia_conceptos WHERE incidencia_id=? ORDER BY ordinal',(prior['id'],))]
                new_concepts=[dict(ordinal=i,codigo=c['con_codigo'],horas=c['cantidad_horas'],factor=c['factor'],tratamiento=c['tratamiento']) for i,c in enumerate(concepts)]
                if prior and all(prior[k]==v for k,v in values.items()) and old_concepts==new_concepts:
                    continue
                db.execute('INSERT INTO incidencias(empleado_id,fecha,tipo,segundos_detectados,codigo,estado,motivo,usuario,actualizado,activa,fuente_json) VALUES (?,?,?,?,?,?,?,?,?,?,?) '
                    'ON CONFLICT(empleado_id,fecha,tipo) DO UPDATE SET segundos_detectados=excluded.segundos_detectados,codigo=excluded.codigo,estado=excluded.estado,motivo=excluded.motivo,usuario=excluded.usuario,actualizado=excluded.actualizado,activa=excluded.activa,fuente_json=excluded.fuente_json',
                    (row['id'],row['fecha'],kind,qty,code,state,reason,user,planning.today().isoformat(),int(qty>0),source_json))
                identifier=db.execute('SELECT id FROM incidencias WHERE empleado_id=? AND fecha=? AND tipo=?',(row['id'],row['fecha'],kind)).fetchone()[0]
                db.execute('DELETE FROM incidencia_conceptos WHERE incidencia_id=?',(identifier,))
                db.executemany('INSERT INTO incidencia_conceptos(incidencia_id,ordinal,codigo,horas,factor,tratamiento) VALUES (?,?,?,?,?,?)',
                    [(identifier,c['ordinal'],c['codigo'],c['horas'],c['factor'],c['tratamiento']) for c in new_concepts])
                before=None if prior is None else {**dict(prior), 'conceptos':old_concepts}
                planning.audit(db,row['id'],row['fecha'],'INCIDENCIA_'+kind,before,
                    dict(incidencia_id=identifier,**values,conceptos=new_concepts),user)


def validate(area, employee, day, kind, data, user):
    if kind not in TYPES: raise ValueError('Seleccione una sola incidencia detectada')
    allowed={'HE':{'he_estado','motivo_he'},'TARDANZA':{'tardanza_estado','motivo_tardanza'},'FALTANTE':{'cod_ausencia'},'DOMINGO':{'domingo_estado','motivo_domingo'}}[kind]
    if set(data)-allowed: raise ValueError('No se pueden combinar incidencias ni introducir excepciones')
    with database.transaction():
        row=next((r for r in planning.report(area,employee,day,day) if quantities(r)[kind]>0),None)
        if row is None: raise ValueError('No se detectó esta incidencia en la jornada; no se puede validar')
        previous=planning.decisions(day,day).get((employee,day),{})
        updated={**previous,**data}
        if kind=='FALTANTE':
            code=data.get('cod_ausencia','')
            if not code or code not in planning.CODIGOS_JUSTIFICACION or code=='732':
                raise ValueError('Seleccione el código correspondiente al tiempo faltante')
            policy=database.read_catalog('config').get('politicas_ausencia',{})
            updated['remunerada']=planning.PAID_DEFAULTS.get(code,policy.get(code))
        planning.save_decision(employee,day,updated,user,audit_combined=False)
        result=planning.report(area,employee,day,day)
        sync(result,user)
