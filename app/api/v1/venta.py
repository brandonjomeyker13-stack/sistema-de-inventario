"""
app/api/v1/venta.py — Endpoints de ventas y ganancias.

Todos requieren Bearer token, mismo criterio que producto.py: las ventas
están atadas al usuario_id del token.
"""

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual, exigir_suscripcion_activa
from app.core.fechas import hoy_local
from app.models.usuario import Usuario
from app.schemas.venta import (
    VentaCrear, VentaOut, VentasPorFechaOut, GananciaOut, ResumenVentasOut,
)
from app.services import venta_service

router = APIRouter(prefix="/ventas", tags=["Ventas"])


@router.post("", response_model=VentaOut, status_code=status.HTTP_201_CREATED)
def vender(
    datos: VentaCrear,
    idempotency_key: str | None = Header(default=None),
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Registra una venta de uno o varios productos.

    Acepta `{"items": [...]}` y también la forma antigua de un solo
    producto (`nombre_producto` + `cantidad`). El schema normaliza las dos
    a `items`, así que aquí ya llega una sola forma.

    REINTENTOS SIN DUPLICAR: manda un identificador único por venta, en la
    cabecera `Idempotency-Key` o en el campo `clave_idempotencia`. Si la
    misma clave llega dos veces, la segunda devuelve la venta ya
    registrada en lugar de crear otra.

    Es para la tienda con mala señal: la petición sale, la conexión se
    corta antes de que llegue la respuesta, y el frontend no sabe si la
    venta quedó guardada. Sin la clave, reintentar descuenta el stock dos
    veces y suma plata que nadie pagó — y eso no se nota, porque parece un
    buen día.

    La clave se genera UNA VEZ, cuando el tendero pulsa cobrar, y se
    repite en todos los reintentos de ESE cobro. Si se generara en cada
    envío no serviría de nada.
    """
    items = [item.model_dump() for item in datos.items]
    return venta_service.vender(
        db, usuario_actual.id, items, cliente_id=datos.cliente_id, es_fiado=datos.es_fiado,
        dias_plazo=datos.dias_plazo, fecha_vencimiento=datos.fecha_vencimiento,
        # La cabecera manda; el cuerpo es el plan B, igual que con el token
        # de la canasta, para cuando un proxy se come las cabeceras que no
        # conoce.
        clave_idempotencia=idempotency_key or datos.clave_idempotencia,
    )


@router.get("", response_model=VentasPorFechaOut)
def listar_ventas(
    fecha: str | None = Query(default=None, description="Un día concreto, AAAA-MM-DD"),
    desde: str | None = Query(default=None, description="Inicio del rango, AAAA-MM-DD"),
    hasta: str | None = Query(default=None, description="Fin del rango, AAAA-MM-DD"),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Ventas de un día (`fecha`) o de un rango (`desde`/`hasta`), inclusive.

    El rango evita que un reporte "del 1 al 15" sean quince peticiones.
    Sin ningún parámetro devuelve las de hoy.
    """
    ventas, ganancia = venta_service.ventas_por_fecha(
        db, usuario_actual.id, fecha, desde, hasta
    )
    return {"ventas": ventas, "ganancia_total": ganancia}


@router.get("/resumen", response_model=ResumenVentasOut)
def resumen(
    dias: int = Query(default=14, ge=1, le=90),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Totales por día para el panel, en una sola petición.

    Reemplaza el patrón de llamar a GET /ventas?fecha=... una vez por día.
    El tope de 90 días evita que alguien pida /resumen?dias=100000 y se
    lleve la base por delante.
    """
    return venta_service.resumen_ultimos_dias(db, usuario_actual.id, dias)


@router.get("/ganancia-hoy", response_model=GananciaOut)
def ganancia_hoy(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    ganancia = venta_service.ganancia_hoy(db, usuario_actual.id)
    return {"fecha": hoy_local(), "ganancia_total": ganancia}


@router.delete("/{venta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    venta_id: str,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    venta_service.eliminar_venta(db, usuario_actual.id, venta_id)