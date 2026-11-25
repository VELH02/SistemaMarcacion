"""Códigos internos heredados. El motor de planning calcula los factores legales por tramo.

Los factores históricos del catálogo no sustituyen los calculados en la exportación.
"""

CODIGOS_JUSTIFICACION = {
    "300": "ASISTENCIA MEDICA",
    "730": "NO JUSTIFICADA",
    "302": "CARNET DE SALUD",
    "110": "INCAPACIDAD ACCIDENTE DE TRABAJO",
    "100": "ENFERMEDAD COMUN",
    "760": "INCAPACIDAD NO PAGADA",
    "120": "LICENCIA DE MATERNIDAD",
    "750": "PERMISO NO REMUNERADO",
    "540": "PERMISO DE FALLECIMIENTO",
    "330": "PERMISO DE MATERNIDAD",
    "350": "PERMISO DE NACIMIENTO",
    "310": "PERMISO REMUNERADO",
    "320": "PERMISO SINDICAL",
    "720": "SUSPENSION",
    "732": "TARDANZAS"
}

CONCEPTOS_PANAMA = {
    "450": {"nombre": "EXTRA JORN DIURNA", "factor": 1.25},
    "452": {"nombre": "EXTRA JORN MIXTA NOC-DIU", "factor": 1.75},
    "454": {"nombre": "EXC EXTRA JOR DIURNA", "factor": 2.19},
    "456": {"nombre": "EXC EXTRA JOR MIXTA N-D", "factor": 3.06},
    "550": {"nombre": "EXTRA JORN NOCTURNA", "factor": 1.50},
    "552": {"nombre": "EXTRA JORN MIXTA DIU-NOC", "factor": 1.50},
    "554": {"nombre": "EXC EXTRA JOR NOCTURNA", "factor": 2.63},
    "556": {"nombre": "EXC EXTRA JOR MIXTA D-N", "factor": 2.63},
    "650": {"nombre": "JORNADA DIA FERIADO 2.5", "factor": 2.50},
    "652": {"nombre": "JORNADA FIN DE SEMANA 1.5", "factor": 1.50},
    "654": {"nombre": "RECARGO DE DIA FERIADO 1.5", "factor": 1.50},
    "656": {"nombre": "RECARGO DE DOMINGO .5", "factor": 0.50},
    "866": {"nombre": "EXTRA JOR DIURNA DIA FER", "factor": 3.13},
    "852": {"nombre": "EXTRA JOR MIXTA N-D DIA FER", "factor": 4.38},
    "854": {"nombre": "EXC EXT JOR DIURNA DIA FER", "factor": 5.47},
    "856": {"nombre": "EXC EXT JOR MIXTA N-D D.FER", "factor": 7.66},
    "858": {"nombre": "EXTRA JOR DIUR FIN SEMANA", "factor": 1.88},
    "860": {"nombre": "EXT JOR MIXTA N-D FIN SEM", "factor": 2.63},
    "862": {"nombre": "EXC EXT JOR DIUR FIN SEM", "factor": 3.28},
    "864": {"nombre": "EXC EXT JOR MIXTA N-D FIN SEM", "factor": 4.59},
    "950": {"nombre": "EXTRA JOR NOCTURNA DIA FER", "factor": 3.75},
    "952": {"nombre": "EXTRA JOR MIXTA D-N DIA FER", "factor": 3.75},
    "954": {"nombre": "EXC EXT JOR NOCT DIA FER", "factor": 6.56},
    "956": {"nombre": "EXC EXT JOR MIXTA D-N D.FER", "factor": 6.56},
    "958": {"nombre": "EXTRA JOR NOCT FIN SEMANA", "factor": 2.25},
    "960": {"nombre": "EXT JOR MIXTA D-N FIN SEM", "factor": 2.25},
    "962": {"nombre": "EXC EXT JOR NOCT FIN SEM", "factor": 3.94},
    "964": {"nombre": "EXC EXT JOR MIXTA D-N FIN SEM", "factor": 3.94}
}

