"""
app/core/sectores.py — Catálogo cerrado de sectores de negocio.

Es una lista fija en código, no una tabla ni un texto libre. La razón no
es simplicidad: es que este campo es la llave del análisis de mercado
comparado que viene después.

Si fuera texto libre acabarías con "papeleria", "Papelería", "papelerias"
y "PAPELERIA" como cuatro sectores distintos, y agregar ventas por sector
sería imposible sin limpiar los datos a mano. Un catálogo cerrado
garantiza que dos negocios que ponen lo mismo queden realmente juntos.

Va en código y no en base porque la lista es la misma para todos los
negocios: no es dato de un usuario, es una decisión del producto. Añadir
un sector es un despliegue, y está bien que lo sea — cada sector nuevo
fragmenta la muestra y hay que decidirlo, no dejarlo pasar.
"""

# clave -> nombre para mostrar. La clave es lo que se guarda; nunca se
# cambia una vez publicada, o los datos históricos dejarían de agrupar.
SECTORES: dict[str, str] = {
    "tienda": "Tienda de barrio / minimercado",
    "papeleria": "Papelería",
    "ferreteria": "Ferretería",
    # Las claves van sin tildes ni espacios a propósito: viajan en URLs y
    # en filtros, y una tilde ahí es una fuente de errores tonta.
    "drogueria": "Droguería",
    "panaderia": "Panadería",
    "carniceria": "Carnicería / fruver",
    "licorera": "Licorera",
    "ropa": "Ropa y calzado",
    "belleza": "Belleza y cuidado personal",
    "mascotas": "Mascotas / agroveterinaria",
    "restaurante": "Restaurante / comidas",
    "tecnologia": "Tecnología y accesorios",
    "otro": "Otro",
}


def es_valido(clave: str | None) -> bool:
    return clave is None or clave in SECTORES


def listar() -> list[dict]:
    return [{"clave": c, "nombre": n} for c, n in SECTORES.items()]
