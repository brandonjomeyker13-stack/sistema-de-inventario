"""
app/api/v1/analitica.py — Análisis del propio negocio.

Todo lo de aquí funciona con UNA sola tienda desde el primer día. El
análisis comparado entre negocios del mismo sector es otra cosa y todavía
no existe: necesita varios negocios por sector para no ser engañoso, y un
umbral mínimo para que nadie pueda deducir las cifras de su competencia.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.api.deps import obtener_usuario_actual, exigir_suscripcion_activa
from app.models.usuario import Usuario
from app.schemas.analitica import (
    ResumenAnaliticaOut, ProductoRankingOut, CapitalParadoOut,
    AlertaAgotarseOut, DiaSemanaOut, ListaDeCompraOut,
)
from app.services import analitica_service

# Todo el análisis exige suscripción al día: es la parte que se vende, no
# el registro de ventas. Va en el router y no endpoint por endpoint porque
# aquí no hay excepciones — si mañana se agrega otra ruta, queda protegida
# sin que nadie tenga que acordarse.
router = APIRouter(
    prefix="/analitica",
    tags=["Análisis"],
    dependencies=[Depends(exigir_suscripcion_activa)],
)


@router.get("/resumen", response_model=ResumenAnaliticaOut)
def resumen(
    dias: int = Query(default=30, ge=1, le=365),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Toda la pantalla de análisis en una petición."""
    return analitica_service.resumen(db, usuario_actual.id, dias)


@router.get("/mas-vendidos", response_model=list[ProductoRankingOut])
def mas_vendidos(
    dias: int = Query(default=30, ge=1, le=365),
    por: str = Query(default="unidades", pattern="^(unidades|ingresos|ganancia)$"),
    limite: int = Query(default=10, ge=1, le=100),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Ranking de productos. Ordenar por `ganancia` en vez de `unidades`
    suele contar una historia distinta, y más útil."""
    return analitica_service.mas_vendidos(db, usuario_actual.id, dias, por, limite)


@router.get("/capital-parado", response_model=CapitalParadoOut)
def capital_parado(
    dias: int = Query(default=60, ge=7, le=365),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Productos sin venderse en `dias`, y cuánto dinero representan al
    costo. Incluye los que nunca se han vendido."""
    return analitica_service.capital_parado(db, usuario_actual.id, dias)


@router.get("/por-agotarse", response_model=list[AlertaAgotarseOut])
def por_agotarse(
    dias_historial: int = Query(default=30, ge=7, le=365),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Qué se acaba pronto según el ritmo de venta reciente."""
    return analitica_service.por_agotarse(db, usuario_actual.id, dias_historial)


@router.get("/que-comprar", response_model=ListaDeCompraOut)
def que_comprar(
    dias_historial: int = Query(default=30, ge=7, le=365),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """La lista de lo que hay que pedirle al proveedor.

    Junta las dos señales, porque cada una sola tiene un punto ciego:

      · Le quedan menos unidades que su mínimo. Sirve desde el primer día y
        es la única que ve un producto sin historial de ventas — uno nuevo
        se agotaría en silencio con solo la otra señal.
      · Al ritmo al que se vende, se acaba esta semana. Ve venir el
        problema antes de llegar al mínimo.

    `texto` viene lista para pegar en WhatsApp y mandársela al proveedor.
    Es el mismo texto que devuelve el asistente si se le pregunta, para que
    la pantalla y el chat no puedan contradecirse.

    No sugiere CUÁNTO comprar a propósito: el tendero pide por bulto, por
    caja de veinticuatro o por paca según lo que le venda su proveedor. Se
    le dan los datos y decide él, que es quien sabe.
    """
    return analitica_service.que_comprar(db, usuario_actual.id, dias_historial)


@router.get("/dias-fuertes", response_model=list[DiaSemanaOut])
def dias_fuertes(
    dias: int = Query(default=90, ge=7, le=365),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
    db: Session = Depends(get_db),
):
    """Promedio de venta por día de la semana."""
    return analitica_service.dias_fuertes(db, usuario_actual.id, dias)
