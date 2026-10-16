#Agregar un historico, just in case de que la persona no le autentique
#Servidor de Google tema horas
#Conseguir una pantalla y camara adicional (Backup)
#Cambiar Color de botones de main, por un gris claro
#Crear un super user para el registro (coordinadores)
#Conseguir un par de UPS para las 2 pantallitas cool
#Conseguir el espacio (fisico) para las UPS
#Hacer que el reloj se vea en la pantalla principal
import os
import time
import json
import multiprocessing as mp
import tkinter as tk
from tkinter import ttk
from datetime import datetime
import numpy as np
import cv2
import face_recognition
from PIL import Image, ImageTk
import requests
import urllib3
import sys
# Desactivar advertencias de certificados SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ----------------------------------------------------------------------
# CONFIGURACIÓN DE ARCHIVOS, IP Y PALETA DE COLORES (VERDE NUTRESA)
# ----------------------------------------------------------------------
CONFIG_FILE = "config.json"
DEFAULT_SERVER_URL = "http://127.0.0.1:5000/api"
DIR_ROSTROS = "base_rostros"
ADMIN_PIN = "123456"

UMBRAL_DISTANCIA_ESTRICTO = 0.48  

FONT_PRIMARY = "sans-serif"

COLOR_PRIMARY = "#008037"        # Verde Oficial Nutresa
COLOR_PRIMARY_HOVER = "#00642B"  # Verde Oscuro (Hover)
COLOR_SECONDARY = "#F2F5F3"      # Gris Bosque Oscuro
COLOR_SECONDARY_HOVER = "#1E2622"
COLOR_BG = "#F2F5F3"             # Fondo General
COLOR_CARD = "#FFFFFF"           # Tarjetas / Contenedores
COLOR_TEXT_DARK = "#1A241E"      # Texto Principal
COLOR_MUTED = "#637368"          # Texto Secundario
COLOR_BORDER = "#D3DED7"         # Bordes
COLOR_DANGER = "#D9383A"         # Rojo Alerta / Borrar
COLOR_WARNING = "#D9822B"        # Naranja Advertencia


# ----------------------------------------------------------------------
# ENTORNO LOCAL Y CONFIGURACIÓN DEL SERVIDOR
# ----------------------------------------------------------------------
def inicializar_entorno():
    if not os.path.exists(DIR_ROSTROS):
        os.makedirs(DIR_ROSTROS)


def parse_url_to_ip_port(url):
    clean_url = url.replace("/api", "").rstrip("/")
    if ":" in clean_url.replace("http://", "").replace("https://", ""):
        parts = clean_url.rsplit(":", 1)
        return parts[0], parts[1]
    return clean_url, "5000"


def cargar_configuracion():
    if not os.path.exists(CONFIG_FILE):
        config = {
            "server_ip": "http://127.0.0.1",
            "server_port": "5000",
            "server_url": DEFAULT_SERVER_URL
        }
        guardar_configuracion("http://127.0.0.1", "5000")
        return config
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "server_ip" not in data or "server_port" not in data:
                ip, port = parse_url_to_ip_port(data.get("server_url", DEFAULT_SERVER_URL))
                data["server_ip"] = ip
                data["server_port"] = port
            return data
    except Exception:
        return {
            "server_ip": "http://127.0.0.1",
            "server_port": "5000",
            "server_url": DEFAULT_SERVER_URL
        }


def guardar_configuracion(server_ip, server_port):
    ip = server_ip.strip().rstrip("/")
    port = server_port.strip()
    
    if not ip.startswith("http://") and not ip.startswith("https://"):
        ip = f"http://{ip}"
        
    full_url = f"{ip}:{port}/api" if port else f"{ip}/api"
    
    config = {
        "server_ip": ip,
        "server_port": port,
        "server_url": full_url
    }
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)
    return config


def get_server_url():
    config = cargar_configuracion()
    return config.get("server_url", DEFAULT_SERVER_URL)


# ----------------------------------------------------------------------
# GESTIÓN BIOMÉTRICA
# ----------------------------------------------------------------------
def obtener_vector_biometrico(emp_id):
    inicializar_entorno()
    ruta_local = os.path.join(DIR_ROSTROS, f"{emp_id}.npy")
    server_url = get_server_url()

    if os.path.exists(ruta_local):
        try:
            vector = np.load(ruta_local)
            try:
                res = requests.get(f"{server_url}/empleados/{emp_id}", timeout=3, verify=False)
                depto = res.json().get("departamento", "N/A") if res.status_code == 200 else "N/A"
            except Exception:
                depto = "N/A"
            return True, depto, vector, "OK (Cargado de base local)"
        except Exception:
            pass

    try:
        res = requests.get(f"{server_url}/empleados/{emp_id}", timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json()
            vector_list = data["vector_facial"]
            vector = np.array(vector_list, dtype=np.float64)
            np.save(ruta_local, vector)
            return True, data.get("departamento", "N/A"), vector, "✓ Vector restaurado desde Backup Servidor"
        elif res.status_code == 404:
            return False, "", None, f"⚠️ El ID {emp_id} no está registrado."
        else:
            return False, "", None, f"⚠️ Respuesta del servidor: HTTP {res.status_code}"
    except requests.exceptions.RequestException as e:
        return False, "", None, f"❌ Sin conexión al puerto REST del servidor ({server_url})"


def api_guardar_nuevo_empleado(emp_id, departamento, vector_np):
    inicializar_entorno()
    ruta_local = os.path.join(DIR_ROSTROS, f"{emp_id}.npy")
    np.save(ruta_local, vector_np)

    server_url = get_server_url()
    payload = {
        "empleado_id": str(emp_id),
        "departamento": departamento,
        "vector_facial": vector_np.tolist()
    }
    try:
        res = requests.post(f"{server_url}/empleados/enrolar", json=payload, timeout=5, verify=False)
        if res.status_code in [200, 201]:
            return True, "Colaborador enrolado localmente y respaldado en servidor."
        else:
            return True, "Enrolado localmente (⚠️ No se pudo hacer el backup en servidor)."
    except requests.exceptions.RequestException:
        return True, "Enrolado localmente (⚠️ Sin conexión con servidor para backup)."


def api_registrar_marcacion(emp_id, tipo_marcacion, nota=""):
    server_url = get_server_url()
    payload = {
        "empleado_id": str(emp_id),
        "tipo_marcacion": tipo_marcacion,
        "nota": nota
    }
    try:
        res = requests.post(f"{server_url}/marcaciones", json=payload, timeout=5, verify=False)
        if res.status_code in [200, 201]:
            data = res.json()
            return True, data.get("mensaje", "Marcación registrada")
        else:
            err_msg = res.json().get("error", "Error en el servidor")
            return False, f"⚠️ {err_msg}"
    except requests.exceptions.RequestException as e:
        return False, f"❌ Error de conexión al servidor ({e})"


def api_obtener_historial(emp_id):
    server_url = get_server_url()
    try:
        res = requests.get(f"{server_url}/historial/{emp_id}", timeout=5, verify=False)
        if res.status_code == 200:
            return res.json().get("historial", [])
        return []
    except Exception:
        return []


# ----------------------------------------------------------------------
# DETECCIÓN DE PARPADEO (EAR)
# ----------------------------------------------------------------------
def calcular_ear(ojo):
    A = np.linalg.norm(ojo[1] - ojo[5])
    B = np.linalg.norm(ojo[2] - ojo[4])
    C = np.linalg.norm(ojo[0] - ojo[3])
    return (A + B) / (2.0 * C)


# ----------------------------------------------------------------------
# WORKER INDEPENDIENTE
# ----------------------------------------------------------------------
def worker_reconocimiento(input_queue, output_queue):
    cont_parpadeos = 0
    ojo_cerrado = False

    while True:
        try:
            item = input_queue.get()
            if item is None:
                break

            if item == "RESET":
                cont_parpadeos = 0
                ojo_cerrado = False
                continue

            frame_rgb, vector_registrado = item
            frame_h, frame_w, _ = frame_rgb.shape

            frame_small = cv2.resize(frame_rgb, (0, 0), fx=0.5, fy=0.5)
            locations_small = face_recognition.face_locations(frame_small, model="hog")

            if len(locations_small) == 0:
                output_queue.put({
                    "rect": None, "verificado": False, "similitud": 0.0,
                    "alerta_liveness": "Buscando rostro..."
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

                ear_izq = calcular_ear(ojo_izq)
                ear_der = calcular_ear(ojo_der)
                ear_promedio = (ear_izq + ear_der) / 2.0

                if ear_promedio < 0.20:
                    ojo_cerrado = True
                elif ear_promedio > 0.25 and ojo_cerrado:
                    cont_parpadeos += 1
                    ojo_cerrado = False

            if cont_parpadeos < 1:
                output_queue.put({
                    "rect": (l, t, r, b), "verificado": False, "similitud": 0.0,
                    "alerta_liveness": "👁 PARPADEE PARA PROBAR QUE ES REAL"
                })
                continue

            encodings = face_recognition.face_encodings(frame_rgb, [(t, r, b, l)])
            if len(encodings) > 0:
                encoding_capturado = encodings[0]
                distancia = face_recognition.face_distance([vector_registrado], encoding_capturado)[0]
                es_valido = distancia < UMBRAL_DISTANCIA_ESTRICTO
                similitud = max(0.0, min(100.0, (1.0 - (distancia / UMBRAL_DISTANCIA_ESTRICTO)) * 100))

                output_queue.put({
                    "rect": (l, t, r, b),
                    "verificado": es_valido,
                    "similitud": similitud,
                    "alerta_liveness": ""
                })
            else:
                output_queue.put({
                    "rect": (l, t, r, b), "verificado": False, "similitud": 0.0,
                    "alerta_liveness": ""
                })

        except Exception:
            pass


# ----------------------------------------------------------------------
# COMPONENTE ENCABEZADO
# ----------------------------------------------------------------------
class HeaderNutresa(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLOR_BG)
        
        top_accent = tk.Frame(self, bg=COLOR_PRIMARY, height=6)
        top_accent.pack(fill="x", side="top")

        brand_frame = tk.Frame(self, bg=COLOR_BG)
        brand_frame.pack(pady=(8, 4))

        if os.path.exists("logo.png"):
            try:
                img_pil = Image.open("logo.png")
                img_pil.thumbnail((220, 45), Image.Resampling.LANCZOS)
                self.img = ImageTk.PhotoImage(img_pil)
                lbl_logo = tk.Label(brand_frame, image=self.img, bg=COLOR_BG)
                lbl_logo.pack()
            except Exception:
                self._crear_logo_texto(brand_frame)
        else:
            self._crear_logo_texto(brand_frame)

    def _crear_logo_texto(self, parent):
        lbl_brand = tk.Label(parent, text="Grupo Nutresa", font=(FONT_PRIMARY, 18, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG)
        lbl_brand.pack()
        lbl_sub = tk.Label(parent, text="SISTEMA DE ASISTENCIA Y TIEMPO", font=(FONT_PRIMARY, 8, "bold"), fg=COLOR_MUTED, bg=COLOR_BG)
        lbl_sub.pack(pady=(1, 0))


# ----------------------------------------------------------------------
# APLICACIÓN PRINCIPAL
# ----------------------------------------------------------------------
class SistemaMarcacionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Grupo Nutresa - Control de Asistencia Biométrico")
        self.geometry("840x670")
        self.minsize(800, 600)
        self.configure(bg=COLOR_BG)

        inicializar_entorno()

        self.current_emp_code = ""
        self.current_emp_depto = ""
        self.current_emp_vector = None
        self.current_action = ""
        self.admin_target = "PantallaEnrolar"
        
        self.timeout_seconds = 30
        self.timer_id = None
        self.t_inicio_solicitud = 0.0

        self.input_queue = mp.Queue()
        self.output_queue = mp.Queue()
        self.worker_process = mp.Process(
            target=worker_reconocimiento,
            args=(self.input_queue, self.output_queue),
            daemon=True
        )
        self.worker_process.start()

        self.container = tk.Frame(self, bg=COLOR_BG)
        self.container.pack(fill="both", expand=True)

        self.bind_all("<Button-1>", self.reset_inactivity_timer)
        self.bind_all("<Key>", self.reset_inactivity_timer)

        self.frames = {}
        for F in (PantallaPrincipal, PantallaTeclado, PantallaBiometrica, PantallaHistorial, PantallaEnrolar, PantallaAdminPin, PantallaConfiguracion):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.show_frame("PantallaPrincipal")

    def show_frame(self, page_name):
        for name, frame in self.frames.items():
            if hasattr(frame, "detener_camara"):
                frame.detener_camara()

        frame = self.frames[page_name]
        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()
        self.reset_inactivity_timer()

    def reset_inactivity_timer(self, event=None):
        if self.timer_id:
            self.after_cancel(self.timer_id)
        
        if self.get_current_frame_name() != "PantallaPrincipal":
            self.timer_id = self.after(self.timeout_seconds * 1000, self.auto_return_to_main)

    def auto_return_to_main(self):
        self.current_emp_code = ""
        self.current_emp_vector = None
        self.current_action = ""
        self.show_frame("PantallaPrincipal")

    def get_current_frame_name(self):
        for name, frame in self.frames.items():
            if frame.winfo_viewable():
                return name
        return "PantallaPrincipal"

    def on_closing(self):
        try:
            self.input_queue.put(None)
        except Exception:
            pass
        self.destroy()


# ----------------------------------------------------------------------
# VISTA: PANTALLA PRINCIPAL
# ----------------------------------------------------------------------
class PantallaPrincipal(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.iconos = {}

        HeaderNutresa(self).pack(fill="x")

        lbl_instruccion = tk.Label(
            self, text="SELECCIONE LA OPCIÓN QUE DESEA REGISTRAR", 
            font=(FONT_PRIMARY, 12, "bold"), fg="#37414B", bg=COLOR_BG
        )
        lbl_instruccion.pack(pady=(5, 5))

        center_card = tk.Frame(self, bg=COLOR_PRIMARY, bd=1, relief="solid", highlightthickness=0)
        center_card.pack(expand=True, padx=70, pady=(5, 10), fill="both")

        grid_frame = tk.Frame(center_card, bg=COLOR_PRIMARY)
        grid_frame.pack(expand=True, fill="both", padx=10, pady=10)

        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, minsize=10)
        grid_frame.columnconfigure(2, weight=1)
        
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.rowconfigure(1, minsize=10)
        grid_frame.rowconfigure(2, weight=1)

        self._crear_boton_estilizado(
            grid_frame, "", "", COLOR_SECONDARY, COLOR_SECONDARY_HOVER, 
            0, 0, "ENTRADA", img_filename="entrada.png"
        )
        self._crear_boton_estilizado(
            grid_frame, "", "", COLOR_SECONDARY, COLOR_SECONDARY_HOVER, 
            0, 2, "SALIDA", img_filename="salida.png"
        )
        
        self._crear_boton_estilizado(
            grid_frame, "📋  MARCACIONES", "CONSULTAR HISTORIAL", COLOR_SECONDARY, COLOR_SECONDARY_HOVER, 
            2, 0, "MARCACIONES", 
        )
        self._crear_boton_estilizado(
            grid_frame, "⏱  HORA EXTRA", "SOBRETIEMPO ESPECIAL", COLOR_SECONDARY, COLOR_SECONDARY_HOVER, 
            2, 2, "TIEMPO EXTRA"
        )

        admin_btns_frame = tk.Frame(self, bg=COLOR_BG)
        admin_btns_frame.pack(pady=(0, 10))

        btn_enrolar = tk.Button(
            admin_btns_frame, text="⚙️  AGREGAR NUEVO COLABORADOR (ADMIN)", font=(FONT_PRIMARY, 9, "bold"),
            bg=COLOR_BG, fg=COLOR_MUTED, activebackground=COLOR_BORDER, bd=0, relief="flat", cursor="hand2",
            command=lambda: self.abrir_admin("PantallaEnrolar")
        )
        btn_enrolar.pack(side="left", padx=10)

        btn_config = tk.Button(
            admin_btns_frame, text="🌐  CONFIGURAR IP SERVIDOR (ADMIN)", font=(FONT_PRIMARY, 9, "bold"),
            bg=COLOR_BG, fg=COLOR_MUTED, activebackground=COLOR_BORDER, bd=0, relief="flat", cursor="hand2",
            command=lambda: self.abrir_admin("PantallaConfiguracion")
        )
        btn_config.pack(side="left", padx=10)

    def _crear_boton_estilizado(self, parent, titulo, subtitulo, bg, bg_hover, row, col, accion, img_filename=None):
        img_obj = None
        if img_filename and os.path.exists(img_filename):
            try:
                pil_img = Image.open(img_filename)
                pil_img = pil_img.resize((120, 80), Image.Resampling.LANCZOS)
                img_obj = ImageTk.PhotoImage(pil_img)
                self.iconos[accion] = img_obj
            except Exception:
                img_obj = None

        texto_boton = f"{titulo}\n{subtitulo}" if not img_filename else f"{titulo}\n{subtitulo}"

        btn_kwargs = {
            "text": texto_boton,
            "font": (FONT_PRIMARY, 14, "bold"),
            "bg": bg,
            "fg": "#37414B",
            "activebackground": bg_hover,
            "activeforeground": "#FFFFFF",
            "bd": 0,
            "relief": "flat",
            "cursor": "hand2",
            "justify": "center",
            "command": lambda: self.seleccionar_accion(accion)
        }

        if img_obj:
            btn_kwargs["image"] = img_obj
            btn_kwargs["compound"] = "top"

        btn = tk.Button(parent, **btn_kwargs)
        btn.bind("<Enter>", lambda e: btn.config(bg=bg_hover))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        btn.grid(row=row, column=col, sticky="nsew", ipadx=10, ipady=10)

    def abrir_admin(self, destino):
        self.controller.admin_target = destino
        self.controller.show_frame("PantallaAdminPin")

    def seleccionar_accion(self, accion):
        self.controller.current_action = accion
        self.controller.current_emp_code = ""
        self.controller.current_emp_vector = None
        self.controller.show_frame("PantallaTeclado")


# ----------------------------------------------------------------------
# VISTA: ACCESO ADMINISTRATIVO
# ----------------------------------------------------------------------
class PantallaAdminPin(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid")
        card.pack(pady=10, padx=140, fill="both", expand=True)

        lbl_title = tk.Label(card, text="ACCESO ADMINISTRATIVO", font=(FONT_PRIMARY, 12, "bold"), fg=COLOR_TEXT_DARK, bg=COLOR_CARD)
        lbl_title.pack(pady=(10, 2))

        self.display_var = tk.StringVar()
        self.display = tk.Entry(
            card, textvariable=self.display_var, show="*", font=(FONT_PRIMARY, 18, "bold"),
            justify="center", bd=2, relief="solid", state="readonly", 
            fg=COLOR_TEXT_DARK, bg=COLOR_CARD
        )
        self.display.pack(pady=5, ipadx=10, ipady=4)

        self.lbl_status = tk.Label(card, text="", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_CARD)
        self.lbl_status.pack(pady=2)

        keypad = tk.Frame(card, bg=COLOR_CARD)
        keypad.pack(pady=5)

        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('BORRAR', 3, 0), ('0', 3, 1), ('ENTRAR', 3, 2)
        ]

        for text, row, col in buttons:
            if text == 'BORRAR':
                btn = tk.Button(keypad, text=text, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_DANGER, fg="#FFFFFF", width=7, height=2, bd=0, relief="flat", cursor="hand2", command=self.press_borrar)
            elif text == 'ENTRAR':
                btn = tk.Button(keypad, text=text, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_PRIMARY, fg="#FFFFFF", width=7, height=2, bd=0, relief="flat", cursor="hand2", command=self.verificar_pin)
            else:
                btn = tk.Button(keypad, text=text, font=(FONT_PRIMARY, 12, "bold"), bg=COLOR_BG, fg=COLOR_TEXT_DARK, width=5, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=text: self.press_num(t))
            btn.grid(row=row, column=col, padx=3, pady=3)

        btn_cancel = tk.Button(card, text="CANCELAR", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_SECONDARY, fg="#FFFFFF", bd=0, relief="flat", cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        btn_cancel.pack(pady=8, ipadx=15, ipady=4)

    def on_show(self):
        self.display_var.set("")
        self.lbl_status.config(text="")

    def press_num(self, num):
        self.lbl_status.config(text="")
        curr = self.display_var.get()
        if len(curr) < 8:
            self.display_var.set(curr + num)

    def press_borrar(self):
        self.lbl_status.config(text="")
        self.display_var.set(self.display_var.get()[:-1])

    def verificar_pin(self):
        if self.display_var.get() == ADMIN_PIN:
            target = getattr(self.controller, 'admin_target', 'PantallaEnrolar')
            self.controller.show_frame(target)
        else:
            self.lbl_status.config(text="❌ PIN Incorrecto", fg=COLOR_DANGER)
            self.display_var.set("")


# ----------------------------------------------------------------------
# VISTA: CONFIGURACIÓN CON PRUEBA DE CONEXIÓN ROBUSTA Y FLEXIBLE
# ----------------------------------------------------------------------
class PantallaConfiguracion(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        lbl_title = tk.Label(self, text="CONFIGURACIÓN DE RED Y SERVIDOR REST API", font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG)
        lbl_title.pack(pady=2)

        card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid")
        card.pack(pady=2, padx=30, fill="both", expand=True)

        fields_frame = tk.Frame(card, bg=COLOR_CARD)
        fields_frame.pack(pady=(6, 4), padx=20, fill="x")

        # IP
        ip_box = tk.Frame(fields_frame, bg=COLOR_CARD)
        ip_box.pack(side="left", fill="x", expand=True, padx=(0, 10))

        tk.Label(ip_box, text="1. DIRECCIÓN IP / HOST:", font=(FONT_PRIMARY, 9, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w")
        self.var_ip = tk.StringVar()
        self.ent_ip = tk.Entry(ip_box, textvariable=self.var_ip, font=(FONT_PRIMARY, 12, "bold"), justify="center", bd=1, relief="solid", bg=COLOR_BG, fg=COLOR_TEXT_DARK)
        self.ent_ip.pack(fill="x", ipady=5)

        # Puerto
        port_box = tk.Frame(fields_frame, bg=COLOR_CARD)
        port_box.pack(side="right", padx=(10, 0))

        tk.Label(port_box, text="2. PUERTO:", font=(FONT_PRIMARY, 9, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w")
        self.var_port = tk.StringVar()
        self.ent_port = tk.Entry(port_box, textvariable=self.var_port, font=(FONT_PRIMARY, 12, "bold"), justify="center", width=12, bd=1, relief="solid", bg=COLOR_BG, fg=COLOR_TEXT_DARK)
        self.ent_port.pack(ipady=5)

        self.active_var = self.var_ip
        self.active_entry = self.ent_ip

        self.ent_ip.bind("<Button-1>", lambda e: self.set_active(self.var_ip, self.ent_ip))
        self.ent_port.bind("<Button-1>", lambda e: self.set_active(self.var_port, self.ent_port))

        shortcuts_frame = tk.Frame(card, bg=COLOR_CARD)
        shortcuts_frame.pack(pady=4)

        shortcuts = [
            ("http://", lambda: self.add_shortcut_ip("http://")),
            ("https://", lambda: self.add_shortcut_ip("https://")),
            ("192.168.", lambda: self.add_shortcut_ip("192.168.")),
            (":5000/api", self.apply_shortcut_5000),
            ("127.0.0.1", lambda: self.add_shortcut_ip("127.0.0.1"))
        ]

        for txt, cmd in shortcuts:
            btn = tk.Button(shortcuts_frame, text=txt, font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_BG, fg=COLOR_PRIMARY, bd=1, relief="solid", cursor="hand2", padx=10, pady=5, command=cmd)
            btn.pack(side="left", padx=4)

        keypad_frame = tk.Frame(card, bg=COLOR_CARD)
        keypad_frame.pack(pady=4)

        keypad_buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2), ('.', 0, 3), ('⌫ BORRAR', 0, 4),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2), (':', 1, 3), ('LIMPIAR', 1, 4),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2), ('/', 2, 3), ('⇄ CAMBIAR', 2, 4),
            ('0', 3, 0), ('-', 3, 3)
        ]

        for item in keypad_buttons:
            txt, r, c = item[0], item[1], item[2]
            if txt == '⌫ BORRAR':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_DANGER, fg="#FFFFFF", width=11, height=2, bd=0, relief="flat", cursor="hand2", command=self.borrar_caracter)
            elif txt == 'LIMPIAR':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_WARNING, fg="#FFFFFF", width=11, height=2, bd=0, relief="flat", cursor="hand2", command=self.borrar_todo)
            elif txt == '⇄ CAMBIAR':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_SECONDARY, fg="#FFFFFF", width=11, height=2, bd=0, relief="flat", cursor="hand2", command=self.toggle_active_field)
            elif txt == '0':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 13, "bold"), bg=COLOR_BG, fg=COLOR_TEXT_DARK, width=18, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=txt: self.add_text(t))
                btn.grid(row=r, column=c, columnspan=3, padx=3, pady=3)
                continue
            else:
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 13, "bold"), bg=COLOR_BG, fg=COLOR_TEXT_DARK, width=5, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=txt: self.add_text(t))
            
            btn.grid(row=r, column=c, padx=3, pady=3)

        self.lbl_status = tk.Label(card, text="", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_CARD, wraplength=500)
        self.lbl_status.pack(pady=2)

        frame_actions = tk.Frame(card, bg=COLOR_CARD)
        frame_actions.pack(pady=2)

        btn_test = tk.Button(frame_actions, text="🔍 PROBAR CONEXIÓN", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_WARNING, fg="#FFFFFF", bd=0, relief="flat", cursor="hand2", padx=10, pady=5, command=self.probar_conexion)
        btn_test.grid(row=0, column=0, padx=5)

        btn_save = tk.Button(frame_actions, text="💾 GUARDAR CONFIGURACIÓN", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_PRIMARY, fg="#FFFFFF", bd=0, relief="flat", cursor="hand2", padx=10, pady=5, command=self.guardar_configuracion)
        btn_save.grid(row=0, column=1, padx=5)

        btn_volver = tk.Button(self, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_SECONDARY, fg="#FFFFFF", bd=0, relief="flat", padx=12, pady=4, cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        btn_volver.pack(pady=4)

    def set_active(self, var, entry_widget):
        self.active_var = var
        self.active_entry = entry_widget
        self.ent_ip.config(bg=COLOR_BG, bd=1, relief="solid")
        self.ent_port.config(bg=COLOR_BG, bd=1, relief="solid")
        entry_widget.config(bg="#E8F5E9", bd=2, relief="solid")

    def toggle_active_field(self):
        if self.active_var == self.var_ip:
            self.set_active(self.var_port, self.ent_port)
        else:
            self.set_active(self.var_ip, self.ent_ip)

    def add_text(self, text):
        self.active_var.set(self.active_var.get() + text)

    def add_shortcut_ip(self, text):
        self.set_active(self.var_ip, self.ent_ip)
        self.var_ip.set(self.var_ip.get() + text)

    def apply_shortcut_5000(self):
        self.var_port.set("5000")
        self.set_active(self.var_ip, self.ent_ip)

    def borrar_caracter(self):
        curr = self.active_var.get()
        if len(curr) > 0:
            self.active_var.set(curr[:-1])

    def borrar_todo(self):
        self.active_var.set("")

    def on_show(self):
        cfg = cargar_configuracion()
        self.var_ip.set(cfg.get("server_ip", "http://127.0.0.1"))
        self.var_port.set(cfg.get("server_port", "5000"))
        self.set_active(self.var_ip, self.ent_ip)
        self.lbl_status.config(text="")

    def probar_conexion(self):
        ip = self.var_ip.get().strip().rstrip("/")
        port = self.var_port.get().strip()
        
        if not ip:
            self.lbl_status.config(text="⚠️ Ingrese una dirección IP válida.", fg=COLOR_DANGER)
            return

        if not ip.startswith("http://") and not ip.startswith("https://"):
            ip = f"http://{ip}"

        base_url = f"{ip}:{port}" if port else f"{ip}"
        
        self.lbl_status.config(text=f"⏳ Probando puerto en {base_url}...", fg=COLOR_WARNING)
        self.update_idletasks()

        # Probar endpoints más probables (Ping, API Raíz o Marcaciones)
        endpoints_a_probar = [
            f"{base_url}/api/ping",
            f"{base_url}/api",
            f"{base_url}/api/marcaciones",
            f"{base_url}/"
        ]

        exito = False
        mensaje_respuesta = ""

        for target_url in endpoints_a_probar:
            try:
                # Se envía petición de prueba
                res = requests.get(target_url, timeout=3, verify=False)
                # Si responde 200, 400, 405 o 404 significa que EL PUERTO SÍ RESPONDE Y ESCUCHA HTTP
                if res.status_code in [200, 201, 400, 404, 405]:
                    exito = True
                    mensaje_respuesta = f"✅ ¡Conexión con el Servidor Establecida! (HTTP {res.status_code})"
                    break
            except requests.exceptions.ConnectionError:
                # El puerto rechaza la conexión
                continue
            except Exception as e:
                continue

        if exito:
            self.lbl_status.config(text=mensaje_respuesta, fg=COLOR_PRIMARY)
        else:
            self.lbl_status.config(
                text=f"❌ Imposible conectar al puerto HTTP en {base_url}\n"
                     f"Verifique que el firewall de Windows del servidor permita el puerto {port}.", 
                fg=COLOR_DANGER
            )

    def guardar_configuracion(self):
        ip = self.var_ip.get().strip()
        port = self.var_port.get().strip()

        if not ip:
            self.lbl_status.config(text="⚠️ Ingrese una IP válida.", fg=COLOR_DANGER)
            return

        guardar_configuracion(ip, port)
        self.lbl_status.config(text="✓ Configuración de Servidor e IP guardada correctamente.", fg=COLOR_PRIMARY)
        self.after(1200, lambda: self.controller.show_frame("PantallaPrincipal"))


# ----------------------------------------------------------------------
# VISTA: TECLADO NUMÉRICO TÁCTIL
# ----------------------------------------------------------------------
class PantallaTeclado(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        self.lbl_accion = tk.Label(self, text="", font=(FONT_PRIMARY, 12, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG)
        self.lbl_accion.pack(pady=5)

        self.display_var = tk.StringVar()
        self.display = tk.Entry(
            self, textvariable=self.display_var, font=(FONT_PRIMARY, 22, "bold"),
            justify="center", bd=2, relief="solid", state="readonly", 
            fg=COLOR_TEXT_DARK, bg=COLOR_CARD, highlightthickness=1, highlightcolor=COLOR_PRIMARY
        )
        self.display.pack(pady=5, ipadx=10, ipady=6)

        self.lbl_msg = tk.Label(self, text="", font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_BG, wraplength=500)
        self.lbl_msg.pack(pady=2)

        card_keypad = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid")
        card_keypad.pack(pady=5, padx=120)

        keypad = tk.Frame(card_keypad, bg=COLOR_CARD)
        keypad.pack(padx=15, pady=10)

        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('BORRAR', 3, 0), ('0', 3, 1), ('ACEPTAR', 3, 2)
        ]

        for text, row, col in buttons:
            if text == 'BORRAR':
                btn = tk.Button(keypad, text=text, font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_DANGER, fg="#FFFFFF", width=8, height=2, bd=0, relief="flat", cursor="hand2", command=self.press_borrar)
            elif text == 'ACEPTAR':
                btn = tk.Button(keypad, text=text, font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_PRIMARY, fg="#FFFFFF", width=8, height=2, bd=0, relief="flat", cursor="hand2", command=self.press_siguiente)
            else:
                btn = tk.Button(keypad, text=text, font=(FONT_PRIMARY, 14, "bold"), bg=COLOR_BG, fg=COLOR_TEXT_DARK, width=5, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=text: self.press_num(t))
            btn.grid(row=row, column=col, padx=4, pady=4)

        btn_volver = tk.Button(self, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_SECONDARY, fg="#FFFFFF", bd=0, relief="flat", padx=15, pady=8, cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        btn_volver.pack(pady=10)

    def on_show(self):
        self.display_var.set("")
        self.lbl_msg.config(text="")
        self.lbl_accion.config(text=f"OPERACIÓN: {self.controller.current_action} — INGRESE CÓDIGO DE COLABORADOR")

    def press_num(self, num):
        self.lbl_msg.config(text="")
        curr = self.display_var.get()
        if len(curr) < 8:
            self.display_var.set(curr + num)

    def press_borrar(self):
        self.lbl_msg.config(text="")
        self.display_var.set(self.display_var.get()[:-1])

    def press_siguiente(self):
        codigo = self.display_var.get().strip()
        if not codigo:
            return
        
        self.lbl_msg.config(text="⏳ Buscando biometría...", fg=COLOR_WARNING)
        self.update_idletasks()

        ok, depto, vector, msg = obtener_vector_biometrico(codigo)
        if not ok:
            self.lbl_msg.config(text=msg, fg=COLOR_DANGER)
            return

        self.controller.t_inicio_solicitud = time.perf_counter()
        print("\n==================================================")
        print(f"[BENCHMARK] ⏱️ Solicitud iniciada para Colaborador ID: {codigo} ({msg})")

        self.controller.current_emp_code = codigo
        self.controller.current_emp_depto = depto
        self.controller.current_emp_vector = vector
        self.controller.show_frame("PantallaBiometrica")


# ----------------------------------------------------------------------
# VISTA: RECONOCIMIENTO BIOMÉTRICO
# ----------------------------------------------------------------------
class PantallaBiometrica(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.cap = None
        self.is_running = False
        self.vector_registrado = None
        self.verificado = False
        self.first_frame_captured = False

        self.last_face_rect = None
        self.last_color_box = (217, 130, 43)
        self.is_worker_busy = False

        HeaderNutresa(self).pack(fill="x")

        self.lbl_sub = tk.Label(self, text="Mire a la cámara y PARPADEE para verificar", font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_MUTED, bg=COLOR_BG)
        self.lbl_sub.pack(pady=5)

        self.card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid")
        self.card.pack(pady=5, padx=80)

        self.lbl_video = tk.Label(self.card, bg="#000000", width=440, height=300)
        self.lbl_video.pack(pady=10, padx=10)

        self.lbl_status = tk.Label(self.card, text="INICIANDO CÁMARA...", font=(FONT_PRIMARY, 10, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD, wraplength=400)
        self.lbl_status.pack(pady=(0, 10))

        self.btn_cancelar = tk.Button(self, text="CANCELAR", font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_SECONDARY, fg="#FFFFFF", bd=0, relief="flat", padx=15, pady=8, cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        self.btn_cancelar.pack(pady=10)

    def on_show(self):
        self.verificado = False
        self.last_face_rect = None
        self.is_worker_busy = False
        self.first_frame_captured = False

        emp_id = self.controller.current_emp_code
        self.vector_registrado = self.controller.current_emp_vector

        if self.vector_registrado is None:
            self.lbl_sub.config(text=f"COLABORADOR ID: {emp_id}")
            self.lbl_status.config(text=f"❌ ERROR BIOMÉTRICO: No se encontró el rostro del colaborador.", fg=COLOR_DANGER)
            self.btn_cancelar.pack(pady=10)
            return

        t0 = time.perf_counter()
        self.controller.input_queue.put("RESET")
        
        while not self.controller.output_queue.empty():
            try:
                self.controller.output_queue.get_nowait()
            except Exception:
                pass
                
        t_proc = (time.perf_counter() - t0) * 1000
        print(f"[BENCHMARK] ⚡ Envío RESET a Worker: {t_proc:.2f} ms")

        self.lbl_sub.config(text=f"COLABORADOR ID: {emp_id} — PARPADEE ANTE LA CÁMARA")
        self.lbl_status.config(text="👁 ESPERANDO PARPADEO DE VALIDACIÓN...", fg=COLOR_WARNING)
        self.btn_cancelar.pack(pady=10)

        self.detener_camara()

        t0 = time.perf_counter()
        if os.name == 'nt':
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(0)

        t_cam = (time.perf_counter() - t0) * 1000
        print(f"[BENCHMARK] 📷 Inicialización de cámara: {t_cam:.2f} ms")

        self.is_running = True
        self.actualizar_camara()

    def actualizar_camara(self):
        if not self.is_running or self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if ret:
            if not self.first_frame_captured:
                self.first_frame_captured = True
                t_total = time.perf_counter() - getattr(self.controller, 't_inicio_solicitud', time.perf_counter())
                print(f"[BENCHMARK] 🚀 Primer frame capturado. Total: {t_total:.3f} s\n==================================================\n")

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if not self.is_worker_busy and not self.verificado:
                self.is_worker_busy = True
                try:
                    self.controller.input_queue.put_nowait((frame_rgb, self.vector_registrado))
                except Exception:
                    self.is_worker_busy = False

            if not self.controller.output_queue.empty():
                res = self.controller.output_queue.get()
                self.is_worker_busy = False
                
                self.last_face_rect = res["rect"]

                if res["alerta_liveness"]:
                    self.last_color_box = (217, 130, 43)
                    self.lbl_status.config(text=res["alerta_liveness"], fg=COLOR_WARNING)
                elif res["verificado"]:
                    self.last_color_box = (0, 128, 55)
                    self.procesar_exito(res["similitud"])
                elif res["rect"] is not None:
                    self.last_color_box = (217, 56, 58)
                    self.lbl_status.config(
                        text=f"❌ ROSTRO NO COINCIDE ({res['similitud']:.1f}% Similitud)", 
                        fg=COLOR_DANGER
                    )

            if self.last_face_rect is not None:
                x1, y1, x2, y2 = self.last_face_rect
                cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), self.last_color_box, 3)

            img = Image.fromarray(frame_rgb)
            img = img.resize((440, 300), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.lbl_video.imgtk = imgtk
            self.lbl_video.configure(image=imgtk)

        if not self.verificado and self.is_running:
            self.after(10, self.actualizar_camara)

    def procesar_exito(self, similitud):
        self.verificado = True
        emp_id = self.controller.current_emp_code
        accion = self.controller.current_action

        if accion in ["ENTRADA", "SALIDA", "TIEMPO EXTRA"]:
            ok, mensaje_servidor = api_registrar_marcacion(emp_id, accion)
            if ok:
                self.lbl_status.config(
                    text=f"✓ PERSONA VERIFICADA ({similitud:.1f}%)\n{mensaje_servidor}", 
                    fg=COLOR_PRIMARY
                )
            else:
                self.lbl_status.config(text=mensaje_servidor, fg=COLOR_DANGER)
            
            self.btn_cancelar.pack_forget()
            self.after(2000, lambda: self.controller.show_frame("PantallaPrincipal"))

        elif accion == "MARCACIONES":
            self.lbl_status.config(text=f"✓ IDENTIDAD VERIFICADA ({similitud:.1f}%)\nCargando historial...", fg=COLOR_PRIMARY)
            self.btn_cancelar.pack_forget()
            self.after(1200, lambda: self.controller.show_frame("PantallaHistorial"))

    def detener_camara(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None


# ----------------------------------------------------------------------
# VISTA: CONSULTAR HISTORIAL DE MARCACIONES
# ----------------------------------------------------------------------
class PantallaHistorial(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        self.lbl_titulo = tk.Label(self, text="", font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG)
        self.lbl_titulo.pack(pady=5)

        card_table = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid")
        card_table.pack(pady=5, padx=30, fill="both", expand=True)

        columns = ("fecha", "entrada", "salida", "horas", "tarde")
        self.tree = ttk.Treeview(card_table, columns=columns, show="headings", height=10)
        self.tree.heading("fecha", text="FECHA")
        self.tree.heading("entrada", text="HORA ENTRADA")
        self.tree.heading("salida", text="HORA SALIDA")
        self.tree.heading("horas", text="HORAS TRAB.")
        self.tree.heading("tarde", text="MIN. TARDE")

        self.tree.column("fecha", anchor="center", width=120)
        self.tree.column("entrada", anchor="center", width=120)
        self.tree.column("salida", anchor="center", width=120)
        self.tree.column("horas", anchor="center", width=110)
        self.tree.column("tarde", anchor="center", width=110)

        scrollbar = ttk.Scrollbar(card_table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)

        self.tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        scrollbar.pack(side="right", fill="y", pady=10)

        btn_volver = tk.Button(self, text="← VOLVER AL MENÚ PRINCIPAL", font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_SECONDARY, fg="#FFFFFF", bd=0, relief="flat", padx=15, pady=8, cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        btn_volver.pack(pady=10)

    def on_show(self):
        emp_id = self.controller.current_emp_code
        depto = self.controller.current_emp_depto
        self.lbl_titulo.config(text=f"HISTORIAL DE MARCACIONES — COLABORADOR ID: {emp_id} ({depto})")

        for item in self.tree.get_children():
            self.tree.delete(item)

        registros = api_obtener_historial(emp_id)
        for reg in registros:
            self.tree.insert("", "end", values=(reg["fecha"], reg["entrada"], reg["salida"], reg["horas"], reg["tarde"]))


# ----------------------------------------------------------------------
# VISTA: ENROLAR NUEVO COLABORADOR
# ----------------------------------------------------------------------
class PantallaEnrolar(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.cap = None
        self.is_running = False
        self.ultimo_frame = None

        HeaderNutresa(self).pack(fill="x")

        lbl_titulo = tk.Label(self, text="ENROLAMIENTO FACIAL DE NUEVO COLABORADOR", font=(FONT_PRIMARY, 12, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG)
        lbl_titulo.pack(pady=4)

        main_frame = tk.Frame(self, bg=COLOR_BG)
        main_frame.pack(fill="both", expand=True, padx=15, pady=5)

        panel_form = tk.Frame(main_frame, bg=COLOR_CARD, bd=1, relief="solid")
        panel_form.pack(side="left", fill="both", expand=True, padx=(5, 5), pady=5)

        tk.Label(panel_form, text="1. ID / CÉDULA:", font=(FONT_PRIMARY, 10, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w", padx=15, pady=(8, 0))
        
        self.var_id = tk.StringVar()
        self.ent_id = tk.Entry(panel_form, textvariable=self.var_id, font=(FONT_PRIMARY, 16, "bold"), justify="center", bd=1, relief="solid", state="readonly", bg=COLOR_BG)
        self.ent_id.pack(fill="x", padx=15, pady=(4, 6))

        keypad_frame = tk.Frame(panel_form, bg=COLOR_CARD)
        keypad_frame.pack(pady=4)

        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('BORRAR', 3, 0), ('0', 3, 1)
        ]

        for text, row, col in buttons:
            if text == 'BORRAR':
                btn = tk.Button(keypad_frame, text=text, font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_DANGER, fg="#FFFFFF", width=8, height=2, bd=0, relief="flat", cursor="hand2", command=self._borrar_id)
            else:
                btn = tk.Button(keypad_frame, text=text, font=(FONT_PRIMARY, 12, "bold"), bg=COLOR_BG, fg=COLOR_TEXT_DARK, width=5, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=text: self._press_num(t))
            btn.grid(row=row, column=col, padx=3, pady=3)

        tk.Label(panel_form, text="2. DEPARTAMENTO:", font=(FONT_PRIMARY, 10, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w", padx=15, pady=(8, 0))
        self.var_depto = tk.StringVar(value="OPERACIONES")
        deptos = ["OPERACIONES", "LOGÍSTICA", "ADMINISTRACIÓN", "VENTAS", "MANTENIMIENTO"]
        opt_depto = ttk.OptionMenu(panel_form, self.var_depto, deptos[0], *deptos)
        opt_depto.pack(fill="x", padx=15, pady=4)

        self.lbl_status = tk.Label(panel_form, text="", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_CARD, wraplength=220)
        self.lbl_status.pack(pady=5)

        panel_cam = tk.Frame(main_frame, bg=COLOR_CARD, bd=1, relief="solid")
        panel_cam.pack(side="right", fill="both", expand=True, padx=(5, 5), pady=5)

        self.lbl_video = tk.Label(panel_cam, bg="#000000", width=420, height=280)
        self.lbl_video.pack(pady=10, padx=10, expand=True)

        btn_guardar = tk.Button(panel_cam, text="📸 CAPTURAR Y ENROLAR", font=(FONT_PRIMARY, 12, "bold"), bg=COLOR_PRIMARY, fg="#FFFFFF", activebackground=COLOR_PRIMARY_HOVER, bd=0, relief="flat", cursor="hand2", command=self.guardar_enrolamiento)
        btn_guardar.pack(pady=10, ipadx=15, ipady=8, fill="x", padx=20)

        btn_volver = tk.Button(self, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_SECONDARY, fg="#FFFFFF", bd=0, relief="flat", padx=15, pady=6, cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        btn_volver.pack(pady=(0, 10))

    def on_show(self):
        self.var_id.set("")
        self.lbl_status.config(text="")
        self.ultimo_frame = None
        self.detener_camara()
        if os.name == 'nt':
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        else:
            self.cap = cv2.VideoCapture(0)
        self.is_running = True
        self.actualizar_camara()

    def _press_num(self, num):
        curr = self.var_id.get()
        if len(curr) < 8:
            self.var_id.set(curr + num)

    def _borrar_id(self):
        self.var_id.set(self.var_id.get()[:-1])

    def actualizar_camara(self):
        if not self.is_running or self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.ultimo_frame = frame_rgb.copy()

            locations = face_recognition.face_locations(cv2.resize(frame_rgb, (0, 0), fx=0.5, fy=0.5))
            if len(locations) > 0:
                top, right, bottom, left = locations[0]
                cv2.rectangle(frame_rgb, (left*2, top*2), (right*2, bottom*2), (0, 255, 0), 2)

            img = Image.fromarray(frame_rgb)
            img = img.resize((420, 280), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.lbl_video.imgtk = imgtk
            self.lbl_video.configure(image=imgtk)

        if self.is_running:
            self.after(15, self.actualizar_camara)

    def guardar_enrolamiento(self):
        emp_id = self.var_id.get().strip()
        depto = self.var_depto.get().strip()

        if not emp_id:
            self.lbl_status.config(text="⚠️ Ingrese un ID válido.", fg=COLOR_DANGER)
            return

        if self.ultimo_frame is None:
            self.lbl_status.config(text="⚠️ Sin señal de cámara.", fg=COLOR_DANGER)
            return

        self.lbl_status.config(text="⏳ Generando vector y guardando respaldo...", fg=COLOR_WARNING)
        self.update_idletasks()

        encodings = face_recognition.face_encodings(self.ultimo_frame)
        if len(encodings) == 0:
            self.lbl_status.config(text="❌ No se detectó rostro.", fg=COLOR_DANGER)
            return

        encoding_np = encodings[0]

        ok, msg = api_guardar_nuevo_empleado(emp_id, depto, encoding_np)
        if ok:
            self.lbl_status.config(text=f"✓ {msg}", fg=COLOR_PRIMARY)
            self.after(1500, lambda: self.controller.show_frame("PantallaPrincipal"))
        else:
            self.lbl_status.config(text=msg, fg=COLOR_DANGER)

    def detener_camara(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None


# ----------------------------------------------------------------------
# PUNTO DE ENTRADA PRINCIPAL
# ----------------------------------------------------------------------
if __name__ == "__main__":
    mp.freeze_support()
    app = SistemaMarcacionApp()
    app.mainloop()