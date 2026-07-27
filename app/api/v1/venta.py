"""
app/api/v1/venta.py — Endpoints de ventas y ganancias.

Todos requieren Bearer token, mismo criterio que producto.py: las ventas
están atadas al usuario_id del token.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual
from app.models.usuario import Usuario
from app.schemas.venta import VentaCrear, VentaOut, VentasPorFechaOut, GananciaOut
from app.services import venta_service

router = APIRouter(prefix="/ventas", tags=["Ventas"])


@router.post("", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
def vender(
    datos: VentaCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return venta_service.vender(db, usuario_actual.id, datos.nombre_producto, datos.cantidad)


@router.get("", response_model=VentasPorFechaOut)
def listar_por_fecha(
    fecha: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    ventas, ganancia = venta_service.ventas_por_fecha(db, usuario_actual.id, fecha)
    return {"ventas": ventas, "ganancia_total": ganancia}


@router.get("/ganancia-hoy", response_model=GananciaOut)
def ganancia_hoy(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    from datetime import datetime

    ganancia = venta_service.ganancia_hoy(db, usuario_actual.id)
    return {"fecha": datetime.now().strftime("%Y-%m-%d"), "ganancia_total": ganancia}


@router.delete("/{venta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    venta_id: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    venta_service.eliminar_venta(db, usuario_actual.id, venta_id)