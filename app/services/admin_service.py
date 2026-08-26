"""
app/services/admin_service.py — El panel con el que llevamos las cuentas.

Existe para no tener que entrar a Supabase a cambiar fechas a mano. Editar
la base de datos directamente para cobrar tiene tres problemas: es fácil
equivocarse de fila, no queda rastro de quién lo hizo, y obliga a darle
acceso a la base a quien solo necesita cobrar.

QUÉ MUESTRA Y QUÉ NO

Muestra el ESTADO de cada cuenta: si paga, hasta cuándo, si usa la
aplicación. NO muestra lo que vende, ni sus productos, ni sus fiados. Los
datos de una tienda son de esa tienda, y el hecho de que nosotros
mantengamos el sistema no nos da derecho a mirarlos.

Si algún día hace falta entrar a la cuenta de un cliente para resolverle un
problema, eso es otra cosa: se le pide permiso y se hace con él delante.
"""

from sqlalchemy.orm import Session

from app.api.deps import estado_acceso
from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.core.fechas import fecha_valida, hoy_local, normalizar_fecha, sumar_dias
from app.models.registro_admin import CAMBIO_ACTIVO, CAMBIO_ADMIN, CAMBIO_SUSCRIPCION
from app.repositories import admin_repository

# Ventana de "se vence pronto": los que hay que llamar esta semana.
DIAS_POR_VENCER = 7

# Cuántos días de ventas se miran para saber si la cuenta está viva.
DIAS_DE_USO = 7


def _vista(usuario, uso: dict) -> dict:
    """Una cuenta como la ve el panel."""
    estado = estado_acceso(usuario)

    if estado["activa"] and estado["en_prueba"]:
        situacion = "prueba"
    elif estado["activa"]:
        situacion = "pagando"
    elif usuario.suscripcion_hasta:
        situacion = "vencida"      # fue cliente y dejó de pagar
    else:
        situacion = "sin_pagar"    # se le acabó la prueba y nunca pagó

    return {
        "id": usuario.id,
        "nombre_negocio": usuario.nombre_negocio,
        "email": usuario.email,
        "sector": usuario.sector,
        "situacion": situacion,
        "dias_restantes": estado["dias_restantes"],
        "suscripcion_hasta": usuario.suscripcion_hasta,
        "prueba_hasta": usuario.prueba_hasta,
        "activo": usuario.activo,
        "email_verificado": usuario.email_verificado,
        "es_admin": usuario.es_admin,
        "creado_en": usuario.creado_en,
        # Lo que distingue a un cliente que usa la aplicación de uno que se
        # registró y la abandonó. Un negocio con cero productos a los tres
        # días es alguien a quien hay que llamar, no esperar.
        "productos": uso.get("productos", 0),
        "ventas_ultimos_dias": uso.get("ventas_recientes", 0),
        # Se le acaba esta semana: es la lista de a quién cobrarle.
        "por_vencer": estado["activa"] and estado["dias_restantes"] <= DIAS_POR_VENCER,
    }


def listar_negocios(db: Session, q: str | None = None) -> dict:
    negocios = admin_repository.listar_negocios(db, q)
    uso = admin_repository.conteos_de_uso(db, sumar_dias(-DIAS_DE_USO))

    vistas = [_vista(u, uso.get(u.id, {})) for u in negocios]

    return {
        "total": len(vistas),
        "pagando": sum(1 for v in vistas if v["situacion"] == "pagando"),
        "en_prueba": sum(1 for v in vistas if v["situacion"] == "prueba"),
        "vencidas": sum(1 for v in vistas if v["situacion"] in ("vencida", "sin_pagar")),
        "por_vencer": sum(1 for v in vistas if v["por_vencer"]),
        "negocios": vistas,
    }


def obtener_negocio(db: Session, usuario_id: str) -> dict:
    usuario = admin_repository.obtener_negocio(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Ese negocio no existe")

    uso = admin_repository.conteos_de_uso(db, sumar_dias(-DIAS_DE_USO))
    vista = _vista(usuario, uso.get(usuario.id, {}))
    vista["historial"] = admin_repository.historial(db, usuario_id, limite=50)
    return vista


def cambiar_suscripcion(db: Session, admin, usuario_id: str,
                        hasta: str | None, nota: str | None = None) -> dict:
    """Le pone (o le quita) la fecha hasta la que puede usar la aplicación.

    `hasta` en None deja la cuenta sin suscripción, que es como se marca a
    quien dejó de pagar. Ojo: eso NO le devuelve los días de prueba —
    `prueba_hasta` está en otra columna y ya quedó en el pasado.
    """
    usuario = admin_repository.obtener_negocio(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Ese negocio no existe")

    if hasta is not None:
        try:
            hasta = normalizar_fecha(hasta)
        except ValueError as e:
            raise ErrorNegocio(str(e))
        if hasta < hoy_local():
            # Se permite igualarla a hoy (vence al final del día), pero no
            # ponerla en el pasado: eso es siempre un dedazo, y el efecto
            # —dejar al cliente sin vender— se nota al instante y sin
            # explicación posible.
            raise ErrorNegocio(
                f"Esa fecha ya pasó ({hasta}). Para cortarle el acceso, deja la "
                "suscripción vacía."
            )

    antes = usuario.suscripcion_hasta
    usuario.suscripcion_hasta = hasta

    admin_repository.registrar_cambio(
        db, admin.id, usuario, CAMBIO_SUSCRIPCION, antes, hasta, nota,
    )
    db.commit()

    return obtener_negocio(db, usuario_id)


def cambiar_activo(db: Session, admin, usuario_id: str, activo: bool,
                   nota: str | None = None) -> dict:
    """Habilita o deshabilita la cuenta entera.

    Distinto de quitarle la suscripción: sin suscripción sigue entrando y
    viendo sus datos en solo lectura; deshabilitada no puede ni entrar. Es
    para casos serios, no para cobrar.
    """
    usuario = admin_repository.obtener_negocio(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Ese negocio no existe")

    if usuario.id == admin.id and not activo:
        raise ErrorNegocio("No puedes deshabilitar tu propia cuenta")

    antes = usuario.activo
    usuario.activo = activo

    admin_repository.registrar_cambio(
        db, admin.id, usuario, CAMBIO_ACTIVO, str(antes), str(activo), nota,
    )
    db.commit()

    return obtener_negocio(db, usuario_id)


def cambiar_admin(db: Session, admin, usuario_id: str, es_admin: bool,
                  nota: str | None = None) -> dict:
    """Da o quita permisos de administrador.

    Existe para que el primer admin —marcado a mano en la base— pueda
    marcar al socio sin volver a entrar a Supabase.
    """
    usuario = admin_repository.obtener_negocio(db, usuario_id)
    if not usuario:
        raise NoEncontrado("Ese negocio no existe")

    if usuario.id == admin.id and not es_admin:
        # Sin esto, quitarse el permiso a uno mismo siendo el único admin
        # dejaría el panel inaccesible para todos, y habría que volver a
        # entrar a Supabase a mano para recuperarlo.
        raise ErrorNegocio(
            "No puedes quitarte a ti mismo el permiso de administrador. "
            "Pídeselo a otro administrador."
        )

    antes = usuario.es_admin
    usuario.es_admin = es_admin

    admin_repository.registrar_cambio(
        db, admin.id, usuario, CAMBIO_ADMIN, str(antes), str(es_admin), nota,
    )
    db.commit()

    return obtener_negocio(db, usuario_id)


def bitacora(db: Session, limite: int = 100) -> list:
    """Todo lo que se ha hecho últimamente, de lo más reciente hacia atrás.

    Es la vista que permite que dos socios estén al día de lo que hizo el
    otro sin tener que preguntárselo.
    """
    return admin_repository.historial(db, None, limite)
