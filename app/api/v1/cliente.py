"""
app/api/v1/cliente.py — Clientes y la libreta de fiados.

`/fiados` va aquí y no en un router aparte porque un fiado siempre es de
un cliente: separarlos obligaría al frontend a cruzar dos recursos para
pintar una sola pantalla.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual
from app.models.usuario import Usuario
from app.schemas.cliente import (
    ClienteCrear, ClienteActualizar, ClienteOut, DeudorOut, DetalleFiadosOut,
    AbonoCrear, AbonoOut,
)
from app.services import cliente_service

router = APIRouter(tags=["Clientes y fiados"])


@router.get("/clientes", response_model=list[ClienteOut])
def listar(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return cliente_service.listar(db, usuario_actual.id)


@router.post("/clientes", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def agregar(
    datos: ClienteCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return cliente_service.agregar(db, usuario_actual.id, datos.nombre, datos.telefono, datos.notas,
                                   datos.dias_plazo)


@router.put("/clientes/{cliente_id}", response_model=ClienteOut)
def editar(
    cliente_id: str,
    datos: ClienteActualizar,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    return cliente_service.editar(
        db, usuario_actual.id, cliente_id, datos.nombre, datos.telefono, datos.notas,
        datos.dias_plazo,
    )


@router.delete("/clientes/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(
    cliente_id: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Falla con 400 si el cliente todavía debe algo: borrarlo escondería
    la deuda en vez de resolverla."""
    cliente_service.eliminar(db, usuario_actual.id, cliente_id)


@router.get("/fiados", response_model=list[DeudorOut])
def libreta(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Quién debe y cuánto, de mayor a menor deuda. Solo aparece quien
    tiene saldo pendiente; los que ya pagaron no ensucian la pantalla."""
    return cliente_service.libreta_de_fiados(db, usuario_actual.id)


@router.get("/fiados/{cliente_id}", response_model=DetalleFiadosOut)
def detalle(
    cliente_id: str,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Las ventas fiadas de un cliente, incluidas las ya saldadas, con lo
    abonado y lo que falta en cada una."""
    return cliente_service.detalle_fiados(db, usuario_actual.id, cliente_id)


@router.post("/ventas/{venta_id}/abonos", response_model=AbonoOut,
             status_code=status.HTTP_201_CREATED)
def abonar(
    venta_id: str,
    datos: AbonoCrear,
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Registra un pago parcial contra una venta fiada. Rechaza abonos
    mayores que el saldo: un dedazo no puede dejar la deuda en negativo."""
    return cliente_service.registrar_abono(
        db, usuario_actual.id, venta_id, datos.monto, datos.nota
    )
