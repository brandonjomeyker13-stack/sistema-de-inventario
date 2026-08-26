"""
app/repositories/admin_repository.py — Consultas del panel de administración.

Es el ÚNICO repositorio que no filtra por usuario_id, porque su trabajo es
justamente ver todas las cuentas. Quien lo llame tiene que haber pasado por
`deps.exigir_admin` — no hay otra barrera.

Lo que NO hay aquí, a propósito: nada que devuelva las ventas, los
productos o los fiados de un negocio. El panel muestra el ESTADO de la
cuenta (si paga, hasta cuándo, si la usa), no lo que vende. Los datos de
una tienda son de esa tienda.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.registro_admin import RegistroAdmin
from app.models.producto import Producto
from app.models.usuario import Usuario
from app.models.venta import Venta


def listar_negocios(db: Session, q: str | None = None) -> list[Usuario]:
    """Todas las cuentas, opcionalmente filtradas por nombre o correo.

    Sin paginar: son las cuentas de clientes, y el día que sean tantas que
    no quepan en una pantalla será una buena noticia que ya justificará
    paginarlo.
    """
    query = db.query(Usuario)
    if q:
        termino = f"%{q.strip()}%"
        query = query.filter(
            Usuario.nombre_negocio.ilike(termino) | Usuario.email.ilike(termino)
        )
    return query.order_by(Usuario.creado_en.desc()).all()


def obtener_negocio(db: Session, usuario_id: str) -> Usuario | None:
    return db.query(Usuario).filter(Usuario.id == usuario_id).first()


def conteos_de_uso(db: Session, desde: str) -> dict[str, dict]:
    """Cuántos productos tiene cada negocio y cuántas ventas hizo desde
    `desde`, indexado por usuario_id.

    Es lo que distingue a un cliente que USA la aplicación de uno que se
    registró y la abandonó — y por tanto a quién hay que llamar antes de
    que se le acabe la prueba.

    Van en DOS consultas agrupadas y no una por negocio: con cincuenta
    cuentas, eso serían cien idas a Supabase para pintar una lista.
    """
    productos = dict(
        db.query(Producto.usuario_id, func.count(Producto.id))
        .filter(Producto.eliminado.is_(False))
        .group_by(Producto.usuario_id)
        .all()
    )
    ventas = dict(
        db.query(Venta.usuario_id, func.count(Venta.id))
        .filter(Venta.eliminado.is_(False), Venta.fecha >= desde)
        .group_by(Venta.usuario_id)
        .all()
    )

    return {
        usuario_id: {
            "productos": int(productos.get(usuario_id, 0)),
            "ventas_recientes": int(ventas.get(usuario_id, 0)),
        }
        for usuario_id in set(productos) | set(ventas)
    }


def registrar_cambio(db: Session, admin_id: str, usuario_id: str, accion: str,
                     antes: str | None, despues: str | None,
                     nota: str | None) -> RegistroAdmin:
    """Anota un cambio en la bitácora. No hace commit: quien llama guarda
    el cambio y su registro en la misma transacción, para que no pueda
    quedar uno sin el otro."""
    registro = RegistroAdmin(
        admin_id=admin_id,
        usuario_id=usuario_id,
        accion=accion,
        valor_antes=antes,
        valor_despues=despues,
        nota=(nota or "").strip() or None,
    )
    db.add(registro)
    return registro


def historial(db: Session, usuario_id: str | None = None,
              limite: int = 100) -> list[RegistroAdmin]:
    """La bitácora, de lo más reciente a lo más antiguo.

    Sin `usuario_id` devuelve la de todos, que es la vista de "qué se ha
    hecho últimamente" — la que sirve para que dos socios estén al día de
    lo que hizo el otro.
    """
    query = db.query(RegistroAdmin)
    if usuario_id:
        query = query.filter(RegistroAdmin.usuario_id == usuario_id)
    return query.order_by(RegistroAdmin.creado_en.desc()).limit(limite).all()
