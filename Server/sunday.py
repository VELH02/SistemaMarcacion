"""ALICAPSA agreement: a worked Sunday earns at least eight weekend hours."""
import json
from collections import defaultdict
from datetime import date, timedelta


def attach_rest_work(schedule, grouped, unmatched, employees, shifts):
    """Use an RH-validated reference without replacing the scheduled rest day."""
    import planning
    pending=defaultdict(list)
    for item in unmatched:
        if item['start'] and item['start'].weekday()==6:
            key=(item['employee'],item['start'].date().isoformat())
            if key not in schedule or schedule[key]['turno_id']=='DESCANSO':
                pending[key].append(item)
    attached=set()
    for (employee,day),sessions in pending.items():
        actual=min(s['start'] for s in sessions)
        candidates=[]
        for (emp,ref_day),assignment in schedule.items():
            if emp!=employee or assignment['turno_id']=='DESCANSO': continue
            shift=json.loads(assignment['turno_json'])
            if shift.get('configurado'):
                candidates.append((assignment['turno_id'],shift,ref_day,'ASIGNACION'))
        for identifier,shift in shifts.items():
            if shift.get('configurado'):
                candidates.append((identifier,shift,'','CATALOGO_RH'))
        def score(candidate):
            identifier,shift,ref_day,origin=candidate
            ref=planning.bounds(day,shift)[0]
            distance=min(abs((actual-ref+timedelta(days=i)).total_seconds()) for i in (-1,0,1))
            date_distance=abs((date.fromisoformat(day)-date.fromisoformat(ref_day)).days) if ref_day else 999
            return distance,origin!='ASIGNACION',date_distance,bool(ref_day and ref_day>day),identifier
        candidates.sort(key=score)
        if not candidates or score(candidates[0])[0]>4*3600: continue
        identifier,shift,ref_day,origin=candidates[0]
        snapshot={**shift,'domingo_referencia':True,'referencia_fecha':ref_day,'referencia_origen':origin}
        schedule[(employee,day)]=dict(empleado_id=employee,fecha=day,turno_id=identifier,turno_json=json.dumps(snapshot,ensure_ascii=False))
        grouped[(employee,day)].extend(sessions)
        attached.update(id(s) for s in sessions)
    return [s for s in unmatched if id(s) not in attached]


def calculate(base, shift, work, decision, config):
    import planning
    day=base['fecha']
    limit=planning.LIMITS[base['jornada']]
    remaining=limit*3600
    ordinary,extra=[],[]
    for a,b in work:
        duration=min((b-a).total_seconds(),remaining)
        if duration>0: ordinary.append((a,a+timedelta(seconds=duration)))
        if a+timedelta(seconds=duration)<b: extra.append((a+timedelta(seconds=duration),b))
        remaining-=duration
    normal=planning.seconds(ordinary)/3600
    state=decision.get('domingo_estado','pendiente')
    paid=state=='aprobada'
    code='650' if planning.holiday(date.fromisoformat(day),config)=='feriado' else '652'
    # Eight paid-equivalent hours are guaranteed; actual work is never fabricated.
    base.update(estado='COMPLETO',dia_descanso_trabajado=True,horas_totales=planning.seconds(work)/3600,
        horas_ordinarias=normal,horas_fin_semana=8.0,horas_fin_semana_aprobadas=8.0 if paid else 0,
        complemento_dominical=max(0,8-normal*8/limit),domingo_estado=state,
        motivo_domingo=decision.get('motivo_domingo',''),codigo_domingo=code,
        origen_turno_domingo=shift.get('referencia_origen','ASIGNACION_DOMINICAL'),
        horas_pagables=limit if paid else 0,horas_equivalentes=8.0 if paid else 0,
        ausencia=False,ausencia_horas=0,descuento_horas=0,permiso_horas=0,cod_ausencia='',
        extra_horas=planning.seconds(extra)/3600,intervalos_extra=extra,
        extra_aprobadas=planning.seconds(extra)/3600 if base['he_aprobadas'] else 0,
        fuente_domingo=dict(regla='ALICAPSA_DOMINGO_MINIMO_8',turno=base['turno_id'],horario=shift,
            entrada=base['entrada_fecha'],salida=base['salida_fecha'],horas_reales=planning.seconds(work)/3600,
            horas_reconocidas=8.0,limite_ordinario_legal=limit))
    base['alertas']=[a for a in base['alertas'] if a!='HORARIO_EXCEDE_LIMITE_ORDINARIO']
    if shift.get('domingo_referencia'):
        base.update(tardanza_min=0,anticipacion_min=0)
    base['tardanza_computable_min']=0 if base['tardanza_estado']=='invalidada' else base['tardanza_min']
    if base['tardanza_min'] and base['tardanza_estado']=='pendiente': base['alertas'].append('TARDANZA_PENDIENTE')
    if state=='pendiente': base['alertas'].append('DOMINGO_PENDIENTE')
    if extra and base['he_estado']=='pendiente': base['alertas'].append('HE_PENDIENTE')
    base['alertas'].append('DESCANSO_TRABAJADO_REQUIERE_COMPENSACION')
    if paid:
        base['conceptos'].append(dict(codigo_colaborador=base['id'],con_codigo=code,
            con_nombre=planning.CONCEPTOS_PANAMA[code]['nombre'],cantidad_horas=8.0,
            tratamiento='FIN_SEMANA',factor=2.5 if code=='650' else 1.5))
    if base['tardanza_computable_min']:
        base['conceptos'].append(dict(codigo_colaborador=base['id'],con_codigo='732',
            con_nombre=planning.CODIGOS_JUSTIFICACION['732'],cantidad_horas=base['tardanza_min']/60,
            tratamiento='TARDANZA_SIN_DESCUENTO_DOMINGO',factor=0))
    return base
