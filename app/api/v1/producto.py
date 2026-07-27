"""
app/api/v1/producto.py — Endpoints del inventario de productos.

Todos requieren Bearer token: los productos siempre están atados al
usuario_id del token, nunca se reciben ni exponen "sueltos".
"""

from fastapi import APIRouter, Depends, status
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


@router.post("", response_model=ProductoOut, status_code=status.HTTP_201_CREATED)
def agregar(
    datos: ProductoCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return product_service.agregar(
        db, usuario_actual.id, datos.nombre, datos.cantidad, datos.precio, datos.cuanto_costo
    )


@router.put("/{producto_id}", response_model=ProductoOut)
def editar(
    producto_id: str,
    datos: ProductoActualizar,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return product_service.editar(
        db, usuario_actual.id, producto_id, datos.nombre, datos.cantidad, datos.precio, datos.cuanto_costo
    )


@router.delete("/{producto_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    producto_id: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    product_service.eliminar(db, usuario_actual.id, producto_id)