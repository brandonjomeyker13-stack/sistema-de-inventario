"""
app/api/v1/producto.py — Endpoints del inventario de productos.

Todos requieren Bearer token: los productos siempre están atados al
usuario_id del token, nunca se reciben ni exponen "sueltos".
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual
from app.models.usuario import Usuario
from app.schemas.producto import ProductoCrear, ProductoActualizar, ProductoOut
from app.services import product_service

router = APIRouter(prefix="/productos", tags=["Productos"])


@router.get("", response_model=list[ProductoOut])
def listar(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return product_service.listar(db, usuario_actual.id)


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
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return product_service.agregar(
        db, usuario_actual.id, datos.nombre, datos.cantidad, datos.precio, datos.cuanto_costo,
        datos.codigo_barras, datos.categoria_id,
    )


@router.put("/{producto_id}", response_model=ProductoOut)
def editar(
    producto_id: str,
    datos: ProductoActualizar,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return product_service.editar(
        db, usuario_actual.id, producto_id, datos.nombre, datos.cantidad, datos.precio,
        datos.cuanto_costo, datos.codigo_barras, datos.categoria_id,
    )


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    producto_id: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    product_service.eliminar(db, usuario_actual.id, producto_id)