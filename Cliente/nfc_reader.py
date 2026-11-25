# ======================================================================
# GESTOR NATIVO PC/SC POR EVENTOS PARA LECTOR NFC CRYPTNOX
# ======================================================================
import sys
import time
import ctypes
import threading


class GestorNFC:
    """
    Usa SCardGetStatusChange del subsistema PC/SC nativo (winscard / PCSC / libpcsclite)
    para detectar inserción y retiro de tarjetas por eventos sin sondear
    continuamente el campo RF.
    """

    SCARD_SCOPE_SYSTEM = 2
    SCARD_SHARE_SHARED = 2
    SCARD_PROTOCOL_T0 = 1
    SCARD_PROTOCOL_T1 = 2
    SCARD_LEAVE_CARD = 0

    SCARD_STATE_UNAWARE = 0x00000000
    SCARD_STATE_CHANGED = 0x00000002
    SCARD_STATE_UNAVAILABLE = 0x00000008
    SCARD_STATE_EMPTY = 0x00000010
    SCARD_STATE_PRESENT = 0x00000020
    SCARD_STATE_MUTE = 0x00000200

    SCARD_E_TIMEOUT = 0x8010000A
    SCARD_W_RESET_CARD = 0x80100068

    def __init__(self, root):
        self.root = root
        self.activo = False
        self.callback_uid = None
        self.callback_estado = None
        self.callback_error = None
        self.callback_retirada = None

        self._lock = threading.Lock()
        self._forzar_relectura = False
        self._sesion_id = 0
        self._disponible = False
        self._hContext = None

        self._init_pcsc_bindings()

        self._running = True
        self._thread = threading.Thread(target=self._loop_eventos, daemon=True)
        self._thread.start()

    def _init_pcsc_bindings(self):
        try:
            if sys.platform == "win32":
                self.scard = ctypes.WinDLL("winscard.dll")
                self.DWORD = ctypes.c_uint32
            elif sys.platform == "darwin":
                self.scard = ctypes.CDLL("/System/Library/Frameworks/PCSC.framework/PCSC")
                self.DWORD = ctypes.c_ulong
            else:
                self.scard = ctypes.CDLL("libpcsclite.so.1")
                self.DWORD = ctypes.c_ulong

            self.SCARDCONTEXT = ctypes.c_void_p
            self.SCARDHANDLE = ctypes.c_void_p
            DWORD = self.DWORD
            SCARDCONTEXT = self.SCARDCONTEXT
            SCARDHANDLE = self.SCARDHANDLE

            class SCARD_IO_REQUEST(ctypes.Structure):
                _fields_ = [
                    ("dwProtocol", DWORD),
                    ("cbPciLength", DWORD),
                ]

            class SCARD_READERSTATE(ctypes.Structure):
                _fields_ = [
                    ("szReader", ctypes.c_char_p),
                    ("pvUserData", ctypes.c_void_p),
                    ("dwCurrentState", DWORD),
                    ("dwEventState", DWORD),
                    ("cbAtr", DWORD),
                    ("rgbAtr", ctypes.c_ubyte * 36),
                ]

            self.SCARD_IO_REQUEST = SCARD_IO_REQUEST
            self.SCARD_READERSTATE = SCARD_READERSTATE

            self.SCardEstablishContext = self.scard.SCardEstablishContext
            self.SCardListReaders = getattr(self.scard, "SCardListReadersA", None) or self.scard.SCardListReaders
            self.SCardGetStatusChange = getattr(self.scard, "SCardGetStatusChangeA", None) or self.scard.SCardGetStatusChange
            self.SCardConnect = getattr(self.scard, "SCardConnectA", None) or self.scard.SCardConnect
            self.SCardReconnect = getattr(self.scard, "SCardReconnect", None)
            self.SCardTransmit = self.scard.SCardTransmit
            self.SCardDisconnect = self.scard.SCardDisconnect
            self.SCardReleaseContext = self.scard.SCardReleaseContext

            self.SCardEstablishContext.argtypes = [DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(SCARDCONTEXT)]
            self.SCardEstablishContext.restype = DWORD

            self.SCardListReaders.argtypes = [SCARDCONTEXT, ctypes.c_char_p, ctypes.c_void_p, ctypes.POINTER(DWORD)]
            self.SCardListReaders.restype = DWORD

            self.SCardGetStatusChange.argtypes = [SCARDCONTEXT, DWORD, ctypes.POINTER(SCARD_READERSTATE), DWORD]
            self.SCardGetStatusChange.restype = DWORD

            self.SCardConnect.argtypes = [SCARDCONTEXT, ctypes.c_char_p, DWORD, DWORD, ctypes.POINTER(SCARDHANDLE), ctypes.POINTER(DWORD)]
            self.SCardConnect.restype = DWORD

            if self.SCardReconnect:
                self.SCardReconnect.argtypes = [SCARDHANDLE, DWORD, DWORD, DWORD, ctypes.POINTER(DWORD)]
                self.SCardReconnect.restype = DWORD

            self.SCardTransmit.argtypes = [
                SCARDHANDLE,
                ctypes.POINTER(SCARD_IO_REQUEST),
                ctypes.POINTER(ctypes.c_ubyte),
                DWORD,
                ctypes.POINTER(SCARD_IO_REQUEST),
                ctypes.POINTER(ctypes.c_ubyte),
                ctypes.POINTER(DWORD),
            ]
            self.SCardTransmit.restype = DWORD

            self.SCardDisconnect.argtypes = [SCARDHANDLE, DWORD]
            self.SCardDisconnect.restype = DWORD

            self.SCardReleaseContext.argtypes = [SCARDCONTEXT]
            self.SCardReleaseContext.restype = DWORD

            self._hContext = self.SCARDCONTEXT()
            self._disponible = True
        except Exception as e:
            print(f"[NFC WARNING] No se pudo cargar el subsistema PC/SC: {e}")
            self._disponible = False

    def iniciar_escucha(self, callback_uid, callback_estado=None, callback_error=None, callback_retirada=None):
        """Activa la detección por eventos de tarjetas NFC para la vista actual."""
        with self._lock:
            self._sesion_id += 1
            self.callback_uid = callback_uid
            self.callback_estado = callback_estado
            self.callback_error = callback_error
            self.callback_retirada = callback_retirada
            self._forzar_relectura = False
            self.activo = True

    def detener_escucha(self):
        """Pausa la detección de tarjetas NFC al salir de la pantalla."""
        with self._lock:
            self._sesion_id += 1
            self.activo = False
            self.callback_uid = None
            self.callback_estado = None
            self.callback_error = None
            self.callback_retirada = None
            self._forzar_relectura = False

    def solicitar_relectura_actual(self):
        """Fuerza una única lectura de la tarjeta si ya está apoyada sobre el lector."""
        with self._lock:
            self._forzar_relectura = True

    def cerrar(self):
        self._running = False
        self.detener_escucha()
        self._liberar_contexto()

    def _liberar_contexto(self):
        if self._disponible and self._hContext and self._hContext.value:
            try:
                self.SCardReleaseContext(self._hContext)
            except Exception:
                pass
            self._hContext = self.SCARDCONTEXT()

    def _asegurar_contexto(self):
        if not self._disponible:
            return False
        if not self._hContext.value:
            ret = self.SCardEstablishContext(
                self.SCARD_SCOPE_SYSTEM, None, None, ctypes.byref(self._hContext)
            )
            if (ret & 0xFFFFFFFF) != 0:
                return False
        return True

    def _obtener_lector(self):
        readers_len = self.DWORD(0)
        ret = self.SCardListReaders(self._hContext, None, None, ctypes.byref(readers_len))
        if (ret & 0xFFFFFFFF) != 0 or readers_len.value == 0:
            self._liberar_contexto()
            return None

        readers_buf = ctypes.create_string_buffer(readers_len.value)
        ret = self.SCardListReaders(self._hContext, None, readers_buf, ctypes.byref(readers_len))
        if (ret & 0xFFFFFFFF) != 0:
            return None

        readers = [r for r in readers_buf.raw.split(b"\x00") if r]
        if not readers:
            return None

        cryptnox_readers = [r for r in readers if b"cryptnox" in r.lower()]
        if cryptnox_readers:
            for r in cryptnox_readers:
                rl = r.lower()
                if any(tag in rl for tag in (b"contactless", b"picc", b"nfc", b"cl")):
                    return r
            return cryptnox_readers[0]

        for r in readers:
            rl = r.lower()
            if any(tag in rl for tag in (b"contactless", b"picc", b"nfc", b"cl")):
                return r
        return readers[0]

    def _notificar_estado(self, sesion, conectado, mensaje):
        def _dispatch():
            with self._lock:
                if not self.activo or self._sesion_id != sesion or not self.callback_estado:
                    return
                cb = self.callback_estado
            cb(conectado, mensaje)
        try:
            self.root.after(0, _dispatch)
        except Exception:
            pass

    def _notificar_uid(self, sesion, uid_hex):
        def _dispatch():
            with self._lock:
                if not self.activo or self._sesion_id != sesion or not self.callback_uid:
                    return
                cb = self.callback_uid
            cb(uid_hex)
        try:
            self.root.after(0, _dispatch)
        except Exception:
            pass

    def _notificar_error(self, sesion, mensaje):
        def _dispatch():
            with self._lock:
                if not self.activo or self._sesion_id != sesion or not self.callback_error:
                    return
                cb = self.callback_error
            cb(mensaje)
        try:
            self.root.after(0, _dispatch)
        except Exception:
            pass

    def _notificar_retirada(self, sesion):
        def _dispatch():
            with self._lock:
                if not self.activo or self._sesion_id != sesion or not self.callback_retirada:
                    return
                cb = self.callback_retirada
            cb()
        try:
            self.root.after(0, _dispatch)
        except Exception:
            pass

    def _leer_uid_una_vez(self, reader_name):
        """Conecta con la tarjeta presente, solicita el UID (FF CA 00 00 00) y desconecta."""
        ultimo_err = "Sin respuesta de la tarjeta"
        for _ in range(3):
            hCard = self.SCARDHANDLE()
            active_protocol = self.DWORD(0)

            ret = self.SCardConnect(
                self._hContext,
                reader_name,
                self.SCARD_SHARE_SHARED,
                self.SCARD_PROTOCOL_T0 | self.SCARD_PROTOCOL_T1,
                ctypes.byref(hCard),
                ctypes.byref(active_protocol),
            )
            ret_u32 = ret & 0xFFFFFFFF
            if ret_u32 != 0:
                ultimo_err = f"No se pudo conectar (0x{ret_u32:08X})"
                time.sleep(0.08)
                continue

            try:
                io_send = self.SCARD_IO_REQUEST(
                    active_protocol.value, ctypes.sizeof(self.SCARD_IO_REQUEST)
                )
                apdu = (ctypes.c_ubyte * 5)(0xFF, 0xCA, 0x00, 0x00, 0x00)
                recv_buf = (ctypes.c_ubyte * 258)()
                recv_len = self.DWORD(len(recv_buf))

                ret_tx = self.SCardTransmit(
                    hCard,
                    ctypes.byref(io_send),
                    apdu,
                    len(apdu),
                    None,
                    recv_buf,
                    ctypes.byref(recv_len),
                )
                ret_tx_u32 = ret_tx & 0xFFFFFFFF

                if ret_tx_u32 == self.SCARD_W_RESET_CARD and self.SCardReconnect:
                    rec_ret = self.SCardReconnect(
                        hCard,
                        self.SCARD_SHARE_SHARED,
                        self.SCARD_PROTOCOL_T0 | self.SCARD_PROTOCOL_T1,
                        self.SCARD_LEAVE_CARD,
                        ctypes.byref(active_protocol),
                    )
                    if (rec_ret & 0xFFFFFFFF) == 0:
                        io_send = self.SCARD_IO_REQUEST(
                            active_protocol.value, ctypes.sizeof(self.SCARD_IO_REQUEST)
                        )
                        recv_len = self.DWORD(len(recv_buf))
                        ret_tx = self.SCardTransmit(
                            hCard,
                            ctypes.byref(io_send),
                            apdu,
                            len(apdu),
                            None,
                            recv_buf,
                            ctypes.byref(recv_len),
                        )
                        ret_tx_u32 = ret_tx & 0xFFFFFFFF

                if ret_tx_u32 == 0 and recv_len.value >= 2:
                    response = list(recv_buf[:recv_len.value])
                    data, sw1, sw2 = response[:-2], response[-2], response[-1]
                    if sw1 == 0x90 and sw2 == 0x00 and len(data) > 0:
                        return True, "".join(f"{b:02X}" for b in data)
                    ultimo_err = f"SW {sw1:02X}{sw2:02X}"
                else:
                    ultimo_err = f"Error APDU (0x{ret_tx_u32:08X})"
            finally:
                self.SCardDisconnect(hCard, self.SCARD_LEAVE_CARD)

            time.sleep(0.08)

        return False, ultimo_err

    def _loop_eventos(self):
        sesion_actual = -1
        reader_name = None
        reader_state = None
        tarjeta_presente_prev = False
        ultimo_estado_conectado = None

        while self._running:
            with self._lock:
                activo = self.activo
                sesion = self._sesion_id
                forzar = self._forzar_relectura
                if forzar:
                    self._forzar_relectura = False

            if not activo:
                sesion_actual = -1
                reader_name = None
                reader_state = None
                tarjeta_presente_prev = False
                ultimo_estado_conectado = None
                time.sleep(0.15)
                continue

            if sesion != sesion_actual:
                sesion_actual = sesion
                reader_name = None
                reader_state = None
                tarjeta_presente_prev = False
                ultimo_estado_conectado = None

            if not self._asegurar_contexto():
                if ultimo_estado_conectado is not False:
                    ultimo_estado_conectado = False
                    self._notificar_estado(sesion, False, "🔴 Servicio Smart Card inactivo en el sistema.")
                time.sleep(0.5)
                continue

            if reader_name is None:
                lector = self._obtener_lector()
                if lector is None:
                    if ultimo_estado_conectado is not False:
                        ultimo_estado_conectado = False
                        self._notificar_estado(sesion, False, "🔴 Lector NFC Cryptnox no detectado. Conecte el cable USB.")
                    time.sleep(0.4)
                    continue

                reader_name = lector
                reader_state = self.SCARD_READERSTATE()
                reader_state.szReader = reader_name
                reader_state.dwCurrentState = self.SCARD_STATE_UNAWARE
                tarjeta_presente_prev = False

                nombre_str = reader_name.decode("utf-8", errors="replace")
                ultimo_estado_conectado = True
                self._notificar_estado(sesion, True, f"🟢 Lector listo ({nombre_str}) — Esperando tarjeta...")

            ret = self.SCardGetStatusChange(self._hContext, 250, ctypes.byref(reader_state), 1)
            ret_u32 = ret & 0xFFFFFFFF

            if ret_u32 == self.SCARD_E_TIMEOUT:
                if forzar and tarjeta_presente_prev:
                    ok, res_uid = self._leer_uid_una_vez(reader_name)
                    if ok:
                        self._notificar_uid(sesion, res_uid)
                    else:
                        self._notificar_error(sesion, res_uid)
                continue

            if ret_u32 != 0:
                reader_name = None
                reader_state = None
                self._liberar_contexto()
                if ultimo_estado_conectado is not False:
                    ultimo_estado_conectado = False
                    self._notificar_estado(sesion, False, "🔴 Lector NFC desconectado. Reintentando...")
                time.sleep(0.4)
                continue

            event_state = reader_state.dwEventState
            reader_state.dwCurrentState = event_state & ~self.SCARD_STATE_CHANGED

            if event_state & self.SCARD_STATE_UNAVAILABLE:
                reader_name = None
                reader_state = None
                continue

            presente = bool(event_state & self.SCARD_STATE_PRESENT)
            muda = bool(event_state & self.SCARD_STATE_MUTE)

            if presente and (not tarjeta_presente_prev or forzar):
                tarjeta_presente_prev = True
                if muda:
                    self._notificar_error(sesion, "Tarjeta no compatible o mal posicionada")
                else:
                    ok, res_uid = self._leer_uid_una_vez(reader_name)
                    if ok:
                        self._notificar_uid(sesion, res_uid)
                    else:
                        self._notificar_error(sesion, res_uid)

            elif not presente and tarjeta_presente_prev:
                tarjeta_presente_prev = False
                self._notificar_retirada(sesion)