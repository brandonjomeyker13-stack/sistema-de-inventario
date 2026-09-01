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
    CambiarActivo, CambiarAdmin, CambiarSuscripcion, ConsultaOut,
    EtiquetaOut, EtiquetarConsulta, ListaConsultasOut,
    ListaNegociosOut, ListaValoracionesOut, NegocioDetalleOut,
    RegistroAdminOut, RevisarValoracion, ValoracionOut,
)
from app.services import admin_service, consulta_service, valoracion_service

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


# --- Las preguntas que le hacen a Trackie --------------------------------
#
# Esta parte del panel no sirve para cobrar: sirve para que Trackie deje de
# costar. Cada pregunta que el enrutador no reconoce se responde con el
# modelo, y eso cuesta tokens y una espera. Etiquetándolas se sabe cuáles
# vale la pena reconocer, y se va armando el conjunto con el que algún día
# se entrena un clasificador propio.


@router.get("/consultas", response_model=ListaConsultasOut)
def listar_consultas(
    estado: str | None = Query(default=None, description="pendiente | etiquetada | descartada"),
    sin_reconocer: bool = Query(default=False, description="Solo las que el enrutador no supo"),
    limite: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Las preguntas, lo más preguntado primero.

    `sin_reconocer=true` deja solo las que hoy cuestan tokens. Es la vista
    por la que conviene empezar: etiquetar la pregunta que se hizo cuarenta
    veces vale cuarenta veces más que etiquetar la que se hizo una.
    """
    return consulta_service.listar(db, estado, sin_reconocer, limite)


@router.get("/consultas/etiquetas", response_model=list[EtiquetaOut])
def etiquetas_disponibles(db: Session = Depends(get_db)):
    """Con qué se puede etiquetar, y cuántos ejemplos lleva cada una.

    El número importa tanto como la lista: un conjunto con mil ejemplos de
    una intención y tres de otra no sirve para entrenar, y eso solo se ve
    mirándolos juntos.
    """
    return consulta_service.etiquetas(db)


@router.put("/consultas/{consulta_id}/etiqueta", response_model=ConsultaOut)
def etiquetar_consulta(
    consulta_id: str,
    datos: EtiquetarConsulta,
    admin: Usuario = Depends(exigir_admin),
    db: Session = Depends(get_db),
):
    """Le pone a una pregunta la intención que de verdad tenía.

    Solo se aceptan intenciones del catálogo cerrado, más "ninguna". Con
    etiquetas libres, el conjunto acabaría con "compras", "compra" y
    "lista_compra" como si fueran tres cosas distintas, y eso no tiene
    arreglo después.
    """
    return consulta_service.etiquetar(db, admin, consulta_id, datos.intencion)


@router.put("/consultas/{consulta_id}/descartar", response_model=ConsultaOut)
def descartar_consulta(
    consulta_id: str,
    admin: Usuario = Depends(exigir_admin),
    db: Session = Depends(get_db),
):
    """La pregunta no sirve ni como ejemplo: una prueba, un pegado, ruido.

    No se borra a propósito. Borrada, la siguiente vez que alguien la
    escribiera volvería a la bandeja y habría que descartarla otra vez.
    """
    return consulta_service.descartar(db, admin, consulta_id)


@router.put("/consultas/{consulta_id}/reabrir", response_model=ConsultaOut)
def reabrir_consulta(
    consulta_id: str,
    admin: Usuario = Depends(exigir_admin),
    db: Session = Depends(get_db),
):
    """Deshace una etiqueta puesta por error. Vuelve a la bandeja."""
    return consulta_service.reabrir(db, admin, consulta_id)


@router.get("/valoraciones", response_model=ListaValoracionesOut)
def listar_valoraciones(
    valoracion: str | None = Query(default=None, description="buena | mala"),
    estado: str | None = Query(default=None, description="pendiente | revisada"),
    limite: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Lo que los tenderos calificaron, lo más reciente primero.

    Empezar por `valoracion=mala&estado=pendiente`: son las quejas sin
    atender, y cada una viene del único que puede saber si la respuesta era
    cierta — el dueño mirando su propia estantería.
    """
    return valoracion_service.listar(db, valoracion, estado, limite)


@router.put("/valoraciones/{valoracion_id}/revisar", response_model=ValoracionOut)
def revisar_valoracion(
    valoracion_id: str,
    datos: RevisarValoracion,
    admin: Usuario = Depends(exigir_admin),
    db: Session = Depends(get_db),
):
    """Marca la queja como atendida, y de paso la etiqueta si procede.

    Etiquetarla es lo que la convierte en un ejemplo de entrenamiento: una
    queja con su intención correcta vale más que una pregunta etiquetada a
    ojo desde el panel, porque viene con la prueba de que estaba mal.
    """
    return valoracion_service.revisar(db, admin, valoracion_id, datos.intencion_correcta)
