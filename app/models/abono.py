"""
app/models/abono.py — Los pagos parciales contra una venta fiada.

Un fiado no se paga de golpe: doña Rosa debe 40 mil y va abonando 10 mil
el viernes, 15 el otro. Cada uno de esos pagos es una fila aquí.

Decisión importante: el saldo pendiente NO se guarda en `ventas`. Se
calcula como `precio_venta_total - suma(abonos)`. Un saldo almacenado se
desincroniza en cuanto un abono se registre mal, se borre, o dos
peticiones lleguen a la vez — y en ese momento el sistema le estaría
diciendo al tendero que le deben una cifra que no es. Calculado siempre
cuadra, y con una tabla de este tamaño el coste es irrelevante.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Float, DateTime, ForeignKey

from app.database.session import Base


class Abono(Base):
    __tablename__ = "abonos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    venta_id = Column(String(36), ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False, index=True)
    monto = Column(Float, nullable=False)
    # Fecha del negocio, igual que en ventas (ver app/core/fechas.py).
    fecha = Column(String(10), nullable=False)
    nota = Column(String(255), nullable=True)
    creado_en = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
