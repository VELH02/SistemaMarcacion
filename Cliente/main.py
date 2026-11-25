# ======================================================================
# CONTROL DE ASISTENCIA Y TIEMPO - APLICACIÓN PRINCIPAL (ALICAPSA)
# ======================================================================
import time
import threading
import multiprocessing as mp
import tkinter as tk

from config import (
    EMPLEADOS_FILE_LOCAL,
    INTERVALO_SYNC_SEGUNDOS,
    TIMEOUT_INACTIVIDAD_SEGUNDOS,
    COLOR_BG,
)
from storage import (
    MAPA_NFC_A_ID,
    inicializar_entorno,
    cargar_empleados_locales,
    reconstruir_mapa_nfc_local,
)
from api_client import (
    servidor_disponible,
    sincronizar_todo,
)
from nfc_reader import GestorNFC
from biometria import worker_reconocimiento
from ui_components import aplicar_estilos_ttk
from views import (
    PantallaPrincipal,
    PantallaNFC,
    PantallaTeclado,
    PantallaBiometrica,
    PantallaHistorial,
    PantallaEnrolar,
    PantallaAdminPin,
    PantallaConfiguracion,
    PantallaLog,
)


class SistemaMarcacionApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Alicapsa - Control de Asistencia Biométrico y NFC")
        self.geometry("840x690")
        self.minsize(800, 620)
        self.configure(bg=COLOR_BG)

        aplicar_estilos_ttk(self)

        # Inicializar entorno local y cargar índice NFC en memoria RAM
        inicializar_entorno()
        emps_iniciales = cargar_empleados_locales()
        reconstruir_mapa_nfc_local(emps_iniciales)
        print(
            f"[INIT] Base local cargada desde '{EMPLEADOS_FILE_LOCAL}': "
            f"{len(emps_iniciales)} empleados, {len(MAPA_NFC_A_ID)} tarjetas NFC."
        )

        # Gestor global del lector NFC Cryptnox por eventos PC/SC
        self.gestor_nfc = GestorNFC(self)

        # Estado de sesión de marcación actual
        self.current_frame_name = "PantallaPrincipal"
        self.current_emp_code = ""
        self.current_emp_nfc = ""
        self.current_emp_depto = ""
        self.current_emp_vector = None
        self.current_action = ""
        self.admin_target = "PantallaEnrolar"
        self.admin_return_frame = "PantallaPrincipal"
        self.admin_override_nfc = False

        self.timeout_seconds = TIMEOUT_INACTIVIDAD_SEGUNDOS
        self.timer_id = None
        self.t_inicio_solicitud = 0.0

        # Proceso independiente para reconocimiento facial y liveness
        self.input_queue = mp.Queue()
        self.output_queue = mp.Queue()
        self.worker_process = mp.Process(
            target=worker_reconocimiento,
            args=(self.input_queue, self.output_queue),
            daemon=True,
        )
        self.worker_process.start()

        # Hilo de sincronización automática en segundo plano
        self.sync_activa = True
        self.sync_stop = threading.Event()
        self.hilo_sync = threading.Thread(target=self._loop_sincronizacion_periodica, daemon=True)
        self.hilo_sync.start()

        # Contenedor principal de pantallas
        self.container = tk.Frame(self, bg=COLOR_BG)
        self.container.pack(fill="both", expand=True)

        self.bind_all("<Button-1>", self.reset_inactivity_timer)
        self.bind_all("<Key>", self.reset_inactivity_timer)

        self.frames = {}
        for view_cls in (
            PantallaPrincipal,
            PantallaNFC,
            PantallaTeclado,
            PantallaBiometrica,
            PantallaHistorial,
            PantallaEnrolar,
            PantallaAdminPin,
            PantallaConfiguracion,
            PantallaLog,
        ):
            page_name = view_cls.__name__
            frame = view_cls(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.show_frame("PantallaPrincipal")

    def _loop_sincronizacion_periodica(self):
        """
        Ciclo en segundo plano:
        - Detecta cuando el servidor pasa de OFFLINE -> ONLINE y ejecuta de inmediato
          una sincronización bidireccional completa (sube pendientes y descarga empleados).
        - Mientras está ONLINE, sube pendientes cada 30 segundos y descarga empleados
          periódicamente según INTERVALO_SYNC_SEGUNDOS.
        """
        estaba_offline = True
        ultimo_sync_empleados = 0.0

        while self.sync_activa:
            try:
                online = servidor_disponible(timeout=3)

                if online:
                    ahora = time.monotonic()
                    necesita_descarga = (
                        estaba_offline
                        or (ahora - ultimo_sync_empleados) >= INTERVALO_SYNC_SEGUNDOS
                    )

                    if estaba_offline:
                        print("[SYNC] 🟢 Servidor detectado en línea. Iniciando sincronización bidireccional...")

                    sync_ok = sincronizar_todo(descargar_empleados=necesita_descarga)
                    if sync_ok:
                        estaba_offline = False
                        if necesita_descarga:
                            ultimo_sync_empleados = ahora
                    else:
                        estaba_offline = True
                else:
                    if not estaba_offline:
                        print("[SYNC] 🔴 Servidor fuera de línea. Modo Offline activo.")
                    estaba_offline = True

            except Exception as e:
                print(f"[SYNC LOOP ERROR] {e}")
                estaba_offline = True

            self.sync_stop.wait(30)

    def show_frame(self, page_name):
        self.gestor_nfc.detener_escucha()
        for frame in self.frames.values():
            if hasattr(frame, "on_hide"):
                frame.on_hide()
            if hasattr(frame, "detener_camara"):
                frame.detener_camara()

        self.current_frame_name = page_name
        frame = self.frames[page_name]
        frame.tkraise()
        if hasattr(frame, "on_show"):
            frame.on_show()
        self.reset_inactivity_timer()

    def reset_inactivity_timer(self, event=None):
        if self.timer_id:
            self.after_cancel(self.timer_id)

        if self.current_frame_name != "PantallaPrincipal":
            self.timer_id = self.after(self.timeout_seconds * 1000, self.auto_return_to_main)

    def auto_return_to_main(self):
        self.current_emp_code = ""
        self.current_emp_nfc = ""
        self.current_emp_vector = None
        self.current_action = ""
        self.admin_override_nfc = False
        self.show_frame("PantallaPrincipal")

    def get_current_frame_name(self):
        return self.current_frame_name

    def on_closing(self):
        self.sync_activa = False
        self.sync_stop.set()
        for frame in self.frames.values():
            if hasattr(frame,'detener_camara'): frame.detener_camara()
        self.gestor_nfc.cerrar()
        try:
            self.input_queue.put(None)
        except Exception:
            pass
        self.worker_process.join(timeout=1)
        if self.worker_process.is_alive():
            self.worker_process.terminate()
            self.worker_process.join(timeout=1)
        self.destroy()


if __name__ == "__main__":
    mp.freeze_support()
    app = SistemaMarcacionApp()
    app.mainloop()
