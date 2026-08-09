"""
app/services/cliente_service.py — Clientes y la libreta de fiados.

Aquí vive la regla que protege al tendero de sí mismo: no se puede abonar
más de lo que se debe. Sin esa validación, un dedazo (50000 en vez de
5000) dejaría un saldo negativo y la deuda del cliente desaparecería sin
que nadie se entere.
"""

from sqlalchemy.orm import Session

from app.core.exceptions import ErrorNegocio, NoEncontrado
from app.core.fechas import hoy_local
from app.repositories import cliente_repository, venta_repository


def listar(db: Session, usuario_id: str):
    return cliente_repository.listar(db, usuario_id)


def obtener(db: Session, usuario_id: str, cliente_id: str):
    cliente = cliente_repository.obtener_por_id(db, usuario_id, cliente_id)
    if not cliente:
        raise NoEncontrado("Cliente no encontrado")
    return cliente


def agregar(db: Session, usuario_id: str, nombre: str, telefono: str | None, notas: str | None):
    if cliente_repository.existe_nombre(db, usuario_id, nombre):
        raise ErrorNegocio(f"Ya tienes un cliente llamado '{nombre.strip()}'")
    return cliente_repository.crear(db, usuario_id, nombre, telefono, notas)


def editar(db: Session, usuario_id: str, cliente_id: str, nombre: str,
           telefono: str | None, notas: str | None):
    cliente = obtener(db, usuario_id, cliente_id)
    if cliente_repository.existe_nombre(db, usuario_id, nombre, excluir_id=cliente_id):
        raise ErrorNegocio(f"Ya tienes otro cliente llamado '{nombre.strip()}'")
    return cliente_repository.actualizar(db, cliente, nombre, telefono, notas)


def eliminar(db: Session, usuario_id: str, cliente_id: str):
    cliente = obtener(db, usuario_id, cliente_id)
    deudas = cliente_repository.deuda_por_cliente(db, usuario_id)
    pendiente = next((d for d in deudas if d["cliente_id"] == cliente_id), None)
    if pendiente:
        # Borrarlo escondería una deuda viva. Que el tendero decida:
        # o le perdona el saldo registrando un abono, o lo conserva.
        raise ErrorNegocio(
            f"No puedes borrar a {cliente.nombre}: todavía debe "
            f"{pendiente['deuda_total']:.0f}. Salda la deuda primero."
        )
    cliente_repository.eliminar(db, cliente)


def libreta_de_fiados(db: Session, usuario_id: str):
    """Quién debe y cuánto. Es la pantalla que reemplaza el cuaderno."""
    return cliente_repository.deuda_por_cliente(db, usuario_id)


def detalle_fiados(db: Session, usuario_id: str, cliente_id: str):
    cliente = obtener(db, usuario_id, cliente_id)
    ventas = cliente_repository.ventas_fiadas_de_cliente(db, usuario_id, cliente_id)
    return {
        "cliente": cliente,
        "ventas": ventas,
        "deuda_total": round(sum(v.saldo_pendiente for v in ventas), 2),
    }


def registrar_abono(db: Session, usuario_id: str, venta_id: str, monto: float, nota: str | None):
    venta = venta_repository.obtener_por_id(db, usuario_id, venta_id)
    if not venta:
        raise NoEncontrado("Venta no encontrada")
    if not venta.es_fiado:
        raise ErrorNegocio("Esa venta no fue fiada, no hay nada que abonar")

    saldo = venta.saldo_pendiente
    if saldo <= 0:
        raise ErrorNegocio("Esa venta ya está saldada")
    if monto > saldo:
        raise ErrorNegocio(
            f"El abono ({monto:.0f}) es mayor que lo que se debe ({saldo:.0f})"
        )

    return cliente_repository.crear_abono(db, venta, round(monto, 2), hoy_local(), nota)
