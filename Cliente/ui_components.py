# ======================================================================
# COMPONENTES VISUALES REUTILIZABLES Y ESTILOS TTK
# ======================================================================
import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from config import (
    FONT_PRIMARY,
    COLOR_PRIMARY,
    COLOR_PRIMARY_HOVER,
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_CARD,
    COLOR_TEXT_DARK,
    COLOR_MUTED,
    resolver_ruta_recurso,
)


def aplicar_estilos_ttk(root):
    """Configura la apariencia global de tablas Treeview."""
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        "Treeview.Heading",
        font=(FONT_PRIMARY, 9, "bold"),
        background=COLOR_PRIMARY,
        foreground="#FFFFFF",
        relief="flat",
        padding=6,
    )
    style.map("Treeview.Heading", background=[("active", COLOR_PRIMARY_HOVER)])
    style.configure(
        "Treeview",
        font=(FONT_PRIMARY, 9),
        background=COLOR_CARD,
        foreground=COLOR_TEXT_DARK,
        fieldbackground=COLOR_CARD,
        rowheight=28,
        borderwidth=0,
    )
    style.map("Treeview", background=[("selected", COLOR_ACCENT)], foreground=[("selected", "#FFFFFF")])


class HeaderNutresa(tk.Frame):
    """Encabezado institucional con franjas de marca y logotipo."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLOR_BG)

        top_accent = tk.Frame(self, bg=COLOR_PRIMARY, height=5)
        top_accent.pack(fill="x", side="top")

        top_subaccent = tk.Frame(self, bg=COLOR_ACCENT, height=2)
        top_subaccent.pack(fill="x", side="top")

        brand_frame = tk.Frame(self, bg=COLOR_BG)
        brand_frame.pack(pady=(8, 4))

        ruta_logo = resolver_ruta_recurso(
            "logo.png",
            r"D:\Users\BREAAPONTE\OneDrive - Grupo Nutresa\Escritorio\Main2\Cliente\logo.png",
        )
        if os.path.exists(ruta_logo):
            try:
                img_pil = Image.open(ruta_logo)
                img_pil.thumbnail((240, 50), Image.Resampling.LANCZOS)
                self.img = ImageTk.PhotoImage(img_pil)
                lbl_logo = tk.Label(brand_frame, image=self.img, bg=COLOR_BG)
                lbl_logo.pack()
            except Exception:
                self._crear_logo_texto(brand_frame)
        else:
            self._crear_logo_texto(brand_frame)

    def _crear_logo_texto(self, parent):
        lbl_brand = tk.Label(
            parent, text="alicapsa", font=(FONT_PRIMARY, 22, "bold"),
            fg=COLOR_PRIMARY, bg=COLOR_BG,
        )
        lbl_brand.pack()
        lbl_sub = tk.Label(
            parent, text="SISTEMA DE ASISTENCIA Y TIEMPO",
            font=(FONT_PRIMARY, 8, "bold"), fg=COLOR_MUTED, bg=COLOR_BG,
        )
        lbl_sub.pack(pady=(1, 0))