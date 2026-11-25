# ======================================================================
# MOTOR DE RECONOCIMIENTO FACIAL Y DETECCIÓN DE PARPADEO (LIVENESS)
# ======================================================================
import numpy as np
import cv2
import face_recognition

from config import UMBRAL_DISTANCIA_ESTRICTO


def calcular_ear(ojo):
    """Calcula el Eye Aspect Ratio (EAR) para detección de parpadeo."""
    A = np.linalg.norm(ojo[1] - ojo[5])
    B = np.linalg.norm(ojo[2] - ojo[4])
    C = np.linalg.norm(ojo[0] - ojo[3])
    return (A + B) / (2.0 * C) if C > 0 else 0.0


def extraer_vector_facial(frame_rgb):
    """Extrae el vector facial de 128 dimensiones de un fotograma RGB (para enrolamiento)."""
    encodings = face_recognition.face_encodings(frame_rgb)
    if len(encodings) != 1:
        return None
    return encodings[0]


def worker_reconocimiento(input_queue, output_queue):
    """Proceso independiente que valida parpadeo (liveness) y similitud biométrica."""
    cont_parpadeos = 0
    ojo_cerrado = False
    session_id = None

    while True:
        try:
            item = input_queue.get()
            if item is None:
                break

            if isinstance(item, tuple) and item[0] == "RESET":
                session_id = item[1]
                cont_parpadeos = 0
                ojo_cerrado = False
                continue

            incoming_session, frame_rgb, vector_registrado = item
            if incoming_session != session_id:
                session_id = incoming_session
                cont_parpadeos, ojo_cerrado = 0, False
            frame_h, frame_w, _ = frame_rgb.shape

            frame_small = cv2.resize(frame_rgb, (0, 0), fx=0.5, fy=0.5)
            locations_small = face_recognition.face_locations(frame_small, model="hog")

            if len(locations_small) != 1:
                cont_parpadeos, ojo_cerrado = 0, False
                output_queue.put({
                    "session_id": session_id,
                    "rect": None,
                    "verificado": False,
                    "similitud": 0.0,
                    "alerta_liveness": "Buscando rostro..." if not locations_small else "Debe haber una sola persona ante la cámara",
                })
                continue

            top, right, bottom, left = locations_small[0]
            l, t, r, b = left * 2, top * 2, right * 2, bottom * 2
            l, t, r, b = max(0, l), max(0, t), min(frame_w, r), min(frame_h, b)

            landmarks_list = face_recognition.face_landmarks(frame_rgb, [(t, r, b, l)])

            if len(landmarks_list) > 0:
                landmarks = landmarks_list[0]
                ojo_izq = np.array(landmarks["left_eye"])
                ojo_der = np.array(landmarks["right_eye"])

                ear_promedio = (calcular_ear(ojo_izq) + calcular_ear(ojo_der)) / 2.0

                if ear_promedio < 0.20:
                    ojo_cerrado = True
                elif ear_promedio > 0.25 and ojo_cerrado:
                    cont_parpadeos += 1
                    ojo_cerrado = False

            if cont_parpadeos < 1:
                output_queue.put({
                    "session_id": session_id,
                    "rect": (l, t, r, b),
                    "verificado": False,
                    "similitud": 0.0,
                    "alerta_liveness": "👁 PARPADEE PARA PROBAR QUE ES REAL",
                })
                continue

            encodings = face_recognition.face_encodings(frame_rgb, [(t, r, b, l)])
            if len(encodings) > 0:
                encoding_capturado = encodings[0]
                distancia = face_recognition.face_distance([vector_registrado], encoding_capturado)[0]
                es_valido = distancia < UMBRAL_DISTANCIA_ESTRICTO
                similitud = max(0.0, min(100.0, (1.0 - (distancia / UMBRAL_DISTANCIA_ESTRICTO)) * 100))

                output_queue.put({
                    "session_id": session_id,
                    "rect": (l, t, r, b),
                    "verificado": es_valido,
                    "similitud": similitud,
                    "alerta_liveness": "",
                })
            else:
                output_queue.put({
                    "session_id": session_id,
                    "rect": (l, t, r, b),
                    "verificado": False,
                    "similitud": 0.0,
                    "alerta_liveness": "",
                })

        except Exception:
            cont_parpadeos, ojo_cerrado = 0, False
            output_queue.put(dict(session_id=session_id,rect=None,verificado=False,similitud=0.0,
                alerta_liveness="Error de reconocimiento. Reintente la verificación."))
