# ======================================================================
# PANTALLAS Y VISTAS DE LA INTERFAZ DE USUARIO (ALICAPSA)
# ======================================================================
import os
import time
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
import cv2
import face_recognition
from PIL import Image, ImageTk

from config import (
    ADMIN_PIN,
    DEPTOS_DISPONIBLES,
    FONT_PRIMARY,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_CARD,
    COLOR_CARD_BORDER,
    COLOR_TEXT_DARK,
    COLOR_MUTED,
    COLOR_SECONDARY,
    COLOR_SECONDARY_HOVER,
    COLOR_DANGER,
    COLOR_DANGER_HOVER,
    COLOR_WARNING,
    COLOR_WARNING_HOVER,
    resolver_ruta_recurso,
)
from storage import (
    normalizar_uid_nfc,
    obtener_id_por_nfc,
    cargar_configuracion,
    guardar_configuracion,
    registrar_log_incidente,
    leer_logs_incidentes,
    limpiar_logs_incidentes,
)
from api_client import (
    sincronizar_empleados_servidor,
    sincronizar_marcaciones_pendientes,
    obtener_vector_biometrico,
    api_guardar_nuevo_empleado,
    api_registrar_marcacion,
    api_obtener_historial,
    probar_conexion_servidor,
)
from biometria import extraer_vector_facial
from ui_components import HeaderNutresa


# ----------------------------------------------------------------------
# 1. PANTALLA PRINCIPAL
# ----------------------------------------------------------------------
class PantallaPrincipal(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.iconos = {}

        HeaderNutresa(self).pack(fill="x")

        clock_container = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        clock_container.configure(highlightbackground=COLOR_CARD_BORDER)
        clock_container.pack(pady=(6, 8), padx=100, fill="x")

        tk.Frame(clock_container, bg=COLOR_ACCENT, height=3).pack(fill="x", side="top")

        clock_inner = tk.Frame(clock_container, bg=COLOR_CARD, pady=6, padx=15)
        clock_inner.pack(fill="x")

        self.lbl_reloj = tk.Label(
            clock_inner, text="", font=(FONT_PRIMARY, 32, "bold"),
            fg=COLOR_PRIMARY, bg=COLOR_CARD,
        )
        self.lbl_reloj.pack()

        self.lbl_fecha = tk.Label(
            clock_inner, text="", font=(FONT_PRIMARY, 10, "bold"),
            fg=COLOR_MUTED, bg=COLOR_CARD,
        )
        self.lbl_fecha.pack(pady=(0, 2))

        self.actualizar_reloj()

        tk.Label(
            self, text="SELECCIONE LA OPCIÓN QUE DESEA REGISTRAR",
            font=(FONT_PRIMARY, 10, "bold"), fg=COLOR_TEXT_DARK, bg=COLOR_BG,
        ).pack(pady=(2, 6))

        center_card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        center_card.configure(highlightbackground=COLOR_CARD_BORDER)
        center_card.pack(expand=True, padx=70, pady=(2, 10), fill="both")

        grid_frame = tk.Frame(center_card, bg=COLOR_CARD)
        grid_frame.pack(expand=True, fill="both", padx=12, pady=12)

        grid_frame.columnconfigure(0, weight=1)
        grid_frame.columnconfigure(1, minsize=12)
        grid_frame.columnconfigure(2, weight=1)
        grid_frame.rowconfigure(0, weight=1)
        grid_frame.rowconfigure(1, minsize=12)
        grid_frame.rowconfigure(2, weight=1)

        ruta_entrada = resolver_ruta_recurso(
            "entrada.png",
            r"D:\Users\BREAAPONTE\OneDrive - Grupo Nutresa\Escritorio\Main2\Cliente\entrada.png",
        )
        ruta_salida = resolver_ruta_recurso(
            "salida.png",
            r"D:\Users\BREAAPONTE\OneDrive - Grupo Nutresa\Escritorio\Main2\Cliente\salida.png",
        )

        self._crear_boton_estilizado(grid_frame, "", "", COLOR_SECONDARY, 0, 0, "ENTRADA", img_filename=ruta_entrada)
        self._crear_boton_estilizado(grid_frame, "", "", COLOR_SECONDARY, 0, 2, "SALIDA", img_filename=ruta_salida)
        self._crear_boton_estilizado(grid_frame, "📋  MARCACIONES", "CONSULTAR HISTORIAL", COLOR_SECONDARY, 2, 0, "MARCACIONES")
        self._crear_boton_estilizado(grid_frame, "⏱  HORA EXTRA", "SOBRETIEMPO ESPECIAL", COLOR_SECONDARY, 2, 2, "TIEMPO EXTRA")

        admin_btns_frame = tk.Frame(self, bg=COLOR_BG)
        admin_btns_frame.pack(pady=(0, 10))

        self._crear_boton_admin(admin_btns_frame, "⚙️ AGREGAR COLABORADOR", "PantallaEnrolar")
        self._crear_boton_admin(admin_btns_frame, "🌐 IP SERVIDOR", "PantallaConfiguracion")
        self._crear_boton_admin(admin_btns_frame, "📋 LOG / INCIDENTES (ADMIN)", "PantallaLog")

    def _crear_boton_admin(self, parent, texto, destino):
        btn = tk.Button(
            parent, text=texto, font=(FONT_PRIMARY, 8, "bold"),
            bg=COLOR_CARD, fg=COLOR_PRIMARY, activebackground=COLOR_SECONDARY, activeforeground=COLOR_PRIMARY,
            bd=1, relief="solid", cursor="hand2", padx=8, pady=5,
            command=lambda: self.abrir_admin(destino),
        )
        btn.configure(highlightbackground=COLOR_CARD_BORDER)
        btn.pack(side="left", padx=4)

    def actualizar_reloj(self):
        ahora = datetime.now()
        self.lbl_reloj.config(text=ahora.strftime("%I:%M:%S %p"))
        self.lbl_fecha.config(text=ahora.strftime("%d/%m/%Y"))
        self.after(1000, self.actualizar_reloj)

    def _crear_boton_estilizado(self, parent, titulo, subtitulo, bg, row, col, accion, img_filename=None):
        img_obj = None
        if img_filename and os.path.exists(img_filename):
            try:
                pil_img = Image.open(img_filename).resize((120, 80), Image.Resampling.LANCZOS)
                img_obj = ImageTk.PhotoImage(pil_img)
                self.iconos[accion] = img_obj
            except Exception:
                img_obj = None

        texto_boton = f"{titulo}\n{subtitulo}" if (titulo or subtitulo) else accion

        btn_kwargs = {
            "text": texto_boton,
            "font": (FONT_PRIMARY, 12, "bold"),
            "bg": bg,
            "fg": COLOR_PRIMARY,
            "activebackground": COLOR_PRIMARY,
            "activeforeground": "#FFFFFF",
            "bd": 1,
            "relief": "solid",
            "highlightthickness": 0,
            "cursor": "hand2",
            "justify": "center",
            "command": lambda: self.seleccionar_accion(accion),
        }

        if img_obj:
            btn_kwargs["image"] = img_obj
            btn_kwargs["compound"] = "top"
            if not titulo and not subtitulo:
                btn_kwargs["text"] = ""

        btn = tk.Button(parent, **btn_kwargs)
        btn.configure(highlightbackground=COLOR_CARD_BORDER)
        btn.bind("<Enter>", lambda e: btn.config(bg=COLOR_PRIMARY, fg="#FFFFFF"))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg, fg=COLOR_PRIMARY))
        btn.grid(row=row, column=col, sticky="nsew", ipadx=4, ipady=4)

    def abrir_admin(self, destino):
        self.controller.admin_target = destino
        self.controller.admin_return_frame = "PantallaPrincipal"
        self.controller.show_frame("PantallaAdminPin")

    def seleccionar_accion(self, accion):
        self.controller.current_action = accion
        self.controller.current_emp_code = ""
        self.controller.current_emp_nfc = ""
        self.controller.current_emp_vector = None
        self.controller.admin_override_nfc = False

        if accion in ("ENTRADA", "SALIDA", "MARCACIONES"):
            self.controller.show_frame("PantallaNFC")
        else:
            self.controller.show_frame("PantallaTeclado")


# ----------------------------------------------------------------------
# 2. LECTURA DE TARJETA NFC (CON OPCIÓN PERMISO ADMINISTRADOR)
# ----------------------------------------------------------------------
class PantallaNFC(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.procesando = False
        self._scan_gen = 0
        self._clear_msg_timer = None

        HeaderNutresa(self).pack(fill="x")

        self.lbl_accion = tk.Label(
            self, text="", font=(FONT_PRIMARY, 13, "bold"),
            fg=COLOR_PRIMARY, bg=COLOR_BG,
        )
        self.lbl_accion.pack(pady=(8, 6))

        card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        card.configure(highlightbackground=COLOR_CARD_BORDER)
        card.pack(pady=6, padx=90, fill="both", expand=True)

        tk.Frame(card, bg=COLOR_ACCENT, height=4).pack(fill="x", side="top")

        self.canvas_nfc = tk.Canvas(card, width=160, height=110, bg=COLOR_CARD, highlightthickness=0)
        self.canvas_nfc.pack(pady=(22, 8))
        self._dibujar_icono_nfc()

        self.lbl_instruccion = tk.Label(
            card, text="ACERQUE SU TARJETA NFC AL LECTOR",
            font=(FONT_PRIMARY, 16, "bold"), fg=COLOR_PRIMARY, bg=COLOR_CARD,
        )
        self.lbl_instruccion.pack(pady=(4, 4))

        self.lbl_sub = tk.Label(
            card, text="Coloque su tarjeta sobre el lector Cryptnox para validar su identidad",
            font=(FONT_PRIMARY, 10), fg=COLOR_MUTED, bg=COLOR_CARD,
        )
        self.lbl_sub.pack(pady=(0, 14))

        self.lbl_uid_detectado = tk.Label(
            card, text="", font=(FONT_PRIMARY, 12, "bold"),
            fg=COLOR_TEXT_DARK, bg=COLOR_CARD,
        )
        self.lbl_uid_detectado.pack(pady=(0, 6))

        self.lbl_msg = tk.Label(
            card, text="", font=(FONT_PRIMARY, 10, "bold"),
            bg=COLOR_CARD, wraplength=520,
        )
        self.lbl_msg.pack(pady=(0, 8))

        self.lbl_estado_lector = tk.Label(
            card, text="⏳ Inicializando lector NFC...",
            font=(FONT_PRIMARY, 9, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD,
        )
        self.lbl_estado_lector.pack(side="bottom", pady=12)

        btn_bar = tk.Frame(self, bg=COLOR_BG)
        btn_bar.pack(pady=10)

        btn_reintentar = tk.Button(
            btn_bar, text="📡 LEER DE NUEVO", font=(FONT_PRIMARY, 9, "bold"),
            bg=COLOR_SECONDARY, fg=COLOR_PRIMARY, activebackground=COLOR_SECONDARY_HOVER,
            bd=1, relief="solid", padx=12, pady=6, cursor="hand2",
            command=self._reintentar_lectura_manual,
        )
        btn_reintentar.configure(highlightbackground=COLOR_CARD_BORDER)
        btn_reintentar.pack(side="left", padx=5)

        btn_permiso_admin = tk.Button(
            btn_bar, text="🔑 PERMISO ADMINISTRADOR", font=(FONT_PRIMARY, 9, "bold"),
            bg=COLOR_WARNING, fg="#FFFFFF", activebackground=COLOR_WARNING_HOVER, activeforeground="#FFFFFF",
            bd=0, relief="flat", padx=14, pady=7, cursor="hand2",
            command=self._solicitar_permiso_admin,
        )
        btn_permiso_admin.pack(side="left", padx=5)

        btn_volver = tk.Button(
            btn_bar, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 9, "bold"),
            bg=COLOR_MUTED, fg="#FFFFFF", activebackground=COLOR_TEXT_DARK, activeforeground="#FFFFFF",
            bd=0, relief="flat", padx=14, pady=7, cursor="hand2",
            command=lambda: controller.show_frame("PantallaPrincipal"),
        )
        btn_volver.pack(side="left", padx=5)

    def _solicitar_permiso_admin(self):
        """Permite al coordinador autorizar el ingreso por número de empleado sin tarjeta NFC."""
        self.controller.admin_target = "PantallaTeclado"
        self.controller.admin_return_frame = "PantallaNFC"
        self.controller.show_frame("PantallaAdminPin")

    def _dibujar_icono_nfc(self):
        c = self.canvas_nfc
        c.delete("all")
        c.create_rectangle(25, 22, 115, 88, fill="#EAF5EC", outline=COLOR_PRIMARY, width=2)
        c.create_rectangle(35, 36, 55, 50, fill=COLOR_ACCENT, outline=COLOR_PRIMARY, width=1)
        for i, r in enumerate([14, 24, 34]):
            c.create_arc(
                105 - r, 55 - r, 105 + r, 55 + r,
                start=-45, extent=90, style="arc",
                outline=COLOR_ACCENT if i % 2 == 0 else COLOR_PRIMARY, width=3,
            )

    def _reintentar_lectura_manual(self):
        self._cancelar_timer_mensaje()
        self.procesando = False
        self.lbl_uid_detectado.config(text="")
        self.lbl_msg.config(text="⏳ Leyendo tarjeta sobre el lector...", fg=COLOR_WARNING)
        self.controller.gestor_nfc.solicitar_relectura_actual()

    def _cancelar_timer_mensaje(self):
        if self._clear_msg_timer is not None:
            try:
                self.after_cancel(self._clear_msg_timer)
            except Exception:
                pass
            self._clear_msg_timer = None

    def _programar_limpieza_mensaje(self, ms=3500):
        self._cancelar_timer_mensaje()
        gen = self._scan_gen
        self._clear_msg_timer = self.after(ms, lambda: self._limpiar_aviso_si_vigente(gen))

    def _limpiar_aviso_si_vigente(self, gen):
        if gen != self._scan_gen or self.procesando:
            return
        self.lbl_uid_detectado.config(text="")
        self.lbl_msg.config(text="")

    def on_show(self):
        self._scan_gen += 1
        self._cancelar_timer_mensaje()
        self.procesando = False
        self.controller.admin_override_nfc = False

        accion = self.controller.current_action
        titulo_accion = "CONSULTA DE MARCACIONES" if accion == "MARCACIONES" else f"REGISTRO DE {accion}"
        self.lbl_accion.config(text=titulo_accion)

        self.lbl_instruccion.config(text="ACERQUE SU TARJETA NFC AL LECTOR", fg=COLOR_PRIMARY)
        self.lbl_uid_detectado.config(text="")
        self.lbl_msg.config(text="")
        self.lbl_estado_lector.config(text="⏳ Buscando lector NFC Cryptnox...", fg=COLOR_MUTED)

        self.controller.gestor_nfc.iniciar_escucha(
            callback_uid=self._on_tarjeta_detectada,
            callback_estado=self._on_estado_lector,
            callback_error=self._on_error_lectura,
            callback_retirada=self._on_tarjeta_retirada,
        )

    def on_hide(self):
        self._scan_gen += 1
        self._cancelar_timer_mensaje()
        self.procesando = False

    def _on_estado_lector(self, conectado, mensaje):
        color = COLOR_PRIMARY if conectado else COLOR_DANGER
        self.lbl_estado_lector.config(text=mensaje, fg=color)

    def _on_error_lectura(self, detalle):
        if self.procesando:
            return
        self.controller.reset_inactivity_timer()
        self.bell()
        self.lbl_uid_detectado.config(text="⚠️ LECTURA NO EXITOSA", fg=COLOR_DANGER)
        self.lbl_msg.config(
            text=f"No se pudo leer la tarjeta ({detalle}).\nRetire la tarjeta e intente nuevamente.",
            fg=COLOR_DANGER,
        )
        self._programar_limpieza_mensaje(3500)

    def _on_tarjeta_retirada(self):
        if not self.procesando and self.lbl_msg.cget("text"):
            self._cancelar_timer_mensaje()
            self.lbl_uid_detectado.config(text="")
            self.lbl_msg.config(text="Listo para leer nuevamente. Acerque su tarjeta.", fg=COLOR_MUTED)
            self._programar_limpieza_mensaje(2000)

    def _on_tarjeta_detectada(self, uid_hex):
        if self.procesando:
            return

        uid_limpio = normalizar_uid_nfc(uid_hex)
        if not uid_limpio:
            return

        self._cancelar_timer_mensaje()
        self.procesando = True
        self._scan_gen += 1
        gen_actual = self._scan_gen

        self.controller.reset_inactivity_timer()
        self.bell()

        self.lbl_uid_detectado.config(text=f"TARJETA DETECTADA: {uid_limpio}", fg=COLOR_TEXT_DARK)
        self.lbl_msg.config(text="⏳ Buscando colaborador y datos biométricos...", fg=COLOR_WARNING)

        threading.Thread(
            target=self._buscar_biometria_async,
            args=(uid_limpio, gen_actual),
            daemon=True,
        ).start()

    def _buscar_biometria_async(self, uid_hex, gen):
        t_inicio = time.perf_counter()
        try:
            ok, real_emp_id, depto, vector, msg = obtener_vector_biometrico(uid_hex)
        except Exception as e:
            ok, real_emp_id, depto, vector, msg = False, uid_hex, "", None, f"❌ Error verificando tarjeta: {e}"
        self.after(
            0,
            lambda: self._finalizar_busqueda_biometria(
                uid_hex, gen, t_inicio, ok, real_emp_id, depto, vector, msg
            ),
        )

    def _finalizar_busqueda_biometria(self, uid_hex, gen, t_inicio, ok, real_emp_id, depto, vector, msg):
        if gen != self._scan_gen or self.controller.get_current_frame_name() != "PantallaNFC":
            self.procesando = False
            return

        if not ok or vector is None:
            self.procesando = False
            self.bell()
            self.lbl_uid_detectado.config(text=f"❌ LECTURA NO VÁLIDA ({uid_hex})", fg=COLOR_DANGER)
            self.lbl_msg.config(
                text=f"{msg}\nRetire la tarjeta e intente nuevamente.",
                fg=COLOR_DANGER,
            )
            self._programar_limpieza_mensaje(4000)
            return

        self.procesando = False
        self.controller.t_inicio_solicitud = t_inicio
        print("\n==================================================")
        print(f"[BENCHMARK] ⏱️ Tarjeta NFC {uid_hex} -> Colaborador ID: {real_emp_id} ({msg})")

        self.controller.current_emp_code = real_emp_id
        self.controller.current_emp_nfc = uid_hex
        self.controller.current_emp_depto = depto
        self.controller.current_emp_vector = vector
        self.controller.show_frame("PantallaBiometrica")


# ----------------------------------------------------------------------
# 3. ACCESO ADMINISTRATIVO (PIN DE COORDINADOR / ADMINISTRADOR)
# ----------------------------------------------------------------------
class PantallaAdminPin(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        card.configure(highlightbackground=COLOR_CARD_BORDER)
        card.pack(pady=10, padx=140, fill="both", expand=True)

        self.lbl_title = tk.Label(
            card, text="ACCESO ADMINISTRATIVO",
            font=(FONT_PRIMARY, 12, "bold"), fg=COLOR_PRIMARY, bg=COLOR_CARD,
        )
        self.lbl_title.pack(pady=(12, 2))

        self.lbl_sub = tk.Label(
            card, text="Ingrese la clave de administrador",
            font=(FONT_PRIMARY, 9), fg=COLOR_MUTED, bg=COLOR_CARD,
        )
        self.lbl_sub.pack(pady=(0, 4))

        self.display_var = tk.StringVar()
        self.display = tk.Entry(
            card, textvariable=self.display_var, show="*", font=(FONT_PRIMARY, 18, "bold"),
            justify="center", bd=1, relief="solid", state="readonly",
            fg=COLOR_PRIMARY, bg=COLOR_BG, highlightthickness=0,
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
            ('BORRAR', 3, 0), ('0', 3, 1), ('ENTRAR', 3, 2),
        ]

        for text, row, col in buttons:
            if text == 'BORRAR':
                btn = tk.Button(
                    keypad, text=text, font=(FONT_PRIMARY, 9, "bold"),
                    bg=COLOR_DANGER, fg="#FFFFFF", activebackground=COLOR_DANGER_HOVER, activeforeground="#FFFFFF",
                    width=7, height=2, bd=0, relief="flat", cursor="hand2", command=self.press_borrar,
                )
            elif text == 'ENTRAR':
                btn = tk.Button(
                    keypad, text=text, font=(FONT_PRIMARY, 9, "bold"),
                    bg=COLOR_PRIMARY, fg="#FFFFFF", activebackground=COLOR_PRIMARY_HOVER, activeforeground="#FFFFFF",
                    width=7, height=2, bd=0, relief="flat", cursor="hand2", command=self.verificar_pin,
                )
            else:
                btn = tk.Button(
                    keypad, text=text, font=(FONT_PRIMARY, 12, "bold"),
                    bg=COLOR_SECONDARY, fg=COLOR_TEXT_DARK, activebackground=COLOR_SECONDARY_HOVER,
                    width=5, height=2, bd=1, relief="solid", cursor="hand2",
                    command=lambda t=text: self.press_num(t),
                )
                btn.configure(highlightbackground=COLOR_CARD_BORDER)
            btn.grid(row=row, column=col, padx=3, pady=3)

        btn_cancel = tk.Button(
            card, text="CANCELAR", font=(FONT_PRIMARY, 9, "bold"),
            bg=COLOR_MUTED, fg="#FFFFFF", activebackground=COLOR_TEXT_DARK, activeforeground="#FFFFFF",
            bd=0, relief="flat", cursor="hand2", command=self.cancelar_pin,
        )
        btn_cancel.pack(pady=10, ipadx=15, ipady=4)

    def on_show(self):
        self.display_var.set("")
        self.lbl_status.config(text="")
        target = getattr(self.controller, "admin_target", "PantallaEnrolar")
        if target == "PantallaTeclado":
            self.lbl_title.config(text="PERMISO ADMINISTRADOR")
            self.lbl_sub.config(text="Autorización para ingresar sin tarjeta NFC")
        else:
            self.lbl_title.config(text="ACCESO ADMINISTRATIVO")
            self.lbl_sub.config(text="Ingrese la clave de administrador")

    def cancelar_pin(self):
        retorno = getattr(self.controller, "admin_return_frame", "PantallaPrincipal")
        self.controller.show_frame(retorno)

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
            target = getattr(self.controller, "admin_target", "PantallaEnrolar")
            if target == "PantallaTeclado":
                self.controller.admin_override_nfc = True
                registrar_log_incidente(
                    "COORDINADOR",
                    self.controller.current_action,
                    "Permiso Administrador",
                    "Autorización de ingreso manual sin tarjeta NFC",
                )
            self.controller.show_frame(target)
        else:
            self.lbl_status.config(text="❌ PIN Incorrecto", fg=COLOR_DANGER)
            self.display_var.set("")


# ----------------------------------------------------------------------
# 4. TECLADO NUMÉRICO TÁCTIL (INGRESO DE CÓDIGO DE EMPLEADO)
# ----------------------------------------------------------------------
class PantallaTeclado(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.procesando = False
        self._scan_gen = 0

        HeaderNutresa(self).pack(fill="x")

        self.lbl_banner_admin = tk.Label(
            self, text="", font=(FONT_PRIMARY, 9, "bold"),
            fg="#FFFFFF", bg=COLOR_WARNING, padx=12, pady=3,
        )

        self.lbl_accion = tk.Label(
            self, text="", font=(FONT_PRIMARY, 11, "bold"),
            fg=COLOR_PRIMARY, bg=COLOR_BG,
        )
        self.lbl_accion.pack(pady=6)

        self.display_var = tk.StringVar()
        self.display = tk.Entry(
            self, textvariable=self.display_var, font=(FONT_PRIMARY, 22, "bold"),
            justify="center", bd=1, relief="solid", state="readonly",
            fg=COLOR_PRIMARY, bg=COLOR_CARD, highlightthickness=0,
        )
        self.display.pack(pady=4, ipadx=10, ipady=6)

        self.lbl_msg = tk.Label(self, text="", font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_BG, wraplength=500)
        self.lbl_msg.pack(pady=2)

        card_keypad = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        card_keypad.configure(highlightbackground=COLOR_CARD_BORDER)
        card_keypad.pack(pady=5, padx=120)

        keypad = tk.Frame(card_keypad, bg=COLOR_CARD)
        keypad.pack(padx=15, pady=10)

        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('BORRAR', 3, 0), ('0', 3, 1), ('ACEPTAR', 3, 2),
        ]

        for text, row, col in buttons:
            if text == 'BORRAR':
                btn = tk.Button(
                    keypad, text=text, font=(FONT_PRIMARY, 10, "bold"),
                    bg=COLOR_DANGER, fg="#FFFFFF", activebackground=COLOR_DANGER_HOVER, activeforeground="#FFFFFF",
                    width=8, height=2, bd=0, relief="flat", cursor="hand2", command=self.press_borrar,
                )
            elif text == 'ACEPTAR':
                btn = tk.Button(
                    keypad, text=text, font=(FONT_PRIMARY, 10, "bold"),
                    bg=COLOR_PRIMARY, fg="#FFFFFF", activebackground=COLOR_PRIMARY_HOVER, activeforeground="#FFFFFF",
                    width=8, height=2, bd=0, relief="flat", cursor="hand2", command=self.press_siguiente,
                )
            else:
                btn = tk.Button(
                    keypad, text=text, font=(FONT_PRIMARY, 14, "bold"),
                    bg=COLOR_SECONDARY, fg=COLOR_TEXT_DARK, activebackground=COLOR_SECONDARY_HOVER,
                    width=5, height=2, bd=1, relief="solid", cursor="hand2",
                    command=lambda t=text: self.press_num(t),
                )
                btn.configure(highlightbackground=COLOR_CARD_BORDER)
            btn.grid(row=row, column=col, padx=4, pady=4)

        btn_volver = tk.Button(
            self, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 10, "bold"),
            bg=COLOR_MUTED, fg="#FFFFFF", activebackground=COLOR_TEXT_DARK, activeforeground="#FFFFFF",
            bd=0, relief="flat", padx=15, pady=6, cursor="hand2",
            command=lambda: controller.show_frame("PantallaPrincipal"),
        )
        btn_volver.pack(pady=8)

    def on_show(self):
        self._scan_gen += 1
        self.procesando = False
        self.display_var.set("")
        self.lbl_msg.config(text="")

        es_override = getattr(self.controller, "admin_override_nfc", False)
        if es_override:
            self.lbl_banner_admin.config(text="🔑 PERMISO ADMINISTRADOR AUTORIZADO — SIN TARJETA NFC")
            self.lbl_banner_admin.pack(before=self.lbl_accion, pady=(4, 0))
            self.lbl_accion.config(
                text=f"OPERACIÓN: {self.controller.current_action}\nINGRESE EL NÚMERO DE EMPLEADO PARA VALIDAR SU ROSTRO"
            )
        else:
            self.lbl_banner_admin.pack_forget()
            self.lbl_accion.config(
                text=f"OPERACIÓN: {self.controller.current_action}\nINGRESE CÓDIGO DE COLABORADOR O ACERQUE TARJETA NFC"
            )
            self.controller.gestor_nfc.iniciar_escucha(
                callback_uid=self._on_nfc_leido,
                callback_error=self._on_nfc_error,
            )

    def on_hide(self):
        self._scan_gen += 1
        self.procesando = False

    def _on_nfc_leido(self, uid_hex):
        if self.procesando:
            return
        self.bell()
        self.display_var.set(uid_hex)
        self.controller.current_emp_nfc = uid_hex
        self.press_siguiente()

    def _on_nfc_error(self, detalle):
        if self.procesando:
            return
        self.bell()
        self.lbl_msg.config(text=f"⚠️ Lectura NFC fallida ({detalle}). Intente de nuevo.", fg=COLOR_DANGER)

    def press_num(self, num):
        if self.procesando:
            return
        self.lbl_msg.config(text="")
        curr = self.display_var.get()
        if len(curr) < 16:
            self.display_var.set(curr + num)

    def press_borrar(self):
        if self.procesando:
            return
        self.lbl_msg.config(text="")
        self.display_var.set(self.display_var.get()[:-1])

    def press_siguiente(self):
        if self.procesando:
            return
        codigo_o_nfc = self.display_var.get().strip()
        if not codigo_o_nfc:
            return

        self.procesando = True
        self._scan_gen += 1
        gen_actual = self._scan_gen
        self.lbl_msg.config(text="⏳ Verificando biometría...", fg=COLOR_WARNING)

        threading.Thread(
            target=self._buscar_biometria_async,
            args=(codigo_o_nfc, gen_actual),
            daemon=True,
        ).start()

    def _buscar_biometria_async(self, codigo_o_nfc, gen):
        t_inicio = time.perf_counter()
        try:
            ok, real_emp_id, depto, vector, msg = obtener_vector_biometrico(codigo_o_nfc)
        except Exception as e:
            ok, real_emp_id, depto, vector, msg = False, codigo_o_nfc, "", None, f"❌ Error verificando: {e}"
        self.after(0, lambda: self._finalizar_busqueda(gen, t_inicio, ok, real_emp_id, depto, vector, msg))

    def _finalizar_busqueda(self, gen, t_inicio, ok, real_emp_id, depto, vector, msg):
        if gen != self._scan_gen or self.controller.get_current_frame_name() != "PantallaTeclado":
            self.procesando = False
            return

        self.procesando = False
        if not ok or vector is None:
            self.lbl_msg.config(text=msg, fg=COLOR_DANGER)
            return

        self.controller.t_inicio_solicitud = t_inicio
        print("\n==================================================")
        print(f"[BENCHMARK] ⏱️ Solicitud iniciada para Colaborador ID: {real_emp_id} ({msg})")

        self.controller.current_emp_code = real_emp_id
        self.controller.current_emp_depto = depto
        self.controller.current_emp_vector = vector
        self.controller.show_frame("PantallaBiometrica")


# ----------------------------------------------------------------------
# 5. RECONOCIMIENTO BIOMÉTRICO (CÁMARA + LIVENESS)
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
        self.last_color_box = (0, 140, 251)
        self.is_worker_busy = False

        HeaderNutresa(self).pack(fill="x")

        self.lbl_sub = tk.Label(
            self, text="Mire a la cámara y PARPADEE para verificar",
            font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_MUTED, bg=COLOR_BG,
        )
        self.lbl_sub.pack(pady=5)

        self.card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        self.card.configure(highlightbackground=COLOR_CARD_BORDER)
        self.card.pack(pady=5, padx=80)

        self._blank_img = ImageTk.PhotoImage(Image.new("RGB", (440, 300), (11, 26, 16)))
        self.lbl_video = tk.Label(self.card, image=self._blank_img, bg="#0B1A10", width=440, height=300)
        self.lbl_video.pack(pady=10, padx=10)

        self.lbl_status = tk.Label(
            self.card, text="INICIANDO CÁMARA...", font=(FONT_PRIMARY, 10, "bold"),
            fg=COLOR_MUTED, bg=COLOR_CARD, wraplength=400,
        )
        self.lbl_status.pack(pady=(0, 10))

        self.btn_cancelar = tk.Button(
            self, text="CANCELAR", font=(FONT_PRIMARY, 10, "bold"),
            bg=COLOR_MUTED, fg="#FFFFFF", bd=0, relief="flat",
            padx=15, pady=8, cursor="hand2", command=self.cancelar_verificacion,
        )
        self.btn_cancelar.pack(pady=10)

    def cancelar_verificacion(self):
        emp_id = self.controller.current_emp_code
        accion = self.controller.current_action
        if not self.verificado and emp_id:
            registrar_log_incidente(emp_id, accion, "Cancelación Manual", "El usuario presionó el botón CANCELAR")
        self.controller.admin_override_nfc = False
        self.controller.show_frame("PantallaPrincipal")

    def on_show(self):
        self.verificado = False
        self.last_face_rect = None
        self.is_worker_busy = False
        self.first_frame_captured = False

        emp_id = self.controller.current_emp_code
        self.vector_registrado = self.controller.current_emp_vector

        if self.vector_registrado is None:
            self.lbl_sub.config(text=f"COLABORADOR ID: {emp_id}")
            self.lbl_status.config(
                text="❌ ERROR BIOMÉTRICO: No se encontró el rostro del colaborador.",
                fg=COLOR_DANGER,
            )
            registrar_log_incidente(
                emp_id,
                self.controller.current_action,
                "Vector Inexistente",
                "No hay vector facial disponible para comparar",
            )
            self.btn_cancelar.pack(pady=10)
            return

        t0 = time.perf_counter()
        self.controller.input_queue.put("RESET")

        while not self.controller.output_queue.empty():
            try:
                self.controller.output_queue.get_nowait()
            except Exception:
                pass

        print(f"[BENCHMARK] ⚡ Envío RESET a Worker: {(time.perf_counter() - t0) * 1000:.2f} ms")

        self.lbl_sub.config(text=f"COLABORADOR ID: {emp_id} — PARPADEE ANTE LA CÁMARA")
        self.lbl_status.config(text="👁 ESPERANDO PARPADEO DE VALIDACIÓN...", fg=COLOR_WARNING)
        self.btn_cancelar.pack(pady=10)

        self.detener_camara()

        t0 = time.perf_counter()
        if os.name == "nt":
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap.release()
                self.cap = cv2.VideoCapture(0)
        else:
            self.cap = cv2.VideoCapture(0)

        print(f"[BENCHMARK] 📷 Inicialización de cámara: {(time.perf_counter() - t0) * 1000:.2f} ms")

        if not self.cap.isOpened():
            self.lbl_status.config(text="❌ No se pudo abrir la cámara web.", fg=COLOR_DANGER)
            return

        self.is_running = True
        self.actualizar_camara()

    def actualizar_camara(self):
        if not self.is_running or self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if ret:
            if not self.first_frame_captured:
                self.first_frame_captured = True
                t_total = time.perf_counter() - getattr(self.controller, "t_inicio_solicitud", time.perf_counter())
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
                    self.last_color_box = (0, 140, 251)
                    self.lbl_status.config(text=res["alerta_liveness"], fg=COLOR_WARNING)
                elif res["verificado"]:
                    self.last_color_box = (49, 167, 72)
                    self.procesar_exito(res["similitud"])
                elif res["rect"] is not None:
                    self.last_color_box = (58, 56, 217)
                    self.lbl_status.config(
                        text=f"❌ ROSTRO NO COINCIDE ({res['similitud']:.1f}% Similitud)",
                        fg=COLOR_DANGER,
                    )

            if self.last_face_rect is not None:
                x1, y1, x2, y2 = self.last_face_rect
                cv2.rectangle(frame_rgb, (x1, y1), (x2, y2), self.last_color_box, 3)

            img = Image.fromarray(frame_rgb).resize((440, 300), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.lbl_video.imgtk = imgtk
            self.lbl_video.configure(image=imgtk)

        if not self.verificado and self.is_running:
            self.after(10, self.actualizar_camara)

    def procesar_exito(self, similitud):
        self.verificado = True
        emp_id = self.controller.current_emp_code
        nfc_uid = self.controller.current_emp_nfc
        accion = self.controller.current_action
        es_override = getattr(self.controller, "admin_override_nfc", False)
        self.controller.admin_override_nfc = False

        if accion in ["ENTRADA", "SALIDA", "TIEMPO EXTRA"]:
            ok, mensaje_servidor = api_registrar_marcacion(
                emp_id, accion, nfc_uid=nfc_uid, permiso_admin=es_override
            )
            if ok:
                self.lbl_status.config(
                    text=f"✓ PERSONA VERIFICADA ({similitud:.1f}%)\n{mensaje_servidor}",
                    fg=COLOR_PRIMARY,
                )
            else:
                self.lbl_status.config(text=mensaje_servidor, fg=COLOR_DANGER)

            self.btn_cancelar.pack_forget()
            self.after(2000, lambda: self.controller.show_frame("PantallaPrincipal"))

        elif accion == "MARCACIONES":
            self.lbl_status.config(
                text=f"✓ IDENTIDAD VERIFICADA ({similitud:.1f}%)\nCargando historial...",
                fg=COLOR_PRIMARY,
            )
            self.btn_cancelar.pack_forget()
            self.after(1200, lambda: self.controller.show_frame("PantallaHistorial"))

    def detener_camara(self):
        self.is_running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None


# ----------------------------------------------------------------------
# 6. HISTORIAL DE MARCACIONES
# ----------------------------------------------------------------------
class PantallaHistorial(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        self.lbl_titulo = tk.Label(self, text="", font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG)
        self.lbl_titulo.pack(pady=5)

        card_table = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        card_table.configure(highlightbackground=COLOR_CARD_BORDER)
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

        btn_volver = tk.Button(
            self, text="← VOLVER AL MENÚ PRINCIPAL", font=(FONT_PRIMARY, 10, "bold"),
            bg=COLOR_PRIMARY, fg="#FFFFFF", activebackground=COLOR_PRIMARY_HOVER, activeforeground="#FFFFFF",
            bd=0, relief="flat", padx=15, pady=8, cursor="hand2",
            command=lambda: controller.show_frame("PantallaPrincipal"),
        )
        btn_volver.pack(pady=10)

    def on_show(self):
        emp_id = self.controller.current_emp_code
        depto = self.controller.current_emp_depto
        self.lbl_titulo.config(text=f"HISTORIAL DE MARCACIONES — COLABORADOR ID: {emp_id} ({depto})")

        for item in self.tree.get_children():
            self.tree.delete(item)

        for reg in api_obtener_historial(emp_id):
            self.tree.insert("", "end", values=(reg["fecha"], reg["entrada"], reg["salida"], reg["horas"], reg["tarde"]))


# ----------------------------------------------------------------------
# 7. ENROLAMIENTO FACIAL Y TARJETA NFC DE NUEVO COLABORADOR
# ----------------------------------------------------------------------
class PantallaEnrolar(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller
        self.cap = None
        self.is_running = False
        self.ultimo_frame = None
        self._frame_count = 0

        HeaderNutresa(self).pack(fill="x")

        tk.Label(
            self, text="ENROLAMIENTO FACIAL Y TARJETA NFC DE COLABORADOR",
            font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG,
        ).pack(pady=2)

        main_frame = tk.Frame(self, bg=COLOR_BG)
        main_frame.pack(fill="both", expand=True, padx=12, pady=4)

        panel_form = tk.Frame(main_frame, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        panel_form.configure(highlightbackground=COLOR_CARD_BORDER)
        panel_form.pack(side="left", fill="both", expand=True, padx=(4, 4), pady=4)

        tk.Label(panel_form, text="1. CÓDIGO / CÉDULA:", font=(FONT_PRIMARY, 8, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w", padx=12, pady=(4, 0))
        self.var_id = tk.StringVar()
        self.ent_id = tk.Entry(panel_form, textvariable=self.var_id, font=(FONT_PRIMARY, 12, "bold"), justify="center", bd=1, relief="solid", state="readonly", bg=COLOR_BG, fg=COLOR_PRIMARY)
        self.ent_id.pack(fill="x", padx=12, pady=(2, 4))

        tk.Label(panel_form, text="2. TARJETA NFC (ACERQUE AL LECTOR CRYPTNOX):", font=(FONT_PRIMARY, 8, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w", padx=12, pady=(2, 0))

        nfc_row = tk.Frame(panel_form, bg=COLOR_CARD)
        nfc_row.pack(fill="x", padx=12, pady=(2, 2))

        self.var_nfc = tk.StringVar()
        self.ent_nfc = tk.Entry(nfc_row, textvariable=self.var_nfc, font=(FONT_PRIMARY, 11, "bold"), justify="center", bd=1, relief="solid", state="readonly", bg=COLOR_BG, fg=COLOR_PRIMARY)
        self.ent_nfc.pack(side="left", fill="x", expand=True, ipady=2)

        btn_leer_nfc = tk.Button(
            nfc_row, text="📡 LEER", font=(FONT_PRIMARY, 8, "bold"),
            bg=COLOR_PRIMARY, fg="#FFFFFF", bd=0, relief="flat",
            cursor="hand2", padx=6, pady=2, command=self._reintentar_nfc,
        )
        btn_leer_nfc.pack(side="right", padx=(3, 0))

        btn_limpiar_nfc = tk.Button(
            nfc_row, text="🔄 LIMPIAR", font=(FONT_PRIMARY, 8, "bold"),
            bg=COLOR_SECONDARY, fg=COLOR_PRIMARY, bd=1, relief="solid",
            cursor="hand2", padx=6, command=self._limpiar_nfc,
        )
        btn_limpiar_nfc.configure(highlightbackground=COLOR_CARD_BORDER)
        btn_limpiar_nfc.pack(side="right", padx=(4, 0))

        self.lbl_nfc_lector = tk.Label(
            panel_form, text="📡 Esperando tarjeta en lector NFC...",
            font=(FONT_PRIMARY, 8, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD,
        )
        self.lbl_nfc_lector.pack(anchor="w", padx=12, pady=(0, 4))

        keypad_frame = tk.Frame(panel_form, bg=COLOR_CARD)
        keypad_frame.pack(pady=2)

        buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2),
            ('BORRAR', 3, 0), ('0', 3, 1), ('LIMPIAR', 3, 2),
        ]

        for text, row, col in buttons:
            if text == 'BORRAR':
                btn = tk.Button(keypad_frame, text=text, font=(FONT_PRIMARY, 8, "bold"), bg=COLOR_DANGER, fg="#FFFFFF", width=8, height=2, bd=0, relief="flat", cursor="hand2", command=self._borrar_caracter)
            elif text == 'LIMPIAR':
                btn = tk.Button(keypad_frame, text=text, font=(FONT_PRIMARY, 8, "bold"), bg=COLOR_WARNING, fg="#FFFFFF", width=8, height=2, bd=0, relief="flat", cursor="hand2", command=lambda: self.var_id.set(""))
            else:
                btn = tk.Button(keypad_frame, text=text, font=(FONT_PRIMARY, 10, "bold"), bg=COLOR_SECONDARY, fg=COLOR_TEXT_DARK, width=5, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=text: self._press_num(t))
                btn.configure(highlightbackground=COLOR_CARD_BORDER)
            btn.grid(row=row, column=col, padx=2, pady=2)

        tk.Label(panel_form, text="3. DEPARTAMENTO:", font=(FONT_PRIMARY, 8, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w", padx=12, pady=(4, 0))
        self.var_depto = tk.StringVar(value=DEPTOS_DISPONIBLES[0])
        opt_depto = ttk.OptionMenu(panel_form, self.var_depto, DEPTOS_DISPONIBLES[0], *DEPTOS_DISPONIBLES)
        opt_depto.pack(fill="x", padx=12, pady=2)

        self.lbl_status = tk.Label(panel_form, text="", font=(FONT_PRIMARY, 8, "bold"), bg=COLOR_CARD, wraplength=240)
        self.lbl_status.pack(pady=4)

        panel_cam = tk.Frame(main_frame, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        panel_cam.configure(highlightbackground=COLOR_CARD_BORDER)
        panel_cam.pack(side="right", fill="both", expand=True, padx=(4, 4), pady=4)

        self.lbl_video = tk.Label(panel_cam, bg="#0B1A10", width=400, height=260)
        self.lbl_video.pack(pady=8, padx=8, expand=True)

        btn_guardar = tk.Button(
            panel_cam, text="📸 CAPTURAR Y ENROLAR", font=(FONT_PRIMARY, 11, "bold"),
            bg=COLOR_PRIMARY, fg="#FFFFFF", activebackground=COLOR_PRIMARY_HOVER, activeforeground="#FFFFFF",
            bd=0, relief="flat", cursor="hand2", command=self.guardar_enrolamiento,
        )
        btn_guardar.pack(pady=8, ipadx=10, ipady=6, fill="x", padx=15)

        btn_volver = tk.Button(
            self, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 9, "bold"),
            bg=COLOR_MUTED, fg="#FFFFFF", activebackground=COLOR_TEXT_DARK, activeforeground="#FFFFFF",
            bd=0, relief="flat", padx=12, pady=5, cursor="hand2",
            command=lambda: controller.show_frame("PantallaPrincipal"),
        )
        btn_volver.pack(pady=(0, 6))

    def _limpiar_nfc(self):
        self.var_nfc.set("")
        self.ent_nfc.config(bg=COLOR_BG, bd=1)
        self.lbl_status.config(
            text="Campo NFC limpiado. Retire la tarjeta y acerque otra (o pulse 📡 LEER).",
            fg=COLOR_MUTED,
        )

    def _reintentar_nfc(self):
        self.lbl_status.config(text="⏳ Leyendo tarjeta NFC...", fg=COLOR_WARNING)
        self.controller.gestor_nfc.solicitar_relectura_actual()

    def _on_estado_lector_enrolar(self, conectado, mensaje):
        if conectado:
            self.lbl_nfc_lector.config(text="🟢 Lector NFC listo: acerque la tarjeta del colaborador", fg=COLOR_PRIMARY)
        else:
            self.lbl_nfc_lector.config(text="🔴 Lector NFC no conectado", fg=COLOR_DANGER)

    def _on_error_lectura_enrolar(self, detalle):
        self.bell()
        self.lbl_status.config(
            text=f"⚠️ Lectura NFC no exitosa ({detalle}). Retire y vuelva a acercar la tarjeta.",
            fg=COLOR_DANGER,
        )

    def _on_tarjeta_retirada_enrolar(self):
        if not self.var_nfc.get().strip():
            self.lbl_status.config(text="📡 Tarjeta retirada. Acerque la nueva tarjeta NFC.", fg=COLOR_MUTED)

    def _on_nfc_detectado_enrolar(self, uid_hex):
        self.controller.reset_inactivity_timer()
        self.bell()
        uid_limpio = normalizar_uid_nfc(uid_hex)
        self.var_nfc.set(uid_limpio)
        self.ent_nfc.config(bg="#EAF5EC", bd=2)

        emp_existente = obtener_id_por_nfc(uid_limpio)
        emp_actual = self.var_id.get().strip().upper()
        if emp_existente and emp_existente != emp_actual:
            self.lbl_status.config(
                text=f"⚠️ Advertencia: Esta tarjeta ({uid_limpio}) ya está asignada al ID {emp_existente}.",
                fg=COLOR_WARNING,
            )
        else:
            self.lbl_status.config(text=f"✓ Tarjeta NFC capturada: {uid_limpio}", fg=COLOR_PRIMARY)

    def on_show(self):
        self.var_id.set("")
        self.var_nfc.set("")
        self.ent_id.config(bg="#EAF5EC", bd=2, relief="solid")
        self.ent_nfc.config(bg=COLOR_BG, bd=1, relief="solid")
        self.lbl_status.config(text="")
        self.ultimo_frame = None
        self._frame_count = 0

        self.controller.gestor_nfc.iniciar_escucha(
            callback_uid=self._on_nfc_detectado_enrolar,
            callback_estado=self._on_estado_lector_enrolar,
            callback_error=self._on_error_lectura_enrolar,
            callback_retirada=self._on_tarjeta_retirada_enrolar,
        )

        self.detener_camara()
        if os.name == "nt":
            self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap.release()
                self.cap = cv2.VideoCapture(0)
        else:
            self.cap = cv2.VideoCapture(0)
        self.is_running = True
        self.actualizar_camara()

    def _press_num(self, num):
        curr = self.var_id.get()
        if len(curr) < 12:
            self.var_id.set(curr + num)

    def _borrar_caracter(self):
        curr = self.var_id.get()
        if len(curr) > 0:
            self.var_id.set(curr[:-1])

    def actualizar_camara(self):
        if not self.is_running or self.cap is None or not self.cap.isOpened():
            return

        ret, frame = self.cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.ultimo_frame = frame_rgb.copy()
            self._frame_count += 1

            if self._frame_count % 3 == 0:
                locations = face_recognition.face_locations(cv2.resize(frame_rgb, (0, 0), fx=0.4, fy=0.4))
                self._ultima_cara = locations[0] if len(locations) > 0 else None

            if getattr(self, "_ultima_cara", None):
                top, right, bottom, left = self._ultima_cara
                cv2.rectangle(
                    frame_rgb,
                    (int(left * 2.5), int(top * 2.5)),
                    (int(right * 2.5), int(bottom * 2.5)),
                    (49, 167, 72),
                    2,
                )

            img = Image.fromarray(frame_rgb).resize((400, 260), Image.Resampling.LANCZOS)
            imgtk = ImageTk.PhotoImage(image=img)
            self.lbl_video.imgtk = imgtk
            self.lbl_video.configure(image=imgtk)

        if self.is_running:
            self.after(20, self.actualizar_camara)

    def guardar_enrolamiento(self):
        emp_id = self.var_id.get().strip()
        nfc_uid = self.var_nfc.get().strip()
        depto = self.var_depto.get().strip()

        if not emp_id:
            self.lbl_status.config(text="⚠️ Ingrese un ID / Cédula válido.", fg=COLOR_DANGER)
            return

        if not nfc_uid:
            self.lbl_status.config(text="⚠️ Acerque la tarjeta NFC al lector Cryptnox.", fg=COLOR_DANGER)
            return

        if self.ultimo_frame is None:
            self.lbl_status.config(text="⚠️ Sin señal de cámara.", fg=COLOR_DANGER)
            return

        self.lbl_status.config(text="⏳ Generando vector y guardando...", fg=COLOR_WARNING)
        self.update_idletasks()

        encoding_np = extraer_vector_facial(self.ultimo_frame)
        if encoding_np is None:
            self.lbl_status.config(text="❌ No se detectó rostro.", fg=COLOR_DANGER)
            registrar_log_incidente(emp_id, "ENROLAMIENTO", "Rostro No Detectado", "Cámara no detectó cara limpia")
            return

        ok, msg = api_guardar_nuevo_empleado(emp_id, depto, nfc_uid, encoding_np)
        if ok:
            self.lbl_status.config(text=f"✓ {msg}", fg=COLOR_PRIMARY)
            self.after(1500, lambda: self.controller.show_frame("PantallaPrincipal"))
        else:
            self.lbl_status.config(text=msg, fg=COLOR_DANGER)

    def detener_camara(self):
        self.is_running = False
        self._ultima_cara = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None


# ----------------------------------------------------------------------
# 8. CONFIGURACIÓN DE RED Y SERVIDOR REST API
# ----------------------------------------------------------------------
class PantallaConfiguracion(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        tk.Label(
            self, text="CONFIGURACIÓN DE RED Y SERVIDOR REST API",
            font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG,
        ).pack(pady=4)

        card = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        card.configure(highlightbackground=COLOR_CARD_BORDER)
        card.pack(pady=2, padx=30, fill="both", expand=True)

        fields_frame = tk.Frame(card, bg=COLOR_CARD)
        fields_frame.pack(pady=(6, 4), padx=20, fill="x")

        ip_box = tk.Frame(fields_frame, bg=COLOR_CARD)
        ip_box.pack(side="left", fill="x", expand=True, padx=(0, 10))
        tk.Label(ip_box, text="1. DIRECCIÓN IP / HOST:", font=(FONT_PRIMARY, 9, "bold"), fg=COLOR_MUTED, bg=COLOR_CARD).pack(anchor="w")
        self.var_ip = tk.StringVar()
        self.ent_ip = tk.Entry(ip_box, textvariable=self.var_ip, font=(FONT_PRIMARY, 12, "bold"), justify="center", bd=1, relief="solid", bg=COLOR_BG, fg=COLOR_TEXT_DARK)
        self.ent_ip.pack(fill="x", ipady=5)

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
            ("127.0.0.1", lambda: self.add_shortcut_ip("127.0.0.1")),
        ]

        for txt, cmd in shortcuts:
            btn = tk.Button(shortcuts_frame, text=txt, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_CARD, fg=COLOR_PRIMARY, bd=1, relief="solid", cursor="hand2", padx=8, pady=4, command=cmd)
            btn.configure(highlightbackground=COLOR_CARD_BORDER)
            btn.pack(side="left", padx=4)

        keypad_frame = tk.Frame(card, bg=COLOR_CARD)
        keypad_frame.pack(pady=4)

        keypad_buttons = [
            ('7', 0, 0), ('8', 0, 1), ('9', 0, 2), ('.', 0, 3), ('⌫ BORRAR', 0, 4),
            ('4', 1, 0), ('5', 1, 1), ('6', 1, 2), (':', 1, 3), ('LIMPIAR', 1, 4),
            ('1', 2, 0), ('2', 2, 1), ('3', 2, 2), ('/', 2, 3), ('⇄ CAMBIAR', 2, 4),
            ('0', 3, 0), ('-', 3, 3),
        ]

        for item in keypad_buttons:
            txt, r, c = item[0], item[1], item[2]
            if txt == '⌫ BORRAR':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_DANGER, fg="#FFFFFF", width=11, height=2, bd=0, relief="flat", cursor="hand2", command=self.borrar_caracter)
            elif txt == 'LIMPIAR':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_WARNING, fg="#FFFFFF", width=11, height=2, bd=0, relief="flat", cursor="hand2", command=self.borrar_todo)
            elif txt == '⇄ CAMBIAR':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_PRIMARY, fg="#FFFFFF", width=11, height=2, bd=0, relief="flat", cursor="hand2", command=self.toggle_active_field)
            elif txt == '0':
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 12, "bold"), bg=COLOR_SECONDARY, fg=COLOR_TEXT_DARK, width=18, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=txt: self.add_text(t))
                btn.configure(highlightbackground=COLOR_CARD_BORDER)
                btn.grid(row=r, column=c, columnspan=3, padx=3, pady=3)
                continue
            else:
                btn = tk.Button(keypad_frame, text=txt, font=(FONT_PRIMARY, 12, "bold"), bg=COLOR_SECONDARY, fg=COLOR_TEXT_DARK, width=5, height=2, bd=1, relief="solid", cursor="hand2", command=lambda t=txt: self.add_text(t))
                btn.configure(highlightbackground=COLOR_CARD_BORDER)

            btn.grid(row=r, column=c, padx=3, pady=3)

        self.lbl_status = tk.Label(card, text="", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_CARD, wraplength=500)
        self.lbl_status.pack(pady=2)

        frame_actions = tk.Frame(card, bg=COLOR_CARD)
        frame_actions.pack(pady=4)

        btn_test = tk.Button(frame_actions, text="🔍 PROBAR CONEXIÓN", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_WARNING, fg="#FFFFFF", bd=0, relief="flat", cursor="hand2", padx=10, pady=5, command=self.probar_conexion)
        btn_test.grid(row=0, column=0, padx=5)

        btn_save = tk.Button(frame_actions, text="💾 GUARDAR CONFIGURACIÓN", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_PRIMARY, fg="#FFFFFF", bd=0, relief="flat", cursor="hand2", padx=10, pady=5, command=self.guardar_config)
        btn_save.grid(row=0, column=1, padx=5)

        btn_volver = tk.Button(self, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_MUTED, fg="#FFFFFF", bd=0, relief="flat", padx=12, pady=4, cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        btn_volver.pack(pady=6)

    def set_active(self, var, entry_widget):
        self.active_var = var
        self.active_entry = entry_widget
        self.ent_ip.config(bg=COLOR_BG, bd=1, relief="solid")
        self.ent_port.config(bg=COLOR_BG, bd=1, relief="solid")
        entry_widget.config(bg="#EAF5EC", bd=2, relief="solid")

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

        exito, mensaje_respuesta = probar_conexion_servidor(base_url)
        if exito:
            self.lbl_status.config(text=mensaje_respuesta, fg=COLOR_PRIMARY)
            threading.Thread(target=sincronizar_empleados_servidor, daemon=True).start()
            threading.Thread(target=sincronizar_marcaciones_pendientes, daemon=True).start()
        else:
            self.lbl_status.config(
                text=f"❌ Imposible conectar al puerto HTTP en {base_url}\n"
                     f"Verifique que el firewall del servidor permita el puerto {port}.",
                fg=COLOR_DANGER,
            )

    def guardar_config(self):
        ip = self.var_ip.get().strip()
        port = self.var_port.get().strip()

        if not ip:
            self.lbl_status.config(text="⚠️ Ingrese una IP válida.", fg=COLOR_DANGER)
            return

        guardar_configuracion(ip, port)
        self.lbl_status.config(text="✓ Configuración de Servidor e IP guardada correctamente.", fg=COLOR_PRIMARY)
        threading.Thread(target=sincronizar_empleados_servidor, daemon=True).start()
        threading.Thread(target=sincronizar_marcaciones_pendientes, daemon=True).start()
        self.after(1200, lambda: self.controller.show_frame("PantallaPrincipal"))


# ----------------------------------------------------------------------
# 9. BITÁCORA DE INCIDENCIAS Y AUDITORÍA DE FALLOS (ADMIN)
# ----------------------------------------------------------------------
class PantallaLog(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg=COLOR_BG)
        self.controller = controller

        HeaderNutresa(self).pack(fill="x")

        tk.Label(
            self, text="BITÁCORA DE INCIDENCIAS Y AUDITORÍA DE FALLOS",
            font=(FONT_PRIMARY, 11, "bold"), fg=COLOR_PRIMARY, bg=COLOR_BG,
        ).pack(pady=4)

        card_table = tk.Frame(self, bg=COLOR_CARD, bd=1, relief="solid", highlightthickness=0)
        card_table.configure(highlightbackground=COLOR_CARD_BORDER)
        card_table.pack(pady=4, padx=20, fill="both", expand=True)

        columns = ("fecha", "emp_id", "operacion", "motivo", "detalle")
        self.tree = ttk.Treeview(card_table, columns=columns, show="headings", height=10)
        self.tree.heading("fecha", text="FECHA Y HORA")
        self.tree.heading("emp_id", text="ID / NFC")
        self.tree.heading("operacion", text="OPERACIÓN")
        self.tree.heading("motivo", text="MOTIVO / EVENTO")
        self.tree.heading("detalle", text="DETALLE TÉCNICO")

        self.tree.column("fecha", anchor="center", width=130)
        self.tree.column("emp_id", anchor="center", width=100)
        self.tree.column("operacion", anchor="center", width=110)
        self.tree.column("motivo", anchor="w", width=160)
        self.tree.column("detalle", anchor="w", width=240)

        scrollbar_y = ttk.Scrollbar(card_table, orient="vertical", command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(card_table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=scrollbar_y.set, xscroll=scrollbar_x.set)

        self.tree.pack(side="top", fill="both", expand=True, padx=8, pady=(8, 0))
        scrollbar_y.pack(side="right", fill="y")
        scrollbar_x.pack(side="bottom", fill="x", padx=8, pady=(0, 8))

        btn_bar = tk.Frame(self, bg=COLOR_BG)
        btn_bar.pack(pady=8)

        btn_refresh = tk.Button(btn_bar, text="🔄 REFRESCAR LOG", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_PRIMARY, fg="#FFFFFF", activebackground=COLOR_PRIMARY_HOVER, activeforeground="#FFFFFF", bd=0, relief="flat", padx=12, pady=6, cursor="hand2", command=self.cargar_log)
        btn_refresh.pack(side="left", padx=5)

        btn_clear = tk.Button(btn_bar, text="🗑️ LIMPIAR LOG", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_DANGER, fg="#FFFFFF", activebackground=COLOR_DANGER_HOVER, activeforeground="#FFFFFF", bd=0, relief="flat", padx=12, pady=6, cursor="hand2", command=self.limpiar_log)
        btn_clear.pack(side="left", padx=5)

        btn_volver = tk.Button(btn_bar, text="← REGRESAR AL MENÚ", font=(FONT_PRIMARY, 9, "bold"), bg=COLOR_MUTED, fg="#FFFFFF", activebackground=COLOR_TEXT_DARK, activeforeground="#FFFFFF", bd=0, relief="flat", padx=12, pady=6, cursor="hand2", command=lambda: controller.show_frame("PantallaPrincipal"))
        btn_volver.pack(side="left", padx=5)

    def on_show(self):
        self.cargar_log()

    def cargar_log(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        for row in reversed(leer_logs_incidentes()):
            self.tree.insert("", "end", values=(row[0], row[1], row[2], row[3], row[4]))

    def limpiar_log(self):
        limpiar_logs_incidentes()
        self.cargar_log()