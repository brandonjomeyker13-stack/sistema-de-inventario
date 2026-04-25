import flet as ft
import logica as lg
import database as db
from datetime import datetime


def main(page: ft.Page):
    db.inicializar_db()
    
    page.title = "Sistema de Inventario y Ventas"
    page.window_width = 450
    page.window_height = 700
    page.theme_mode = ft.ThemeMode.DARK
    page.scroll = "adaptive"
    page.padding = 0
    page.window_icon = "assets/logo.png"
    

    
    #  NAVEGACION MANUAL
    
    TAB_LABELS = [" Agregar", " Vender", " Inventario", " Ventas"]
    tab_actual = {"index": 0}
    nav_buttons = []
    vistas = []

    def select_tab(idx):
        tab_actual["index"] = idx
        for i, btn in enumerate(nav_buttons):
            btn.style = ft.ButtonStyle(
                color="white" if i == idx else "grey",
                bgcolor="blue" if i == idx else None,
            )
        for i, v in enumerate(vistas):
            v.visible = (i == idx)
        if idx == 2:
            cargar_inventario()
        page.update()

    for i, label in enumerate(TAB_LABELS):
        idx = i
        btn = ft.ElevatedButton(
            label,
            on_click=lambda e, x=idx: select_tab(x),
            style=ft.ButtonStyle(
                color="white" if i == 0 else "grey",
                bgcolor="blue" if i == 0 else None,
            ),
        )
        nav_buttons.append(btn)

    nav_bar = ft.Container(
        content=ft.Row(nav_buttons, scroll="auto"),
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        bgcolor="grey900",
    )

    
    #  DIALOGO REUTILIZABLE — editar producto
    
    dlg_edit_id    = {"valor": None}
    dlg_txt_nombre = ft.TextField(label="Nombre del Producto")
    dlg_txt_cant   = ft.TextField(label="Cantidad", width=130)
    dlg_txt_precio = ft.TextField(label="Precio de Venta", width=130)
    dlg_txt_costo  = ft.TextField(label="Costo de Compra", width=130)
    dlg_lbl_error  = ft.Text("", color="red", size=13)

    def cerrar_dialogo(e=None):
        dlg_lbl_error.value = ""
        dlg_editar.open = False
        page.update()

    def guardar_edicion(e):
        res = lg.editar_producto(
            dlg_edit_id["valor"],
            dlg_txt_nombre.value,
            dlg_txt_cant.value,
            dlg_txt_precio.value,
            dlg_txt_costo.value,
        )
        if "exito" in res:
            cerrar_dialogo()
            cargar_inventario()
            page.update()
        else:
            dlg_lbl_error.value = res
            page.update()

    dlg_editar = ft.AlertDialog(
        modal=True,
        title=ft.Text("Editar Producto"),
        content=ft.Column(
            [
                dlg_txt_nombre,
                ft.Row([dlg_txt_cant, dlg_txt_costo]),
                dlg_txt_precio,
                dlg_lbl_error,
            ],
            spacing=12,
            tight=True,
        ),
        actions=[
            ft.ElevatedButton(
                "Guardar", icon="SAVE",
                on_click=guardar_edicion,
                style=ft.ButtonStyle(color="white", bgcolor="blue"),
            ),
            ft.TextButton("Cancelar", on_click=cerrar_dialogo),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )
    page.overlay.append(dlg_editar)

    def abrir_dialogo_editar(producto):
        id_p, nombre, cantidad, precio, costo = producto
        dlg_edit_id["valor"]  = id_p
        dlg_txt_nombre.value  = nombre
        dlg_txt_cant.value    = str(cantidad)
        dlg_txt_precio.value  = str(precio)
        dlg_txt_costo.value   = str(costo)
        dlg_lbl_error.value   = ""
        dlg_editar.open = True
        page.update()

    
    #  DIALOGO — confirmar eliminacion
    
    dlg_confirm_accion = {"fn": None}

    def cerrar_confirm(e=None):
        dlg_confirmar.open = False
        page.update()

    def ejecutar_confirm(e):
        dlg_confirmar.open = False
        page.update()
        if dlg_confirm_accion["fn"]:
            dlg_confirm_accion["fn"]()

    dlg_confirmar = ft.AlertDialog(
        modal=True,
        title=ft.Text("Confirmar"),
        content=ft.Text("Esta accion no se puede deshacer. ¿Continuar?"),
        actions=[
            ft.ElevatedButton(
                "Sí, eliminar", icon="DELETE",
                on_click=ejecutar_confirm,
                style=ft.ButtonStyle(color="white", bgcolor="red"),
            ),
            ft.TextButton("Cancelar", on_click=cerrar_confirm),
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.overlay.append(dlg_confirmar)

    def confirmar(fn):
        dlg_confirm_accion["fn"] = fn
        dlg_confirmar.open = True
        page.update()

    
    #  VISTA 1 — AGREGAR PRODUCTO
    
    txt_nombre   = ft.TextField(label="Nombre del Producto", prefix_icon="SHOPPING_BAG")
    txt_cantidad = ft.TextField(label="Cantidad inicial", value="0", width=150)
    txt_precio   = ft.TextField(label="Precio de Venta",  value="0", width=150)
    txt_costo    = ft.TextField(label="Costo de Compra",  value="0", width=150)
    lbl_res_agregar = ft.Text(size=15, weight="bold")

    def click_agregar(e):
        res = lg.agregar_producto(
            txt_nombre.value, txt_cantidad.value,
            txt_precio.value, txt_costo.value
        )
        lbl_res_agregar.value = res
        lbl_res_agregar.color = "green" if "exito" in res else "red"
        if "exito" in res:
            txt_nombre.value   = ""
            txt_cantidad.value = "0"
        page.update()

    vista_agregar = ft.Container(
        content=ft.Column(
            [
                ft.Text("Agregar Producto", size=24, weight="bold"),
                ft.Divider(),
                txt_nombre,
                ft.Row([txt_cantidad, txt_costo]),
                txt_precio,
                ft.ElevatedButton(
                    "Guardar en Inventario", icon="ADD",
                    on_click=click_agregar,
                    style=ft.ButtonStyle(color="white", bgcolor="blue"),
                ),
                lbl_res_agregar,
            ],
            spacing=18,
        ),
        padding=20,
        visible=True,
    )

    
    #  VISTA 2 — REGISTRAR VENTA
    
    txt_buscar_venta = ft.TextField(
        label="Buscar producto...",
        prefix_icon="SEARCH",
        on_change=lambda e: on_escribir_busqueda(e),
    )
    txt_venda_cant   = ft.TextField(label="Cantidad", value="1", width=120)
    col_sugerencias  = ft.Column(spacing=4)
    lbl_res_venta    = ft.Text(size=15, weight="bold")
    lbl_ganancia_dia = ft.Text(size=20, color="green", weight="bold")

    def on_escribir_busqueda(e):
        query = (e.control.value or "").strip().lower()
        col_sugerencias.controls.clear()
        if query:
            productos = lg.obtener_inventario()
            encontrados = [p for p in productos if query in p[1].lower()][:6]
            for p in encontrados:
                _, nombre, cantidad, precio, _ = p
                col_sugerencias.controls.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(nombre, expand=True, weight="bold"),
                            ft.Text(f"Stock: {cantidad}", color="grey", size=12),
                            ft.Text(f"${precio:.2f}", color="green", size=12),
                        ], spacing=8),
                        padding=ft.padding.symmetric(horizontal=12, vertical=8),
                        border_radius=8,
                        bgcolor="grey800",
                        on_click=lambda e, n=nombre: elegir_producto(n),
                        ink=True,
                    )
                )
        page.update()

    def elegir_producto(nombre):
        txt_buscar_venta.value = nombre
        col_sugerencias.controls.clear()
        page.update()

    def refrescar_ganancia_dia():
        ganancia = lg.obtener_ganancia_hoy()
        lbl_ganancia_dia.value = f"Ganancia de hoy: ${ganancia:.2f}"

    def click_vender(e):
        res = lg.vender_producto(txt_buscar_venta.value, txt_venda_cant.value)
        lbl_res_venta.value = res
        lbl_res_venta.color = "cyan" if "exitosa" in res else "red"
        col_sugerencias.controls.clear()
        refrescar_ganancia_dia()
        page.update()

    refrescar_ganancia_dia()

    vista_vender = ft.Container(
        content=ft.Column(
            [
                ft.Text("Registrar Venta", size=24, weight="bold"),
                ft.Divider(),
                txt_buscar_venta,
                col_sugerencias,
                txt_venda_cant,
                ft.ElevatedButton(
                    "Realizar Venta", icon="SELL",
                    on_click=click_vender,
                    style=ft.ButtonStyle(color="white", bgcolor="green"),
                ),
                ft.Divider(),
                lbl_res_venta,
                lbl_ganancia_dia,
            ],
            spacing=14,
        ),
        padding=20,
        visible=False,
    )

   
    #  VISTA 3 — INVENTARIO (con editar y eliminar)
    
    col_inventario = ft.Column(spacing=8)

    def cargar_inventario():
        col_inventario.controls.clear()
        productos = lg.obtener_inventario()
        if not productos:
            col_inventario.controls.append(
                ft.Text("No hay productos en el inventario", color="grey")
            )
            return
        for p in productos:
            prod = p  # captura para closures
            _, nombre, cantidad, precio, costo = p
            color_stock = "red" if cantidad == 0 else ("orange" if cantidad < 5 else "cyan")
            col_inventario.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Text(nombre, weight="bold", size=16),
                        ft.Row([
                            ft.Container(
                                content=ft.Text(f"Stock: {cantidad}", color=color_stock, size=13),
                                border=ft.border.all(1, color_stock),
                                border_radius=20,
                                padding=ft.padding.symmetric(horizontal=8, vertical=3),
                            ),
                            ft.Text(f"Venta: ${precio:.2f}", color="green", size=13),
                            ft.Text(f"Costo: ${costo:.2f}", color="orange", size=13),
                        ], spacing=8),
                        ft.Row([
                            ft.ElevatedButton(
                                "Editar", icon="EDIT",
                                on_click=lambda e, pr=prod: abrir_dialogo_editar(pr),
                                style=ft.ButtonStyle(color="white", bgcolor="blue"),
                                height=35,
                            ),
                            ft.ElevatedButton(
                                "Eliminar", icon="DELETE",
                                on_click=lambda e, pid=p[0]: confirmar(lambda: _eliminar_producto(pid)),
                                style=ft.ButtonStyle(color="white", bgcolor="red"),
                                height=35,
                            ),
                        ], spacing=8),
                    ], spacing=6),
                    border=ft.border.all(1, "grey700"),
                    border_radius=10,
                    padding=14,
                )
            )

    def _eliminar_producto(id_p):
        lg.eliminar_producto(id_p)
        cargar_inventario()
        page.update()

    def click_refrescar_inventario(e):
        cargar_inventario()
        page.update()

    vista_inventario = ft.Container(
        content=ft.Column(
            [
                ft.Text("Inventario Completo", size=24, weight="bold"),
                ft.Divider(),
                ft.ElevatedButton(
                    "Actualizar", icon="REFRESH",
                    on_click=click_refrescar_inventario,
                    style=ft.ButtonStyle(color="white", bgcolor="purple"),
                ),
                col_inventario,
            ],
            spacing=14,
        ),
        padding=20,
        visible=False,
    )

   
    #  VISTA 4 — VENTAS POR FECHA (con eliminar venta)
    
    lbl_fecha_elegida = ft.Text("Ninguna fecha seleccionada", color="grey", size=14)
    col_ventas_fecha  = ft.Column(spacing=8)
    lbl_total_fecha   = ft.Text("", size=18, weight="bold", color="green")
    fecha_elegida     = {"valor": ""}

    def on_fecha_cambiada(e):
        if date_picker.value:
            fecha_str = date_picker.value.strftime("%Y-%m-%d")
            fecha_elegida["valor"] = fecha_str
            lbl_fecha_elegida.value = f"Fecha seleccionada: {fecha_str}"
            lbl_fecha_elegida.color = "white"
        page.update()

    date_picker = ft.DatePicker(
        first_date=datetime(2020, 1, 1),
        last_date=datetime(2030, 12, 31),
        on_change=on_fecha_cambiada,
    )
    page.overlay.append(date_picker)

    def abrir_calendario(e):
        date_picker.open = True
        page.update()

    def cargar_ventas_fecha():
        if not fecha_elegida["valor"]:
            return
        ventas, ganancia = lg.obtener_ventas_por_fecha(fecha_elegida["valor"])
        col_ventas_fecha.controls.clear()
        if not ventas:
            col_ventas_fecha.controls.append(
                ft.Text("No hay ventas registradas para esta fecha", color="grey")
            )
            lbl_total_fecha.value = ""
        else:
            for v in ventas:
                id_v, nombre, cantidad, total, gan, fecha = v
                col_ventas_fecha.controls.append(
                    ft.Container(
                        content=ft.Column([
                            ft.Text(nombre, weight="bold", size=15),
                            ft.Row([
                                ft.Text(f"x{cantidad} uds", color="grey", size=13),
                                ft.Text(f"Total: ${total:.2f}", color="cyan", size=13),
                                ft.Text(f"Gan: ${gan:.2f}", color="green", size=13),
                            ], spacing=8),
                            ft.ElevatedButton(
                                "Eliminar venta", icon="DELETE",
                                on_click=lambda e, vid=id_v: confirmar(lambda: _eliminar_venta(vid)),
                                style=ft.ButtonStyle(color="white", bgcolor="red"),
                                height=35,
                            ),
                        ], spacing=6),
                        border=ft.border.all(1, "grey700"),
                        border_radius=10,
                        padding=14,
                    )
                )
            lbl_total_fecha.value = f"Ganancia total del dia: ${ganancia:.2f}"
            lbl_total_fecha.color = "green"

    def _eliminar_venta(id_v):
        lg.eliminar_venta(id_v)
        refrescar_ganancia_dia()
        cargar_ventas_fecha()
        page.update()

    def click_buscar_ventas(e):
        if not fecha_elegida["valor"]:
            lbl_total_fecha.value = "Selecciona una fecha primero"
            lbl_total_fecha.color = "red"
            page.update()
            return
        cargar_ventas_fecha()
        page.update()

    vista_ventas_fecha = ft.Container(
        content=ft.Column(
            [
                ft.Text("Ventas por Fecha", size=24, weight="bold"),
                ft.Divider(),
                ft.ElevatedButton(
                    "Abrir Calendario", icon="CALENDAR_TODAY",
                    on_click=abrir_calendario,
                    style=ft.ButtonStyle(color="white", bgcolor="teal"),
                ),
                lbl_fecha_elegida,
                ft.ElevatedButton(
                    "Buscar Ventas", icon="SEARCH",
                    on_click=click_buscar_ventas,
                    style=ft.ButtonStyle(color="white", bgcolor="orange"),
                ),
                col_ventas_fecha,
                lbl_total_fecha,
            ],
            spacing=14,
        ),
        padding=20,
        visible=False,
    )

   
    #  LAYOUT PRINCIPAL
   
    vistas.extend([vista_agregar, vista_vender, vista_inventario, vista_ventas_fecha])

    page.add(
        ft.Column(
            [
                nav_bar,
                ft.Container(
                    content=ft.Column(
                        [vista_agregar, vista_vender, vista_inventario, vista_ventas_fecha],
                        spacing=0,
                    ),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )
    )





    


ft.app(target=main, assets_dir="assets")