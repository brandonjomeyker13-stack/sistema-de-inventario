"""
theme.py — Paleta y constantes visuales de NorBox.

Antes cada color y radio de borde estaba escrito a mano y repetido en
decenas de lugares dentro de main.py ("grey900", "blue", border_radius=12,
etc.). Esto centraliza esas decisiones en un solo lugar: cambiar el color
de acento de la app, por ejemplo, ahora es una sola línea acá en vez de
una búsqueda y reemplazo por todo el archivo.

Paleta: fondo tipo "slate" oscuro con un acento teal/esmeralda — pensada
para verse profesional y sobria en un punto de venta, sin depender de
colores "de juguete" (rojo/verde/azul puro) ni de emojis para comunicar
estado.
"""

import flet as ft

# ─── Colores base ───────────────────────────────────────────────────────────
BG_BASE = "#0f172a"        # fondo principal (slate-900)
BG_SUPERFICIE = "#1e293b"   # tarjetas, barras (slate-800)
BG_SUPERFICIE_ALT = "#273449"  # hover / superficie secundaria
BORDE = "#334155"          # slate-700

TEXTO_PRIMARIO = "#f1f5f9"     # slate-100
TEXTO_SECUNDARIO = "#94a3b8"   # slate-400
TEXTO_TENUE = "#64748b"        # slate-500

ACENTO = "#14b8a6"          # teal-500 — color de marca / acciones principales
ACENTO_FUERTE = "#0d9488"    # teal-600 — hover / énfasis

EXITO = "#22c55e"
ADVERTENCIA = "#f59e0b"
PELIGRO = "#ef4444"
INFO = "#38bdf8"

# ─── Espaciado y forma ───────────────────────────────────────────────────────
RADIO_TARJETA = 14
RADIO_BOTON = 10
RADIO_CHIP = 20

ESPACIO_XS = 4
ESPACIO_SM = 8
ESPACIO_MD = 14
ESPACIO_LG = 20
ESPACIO_XL = 28

# ─── Tipografía ──────────────────────────────────────────────────────────────
TITULO_SIZE = 22
SUBTITULO_SIZE = 14
CUERPO_SIZE = 13
ETIQUETA_SIZE = 11


def estilo_boton_primario(bgcolor: str = ACENTO) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color=TEXTO_PRIMARIO,
        bgcolor=bgcolor,
        shape=ft.RoundedRectangleBorder(radius=RADIO_BOTON),
        padding=ft.padding.symmetric(horizontal=18, vertical=12),
    )


def estilo_boton_secundario() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color=TEXTO_SECUNDARIO,
        bgcolor=BG_SUPERFICIE_ALT,
        shape=ft.RoundedRectangleBorder(radius=RADIO_BOTON),
        padding=ft.padding.symmetric(horizontal=16, vertical=10),
    )


def estilo_boton_peligro() -> ft.ButtonStyle:
    return ft.ButtonStyle(
        color=TEXTO_PRIMARIO,
        bgcolor=PELIGRO,
        shape=ft.RoundedRectangleBorder(radius=RADIO_BOTON),
        padding=ft.padding.symmetric(horizontal=16, vertical=10),
    )


def tarjeta(contenido, padding: int = ESPACIO_MD) -> ft.Container:
    """Contenedor tipo 'card' reutilizable para inventario, ventas, etc."""
    return ft.Container(
        content=contenido,
        bgcolor=BG_SUPERFICIE,
        border=ft.border.all(1, BORDE),
        border_radius=RADIO_TARJETA,
        padding=padding,
    )


def titulo_seccion(texto: str, subtitulo: str | None = None) -> ft.Column:
    controles = [ft.Text(texto, size=TITULO_SIZE, weight="bold", color=TEXTO_PRIMARIO)]
    if subtitulo:
        controles.append(ft.Text(subtitulo, size=SUBTITULO_SIZE, color=TEXTO_SECUNDARIO))
    return ft.Column(controles, spacing=2)


def color_stock(cantidad: int, umbral_bajo: int) -> str:
    if cantidad == 0:
        return PELIGRO
    if cantidad < umbral_bajo:
        return ADVERTENCIA
    return EXITO


def estado_vacio(mensaje: str, icono: str = ft.Icons.INBOX_OUTLINED) -> ft.Container:
    """Reemplaza los 'No hay productos' sueltos por un estado vacío consistente."""
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(icono, size=40, color=TEXTO_TENUE),
                ft.Text(mensaje, color=TEXTO_SECUNDARIO, size=CUERPO_SIZE),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=ESPACIO_SM,
        ),
        alignment=ft.alignment.center,
        padding=ESPACIO_XL,
    )