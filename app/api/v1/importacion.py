"""
app/api/v1/importacion.py — Cargar el inventario desde una plantilla.

Dos endpoints y ninguno guarda estado entre llamadas:

  POST /importacion/previsualizar   dice qué pasaría, sin tocar nada
  POST /importacion/aplicar         lo hace

EL ARCHIVO LO LEE EL FRONTEND. Aquí no llega un Excel, llegan las filas ya
convertidas a JSON, con cada celda TAL CUAL salió del archivo (sin limpiar
ni convertir). Así el servidor no tiene que manejar subidas, ni límites de
tamaño, ni parsear un Excel grande en la poca memoria del plan gratuito.

Pero los NÚMEROS los interpreta el backend, no el frontend: entender que
"1.500" son mil quinientos y no uno con cinco es una regla de negocio. Si
viviera en la interfaz habría que mantenerla en dos sitios, y el día que se
desincronicen una tienda queda con los precios divididos por mil.

Como no hay estado, el frontend debe conservar las filas entre la vista
previa y la confirmación, y mandar LAS MISMAS. `aplicar` vuelve a validar
todo de todas formas: entre las dos llamadas el inventario pudo cambiar
desde otra pestaña o desde el celular.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import limites, plantilla
from app.database.session import get_db
from app.api.deps import exigir_suscripcion_activa, obtener_usuario_actual
from app.models.usuario import Usuario
from app.schemas.importacion import (
    PeticionImportar, ResumenImportacion, ResultadoImportacion,
)
from app.services import importacion_service

router = APIRouter(prefix="/importacion", tags=["Importación"])

# Content-type oficial de los .xlsx. Con uno equivocado, algunos navegadores
# guardan el archivo como .zip o lo abren como texto.
TIPO_EXCEL = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/plantilla")
def descargar_plantilla(
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
):
    """Descarga el Excel para llenar con el inventario.

    La genera el backend y no el frontend a propósito: los encabezados salen
    de la MISMA clase con la que el importador lee el archivo, así que no
    pueden desincronizarse. Ver app/core/plantilla.py.

    Va con `obtener_usuario_actual` y no con `exigir_suscripcion_activa`:
    una cuenta en solo lectura no puede importar todavía, pero sí tiene
    sentido que prepare el archivo mientras resuelve el pago.

    Trae dos hojas: "Productos" (solo los títulos, para llenar) e
    "Instrucciones" (qué va en cada columna, con ejemplos). Los ejemplos van
    en la segunda hoja a propósito — si estuvieran en la primera y el
    tendero olvidara borrarlos, se importarían como productos reales.
    """
    return Response(
        content=plantilla.generar(),
        media_type=TIPO_EXCEL,
        headers={
            # `attachment` fuerza la descarga en vez de que el navegador
            # intente mostrarlo.
            "Content-Disposition": f'attachment; filename="{plantilla.NOMBRE_ARCHIVO}"',
        },
    )


@router.post("/previsualizar", response_model=ResumenImportacion)
def previsualizar(
    datos: PeticionImportar,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Dice exactamente qué pasaría, sin guardar nada.

    Devuelve cuántos productos se crearían, cuáles se actualizarían (con el
    valor de antes al lado del nuevo, para poder frenar si algo se ve mal),
    las filas con problemas y los avisos.

    `se_puede_importar` es lo que el frontend debe mirar para habilitar el
    botón de confirmar. Con una sola fila mala no se importa nada.
    """
    limites.exigir(
        f"importar:{usuario_actual.id}", maximo=30, segundos=300,
        mensaje="Demasiadas revisiones seguidas del archivo. Espera un momento.",
    )
    return importacion_service.analizar(
        db, usuario_actual.id, datos.filas, datos.permitir_perdida,
    )


@router.post("/aplicar", response_model=ResultadoImportacion)
def aplicar(
    datos: PeticionImportar,
    usuario_actual: Usuario = Depends(exigir_suscripcion_activa),
    db: Session = Depends(get_db),
):
    """Carga la plantilla de verdad. Todo en una sola transacción.

    Falla con 400 si alguna fila tiene problemas, y no importa ninguna: una
    carga a medias deja al tendero sin saber qué entró, y al reintentar
    duplicaría lo que ya estaba.

    Los productos que ya existen (mismo nombre) se ACTUALIZAN: cantidad,
    precio y costo. No se les toca el código de barras — la plantilla no lo
    trae y el tendero ya se los fue poniendo escaneando.
    """
    limites.exigir(
        f"importar-aplicar:{usuario_actual.id}", maximo=10, segundos=300,
        mensaje="Demasiadas importaciones seguidas. Espera un momento.",
    )
    return importacion_service.importar(
        db, usuario_actual.id, datos.filas, datos.permitir_perdida,
    )
