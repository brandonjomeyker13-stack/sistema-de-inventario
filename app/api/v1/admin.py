"""
app/api/v1/admin.py — El panel con el que llevamos las cuentas.

Existe para no entrar a Supabase a cambiar fechas a mano. Editar la base
directamente para cobrar tiene tres problemas: es fácil equivocarse de
fila, no queda rastro de quién lo hizo, y obliga a darle acceso a la base a
quien solo necesita cobrar.

ESTE ES EL ÚNICO ROUTER QUE VE DATOS DE OTROS NEGOCIOS

En todo el resto del proyecto la seguridad no depende de una comprobación:
depende de que cada consulta lleve `usuario_id` y no pueda alcanzar filas
ajenas. Aquí la única barrera es `exigir_admin`, y por eso va declarada en
el router entero — si mañana alguien agrega una ruta y se olvida de
protegerla, queda protegida igual.

Lo que NO hay aquí, a propósito: nada que devuelva las ventas, los
productos o los fiados de un cliente. El panel muestra el estado de la
cuenta, no lo que vende. Que nosotros mantengamos el sistema no nos da
derecho a mirar su negocio.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import exigir_admin
from app.database.session import get_db
from app.models.usuario import Usuario
from app.schemas.admin import (
    CambiarActivo, CambiarAdmin, CambiarSuscripcion,
    ListaNegociosOut, NegocioDetalleOut, RegistroAdminOut,
)
from app.services import admin_service

# La dependencia va en el router y no endpoint por endpoint a propósito: es
# la única barrera que separa el panel de los datos de todos los clientes, y
# no puede depender de que alguien se acuerde de ponerla.
router = APIRouter(
    prefix="/admin",
    tags=["Administración"],
    dependencies=[Depends(exigir_admin)],
)


@router.get("/negocios", response_model=ListaNegociosOut)
def listar_negocios(
    q: str | None = Query(default=None, description="Busca por nombre o correo"),
    db: Session = Depends(get_db),
):
    """Todas las cuentas, con su estado y los recuentos de arriba.

    `por_vencer` es el número que se mira cada semana: a cuántos hay que
    cobrarles antes del lunes.

    Cada negocio trae además cuántos productos tiene y cuántas ventas hizo
    en la última semana. No es curiosidad: un negocio con cero productos a
    los tres días de registrarse es alguien a quien hay que llamar, no
    esperar a que se le acabe la prueba.
    """
    return admin_service.listar_negocios(db, q)


@router.get("/negocios/{usuario_id}", response_model=NegocioDetalleOut)
def obtener_negocio(usuario_id: str, db: Session = Depends(get_db)):
    """Una cuenta, con el historial de lo que se le ha hecho."""
    return admin_service.obtener_negocio(db, usuario_id)


@router.put("/negocios/{usuario_id}/suscripcion", response_model=NegocioDetalleOut)
def cambiar_suscripcion(
    usuario_id: str,
    datos: CambiarSuscripcion,
    admin: Usuario = Depends(exigir_admin),
    db: Session = Depends(get_db),
):
    """Le pone la fecha hasta la que puede usar la aplicación completa.

    Con `hasta: null` se le quita la suscripción, que es como se marca a
    quien dejó de pagar. Sigue entrando y viendo sus datos en solo lectura;
    lo que no puede es registrar ventas.

    NO le devuelve los días de prueba: esos viven en otra columna y ya
    quedaron en el pasado.

    Rechaza fechas anteriores a hoy. Poner una fecha pasada siempre es un
    dedazo, y el efecto —dejar al cliente sin poder vender— se nota al
    instante y sin explicación posible.

    Todo cambio queda en la bitácora con quién lo hizo y la nota.
    """
    return admin_service.cambiar_suscripcion(db, admin, usuario_id, datos.hasta, datos.nota)


@router.put("/negocios/{usuario_id}/activo", response_model=NegocioDetalleOut)
def cambiar_activo(
    usuario_id: str,
    datos: CambiarActivo,
    admin: Usuario = Depends(exigir_admin),
    db: Session = Depends(get_db),
):
    """Habilita o deshabilita la cuenta entera.

    Es distinto de quitarle la suscripción: sin suscripción sigue entrando
    en solo lectura, deshabilitada no puede ni entrar. Para casos serios,
    no para cobrar.
    """
    return admin_service.cambiar_activo(db, admin, usuario_id, datos.activo, datos.nota)


@router.put("/negocios/{usuario_id}/admin", response_model=NegocioDetalleOut)
def cambiar_admin(
    usuario_id: str,
    datos: CambiarAdmin,
    admin: Usuario = Depends(exigir_admin),
    db: Session = Depends(get_db),
):
    """Da o quita permisos de administrador.

    Existe para que el primer admin —marcado a mano en la base— pueda
    marcar a su socio sin volver a entrar a Supabase.

    No te puedes quitar el permiso a ti mismo: si fueras el único
    administrador, el panel quedaría inaccesible para todos y habría que
    recuperarlo desde la base a mano.
    """
    return admin_service.cambiar_admin(db, admin, usuario_id, datos.es_admin, datos.nota)


@router.get("/bitacora", response_model=list[RegistroAdminOut])
def bitacora(
    limite: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Todo lo que se ha hecho últimamente, de lo más reciente hacia atrás.

    Es la vista que permite que dos socios estén al día de lo que hizo el
    otro sin tener que preguntárselo — y que, el día que discrepen sobre si
    a un cliente ya se le cobró, haya un dato en vez de dos memorias.
    """
    return admin_service.bitacora(db, limite)
