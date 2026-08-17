"""
app/api/v1/producto.py — Endpoints del inventario de productos.

Todos requieren Bearer token: los productos siempre están atados al
usuario_id del token, nunca se reciben ni exponen "sueltos".
"""

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual, exigir_suscripcion_activa
from app.models.usuario import Usuario
from app.schemas.producto import ProductoCrear, ProductoActualizar, ProductoOut
from app.services import product_service

router = APIRouter(prefix="/productos", tags=["Productos"])


@router.get("", response_model=list[ProductoOut])
def listar(
    respuesta: Response,
    q: str | None = Query(default=None, description="Busca en nombre y código de barras"),
    categoria_id: str | None = None,
    sin_codigo: bool = Query(default=False, description="Solo los que no tienen código de barras"),
    limite: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """El inventario, con búsqueda y paginación opcionales.

    Sin `limite` devuelve todo, como siempre. No se pone un tope por
    defecto a propósito: truncar en silencio el inventario de quien tiene
    500 productos haría que la caja mostrara un catálogo incompleto sin
    que nadie lo note. Es peor una respuesta incorrecta que una grande.

    `sin_codigo=true` deja solo los que faltan por escanear. Es la lista de
    trabajo después de importar la plantilla, donde ningún producto trae
    código: el tendero pasa el lector por cada uno y deja de tener que
    buscarlos por nombre. El asistente sabe cuántos son y manda aquí.

    El total (sin paginar) va en `X-Total-Count`.
    """
    respuesta.headers["X-Total-Count"] = str(
        product_service.contar(db, usuario_actual.id, q, categoria_id, sin_codigo)
    )
    return product_service.listar(
        db, usuario_actual.id, q, categoria_id, limite, offset, sin_codigo,
    )


@router.get("/codigo/{codigo_barras}", response_model=ProductoOut | None)
def buscar_por_codigo(
    codigo_barras: str,
    respuesta: Response,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Lo que llama el lector (o la cámara) al escanear.

    Devuelve 200 con el producto si lo conoce, y 204 sin cuerpo si el
    código no está registrado. El 204 no es un error: es la señal de
    "producto nuevo, pregúntale al tendero cómo se llama y a cuánto".
    Un 404 aquí obligaría al frontend a tratar lo normal como excepción.
    """
    producto = product_service.buscar_por_codigo_barras(db, usuario_actual.id, codigo_barras)
    if not producto:
        respuesta.status_code = status.HTTP_204_NO_CONTENT
        return None
    return producto


@router.post("", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def agregar(
    datos: ProductoCrear,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Da de alta un producto o un servicio.

    Con `controla_stock: false` se crea un SERVICIO (fotocopia, impresión,
    plastificado): se vende y deja ganancia como cualquier producto, pero
    no lleva existencias — no se descuenta al venderlo ni sale en las
    alertas de "se está acabando".

    Si el precio queda por debajo del costo responde 400 explicando el
    problema: es casi siempre el costo y el precio invertidos. Para
    guardarlo de todas formas (una liquidación, mercancía dañada) hay que
    reenviarlo con `permitir_perdida: true`.
    """
    return product_service.agregar(
        db, usuario_actual.id, datos.nombre, datos.cantidad, datos.precio, datos.cuanto_costo,
        datos.codigo_barras, datos.categoria_id, controla_stock=datos.controla_stock,
        permitir_perdida=datos.permitir_perdida, stock_minimo=datos.stock_minimo,
    )


@router.put("/{producto_id}", response_model=ProductoOut)
def editar(
    producto_id: str,
    datos: ProductoActualizar,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    return product_service.editar(
        db, usuario_actual.id, producto_id, datos.nombre, datos.cantidad, datos.precio,
        datos.cuanto_costo, datos.codigo_barras, datos.categoria_id,
        controla_stock=datos.controla_stock, permitir_perdida=datos.permitir_perdida,
        stock_minimo=datos.stock_minimo,
    )


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    producto_id: str,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    product_service.eliminar(db, usuario_actual.id, producto_id)