"""
app/repositories/cliente_repository.py — Acceso a datos de clientes y fiados.

Igual que el resto de repositorios: toda función recibe `usuario_id` y
filtra por él. Es la barrera que impide que un negocio vea la libreta de
deudores de otro.
"""

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.fechas import dias_de_atraso
from app.models.cliente import Cliente
from app.models.venta import Venta
from app.models.abono import Abono


def listar(db: Session, usuario_id: str) -> list[Cliente]:
    return (
        db.query(Cliente)
        .filter(Cliente.usuario_id == usuario_id, Cliente.eliminado.is_(False))
        .order_by(Cliente.nombre)
        .all()
    )


def obtener_por_id(db: Session, usuario_id: str, cliente_id: str) -> Cliente | None:
    return (
        db.query(Cliente)
        .filter(
            Cliente.id == cliente_id,
            Cliente.usuario_id == usuario_id,
            Cliente.eliminado.is_(False),
        )
        .first()
    )


def existe_nombre(db: Session, usuario_id: str, nombre: str, excluir_id: str | None = None) -> bool:
    query = db.query(Cliente).filter(
        Cliente.usuario_id == usuario_id,
        Cliente.eliminado.is_(False),
        Cliente.nombre.ilike(nombre.strip()),
    )
    if excluir_id:
        query = query.filter(Cliente.id != excluir_id)
    return db.query(query.exists()).scalar()


def crear(db: Session, usuario_id: str, nombre: str, telefono: str | None,
          notas: str | None, dias_plazo: int | None = None) -> Cliente:
    cliente = Cliente(
        usuario_id=usuario_id, nombre=nombre.strip(), telefono=telefono, notas=notas,
        dias_plazo=dias_plazo,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def actualizar(db: Session, cliente: Cliente, nombre: str, telefono: str | None,
               notas: str | None, dias_plazo: int | None = None) -> Cliente:
    cliente.nombre = nombre.strip()
    cliente.telefono = telefono
    cliente.notas = notas
    cliente.dias_plazo = dias_plazo
    db.commit()
    db.refresh(cliente)
    return cliente


def eliminar(db: Session, cliente: Cliente) -> None:
    cliente.eliminado = True
    db.commit()


def deuda_por_cliente(db: Session, usuario_id: str) -> list[dict]:
    """La libreta de deudores: cuánto debe cada cliente, en una consulta.

    El saldo es `total vendido a crédito - total abonado`. Los abonos se
    suman en una subconsulta agrupada por venta ANTES de unirse: si se
    hiciera con un JOIN directo, una venta con tres abonos se contaría
    tres veces en el total vendido y la deuda saldría inflada.

    Solo devuelve a quien debe algo. Un cliente que ya pagó todo no
    pertenece a la pantalla de fiados.
    """
    abonado = (
        db.query(
            Abono.venta_id.label("venta_id"),
            func.coalesce(func.sum(Abono.monto), 0).label("abonado"),
        )
        .group_by(Abono.venta_id)
        .subquery()
    )

    saldo = Venta.precio_venta_total - func.coalesce(abonado.c.abonado, 0)

    filas = (
        db.query(
            Cliente.id.label("cliente_id"),
            Cliente.nombre.label("nombre"),
            Cliente.telefono.label("telefono"),
            func.coalesce(func.sum(saldo), 0).label("deuda_total"),
            func.count(Venta.id).label("ventas_pendientes"),
            func.min(Venta.fecha).label("fiado_mas_antiguo"),
            # El vencimiento más próximo entre sus deudas vivas. MIN sobre
            # una columna de texto 'YYYY-MM-DD' ordena bien por ser ese
            # formato; los fiados sin plazo son NULL y MIN los ignora.
            func.min(Venta.fecha_vencimiento).label("vence"),
        )
        .join(Venta, Venta.cliente_id == Cliente.id)
        .outerjoin(abonado, abonado.c.venta_id == Venta.id)
        .filter(
            Cliente.usuario_id == usuario_id,
            Cliente.eliminado.is_(False),
            Venta.es_fiado.is_(True),
            Venta.eliminado.is_(False),
            saldo > 0,
        )
        .group_by(Cliente.id, Cliente.nombre, Cliente.telefono)
        .order_by(func.sum(saldo).desc())
        .all()
    )

    deudores = [
        {
            "cliente_id": f.cliente_id,
            "nombre": f.nombre,
            "telefono": f.telefono,
            "deuda_total": round(float(f.deuda_total), 2),
            "ventas_pendientes": int(f.ventas_pendientes),
            "fiado_mas_antiguo": f.fiado_mas_antiguo,
            "vence": f.vence,
            "dias_atraso": dias_de_atraso(f.vence),
        }
        for f in filas
    ]

    # Los atrasados primero, y entre ellos el que más días lleva. El
    # tendero abre esta pantalla para saber a quién cobrar hoy, no para
    # ver un ranking de montos: quien debe 5.000 desde hace un mes es más
    # urgente que quien debe 50.000 desde ayer.
    deudores.sort(key=lambda d: (-d["dias_atraso"], -d["deuda_total"]))
    return deudores


def ventas_fiadas_de_cliente(db: Session, usuario_id: str, cliente_id: str) -> list[Venta]:
    """Las ventas a crédito de un cliente, de la más reciente a la más
    antigua. Incluye las ya saldadas: el tendero necesita poder mirar el
    histórico, no solo lo que falta."""
    return (
        db.query(Venta)
        .filter(
            Venta.usuario_id == usuario_id,
            Venta.cliente_id == cliente_id,
            Venta.es_fiado.is_(True),
            Venta.eliminado.is_(False),
        )
        .order_by(Venta.fecha.desc(), Venta.creado_en.desc())
        .all()
    )


def crear_abono(db: Session, venta: Venta, monto: float, fecha: str, nota: str | None) -> Abono:
    abono = Abono(venta_id=venta.id, monto=monto, fecha=fecha, nota=nota)
    db.add(abono)
    db.commit()
    db.refresh(abono)
    return abono


def total_fiado_por_fechas(db: Session, usuario_id: str, fechas: list[str]) -> dict[str, float]:
    """Cuánto de lo vendido cada día se fió. Alimenta el resumen del panel:
    sin este dato, el tendero ve 'vendí 200 mil' y no entiende por qué en
    el cajón hay 120."""
    filas = (
        db.query(Venta.fecha, func.coalesce(func.sum(Venta.precio_venta_total), 0).label("fiado"))
        .filter(
            Venta.usuario_id == usuario_id,
            Venta.eliminado.is_(False),
            Venta.es_fiado.is_(True),
            Venta.fecha.in_(fechas),
        )
        .group_by(Venta.fecha)
        .all()
    )
    return {f.fecha: round(float(f.fiado), 2) for f in filas}
